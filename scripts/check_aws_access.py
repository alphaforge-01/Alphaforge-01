"""Vérification en lecture seule de l'accès AWS pour AlphaForge (tâche C1).

Ce script ne crée, ne modifie et ne supprime aucune ressource. Il vérifie :

1. que le compte répond (``sts get-caller-identity``) et que la région est
   bien celle attendue (``us-east-1`` par défaut), sans jamais afficher le
   numéro de compte ni l'ARN complet (ils sont masqués) ;
2. les modèles de fondation Bedrock en cycle de vie ``ACTIVE`` qui acceptent
   du texte en entrée et en sortie (condition nécessaire pour l'API Converse) ;
3. les profils d'inférence disponibles ;
4. en option (``--try-converse <model_id>``), UN appel Converse minimal avec un
   outil factice, pour vérifier la prise en charge des appels d'outils.

Les identifiants viennent uniquement de la chaîne par défaut de boto3
(variables d'environnement temporaires de l'atelier, profil AWS CLI ou rôle
IAM). Aucun identifiant de modèle n'est codé en dur : il est donné en argument
ou lu dans ``ALPHAFORGE_ANALYST_MODEL_ID``.

Usage (depuis la racine du projet, dans le terminal qui contient les
identifiants temporaires) ::

    python scripts/check_aws_access.py
    python scripts/check_aws_access.py --try-converse "$ALPHAFORGE_ANALYST_MODEL_ID"

Codes de sortie : 0 succès, 1 erreur AWS ou d'identifiants, 2 erreur de
configuration (région, modèle manquant).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import Any, Callable

EXPECTED_REGION_DEFAULT = "us-east-1"
MODEL_ENV_VAR = "ALPHAFORGE_ANALYST_MODEL_ID"

EXIT_OK = 0
EXIT_AWS_ERROR = 1
EXIT_CONFIG_ERROR = 2

# Codes d'erreur qui signalent des identifiants temporaires expirés ou invalides.
CREDENTIAL_ERROR_CODES = frozenset({
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "UnrecognizedClientException",
})
ACCESS_DENIED_CODES = frozenset({"AccessDeniedException", "AccessDenied"})
THROTTLING_CODES = frozenset({"ThrottlingException", "Throttling", "TooManyRequestsException"})

_ARN_RE = re.compile(r"arn:(aws[\w-]*):([\w-]+):([\w-]*):(\d{12})?:([^\s\"',]+)")
_ACCOUNT_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
_ACCESS_KEY_RE = re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{12,}\b")

ACCOUNT_MASK = "<compte masqué>"
RESOURCE_MASK = "<ressource masquée>"


# ---------------------------------------------------------------------------
# Masquage
# ---------------------------------------------------------------------------

def mask_account_id(account_id: str | None) -> str:
    """Masque entièrement un numéro de compte AWS."""
    return ACCOUNT_MASK if account_id else "<inconnu>"


def mask_arn(arn: str | None) -> str:
    """Garde seulement le service et le type de principal d'un ARN.

    Exemple : un ARN de rôle assumé devient
    ``arn:aws:sts::<compte masqué>:assumed-role/<ressource masquée>``.
    Le nom du rôle et de la session sont masqués aussi.
    """
    if not arn:
        return "<inconnu>"
    match = _ARN_RE.search(arn)
    if not match:
        return RESOURCE_MASK
    partition, service, region, _account, resource = match.groups()
    resource_type = re.split(r"[/:]", resource, maxsplit=1)[0]
    has_more = resource_type != resource
    masked_resource = f"{resource_type}/{RESOURCE_MASK}" if has_more else RESOURCE_MASK
    return f"arn:{partition}:{service}:{region}:{ACCOUNT_MASK}:{masked_resource}"


def principal_type(arn: str | None) -> str:
    """Retourne le type de principal (``assumed-role``, ``user``, ...) sans le nom."""
    if not arn:
        return "inconnu"
    match = _ARN_RE.search(arn)
    if not match:
        return "inconnu"
    return re.split(r"[/:]", match.group(5), maxsplit=1)[0]


def redact_text(text: str | None) -> str:
    """Retire ARN, numéros de compte et identifiants de clé d'un texte libre.

    Sert à afficher un message d'erreur AWS sans fuite (un message
    ``AccessDenied`` contient souvent l'ARN complet de l'appelant).
    """
    if not text:
        return ""
    text = _ARN_RE.sub(lambda m: mask_arn(m.group(0)), text)
    text = _ACCOUNT_RE.sub(ACCOUNT_MASK, text)
    return _ACCESS_KEY_RE.sub("<clé masquée>", text)


# ---------------------------------------------------------------------------
# Erreurs et nouvelles tentatives
# ---------------------------------------------------------------------------

def error_code(exc: BaseException) -> str | None:
    """Extrait le code d'erreur d'une ``ClientError`` de botocore (ou None)."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


