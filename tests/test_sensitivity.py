"""Tests de la mise à l'épreuve des hypothèses (sensitivity.py et scripts/run_sensitivity.py).

Données de prix réelles du jeu de départ, profils et portefeuilles fictifs, aucun appel AWS.
"""

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

from alphaforge import sensitivity as sens
from alphaforge.portfolio import apply_idea, build_snapshot_with_metrics
from alphaforge.profiles import load_personas

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_sensitivity", PROJECT_ROOT / "scripts" / "run_sensitivity.py")
rsens = importlib.util.module_from_spec(_spec)
sys.modules["run_sensitivity"] = rsens
_spec.loader.exec_module(rsens)

EM_DASH = chr(0x2014)
TOL = 1e-12
TSLA_25 = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
NVDA_15 = {"ticker": "NVDA", "target_weight": 0.15, "funding_source": "pro_rata", "funding_ticker": None}
BTC_10 = {"ticker": "BTC-USD", "target_weight": 0.10, "funding_source": "pro_rata", "funding_ticker": None}


def _by_pairs(pairs):
    """Portefeuille fictif inventé à partir de (ticker, poids)."""
    return {"portfolio_id": "test", "label_fr": "Essai", "is_fictional": True, "base_currency": "CAD",
            "positions": [{"ticker": t, "weight": w} for t, w in pairs]}


@pytest.fixture(scope="module")
def personas():
    return load_personas()


@pytest.fixture(scope="module")
def robert_after(personas):
    return apply_idea(personas["robert"]["portfolio"], TSLA_25, "sensitivity")


@pytest.fixture(scope="module")
def grid(personas):
    return sens.run_grid(personas)


# 1. Cas de base ---------------------------------------------------------------------------


@pytest.mark.parametrize("name, idea", [("robert", TSLA_25), ("amira", NVDA_15), ("mateo", TSLA_25)])
def test_base_variant_equals_portfolio_snapshot(personas, name, idea):
    after = apply_idea(personas[name]["portfolio"], idea, "sensitivity")
    snapshot, period = sens.variant_snapshot(after, "portfolio_after", sens.BASE)
    expected, metrics = build_snapshot_with_metrics(after, "portfolio_after")
    for key in ("volatility_ann", "max_drawdown", "largest_correlated_group_weight"):
        assert snapshot[key] == pytest.approx(expected[key], abs=TOL, rel=0)
    assert snapshot["max_drawdown_start"] == expected["max_drawdown_start"]
    assert snapshot["max_drawdown_end"] == expected["max_drawdown_end"]
    assert snapshot["recovery_days"] == expected["recovery_days"]
    assert period["period_start"] == metrics.period_start
    assert period["period_end"] == metrics.period_end
    assert period["n_observations"] == metrics.n_observations


# 2. Date de base des fenêtres ------------------------------------------------------------


def test_window_base_date_is_calendar_date_not_after_target(robert_after):
    tickers = ["SPY", "XIU.TO", "BTC-USD"]
    full = sens.variant_prices(tickers, sens.BASE)
    window = sens.GRID_VARIANTS[1]
    assert window.variant_id == "window_3y"
    prices = sens.variant_prices(tickers, window)
    assert prices.index[0] <= prices.index[-1] - pd.DateOffset(years=3)
    assert prices.index[0] in full.index
    assert prices.index[-1] == full.index[-1]


# 3. Perte maximale des sous-fenêtres -----------------------------------------------------


@pytest.mark.parametrize("variant_id", ["window_3y", "window_1y"])
def test_subwindow_drawdown_not_above_base(robert_after, variant_id):
    variant = next(v for v in sens.GRID_VARIANTS if v.variant_id == variant_id)
    base, _ = sens.variant_snapshot(robert_after, "portfolio_after", sens.BASE)
    sub, _ = sens.variant_snapshot(robert_after, "portfolio_after", variant)
    assert sub["max_drawdown"] <= base["max_drawdown"] + TOL


# 4. scale_thresholds ---------------------------------------------------------------------


