"""Tests B2 : gouvernance. Chiffres inventés, aucun appel AWS."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge.contracts import GovernanceResult, RuleCheck, check_keys  # noqa: E402
from alphaforge.governance import STATUS_SEVERITY, evaluate, worst_status  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
STATUSES = {"compliant", "tension", "conflict", "missing_info"}


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_rule(rule_type="max_single_asset_weight", direction="max", warn=0.2, limit=0.3,
              params=None, rule_id="R1", unit="pct"):
    return {
        "rule_id": rule_id, "rule_type": rule_type, "params": params or {}, "direction": direction,
        "warn_threshold": warn, "limit_threshold": limit, "unit": unit,
        "label_fr": "Règle d'essai", "origin": "checkbox", "is_assumption": True,
    }


def make_profile(*rules):
    return {"profile_id": "test", "rules": list(rules)}


def make_snapshot(**overrides):
    snap = {
        "subject": "portfolio_after", "weights": {"A": 1.0}, "volatility_ann": 0.10,
        "max_drawdown": 0.10, "max_drawdown_start": "2022-01-03", "max_drawdown_end": "2022-06-01",
        "recovery_days": None, "top_asset": "A", "top_asset_weight": 0.10,
        "weight_by_sector": {}, "weight_by_asset_class": {"equity": 0.5, "etf_bond": 0.5},
        "currency_exposure": {"CAD": 1.0}, "defensive_share": 0.5,
        "largest_correlated_group_weight": None,
    }
    snap.update(overrides)
    return snap


def single(rule, snapshot):
    return evaluate(make_profile(rule), snapshot)["checks"][0]


# ---------- contrat ----------

def test_result_respects_contract():
    profile = load_personas()["robert"]["profile"]
    result = evaluate(profile, make_snapshot())
    assert check_keys(result, GovernanceResult) == []
    assert result["profile_id"] == "robert" and result["subject"] == "portfolio_after"
    assert [c["check_id"] for c in result["checks"]] == [f"G{i}" for i in range(1, 7)]
    for check, rule in zip(result["checks"], profile["rules"]):
        assert check_keys(check, RuleCheck) == []
        assert check["rule_id"] == rule["rule_id"]
        assert check["rule_type"] == rule["rule_type"]
        assert check["label_fr"] == rule["label_fr"]
        assert check["unit"] == rule["unit"]
        assert check["status"] in STATUSES


def test_evaluate_does_not_mutate_inputs():
    profile = load_personas()["amira"]["profile"]
    snapshot = make_snapshot()
    before = copy.deepcopy((profile, snapshot))
    evaluate(profile, snapshot)
    assert (profile, snapshot) == before


# ---------- seuils exacts : règle "max" ----------

@pytest.mark.parametrize("value,status,margin", [
    (0.10, "compliant", 0.10),
    (0.20, "compliant", 0.0),      # exactement au seuil de tension : pas franchi
    (0.2000000001, "compliant", 0.0),  # bruit flottant toléré
    (0.21, "tension", 0.09),
    (0.30, "tension", 0.0),        # exactement à la limite : pas franchie
    (0.31, "conflict", -0.01),
    (0.50, "conflict", -0.20),
])
def test_max_rule_thresholds(value, status, margin):
    check = single(make_rule(), make_snapshot(top_asset_weight=value))
    assert check["status"] == status
    assert check["margin"] == pytest.approx(margin, abs=1e-6)
    assert check["value"] == pytest.approx(value)


# ---------- seuils exacts : règle "min" ----------

@pytest.mark.parametrize("value,status,margin", [
    (0.60, "compliant", 0.20),
    (0.40, "compliant", 0.0),
    (0.39, "tension", 0.09),
    (0.30, "tension", 0.0),
    (0.29, "conflict", -0.01),
    (0.0, "conflict", -0.30),
])
def test_min_rule_thresholds(value, status, margin):
    rule = make_rule("min_defensive_share", "min", warn=0.4, limit=0.3)
    check = single(rule, make_snapshot(defensive_share=value))
    assert check["status"] == status
    assert check["margin"] == pytest.approx(margin, abs=1e-6)


def test_min_rule_with_limit_zero_is_never_conflict():
    rule = make_rule("min_defensive_share", "min", warn=0.05, limit=0.0)  # profil d'Amira
    assert single(rule, make_snapshot(defensive_share=0.0))["status"] == "tension"
    assert single(rule, make_snapshot(defensive_share=0.05))["status"] == "compliant"


def test_all_four_statuses_are_produced():
    rule = make_rule()
    found = {
        single(rule, make_snapshot(top_asset_weight=0.1))["status"],
        single(rule, make_snapshot(top_asset_weight=0.25))["status"],
        single(rule, make_snapshot(top_asset_weight=0.4))["status"],
        single(rule, make_snapshot(top_asset_weight=None))["status"],
    }
    assert found == STATUSES


# ---------- seuils partiels : exclusion ----------

def test_excluded_asset_class_rule():
    rule = make_rule("excluded_asset_class", "max", warn=None, limit=0.0,
                     params={"asset_class": "crypto"}, unit="bool")
    ok = single(rule, make_snapshot(weight_by_asset_class={"equity": 1.0}))
    assert (ok["status"], ok["value"], ok["margin"]) == ("compliant", 0.0, 0.0)
    held = single(rule, make_snapshot(weight_by_asset_class={"equity": 0.9, "crypto": 0.1}))
    assert held["status"] == "conflict"
    assert held["margin"] == pytest.approx(-0.1)
    assert held["warn_threshold"] is None


def test_max_rule_without_limit_has_no_conflict_and_no_margin_in_tension():
    rule = make_rule(warn=0.2, limit=None)
    check = single(rule, make_snapshot(top_asset_weight=0.9))
    assert (check["status"], check["margin"]) == ("tension", None)


def test_max_rule_without_warn_goes_straight_to_conflict():
    rule = make_rule(warn=None, limit=0.3)
    assert single(rule, make_snapshot(top_asset_weight=0.3))["status"] == "compliant"
    assert single(rule, make_snapshot(top_asset_weight=0.31))["status"] == "conflict"


# ---------- classes d'actifs ----------

def test_asset_class_weight_rule_and_absent_class_counts_as_zero():
    rule = make_rule("max_asset_class_weight", warn=0.2, limit=0.35, params={"asset_class": "crypto"})
    assert single(rule, make_snapshot(weight_by_asset_class={"crypto": 0.4}))["status"] == "conflict"
    assert single(rule, make_snapshot(weight_by_asset_class={"crypto": 0.35}))["status"] == "tension"
    absent = single(rule, make_snapshot(weight_by_asset_class={"equity": 1.0}))
    assert (absent["status"], absent["value"]) == ("compliant", 0.0)


# ---------- valeurs manquantes ----------

@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "0.3", True])
def test_missing_or_invalid_value_gives_missing_info(bad):
    check = single(make_rule(), make_snapshot(top_asset_weight=bad))
    assert check["status"] == "missing_info"
    assert check["value"] is None and check["margin"] is None
    assert check["missing_reason"]
    assert check["counterfactual"] is None


def test_absent_snapshot_key_gives_missing_info_without_default():
    snapshot = make_snapshot()
    del snapshot["volatility_ann"]
    check = single(make_rule("max_portfolio_volatility"), snapshot)
    assert check["status"] == "missing_info" and check["value"] is None


def test_missing_asset_class_breakdown_gives_missing_info():
    rule = make_rule("max_asset_class_weight", params={"asset_class": "equity"})
    snapshot = make_snapshot(weight_by_asset_class=None)
    assert single(rule, snapshot)["status"] == "missing_info"
    assert single(make_rule("max_asset_class_weight"), make_snapshot())["status"] == "missing_info"


def test_p2_rules_without_data_are_missing_info():
    corr = single(make_rule("max_correlated_group_weight"), make_snapshot())
    assert corr["status"] == "missing_info"
    esg = single(make_rule("esg_exclusion", "max", None, 0.0, unit="bool"), make_snapshot())
    assert esg["status"] == "missing_info" and "ESG" in esg["missing_reason"]
    ok = single(make_rule("max_correlated_group_weight"), make_snapshot(largest_correlated_group_weight=0.1))
    assert ok["status"] == "compliant"


def test_unknown_rule_type_is_missing_info():
    assert single(make_rule("unknown_type"), make_snapshot())["status"] == "missing_info"


def test_present_values_are_kept_when_other_value_is_missing():
    profile = make_profile(make_rule(rule_id="R1"),
                           make_rule("max_portfolio_volatility", rule_id="R2", warn=0.1, limit=0.2))
    result = evaluate(profile, make_snapshot(volatility_ann=None, top_asset_weight=0.25))
    assert [c["status"] for c in result["checks"]] == ["tension", "missing_info"]


# ---------- seuils incohérents (contradictions) ----------

def test_inconsistent_thresholds_give_missing_info():
    inverted_max = single(make_rule(warn=0.4, limit=0.2), make_snapshot())
    inverted_min = single(make_rule("min_defensive_share", "min", warn=0.2, limit=0.4), make_snapshot())
    for check in (inverted_max, inverted_min):
        assert check["status"] == "missing_info"
        assert "incohérents" in check["missing_reason"]


def test_rule_without_threshold_or_with_bad_threshold_is_missing_info():
    assert single(make_rule(warn=None, limit=None), make_snapshot())["status"] == "missing_info"
    assert single(make_rule(warn="x", limit=0.3), make_snapshot())["status"] == "missing_info"
    assert single(make_rule(direction="sideways"), make_snapshot())["status"] == "missing_info"


# ---------- pire statut global ----------

def test_severity_order():
    assert (STATUS_SEVERITY["compliant"] < STATUS_SEVERITY["missing_info"]
            < STATUS_SEVERITY["tension"] < STATUS_SEVERITY["conflict"])


@pytest.mark.parametrize("statuses,expected", [
    (["compliant", "compliant"], "compliant"),
    (["compliant", "missing_info"], "missing_info"),
    (["missing_info", "tension"], "tension"),
    (["tension", "conflict", "compliant"], "conflict"),
    (["missing_info", "conflict"], "conflict"),
    ([], "missing_info"),
])
def test_worst_status(statuses, expected):
    assert worst_status(statuses) == expected


def test_overall_status_never_compliant_when_a_value_is_missing():
    profile = make_profile(make_rule(rule_id="R1"),
                           make_rule("max_portfolio_volatility", rule_id="R2", warn=0.3, limit=0.4))
    result = evaluate(profile, make_snapshot(volatility_ann=None))
    assert result["overall_status"] == "missing_info"


def test_profile_without_rules_is_missing_info_not_compliant():
    result = evaluate({"profile_id": "x", "rules": []}, make_snapshot())
    assert result["overall_status"] == "missing_info" and result["checks"] == []


# ---------- preuves ----------

def test_evidence_ids_are_linked_by_metric_and_subject():
    evidence = fixture("analysis_result_robert_tsla.json")["evidence"]
    profile = load_personas()["robert"]["profile"]
    after = evaluate(profile, make_snapshot(subject="portfolio_after"), evidence=evidence)
    ids = {c["rule_id"]: c["evidence_ids"] for c in after["checks"]}
    assert ids["R1"] == ["E1"] and ids["R2"] == ["E2"] and ids["R3"] == ["E3"] and ids["R4"] == ["E4"]
    assert ids["R5"] == [] and ids["R6"] == []   # aucune preuve : rien n'est inventé
    before = evaluate(profile, make_snapshot(subject="portfolio_before"), evidence=list(evidence.values()))
    assert {c["rule_id"]: c["evidence_ids"] for c in before["checks"]}["R1"] == ["E5"]
    assert all(c["evidence_ids"] == [] for c in before["checks"] if c["rule_id"] != "R1")


def test_no_evidence_gives_empty_ids():
    result = evaluate(load_personas()["robert"]["profile"], make_snapshot())
    assert all(c["evidence_ids"] == [] for c in result["checks"])


def class_entry(evidence_id, asset_class, subject="portfolio_after"):
    return {"evidence_id": evidence_id, "metric": f"weight_by_asset_class.{asset_class}", "subject": subject}


def test_asset_class_rules_link_to_their_own_class_evidence():
    crypto = make_rule("max_asset_class_weight", params={"asset_class": "crypto"}, rule_id="R5")
    equity = make_rule("max_asset_class_weight", params={"asset_class": "equity"}, rule_id="R6")
    entries = [class_entry("E7", "crypto"), class_entry("E8", "equity"), class_entry("E9", "etf_bond")]
    result = evaluate(make_profile(crypto, equity), make_snapshot(), evidence=entries)
    assert [c["evidence_ids"] for c in result["checks"]] == [["E7"], ["E8"]]


def test_excluded_asset_class_rule_links_to_class_evidence():
    rule = make_rule("excluded_asset_class", "max", warn=None, limit=0.0,
                     params={"asset_class": "crypto"}, unit="bool")
    snapshot = make_snapshot(weight_by_asset_class={"equity": 0.9, "crypto": 0.1})
    result = evaluate(make_profile(rule), snapshot, evidence=[class_entry("E3", "crypto")])
    assert result["checks"][0]["status"] == "conflict" and result["checks"][0]["evidence_ids"] == ["E3"]


def test_asset_class_evidence_requires_matching_subject():
    rule = make_rule("max_asset_class_weight", params={"asset_class": "crypto"})
    entries = [class_entry("E1", "crypto", subject="portfolio_before"), class_entry("E2", "crypto", "variant:V1")]
    assert evaluate(make_profile(rule), make_snapshot(subject="portfolio_after"),
                    evidence=entries)["checks"][0]["evidence_ids"] == []
    assert evaluate(make_profile(rule), make_snapshot(subject="variant:V1"),
                    evidence=entries)["checks"][0]["evidence_ids"] == ["E2"]


def test_asset_class_without_evidence_stays_empty_and_value_is_zero():
    """Classe absente du portefeuille : le flux A ne produit aucune preuve, rien n'est inventé."""
    rule = make_rule("max_asset_class_weight", params={"asset_class": "crypto"})
    result = evaluate(make_profile(rule), make_snapshot(), evidence=[class_entry("E8", "equity")])
    assert result["checks"][0]["evidence_ids"] == [] and result["checks"][0]["value"] == 0.0


