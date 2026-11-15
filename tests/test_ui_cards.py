"""Cartes de mesures et verdicts de l'interface v2 (PR-2) : app/components/cards.py et app/ui_labels.py.

Les textes sont vérifiés par des fonctions pures. Le rendu est joué avec `AppTest`, sans
navigateur et sans réseau. Les valeurs manquantes doivent rester inconnues : jamais de zéro.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import ui_labels as labels  # noqa: E402
import ui_texts as texts  # noqa: E402
import view_models as vm  # noqa: E402
from components import cards  # noqa: E402

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

STATUSES = ("compliant", "tension", "conflict", "missing_info")


def _card(**overrides):
    base = dict(metric="volatility_ann", label="Volatilité annualisée", value=0.176,
                value_display="17,6 %", before_display="6,49 %", delta_display="+11,11 pts",
                status="tension")
    base.update(overrides)
    return vm.MetricCard(**base)


# --- Libellés ------------------------------------------------------------------

def test_view_models_reuses_ui_labels():
    assert vm.HEADLINE_METRICS is labels.HEADLINE_METRICS
    assert vm.PROFILE_CHIP_LABELS is labels.PROFILE_CHIP_LABELS


def test_every_headline_metric_has_help_text():
    for metric, label in labels.HEADLINE_METRICS:
        assert label and labels.METRIC_HELP[metric]


def test_status_visuals_cover_every_status():
    for status in STATUSES:
        assert status in labels.STATUS_ICONS and status in labels.STATUS_HELP
        assert status in texts.STATUS_LABELS and status in texts.STATUS_COLORS


def test_labels_have_no_dash_or_emoji():
    for name in dir(labels):
        value = getattr(labels, name)
        if isinstance(value, str):
            assert "\u2014" not in value and not any(0x1F300 <= ord(c) <= 0x1FAFF for c in value)


# --- État visuel ---------------------------------------------------------------

def test_status_styles_are_distinct():
    styles = [cards.status_style(status) for status in STATUSES]
    assert len({s.label for s in styles}) == 4
    assert len({s.color for s in styles}) == 4
    assert len({s.icon for s in styles}) == 4
    assert [s.status for s in styles] == list(STATUSES)


@pytest.mark.parametrize("status", [None, "", "inconnu"])
def test_unknown_status_falls_back_to_neutral_style(status):
    style = cards.status_style(status)
    assert style.status == "missing_info"
    assert style.color == texts.STATUS_COLORS["missing_info"]


def test_unknown_status_keeps_its_raw_text():
    assert cards.status_style("inconnu").label == "inconnu"


# --- Textes des cartes ---------------------------------------------------------

def test_card_texts_full_card():
    content = cards.card_texts(_card())
    assert (content.label, content.value, content.delta) == ("Volatilité annualisée", "17,6 %", "+11,11 pts")
    assert content.before_line == "Avant : 6,49 %"
    assert content.delta_note is None
    assert content.status.status == "tension"
    assert content.help == labels.METRIC_HELP["volatility_ann"]


def test_card_texts_missing_before_is_not_available_not_zero():
    content = cards.card_texts(_card(before_display=None))
    assert content.before_line == "Avant : Non disponible"
    assert "0" not in content.before_line


def test_card_texts_missing_delta_has_no_delta():
    content = cards.card_texts(_card(delta_display=None))
    assert content.delta is None
    assert content.delta_note == labels.CARD_DELTA_UNAVAILABLE


def test_card_texts_without_status():
    assert cards.card_texts(_card(status=None)).status is None


def test_card_texts_unknown_metric_has_no_help():
    assert cards.card_texts(_card(metric="autre")).help is None


# --- Statut des cartes (view_models) -------------------------------------------

@pytest.fixture(scope="module")
def robert_result():
    from alphaforge.analysis_pipeline import run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.profiles import load_personas

    persona = load_personas()["robert"]
    idea = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    return run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline",
                        config=BedrockConfig())


def test_card_status_comes_from_governance_checks(robert_result):
    built = vm.build_metric_cards(robert_result["evidence"], governance=robert_result["governance_after"])
    statuses = {card.metric: card.status for card in built}
    checks = {c["rule_type"]: c["status"] for c in robert_result["governance_after"]["checks"]}
    assert statuses["top_asset_weight"] == checks["max_single_asset_weight"] == "conflict"
    assert statuses["volatility_ann"] == checks["max_portfolio_volatility"]
    assert statuses["max_drawdown"] == checks["max_portfolio_drawdown"]
    assert statuses["defensive_share"] == checks["min_defensive_share"]


def test_card_status_is_none_without_governance(robert_result):
    built = vm.build_metric_cards(robert_result["evidence"])
    assert all(card.status is None for card in built)


def test_card_status_is_none_without_matching_rule(robert_result):
    governance = {"checks": [c for c in robert_result["governance_after"]["checks"]
                             if c["rule_type"] != "min_defensive_share"]}
    built = {c.metric: c.status for c in vm.build_metric_cards(robert_result["evidence"],
                                                              governance=governance)}
    assert built["defensive_share"] is None
    assert built["top_asset_weight"] is not None


def test_card_status_takes_the_worst_of_several_checks(robert_result):
    governance = {"checks": [
        {"rule_type": "max_portfolio_volatility", "status": "compliant"},
        {"rule_type": "max_portfolio_volatility", "status": "conflict"},
    ]}
    built = {c.metric: c.status for c in vm.build_metric_cards(robert_result["evidence"],
                                                              governance=governance)}
    assert built["volatility_ann"] == "conflict"


# --- Rendu Streamlit -----------------------------------------------------------

CARDS_SCRIPT = """
import sys
sys.path.insert(0, {app!r})
import streamlit as st
import view_models as vm
from components import cards
cards_in = [
    vm.MetricCard("volatility_ann", "Volatilité annualisée", 0.176, "17,6 %", "6,49 %", "+11,11 pts", "tension"),
    vm.MetricCard("max_drawdown", "Perte maximale historique", 0.26, "26,04 %", None, None, None),
]
cards.render_metric_cards(cards_in)
cards.render_metric_cards([])
"""


def test_render_metric_cards_without_exception():
    at = AppTest.from_string(CARDS_SCRIPT.format(app=str(APP_DIR)), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert [m.label for m in at.metric] == ["Volatilité annualisée", "Perte maximale historique"]
    assert [m.value for m in at.metric] == ["17,6 %", "26,04 %"]
    assert at.metric[0].delta == "+11,11 pts"
    assert at.metric[1].delta in ("", None)
    captions = [c.value for c in at.caption]
    assert "Avant : 6,49 %" in captions
    assert "Avant : Non disponible" in captions
    assert labels.CARD_DELTA_UNAVAILABLE in captions
    assert not any("Avant : 0" in c for c in captions)


VERDICT_SCRIPT = """
import sys
sys.path.insert(0, {app!r})
import view_models as vm
from components import cards
badge = lambda s: vm.VerdictBadge(s, s, "gray")
cards.render_verdicts(vm.Verdicts(badge("conflict"), badge("conflict"), None), show_missing_esg={show})
cards.render_verdicts(vm.Verdicts(badge("tension"), badge("compliant"), badge("conflict")))
cards.render_verdicts(vm.Verdicts(None, None, None))
"""


@pytest.mark.parametrize("show", [False, True])
def test_render_verdicts(show):
    at = AppTest.from_string(VERDICT_SCRIPT.format(app=str(APP_DIR), show=show), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    captions = [c.value for c in at.caption]
    assert captions.count(labels.VERDICT_ESG) == 1          # seulement le second jeu a un verdict ESG
    assert captions.count(labels.VERDICT_FINANCIAL) == 3
    assert (labels.VERDICT_ESG_NONE in captions) is show
    assert labels.VERDICT_UNAVAILABLE in captions            # verdicts absents : "Non disponible"
    markdown = [m.value for m in at.markdown]
    assert sum(labels.VERDICT_OVERALL in value for value in markdown) == 3


def test_cards_module_is_not_wired_to_state_or_data():
    source = (APP_DIR / "components" / "cards.py").read_text(encoding="utf-8")
    for forbidden in ("session", "data_source", "boto3", "requests"):
        assert forbidden not in source
