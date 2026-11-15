"""Tests P1-9 : verdicts financier et ESG séparés, verdict global inchangé. Données fictives, aucun appel AWS."""
import copy
import itertools
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge.contracts import GovernanceResult, RuleCheck, check_keys  # noqa: E402
from alphaforge.governance import (  # noqa: E402
    ESG_RULE_TYPES, STATUS_SEVERITY, evaluate, is_esg_rule_type, partition_statuses, split_verdicts, worst_status,
)
from alphaforge.profiles import build_profile_from_answers, load_personas  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
STATUSES = ("compliant", "tension", "conflict", "missing_info")
IDEAS = {
    "tsla_25": ("TSLA", 0.25, "pro_rata"), "btc_20": ("BTC-USD", 0.20, "pro_rata"),
    "nvda_20": ("NVDA", 0.20, "from_ticker"), "xom_10": ("XOM", 0.10, "pro_rata"),
}
# (verdict financier, verdict ESG, verdict global) après l'idée, hors ligne, données réelles.
EXPECTED = {
    ("mateo", "tsla_25"): ("compliant", "missing_info", "missing_info"),
    ("mateo", "btc_20"): ("conflict", "missing_info", "conflict"),
    ("mateo", "nvda_20"): ("compliant", "missing_info", "missing_info"),
    ("mateo", "xom_10"): ("compliant", "missing_info", "missing_info"),
    ("robert", "tsla_25"): ("conflict", None, "conflict"), ("robert", "btc_20"): ("conflict", None, "conflict"),
    ("robert", "nvda_20"): ("tension", None, "tension"), ("robert", "xom_10"): ("compliant", None, "compliant"),
    ("amira", "tsla_25"): ("tension", None, "tension"), ("amira", "btc_20"): ("tension", None, "tension"),
    ("amira", "nvda_20"): ("tension", None, "tension"), ("amira", "xom_10"): ("compliant", None, "compliant"),
}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def analyse(persona_id, scenario):
    from alphaforge.analysis_pipeline import run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    persona = load_personas()[persona_id]
    ticker, weight, funding = IDEAS[scenario]
    funding_ticker = None
    if funding == "from_ticker":
        funding_ticker = max(persona["portfolio"]["positions"], key=lambda p: p["weight"])["ticker"]
    idea = {"ticker": ticker, "target_weight": weight, "funding_source": funding, "funding_ticker": funding_ticker}
    return run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline", config=BedrockConfig())


@pytest.fixture(scope="module")
def results():
    return {key: analyse(*key) for key in EXPECTED}


def rule(rule_id, rule_type="max_single_asset_weight", warn=0.2, limit=0.3):
    esg = rule_type == "esg_exclusion"
    return {"rule_id": rule_id, "rule_type": rule_type, "params": {}, "direction": "max",
            "warn_threshold": None if esg else warn, "limit_threshold": 0.0 if esg else limit,
            "unit": "bool" if esg else "pct", "label_fr": f"Règle {rule_id}", "origin": "checkbox",
            "is_assumption": True}


def snapshot(**overrides):
    base = {"subject": "portfolio_after", "weights": {"A": 1.0}, "volatility_ann": 0.10, "max_drawdown": 0.10,
            "max_drawdown_start": "2022-01-03", "max_drawdown_end": "2022-06-01", "recovery_days": None,
            "top_asset": "A", "top_asset_weight": 0.10, "weight_by_sector": {},
            "weight_by_asset_class": {"equity": 0.5, "etf_bond": 0.5}, "currency_exposure": {"CAD": 1.0},
            "defensive_share": 0.5, "largest_correlated_group_weight": None}
    base.update(overrides)
    return base


# ---------- la scène : Mateo avec XOM ----------