def test_old_family_metric_without_class_suffix_is_not_a_match():
    rule = make_rule("max_asset_class_weight", params={"asset_class": "crypto"})
    entries = [{"evidence_id": "E9", "metric": "weight_by_asset_class", "subject": "portfolio_after"}]
    assert evaluate(make_profile(rule), make_snapshot(), evidence=entries)["checks"][0]["evidence_ids"] == []


def test_rule_metric_helper():
    from alphaforge.governance import asset_class_metric, rule_metric
    assert asset_class_metric("crypto") == "weight_by_asset_class.crypto"
    assert rule_metric("max_asset_class_weight", {"asset_class": "equity"}) == "weight_by_asset_class.equity"
    assert rule_metric("excluded_asset_class", {"asset_class": "crypto"}) == "weight_by_asset_class.crypto"
    assert rule_metric("max_asset_class_weight") is None and rule_metric("max_asset_class_weight", {}) is None
    assert rule_metric("max_portfolio_volatility", {"asset_class": "crypto"}) == "volatility_ann"
    assert rule_metric("esg_exclusion") is None


def test_rule_metrics_are_portfolio_snapshot_fields():
    from alphaforge.contracts import PortfolioSnapshot
    from alphaforge.governance import _SNAPSHOT_FIELD
    assert set(_SNAPSHOT_FIELD.values()) <= set(PortfolioSnapshot.__annotations__)


