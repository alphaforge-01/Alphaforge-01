"""Tests du pipeline d'analyse du flux C. Aucun appel reseau ni AWS : doubles ecrits a la main."""
from dataclasses import replace
from pathlib import Path
import copy
import json
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.analysis_pipeline import (
    AnalysisError, check_request, explain, propose_variants, run_analysis,
)
from alphaforge.bedrock_client import BedrockConfig, BedrockError
from alphaforge.contracts import AnalysisResult, ExplanationResult, check_keys
from alphaforge.fixture_collaborators import fixture_deps
from alphaforge.tool_specs import AnalystFailure, AnalystOutcome, ToolBudgetExceeded

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_KEY = "AKIA" + "X" * 16
BEDROCK_CONFIG = BedrockConfig(mode="bedrock", analyst_model_id="model-test")
GUARDRAIL_CONFIG = BedrockConfig(
    mode="bedrock", analyst_model_id="model-test", explainer_model_id="model-test",
    guardrail_id="g-test", guardrail_version="1")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run(profile="robert", **kwargs):
    kwargs.setdefault("deps", fixture_deps())
    kwargs.setdefault("mode", "offline")
    kwargs.setdefault("config", BedrockConfig())
    return run_analysis(
        load(f"profile_{profile}.json"), load("portfolio_robert.json"), load("idea_tsla_25.json"), **kwargs)


class NetworkForbiddenClient:
    """Double dont tout acces est une erreur de test."""

    config = BedrockConfig(mode="bedrock", analyst_model_id="m", guardrail_id="g", guardrail_version="1")

    def __getattr__(self, name):
        raise AssertionError(f"acces reseau interdit : {name}")


class FakeClient:
    def __init__(self, config=GUARDRAIL_CONFIG, grounding=None, request=None, error=None):
        self.config = config
        self._grounding, self._request, self._error = grounding, request, error
        self.calls = []

    def check_output_grounding(self, source, query, answer):
        self.calls.append(("grounding", source, query, answer))
        if self._error:
            raise self._error
        return self._grounding

    def check_request_topic(self, text):
        self.calls.append(("request", text))
        if self._error:
            raise self._error
        return self._request


def guardrail(check, action="none", topics=(), grounding=None, relevance=None):
    return {"check": check, "action": action, "denied_topics": list(topics),
            "grounding_score": grounding, "relevance_score": relevance, "mode": "detect"}


def agent_runner(client, model_id, toolbox, idea, profile):
    toolbox.call("analyze_portfolio")
    toolbox.call("simulate_portfolio_change", dict(idea))
    ids = list(toolbox.evidence())[:1]
    return AnalystOutcome(
        submission={"understood_idea": idea, "variants": [], "highlight_evidence_ids": ids,
                    "unsupported_requests": []},
        actor="agent", model_id=model_id, turns=3, stop_reason="submitted")


def raising(error):
    def runner(client, model_id, toolbox, idea, profile):
        toolbox.call("analyze_portfolio")
        raise error
    return runner


# ---- run_analysis offline ----

def test_offline_result_shape_and_trace():
    result = run("robert")
    assert check_keys(result, AnalysisResult) == []
    assert result["is_fixture"] is True and result["mode"] == "offline"
    trace = result["trace"]
    assert [(t["step"], t["name"]) for t in trace] == [(1, "analysis"), (2, "governance"), (3, "brief")]
    assert trace[0]["actor"] == "code" and trace[0]["details"]["stop_reason"] == "scripted"
    assert trace[1]["actor"] == "code" and trace[2]["actor"] == "code"
    assert all(t["status"] == "ok" for t in trace)
    assert [c["tool_name"] for c in trace[0]["details"]["tool_calls"]] == [
        "analyze_portfolio", "simulate_portfolio_change"]


def test_robert_conflict_amira_compliant_same_asset_figures():
    robert, amira = run("robert"), run("amira")
    assert robert["governance_after"]["overall_status"] == "conflict"
    assert amira["governance_after"]["overall_status"] == "compliant"
    margins_robert = [c["margin"] for c in robert["governance_after"]["checks"]]
    margins_amira = [c["margin"] for c in amira["governance_after"]["checks"]]
    assert margins_robert != margins_amira
    assert robert["snapshot_after"] == amira["snapshot_after"]
    assert robert["snapshot_before"] == amira["snapshot_before"]
    assert robert["evidence"] == amira["evidence"]