def describe_aws_error(exc: BaseException) -> str:
    """Construit un message clair en français, sans secret, pour une erreur AWS."""
    code = error_code(exc)
    name = type(exc).__name__
    if code in CREDENTIAL_ERROR_CODES:
        return (
            f"Identifiants AWS expirés ou invalides ({code}). Récupérer un nouvel "
            "ensemble d'identifiants temporaires sur la page Workshop Studio "
            "(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY et AWS_SESSION_TOKEN), "
            "les coller dans le terminal dédié, puis relancer le script."
        )
    if code in ACCESS_DENIED_CODES:
        return (
            f"Accès refusé ({code}). Vérifier que les identifiants temporaires "
            "sont ceux du compte de l'atelier et qu'ils ne sont pas expirés ; "
            "au besoin, en récupérer de nouveaux. Si le problème persiste, "
            "vérifier l'accès au modèle ou au service dans la console Bedrock. "
            f"Détail (masqué) : {redact_text(str(exc))}"
        )
    if name in {"NoCredentialsError", "PartialCredentialsError"}:
        return (
            "Aucun identifiant AWS complet trouvé par la chaîne par défaut de "
            "boto3. Exporter les trois valeurs temporaires de Workshop Studio "
            "dans ce terminal (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, "
            "AWS_SESSION_TOKEN) ou utiliser CloudShell."
        )
    if code in THROTTLING_CODES:
        return (
            f"Limitation de débit Bedrock ({code}) après plusieurs tentatives. "
            "Les quotas sont partagés : attendre une minute puis relancer."
        )
    label = code or name
    return f"Erreur AWS ({label}) : {redact_text(str(exc))}"


def is_throttling(exc: BaseException) -> bool:
    """Vrai si l'exception est une limitation de débit AWS."""
    return error_code(exc) in THROTTLING_CODES