# ---------- fixtures B0 et personas ----------

def test_robert_tsla_after_matches_fixture_verdicts():
    data = fixture("analysis_result_robert_tsla.json")
    result = evaluate(data["profile"], data["snapshot_after"], evidence=data["evidence"])
    expected = data["governance_after"]
    assert result["overall_status"] == expected["overall_status"] == "conflict"
    for got, want in zip(result["checks"], expected["checks"]):
        assert got["status"] == want["status"], want["rule_id"]
        assert got["value"] == pytest.approx(want["value"])
        assert got["margin"] == pytest.approx(want["margin"], abs=1e-6)
        assert got["evidence_ids"] == want["evidence_ids"]


def test_robert_tsla_before_is_compliant_at_exact_threshold():
    data = fixture("analysis_result_robert_tsla.json")
    check = evaluate(data["profile"], data["snapshot_before"], evidence=data["evidence"])["checks"][0]
    assert check["status"] == "compliant" and check["value"] == pytest.approx(0.2)
    assert check["evidence_ids"] == ["E5"]


def test_fixture_margins_match_contract_definition():
    """Non-régression : marge = distance au prochain seuil (0 au seuil de tension)."""
    data = fixture("analysis_result_robert_tsla.json")
    for key, snapshot in (("governance_before", "snapshot_before"), ("governance_after", "snapshot_after")):
        computed = {c["rule_id"]: c for c in evaluate(data["profile"], data[snapshot])["checks"]}
        for stored in data[key]["checks"]:
            got = computed[stored["rule_id"]]
            assert stored["status"] == got["status"], (key, stored["rule_id"])
            assert stored["margin"] == pytest.approx(got["margin"], abs=1e-6), (key, stored["rule_id"])
    brief = fixture("explanation_brief_robert_novice.json")
    computed = {c["rule_id"]: c for c in evaluate(data["profile"], data["snapshot_after"])["checks"]}
    for stored in brief["checks"]:
        assert stored["margin"] == pytest.approx(computed[stored["rule_id"]]["margin"], abs=1e-6)


