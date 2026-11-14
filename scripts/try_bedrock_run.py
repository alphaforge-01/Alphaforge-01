"""Essai réel de bout en bout du pipeline en mode ``bedrock`` (validation avant la démo).

Le script exécute, pour quelques personas fictifs, l'analyse de l'idée fixe
"ajouter 25 % de TSLA, financé au prorata" avec les VRAIS outils
(``resolve_deps``), puis l'explication aux niveaux ``novice`` et ``pro``. Il
affiche un résumé compact par persona : mode demandé et effectif, statut et
acteur de chaque étape de la trace, raison de repli, outils appelés,
validation, scores du garde-fou et enregistrement de la trace sur S3.

Il n'affiche jamais le texte des prompts, des requêtes ni aucun secret : tout
message passe par ``redact_text``. Simulation éducative sur des données et des
portefeuilles fictifs : aucun ordre, aucun courtier, aucun conseil personnalisé.

Modes :

- par défaut (``--dry-run``) : n'appelle rien, affiche le plan et la
  configuration lue dans l'environnement (sans valeur secrète) et vérifie que
  ``ALPHAFORGE_ANALYST_MODEL_ID``, ``ALPHAFORGE_EXPLAINER_MODEL_ID``,
  ``ALPHAFORGE_GUARDRAIL_ID`` et ``ALPHAFORGE_GUARDRAIL_VERSION`` sont définies ;
- ``--run`` : exécute réellement (consomme du quota partagé, budget borné).

Budget : au plus 3 personas, soit au plus 3 x (1 analyse + 2 explications)
appels de pipeline. Au-delà, le script refuse.

Usage (depuis la racine, dans le terminal qui contient les identifiants
temporaires) ::

    python scripts/try_bedrock_run.py
    python scripts/try_bedrock_run.py --run --personas robert,amira --save-local
    python scripts/try_bedrock_run.py --run --check-requests

Codes de sortie : 0 succès, 1 étape en erreur ou mode effectif autre que
bedrock, 2 configuration ou budget, 3 écart au tableau ``--check-requests``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alphaforge.bedrock_client import BedrockConfig, redact_text  # noqa: E402

EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_CONFIG_ERROR = 2
EXIT_REQUEST_MISMATCH = 3

PROMPTS_PATH = PROJECT_ROOT / "tests" / "fixtures" / "guardrail_prompts.json"
REQUIRED_ENV = (
    "ALPHAFORGE_ANALYST_MODEL_ID",
    "ALPHAFORGE_EXPLAINER_MODEL_ID",
    "ALPHAFORGE_GUARDRAIL_ID",
    "ALPHAFORGE_GUARDRAIL_VERSION",
)
DEFAULT_PERSONAS = ("robert", "amira")
LEVELS = ("novice", "pro")
MAX_PERSONAS = 3
CALLS_PER_PERSONA = 1 + len(LEVELS)  # une analyse + une explication par niveau
MAX_PIPELINE_CALLS = MAX_PERSONAS * CALLS_PER_PERSONA
MAX_REQUEST_CHECKS = 30

# Idée fixe de l'essai : fictive, identique pour tous les personas.
TRIAL_IDEA = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}

# Replis d'explication qui relèvent d'un contrôle du code, pas d'une panne Bedrock.
CONTROLLED_FALLBACKS = frozenset({"rejet_du_validateur", "garde_fou_sortie"})


def emit(line: str = "") -> None:
    """Affiche une ligne après masquage des secrets."""
    print(redact_text(str(line)))


# ---------------------------------------------------------------------------
# Configuration et plan
# ---------------------------------------------------------------------------

def parse_personas(raw: str) -> list[str]:
    """Liste ordonnée et sans doublon des personas demandés."""
    seen: list[str] = []
    for item in raw.split(","):
        name = item.strip().lower()
        if name and name not in seen:
            seen.append(name)
    return seen


def check_budget(personas: list[str]) -> str | None:
    """Rend un message de refus si le budget d'appels est dépassé, sinon None."""
    if not personas:
        return "Aucun persona demandé."
    planned = len(personas) * CALLS_PER_PERSONA
    if len(personas) > MAX_PERSONAS or planned > MAX_PIPELINE_CALLS:
        return (f"Budget dépassé : {len(personas)} personas demandés, au plus {MAX_PERSONAS} "
                f"({MAX_PIPELINE_CALLS} appels de pipeline au maximum). Essai refusé.")
    return None