def _profile():
    return {"profile_id": "x", "rules": [
        {"rule_id": "A", "rule_type": "max_single_asset_weight", "direction": "max", "unit": "pct",
         "warn_threshold": 0.2, "limit_threshold": 0.4},
        {"rule_id": "B", "rule_type": "min_defensive_share", "direction": "min", "unit": "pct",
         "warn_threshold": 0.4, "limit_threshold": 0.3},
        {"rule_id": "C", "rule_type": "excluded_asset_class", "direction": "max", "unit": "bool",
         "warn_threshold": None, "limit_threshold": 0.0},
        {"rule_id": "D", "rule_type": "esg_exclusion", "direction": "max", "unit": "bool",
         "warn_threshold": None, "limit_threshold": 0.0},
        {"rule_id": "E", "rule_type": "max_portfolio_volatility", "direction": "max", "unit": "pct",
         "warn_threshold": 0.8, "limit_threshold": 0.9},
        {"rule_id": "F", "rule_type": "min_defensive_share", "direction": "min", "unit": "pct",
         "warn_threshold": 0.8, "limit_threshold": 0.6},
    ]}


def _rule(profile, rule_id):
    return next(r for r in profile["rules"] if r["rule_id"] == rule_id)


def test_scale_thresholds_directions_and_bounds():
    scaled = sens.scale_thresholds(_profile(), 0.5)
    assert _rule(scaled, "A")["warn_threshold"] == pytest.approx(0.1)
    assert _rule(scaled, "A")["limit_threshold"] == pytest.approx(0.2)
    # Plancher : divisé par 0,5, donc plus haut (plus strict) ; borné à 1
    assert _rule(scaled, "B")["warn_threshold"] == pytest.approx(0.8)
    assert _rule(scaled, "B")["limit_threshold"] == pytest.approx(0.6)
    assert _rule(scaled, "F")["warn_threshold"] == 1.0
    assert _rule(scaled, "F")["limit_threshold"] == 1.0
    loose = sens.scale_thresholds(_profile(), 2.0)
    assert _rule(loose, "E")["warn_threshold"] == 1.0
    assert _rule(loose, "E")["limit_threshold"] == 1.0
    assert _rule(loose, "B")["warn_threshold"] == pytest.approx(0.2)


def test_scale_thresholds_keeps_exclusions_and_original():
    original = _profile()
    snapshot = copy.deepcopy(original)
    scaled = sens.scale_thresholds(original, 0.8)
    assert original == snapshot
    for rule_id in ("C", "D"):
        assert _rule(scaled, rule_id) == _rule(original, rule_id)


@pytest.mark.parametrize("factor", [0, -1, -0.5])
def test_scale_thresholds_rejects_non_positive(factor):
    with pytest.raises(ValueError):
        sens.scale_thresholds(_profile(), factor)


# 5. flip_factor --------------------------------------------------------------------------


def test_flip_factor_known_values():
    rule = {"rule_type": "max_single_asset_weight", "warn_threshold": 0.2, "limit_threshold": 0.22}
    assert sens.flip_factor(rule, 0.25) == {"warn": 1.25, "limit": 1.1364}


def test_flip_factor_none_cases():
    zero = {"rule_type": "max_single_asset_weight", "warn_threshold": 0, "limit_threshold": 0.0}
    assert sens.flip_factor(zero, 0.25) == {"warn": None, "limit": None}
    missing = {"rule_type": "max_single_asset_weight", "limit_threshold": 0.3}
    assert sens.flip_factor(missing, 0.25) == {"warn": None, "limit": 0.8333}
    assert sens.flip_factor({"rule_type": "max_single_asset_weight", "warn_threshold": 0.2}, None) == \
        {"warn": None, "limit": None}
    for rule_type in sens.NON_SCALABLE_RULE_TYPES:
        rule = {"rule_type": rule_type, "warn_threshold": 0.1, "limit_threshold": 0.2}
        assert sens.flip_factor(rule, 0.5) == {"warn": None, "limit": None}


def test_flip_factor_consistent_with_scale_thresholds_for_max_rules(personas, robert_after):
    """Pour une règle plafond en tension, un facteur un peu au-dessus la rend conforme."""
    from alphaforge.governance import evaluate
    profile = personas["robert"]["profile"]
    snapshot, _ = sens.variant_snapshot(robert_after, "portfolio_after", sens.BASE)
    base = {c["rule_id"]: c for c in evaluate(profile, snapshot)["checks"]}
    checked = 0
    for rule in profile["rules"]:
        if rule["direction"] != "max" or rule["rule_type"] in sens.NON_SCALABLE_RULE_TYPES:
            continue
        if base[rule["rule_id"]]["status"] not in ("tension", "conflict"):
            continue
        factors = sens.flip_factor(rule, base[rule["rule_id"]]["value"])
        # Attention ET limite franchies : prendre le plus grand des deux facteurs
        needed = max(f for f in factors.values() if f is not None) + 0.01
        scaled = sens.scale_thresholds(profile, needed)
        after = {c["rule_id"]: c for c in evaluate(scaled, snapshot)["checks"]}
        assert after[rule["rule_id"]]["status"] == "compliant", rule["rule_id"]
        checked += 1
    assert checked >= 2  # R1, R2, R3 de Robert en tension ou conflit


