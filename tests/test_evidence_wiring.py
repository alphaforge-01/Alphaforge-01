"""Tests du cablage des preuves entre les outils (flux A), la gouvernance (flux B) et le pipeline (flux C).

Verifie que la gouvernance recoit les preuves, que chaque couple (metrique, sujet) designe une seule preuve,
et que le resultat d'explication porte le dossier transmis. Aucun appel reseau ni AWS.
"""
from dataclasses import replace
from pathlib import Path
import copy
import itertools
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.analysis_pipeline import AnalysisError, explain, run_analysis
from alphaforge.bedrock_client import BedrockConfig
from alphaforge.fixture_collaborators import fixture_deps
from alphaforge.tool_specs import AnalystOutcome

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


PROFILE, PORTFOLIO, IDEA = load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json")


def deps_with_unique_evidence(calls):
    """Outils factices dont chaque simulation produit des preuves a identifiants neufs, de sujet portfolio_after."""
    base = fixture_deps()
    counter = itertools.count(1)

    def simulate(portfolio, idea, as_of=None, capital_cad=None):
        n = next(counter)
        result = base.simulate_portfolio_change(portfolio, idea, as_of=as_of, capital_cad=capital_cad)
        for i, entry in enumerate(result["evidence"]):
            entry["evidence_id"] = f"S{n}-{i}"
            entry["subject"] = "portfolio_after"
            entry["evidence_key"] = f"{entry['metric']}:portfolio_after"
        result["call_id"] = f"sim-{n}"
        return result

    def evaluate(profile, snapshot, simulate_fn=None, idea=None, *, evidence=None):
        calls.append({"subject": snapshot["subject"], "evidence": copy.deepcopy(evidence)})
        return base.evaluate(profile, snapshot, simulate_fn=simulate_fn, idea=idea, evidence=evidence)

    return replace(base, is_fixture=False, supports_variants=True, simulate_portfolio_change=simulate,
                   evaluate=evaluate)


def test_evaluate_receives_the_evidence_registry_as_keyword():
    calls = []
    run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps_with_unique_evidence(calls), config=BedrockConfig())
    assert calls, "evaluate n'a jamais ete appele"
    for call in calls:
        assert isinstance(call["evidence"], dict) and call["evidence"]
        assert all(entry["evidence_id"] == key for key, entry in call["evidence"].items())


def funded_portfolio():
    """Portefeuille ou SPY (30 %) peut financer les 25 % demandes."""
    portfolio = copy.deepcopy(PORTFOLIO)
    weights = {"SPY": 0.30, "XIU.TO": 0.10, "XBB.TO": 0.20, "AGG": 0.15, "ZST.TO": 0.15, "GLD": 0.10}
    for position in portfolio["positions"]:
        position["weight"] = weights[position["ticker"]]
    return portfolio


def test_variant_evidence_is_relabeled_so_subjects_do_not_collide():
    calls = []
    result = run_analysis(PROFILE, funded_portfolio(), IDEA, deps=deps_with_unique_evidence(calls),
                          config=BedrockConfig())
    assert [v["variant_id"] for v in result["variants"]] == ["V1", "V2"]
    by_subject = {}
    for entry in result["evidence"].values():
        by_subject.setdefault((entry["metric"], entry["subject"]), []).append(entry["evidence_id"])
    # une seule preuve par couple (metrique, sujet) pour l'idee demandee, apres reetiquetage
    assert all(len(ids) == 1 for (metric, subject), ids in by_subject.items() if subject == "portfolio_after")
    for variant_id in ("V1", "V2"):
        subjects = [e["subject"] for e in result["evidence"].values() if e["subject"] == f"variant:{variant_id}"]
        assert subjects, f"aucune preuve etiquetee variant:{variant_id}"
    keys = [e["evidence_key"] for e in result["evidence"].values() if e["subject"] == "variant:V1"]
    assert keys and all(k.endswith(":variant:V1") for k in keys)
    last_variant_call = [c for c in calls if c["subject"] == "variant:V2"][0]
    assert any(e["subject"] == "variant:V2" for e in last_variant_call["evidence"].values())


def test_explored_simulations_of_the_agent_do_not_pollute_the_idea_evidence():
    calls = []
    deps = deps_with_unique_evidence(calls)
    other = {**IDEA, "target_weight": 0.10}

    def runner(client, model_id, toolbox, idea, profile):
        toolbox.call("analyze_portfolio")
        toolbox.call("simulate_portfolio_change", other)   # exploration de l'agent
        toolbox.call("simulate_portfolio_change", dict(idea))
        return AnalystOutcome(
            submission={"understood_idea": idea, "variants": [], "highlight_evidence_ids": [],
                        "unsupported_requests": []}, actor="agent", model_id=model_id, turns=3)

    config = BedrockConfig(mode="bedrock", analyst_model_id="model-test")
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, mode="bedrock", config=config, client=object(),
                          deps=deps, analyst_runner=runner)
    after = [e for e in result["evidence"].values() if e["subject"] == "portfolio_after"]
    explored = [e for e in result["evidence"].values() if e["subject"].startswith("explored:")]
    assert after and explored
    assert len({e["metric"] for e in after}) == len(after)   # pas de metrique en double pour l'idee


