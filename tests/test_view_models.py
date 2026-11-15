"""Structures de présentation de l'interface v2 (PR-1) : app/view_models.py.

Données réelles : analyse hors ligne de Robert avec 25 % de TSLA (outils et gouvernance
du projet, aucun modèle, aucun réseau), et fixtures d'analyse. Les tests vérifient
surtout que rien n'est inventé : chaque valeur rendue vient du résultat d'entrée.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import view_models as vm  # noqa: E402

from alphaforge.analysis_pipeline import run_analysis  # noqa: E402
from alphaforge.bedrock_client import BedrockConfig  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

IDEA = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}


@pytest.fixture(scope="module")
def result():
    persona = load_personas()["robert"]
    return run_analysis(persona["profile"], persona["portfolio"], IDEA,
                        mode="offline", config=BedrockConfig())


@pytest.fixture(scope="module")
def evidence(result):
    return result["evidence"]


def _by_subject_metric(evidence, subject, metric):
    return next(e for e in evidence.values() if e["subject"] == subject and e["metric"] == metric)


# --- Cartes de mesures ---------------------------------------------------------

def test_metric_cards_follow_registry(evidence):
    cards = vm.build_metric_cards(evidence)
    assert [card.metric for card in cards] == [m for m, _ in vm.HEADLINE_METRICS]
    for card in cards:
        after = _by_subject_metric(evidence, "portfolio_after", card.metric)
        before = _by_subject_metric(evidence, "portfolio_before", card.metric)
        delta = _by_subject_metric(evidence, "portfolio_after", f"{card.metric}_delta")
        assert card.value == after["value"]
        assert card.value_display == after["display_value"]
        assert card.before_display == before["display_value"]
        assert card.delta_display == delta["display_value"]


def test_metric_card_known_robert_values(evidence):
    volatility = vm.build_metric_cards(evidence)[0]
    assert (volatility.before_display, volatility.value_display, volatility.delta_display) == (
        "6,49 %", "17,6 %", "+11,11 pts")


def test_metric_cards_accept_evidence_list(evidence):
    assert vm.build_metric_cards(list(evidence.values())) == vm.build_metric_cards(evidence)


def test_metric_card_omitted_without_after_value(evidence):
    trimmed = {k: e for k, e in evidence.items()
               if not (e["subject"] == "portfolio_after" and e["metric"] == "defensive_share")}
    metrics = [card.metric for card in vm.build_metric_cards(trimmed)]
    assert "defensive_share" not in metrics
    assert len(metrics) == len(vm.HEADLINE_METRICS) - 1


def test_metric_card_without_before_or_delta_keeps_none(evidence):
    trimmed = {k: e for k, e in evidence.items()
               if not (e["metric"] == "max_drawdown_delta"
                       or (e["subject"] == "portfolio_before" and e["metric"] == "max_drawdown"))}
    card = next(c for c in vm.build_metric_cards(trimmed) if c.metric == "max_drawdown")
    assert card.before_display is None and card.delta_display is None


def test_metric_card_ignores_non_numeric_value(evidence):
    broken = copy.deepcopy(evidence)
    entry = _by_subject_metric(broken, "portfolio_after", "volatility_ann")
    entry["value"] = "n/a"
    assert "volatility_ann" not in [c.metric for c in vm.build_metric_cards(broken)]


# --- Verdicts ------------------------------------------------------------------

def test_verdicts_robert_has_no_esg(result):
    verdicts = vm.build_verdicts(result["governance_after"])
    assert verdicts.overall.status == "conflict"
    assert verdicts.financial.status == "conflict"
    assert verdicts.esg is None
    assert verdicts.overall.label == "Conflit"


def test_verdicts_split_financial_and_esg():
    governance = {
        "overall_status": "conflict",
        "checks": [
            {"check_id": "G1", "rule_type": "max_single_asset_weight", "status": "compliant"},
            {"check_id": "G2", "rule_type": "esg_exclusion", "status": "conflict"},
        ],
    }
    verdicts = vm.build_verdicts(governance)
    assert verdicts.financial.status == "compliant"
    assert verdicts.esg.status == "conflict"
    assert verdicts.overall.status == "conflict"


def test_verdicts_without_governance():
    assert vm.build_verdicts(None) == vm.Verdicts(None, None, None)


# --- Mesures face aux seuils ---------------------------------------------------

def test_threshold_bars_only_percent_rules(result, evidence):
    bars = vm.build_threshold_bars(result["governance_after"], evidence, result["profile"])
    ids = [bar.check_id for bar in bars]
    assert "G5" not in ids            # règle booléenne, sans seuil à tracer
    assert ids == ["G1", "G2", "G3", "G4", "G6"]


def test_threshold_bar_values_come_from_governance(result, evidence):
    bars = {b.check_id: b for b in vm.build_threshold_bars(result["governance_after"], evidence,
                                                           result["profile"])}
    checks = {c["check_id"]: c for c in result["governance_after"]["checks"]}
    for check_id, bar in bars.items():
        check = checks[check_id]
        assert (bar.value, bar.warn, bar.limit) == (check["value"], check["warn_threshold"],
                                                    check["limit_threshold"])
        assert bar.status == check["status"]
    assert bars["G1"].value_display == "25 %"
    assert bars["G1"].limit_display == "22 %"
    assert bars["G2"].value_display == "17,6 %"


def test_threshold_bar_direction_from_profile_rules(result, evidence):
    bars = {b.check_id: b for b in vm.build_threshold_bars(result["governance_after"], evidence,
                                                           result["profile"])}
    assert bars["G1"].direction == "max"
    assert bars["G4"].direction == "min"


def test_threshold_bar_direction_inferred_without_profile(result):
    bars = {b.check_id: b for b in vm.build_threshold_bars(result["governance_after"])}
    assert bars["G4"].direction == "min"
    assert bars["G1"].direction == "max"
    # Sans registre, le texte vient du format partagé et reste lisible.
    assert bars["G1"].value_display == "25 %"


def test_threshold_bars_skip_missing_info():
    governance = {"checks": [
        {"check_id": "G1", "rule_id": "R1", "label_fr": "x", "status": "missing_info",
         "value": 0.1, "warn_threshold": 0.2, "limit_threshold": 0.3, "unit": "pct"},
        {"check_id": "G2", "rule_id": "R2", "label_fr": "y", "status": "compliant",
         "value": None, "warn_threshold": 0.2, "limit_threshold": 0.3, "unit": "pct"},
    ]}
    assert vm.build_threshold_bars(governance) == []


def test_threshold_bar_without_warn_threshold():
    governance = {"checks": [
        {"check_id": "G1", "rule_id": "R1", "label_fr": "x", "status": "compliant", "value": 0.1,
         "warn_threshold": None, "limit_threshold": 0.3, "unit": "pct"}]}
    (bar,) = vm.build_threshold_bars(governance)
    assert bar.warn is None and bar.warn_display is None


# --- Poids avant et après ------------------------------------------------------

def test_weight_rows_match_registry(evidence):
    rows = vm.build_weight_rows(evidence, {"TSLA": "Tesla"})
    by_ticker = {row.ticker: row for row in rows}
    tsla = by_ticker["TSLA"]
    assert tsla.name == "Tesla"
    assert tsla.before is None and tsla.before_display is None   # absent du registre : rien inventé
    assert tsla.after == 0.25 and tsla.after_display == "25 %"
    for row in rows:
        for subject, value in (("portfolio_before", row.before), ("portfolio_after", row.after)):
            registered = [e["value"] for e in evidence.values()
                          if e["subject"] == subject and e["metric"] == f"weights.{row.ticker}"]
            assert (value in registered) if value is not None else not registered


def test_weight_rows_cover_all_registered_tickers(evidence):
    registered = {e["metric"][len("weights."):] for e in evidence.values()
                  if e["metric"].startswith("weights.")
                  and e["subject"] in ("portfolio_before", "portfolio_after")}
    assert {row.ticker for row in vm.build_weight_rows(evidence)} == registered


def test_weight_rows_sorted_by_largest_weight_then_ticker(evidence):
    rows = vm.build_weight_rows(evidence)
    keys = [(-max(r.before or 0, r.after or 0), r.ticker) for r in rows]
    assert keys == sorted(keys)


def test_weight_rows_empty_without_weights():
    assert vm.build_weight_rows({}) == []
    assert vm.build_weight_rows(None) == []


def test_weight_rows_ignore_variant_subjects(evidence):
    only_variant = {k: e for k, e in evidence.items() if e["subject"].startswith("variant:")}
    assert vm.build_weight_rows(only_variant) == []


# --- Comparaison des variantes -------------------------------------------------

def test_variant_rows_start_with_initial_idea(result):
    rows = vm.build_variant_rows(result)
    assert rows[0].row_id == "initial"
    assert rows[0].target_weight_display == "25 %"
    assert rows[0].status == "conflict"
    assert rows[0].volatility_display == "17,6 %"
    assert [r.row_id for r in rows[1:]] == [v["variant_id"] for v in result["variants"]]


def test_variant_rows_use_variant_evidence(result, evidence):
    row = vm.build_variant_rows(result)[1]
    variant = result["variants"][0]
    assert row.reason_code == variant["reason_code"]
    assert row.reason_label == "réduire le poids"
    assert row.target_weight_display == "17 %"
    assert row.status == variant["governance"]["overall_status"]
    expected = _by_subject_metric(evidence, f"variant:{variant['variant_id']}", "volatility_ann")
    assert row.volatility == expected["value"]
    assert row.volatility_display == expected["display_value"]


def test_variant_row_without_measures_keeps_none(result):
    stripped = copy.deepcopy(result)
    stripped["evidence"] = {k: e for k, e in stripped["evidence"].items()
                            if not e["subject"].startswith("variant:")}
    row = vm.build_variant_rows(stripped)[1]
    assert row.volatility is None and row.max_drawdown_display is None


def test_variant_rows_without_variants(result):
    bare = {**result, "variants": []}
    assert [r.row_id for r in vm.build_variant_rows(bare)] == ["initial"]


def test_variant_rows_without_idea():
    assert vm.build_variant_rows({}) == []


# --- Contexte du profil --------------------------------------------------------

def test_profile_chips_robert(result):
    chips = {chip.label: chip.value for chip in vm.build_profile_chips(result["profile"])}
    profile = result["profile"]
    assert chips["Horizon"].endswith("ans")
    assert chips["Capital fictif"] == "100 000 $" or chips["Capital fictif"].endswith("$")
    assert chips["Cryptoactifs"] == ("autorisés" if profile["crypto_allowed"] else "exclus")
    assert set(chips) <= {"Horizon", "Tolérance au risque", "Expérience", "Préférence ESG",
                          "Cryptoactifs", "Capital fictif"}


def test_profile_chips_skip_missing_fields():
    chips = vm.build_profile_chips({"risk_tolerance": "moderate", "display_name": "X"})
    assert [(c.label, c.value) for c in chips] == [("Tolérance au risque", "modérée")]


def test_profile_chips_without_profile():
    assert vm.build_profile_chips(None) == []
    assert vm.build_profile_chips({}) == []


# --- Vue complète --------------------------------------------------------------

def test_result_view_assembles_every_part(result):
    view = vm.build_result_view(result, {"TSLA": "Tesla"})
    assert view.ticker == "TSLA" and view.target_weight_display == "25 %"
    assert view.profile_name == result["profile"]["display_name"]
    assert view.objective == result["profile"]["objective"]
    assert view.is_fixture is False
    assert len(view.metric_cards) == 4
    assert view.threshold_bars and view.weight_rows and len(view.variant_rows) >= 2
    assert view.profile_chips and view.verdicts.overall.status == "conflict"


def test_result_view_does_not_mutate_input(result):
    snapshot = copy.deepcopy(result)
    vm.build_result_view(result)
    assert result == snapshot


def test_result_view_is_frozen(result):
    view = vm.build_result_view(result)
    with pytest.raises(Exception):
        view.ticker = "X"  # type: ignore[misc]


@pytest.mark.parametrize("name", ["analysis_result_robert_tsla.json", "analysis_result_amira_tsla.json"])
def test_result_view_on_fixtures(name):
    fixture = json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
    view = vm.build_result_view(fixture)
    assert view.is_fixture is True
    assert view.ticker == "TSLA"
    assert view.verdicts.overall is not None
    assert view.variant_rows[0].row_id == "initial"
    registry = {(e["subject"], e["metric"]): e for e in fixture["evidence"].values()}
    for card in view.metric_cards:
        assert card.value == registry[("portfolio_after", card.metric)]["value"]


def test_result_view_on_empty_result_is_empty_not_error():
    view = vm.build_result_view({})
    assert view.metric_cards == [] and view.threshold_bars == []
    assert view.weight_rows == [] and view.variant_rows == [] and view.profile_chips == []
    assert view.verdicts == vm.Verdicts(None, None, None)
    assert view.ticker == "" and view.target_weight_display == ""


def test_module_has_no_streamlit_dependency():
    source = (APP_DIR / "view_models.py").read_text(encoding="utf-8")
    assert "streamlit" not in source