def test_unknown_mode_and_invalid_idea_raise():
    with pytest.raises(AnalysisError):
        run(mode="turbo")
    bad = load("idea_tsla_25.json")
    bad["target_weight"] = 5
    with pytest.raises(AnalysisError):
        run_analysis(load("profile_robert.json"), load("portfolio_robert.json"), bad,
                     deps=fixture_deps(), config=BedrockConfig())


# ---- run_analysis bedrock et replis ----

def test_bedrock_without_complete_config_falls_back_offline():
    called = []
    result = run("robert", mode="bedrock", config=BedrockConfig(), analyst_runner=lambda *a: called.append(1))
    step = result["trace"][0]
    assert called == [] and result["mode"] == "offline"
    assert step["status"] == "fallback" and step["actor"] == "code"
    assert step["details"]["fallback_reason"] == "configuration_incomplete"


@pytest.mark.parametrize("error, name", [
    (BedrockError("erreur " + FAKE_KEY), "BedrockError"),
    (AnalystFailure("pas de soumission " + FAKE_KEY), "AnalystFailure"),
    (ToolBudgetExceeded("budget " + FAKE_KEY), "ToolBudgetExceeded"),
])
def test_runner_failure_falls_back_to_scripted_sequence(error, name):
    result = run("robert", mode="bedrock", config=BEDROCK_CONFIG, client=FakeClient(),
                 analyst_runner=raising(error))
    step = result["trace"][0]
    assert result["mode"] == "offline" and step["actor"] == "code"
    assert step["status"] == "fallback"
    assert step["details"]["fallback_reason"].startswith(name)
    assert FAKE_KEY not in json.dumps(result["trace"])
    assert step["details"]["stop_reason"] == "scripted"
    # la trace ne garde que les appels de la sequence scriptee, pas ceux de l'agent echoue
    assert [c["tool_name"] for c in step["details"]["tool_calls"]] == [
        "analyze_portfolio", "simulate_portfolio_change"]
    assert result["governance_after"]["overall_status"] == "conflict"


def test_successful_agent_runner():
    result = run("robert", mode="bedrock", config=BEDROCK_CONFIG, client=FakeClient(),
                 analyst_runner=agent_runner)
    step = result["trace"][0]
    assert result["mode"] == "bedrock"
    assert step["actor"] == "agent" and step["status"] == "ok" and step["model_id"] == "model-test"
    assert step["details"]["turns"] == 3 and "fallback_reason" not in step["details"]
    assert step["details"]["mode_effective"] == "bedrock"
    assert result["submission"]["highlight_evidence_ids"] == ["E5"]
    assert check_keys(result, AnalysisResult) == []


def test_agent_variants_ignored_ids_not_in_evidence():
    def runner(client, model_id, toolbox, idea, profile):
        outcome = agent_runner(client, model_id, toolbox, idea, profile)
        outcome.submission["highlight_evidence_ids"] = ["E99", "E5"]
        return outcome

    result = run("robert", mode="bedrock", config=BEDROCK_CONFIG, client=FakeClient(), analyst_runner=runner)
    assert result["submission"]["highlight_evidence_ids"] == ["E5"]


# ---- explain ----

def test_explain_offline_steps_and_markdown():
    deps = fixture_deps()
    result = run("robert", deps=deps)
    explanation = explain(result, "novice", deps=deps, config=BedrockConfig())
    assert check_keys(explanation, ExplanationResult) == []
    trace = explanation["trace"]
    assert [(t["step"], t["name"], t["status"]) for t in trace] == [
        (4, "explanation", "ok"), (5, "validation", "ok"), (6, "guardrail", "skipped")]
    assert trace[2]["details"]["reason"] == "mode_offline"
    assert explanation["validation"]["is_valid"] is True
    assert explanation["guardrail"]["action"] == "not_run"
    assert not re.search(r"\[[A-Z]\d+\]", explanation["rendered_markdown"])
    assert "en conflit" in explanation["rendered_markdown"]