def call_with_backoff(
    func: Callable[[], Any],
    *,
    max_attempts: int = 4,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Appelle ``func`` avec délai exponentiel sur ``ThrottlingException``.

    Les autres erreurs remontent immédiatement. ``sleep`` est injectable pour
    que les tests n'attendent pas.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - filtrage par code juste après
            if not is_throttling(exc) or attempt == max_attempts:
                raise
            sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError("inaccessible")  # pragma: no cover


# ---------------------------------------------------------------------------
# Vérifications (clients injectés, aucune création de client ici)
# ---------------------------------------------------------------------------

def check_identity(sts_client: Any, region: str | None,
                   expected_region: str = EXPECTED_REGION_DEFAULT) -> dict:
    """Appelle ``get_caller_identity`` et retourne un résumé masqué."""
    identity = sts_client.get_caller_identity()
    arn = identity.get("Arn")
    return {
        "account_responds": bool(identity.get("Account")),
        "account": mask_account_id(identity.get("Account")),
        "arn": mask_arn(arn),
        "principal_type": principal_type(arn),
        "region": region,
        "region_ok": region == expected_region,
        "expected_region": expected_region,
    }


def _optional_flag(summary: dict, keys: tuple[str, ...]) -> bool | None:
    """Lit un indicateur facultatif s'il est renvoyé par l'API, sinon None."""
    for key in keys:
        if key in summary:
            return bool(summary[key])
    return None


def list_active_text_models(bedrock_client: Any) -> list[dict]:
    """Liste les modèles ``ACTIVE`` avec texte en entrée et en sortie.

    L'API ``ListFoundationModels`` ne renvoie pas (version actuelle de boto3)
    d'indicateur explicite de compatibilité Converse ni d'appels d'outils.
    Le filtre texte/texte est une condition nécessaire, pas suffisante : la
    prise en charge réelle des outils se confirme avec ``--try-converse``.
    Si une version future de l'API renvoie ces indicateurs, ils sont repris.
    """
    response = bedrock_client.list_foundation_models(byOutputModality="TEXT")
    models = []
    for summary in response.get("modelSummaries", []):
        status = summary.get("modelLifecycle", {}).get("status")
        if status != "ACTIVE":
            continue
        if "TEXT" not in summary.get("outputModalities", []):
            continue
        if "TEXT" not in summary.get("inputModalities", []):
            continue
        models.append({
            "model_id": summary.get("modelId"),
            "provider": summary.get("providerName"),
            "name": summary.get("modelName"),
            "inference_types": list(summary.get("inferenceTypesSupported", [])),
            "streaming": summary.get("responseStreamingSupported"),
            "converse": _optional_flag(summary, ("converseSupported",)),
            "tool_use": _optional_flag(summary, ("toolUseSupported", "toolsSupported")),
        })
    return sorted(models, key=lambda m: (m["provider"] or "", m["model_id"] or ""))


def list_inference_profiles(bedrock_client: Any, max_pages: int = 20) -> list[dict]:
    """Liste les profils d'inférence (identifiant, statut, type, modèles).

    Les ARN ne sont pas conservés : ceux des profils contiennent le numéro
    de compte.
    """
    profiles: list[dict] = []
    kwargs: dict = {}
    for _ in range(max_pages):
        response = bedrock_client.list_inference_profiles(**kwargs)
        for item in response.get("inferenceProfileSummaries", []):
            profiles.append({
                "profile_id": item.get("inferenceProfileId"),
                "name": item.get("inferenceProfileName"),
                "status": item.get("status"),
                "type": item.get("type"),
                "model_count": len(item.get("models", [])),
            })
        token = response.get("nextToken")
        if not token:
            break
        kwargs = {"nextToken": token}
    return sorted(profiles, key=lambda p: p["profile_id"] or "")


DUMMY_TOOL_NAME = "get_fictional_metric"


def build_dummy_tool_config(tool_choice: str = "auto") -> dict:
    """Outil factice pour l'essai Converse : il ne fait rien et ne touche aucune donnée."""
    choice = {"any": {}} if tool_choice == "any" else {"auto": {}}
    return {
        "tools": [{
            "toolSpec": {
                "name": DUMMY_TOOL_NAME,
                "description": (
                    "Outil factice de test. Retourne une métrique fictive pour "
                    "un symbole fictif. Aucune donnée réelle."
                ),
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Symbole fictif"},
                    },
                    "required": ["ticker"],
                }},
            }
        }],
        "toolChoice": choice,
    }


def try_converse(runtime_client: Any, model_id: str, *, tool_choice: str = "auto",
                 sleep: Callable[[float], None] = time.sleep) -> dict:
    """Fait UN appel Converse minimal avec l'outil factice.

    Parcourt tous les blocs de contenu (texte et demandes d'outil) sans
    supposer que le premier bloc contient la réponse.
    """
    request = {
        "modelId": model_id,
        "messages": [{
            "role": "user",
            "content": [{"text": (
                "Test technique. Appelle l'outil get_fictional_metric avec le "
                "symbole FICTIF, sans autre texte."
            )}],
        }],
        "toolConfig": build_dummy_tool_config(tool_choice),
        "inferenceConfig": {"maxTokens": 200},
    }
    response = call_with_backoff(lambda: runtime_client.converse(**request), sleep=sleep)
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    tool_names = [b["toolUse"].get("name") for b in blocks if "toolUse" in b]
    texts = [b["text"] for b in blocks if "text" in b]
    return {
        "model_id": model_id,
        "stop_reason": response.get("stopReason"),
        "tool_names": tool_names,
        "text": " ".join(texts).strip(),
        "tool_call_ok": DUMMY_TOOL_NAME in tool_names,
    }


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------

def _flag_label(value: bool | None) -> str:
    if value is None:
        return "non renvoyé par l'API"
    return "oui" if value else "non"