def test_flip_factor_consistent_with_scale_thresholds_for_min_rules():
    from alphaforge.governance import evaluate
    rule = {"rule_id": "R4", "rule_type": "min_defensive_share", "direction": "max", "unit": "pct",
            "warn_threshold": 0.4, "limit_threshold": 0.3, "label_fr": "Part défensive", "params": {}}
    rule["direction"] = "min"
    profile = {"profile_id": "x", "rules": [rule]}
    value = 0.35  # sous le seuil d'attention : tension
    snapshot = {"defensive_share": value, "subject": "portfolio_after"}
    factor = sens.flip_factor(rule, value)["warn"]  # 0,4 / 0,35
    scaled = sens.scale_thresholds(profile, factor + 0.01)
    status = evaluate(scaled, snapshot)["checks"][0]["status"]
    assert status == "compliant"


# 6. Devise locale ------------------------------------------------------------------------

LOCAL = next(v for v in sens.GRID_VARIANTS if v.variant_id == "currency_local")


def test_local_currency_same_calendar_different_values_for_usd_assets():
    tickers = ["SPY", "XIU.TO", "NVDA"]
    cad = sens.variant_prices(tickers, sens.BASE)
    local = sens.variant_prices(tickers, LOCAL)
    assert list(cad.index) == list(local.index)
    assert not cad["SPY"].equals(local["SPY"])
    pd.testing.assert_series_equal(cad["XIU.TO"], local["XIU.TO"])


def test_all_cad_portfolio_same_returns_in_both_currencies():
    tickers = ["XIU.TO", "RY.TO", "XBB.TO"]
    cad = sens.variant_prices(tickers, sens.BASE).pct_change().iloc[1:]
    local = sens.variant_prices(tickers, LOCAL).pct_change().iloc[1:]
    pd.testing.assert_frame_equal(cad, local, check_exact=True)
    portfolio = _by_pairs([("XIU.TO", 0.5), ("RY.TO", 0.3), ("XBB.TO", 0.2)])
    snap_cad, _ = sens.variant_snapshot(portfolio, "p", sens.BASE)
    snap_local, _ = sens.variant_snapshot(portfolio, "p", LOCAL)
    assert snap_cad["volatility_ann"] == snap_local["volatility_ann"]
    assert snap_cad["max_drawdown"] == snap_local["max_drawdown"]


# 7. as_of --------------------------------------------------------------------------------


def test_as_of_2024_uses_no_later_date(robert_after):
    variant = next(v for v in sens.GRID_VARIANTS if v.variant_id == "as_of_2024")
    prices = sens.variant_prices(["SPY", "XIU.TO", "BTC-USD"], variant)
    assert prices.index[-1] <= pd.Timestamp("2024-11-12")
    _, period = sens.variant_snapshot(robert_after, "portfolio_after", variant)
    assert period["period_end"] <= "2024-11-12"
    assert period["period_start"] < period["period_end"]


# 8. Hebdomadaire -------------------------------------------------------------------------


def test_weekly_one_point_per_week_and_base_date():
    weekly = next(v for v in sens.GRID_VARIANTS if v.variant_id == "weekly")
    tickers = ["SPY", "XIU.TO"]
    daily = sens.variant_prices(tickers, sens.BASE)
    prices = sens.variant_prices(tickers, weekly)
    assert prices.index[0] == daily.index[0]
    weeks = prices.index[1:].to_period("W-FRI")
    assert weeks.is_unique
    assert len(prices) < len(daily) / 3
    assert sens.periods_per_year(weekly) == 52
    assert sens.periods_per_year(sens.BASE) == sens.TRADING_DAYS_PER_YEAR


# 9. Statut R3 non comparable -------------------------------------------------------------


def _drawdown_rule_ids(outcome):
    return [k for k, v in outcome.rules.items() if v["rule_type"] in sens.DRAWDOWN_RULE_TYPES]