def test_explain_levels_differ_in_limits_but_share_evidence_values():
    deps = fixture_deps()
    result = run("robert", deps=deps)
    novice = explain(result, "novice", deps=deps, config=BedrockConfig())
    pro = explain(result, "pro", deps=deps, config=BedrockConfig())
    assert novice["output"]["limits_context"] != pro["output"]["limits_context"]
    assert novice["rendered_markdown"] != pro["rendered_markdown"]
    brief_novice = deps.build_brief(result, "novice")
    brief_pro = deps.build_brief(result, "pro")
    assert brief_novice["evidence"] == brief_pro["evidence"]
    assert brief_novice["limits"] != brief_pro["limits"]


def test_explain_unknown_mode_raises():
    deps = fixture_deps()
    with pytest.raises(AnalysisError):
        explain(run("robert", deps=deps), "novice", mode="turbo", deps=deps, config=BedrockConfig())


def llm_output(deps, result, level="novice"):
    output = deps.render_template(deps.build_brief(result, level))
    output["origin"] = "llm"
    return output


def test_explain_bedrock_invalid_text_falls_back_to_template():
    deps = fixture_deps()
    result = run("robert", deps=deps)

    def runner(client, model_id, brief, validate):
        invalid = load("explainer_output_invalid.json")
        invalid["origin"] = "llm"
        return invalid

    explanation = explain(result, "novice", "bedrock", deps=deps, client=FakeClient(grounding=guardrail(
        "output_grounding")), config=GUARDRAIL_CONFIG, explainer_runner=runner)
    step4, step5, _ = explanation["trace"]
    assert step5["status"] == "fallback" and step4["status"] == "fallback"
    assert step5["details"]["is_valid"] is True
    assert step4["details"]["fallback_reason"] == "rejet_du_validateur"
    assert "number_outside_registry" in step4["details"]["rejection_codes"]
    assert explanation["output"]["origin"] == "template"
    assert explanation["validation"]["is_valid"] is True
    assert "99" not in explanation["rendered_markdown"]


def test_explain_bedrock_valid_llm_text_is_kept_and_grounding_reflected():
    deps = fixture_deps()
    result = run("robert", deps=deps)
    client = FakeClient(grounding=guardrail("output_grounding", "none", grounding=0.82, relevance=0.9))
    explanation = explain(
        result, "novice", "bedrock", deps=deps, client=client, config=GUARDRAIL_CONFIG,
        explainer_runner=lambda c, m, brief, validate: llm_output(deps, result))
    step4, step5, step6 = explanation["trace"]
    assert step4["actor"] == "agent" and step4["status"] == "ok" and step4["model_id"] == "model-test"
    assert step5["status"] == "ok"
    assert step6["status"] == "ok" and step6["actor"] == "guardrail"
    assert step6["details"]["grounding_score"] == 0.82 and step6["details"]["relevance_score"] == 0.9
    assert explanation["guardrail"]["grounding_score"] == 0.82
    kind, source, query, answer = client.calls[0]
    from alphaforge.analysis_pipeline import _model_text
    # le garde-fou recoit les phrases du modele (limite de 5000 caracteres), pas le texte rendu complet
    assert answer == _model_text(explanation["output"], explanation["brief"]) and "brief_id" in source


def test_explain_bedrock_runner_error_falls_back_with_reason():
    deps = fixture_deps()
    result = run("robert", deps=deps)

    def runner(client, model_id, brief, validate):
        raise BedrockError("echec " + FAKE_KEY)

    explanation = explain(result, "novice", "bedrock", deps=deps, client=FakeClient(grounding=guardrail(
        "output_grounding")), config=GUARDRAIL_CONFIG, explainer_runner=runner)
    details = explanation["trace"][0]["details"]
    assert explanation["trace"][0]["status"] == "fallback"
    assert details["fallback_reason"].startswith("BedrockError")
    assert FAKE_KEY not in json.dumps(explanation["trace"])


