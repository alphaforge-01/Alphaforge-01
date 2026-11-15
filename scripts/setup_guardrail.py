"""Création idempotente du garde-fou Bedrock ``alphaforge-guardrail`` (tâche C2).

Ce script est la SEULE chose du dépôt qui modifie le compte AWS, et seulement
avec ``--apply``. Sans ``--apply`` il fonctionne en mode simulation : il
affiche la configuration qu'il enverrait, sans aucun appel AWS.

Configuration du garde-fou :

- trois sujets refusés ÉTROITS (conseil d'investissement personnalisé,
  exécution ou passage d'ordres, prédiction de rendement futur). Chaque
  définition précise que l'analyse historique d'une idée de placement fictive
  n'est pas visée, pour éviter les faux refus sur le cas de démo ;
- vérification d'ancrage contextuel (GROUNDING et RELEVANCE) en MODE
  DÉTECTION : ``action = NONE``, les scores sont calculés et affichés dans la
  trace sans bloquer. Le champ ``action`` existe bien pour ce volet dans la
  version de boto3 installée (1.44), donc le seuil n'a pas besoin d'être
  abaissé artificiellement. Seuils réglables par arguments ;
- messages de blocage en français.

Comportement avec ``--apply`` : liste les garde-fous existants ; si
``alphaforge-guardrail`` n'existe pas, il est créé, sinon il est mis à jour
(``update_guardrail``). Dans les deux cas, une nouvelle version numérotée est
publiée. Le script affiche l'identifiant et la version à copier dans
``ALPHAFORGE_GUARDRAIL_ID`` et ``ALPHAFORGE_GUARDRAIL_VERSION``. Aucun ARN
n'est affiché.

``--test`` envoie les requêtes de ``tests/fixtures/guardrail_prompts.json`` à
``ApplyGuardrail`` (lecture seule, mais consomme du quota partagé) et affiche
un tableau attendu/obtenu.

Usage (depuis la racine, dans le terminal qui contient les identifiants
temporaires) ::

    python scripts/setup_guardrail.py                 # simulation, aucun appel
    python scripts/setup_guardrail.py --apply         # crée ou met à jour
    python scripts/setup_guardrail.py --test          # utilise ALPHAFORGE_GUARDRAIL_ID/VERSION
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_aws_access import (  # noqa: E402
    EXIT_AWS_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_OK,
    call_with_backoff,
    default_client_factory,
    describe_aws_error,
    resolve_region,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_PATH = PROJECT_ROOT / "tests" / "fixtures" / "guardrail_prompts.json"

EXIT_TEST_MISMATCH = 3  # au moins une requête n'a pas le résultat attendu

GUARDRAIL_NAME = "alphaforge-guardrail"
GUARDRAIL_ID_ENV = "ALPHAFORGE_GUARDRAIL_ID"
GUARDRAIL_VERSION_ENV = "ALPHAFORGE_GUARDRAIL_VERSION"

DEFAULT_GROUNDING_THRESHOLD = 0.5
DEFAULT_RELEVANCE_THRESHOLD = 0.5
MAX_THRESHOLD = 0.99  # borne documentée par AWS pour l'ancrage contextuel

# Limites de l'API CreateGuardrail (modèle de service botocore).
MAX_TOPIC_NAME = 100
MAX_TOPIC_DEFINITION = 200
MAX_TOPIC_EXAMPLES = 5
MAX_EXAMPLE_LENGTH = 100
MAX_MESSAGE_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 200
TOPIC_NAME_PATTERN = re.compile(r"^[0-9a-zA-Z\-_ !?.]+$")
GUARDRAIL_NAME_PATTERN = re.compile(r"^[0-9a-zA-Z\-_]{1,50}$")

TOPIC_PERSONALIZED_ADVICE = "personalized_advice"
TOPIC_ORDER_EXECUTION = "order_execution"
TOPIC_RETURN_PREDICTION = "return_prediction"

DENIED_TOPICS: list[dict] = [
    # Definitions courtes, a l'affirmatif, sans clause "non vise" : le classifieur de Bedrock traite mal les
    # negations (premier essai : 1 faux refus et 4 refus manques sur 19 requetes). Le perimetre est borne par
    # le temps (le futur, pas l'historique observe) et par la personne (la situation reelle de l'utilisateur,
    # pas un profil fictif), de sorte que l'analyse d'une idee fictive n'entre pas dans ces sujets.
    {
        "name": TOPIC_PERSONALIZED_ADVICE,
        "definition": (
            "Conseil d'investissement personnalisé : dire à l'utilisateur quoi acheter, "
            "vendre ou garder selon sa propre situation, ses économies ou ses objectifs réels."
        ),
        "examples": [
            "Dis-moi quoi acheter avec mes économies.",
            "Compte tenu de ma situation, que devrais-je vendre ou acheter ?",
            "Quel placement me conseilles-tu pour ma retraite ?",
            "Comment en profiter ?",
            "Est-ce que je devrais vendre mes obligations pour acheter autre chose ?",
        ],
    },
    {
        "name": TOPIC_ORDER_EXECUTION,
        "definition": (
            "Demande d'exécuter une opération financière pour l'utilisateur : acheter, vendre, "
            "passer ou envoyer un ordre, ou agir sur son compte de courtage."
        ),
        "examples": [
            "Achète TSLA pour moi.",
            "Passe un ordre de vente sur mon compte.",
            "Connecte-toi à mon courtier et vends tout.",
            "Envoie un ordre d'achat demain matin.",
            "Exécute ce rééquilibrage sur mon compte réel.",
        ],
    },
    {
        "name": TOPIC_RETURN_PREDICTION,
        "definition": (
            "Prédiction ou promesse du prix ou du rendement futur d'un actif ou d'un "
            "portefeuille : combien il vaudra, s'il va monter ou baisser, quel gain garanti."
        ),
        "examples": [
            "Que va faire mon portefeuille l'an prochain ?",
            "Combien vaudra cette action dans six mois ?",
            "Garantis-moi 10 % de rendement par an.",
            "Est-ce que le Bitcoin va monter le mois prochain ?",
            "Mon portefeuille va-t-il battre le marché en 2027 ?",
        ],
    },
]

BLOCKED_INPUT_MESSAGE = (
    "Demande refusée par le garde-fou : AlphaForge est une simulation "
    "éducative. Il ne donne pas de conseil d'investissement personnalisé, ne "
    "passe aucun ordre et ne prédit pas les rendements futurs. Vous pouvez "
    "demander l'analyse historique d'une idée de placement fictive."
)
BLOCKED_OUTPUT_MESSAGE = (
    "Réponse retenue par le garde-fou : le texte produit sortait du cadre de "
    "la simulation éducative (conseil personnalisé, ordre ou prédiction). "
    "L'explication par gabarit reste disponible."
)
GUARDRAIL_DESCRIPTION = (
    "AlphaForge (simulation éducative) : refuse conseil personnalisé, ordres "
    "et prédictions de rendement ; ancrage contextuel en mode détection."
)


# ---------------------------------------------------------------------------
# Configuration (fonctions pures)
# ---------------------------------------------------------------------------

def build_guardrail_config(
    grounding_threshold: float = DEFAULT_GROUNDING_THRESHOLD,
    relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    grounding_action: str = "NONE",
    name: str = GUARDRAIL_NAME,
) -> dict:
    """Retourne les paramètres communs à ``create_guardrail`` et ``update_guardrail``.

    ``grounding_action = "NONE"`` correspond au mode détection (scores sans
    blocage). Les sujets refusés bloquent en entrée et en sortie.
    """
    topics = [
        {
            "name": topic["name"],
            "definition": topic["definition"],
            "examples": list(topic["examples"]),
            "type": "DENY",
            "inputAction": "BLOCK",
            "outputAction": "BLOCK",
            "inputEnabled": True,
            "outputEnabled": True,
        }
        for topic in DENIED_TOPICS
    ]
    filters = [
        {"type": "GROUNDING", "threshold": float(grounding_threshold),
         "action": grounding_action, "enabled": True},
        {"type": "RELEVANCE", "threshold": float(relevance_threshold),
         "action": grounding_action, "enabled": True},
    ]
    return {
        "name": name,
        "description": GUARDRAIL_DESCRIPTION,
        "topicPolicyConfig": {"topicsConfig": topics},
        "contextualGroundingPolicyConfig": {"filtersConfig": filters},
        "blockedInputMessaging": BLOCKED_INPUT_MESSAGE,
        "blockedOutputsMessaging": BLOCKED_OUTPUT_MESSAGE,
    }


def validate_config(config: dict) -> list[str]:
    """Vérifie les limites de l'API avant tout envoi. Retourne la liste des erreurs."""
    errors: list[str] = []
    if not GUARDRAIL_NAME_PATTERN.match(config.get("name", "")):
        errors.append("nom du garde-fou invalide")
    if len(config.get("description", "")) > MAX_DESCRIPTION_LENGTH:
        errors.append("description trop longue")
    for key in ("blockedInputMessaging", "blockedOutputsMessaging"):
        if not 1 <= len(config.get(key, "")) <= MAX_MESSAGE_LENGTH:
            errors.append(f"{key} : longueur hors limites")
    for topic in config["topicPolicyConfig"]["topicsConfig"]:
        name = topic["name"]
        if len(name) > MAX_TOPIC_NAME or not TOPIC_NAME_PATTERN.match(name):
            errors.append(f"sujet {name} : nom invalide")
        if not 1 <= len(topic["definition"]) <= MAX_TOPIC_DEFINITION:
            errors.append(f"sujet {name} : définition de {len(topic['definition'])} caractères")
        if len(topic["examples"]) > MAX_TOPIC_EXAMPLES:
            errors.append(f"sujet {name} : trop d'exemples")
        for example in topic["examples"]:
            if not 1 <= len(example) <= MAX_EXAMPLE_LENGTH:
                errors.append(f"sujet {name} : exemple trop long")
    for flt in config["contextualGroundingPolicyConfig"]["filtersConfig"]:
        if not 0.0 <= flt["threshold"] <= MAX_THRESHOLD:
            errors.append(f"seuil {flt['type']} hors de [0, {MAX_THRESHOLD}]")
        if flt.get("action") not in ("NONE", "BLOCK"):
            errors.append(f"action {flt['type']} invalide")
    return errors