@pytest.mark.parametrize("variant_id", ["window_3y", "window_1y", "weekly", "as_of_2024", "as_of_2025"])
def test_drawdown_rule_not_comparable(personas, robert_after, variant_id):
    variant = next(v for v in sens.GRID_VARIANTS if v.variant_id == variant_id)
    assert not variant.drawdown_comparable
    outcome = sens.evaluate_variant(personas["robert"]["profile"], robert_after, "portfolio_after", variant)
    ids = _drawdown_rule_ids(outcome)
    assert ids
    assert all(not outcome.rules[i]["comparable"] for i in ids)
    others = [i for i in outcome.rules if i not in ids]
    assert all(outcome.rules[i]["comparable"] for i in others)


def test_blocks_not_comparable_and_others_comparable(personas, robert_after):
    for block in sens.annual_blocks():
        assert not block.drawdown_comparable
    outcome = sens.evaluate_variant(personas["robert"]["profile"], robert_after, "portfolio_after",
                                    sens.annual_blocks()[0])
    assert all(not outcome.rules[i]["comparable"] for i in _drawdown_rule_ids(outcome))


@pytest.mark.parametrize("variant_id", ["base", "currency_local", "thresholds_strict", "thresholds_loose"])
def test_drawdown_rule_comparable_otherwise(personas, robert_after, variant_id):
    variant = next(v for v in sens.GRID_VARIANTS if v.variant_id == variant_id)
    assert variant.drawdown_comparable
    outcome = sens.evaluate_variant(personas["robert"]["profile"], robert_after, "portfolio_after", variant)
    assert all(info["comparable"] for info in outcome.rules.values())


def test_changed_rules_ignores_non_comparable():
    def outcome(statuses):
        rules = {k: {"status": s, "value": 0.0, "rule_type": "x", "comparable": c}
                 for k, (s, c) in statuses.items()}
        return sens.VariantOutcome("v", "a", "b", 1, 0.0, 0.0, None, "compliant", "compliant", None, rules)

    base = outcome({"R1": ("compliant", True), "R2": ("tension", True), "R3": ("conflict", True)})
    other = outcome({"R1": ("tension", True), "R2": ("tension", True), "R3": ("compliant", False),
                     "R9": ("conflict", True)})
    assert sens.changed_rules(base, other) == ["R1"]


# 10. idea_has_no_effect ------------------------------------------------------------------


def test_idea_has_no_effect(personas):
    amira = personas["amira"]["portfolio"]
    assert sens.idea_has_no_effect(amira, NVDA_15) is True
    assert sens.idea_has_no_effect(amira, BTC_10) is True
    assert sens.idea_has_no_effect(amira, TSLA_25) is False


# 11. Blocs annuels -----------------------------------------------------------------------


def test_annual_blocks_disjoint_and_about_one_year():
    blocks = sens.annual_blocks()
    assert len(blocks) == 5
    tickers = ["SPY", "XIU.TO"]
    frames = [sens.variant_prices(tickers, b) for b in blocks]
    for frame in frames:
        span = (frame.index[-1] - frame.index[0]).days
        assert 340 <= span <= 380
    for prev, nxt in zip(frames, frames[1:]):
        returns_prev, returns_next = prev.index[1:], nxt.index[1:]
        assert returns_prev.max() <= nxt.index[0] < returns_next.min()
        assert set(returns_prev).isdisjoint(returns_next)


# 12. Grille ------------------------------------------------------------------------------


def test_run_grid_shape_and_content(grid):
    assert len(grid) == 15
    ids = {v.variant_id for v in sens.GRID_VARIANTS}
    for row in grid:
        assert set(row["outcomes"]) == ids
        assert set(row["changes"]) == ids - {"base"}
    assert {(r["persona"], r["idea"]) for r in grid} >= {("robert", "TSLA_25"), ("amira", "NVDA_15")}
    summary = sens.axis_summary(grid)
    assert [s["variant_id"] for s in summary] == [v.variant_id for v in sens.GRID_VARIANTS[1:]]
    assert all(s["n_cases"] == 15 for s in summary)


def test_run_grid_deterministic(personas, grid):
    again = sens.run_grid(personas)
    assert again == grid
    assert sens.axis_summary(again) == sens.axis_summary(grid)


# 13. Script ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def script_outputs(tmp_path_factory):
    first, second = tmp_path_factory.mktemp("run1"), tmp_path_factory.mktemp("run2")
    codes = (rsens.main(["--out-dir", str(first)]), rsens.main(["--out-dir", str(second)]))
    return first, second, codes


def test_script_writes_files_and_returns_zero(script_outputs):
    first, _, codes = script_outputs
    assert codes == (0, 0)
    assert (first / "sensitivity.md").is_file()
    payload = json.loads((first / "sensitivity.json").read_text(encoding="utf-8"))
    assert len(payload["grid"]) == 15


