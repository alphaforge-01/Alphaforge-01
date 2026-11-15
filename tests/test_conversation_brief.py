"""Dossier de l'agent conversationnel (issue 78) : faits du code, identifiants uniques, ce qui manque."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alphaforge.analysis_pipeline import answer_question, run_analysis  # noqa: E402
from alphaforge.contracts import ConversationBrief, check_keys  # noqa: E402
from alphaforge.conversation_brief import LOSS_CAPACITY, NO_ANALYSIS, build_conversation_brief  # noqa: E402
from alphaforge.explanation_validator import validate_reply  # noqa: E402
from alphaforge.pipeline_deps import resolve_deps  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

IDEA = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}


@pytest.fixture(scope="module")
def robert():
    persona = load_personas()["robert"]
    deps = resolve_deps()
    result = run_analysis(persona["profile"], persona["portfolio"], IDEA, deps=deps)
    from alphaforge.tool_specs import ToolBox

    toolbox = ToolBox(deps, persona["portfolio"], as_of=None, capital_cad=persona["profile"].get("capital_cad"))
    tool_result = toolbox.call("analyze_portfolio")
    evidence = toolbox.evidence()
    xray = {"snapshot": tool_result["data"], "evidence": evidence,
            "governance": deps.evaluate(persona["profile"], tool_result["data"], evidence=evidence),
            "limits": result["limits"]}
    return persona, result, xray


@pytest.mark.parametrize("kind", ["explanation", "what_changes", "profile", "xray"])
@pytest.mark.parametrize("level", ["novice", "pro"])
def test_every_kind_gives_a_complete_brief_with_unique_ids_and_a_valid_code_reply(robert, kind, level):
    persona, result, xray = robert
    for source in ({"result": result}, {"xray": xray}):
        brief = build_conversation_brief("Question ?", kind, level, persona["profile"], **source)
        assert check_keys(brief, ConversationBrief) == []
        ids = [e["evidence_id"] for e in brief["evidence"]]
        assert len(ids) == len(set(ids))
        assert any(e.get("subject") == "profile" for e in brief["evidence"])     # faits declares du profil
        reply = answer_question(brief, "offline")["reply"]
        assert validate_reply(reply, brief)["is_valid"]


def test_brief_id_never_depends_on_the_question(robert):
    persona, result, _ = robert
    first = build_conversation_brief("une question", "explanation", "novice", persona["profile"], result=result)
    second = build_conversation_brief("une autre MARQUEUR", "explanation", "novice", persona["profile"], result=result)
    assert first["brief_id"] == second["brief_id"] and second["question"] == "une autre MARQUEUR"


def test_missing_information_is_declared(robert):
    persona, _, xray = robert
    profile = build_conversation_brief("q", "profile", "novice", persona["profile"], xray=xray)
    assert LOSS_CAPACITY in profile["missing"]
    no_idea = build_conversation_brief("q", "explanation", "novice", persona["profile"], xray=xray)
    assert NO_ANALYSIS in no_idea["missing"] and no_idea["idea"] is None


def test_focus_points_to_the_flagged_checks(robert):
    persona, result, _ = robert
    why = build_conversation_brief("q", "explanation", "novice", persona["profile"], result=result)
    flagged = {c["check_id"] for c in why["checks"] if c["status"] != "compliant"}
    assert set(why["focus"]) == flagged
    changes = build_conversation_brief("q", "what_changes", "novice", persona["profile"], result=result)
    assert changes["focus"] and all(
        next(c for c in changes["checks"] if c["check_id"] == ref)["counterfactual"] for ref in changes["focus"])


def test_without_any_analysis_or_xray_only_the_profile_remains(robert):
    persona, _, _ = robert
    brief = build_conversation_brief("q", "profile", "pro", persona["profile"])
    assert brief["checks"] == [] and brief["limits"] and brief["evidence"]
    assert all(e["subject"] == "profile" for e in brief["evidence"])
