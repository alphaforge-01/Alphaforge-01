"""Tests B5 : contrefactuel. `simulate_fn` est une fonction simulée : aucune logique du flux A,
aucun appel AWS. Chiffres inventés."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge import counterfactual  # noqa: E402
from alphaforge.contracts import Counterfactual, RuleCheck, check_keys  # noqa: E402
from alphaforge.counterfactual import (  # noqa: E402
    NO_SOLUTION_FR, compute_counterfactuals, largest_compliant_weight, sweep, weight_grid,
)
from alphaforge.explanation_brief import build_brief  # noqa: E402
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import render_markdown  # noqa: E402
from alphaforge.governance import evaluate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_rule(rule_id, rule_type, direction, warn, limit, params=None):
    return {"rule_id": rule_id, "rule_type": rule_type, "params": params or {}, "direction": direction,
            "warn_threshold": warn, "limit_threshold": limit, "unit": "pct", "label_fr": f"Règle {rule_id}",
            "origin": "checkbox", "is_assumption": True}


def make_idea(weight=0.25):
    return {"ticker": "TSLA", "target_weight": weight, "funding_source": "pro_rata", "funding_ticker": None}


def snapshot_for(weight, **overrides):
    """Instantané inventé : tout est une fonction affine du poids de TSLA."""
    snap = {
        "subject": "portfolio_after", "weights": {"TSLA": weight, "SPY": round(1 - weight, 6)},
        "volatility_ann": 0.10 + 0.5 * weight, "max_drawdown": 0.10 + 0.8 * weight,
        "max_drawdown_start": "2022-01-03", "max_drawdown_end": "2022-06-01", "recovery_days": None,
        "top_asset": "TSLA", "top_asset_weight": weight, "weight_by_sector": {},
        "weight_by_asset_class": {"equity": weight, "etf_equity": round(1 - weight, 6)},
        "currency_exposure": {"USD": 1.0}, "defensive_share": 0.6 - weight,
        "largest_correlated_group_weight": None,
    }
    snap.update(overrides)
    return snap


def tool_result(snapshot):
    return {"tool_name": "simulate_portfolio_change", "call_id": "c", "params": {}, "status": "ok",
            "error_message": None, "data": snapshot, "evidence": []}


class FakeSimulator:
    """Simulateur bouchon : enregistre les idées reçues. `mutate(weight, snapshot)` peut altérer le résultat."""

    def __init__(self, mutate=None, as_tool_result=True):
        self.calls = []
        self.mutate = mutate
        self.as_tool_result = as_tool_result

    def __call__(self, idea):
        self.calls.append(copy.deepcopy(idea))
        weight = idea["target_weight"]
        snapshot = snapshot_for(weight)
        if self.mutate:
            snapshot = self.mutate(weight, snapshot)
        if snapshot is None or isinstance(snapshot, Exception):
            return snapshot
        return tool_result(snapshot) if self.as_tool_result else snapshot


R1 = make_rule("R1", "max_single_asset_weight", "max", 0.20, 0.30)
R2 = make_rule("R2", "max_portfolio_volatility", "max", 0.16, 0.25)    # compliant si poids <= 0.12
R3 = make_rule("R3", "max_portfolio_drawdown", "max", 0.40, 0.60)
R4 = make_rule("R4", "min_defensive_share", "min", 0.40, 0.30)         # compliant si poids <= 0.20
PROFILE = {"profile_id": "test", "rules": [R1, R2, R3, R4]}


# ---------- grille ----------

def test_grid_steps_of_one_point_without_float_drift():
    grid = weight_grid(0.25)
    assert grid[0] == 0.01 and grid[-1] == 0.25 and len(grid) == 25
    assert grid == [round(k / 100, 2) for k in range(1, 26)]
    assert all(b - a == pytest.approx(0.01) for a, b in zip(grid, grid[1:]))


@pytest.mark.parametrize("target,count", [
    (0.01, 1), (0.0099, 0), (0.02, 2), (0.255, 25), (0.29, 29), (0.07, 7), (0.57, 57), (1.0, 100), (3.0, 100),
    (0, 0), (-0.1, 0), (None, 0), ("0.25", 0), (True, 0), (float("nan"), 0), (float("inf"), 0),
])
def test_grid_boundaries(target, count):
    assert len(weight_grid(target)) == count


def test_simulator_called_once_per_weight_with_only_weight_changed():
    sim = FakeSimulator()
    original = make_idea(0.25)
    snapshot = copy.deepcopy(original)
    compute_counterfactuals(PROFILE, original, sim)
    assert [c["target_weight"] for c in sim.calls] == weight_grid(0.25)
    assert all({k: v for k, v in c.items() if k != "target_weight"} ==
               {k: v for k, v in original.items() if k != "target_weight"} for c in sim.calls)
    assert original == snapshot            # l'idée de l'appelant n'est pas modifiée


# ---------- plus grand poids conforme, seuils exacts ----------

def test_largest_compliant_weight_per_rule():
    result = compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator())
    assert result["R1"]["compliant_at_or_below"] == 0.20     # exactement au seuil : conforme
    assert result["R2"]["compliant_at_or_below"] == 0.12     # 0.10 + 0.5 * 0.12 = 0.16, au seuil
    assert result["R3"]["compliant_at_or_below"] == 0.25     # conforme sur toute la grille
    assert result["R4"]["compliant_at_or_below"] == 0.20     # 0.6 - 0.20 = 0.40, au seuil
    assert result["R1"]["display_value"] == "20 %" and result["R2"]["display_value"] == "12 %"


def test_exact_threshold_weight_is_compliant_and_next_point_is_not():
    rule = make_rule("R1", "max_single_asset_weight", "max", 0.07, 0.30)
    profile = {"profile_id": "t", "rules": [rule]}
    assert compute_counterfactuals(profile, make_idea(0.10), FakeSimulator())["R1"]["compliant_at_or_below"] == 0.07


def test_contract_shape():
    cf = compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator())["R1"]
    assert check_keys(cf, Counterfactual) == []
    assert set(cf) == {"parameter", "compliant_at_or_below", "display_value"} and cf["parameter"] == "target_weight"
    assert isinstance(cf["compliant_at_or_below"], float)


def test_accepts_tool_result_or_raw_snapshot():
    a = compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(as_tool_result=True))
    b = compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(as_tool_result=False))
    assert a == b and a["R1"]["compliant_at_or_below"] == 0.20


# ---------- non-monotonie ----------

def test_non_monotone_compliance_returns_the_largest_not_the_first_break():
    def mutate(weight, snap):
        # Volatilité conforme à 0.01 à 0.05, non conforme de 0.06 à 0.22, conforme de nouveau à 0.23 et 0.24.
        snap["volatility_ann"] = 0.10 if (weight <= 0.05 or 0.23 <= weight <= 0.24) else 0.30
        return snap
    result = compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate))
    assert result["R2"]["compliant_at_or_below"] == 0.24


def test_non_monotone_gap_below_the_max():
    def mutate(weight, snap):
        snap["volatility_ann"] = 0.10 if weight in (0.03, 0.08) else 0.30
        return snap
    assert compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate))["R2"][
        "compliant_at_or_below"] == 0.08


# ---------- aucun poids conforme ----------

def test_no_compliant_weight_gives_counterfactual_with_none_bound():
    def mutate(weight, snap):
        snap["volatility_ann"] = 0.90
        return snap
    cf = compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate))["R2"]
    assert cf == {"parameter": "target_weight", "compliant_at_or_below": None, "display_value": NO_SOLUTION_FR}
    assert check_keys(cf, Counterfactual) == []


# ---------- valeurs manquantes et simulation indisponible ----------

def test_missing_info_is_never_compliant_and_blocks_a_claim_above():
    def mutate(weight, snap):
        if weight >= 0.15:
            snap["volatility_ann"] = None      # information manquante pour les gros poids
        return snap
    # Les poids 0.15 à 0.25 sont inconnus : on ne peut pas affirmer que 0.12 est le plus grand conforme.
    assert compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate))["R2"] is None


def test_missing_info_below_the_best_weight_does_not_block():
    def mutate(weight, snap):
        if weight <= 0.03:
            snap["volatility_ann"] = None
        return snap
    assert compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate))["R2"][
        "compliant_at_or_below"] == 0.12


def test_missing_info_everywhere_is_not_reported_as_compliant_nor_as_no_solution():
    def mutate(weight, snap):
        snap["volatility_ann"] = None
        return snap
    result = compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate))
    assert result["R2"] is None
    assert result["R1"]["compliant_at_or_below"] == 0.20     # les autres règles restent calculées


def test_no_compliant_weight_but_some_unknown_is_not_a_claim_of_no_solution():
    def mutate(weight, snap):
        snap["volatility_ann"] = None if weight == 0.02 else 0.90
        return snap
    assert compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate))["R2"] is None


@pytest.mark.parametrize("bad", [
    lambda w, s: None,
    lambda w, s: "texte",
    lambda w, s: {"weights": "pas un dict"},
])
def test_unusable_simulation_gives_none(bad):
    sim = FakeSimulator()
    sim.mutate = None
    simulator = lambda idea: bad(idea["target_weight"], None)  # noqa: E731
    assert set(compute_counterfactuals(PROFILE, make_idea(0.25), simulator).values()) == {None}


def test_failed_tool_status_gives_none():
    failed = {"tool_name": "simulate_portfolio_change", "call_id": "c", "params": {}, "status": "error",
              "error_message": "boom", "data": {}, "evidence": []}
    missing = dict(failed, status="missing_info")
    for result in (failed, missing):
        assert set(compute_counterfactuals(PROFILE, make_idea(0.25), lambda i, r=result: r).values()) == {None}


def test_simulator_exception_gives_none_without_raising():
    def explode(idea):
        raise RuntimeError("données absentes")
    assert set(compute_counterfactuals(PROFILE, make_idea(0.25), explode).values()) == {None}
    points = sweep(PROFILE, make_idea(0.02), explode)
    assert [p[1] for p in points] == [None, None] and "RuntimeError" in points[0][2]


def test_snapshot_not_matching_requested_weight_is_rejected():
    def mutate(weight, snap):
        snap["weights"] = {"TSLA": 0.5, "SPY": 0.5}
        return snap
    assert set(compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate)).values()) == {None}


def test_snapshot_without_subject_is_unavailable():
    def mutate(weight, snap):
        del snap["subject"]
        return snap
    assert set(compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(mutate)).values()) == {None}


def test_no_simulate_fn_or_idea_or_grid_gives_none():
    assert compute_counterfactuals(PROFILE, make_idea(0.25), None) == {r: None for r in ("R1", "R2", "R3", "R4")}
    assert compute_counterfactuals(PROFILE, None, FakeSimulator()) == {r: None for r in ("R1", "R2", "R3", "R4")}
    sim = FakeSimulator()
    assert compute_counterfactuals(PROFILE, make_idea(0.005), sim)["R1"] is None and sim.calls == []
    assert largest_compliant_weight(PROFILE, make_idea(0.25), None) is None


# ---------- règle sans donnée évaluable ----------

def test_rule_that_cannot_be_evaluated_stays_none():
    esg = make_rule("R9", "esg_exclusion", "max", None, 0.0)
    profile = {"profile_id": "t", "rules": [R1, esg]}
    result = compute_counterfactuals(profile, make_idea(0.25), FakeSimulator())
    assert result["R9"] is None and result["R1"]["compliant_at_or_below"] == 0.20


def test_unknown_rule_id_is_none():
    assert compute_counterfactuals(PROFILE, make_idea(0.25), FakeSimulator(), rule_ids=["R99"]) == {"R99": None}


# ---------- poids conforme pour tout le profil ----------

def test_largest_weight_for_whole_profile():
    cf = largest_compliant_weight(PROFILE, make_idea(0.25), FakeSimulator())
    assert cf["compliant_at_or_below"] == 0.12      # la règle la plus stricte (R2) décide
    assert cf["display_value"] == "12 %"


def test_whole_profile_missing_info_blocks_conformity():
    def mutate(weight, snap):
        snap["max_drawdown"] = None
        return snap
    assert largest_compliant_weight(PROFILE, make_idea(0.25), FakeSimulator(mutate)) is None


def test_whole_profile_with_a_known_conflict_is_no_solution_even_if_other_rule_missing():
    def mutate(weight, snap):
        snap["max_drawdown"] = None            # R3 manquante
        snap["top_asset_weight"] = 0.9         # R1 en conflit partout : verdict global connu
        return snap
    cf = largest_compliant_weight(PROFILE, make_idea(0.25), FakeSimulator(mutate))
    assert cf["compliant_at_or_below"] is None and cf["display_value"] == NO_SOLUTION_FR


# ---------- intégration avec evaluate ----------

def test_evaluate_attaches_counterfactuals_to_flagged_checks_only():
    idea = make_idea(0.25)
    sim = FakeSimulator()
    result = evaluate(PROFILE, snapshot_for(0.25), simulate_fn=sim, idea=idea)
    by_rule = {c["rule_id"]: c for c in result["checks"]}
    assert by_rule["R1"]["status"] == "tension" and by_rule["R1"]["counterfactual"]["compliant_at_or_below"] == 0.20
    assert by_rule["R2"]["status"] == "tension" and by_rule["R2"]["counterfactual"]["compliant_at_or_below"] == 0.12
    assert by_rule["R3"]["status"] == "compliant" and by_rule["R3"]["counterfactual"] is None
    assert len(sim.calls) == 25                    # une seule série de simulations pour tous les contrôles
    for check in result["checks"]:
        assert check_keys(check, RuleCheck) == []


def test_evaluate_statuses_and_margins_are_unchanged_by_counterfactual():
    snapshot = snapshot_for(0.25)
    plain = evaluate(PROFILE, snapshot)
    with_cf = evaluate(PROFILE, snapshot, simulate_fn=FakeSimulator(), idea=make_idea(0.25))
    assert plain["overall_status"] == with_cf["overall_status"]
    for a, b in zip(plain["checks"], with_cf["checks"]):
        assert {k: v for k, v in a.items() if k != "counterfactual"} == {k: v for k, v in b.items()
                                                                          if k != "counterfactual"}


def test_evaluate_with_unavailable_simulation_leaves_none():
    result = evaluate(PROFILE, snapshot_for(0.25), simulate_fn=lambda i: None, idea=make_idea(0.25))
    assert all(c["counterfactual"] is None for c in result["checks"])


def test_evaluate_does_not_recurse_into_simulation():
    sim = FakeSimulator()
    evaluate(PROFILE, snapshot_for(0.25), simulate_fn=sim, idea=make_idea(0.25))
    assert len(sim.calls) == 25


def test_robert_fixture_counterfactual_flows_to_brief_and_rendering():
    data = load("analysis_result_robert_tsla.json")
    profile = data["profile"]

    def simulate(idea):
        w = idea["target_weight"]
        snap = copy.deepcopy(data["snapshot_after"])
        snap["weights"]["TSLA"] = w
        snap["top_asset_weight"] = w
        snap["volatility_ann"] = 0.10 + 0.44 * w         # 0.21 à 0.25
        snap["max_drawdown"] = 0.10 + 0.76 * w           # 0.29 à 0.25
        snap["defensive_share"] = 0.4125 + (0.25 - w)    # le poids libéré va au défensif (invention de test)
        return tool_result(snap)

    data["governance_after"] = evaluate(profile, data["snapshot_after"], simulate_fn=simulate,
                                        idea=data["idea"], evidence=data["evidence"])
    g1 = data["governance_after"]["checks"][0]
    assert g1["status"] == "conflict"
    assert g1["counterfactual"] == {"parameter": "target_weight", "compliant_at_or_below": 0.2,
                                    "display_value": "20 %"}
    brief = build_brief(data, "novice")
    assert next(c for c in brief["checks"] if c["check_id"] == "G1")["counterfactual"] == g1["counterfactual"]
    markdown = render_markdown(render_template(brief), brief)
    assert "Concentration par actif : le plus grand poids testé conforme à cette règle est 20 %." in markdown


def test_module_has_no_network_or_model_dependency():
    source = Path(counterfactual.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(boto3|botocore|requests|urllib|anthropic|pandas)", source, re.M)
    assert "\u2014" not in source
    assert "agent_tools" not in source.split('"""')[2]   # aucune logique du flux A importée ici


def test_non_monotone_result_is_worded_as_largest_tested_weight_not_at_or_below():
    data = load("analysis_result_robert_tsla.json")

    def simulate(idea):
        w = idea["target_weight"]
        snap = copy.deepcopy(data["snapshot_after"])
        snap["weights"]["TSLA"] = w
        snap["top_asset_weight"] = 0.15 if (w <= 0.05 or 0.23 <= w <= 0.24) else 0.25   # non monotone
        return tool_result(snap)

    data["governance_after"] = evaluate(data["profile"], data["snapshot_after"], simulate_fn=simulate,
                                        idea=data["idea"], evidence=data["evidence"])
    cf = data["governance_after"]["checks"][0]["counterfactual"]
    assert cf["compliant_at_or_below"] == 0.24 and cf["display_value"] == "24 %"
    for level in ("novice", "pro"):
        brief = build_brief(data, level)
        text = render_markdown(render_template(brief), brief)
        assert "le plus grand poids testé conforme à cette règle est 24 %" in text
        assert "% ou moins" not in text