def test_explain_bedrock_guardrail_error_and_missing_guardrail():
    deps = fixture_deps()
    result = run("robert", deps=deps)
    runner = lambda c, m, brief, validate: llm_output(deps, result)
    failing = explain(result, "novice", "bedrock", deps=deps, client=FakeClient(error=BedrockError("x")),
                      config=GUARDRAIL_CONFIG, explainer_runner=runner)
    assert failing["trace"][2]["status"] == "error"
    no_guardrail_config = BedrockConfig(mode="bedrock", analyst_model_id="model-test")
    missing = explain(result, "novice", "bedrock", deps=deps, client=FakeClient(config=no_guardrail_config),
                      config=no_guardrail_config, explainer_runner=runner)
    assert missing["trace"][2]["status"] == "skipped"
    assert missing["trace"][2]["details"]["reason"] == "garde_fou_non_configure"


# ---- check_request ----

def test_check_request_offline_not_run_without_touching_client():
    result = check_request("Achete 100 actions", mode="offline", client=NetworkForbiddenClient(),
                           config=BedrockConfig())
    assert result["action"] == "not_run" and result["check"] == "request_topic"


def test_check_request_without_guardrail_config_not_run():
    config = BedrockConfig(mode="bedrock", analyst_model_id="m")
    assert check_request("texte", config=config)["action"] == "not_run"


def test_check_request_bedrock_intervened_none_and_error():
    intervened = guardrail("request_topic", "intervened", topics=["trade_execution"])
    client = FakeClient(request=intervened)
    result = check_request("Passe un ordre", mode="bedrock", client=client)
    assert result["action"] == "intervened" and result["denied_topics"] == ["trade_execution"]
    assert client.calls == [("request", "Passe un ordre")]
    allowed = FakeClient(request=guardrail("request_topic", "none"))
    assert check_request("Compare deux fonds", mode="bedrock", client=allowed)["action"] == "none"
    broken = FakeClient(error=BedrockError("panne"))
    assert check_request("texte", mode="bedrock", client=broken)["action"] == "not_run"


def test_check_request_uses_config_mode_by_default():
    assert check_request("texte", config=BedrockConfig(), client=NetworkForbiddenClient())["action"] == "not_run"


# ---- propose_variants ----

PORTFOLIO = {"portfolio_id": "p", "label_fr": "t", "is_fictional": True, "base_currency": "CAD",
             "positions": [{"ticker": "AAA", "weight": 0.5}, {"ticker": "BBB", "weight": 0.3},
                           {"ticker": "TSLA", "weight": 0.2}]}


def idea(weight=0.25, source="pro_rata", funding=None):
    return {"ticker": "TSLA", "target_weight": weight, "funding_source": source, "funding_ticker": funding}


def check(status, cap=None, with_counterfactual=True):
    counterfactual = {"parameter": "target_weight", "compliant_at_or_below": cap, "display_value": "x"} \
        if with_counterfactual else None
    return {"check_id": "G1", "status": status, "counterfactual": counterfactual}


def governance(status, *checks):
    return {"overall_status": status, "checks": list(checks)}


def test_no_variant_when_compliant():
    assert propose_variants(governance("compliant", check("compliant")), idea(), PORTFOLIO) == []


def test_conflict_with_counterfactual_pro_rata():
    variants = propose_variants(governance("conflict", check("conflict", 0.22)), idea(), PORTFOLIO)
    assert [v["reason_code"] for v in variants] == ["reduce_weight", "change_funding_source"]
    assert variants[0]["idea"]["target_weight"] == 0.22
    assert variants[1]["idea"]["funding_source"] == "from_ticker"
    assert variants[1]["idea"]["funding_ticker"] == "AAA"
    assert variants[1]["idea"]["target_weight"] == 0.25


def test_from_ticker_gives_spread_across_existing():
    variants = propose_variants(
        governance("conflict", check("conflict", 0.2)), idea(source="from_ticker", funding="AAA"), PORTFOLIO)
    assert [v["reason_code"] for v in variants] == ["reduce_weight", "spread_across_existing"]
    assert variants[1]["idea"]["funding_source"] == "pro_rata" and variants[1]["idea"]["funding_ticker"] is None


def test_smallest_counterfactual_cap_is_used_and_none_ignored():
    gov = governance("conflict", check("conflict", 0.22), check("tension", 0.2), check("conflict", None))
    assert propose_variants(gov, idea(), PORTFOLIO)[0]["idea"]["target_weight"] == 0.2


