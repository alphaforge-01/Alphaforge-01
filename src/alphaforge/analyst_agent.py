"""Agent analyste (Bedrock Converse avec outils).

Ce qu'il fait : comprendre l'idee structuree, appeler les outils deterministes,
proposer au plus deux variantes, puis cloturer par ``submit_analysis``.
Ce qu'il ne fait pas : rediger du texte pour l'utilisateur, calculer, juger.

Garde-fous du code (pas du prompt) :
- tours et appels d'outils bornes (6 tours, 12 appels) ;
- toute sortie est validee ; une soumission invalide est renvoyee au modele une fois ;
- aucune erreur ici ne plante l'application : le pipeline bascule sur la sequence scriptee ;
- le raisonnement interne eventuel du modele n'est ni lu ni conserve.
"""
from __future__ import annotations

import json
from typing import Any

from .bedrock_client import BedrockClient, extract_tool_uses, redact_text
from .contracts import AnalystSubmission, InvestmentIdea, InvestorProfile
from .prompt_loader import load_prompt
from .tool_specs import (
    MAX_HIGHLIGHTS, MAX_VARIANTS, REASON_CODES, UNSUPPORTED_CODES, AnalystFailure, AnalystOutcome, ToolBox,
    ToolBudgetExceeded, normalize_idea, tool_config,
)

PROMPT_NAME = "analyst_v1"
MAX_TURNS = 6
MAX_UNSUPPORTED = 5
INFERENCE_CONFIG = {"maxTokens": 1024, "temperature": 0}


