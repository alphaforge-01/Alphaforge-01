"""Agent conversationnel avec outils : outils deterministes, dossier assemble, boucle bornee, pipeline."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alphaforge import conversation_router as cr  # noqa: E402
from alphaforge import conversation_tools as ct  # noqa: E402
from alphaforge.analysis_pipeline import converse_with_tools  # noqa: E402
from alphaforge.bedrock_client import BedrockConfig  # noqa: E402
from alphaforge.prompt_loader import load_prompt  # noqa: E402

CONFIG = BedrockConfig(mode="bedrock", analyst_model_id="m", explainer_model_id="m", conversation_model_id="m-conv",
                       guardrail_id="g-test", guardrail_version="1")
PASSED = {"check": "request_topic", "action": "none", "denied_topics": [], "grounding_score": None,
          "relevance_score": None, "mode": "block"}
REFUSED = {**PASSED, "action": "intervened", "denied_topics": ["order_execution"]}


def _evidence(eid, key, label, value="12,0 %"):
    return {"evidence_id": eid, "evidence_key": key, "tool_name": "analyze_portfolio", "metric": key.split(":")[0],
            "subject": "portfolio_before", "label_fr": label, "value": 0.12, "unit": "pct", "display_value": value,
            "qualifier": None, "period_start": "2021-01-01", "period_end": "2025-12-31", "as_of": "2025-12-31",
            "currency": "CAD"}


GLOSSARY = [
    {"term_id": "T1", "term": "Volatilité", "novice": {"definition": "Ampleur des variations.", "analogy": "Une route."},
     "pro": {"definition": "Ecart-type annualise.", "analogy": ""}},
    {"term_id": "T2", "term": "Corrélation", "novice": {"definition": "Mouvements ensemble.", "analogy": ""},
     "pro": {"definition": "Coefficient de Pearson.", "analogy": ""}},
]
UNIVERSE = [
    {"ticker": "NVDA", "name": "NVIDIA", "sector": "Information Technology"},
    {"ticker": "MSFT", "name": "Microsoft", "sector": "Information Technology"},
    {"ticker": "XIU.TO", "name": "iShares S&P/TSX 60", "sector": "Broad market (Canada)"},
]
XRAY = {
    "evidence": {"E1": _evidence("E1", "max_drawdown:portfolio_before", "Perte maximale"),
                 "E2": _evidence("E2", "volatility_ann:portfolio_before", "Volatilite annualisee")},
    "governance": {"checks": [{"check_id": "G1", "rule_id": "r1", "rule_type": "max_drawdown",
                               "label_fr": "Perte maximale", "status": "compliant", "evidence_ids": ["E1"]}]},
}
ANALYSIS_BRIEF = {
    # Memes identifiants que la radiographie : le dossier doit les renumeroter sans collision.
    "evidence": [_evidence("E1", "max_drawdown:portfolio_after", "Perte maximale apres", "26,0 %")],
    "checks": [{"check_id": "G1", "rule_id": "r1", "rule_type": "max_portfolio_drawdown", "label_fr": "Perte maximale",
                "status": "conflict", "evidence_ids": ["E1"]}],
    "idea": {"ticker": "NVDA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None},
    "limits": [{"limit_id": "L1", "text": "Passe"}],
    "glossary": [],
}


def providers(analysis=None):
    return ct.ConversationProviders(
        profile={"profile_id": "robert"},
        profile_context=lambda: {"risk_tolerance": "low_moderate"},
        profile_facts=lambda: {"status": "ok", "evidence": [
            {**_evidence("X", "horizon:profile", "Horizon", "3 a 5 ans"), "unit": "text"}],
            "data": {"missing": ["loss_capacity"]}},
        xray=lambda: copy.deepcopy(XRAY),
        asset_facts=lambda ticker: {"evidence": {"E1": _evidence("E1", f"volatility_ann:{ticker}", "Vol. actif")}},
        universe=lambda: UNIVERSE,
        glossary=lambda: GLOSSARY,
        analysis_brief=lambda level: copy.deepcopy(analysis),
    )


# ---- outils ----

def test_glossary_tool_returns_the_definition_at_the_requested_level():
    box = ct.ConversationToolBox(providers(), "pro")
    result = box.call("lookup_glossary", {"term": "volatilite"})
    assert result["status"] == "ok" and result["definition"] == "Ecart-type annualise."
    brief = box.brief("c'est quoi la volatilite ?")
    assert brief["answer_kind"] == "concept" and brief["glossary"][0]["term_id"] == "T1" and brief["focus"] == ["T1"]


def test_glossary_tool_never_invents_a_missing_term():
    box = ct.ConversationToolBox(providers(), "novice")
    result = box.call("lookup_glossary", {"term": "ratio de Sharpe"})
    assert result["status"] == "not_found" and "Volatilité" in result["known_terms"]
    assert box.brief("q")["glossary"] == [] and any(m.startswith("definition") for m in box.missing)


def test_evidence_from_several_tools_is_renumbered_without_collision():
    box = ct.ConversationToolBox(providers(ANALYSIS_BRIEF), "novice")
    box.call("analyze_portfolio", {})
    box.call("get_current_analysis", {})
    brief = box.brief("pourquoi ?")
    ids = [e["evidence_id"] for e in brief["evidence"]]
    assert ids == ["E1", "E2", "E3"]
    assert [c["check_id"] for c in brief["checks"]] == ["G1", "G2"]
    assert brief["checks"][1]["evidence_ids"] == ["E3"] and brief["checks"][1]["status"] == "conflict"
    assert brief["answer_kind"] == "explanation" and "G2" in brief["focus"]


def test_current_analysis_without_simulation_is_reported_missing():
    box = ct.ConversationToolBox(providers(None), "novice")
    assert box.call("get_current_analysis", {})["status"] == "not_found"
    assert "analyse_en_cours" in box.brief("q")["missing"]


def test_list_assets_is_a_factual_listing_of_the_universe():
    box = ct.ConversationToolBox(providers(), "novice")
    result = box.call("list_assets", {"sector": "technologie"})
    assert result["assets"] == ["NVDA", "MSFT"]
    entry = box.brief("un peu de tech")["evidence"][0]
    assert entry["unit"] == "text" and "NVDA (NVIDIA)" in entry["display_value"]
    assert box.call("list_assets", {"sector": "inconnu"})["status"] == "error"


def test_tools_reject_assets_outside_the_universe():
    box = ct.ConversationToolBox(providers(), "novice")
    assert box.call("get_asset_facts", {"ticker": "ZZZZ"})["status"] == "error"
    assert box.call("propose_idea", {"ticker": "ZZZZ", "weight_pct": 10})["status"] == "error"
    assert box.call("propose_idea", {"ticker": "NVDA", "weight_pct": 0})["status"] == "error"
    assert box.proposal is None


def test_propose_idea_only_builds_a_proposal():
    box = ct.ConversationToolBox(providers(), "novice")
    assert box.call("propose_idea", {"ticker": "nvda", "weight_pct": 25})["status"] == "ok"
    assert box.proposal == {"ticker": "NVDA", "target_weight": 0.25, "funding_source": "pro_rata",
                            "funding_ticker": None}


def test_no_order_tool_exists_and_unknown_tools_are_refused():
    names = {spec["toolSpec"]["name"] for spec in ct.TOOL_SPECS}
    assert not any(word in name for name in names for word in ("order", "trade", "buy", "sell", "execute"))
    box = ct.ConversationToolBox(providers(), "novice")
    assert box.call("place_order", {"ticker": "NVDA"})["status"] == "error"


def test_tool_budget_is_bounded():
    box = ct.ConversationToolBox(providers(), "novice")
    for _ in range(ct.MAX_TOOL_CALLS):
        box.call("get_profile_facts", {})
    try:
        box.call("get_profile_facts", {})
    except ct.ToolBudgetExceeded:
        pass
    else:
        raise AssertionError("budget non borne")


def test_a_failing_provider_becomes_a_tool_error():
    bad = providers()
    bad.xray = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    box = ct.ConversationToolBox(bad, "novice")
    assert box.call("analyze_portfolio", {})["status"] == "error"


def test_trace_keeps_only_closed_parameters():
    box = ct.ConversationToolBox(providers(), "novice")
    box.call("lookup_glossary", {"term": "MARQUEUR volatilite"})
    box.call("list_assets", {"sector": "technologie"})
    calls = box.trace_calls()
    assert "MARQUEUR" not in json.dumps(calls)
    assert calls[1]["params"] == {"sector": "technologie"} and calls[1]["status"] == "ok"


def test_replay_rebuilds_the_brief_at_another_level_without_proposal():
    calls = [{"name": "lookup_glossary", "params": {"term": "volatilite"}},
             {"name": "propose_idea", "params": {"ticker": "NVDA", "weight_pct": 10}}]
    brief = ct.replay(providers(), "pro", calls, "q")
    assert brief["level"] == "pro" and brief["glossary"][0]["definition"] == "Ecart-type annualise."


# ---- boucle de l'agent ----

def tool_response(*uses):
    content = [{"toolUse": {"toolUseId": f"t{i}", "name": name, "input": params}}
               for i, (name, params) in enumerate(uses)]
    return {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": "tool_use"}


class FakeClient:
    def __init__(self, responses, score=0.9):
        self.responses = list(responses)
        self.calls = []
        self.score = score
        self.last_grounding_flags = {}

    def converse(self, model_id, messages, system=None, tool_config=None, inference_config=None):
        self.calls.append({"model_id": model_id, "messages": copy.deepcopy(messages), "tools": tool_config})
        return self.responses.pop(0)

    def check_output_grounding(self, source, query, answer):
        return {"check": "output_grounding", "action": "none", "denied_topics": [], "grounding_score": self.score,
                "relevance_score": 0.9, "mode": "detect"}


def test_router_prompt_forbids_choosing_assets_for_the_user():
    prompt = load_prompt(cr.PROMPT_NAME)
    assert "Ne choisis jamais un actif" in prompt and "propose_idea" in prompt
    assert chr(0x2014) not in prompt


def test_router_runs_tools_and_stops_on_finish_in_one_turn():
    box = ct.ConversationToolBox(providers(), "novice")
    client = FakeClient([tool_response(("analyze_portfolio", {}), ("finish", {}))])
    outcome = cr.run_router(client, "m-conv", box, "mon portefeuille est-il risque ?",
                            profile_label="Robert", has_analysis=False)
    assert outcome.turns == 1 and outcome.stop_reason == "finished"
    assert [c["name"] for c in box.calls] == ["analyze_portfolio"]
    assert client.calls[0]["tools"]["tools"]


def test_router_turns_are_bounded():
    box = ct.ConversationToolBox(providers(), "novice")
    client = FakeClient([tool_response(("get_profile_facts", {}))] * cr.MAX_TURNS)
    outcome = cr.run_router(client, "m", box, "q", profile_label="R", has_analysis=False)
    assert outcome.stop_reason == "max_turns" and len(client.calls) == cr.MAX_TURNS


def test_router_question_is_truncated():
    box = ct.ConversationToolBox(providers(), "novice")
    client = FakeClient([tool_response(("finish", {}))])
    cr.run_router(client, "m", box, "x" * 1000, profile_label="R", has_analysis=False)
    assert "x" * (cr.MAX_QUESTION_CHARS + 1) not in json.dumps(client.calls[0]["messages"])


# ---- pipeline ----

NOT_RUN = {**PASSED, "action": "not_run"}


def test_pipeline_offline_or_unchecked_question_returns_none():
    client = FakeClient([])
    assert converse_with_tools("q", "novice", providers(), "offline", request_check=PASSED) is None
    assert converse_with_tools("q", "novice", providers(), "bedrock", request_check=NOT_RUN,
                               client=client, config=CONFIG) is None
    assert converse_with_tools("q", "novice", providers(), "bedrock", request_check=None,
                               client=client, config=CONFIG) is None
    assert client.calls == []


def test_flagged_message_reaches_the_agent_with_the_notice_and_is_reformulated():
    client = FakeClient([tool_response(("propose_idea", {"ticker": "NVDA", "weight_pct": 5}))])
    out = converse_with_tools("Et si je mettais 5% de nvidia ?", "novice", providers(), "bedrock",
                              request_check=REFUSED, client=client, config=CONFIG)
    assert out["kind"] == "proposal" and out["notice"] == ["order_execution"]
    sent = json.dumps(client.calls[0]["messages"], ensure_ascii=False)
    assert "SIGNALEMENT DU GARDE-FOU" in sent and "passage d'ordres" in sent
    assert out["trace"][0]["details"]["guardrail_notice"] == ["order_execution"]


def test_flagged_answer_keeps_the_notice_in_the_brief_and_goes_through_controls():
    client = FakeClient([tool_response(("get_asset_facts", {"ticker": "NVDA"}), ("finish", {})),
                         {"output": {"message": {"role": "assistant", "content": [
                             {"text": json.dumps({"answer": "Sur la periode passee, la mesure atteint [E1]."})}]}},
                          "stopReason": "end_turn"}])
    out = converse_with_tools("Que va faire NVDA l'an prochain ?", "novice", providers(), "bedrock",
                              request_check={**REFUSED, "denied_topics": ["return_prediction"]},
                              client=client, config=CONFIG,
                              validate=lambda reply, brief: {"is_valid": True, "rejections": [],
                                                             "checked_references": []})
    assert out["kind"] == "answer" and out["reply"]["origin"] == "llm"
    assert out["brief"]["guardrail_notice"] == ["return_prediction"]
    assert [step["name"] for step in out["trace"]][-2:] == ["validation", "guardrail"]


def test_local_refusal_is_passed_as_a_flag():
    client = FakeClient([tool_response(("finish", {}))])
    out = converse_with_tools("q", "novice", providers(), "bedrock", request_check=PASSED, client=client,
                              config=CONFIG, flagged_topics=["order_execution"],
                              validate=lambda reply, brief: {"is_valid": True, "rejections": [],
                                                             "checked_references": []},
                              fallback=lambda brief: {"brief_id": brief["brief_id"], "answer": "CODE.",
                                                      "origin": "template", "model_id": None,
                                                      "prompt_version": None, "attempt": 0})
    assert out["notice"] == ["order_execution"]


def test_pipeline_proposal_is_never_simulated():
    client = FakeClient([tool_response(("propose_idea", {"ticker": "NVDA", "weight_pct": 25}))])
    out = converse_with_tools("un quart en nvidia", "novice", providers(), "bedrock", request_check=PASSED,
                              client=client, config=CONFIG)
    assert out["kind"] == "proposal" and out["idea"]["target_weight"] == 0.25
    assert len(client.calls) == 1


def test_pipeline_answer_goes_through_validation_and_guardrail():
    client = FakeClient([tool_response(("lookup_glossary", {"term": "volatilite"}), ("finish", {})),
                         {"output": {"message": {"role": "assistant", "content": [
                             {"text": json.dumps({"answer": "La volatilite [T1] decrit les variations."})}]}},
                          "stopReason": "end_turn"}])
    out = converse_with_tools("c'est quoi la volatilite ? MARQUEUR", "novice", providers(), "bedrock",
                              request_check=PASSED, client=client, config=CONFIG,
                              validate=lambda reply, brief: {"is_valid": True, "rejections": [],
                                                             "checked_references": []},
                              fallback=lambda brief: {"brief_id": brief["brief_id"], "answer": "CODE.",
                                                      "origin": "template", "model_id": None,
                                                      "prompt_version": None, "attempt": 0})
    assert out["kind"] == "answer" and out["reply"]["origin"] == "llm"
    assert [step["step"] for step in out["trace"]] == [1, 2, 3, 4]
    assert out["trace"][0]["details"]["tool_calls"][0]["tool_name"] == "lookup_glossary"
    assert "MARQUEUR" not in json.dumps(out["trace"])
    assert out["calls"][0]["name"] == "lookup_glossary"


def test_pipeline_router_failure_falls_back_to_rules():
    def broken(*args, **kwargs):
        raise cr.RouterFailure("x")
    assert converse_with_tools("q", "novice", providers(), "bedrock", request_check=PASSED,
                               client=FakeClient([]), config=CONFIG, router=broken) is None


# ---- niveau novice sans jargon ----

def test_novice_brief_renames_rules_without_jargon_and_keeps_status():
    from alphaforge.conversation_fallback import plain_brief
    box = ct.ConversationToolBox(providers(ANALYSIS_BRIEF), "novice")
    box.call("get_current_analysis", {})
    plain = plain_brief(box.brief("q"))
    assert plain["checks"][0]["label_fr"] == "Une plus forte baisse passée limitée"
    assert plain["checks"][0]["status"] == "conflict" and plain["checks"][0]["evidence_ids"] == ["E1"]
    pro = ct.ConversationToolBox(providers(ANALYSIS_BRIEF), "pro")
    pro.call("get_current_analysis", {})
    assert plain_brief(pro.brief("q"))["checks"][0]["label_fr"] == "Perte maximale"


def test_novice_fallback_uses_everyday_words():
    from alphaforge.conversation_fallback import build_fallback_reply
    box = ct.ConversationToolBox(providers(), "novice")
    box.call("analyze_portfolio", {})
    answer = build_fallback_reply(box.brief("q"))["answer"].casefold()
    assert "la plus forte baisse passée" in answer
    assert "perte maximale" not in answer and "volatilit" not in answer


def test_answer_prompt_has_a_novice_section_without_jargon():
    prompt = load_prompt("conversation_v1")
    assert "NIVEAU NOVICE" in prompt and "la plus forte baisse passee" in prompt
    assert chr(0x2014) not in prompt