def test_without_counterfactual_halves_weight():
    gov = governance("tension", check("tension", with_counterfactual=False))
    variants = propose_variants(gov, idea(0.3), PORTFOLIO)
    assert variants[0]["reason_code"] == "reduce_weight" and variants[0]["idea"]["target_weight"] == 0.15


def test_at_most_two_variants_and_no_funding_variant_without_other_positions():
    gov = governance("conflict", check("conflict", 0.1))
    assert len(propose_variants(gov, idea(), PORTFOLIO)) <= 2
    alone = {**PORTFOLIO, "positions": [{"ticker": "TSLA", "weight": 1.0}]}
    assert [v["reason_code"] for v in propose_variants(gov, idea(), alone)] == ["reduce_weight"]


def test_counterfactual_not_below_requested_weight_gives_no_reduction():
    gov = governance("conflict", check("conflict", 0.5))
    codes = [v["reason_code"] for v in propose_variants(gov, idea(0.25), PORTFOLIO)]
    assert "reduce_weight" not in codes


# ---- variantes dans un run complet ----

def test_variants_go_back_through_governance():
    base = fixture_deps()
    evaluations = []

    def evaluate(profile, snapshot, simulate_fn=None, idea=None, *, evidence=None):
        evaluations.append({"subject": snapshot.get("subject"), "idea": copy.deepcopy(idea),
                            "has_simulate_fn": simulate_fn is not None})
        return base.evaluate(profile, snapshot, simulate_fn=simulate_fn, idea=idea, evidence=evidence)

    simulated = []

    def simulate(portfolio, candidate, as_of=None, capital_cad=None):
        simulated.append(copy.deepcopy(candidate))
        return base.simulate_portfolio_change(portfolio, candidate, as_of=as_of, capital_cad=capital_cad)

    deps = replace(base, is_fixture=False, supports_variants=True, evaluate=evaluate,
                   simulate_portfolio_change=simulate)
    # SPY pese 30 % : il peut financer les 25 % demandes (sinon aucune variante de financement)
    funded = load("portfolio_robert.json")
    for position in funded["positions"]:
        position["weight"] = {"SPY": 0.30, "XIU.TO": 0.10, "XBB.TO": 0.20, "AGG": 0.15, "ZST.TO": 0.15,
                              "GLD": 0.10}[position["ticker"]]
    result = run_analysis(load("profile_robert.json"), funded, load("idea_tsla_25.json"), deps=deps,
                          mode="offline", config=BedrockConfig())
    assert result["is_fixture"] is False
    assert [v["variant_id"] for v in result["variants"]] == ["V1", "V2"]
    assert [v["reason_code"] for v in result["variants"]] == ["reduce_weight", "change_funding_source"]
    assert [v["snapshot"]["subject"] for v in result["variants"]] == ["variant:V1", "variant:V2"]
    assert [v["governance"]["subject"] for v in result["variants"]] == ["variant:V1", "variant:V2"]
    variant_evals = [e for e in evaluations if str(e["subject"]).startswith("variant:")]
    assert [e["subject"] for e in variant_evals] == ["variant:V1", "variant:V2"]
    assert [e["idea"] for e in variant_evals] == [v["idea"] for v in result["variants"]]
    assert all(e["has_simulate_fn"] for e in variant_evals)
    assert len(evaluations) == 4
    assert result["variants"][0]["idea"]["target_weight"] == 0.22
    assert [v["reason_code"] for v in result["submission"]["variants"]] == ["reduce_weight", "change_funding_source"]
    assert [v["variant_id"] for v in result["trace"][1]["details"]["variants"]] == ["V1", "V2"]
    # chaque variante est simulee par l'outil deterministe (idee initiale + 2 variantes + appels du script)
    assert [s["target_weight"] for s in simulated][-2:] == [0.22, 0.25]
    assert any(c["tool_name"] == "simulate_portfolio_change" for c in result["trace"][0]["details"]["tool_calls"])


def test_compliant_run_has_no_variants_with_variants_supported():
    deps = replace(fixture_deps(), is_fixture=False, supports_variants=True)
    assert run("amira", deps=deps)["variants"] == []
