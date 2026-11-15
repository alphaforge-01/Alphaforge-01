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

PROMPT_NAME = "explainer_v5"
PROMPT_VERSION = PROMPT_NAME
# Pas de temperature : les modeles Claude recents la refusent (ValidationException, constate sur le compte).
# 4000 jetons : Haiku tronquait parfois sa reponse a 2500 (stopReason max_tokens, constate). Plafond de cout borne.
INFERENCE_CONFIG = {"maxTokens": 4000}
_STRING_SLOTS = ("summary", "counterfactual", "variants", "limits_context")
# Lien, image ou HTML dans le texte du modele : l'interface rend le Markdown, donc un lien ou une image distante
# serait affiche ou chargee. Le texte d'une explication est du texte simple. Constate a l'audit : le validateur
# accepte ces formes, d'ou ce rejet en amont qui declenche la nouvelle tentative.
_UNSAFE_MARKDOWN = re.compile(r"https?://|www\.|\]\(|!\[|<[A-Za-z/!]", re.IGNORECASE)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_output(text: str, brief: ExplanationBrief, *, model_id: str, attempt: int) -> tuple[ExplainerOutput | None, str | None]:
    """Extrait l'objet JSON des emplacements. Rend (sortie, None) ou (None, probleme)."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None, "Aucun objet JSON trouve dans la reponse."
    try:
        # strict=False : un retour a la ligne dans un texte est une erreur frequente des modeles, sans gravite
        raw = json.loads(cleaned[start:end + 1], strict=False)
    except ValueError as error:
        detail = f" ({getattr(error, 'msg', 'erreur')}, ligne {getattr(error, 'lineno', '?')}, colonne {getattr(error, 'colno', '?')})"
        return None, "JSON invalide" + detail + "."
    for slot in _STRING_SLOTS:
        if not isinstance(raw.get(slot), str):
            return None, f"Emplacement manquant ou invalide : {slot}."
    factors = raw.get("factors")
    if not isinstance(factors, list) or not all(
            isinstance(f, dict) and isinstance(f.get("check_id"), str) and isinstance(f.get("text"), str)
            for f in factors):
        return None, "Emplacement factors invalide : liste de {check_id, text}."
    texts = [raw[slot] for slot in _STRING_SLOTS] + [f["text"] for f in factors]
    if any(_UNSAFE_MARKDOWN.search(text) for text in texts):
        return None, "Le texte contient un lien, une image ou du HTML : ecris du texte simple, sans adresse ni balise."
    return ExplainerOutput(
        brief_id=brief["brief_id"], level=brief["level"], summary=raw["summary"],
        factors=[{"check_id": f["check_id"], "text": f["text"]} for f in factors],
        counterfactual=raw["counterfactual"], variants=raw["variants"], limits_context=raw["limits_context"],
        origin="llm", model_id=redact_text(model_id), prompt_version=PROMPT_VERSION, attempt=attempt,
    ), None


_GUIDANCE = {
    "unknown_reference": "n'utilise que des renvois [E#], [G#], [T#] presents dans le dossier ; aucun autre crochet",
    "number_outside_registry": "aucun chiffre ni nombre en lettres : remplace-le par le renvoi de sa preuve",
    "too_long": "raccourcis cet emplacement (une ou deux phrases courtes)",
    "forbidden_term": "remplace ce mot par une formulation neutre qui decrit seulement ce qui est observe",
    "missing_rule_citation": "cite par son renvoi [G#] chaque regle en tension ou en conflit",
    "slot_missing": "remplis tous les emplacements demandes",
}


def describe_rejections(rejections: list[dict[str, Any]], limit: int = 12) -> str:
    """Retour de correction pour le modele : emplacement, code et extrait de chaque rejet, puis une consigne par code."""
    lines = [
        f"- {r.get('slot', '?')} : {r.get('code', '?')} ({redact_text(str(r.get('excerpt', '')))[:60]})"
        for r in rejections[:limit]
    ]
    codes = list(dict.fromkeys(r.get("code") for r in rejections if r.get("code")))
    advice = [f"{code} : {_GUIDANCE[code]}" for code in codes if code in _GUIDANCE]
    return "Rejets du validateur :\n" + "\n".join(lines) + ("\nConsignes : " + " ; ".join(advice) if advice else "")


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
        if response.get("stopReason") == "max_tokens":
            # Reponse tronquee : le JSON serait incomplet. Message exact pour la nouvelle tentative.
            output, problem = None, "Reponse tronquee (max_tokens) : raccourcis chaque emplacement."
        else:
            output, problem = parse_output(text, brief, model_id=model_id, attempt=attempt)
        if output is not None:
            try:
                verdict = validate(output, brief)
            except Exception as error:  # un validateur defaillant ne doit pas faire planter la page
                raise ExplainerFailure(f"Validateur en erreur ({type(error).__name__}).") from error
            if verdict["is_valid"] or attempt == 2:
                return output
            problem = describe_rejections(verdict["rejections"])
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