def build_user_message(idea: InvestmentIdea, profile: InvestorProfile) -> str:
    """Message initial : idee structuree et regles du profil fictif (seuils = hypotheses)."""
    rules = [
        {
            "rule_id": rule["rule_id"], "rule_type": rule["rule_type"], "params": rule["params"],
            "direction": rule["direction"], "warn_threshold": rule["warn_threshold"],
            "limit_threshold": rule["limit_threshold"], "label_fr": rule["label_fr"],
        }
        for rule in profile.get("rules", [])
    ]
    payload = {
        "idee_a_analyser": {
            "ticker": idea["ticker"], "target_weight": idea["target_weight"],
            "funding_source": idea["funding_source"], "funding_ticker": idea.get("funding_ticker"),
        },
        "profil_fictif": {
            "profile_id": profile["profile_id"], "horizon_years_min": profile["horizon_years_min"],
            "horizon_years_max": profile["horizon_years_max"], "risk_tolerance": profile["risk_tolerance"],
            "regles": rules,
        },
    }
    return (
        "Analyse l'idee suivante pour le profil fictif ci-dessous. Les seuils des regles sont des hypotheses.\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def parse_submission(raw: Any) -> tuple[AnalystSubmission | None, str | None]:
    """Valide les parametres de ``submit_analysis``. Rend (soumission, None) ou (None, probleme)."""
    if not isinstance(raw, dict):
        return None, "Les parametres de submit_analysis doivent etre un objet."
    understood, problem = normalize_idea(raw.get("understood_idea"))
    if understood is None:
        return None, f"understood_idea invalide : {problem}"
    variants: list[dict[str, Any]] = []
    for item in raw.get("variants") or []:
        if not isinstance(item, dict) or item.get("reason_code") not in REASON_CODES:
            return None, f"reason_code invalide, valeurs permises : {', '.join(REASON_CODES)}."
        variant_idea, problem = normalize_idea(item.get("idea"))
        if variant_idea is None:
            return None, f"idee de variante invalide : {problem}"
        variants.append({"reason_code": item["reason_code"], "idea": variant_idea})
    if len(variants) > MAX_VARIANTS:
        return None, f"Au plus {MAX_VARIANTS} variantes."
    highlights = raw.get("highlight_evidence_ids") or []
    if not isinstance(highlights, list) or not all(isinstance(h, str) for h in highlights) \
            or len(highlights) > MAX_HIGHLIGHTS:
        return None, f"highlight_evidence_ids : au plus {MAX_HIGHLIGHTS} identifiants (chaines)."
    unsupported = raw.get("unsupported_requests") or []
    if not isinstance(unsupported, list) or not all(u in UNSUPPORTED_CODES for u in unsupported):
        return None, f"unsupported_requests : codes permis {', '.join(UNSUPPORTED_CODES)}."
    cleaned = list(dict.fromkeys(unsupported))[:MAX_UNSUPPORTED]
    return AnalystSubmission(
        understood_idea=understood, variants=variants,
        highlight_evidence_ids=list(highlights), unsupported_requests=cleaned,
    ), None


def _tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Version compacte d'un ToolResult pour le modele : donnees et preuves, sans metadonnees inutiles."""
    return {
        "status": result["status"],
        "error_message": result.get("error_message"),
        "data": result.get("data", {}),
        "evidence": [
            {k: e.get(k) for k in ("evidence_id", "label_fr", "display_value", "subject", "period_start",
                                   "period_end", "currency")}
            for e in result.get("evidence", []) or []
        ],
    }


def _result_block(tool_use_id: str, payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"toolUseId": tool_use_id, "content": [{"json": payload}]}
    if is_error:
        block["status"] = "error"
    return {"toolResult": block}


def run_analyst(
    client: BedrockClient,
    model_id: str | None,
    toolbox: ToolBox,
    idea: InvestmentIdea,
    profile: InvestorProfile,
    *,
    max_turns: int = MAX_TURNS,
) -> AnalystOutcome:
    """Boucle d'outils bornee. Leve ``AnalystFailure`` si aucune soumission valide n'aboutit."""
    if not model_id:
        raise AnalystFailure("Identifiant de modele de l'analyste non configure.")
    system = load_prompt(PROMPT_NAME)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": build_user_message(idea, profile)}]}]
    nudged = False
    rejected_submission = False
    for turn in range(1, max_turns + 1):
        response = client.converse(
            model_id, messages, system=system, tool_config=tool_config(), inference_config=INFERENCE_CONFIG)
        if response.get("stopReason") == "max_tokens":
            raise AnalystFailure("Reponse de l'analyste tronquee (max_tokens).")
        try:
            messages.append(response["output"]["message"])
        except (KeyError, TypeError) as error:
            raise AnalystFailure("Reponse Converse mal formee.") from error
        tool_uses = extract_tool_uses(response)
        if not tool_uses:
            if nudged:
                raise AnalystFailure("L'analyste a repondu sans appeler submit_analysis.")
            nudged = True
            messages.append({"role": "user", "content": [{"text": "Termine maintenant avec l'outil submit_analysis."}]})
            continue
        blocks: list[dict[str, Any]] = []
        submission: AnalystSubmission | None = None
        bad_submit = False
        for use in tool_uses:
            name, params, use_id = use.get("name"), use.get("input") or {}, use["toolUseId"]
            if name == "submit_analysis":
                parsed, problem = parse_submission(params)
                if parsed is not None:
                    submission = parsed
                    blocks.append(_result_block(use_id, {"status": "ok"}))
                else:
                    bad_submit = True
                    blocks.append(_result_block(use_id, {"status": "error", "error_message": problem}, is_error=True))
                continue
            try:
                result = toolbox.call(str(name), params if isinstance(params, dict) else {})
            except ToolBudgetExceeded:
                blocks.append(_result_block(
                    use_id, {"status": "error", "error_message": "Budget d'appels atteint : appelle submit_analysis."},
                    is_error=True))
                continue
            blocks.append(_result_block(use_id, _tool_payload(result), is_error=result["status"] == "error"))
        if submission is not None:
            return AnalystOutcome(
                submission=submission, actor="agent", model_id=model_id, turns=turn, stop_reason="submitted")
        if bad_submit:
            if rejected_submission:
                raise AnalystFailure("Soumission invalide deux fois de suite.")
            rejected_submission = True
        else:
            rejected_submission = False
        messages.append({"role": "user", "content": blocks})
    raise AnalystFailure(f"{max_turns} tours sans soumission valide.")