def test_mateo_with_xom_shows_financial_compliant_esg_missing_overall_missing(results):
    governance = results[("mateo", "xom_10")]["governance_after"]
    assert governance["financial_status"] == "compliant"
    assert governance["esg_status"] == "missing_info"
    assert governance["overall_status"] == "missing_info"
    financial = [c for c in governance["checks"] if c["rule_type"] != "esg_exclusion"]
    assert len(financial) == 6 and all(c["status"] == "compliant" for c in financial)
    (esg,) = [c for c in governance["checks"] if c["rule_type"] == "esg_exclusion"]
    assert esg["status"] == "missing_info" and esg["value"] is None and esg["evidence_ids"] == []


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_the_three_verdicts_of_every_demo_scenario(results, key):
    governance = results[key]["governance_after"]
    financial, esg, overall = EXPECTED[key]
    assert (governance["financial_status"], governance["esg_status"], governance["overall_status"]) == (
        financial, esg, overall)
    assert split_verdicts(governance) == {"overall": overall, "financial": financial, "esg": esg}


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_the_starting_portfolio_and_the_variants_carry_the_same_fields(results, key):
    result = results[key]
    for governance in [result["governance_before"], *(v["governance"] for v in result["variants"])]:
        assert "financial_status" in governance and "esg_status" in governance
        financial, esg = partition_statuses(governance["checks"])
        assert (governance["financial_status"], governance["esg_status"]) == (financial, esg)
    assert (key[0] == "mateo") == (result["governance_before"]["esg_status"] is not None)


def test_a_financial_conflict_is_not_hidden_by_the_esg_gap(results):
    governance = results[("mateo", "btc_20")]["governance_after"]
    assert governance["financial_status"] == "conflict" and governance["esg_status"] == "missing_info"
    assert governance["overall_status"] == "conflict"


@pytest.mark.parametrize("persona_id", ["robert", "amira"])
def test_profiles_without_esg_rule_get_no_esg_verdict(results, persona_id):
    for scenario in IDEAS:
        governance = results[(persona_id, scenario)]["governance_after"]
        assert "esg_status" in governance and governance["esg_status"] is None
        assert governance["financial_status"] == governance["overall_status"]
        assert all(c["rule_type"] != "esg_exclusion" for c in governance["checks"])


# ---------- priorités et calcul ----------

@pytest.mark.parametrize("financial", list(itertools.product(STATUSES, repeat=2)))
def test_financial_status_follows_the_existing_priorities(financial):
    values = {"compliant": 0.10, "tension": 0.25, "conflict": 0.40}
    checks_profile = {"profile_id": "t", "rules": [rule("R1"), rule("R2", "max_portfolio_volatility")]}
    shot = snapshot(top_asset_weight=values.get(financial[0]), volatility_ann=values.get(financial[1]))
    governance = evaluate(checks_profile, shot)
    assert governance["financial_status"] == worst_status(financial)
    assert governance["esg_status"] is None and governance["overall_status"] == governance["financial_status"]


def test_priority_order_is_the_existing_one():
    assert STATUS_SEVERITY["compliant"] < STATUS_SEVERITY["missing_info"] < STATUS_SEVERITY["tension"] < \
        STATUS_SEVERITY["conflict"]
    assert partition_statuses([{"rule_type": "max_single_asset_weight", "status": "tension"},
                               {"rule_type": "esg_exclusion", "status": "missing_info"}]) == ("tension", "missing_info")


@pytest.mark.parametrize("fin_value,expected_financial,expected_overall", [
    (0.10, "compliant", "missing_info"), (0.25, "tension", "tension"), (0.40, "conflict", "conflict"), (None, "missing_info", "missing_info"),
])
def test_financial_status_comes_only_from_financial_rules(fin_value, expected_financial, expected_overall):
    profile = {"profile_id": "t", "rules": [rule("R1"), rule("R7", "esg_exclusion")]}
    governance = evaluate(profile, snapshot(top_asset_weight=fin_value))
    assert governance["financial_status"] == expected_financial
    assert governance["esg_status"] == "missing_info"
    assert governance["overall_status"] == expected_overall


def test_esg_status_comes_only_from_esg_rules_whatever_the_financial_statuses():
    for value in (0.10, 0.25, 0.40, None):
        profile = {"profile_id": "t", "rules": [rule("R1"), rule("R7", "esg_exclusion")]}
        assert evaluate(profile, snapshot(top_asset_weight=value))["esg_status"] == "missing_info"


def test_overall_status_is_the_worst_of_the_two_verdicts_and_is_unchanged():
    profile = {"profile_id": "t", "rules": [rule("R1"), rule("R2", "max_portfolio_volatility"),
                                            rule("R7", "esg_exclusion")]}
    for top, vol in itertools.product((0.10, 0.25, 0.40, None), repeat=2):
        governance = evaluate(profile, snapshot(top_asset_weight=top, volatility_ann=vol))
        assert governance["overall_status"] == worst_status(c["status"] for c in governance["checks"])
        assert governance["overall_status"] == worst_status([governance["financial_status"],
                                                             governance["esg_status"]])


