"""Tests des libellés français des classes d'actifs, secteurs et devises (P1-8)."""
from __future__ import annotations

import re

import pytest

from alphaforge import agent_tools
from alphaforge.asset_labels import (
    ASSET_CLASS_FR,
    CURRENCY_FR,
    SECTOR_FR,
    asset_class_fr,
    currency_fr,
    sector_fr,
)
from alphaforge.data_loading import load_universe
from alphaforge.profiles import load_personas

ENGLISH_NAMES = sorted(set(SECTOR_FR) | set(ASSET_CLASS_FR))


def _contains_word(text: str, word: str) -> bool:
    return re.search(r"(?<![\w'])" + re.escape(word) + r"(?!\w)", text) is not None


def test_every_universe_class_and_sector_is_translated():
    universe = load_universe()
    assert set(universe["asset_class"]) <= set(ASSET_CLASS_FR)
    assert set(universe["sector"]) <= set(SECTOR_FR)
    assert set(universe["currency"]) <= set(CURRENCY_FR)


@pytest.mark.parametrize("func,code,expected", [
    (asset_class_fr, "equity", "Actions"),
    (asset_class_fr, "etf_bond", "FNB d'obligations"),
    (sector_fr, "Consumer Discretionary", "Consommation discrétionnaire"),
    (sector_fr, "Information Technology", "Technologies de l'information"),
    (currency_fr, "CAD", "dollar canadien (CAD)"),
])
def test_known_names_are_translated(func, code, expected):
    assert func(code) == expected


@pytest.mark.parametrize("func", [asset_class_fr, sector_fr, currency_fr])
def test_unknown_name_is_returned_unchanged(func):
    assert func("Inconnu XYZ") == "Inconnu XYZ"


def test_translations_have_no_em_dash():
    for text in (*ASSET_CLASS_FR.values(), *SECTOR_FR.values(), *CURRENCY_FR.values()):
        assert "\u2014" not in text


def test_ui_tables_match_package_tables():
    """L'interface et les preuves doivent dire la même chose."""
    ui_texts = pytest.importorskip("app.ui_texts")
    assert ui_texts.ASSET_CLASS_LABELS == ASSET_CLASS_FR
    assert ui_texts.SECTOR_LABELS == SECTOR_FR


@pytest.fixture(scope="module")
def tsla_simulation():
    personas = load_personas()
    labels = []
    for data in personas.values():
        result = agent_tools.simulate_portfolio_change(
            data["portfolio"], {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata",
                                "funding_ticker": None})
        assert result["status"] == "ok"
        labels += [entry["label_fr"] for entry in result["evidence"]]
        before = agent_tools.analyze_portfolio(data["portfolio"])
        labels += [entry["label_fr"] for entry in before["evidence"]]
    return labels


def test_evidence_labels_have_no_english_class_or_sector(tsla_simulation):
    leftovers = sorted({(word, label) for label in tsla_simulation for word in ENGLISH_NAMES
                        if _contains_word(label, word)})
    assert leftovers == []


def test_evidence_labels_use_french_names(tsla_simulation):
    assert "Poids du secteur : Consommation discrétionnaire" in " | ".join(tsla_simulation)
    assert any(label.startswith("Poids de la classe d'actifs : Actions") for label in tsla_simulation)
    assert any(label.startswith("Exposition au dollar canadien (CAD)") for label in tsla_simulation)


def test_evidence_keys_keep_original_codes():
    """La clé de preuve reste stable : seul le libellé est traduit."""
    data = load_personas()["robert"]
    result = agent_tools.analyze_portfolio(data["portfolio"])
    keys = {entry["evidence_key"] for entry in result["evidence"]}
    assert "weight_by_asset_class.etf_bond:portfolio_before" in keys
    assert "currency_exposure.CAD:portfolio_before" in keys