def test_same_idea_gives_different_verdicts_per_profile():
    """Scène 2 : mêmes chiffres, profils différents, verdicts différents."""
    snapshot = fixture("analysis_result_robert_tsla.json")["snapshot_after"]
    personas = load_personas()
    robert = evaluate(personas["robert"]["profile"], snapshot)
    amira = evaluate(personas["amira"]["profile"], snapshot)
    assert robert["overall_status"] == "conflict"
    assert robert["checks"][0]["status"] == "conflict"   # 25 % au-delà de 22 %
    assert amira["checks"][0]["status"] == "compliant"   # 25 % sous 35 %
    assert amira["overall_status"] != robert["overall_status"]


def test_personas_starting_portfolios_have_no_conflict_on_concentration():
    """Les 3 personas : un instantané sain est conforme sur toutes les règles."""
    for entry in load_personas().values():
        result = evaluate(entry["profile"], make_snapshot(
            top_asset_weight=0.10, volatility_ann=0.10, max_drawdown=0.10,
            defensive_share=0.7, weight_by_asset_class={"equity": 0.3, "etf_bond": 0.7}))
        # Mateo a une règle ESG sans preuve possible : au mieux `missing_info`, jamais `compliant`.
        has_esg = any(r["rule_type"] == "esg_exclusion" for r in entry["profile"]["rules"])
        assert result["overall_status"] == ("missing_info" if has_esg else "compliant"), entry["profile"]["profile_id"]
        financial = [c for c in result["checks"] if c["rule_type"] != "esg_exclusion"]
        assert all(c["status"] == "compliant" for c in financial)