# ---------- jamais "conforme" sans preuve ESG ----------

def test_esg_rule_is_missing_info_whatever_the_snapshot_or_evidence():
    profile = {"profile_id": "t", "rules": [rule("R7", "esg_exclusion")]}
    shots = [snapshot(), snapshot(weight_by_asset_class={}), snapshot(top_asset_weight=0.0),
             snapshot(weight_by_sector={"Energy": 0.0})]
    fake = [{"evidence_id": "E1", "metric": "esg_exclusion", "subject": "portfolio_after", "value": 0.0},
            {"evidence_id": "E2", "metric": "esg_score", "subject": "portfolio_after", "value": 1.0}]
    for shot in shots:
        for evidence in (None, fake):
            governance = evaluate(profile, shot, evidence=evidence)
            assert governance["esg_status"] == "missing_info" and governance["checks"][0]["evidence_ids"] == []
            assert governance["overall_status"] == "missing_info"


def test_esg_status_is_never_compliant_for_any_persona_or_custom_profile(results):
    assert all(g["esg_status"] != "compliant" for r in results.values()
               for g in [r["governance_before"], r["governance_after"]])
    custom = build_profile_from_answers({"objective": "Croissance équilibrée", "horizon_years_min": 8,
                                         "horizon_years_max": 12, "risk_tolerance": "moderate",
                                         "experience": "intermediate", "esg_preference": "strong",
                                         "crypto_allowed": False, "capital_cad": 50000})
    governance = evaluate(custom, snapshot())
    assert governance["esg_status"] == "missing_info" and governance["financial_status"] == "compliant"


@pytest.mark.parametrize("preference", ["none", "moderate"])
def test_custom_profile_without_strong_esg_has_no_esg_verdict(preference):
    custom = build_profile_from_answers({"objective": "Croissance équilibrée", "horizon_years_min": 8,
                                         "horizon_years_max": 12, "risk_tolerance": "moderate",
                                         "experience": "intermediate", "esg_preference": preference,
                                         "crypto_allowed": False, "capital_cad": 50000})
    governance = evaluate(custom, snapshot())
    assert governance["esg_status"] is None and governance["financial_status"] == governance["overall_status"]


# ---------- familles absentes ----------

def test_profile_without_financial_rule_has_no_financial_verdict_but_keeps_its_overall():
    governance = evaluate({"profile_id": "t", "rules": [rule("R7", "esg_exclusion")]}, snapshot())
    assert governance["financial_status"] is None and governance["esg_status"] == "missing_info"
    assert governance["overall_status"] == "missing_info"


def test_profile_without_any_rule_keeps_the_legacy_overall_and_has_no_other_verdict():
    governance = evaluate({"profile_id": "t", "rules": []}, snapshot())
    assert governance["overall_status"] == "missing_info" and governance["checks"] == []
    assert governance["financial_status"] is None and governance["esg_status"] is None


def test_esg_rule_types_helper():
    assert ESG_RULE_TYPES == {"esg_exclusion"} and is_esg_rule_type("esg_exclusion")
    for other in ("max_single_asset_weight", "excluded_asset_class", "max_correlated_group_weight", None, ""):
        assert not is_esg_rule_type(other)


# ---------- compatibilité avec les anciens résultats ----------

def test_new_fields_are_optional_in_the_contract():
    assert {"financial_status", "esg_status"} <= set(GovernanceResult.__annotations__)
    assert GovernanceResult.__required_keys__ >= {"profile_id", "subject", "overall_status", "checks"}
    legacy = {"profile_id": "robert", "subject": "portfolio_after", "overall_status": "conflict", "checks": []}
    assert check_keys(legacy, GovernanceResult) == []
    assert "financial_status" not in GovernanceResult.__required_keys__ or check_keys(legacy, GovernanceResult) == []
    assert "NotRequired" in str(GovernanceResult.__annotations__["financial_status"])
    assert "NotRequired" in str(GovernanceResult.__annotations__["esg_status"])