def describe_config(config: dict) -> str:
    """Résumé lisible de la configuration (mode simulation)."""
    lines = [f"Garde-fou : {config['name']}", "Sujets refusés (blocage entrée et sortie) :"]
    for topic in config["topicPolicyConfig"]["topicsConfig"]:
        lines.append(f"- {topic['name']} : {topic['definition']}")
    lines.append("Ancrage contextuel :")
    for flt in config["contextualGroundingPolicyConfig"]["filtersConfig"]:
        mode = "détection" if flt["action"] == "NONE" else "blocage"
        lines.append(f"- {flt['type']} : seuil {flt['threshold']:.2f}, mode {mode}")
    lines.append(f"Message de blocage (entrée) : {config['blockedInputMessaging']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Opérations sur le compte (client injecté)
# ---------------------------------------------------------------------------

def find_guardrail_by_name(client: Any, name: str, max_pages: int = 20) -> dict | None:
    """Cherche un garde-fou par nom exact parmi ceux du compte (paginé)."""
    kwargs: dict = {}
    for _ in range(max_pages):
        response = client.list_guardrails(**kwargs)
        for summary in response.get("guardrails", []):
            if summary.get("name") == name:
                return summary
        token = response.get("nextToken")
        if not token:
            return None
        kwargs = {"nextToken": token}
    return None


def wait_until_ready(client: Any, guardrail_id: str, *,
                     sleep: Callable[[float], None] = time.sleep,
                     poll_seconds: float = 2.0, max_polls: int = 30) -> str:
    """Attend que le brouillon soit ``READY`` avant de publier une version."""
    status = "INCONNU"
    for _ in range(max_polls):
        status = client.get_guardrail(guardrailIdentifier=guardrail_id).get("status", "INCONNU")
        if status == "READY":
            return status
        if status == "FAILED":
            raise RuntimeError("Le garde-fou est en état FAILED : voir la console Bedrock.")
        sleep(poll_seconds)
    raise TimeoutError(f"Le garde-fou n'est pas prêt (dernier état : {status}).")


def apply_guardrail_config(client: Any, config: dict, *,
                           sleep: Callable[[float], None] = time.sleep) -> dict:
    """Crée ou met à jour le garde-fou, puis publie une nouvelle version.

    Idempotent par nom : un deuxième appel met à jour au lieu de créer.
    Retourne ``{"action", "guardrail_id", "version"}``, sans ARN.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + "; ".join(errors))
    existing = find_guardrail_by_name(client, config["name"])
    if existing is None:
        response = call_with_backoff(lambda: client.create_guardrail(**config), sleep=sleep)
        action = "created"
    else:
        response = call_with_backoff(
            lambda: client.update_guardrail(guardrailIdentifier=existing["id"], **config),
            sleep=sleep)
        action = "updated"
    guardrail_id = response["guardrailId"]
    wait_until_ready(client, guardrail_id, sleep=sleep)
    version = call_with_backoff(
        lambda: client.create_guardrail_version(
            guardrailIdentifier=guardrail_id,
            description="Version publiée par scripts/setup_guardrail.py"),
        sleep=sleep)
    return {"action": action, "guardrail_id": guardrail_id, "version": version["version"]}


# ---------------------------------------------------------------------------
# Tests des requêtes (ApplyGuardrail, lecture seule)
# ---------------------------------------------------------------------------

def load_prompts(path: Path = PROMPTS_PATH) -> list[dict]:
    """Charge le jeu de requêtes permises et refusées."""
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_assessment(response: dict, check: str = "request_topic",
                         mode: str = "detect") -> dict:
    """Convertit une réponse ``ApplyGuardrail`` en ``GuardrailResult`` (contrats).

    Sert à afficher les interventions du garde-fou à l'étape 6 de la trace.
    """
    denied: list[str] = []
    grounding = relevance = None
    for assessment in response.get("assessments", []):
        for topic in assessment.get("topicPolicy", {}).get("topics", []):
            if topic.get("action") == "BLOCKED" or topic.get("detected"):
                if topic.get("name") not in denied:
                    denied.append(topic.get("name"))
        for flt in assessment.get("contextualGroundingPolicy", {}).get("filters", []):
            if flt.get("type") == "GROUNDING":
                grounding = flt.get("score")
            elif flt.get("type") == "RELEVANCE":
                relevance = flt.get("score")
    intervened = response.get("action") == "GUARDRAIL_INTERVENED"
    return {
        "check": check,
        "action": "intervened" if intervened else "none",
        "denied_topics": denied,
        "grounding_score": grounding,
        "relevance_score": relevance,
        "mode": mode,
    }


def evaluate_prompt(runtime_client: Any, guardrail_id: str, version: str, prompt: dict, *,
                    sleep: Callable[[float], None] = time.sleep) -> dict:
    """Envoie une requête au garde-fou (source INPUT) et compare au résultat attendu."""
    response = call_with_backoff(
        lambda: runtime_client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
            source="INPUT",
            content=[{"text": {"text": prompt["text"]}}],
        ),
        sleep=sleep)
    result = summarize_assessment(response, check="request_topic", mode="block")
    obtained = "denied" if result["action"] == "intervened" else "allowed"
    return {
        "id": prompt["id"],
        "expected": prompt["expected"],
        "obtained": obtained,
        "expected_topic": prompt.get("topic"),
        "denied_topics": result["denied_topics"],
        "match": obtained == prompt["expected"],
    }


def run_prompt_tests(runtime_client: Any, guardrail_id: str, version: str,
                     prompts: list[dict], *,
                     sleep: Callable[[float], None] = time.sleep) -> list[dict]:
    """Évalue toutes les requêtes, une par une (quota partagé : pas de parallélisme)."""
    return [evaluate_prompt(runtime_client, guardrail_id, version, p, sleep=sleep) for p in prompts]


def format_test_table(rows: list[dict]) -> str:
    """Tableau texte attendu/obtenu."""
    labels = {"allowed": "permise", "denied": "refusée"}
    lines = [f"{'id':<6} {'attendu':<9} {'obtenu':<9} {'ok':<4} sujets détectés", "-" * 60]
    for row in rows:
        lines.append(
            f"{row['id']:<6} {labels[row['expected']]:<9} {labels[row['obtained']]:<9} "
            f"{'oui' if row['match'] else 'NON':<4} {', '.join(row['denied_topics']) or '-'}"
        )
    ok = sum(r["match"] for r in rows)
    lines.append(f"Concordance : {ok}/{len(rows)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crée ou met à jour le garde-fou alphaforge-guardrail (simulation par défaut).")
    parser.add_argument("--apply", action="store_true",
                        help="Crée ou met à jour réellement le garde-fou (modifie le compte).")
    parser.add_argument("--test", action="store_true",
                        help="Évalue les requêtes de tests/fixtures/guardrail_prompts.json.")
    parser.add_argument("--region", help="Région AWS (sinon AWS_REGION).")
    parser.add_argument("--grounding-threshold", type=float, default=DEFAULT_GROUNDING_THRESHOLD)
    parser.add_argument("--relevance-threshold", type=float, default=DEFAULT_RELEVANCE_THRESHOLD)
    parser.add_argument("--grounding-action", choices=("NONE", "BLOCK"), default="NONE",
                        help="NONE = mode détection (défaut), BLOCK = blocage.")
    parser.add_argument("--guardrail-id", help=f"Pour --test (sinon {GUARDRAIL_ID_ENV}).")
    parser.add_argument("--guardrail-version", help=f"Pour --test (sinon {GUARDRAIL_VERSION_ENV}).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *,
         client_factory: Callable[[str], Callable[[str], Any]] | None = None,
         environ: dict | None = None,
         sleep: Callable[[float], None] = time.sleep) -> int:
    """Point d'entrée mince. Aucun client AWS n'est créé sans --apply ou --test."""
    args = parse_args(argv)
    env = dict(os.environ) if environ is None else environ
    config = build_guardrail_config(args.grounding_threshold, args.relevance_threshold,
                                    args.grounding_action)
    errors = validate_config(config)
    if errors:
        print("Configuration invalide : " + "; ".join(errors))
        return EXIT_CONFIG_ERROR

    if not args.apply and not args.test:
        print("Mode simulation : aucun appel AWS. Configuration qui serait envoyée :")
        print(describe_config(config))
        print("Relancer avec --apply pour créer ou mettre à jour le garde-fou.")
        return EXIT_OK

    region = resolve_region(args.region, env)
    if not region:
        print("Région absente : définir AWS_REGION=us-east-1 dans ce terminal ou passer --region.")
        return EXIT_CONFIG_ERROR

    guardrail_id = args.guardrail_id or env.get(GUARDRAIL_ID_ENV)
    version = args.guardrail_version or env.get(GUARDRAIL_VERSION_ENV)
    try:
        make_client = (client_factory or default_client_factory)(region)
        if args.apply:
            result = apply_guardrail_config(make_client("bedrock"), config, sleep=sleep)
            verb = "créé" if result["action"] == "created" else "mis à jour"
            print(f"Garde-fou {config['name']} {verb}, version {result['version']} publiée.")
            print("À copier dans votre environnement local (jamais dans le dépôt) :")
            print(f"{GUARDRAIL_ID_ENV}={result['guardrail_id']}")
            print(f"{GUARDRAIL_VERSION_ENV}={result['version']}")
            guardrail_id, version = result["guardrail_id"], result["version"]
        if args.test:
            if not guardrail_id or not version:
                print(f"Pour --test, définir {GUARDRAIL_ID_ENV} et {GUARDRAIL_VERSION_ENV} "
                      "ou passer --guardrail-id et --guardrail-version.")
                return EXIT_CONFIG_ERROR
            rows = run_prompt_tests(make_client("bedrock-runtime"), guardrail_id, version,
                                    load_prompts(), sleep=sleep)
            print(format_test_table(rows))
            if not all(r["match"] for r in rows):
                return EXIT_TEST_MISMATCH
    except Exception as exc:  # noqa: BLE001 - message clair et masqué pour toute erreur AWS
        print(describe_aws_error(exc))
        return EXIT_AWS_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
