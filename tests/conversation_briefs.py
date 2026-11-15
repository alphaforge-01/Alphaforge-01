"""Dossiers de conversation fictifs pour les tests (Robert, idée fictive de 25 % dans TSLA)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from alphaforge.analysis_pipeline import run_analysis
from alphaforge.bedrock_client import BedrockConfig
from alphaforge.fixture_collaborators import fixture_deps

FIXTURES = Path(__file__).parent / "fixtures"
QUESTION = "Pourquoi mon idee est-elle en conflit ? MARQUEUR-QUESTION"
# Faits déclarés du profil (sujet "profile"), au format des preuves de get_profile_facts : valeurs fictives.
PROFILE_EVIDENCE = [
    {"evidence_id": "E90", "evidence_key": "profile_objective:profile", "tool_name": "get_profile_facts",
     "metric": "profile_objective", "subject": "profile", "label_fr": "Objectif déclaré", "value": "preserve",
     "unit": "text", "display_value": "Préserver le capital avant la retraite", "qualifier": None,
     "period_start": None, "period_end": None},
    {"evidence_id": "E91", "evidence_key": "profile_horizon:profile", "tool_name": "get_profile_facts",
     "metric": "profile_horizon", "subject": "profile", "label_fr": "Horizon déclaré", "value": "3-5",
     "unit": "text", "display_value": "de 3 à 5 ans", "qualifier": None, "period_start": None, "period_end": None},
    {"evidence_id": "E92", "evidence_key": "profile_risk_tolerance:profile", "tool_name": "get_profile_facts",
     "metric": "profile_risk_tolerance", "subject": "profile", "label_fr": "Tolérance au risque déclarée",
     "value": "low_moderate", "unit": "text", "display_value": "faible à modérée", "qualifier": None,
     "period_start": None, "period_end": None},
]
_CACHE: dict = {}


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _explanation_brief(level):
    if level not in _CACHE:
        deps = fixture_deps()
        result = run_analysis(_load("profile_robert.json"), _load("portfolio_robert.json"),
                              _load("idea_tsla_25.json"), deps=deps, config=BedrockConfig())
        _CACHE[level] = deps.build_brief(result, level)
    return copy.deepcopy(_CACHE[level])


def make_brief(answer_kind="explanation", level="novice", **overrides):
    """Dossier de conversation complet ; `overrides` remplace des champs (focus, missing, evidence...)."""
    eb = _explanation_brief(level)
    brief = {
        "brief_id": "conv-test", "level": level, "answer_kind": answer_kind, "focus": [], "question": QUESTION,
        "profile_context": eb.get("profile_context"), "evidence": eb["evidence"] + copy.deepcopy(PROFILE_EVIDENCE),
        "checks": eb["checks"], "idea": eb["idea"], "glossary": eb["glossary"], "limits": eb["limits"],
        "cards": [], "missing": [],
    }
    brief.update(overrides)
    return brief


def reply(text, brief=None, origin="llm"):
    return {"brief_id": (brief or {}).get("brief_id", "conv-test"), "answer": text, "origin": origin,
            "model_id": "m" if origin == "llm" else None, "prompt_version": "conversation_v1" if origin == "llm"
            else None, "attempt": 1 if origin == "llm" else 0}


def check_by_status(brief, status):
    return next(c for c in brief["checks"] if c["status"] == status)


def evidence_of(brief, check):
    ids = {e["evidence_id"] for e in brief["evidence"]}
    return next(ref for ref in check["evidence_ids"] if ref in ids)
