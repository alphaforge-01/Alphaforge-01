"""Agent explicateur (Bedrock Converse, un appel, aucun outil).

Il ne voit que le dossier d'explication. Il redige dans des emplacements fixes,
par renvois [E3] [G1] [T2], sans aucun chiffre en clair. Le code insere ensuite
les valeurs du registre. Un texte rejete par le validateur est renvoye une seule
fois au modele avec les codes de rejet ; au-dela, le pipeline utilise le gabarit.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .bedrock_client import BedrockClient, extract_text, redact_text
from .contracts import ExplainerOutput, ExplanationBrief
from .prompt_loader import load_prompt
from .tool_specs import ExplainerFailure

PROMPT_NAME = "explainer_v1"
PROMPT_VERSION = PROMPT_NAME
INFERENCE_CONFIG = {"maxTokens": 1500, "temperature": 0}
_STRING_SLOTS = ("summary", "counterfactual", "variants", "limits_context")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_output(text: str, brief: ExplanationBrief, *, model_id: str, attempt: int) -> tuple[ExplainerOutput | None, str | None]:
    """Extrait l'objet JSON des emplacements. Rend (sortie, None) ou (None, probleme)."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None, "Aucun objet JSON trouve dans la reponse."
    try:
        raw = json.loads(cleaned[start:end + 1])
    except ValueError:
        return None, "JSON invalide."
    for slot in _STRING_SLOTS:
        if not isinstance(raw.get(slot), str):
            return None, f"Emplacement manquant ou invalide : {slot}."
    factors = raw.get("factors")
    if not isinstance(factors, list) or not all(
            isinstance(f, dict) and isinstance(f.get("check_id"), str) and isinstance(f.get("text"), str)
            for f in factors):
        return None, "Emplacement factors invalide : liste de {check_id, text}."
    return ExplainerOutput(
        brief_id=brief["brief_id"], level=brief["level"], summary=raw["summary"],
        factors=[{"check_id": f["check_id"], "text": f["text"]} for f in factors],
        counterfactual=raw["counterfactual"], variants=raw["variants"], limits_context=raw["limits_context"],
        origin="llm", model_id=redact_text(model_id), prompt_version=PROMPT_VERSION, attempt=attempt,
    ), None


def explain_with_llm(
    client: BedrockClient,
    model_id: str | None,
    brief: ExplanationBrief,
    validate: Callable[[ExplainerOutput, ExplanationBrief], Any],
) -> ExplainerOutput:
    """Un appel, puis au plus un nouvel essai si le validateur rejette le texte.

    Leve ``ExplainerFailure`` si aucune sortie JSON exploitable n'est obtenue.
    La sortie rendue peut encore etre invalide apres le second essai : le
    pipeline la valide de nouveau et utilise alors le gabarit.
    """
    if not model_id:
        raise ExplainerFailure("Identifiant de modele de l'explicateur non configure.")
    system = load_prompt(PROMPT_NAME)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": "Dossier d'explication :\n" + json.dumps(brief, ensure_ascii=False)}]}]
    last_problem = "Aucune reponse exploitable."
    for attempt in (1, 2):
        response = client.converse(model_id, messages, system=system, inference_config=INFERENCE_CONFIG)
        text = extract_text(response)
        output, problem = parse_output(text, brief, model_id=model_id, attempt=attempt)
        if output is not None:
            try:
                verdict = validate(output, brief)
            except Exception as error:  # un validateur defaillant ne doit pas faire planter la page
                raise ExplainerFailure(f"Validateur en erreur ({type(error).__name__}).") from error
            if verdict["is_valid"] or attempt == 2:
                return output
            codes = ", ".join(
                f"{r['code']} ({redact_text(str(r.get('excerpt', '')))[:40]})" for r in verdict["rejections"][:6])
            problem = f"Rejet du validateur : {codes}."
        last_problem = problem or last_problem
        if attempt == 1:
            try:
                messages.append(response["output"]["message"])
            except (KeyError, TypeError) as error:
                raise ExplainerFailure("Reponse Converse mal formee.") from error
            messages.append({"role": "user", "content": [{"text": (
                f"Ta reponse a ete rejetee. {last_problem} Corrige et renvoie uniquement l'objet JSON, "
                "sans chiffre en clair et avec des renvois existants.")}]})
    raise ExplainerFailure(last_problem)