def missing_env(env: dict) -> list[str]:
    return [name for name in REQUIRED_ENV if not str(env.get(name, "")).strip()]


def trial_config(env: dict) -> BedrockConfig:
    """Configuration de l'environnement, mode forcé à ``bedrock`` pour l'essai."""
    return replace(BedrockConfig.from_env(env), mode="bedrock")


def describe_config(config: BedrockConfig, env: dict) -> list[str]:
    """Configuration lisible, sans valeur secrète ni identifiant de ressource du compte."""
    def defined(name: str) -> str:
        return "défini" if str(env.get(name, "")).strip() else "MANQUANT"

    return [
        f"Région : {config.region}",
        f"ALPHAFORGE_MODE (environnement) : {env.get('ALPHAFORGE_MODE') or 'non défini'} "
        "(l'essai force le mode bedrock)",
        f"ALPHAFORGE_ANALYST_MODEL_ID : {config.analyst_model_id or 'MANQUANT'}",
        f"ALPHAFORGE_EXPLAINER_MODEL_ID : {config.explainer_model_id or 'MANQUANT'}",
        f"ALPHAFORGE_GUARDRAIL_ID : {defined('ALPHAFORGE_GUARDRAIL_ID')}",
        f"ALPHAFORGE_GUARDRAIL_VERSION : {config.guardrail_version or 'MANQUANT'}",
        f"ALPHAFORGE_TRACE_BUCKET : {defined('ALPHAFORGE_TRACE_BUCKET')} "
        "(sans compartiment, les traces ne vont pas sur S3)",
        "Identifiants : chaîne par défaut de boto3, jamais lus ni affichés par ce script.",
    ]


def describe_plan(personas: list[str], *, save_local: bool, check_requests: bool) -> list[str]:
    lines = [
        f"Personas : {', '.join(personas)}",
        f"Idée fictive : {TRIAL_IDEA['ticker']} à {TRIAL_IDEA['target_weight']:.0%}, financée au prorata",
        f"Par persona : 1 analyse + {len(LEVELS)} explications ({', '.join(LEVELS)})",
        f"Appels de pipeline prévus : {len(personas) * CALLS_PER_PERSONA} (budget {MAX_PIPELINE_CALLS})",
        f"Copie locale des traces : {'oui (outputs/reports/traces/)' if save_local else 'non'}",
        f"Vérification des requêtes du garde-fou : {'oui' if check_requests else 'non'}",
    ]
    return lines


# ---------------------------------------------------------------------------
# Résumé d'un persona (aucun texte de prompt, aucun secret)
# ---------------------------------------------------------------------------

def _step_line(step: dict) -> str:
    details = step.get("details") or {}
    line = f"  {step.get('step')}. {step.get('name')} : {step.get('status')} (acteur {step.get('actor')})"
    if details.get("fallback_reason"):
        line += f", repli : {details['fallback_reason']}"
    if details.get("error"):
        line += f", erreur : {details['error']}"
    return line


def _trace_saved_label(details: dict) -> str:
    saved = details.get("trace_saved")
    if not isinstance(saved, dict):
        return "non tentée"
    if saved.get("saved"):
        return f"oui ({saved.get('location')})"
    return f"non ({saved.get('reason')})"