def test_snapshot_subjects_are_forced():
    deps = deps_with_unique_evidence([])
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps, config=BedrockConfig())
    assert result["snapshot_before"]["subject"] == "portfolio_before"
    assert result["snapshot_after"]["subject"] == "portfolio_after"
    assert result["governance_before"]["subject"] == "portfolio_before"
    assert result["governance_after"]["subject"] == "portfolio_after"


def test_explanation_result_carries_the_brief_seen_by_the_explainer():
    deps = fixture_deps()
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps, config=BedrockConfig())
    explanation = explain(result, "pro", deps=deps, config=BedrockConfig())
    assert explanation["brief"] == deps.build_brief(result, "pro")
    assert explanation["brief"]["level"] == "pro"


def test_build_brief_value_error_becomes_a_readable_analysis_error():
    deps = fixture_deps()
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps, config=BedrockConfig())

    def failing(result, level):
        raise ValueError("Limite obligatoire absente du resultat : L9")

    with pytest.raises(AnalysisError, match="Dossier d'explication impossible"):
        explain(result, "novice", deps=replace(deps, build_brief=failing), config=BedrockConfig())


def test_default_limits_come_from_the_flux_b_catalog():
    from alphaforge.analysis_pipeline import _load_limits
    from alphaforge.pipeline_deps import PipelineDeps

    base = fixture_deps()
    deps = replace(base, limits_for=None)
    assert isinstance(deps, PipelineDeps)
    limits = _load_limits(deps, ["LM1"])
    ids = [item["limit_id"] for item in limits]
    assert "LM1" in ids and len(ids) >= 2   # catalogue complet, pas seulement les limites citees
    assert all(item["text_novice"] and item["text_pro"] for item in limits)


def test_limits_for_from_deps_still_wins():
    deps = replace(fixture_deps(), limits_for=lambda ids: [{"limit_id": "X", "text_novice": "a", "text_pro": "b"}])
    from alphaforge.analysis_pipeline import _load_limits
    assert _load_limits(deps, []) == [{"limit_id": "X", "text_novice": "a", "text_pro": "b"}]


# ---- variantes finançables, trace complete, import strict ----

def test_no_funding_variant_when_no_position_can_fund_the_idea():
    from alphaforge.analysis_pipeline import propose_variants
    governance = load("analysis_result_robert_tsla.json")["governance_after"]
    variants = propose_variants(governance, IDEA, PORTFOLIO)   # la plus grosse autre position pese 20 % < 25 %
    assert [v["reason_code"] for v in variants] == ["reduce_weight"]


def test_funding_variant_uses_the_largest_position_that_can_fund():
    from alphaforge.analysis_pipeline import propose_variants
    governance = load("analysis_result_robert_tsla.json")["governance_after"]
    variants = propose_variants(governance, IDEA, funded_portfolio())
    funding = [v for v in variants if v["reason_code"] == "change_funding_source"]
    assert funding and funding[0]["idea"]["funding_ticker"] == "SPY"


def test_trace_step_one_lists_variant_simulations_too():
    result = run_analysis(PROFILE, funded_portfolio(), IDEA, deps=deps_with_unique_evidence([]),
                          config=BedrockConfig())
    simulated = [c["params"]["target_weight"] for c in result["trace"][0]["details"]["tool_calls"]
                 if c["tool_name"] == "simulate_portfolio_change"]
    assert len(simulated) == 1 + len(result["variants"])   # l'idee puis chaque variante


def test_load_real_deps_only_swallows_a_missing_module(monkeypatch):
    import importlib
    from alphaforge import pipeline_deps

    real_import = importlib.import_module

    def missing(name, *a, **k):
        if name == "alphaforge.agent_tools":
            raise ModuleNotFoundError("absent", name="alphaforge.agent_tools")
        return real_import(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", missing)
    assert pipeline_deps.load_real_deps() is None   # module absent : cas normal, bouchons

    def broken(name, *a, **k):
        if name == "alphaforge.agent_tools":
            raise ModuleNotFoundError("No module named 'numpyy'", name="numpyy")
        return real_import(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", broken)
    with pytest.raises(ModuleNotFoundError):
        pipeline_deps.load_real_deps()                # bogue dans un module existant : il remonte


def test_explanation_result_matches_the_contract_with_the_optional_brief():
    from alphaforge.contracts import ExplanationResult, check_keys
    deps = fixture_deps()
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps, config=BedrockConfig())
    explanation = explain(result, "novice", deps=deps, config=BedrockConfig())
    assert check_keys(explanation, ExplanationResult) == []
    without_brief = {key: value for key, value in explanation.items() if key != "brief"}
    assert check_keys(without_brief, ExplanationResult) == []   # la cle reste facultative pour les anciens appelants
    assert explanation["brief"]["brief_id"] == deps.build_brief(result, "novice")["brief_id"]