@pytest.mark.parametrize("name", ["analysis_result_robert_tsla.json", "analysis_result_amira_tsla.json"])
def test_old_fixture_results_still_respect_the_contract_and_split_by_their_checks(name):
    result = load(name)
    for key in ("governance_before", "governance_after"):
        governance = result[key]
        assert "financial_status" not in governance and check_keys(governance, GovernanceResult) == []
        verdicts = split_verdicts(governance)
        assert verdicts["overall"] == governance["overall_status"]
        assert verdicts["esg"] is None
        expected = worst_status(c["status"] for c in governance["checks"]) if governance["checks"] else None
        assert verdicts["financial"] == expected            # fixture sans contrôle : aucun verdict inventé


def test_split_verdicts_reads_stored_fields_when_there_are_no_checks():
    stored = {"overall_status": "missing_info", "checks": [], "financial_status": "compliant",
              "esg_status": "missing_info"}
    assert split_verdicts(stored) == {"overall": "missing_info", "financial": "compliant", "esg": "missing_info"}
    assert split_verdicts({"overall_status": "tension", "checks": []}) == {"overall": "tension", "financial": None,
                                                                          "esg": None}


def test_split_verdicts_trusts_the_checks_over_inconsistent_stored_fields():
    governance = {"overall_status": "conflict", "financial_status": "compliant", "esg_status": "compliant",
                  "checks": [{"rule_type": "max_single_asset_weight", "status": "conflict"},
                             {"rule_type": "esg_exclusion", "status": "missing_info"}]}
    assert split_verdicts(governance) == {"overall": "conflict", "financial": "conflict", "esg": "missing_info"}


def test_evaluate_output_is_a_strict_superset_of_the_legacy_shape_and_json_serializable():
    persona = load_personas()["mateo"]["profile"]
    governance = evaluate(persona, snapshot())
    assert set(governance) == {"profile_id", "subject", "overall_status", "checks", "financial_status", "esg_status"}
    assert json.loads(json.dumps(governance))["esg_status"] == "missing_info"
    for check in governance["checks"]:
        assert check_keys(check, RuleCheck) == [] and set(check) == set(RuleCheck.__annotations__)


def test_checks_and_overall_status_are_identical_with_or_without_the_new_fields():
    profile = load_personas()["mateo"]["profile"]
    governance = evaluate(profile, snapshot(top_asset_weight=0.3))
    legacy = {k: v for k, v in governance.items() if k not in ("financial_status", "esg_status")}
    assert legacy["overall_status"] == worst_status(c["status"] for c in legacy["checks"])
    assert [c["rule_id"] for c in legacy["checks"]] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]


def test_thresholds_of_the_profiles_are_untouched():
    mateo = load_personas()["mateo"]["profile"]["rules"]
    assert [(r["rule_id"], r["warn_threshold"], r["limit_threshold"]) for r in mateo] == [
        ("R1", 0.25, 0.3), ("R2", 0.22, 0.32), ("R3", 0.3, 0.5), ("R4", 0.25, 0.15), ("R5", None, 0.0),
        ("R6", 0.7, 0.85), ("R7", None, 0.0)]


def test_brief_pipeline_and_fixture_flow_accept_results_with_and_without_the_fields():
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.explanation_brief import build_brief
    from alphaforge.fixture_collaborators import fixture_deps
    legacy = load("analysis_result_robert_tsla.json")
    assert "financial_status" not in legacy["governance_after"]
    assert build_brief(legacy, "novice")["checks"] == legacy["governance_after"]["checks"]
    deps = fixture_deps()
    result = run_analysis(load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json"),
                          deps=deps, config=BedrockConfig())
    explanation = explain(result, "pro", deps=deps, config=BedrockConfig())
    assert explanation["validation"]["is_valid"] is True
    assert split_verdicts(result["governance_after"])["overall"] == result["governance_after"]["overall_status"]


def test_explanation_of_mateo_with_xom_is_still_valid_and_does_not_claim_esg_compliance(results):
    from alphaforge.analysis_pipeline import explain
    from alphaforge.bedrock_client import BedrockConfig
    for level in ("novice", "pro"):
        explanation = explain(results[("mateo", "xom_10")], level, mode="offline", config=BedrockConfig())
        assert explanation["validation"]["is_valid"] is True
        assert "toutes les règles" not in explanation["output"]["summary"].lower()


def test_governance_module_stays_free_of_network_and_model_dependencies():
    import re
    from alphaforge import governance
    source = Path(governance.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(boto3|botocore|requests|urllib|anthropic)", source, re.M)
    assert "\u2014" not in source
    assert copy.deepcopy(ESG_RULE_TYPES) == ESG_RULE_TYPES