def summarize_persona(persona_id: str, result: dict, explanations: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Rend (lignes du résumé, problèmes bloquants) pour un persona."""
    lines = [f"== {persona_id} =="]
    problems: list[str] = []
    trace = list(result.get("trace") or [])
    first = (trace[0].get("details") or {}) if trace else {}
    lines.append(f"Mode demandé : {first.get('mode_requested', 'bedrock')} ; "
                 f"mode effectif : {result.get('mode')}")
    if result.get("mode") != "bedrock":
        problems.append(f"{persona_id} : analyse en mode {result.get('mode')} au lieu de bedrock")
    if result.get("is_fixture"):
        problems.append(f"{persona_id} : outils bouchons (is_fixture) au lieu des vrais outils")
    tools = [call.get("tool_name") for call in first.get("tool_calls", []) if isinstance(call, dict)]
    lines.append(f"Outils appelés ({len(tools)}) : {', '.join(tools) or 'aucun'}")
    lines.append("Trace de l'analyse :")
    for step in trace:
        lines.append(_step_line(step))
        if step.get("status") == "error":
            problems.append(f"{persona_id} : étape {step.get('name')} en erreur")
    if trace:
        lines.append(f"Trace S3 de l'analyse : {_trace_saved_label(trace[-1].get('details') or {})}")

    for level, explanation in explanations.items():
        lines.append(f"Explication {level} :")
        steps = list(explanation.get("trace") or [])
        for step in steps:
            lines.append(_step_line(step))
            if step.get("status") == "error":
                problems.append(f"{persona_id}/{level} : étape {step.get('name')} en erreur")
        explanation_step = next((s for s in steps if s.get("name") == "explanation"), None)
        if explanation_step is not None and explanation_step.get("actor") != "agent":
            reason = (explanation_step.get("details") or {}).get("fallback_reason")
            if reason not in CONTROLLED_FALLBACKS:
                problems.append(f"{persona_id}/{level} : explication hors Bedrock ({reason or 'inconnu'})")
        validation = explanation.get("validation") or {}
        codes = [r.get("code") for r in validation.get("rejections", []) if isinstance(r, dict)]
        lines.append(f"  validation : {'valide' if validation.get('is_valid') else 'invalide'}"
                     + (f" (rejets : {', '.join(codes)})" if codes else ""))
        guard = explanation.get("guardrail") or {}
        lines.append(f"  garde-fou : action {guard.get('action')}, ancrage {guard.get('grounding_score')}, "
                     f"pertinence {guard.get('relevance_score')}")
        if steps:
            lines.append(f"  trace S3 : {_trace_saved_label(steps[-1].get('details') or {})}")
    return lines, problems


# ---------------------------------------------------------------------------
# Vérification des requêtes (ApplyGuardrail via check_request)
# ---------------------------------------------------------------------------

def load_prompts(path: Path = PROMPTS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_request_checks(prompts: list[dict], check_fn: Callable[[str], dict]) -> list[dict]:
    """Passe chaque requête à ``check_fn`` ; ``not_run`` compte comme un écart."""
    rows = []
    for prompt in prompts[:MAX_REQUEST_CHECKS]:
        action = (check_fn(prompt["text"]) or {}).get("action")
        obtained = {"intervened": "denied", "none": "allowed"}.get(action, "not_run")
        rows.append({"id": prompt["id"], "expected": prompt["expected"], "obtained": obtained,
                     "match": obtained == prompt["expected"]})
    return rows


def format_request_table(rows: list[dict]) -> list[str]:
    labels = {"allowed": "permise", "denied": "refusée", "not_run": "non vérifiée"}
    lines = [f"{'id':<6} {'attendu':<13} {'obtenu':<13} ok", "-" * 40]
    for row in rows:
        lines.append(f"{row['id']:<6} {labels[row['expected']]:<13} {labels[row['obtained']]:<13} "
                     f"{'oui' if row['match'] else 'NON'}")
    lines.append(f"Concordance : {sum(r['match'] for r in rows)}/{len(rows)}")
    return lines


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Essai réel du pipeline en mode bedrock (simulation éducative, budget borné).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Défaut : n'appelle rien, affiche le plan.")
    group.add_argument("--run", action="store_true", help="Exécute réellement (quota partagé).")
    parser.add_argument("--personas", default=",".join(DEFAULT_PERSONAS),
                        help=f"Liste séparée par des virgules (au plus {MAX_PERSONAS}).")
    parser.add_argument("--save-local", action="store_true",
                        help="Copie les traces dans outputs/reports/traces/.")
    parser.add_argument("--check-requests", action="store_true",
                        help="Passe les requêtes de tests/fixtures/guardrail_prompts.json au garde-fou.")
    return parser.parse_args(argv)


def _default_client_factory(config: BedrockConfig) -> Any:
    from alphaforge.bedrock_client import BedrockClient

    return BedrockClient(config)


def main(argv: list[str] | None = None, *,
         environ: dict | None = None,
         deps_factory: Callable[[], Any] | None = None,
         client_factory: Callable[[BedrockConfig], Any] | None = None,
         personas_loader: Callable[[], dict] | None = None,
         run_analysis_fn: Callable[..., dict] | None = None,
         explain_fn: Callable[..., dict] | None = None,
         check_request_fn: Callable[..., dict] | None = None,
         prompts_loader: Callable[[], list[dict]] | None = None,
         local_dir: Path | None = None) -> int:
    """Point d'entrée mince. En simulation, aucun module réseau n'est appelé."""
    args = parse_args(argv)
    env = dict(os.environ) if environ is None else environ
    personas = parse_personas(args.personas)
    refusal = check_budget(personas)
    if refusal:
        emit(refusal)
        return EXIT_CONFIG_ERROR

    config = trial_config(env)
    emit("== Configuration ==")
    for line in describe_config(config, env):
        emit(line)
    emit("== Plan ==")
    for line in describe_plan(personas, save_local=args.save_local, check_requests=args.check_requests):
        emit(line)
    missing = missing_env(env)
    if missing:
        emit("Variables manquantes : " + ", ".join(missing) + ". Les définir dans le terminal dédié.")
        return EXIT_CONFIG_ERROR
    if not args.run:
        emit("Mode simulation : aucun appel. Relancer avec --run pour l'essai réel.")
        return EXIT_OK

    from alphaforge import analysis_pipeline
    from alphaforge.trace_store import build_trace_document, save_local_copy

    run_analysis = run_analysis_fn or analysis_pipeline.run_analysis
    explain = explain_fn or analysis_pipeline.explain
    check_request = check_request_fn or analysis_pipeline.check_request
    catalog = (personas_loader or _load_personas)()
    unknown = [p for p in personas if p not in catalog]
    if unknown:
        emit(f"Persona inconnu : {', '.join(unknown)}. Valeurs permises : {', '.join(sorted(catalog))}.")
        return EXIT_CONFIG_ERROR

    deps = (deps_factory or _resolve_deps)()
    if getattr(deps, "is_fixture", False):
        emit("Attention : resolve_deps a rendu les bouchons de fixtures, pas les vrais outils.")
    client = (client_factory or _default_client_factory)(config)
    problems: list[str] = []
    for persona_id in personas:
        entry = catalog[persona_id]
        try:
            result = run_analysis(entry["profile"], entry["portfolio"], dict(TRIAL_IDEA), mode="bedrock",
                                  deps=deps, client=client, config=config)
            explanations = {level: explain(result, level, mode="bedrock", deps=deps, client=client,
                                           config=config) for level in LEVELS}
        except Exception as error:  # noqa: BLE001 - l'essai continue avec le persona suivant
            emit(f"== {persona_id} ==")
            emit(f"Échec : {type(error).__name__} : {redact_text(str(error))}")
            problems.append(f"{persona_id} : échec du pipeline")
            continue
        lines, persona_problems = summarize_persona(persona_id, result, explanations)
        for line in lines:
            emit(line)
        problems += persona_problems
        if args.save_local:
            documents = [build_trace_document(result)]
            documents += [build_trace_document(result, explanation) for explanation in explanations.values()]
            for document in documents:
                path = save_local_copy(document, local_dir)
                try:
                    shown = path.relative_to(PROJECT_ROOT)
                except ValueError:
                    shown = path.name
                emit(f"Copie locale : {shown}")

    exit_code = EXIT_OK
    if problems:
        emit("== Problèmes ==")
        for problem in problems:
            emit(f"- {problem}")
        exit_code = EXIT_RUN_FAILED

    if args.check_requests:
        prompts = (prompts_loader or load_prompts)()
        rows = run_request_checks(
            prompts, lambda text: check_request(text, mode="bedrock", client=client, config=config))
        emit("== Requêtes du garde-fou ==")
        for line in format_request_table(rows):
            emit(line)
        if not all(r["match"] for r in rows) and exit_code == EXIT_OK:
            exit_code = EXIT_REQUEST_MISMATCH
    return exit_code


def _load_personas() -> dict:
    from alphaforge.profiles import load_personas

    return load_personas()


def _resolve_deps() -> Any:
    from alphaforge.pipeline_deps import resolve_deps

    return resolve_deps()


if __name__ == "__main__":
    sys.exit(main())
