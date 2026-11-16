"""Dossier de l'agent conversationnel (issue 78) : le code choisit les faits, l'agent ne fait que rediger.

`build_conversation_brief` assemble un `ConversationBrief` a partir de ce que le code a deja calcule :
- le dossier d'explication de la derniere analyse (`explanation_brief.build_brief`), s'il y en a une :
  memes preuves, controles, glossaire et limites que l'explication ;
- sinon la radiographie du portefeuille fictif (outil `analyze_portfolio` et gouvernance), sans idee ;
- les faits declares du profil fictif (outil `get_profile_facts`), renumerotes apres les autres preuves pour
  qu'aucun identifiant ne se repete.

Rien n'est calcule ici. La question de l'utilisateur est recopiee telle quelle dans le champ `question`,
mais `brief_id` ne depend jamais d'elle.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Dict, List, Mapping, Optional

from .contracts import AnswerKind, ConversationBrief, Level

LOSS_CAPACITY = "loss_capacity"   # cle connue de conversation_fallback.MISSING_PHRASES
NO_ANALYSIS = "analysis"          # aucune idee analysee : dit par une phrase generale


def _number(evidence_id: str) -> int:
    match = re.fullmatch(r"E(\d+)", str(evidence_id))
    return int(match.group(1)) if match else 0


def _profile_facts(profile: Mapping[str, Any], first_number: int) -> List[Dict[str, Any]]:
    """Faits declares du profil, en preuves `E#` a partir de `first_number`. Outil en echec : aucune preuve."""
    from .agent_tools import get_profile_facts

    result = get_profile_facts(profile)
    if result.get("status") != "ok":
        return []
    facts = []
    for offset, entry in enumerate(result.get("evidence") or []):
        fact = copy.deepcopy(entry)
        fact["evidence_id"] = f"E{first_number + offset}"
        facts.append(fact)
    return facts


def _xray_parts(xray: Mapping[str, Any], level: Level) -> Dict[str, Any]:
    """Preuves, controles, glossaire et limites de la radiographie (portefeuille fictif sans idee)."""
    from .explanation_brief import _glossary_for, load_glossary
    from .reference_texts import merge_mandatory_limits

    # Portefeuille actuel seulement : une radiographie de donnees d'essai peut contenir des valeurs apres l'idee.
    evidence = [copy.deepcopy(entry) for entry in (xray.get("evidence") or {}).values()
                if entry.get("subject", "portfolio_before") == "portfolio_before"]
    checks = copy.deepcopy((xray.get("governance") or {}).get("checks") or [])
    field = "text_novice" if level == "novice" else "text_pro"
    limits = [{"limit_id": item["limit_id"], "text": item[field]}
              for item in xray.get("limits") or [] if isinstance(item.get(field), str)]
    rule_types = sorted({check["rule_type"] for check in checks})
    return {"evidence": evidence, "checks": checks, "idea": None,
            "glossary": _glossary_for(rule_types, level, load_glossary()),
            "limits": merge_mandatory_limits(limits, level), "ranked": []}


def _focus(answer_kind: AnswerKind, checks: List[Mapping[str, Any]], ranked: List[Mapping[str, Any]]) -> List[str]:
    if answer_kind == "explanation":
        return [factor["check_id"] for factor in ranked] or [
            c["check_id"] for c in checks if c.get("status") != "compliant"]
    if answer_kind == "what_changes":
        return [c["check_id"] for c in checks if c.get("status") != "compliant" and c.get("counterfactual")]
    return []


def build_conversation_brief(
    question: str,
    answer_kind: AnswerKind,
    level: Level,
    profile: Mapping[str, Any],
    *,
    result: Optional[Mapping[str, Any]] = None,
    xray: Optional[Mapping[str, Any]] = None,
) -> ConversationBrief:
    """Dossier de conversation pour une question deja routee (`question_routing.classify_question`).

    `result` est la derniere analyse (`AnalysisResult`) pour ce profil, `xray` la radiographie du portefeuille.
    Leve `ValueError` si `result` est incoherent (meme regle que le dossier d'explication).
    """
    from .explanation_brief import build_brief, build_profile_context
    from .reference_texts import mandatory_limits

    if answer_kind == "xray" and xray is not None:
        # Le portefeuille fictif actuel, meme apres une analyse : le dossier d'une analyse decrit l'apres-idee.
        parts = _xray_parts(xray, level)
    elif result is not None:
        explanation_brief = build_brief(result, level)   # type: ignore[arg-type]
        parts = {key: copy.deepcopy(explanation_brief[key]) for key in ("evidence", "checks", "idea", "glossary", "limits")}
        parts["ranked"] = explanation_brief["ranked_factors"]
    elif xray is not None:
        parts = _xray_parts(xray, level)
    else:
        parts = {"evidence": [], "checks": [], "idea": None, "glossary": [], "limits": mandatory_limits(level),
                 "ranked": []}
    first = max((_number(e.get("evidence_id", "")) for e in parts["evidence"]), default=0) + 1
    facts = _profile_facts(profile, first)
    evidence = parts["evidence"] + facts

    missing: List[str] = []
    if answer_kind == "profile" and not any(f.get("metric") == "profile_loss_capacity" for f in facts):
        missing.append(LOSS_CAPACITY)
    if answer_kind in ("explanation", "what_changes") and parts["idea"] is None:
        missing.append(NO_ANALYSIS)

    content: Dict[str, Any] = {
        "level": level,
        "answer_kind": answer_kind,
        "focus": _focus(answer_kind, parts["checks"], parts["ranked"]),
        "profile_context": build_profile_context(profile),
        "evidence": evidence,
        "checks": parts["checks"],
        "idea": parts["idea"],
        "glossary": parts["glossary"],
        "limits": parts["limits"],
        "cards": [],
        "missing": missing,
    }
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    brief: Dict[str, Any] = {"brief_id": "conv-" + digest.hexdigest()[:16], **content,
                             "question": question if isinstance(question, str) else ""}
    return brief  # type: ignore[return-value]