def format_report(identity: dict, models: list[dict], profiles: list[dict]) -> str:
    """Construit le rapport texte en français (aucune donnée sensible)."""
    lines = [
        "== Identité ==",
        f"Le compte répond : {'oui' if identity['account_responds'] else 'non'}",
        f"Compte : {identity['account']}",
        f"Principal : {identity['arn']} (type : {identity['principal_type']})",
        f"Région : {identity['region']} "
        f"({'conforme' if identity['region_ok'] else 'ATTENTION, attendu ' + identity['expected_region']})",
        "",
        f"== Modèles ACTIVE texte vers texte ({len(models)}) ==",
        "Converse et appels d'outils : à confirmer avec --try-converse si l'API ne le dit pas.",
    ]
    for m in models:
        lines.append(
            f"- {m['model_id']} | {m['provider']} | inférence : "
            f"{','.join(m['inference_types']) or '?'} | Converse : {_flag_label(m['converse'])} | "
            f"outils : {_flag_label(m['tool_use'])}"
        )
    lines += ["", f"== Profils d'inférence ({len(profiles)}) =="]
    for p in profiles:
        lines.append(f"- {p['profile_id']} | {p['type']} | {p['status']} | {p['model_count']} modèle(s)")
    return "\n".join(lines)


def format_converse_result(result: dict) -> str:
    """Résumé de l'essai Converse."""
    tools = ", ".join(result["tool_names"]) or "aucun"
    verdict = "appel d'outil reçu" if result["tool_call_ok"] else "aucun appel de l'outil factice"
    return "\n".join([
        "== Essai Converse ==",
        f"Modèle : {result['model_id']}",
        f"Raison d'arrêt : {result['stop_reason']}",
        f"Outil demandé : {tools} ({verdict})",
    ])


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def resolve_region(cli_region: str | None, environ: dict) -> str | None:
    """Région : argument, puis ``AWS_REGION``, puis ``AWS_DEFAULT_REGION``."""
    return cli_region or environ.get("AWS_REGION") or environ.get("AWS_DEFAULT_REGION") or None


def default_client_factory(region: str) -> Callable[[str], Any]:
    """Crée les clients boto3 avec la chaîne d'identifiants par défaut."""
    import boto3  # import local : les tests n'en ont pas besoin

    session = boto3.Session(region_name=region)
    return lambda service: session.client(service)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vérifie l'accès AWS et Bedrock en lecture seule (aucune ressource créée).")
    parser.add_argument("--region", help="Région AWS (sinon AWS_REGION).")
    parser.add_argument("--expected-region", default=EXPECTED_REGION_DEFAULT,
                        help="Région attendue (défaut : us-east-1).")
    parser.add_argument("--try-converse", nargs="?", const="", default=None, metavar="MODEL_ID",
                        help=f"Fait un appel Converse avec un outil factice. Sans valeur : {MODEL_ENV_VAR}.")
    parser.add_argument("--tool-choice", choices=("auto", "any"), default="auto",
                        help="Choix d'outil pour l'essai ('any' teste le choix forcé).")
    parser.add_argument("--skip-listing", action="store_true",
                        help="Ne liste pas les modèles ni les profils.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *,
         client_factory: Callable[[str], Callable[[str], Any]] | None = None,
         environ: dict | None = None,
         sleep: Callable[[float], None] = time.sleep) -> int:
    """Point d'entrée mince : lit la configuration, appelle les fonctions testables."""
    args = parse_args(argv)
    env = dict(os.environ) if environ is None else environ
    region = resolve_region(args.region, env)
    if not region:
        print("Région absente : définir AWS_REGION=us-east-1 dans ce terminal ou passer --region.")
        return EXIT_CONFIG_ERROR

    model_id = None
    if args.try_converse is not None:
        model_id = args.try_converse or env.get(MODEL_ENV_VAR)
        if not model_id:
            print(f"Aucun modèle pour l'essai Converse : passer un identifiant ou définir {MODEL_ENV_VAR}.")
            return EXIT_CONFIG_ERROR

    try:
        make_client = (client_factory or default_client_factory)(region)
        identity = check_identity(make_client("sts"), region, args.expected_region)
        models: list[dict] = []
        profiles: list[dict] = []
        if not args.skip_listing:
            bedrock = make_client("bedrock")
            models = list_active_text_models(bedrock)
            profiles = list_inference_profiles(bedrock)
        print(format_report(identity, models, profiles))
        if not identity["region_ok"]:
            print(f"Région {region} différente de {args.expected_region} : corriger AWS_REGION.")
            return EXIT_CONFIG_ERROR
        if model_id:
            result = try_converse(make_client("bedrock-runtime"), model_id,
                                  tool_choice=args.tool_choice, sleep=sleep)
            print()
            print(format_converse_result(result))
    except Exception as exc:  # noqa: BLE001 - message clair et masqué pour toute erreur AWS
        print(describe_aws_error(exc))
        return EXIT_AWS_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