def test_esg_rule_is_missing_info_even_when_everything_else_is_compliant():
    mateo = load_personas()["mateo"]["profile"]
    result = evaluate(mateo, make_snapshot(top_asset_weight=0.10, volatility_ann=0.10, max_drawdown=0.10,
                                           defensive_share=0.7, weight_by_asset_class={"equity": 0.3, "etf_bond": 0.7}))
    esg = next(c for c in result["checks"] if c["rule_type"] == "esg_exclusion")
    assert esg["status"] == "missing_info" and esg["value"] is None and esg["margin"] is None
    assert "ESG" in esg["missing_reason"] and "impossible" in esg["missing_reason"]
    assert esg["evidence_ids"] == [] and esg["counterfactual"] is None
    assert result["overall_status"] == "missing_info"


def test_esg_missing_info_does_not_hide_a_financial_conflict():
    mateo = load_personas()["mateo"]["profile"]
    result = evaluate(mateo, make_snapshot(top_asset_weight=0.9))
    assert result["overall_status"] == "conflict"
    assert next(c for c in result["checks"] if c["rule_type"] == "esg_exclusion")["status"] == "missing_info"


def test_counterfactual_stays_none_without_simulation():
    """Sans simulate_fn ou sans idée, aucun contrefactuel n'est inventé (le calcul est testé dans test_counterfactual.py)."""
    idea = {"ticker": "TSLA", "target_weight": 0.5, "funding_source": "pro_rata", "funding_ticker": None}
    snapshot = make_snapshot(top_asset_weight=0.5)
    for kwargs in ({}, {"idea": idea}, {"simulate_fn": lambda i: None}):
        result = evaluate(make_profile(make_rule()), snapshot, **kwargs)
        assert result["checks"][0]["status"] == "conflict"
        assert result["checks"][0]["counterfactual"] is None


def test_counterfactual_is_only_attempted_for_tension_and_conflict():
    calls = []
    idea = {"ticker": "TSLA", "target_weight": 0.1, "funding_source": "pro_rata", "funding_ticker": None}
    evaluate(make_profile(make_rule()), make_snapshot(top_asset_weight=0.1),
             simulate_fn=lambda i: calls.append(i), idea=idea)
    assert calls == []


# ---------- entrées invalides ----------

@pytest.mark.parametrize("snapshot", [None, [], {}, {"subject": 3}])
def test_invalid_snapshot_raises(snapshot):
    with pytest.raises(ValueError):
        evaluate(make_profile(make_rule()), snapshot)


def test_profile_without_id_raises():
    with pytest.raises(ValueError):
        evaluate({"rules": []}, make_snapshot())
