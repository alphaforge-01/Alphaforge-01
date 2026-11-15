"""Tests de l'analyseur déterministe des demandes en langage naturel (request_parsing)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alphaforge import request_parsing as rp  # noqa: E402

# Univers réduit et inventé pour les tests : mêmes formes de tickers que le vrai univers.
UNIVERSE = [
    {"ticker": "TSLA", "name": "Tesla", "asset_class": "equity"},
    {"ticker": "NVDA", "name": "NVIDIA", "asset_class": "equity"},
    {"ticker": "AAPL", "name": "Apple", "asset_class": "equity"},
    {"ticker": "PG", "name": "Procter & Gamble", "asset_class": "equity"},
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "asset_class": "etf_equity"},
    {"ticker": "XIU.TO", "name": "iShares S&P/TSX 60 Index ETF", "asset_class": "etf_equity"},
    {"ticker": "SHOP.TO", "name": "Shopify", "asset_class": "equity"},
    {"ticker": "BTC-USD", "name": "Bitcoin", "asset_class": "crypto"},
    {"ticker": "MSFT", "name": "Microsoft", "asset_class": "equity"},
]
GUARDRAIL_PROMPTS = PROJECT_ROOT / "tests" / "fixtures" / "guardrail_prompts.json"


def parse(text, held=None):
    return rp.parse_request(text, UNIVERSE, held_tickers=held)


def test_simple_idea_pro_rata():
    result = parse("Et si je mettais 25 % dans TSLA ?")
    assert result.status == "idea"
    assert result.idea == {"ticker": "TSLA", "target_weight": 0.25,
                           "funding_source": "pro_rata", "funding_ticker": None}


def test_idea_with_funding_ticker_and_alias():
    result = parse("ajoute 10 % de BTC en vendant XIU.TO", held=["XIU.TO", "SPY"])
    assert result.status == "idea"
    assert result.idea["ticker"] == "BTC-USD"
    assert result.idea["target_weight"] == 0.10
    assert result.idea["funding_source"] == "from_ticker"
    assert result.idea["funding_ticker"] == "XIU.TO"


@pytest.mark.parametrize("text,ticker", [
    ("15 % de bitcoin", "BTC-USD"),
    ("Mettre 10 % dans Apple", "AAPL"),
    ("12 % dans Shopify", "SHOP.TO"),
    ("20 pour cent dans nvidia", "NVDA"),
])
def test_names_and_aliases(text, ticker):
    result = parse(text)
    assert result.status == "idea"
    assert result.idea["ticker"] == ticker


@pytest.mark.parametrize("text,suggestion", [
    ("12,5 % dans TSLA", 0.12),
    ("0,5 % dans TSLA", 0.01),
])
def test_decimal_weight_asks_and_proposes_rounding(text, suggestion):
    # Poids entiers seulement (le curseur va de 1 à 100) : une décimale propose l'arrondi.
    result = parse(text)
    assert result.status == "clarify"
    assert result.reason == rp.WEIGHT_OUT_OF_RANGE
    assert result.suggested_weights == (suggestion,)
    assert result.tickers == ("TSLA",)


@pytest.mark.parametrize("text", ["-10 % dans TSLA", "Mettre -5 % dans TSLA"])
def test_negative_weight_is_out_of_range(text):
    result = parse(text)
    assert result.reason == rp.WEIGHT_OUT_OF_RANGE
    assert result.suggested_weights == ()


@pytest.mark.parametrize("text", ["1e2 % dans TSLA", "10.5.3 % dans TSLA"])
def test_malformed_numbers_are_not_read(text):
    # Ni 2 % ni 5,3 % : un nombre mal formé n'est jamais lu en silence.
    result = parse(text)
    assert result.status == "clarify"
    assert result.target_weight is None


def test_funding_marker_before_target():
    result = parse("En vendant SPY, mets 10 % dans TSLA", held=["SPY"])
    assert result.status == "idea"
    assert result.idea["ticker"] == "TSLA"
    assert result.idea["funding_ticker"] == "SPY"


def test_vendre_is_a_funding_marker():
    result = parse("20 % dans MSFT et vendre AAPL", held=["AAPL"])
    assert result.status == "idea"
    assert result.idea["ticker"] == "MSFT"
    assert result.idea["funding_ticker"] == "AAPL"


def test_funding_without_target():
    result = parse("10 % en vendant SPY")
    assert result.status == "clarify"
    assert result.reason == rp.MISSING_TARGET
    assert result.funding_ticker == "SPY"


def test_several_assets_keep_funding():
    result = parse("10 % dans TSLA et NVDA en vendant SPY")
    assert result.reason == rp.SEVERAL_ASSETS
    assert result.tickers == ("TSLA", "NVDA")
    assert result.funding_ticker == "SPY"


def test_pro_rata_wins_over_funding_marker():
    result = parse("10 % dans AAPL depuis SPY au prorata")
    assert result.idea["funding_source"] == "pro_rata"


def test_missing_weight_proposes_one_click_weights():
    result = parse("Et si j'ajoutais du Tesla ?")
    assert result.status == "clarify"
    assert result.reason == rp.MISSING_WEIGHT
    assert result.tickers == ("TSLA",)
    assert result.suggested_weights == rp.SUGGESTED_WEIGHTS


def test_two_assets_is_ambiguous():
    result = parse("25 % dans TSLA et NVDA")
    assert result.status == "clarify"
    assert result.reason == rp.SEVERAL_ASSETS
    assert result.tickers == ("TSLA", "NVDA")
    assert result.idea is None


def test_two_weights_is_ambiguous():
    assert parse("10 % ou 20 % dans TSLA").reason == rp.SEVERAL_WEIGHTS


def test_asset_outside_universe_is_never_guessed():
    result = parse("40 % dans GME")
    assert result.status == "clarify"
    assert result.reason == rp.UNKNOWN_ASSET
    assert result.unknown_tokens == ("GME",)


def test_short_ticker_needs_uppercase():
    # "pg" en minuscules n'est pas reconnu : un mot courant ne devient pas un actif.
    assert parse("30 % de pg").reason == rp.UNKNOWN_ASSET
    assert parse("30 % de PG").idea["ticker"] == "PG"


def test_suffix_is_not_split():
    # XIU.TO est reconnu entier, et la fin de phrase ne gêne pas.
    assert parse("10 % dans TSLA en vendant XIU.TO.", held=["XIU.TO"]).idea["funding_ticker"] == "XIU.TO"


def test_question_without_idea():
    assert parse("Explique-moi la volatilité").reason == rp.NOT_AN_IDEA


def test_weight_out_of_range():
    assert parse("150 % dans TSLA").reason == rp.WEIGHT_OUT_OF_RANGE
    assert parse("0 % dans TSLA").reason == rp.WEIGHT_OUT_OF_RANGE


def test_funding_must_be_held_and_distinct():
    assert parse("10 % dans TSLA en vendant SPY", held=["XIU.TO"]).reason == rp.FUNDING_NOT_HELD
    assert parse("10 % dans TSLA en vendant TSLA", held=["TSLA"]).reason == rp.FUNDING_SAME_AS_ASSET
    assert parse("10 % dans TSLA en vendant SPY et XIU.TO").reason == rp.SEVERAL_FUNDING


@pytest.mark.parametrize("text,topic", [
    ("Achète TSLA pour moi.", rp.ORDER_EXECUTION),
    ("Passe un ordre d'achat de 25 % de TSLA", rp.ORDER_EXECUTION),
    ("Est-ce que TSLA va monter ?", rp.RETURN_PREDICTION),
    ("Dis-moi quoi acheter.", rp.PERSONALIZED_ADVICE),
    ("Dois-je mettre 25 % dans TSLA ?", rp.PERSONALIZED_ADVICE),
])
def test_refused_topics(text, topic):
    result = parse(text)
    assert result.status == "refused"
    assert result.reason == topic
    assert result.idea is None


@pytest.mark.parametrize("text,topic", [
    ("Achete 25 % de TSLA", rp.ORDER_EXECUTION),
    ("Achète 25 % de TSLA maintenant", rp.ORDER_EXECUTION),
    ("achete moi 10 % de TSLA", rp.ORDER_EXECUTION),
    ("Execute 10 % de TSLA", rp.ORDER_EXECUTION),
    ("Exécute un achat de 10 % de TSLA", rp.ORDER_EXECUTION),
    ("Place un ordre sur TSLA 25 %", rp.ORDER_EXECUTION),
    ("Ouvre une position de 10 % sur TSLA", rp.ORDER_EXECUTION),
    ("Mets 25 % dans TSLA sur mon compte Questrade", rp.ORDER_EXECUTION),
    ("Ajoute 10 % de TSLA à mon vrai portefeuille", rp.ORDER_EXECUTION),
    ("TSLA va doubler, mets 25 %", rp.RETURN_PREDICTION),
    ("Combien TSLA va rapporter si j'en mets 25 % ?", rp.RETURN_PREDICTION),
    ("Quel rendement aura TSLA l'an prochain avec 25 % ?", rp.RETURN_PREDICTION),
    ("25 % dans TSLA, quel sera son rendement futur ?", rp.RETURN_PREDICTION),
    ("Vends XIU.TO", rp.ORDER_EXECUTION),
])
def test_review_orders_and_predictions_are_refused(text, topic):
    result = parse(text, held=["XIU.TO"])
    assert result.status == "refused"
    assert result.reason == topic
    assert result.suggested_weights == ()
    assert result.idea is None


def test_selling_to_fund_is_not_an_order():
    # "en vendant" décrit la source des fonds d'une simulation, pas un ordre.
    assert parse("ajoute 10 % de BTC en vendant XIU.TO").status == "idea"


def test_guardrail_fixture_prompts_agree_with_local_screening():
    """Les requêtes refusées par le garde-fou le sont aussi localement, les permises jamais."""
    prompts = json.loads(GUARDRAIL_PROMPTS.read_text(encoding="utf-8"))
    for prompt in prompts:
        refused = rp.screen_request(prompt["text"]) is not None
        assert refused == (prompt["expected"] == "denied"), prompt["text"]


def test_normalize_keeps_positions():
    text = "Été à Montréal \u2019"
    assert len(rp.normalize(text)) == len(text)
    assert rp.normalize("Énergie") == "energie"