def test_script_outputs_identical_bytes(script_outputs):
    first, second, _ = script_outputs
    for name in ("sensitivity.md", "sensitivity.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_markdown_disclaimer_no_em_dash_no_english_codes(script_outputs):
    text = (script_outputs[0] / "sensitivity.md").read_text(encoding="utf-8")
    assert "pas un conseil financier personnalisé" in text
    assert EM_DASH not in text
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    prose = re.sub(r"`[^`\n]*`", "", prose)
    assert not re.search(r"\b(compliant|conflict)\b", prose)
    assert EM_DASH not in (script_outputs[0] / "sensitivity.json").read_text(encoding="utf-8")


def test_flip_factor_floor_rule_uses_threshold_over_value():
    """Plancher : facteur = seuil / valeur, même sens que scale_thresholds."""
    rule = {"rule_type": "min_defensive_share", "direction": "min", "warn_threshold": 0.4, "limit_threshold": 0.3}
    assert sens.flip_factor(rule, 0.5) == {"warn": 0.8, "limit": 0.6}
    assert sens.flip_factor(rule, 0.0) == {"warn": None, "limit": None}


# Revue : verdict financier comparable ------------------------------------------------------


def _outcome(rules, financial):
    return sens.VariantOutcome(variant_id="x", period_start="", period_end="", n_observations=0,
                               volatility_ann=0.0, max_drawdown=0.0, largest_correlated_group_weight=None,
                               overall=financial, financial=financial, esg=None, rules=rules)


def _rule_info(status, comparable=True, rule_type="max_portfolio_volatility"):
    return {"status": status, "value": 0.0, "rule_type": rule_type, "label_fr": "", "comparable": comparable}


def test_comparable_financial_keeps_base_status_for_non_comparable_rule():
    base = _outcome({"R2": _rule_info("compliant"), "R3": _rule_info("tension", rule_type="max_portfolio_drawdown")}, "tension")
    other = _outcome({"R2": _rule_info("compliant"),
                      "R3": _rule_info("compliant", comparable=False, rule_type="max_portfolio_drawdown")}, "compliant")
    assert sens.comparable_financial(base, other) == "tension"


def test_comparable_financial_ignores_esg_rules():
    base = _outcome({"R1": _rule_info("compliant"), "R7": _rule_info("missing_info", rule_type="esg_exclusion")}, "compliant")
    assert sens.comparable_financial(base, base) == "compliant"


def test_grid_amira_tsla_window_change_is_not_a_verdict_change(personas):
    """Le changement d'Amira TSLA 25 % sur 3 ans venait seulement de R3, non comparable."""
    rows = sens.run_grid({"amira": personas["amira"]}, ideas=[sens.DEFAULT_IDEAS[0]])
    outcomes = rows[0]["outcomes"]
    for variant_id in ("window_3y", "window_1y"):
        assert outcomes[variant_id]["financial_comparable"] == outcomes["base"]["financial"]


def test_summary_counts_rules_per_persona(personas):
    rows = sens.run_grid(personas)
    for item in sens.axis_summary(rows):
        assert all(":" in key for key in item["rule_changes"])
        for change in item["financial_verdict_changes"]:
            assert change["after"] != change["before"]


def test_stable_rules_by_persona(personas):
    stable = sens.stable_rules_by_persona(sens.run_grid(personas))
    assert set(stable) == {"amira", "mateo", "robert"}
    assert "R1" in stable["robert"]


def test_variant_below_volatility_minimum_raises(robert_after):
    """Une variante trop courte (hebdomadaire sur un an : 52 rendements) est refusée explicitement."""
    from alphaforge.metrics import InsufficientDataError

    short = sens.Variant("weekly_1y", "frequence", "Hebdomadaire sur 1 an", "Test.", window_years=1,
                         frequency="weekly")
    with pytest.raises(InsufficientDataError):
        sens.variant_snapshot(robert_after, "portfolio_after", short)


def test_report_variants_all_have_enough_returns(personas):
    """Toutes les variantes et tous les blocs du rapport dépassent le minimum de la volatilité."""
    from alphaforge.metrics import MIN_OBSERVATIONS_FOR_VOLATILITY

    rows = sens.run_grid({"robert": personas["robert"]}, ideas=[sens.DEFAULT_IDEAS[0]])
    assert min(o["n_observations"] for o in rows[0]["outcomes"].values()) >= MIN_OBSERVATIONS_FOR_VOLATILITY
