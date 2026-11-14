"""Tests du portefeuille fictif : validation, rendements, radiographie et simulation d'idée.

Portefeuilles inventés (ou fictifs des personas), données de prix réelles du jeu de départ,
aucun appel AWS.
"""

import copy
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alphaforge import governance
from alphaforge.calendar_alignment import daily_cad_returns, returns_base_date
from alphaforge.contracts import PortfolioSnapshot, check_keys
from alphaforge.metrics import compute_return_metrics
from alphaforge.portfolio import (
    PortfolioError,
    apply_idea,
    build_snapshot,
    portfolio_daily_returns,
    portfolio_weights,
)

PERSONAS_PATH = Path(__file__).resolve().parents[1] / "data" / "external" / "investor_profiles.json"
AS_OF = "2023-12-29"


def _from_pairs(pairs):
    """Portefeuille fictif à partir d'une liste de (ticker, poids)."""
    return {
        "portfolio_id": "test",
        "label_fr": "Portefeuille d'essai",
        "is_fictional": True,
        "base_currency": "CAD",
        "positions": [{"ticker": t, "weight": w} for t, w in pairs],
    }


def _idea(ticker, target, funding="pro_rata", funding_ticker=None):
    return {
        "ticker": ticker,
        "target_weight": target,
        "funding_source": funding,
        "funding_ticker": funding_ticker,
    }


def _as_dict(portfolio):
    return {p["ticker"]: p["weight"] for p in portfolio["positions"]}


@pytest.fixture(scope="module")
def personas():
    return json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))["personas"]


@pytest.fixture(scope="module")
def robert(personas):
    return personas["robert"]["portfolio"]


@pytest.fixture(scope="module")
def robert_profile(personas):
    return personas["robert"]["profile"]


@pytest.fixture(scope="module")
def snapshot(robert):
    return build_snapshot(robert, "portfolio_before")


def _contains_numpy(value):
    if isinstance(value, (np.generic, np.ndarray)):
        return True
    if isinstance(value, dict):
        return any(_contains_numpy(k) or _contains_numpy(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_numpy(v) for v in value)
    return False


def _all_floats(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _all_floats(v)
    elif isinstance(value, float):
        yield value


# ---------- portfolio_weights ----------

class TestPortfolioWeights:
    def test_valid_portfolio_returns_series(self):
        weights = portfolio_weights(_from_pairs([("XIU.TO", 0.6), ("XBB.TO", 0.4)]))
        assert weights["XIU.TO"] == pytest.approx(0.6), "Le poids de XIU.TO doit être conservé"
        assert weights.sum() == pytest.approx(1.0)

    def test_empty_positions_rejected(self):
        with pytest.raises(PortfolioError):
            portfolio_weights(_from_pairs([]))

    def test_missing_positions_key_rejected(self):
        with pytest.raises(PortfolioError):
            portfolio_weights({"portfolio_id": "x"})

    def test_duplicate_ticker_rejected(self):
        with pytest.raises(PortfolioError, match="plusieurs fois"):
            portfolio_weights(_from_pairs([("XIU.TO", 0.5), ("XIU.TO", 0.5)]))

    def test_unknown_ticker_rejected(self):
        with pytest.raises(PortfolioError, match="FAKE"):
            portfolio_weights(_from_pairs([("XIU.TO", 0.5), ("FAKE", 0.5)]))

    def test_negative_weight_rejected(self):
        with pytest.raises(PortfolioError):
            portfolio_weights(_from_pairs([("XIU.TO", 1.2), ("XBB.TO", -0.2)]))

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_non_finite_weight_rejected(self, bad):
        with pytest.raises(PortfolioError):
            portfolio_weights(_from_pairs([("XIU.TO", bad), ("XBB.TO", 0.5)]))

    @pytest.mark.parametrize("a,b", [(0.5, 0.4), (0.6, 0.5)])
    def test_sum_not_one_rejected(self, a, b):
        with pytest.raises(PortfolioError, match="100"):
            portfolio_weights(_from_pairs([("XIU.TO", a), ("XBB.TO", b)]))

    def test_sum_within_tolerance_accepted_and_normalized(self):
        weights = portfolio_weights(_from_pairs([("XIU.TO", 0.6), ("XBB.TO", 0.4 + 5e-7)]))
        assert weights.sum() == pytest.approx(1.0, abs=1e-12), "Les poids doivent être renormalisés"

    def test_sum_just_outside_tolerance_rejected(self):
        with pytest.raises(PortfolioError):
            portfolio_weights(_from_pairs([("XIU.TO", 0.6), ("XBB.TO", 0.4 + 5e-6)]))

    def test_zero_weights_dropped(self):
        weights = portfolio_weights(_from_pairs([("XIU.TO", 0.6), ("XBB.TO", 0.4), ("GLD", 0.0)]))
        assert "GLD" not in weights.index, "Un poids nul doit être retiré"
        assert weights.sum() == pytest.approx(1.0)
        assert weights["XIU.TO"] == pytest.approx(0.6)


# ---------- portfolio_daily_returns ----------

class TestDailyReturns:
    def test_two_asset_matches_hand_computation(self):
        portfolio = _from_pairs([("XIU.TO", 0.6), ("XBB.TO", 0.4)])
        returns = daily_cad_returns(tickers=["XIU.TO", "XBB.TO"])
        expected = returns[["XIU.TO", "XBB.TO"]].to_numpy() @ np.array([0.6, 0.4])
        actual = portfolio_daily_returns(portfolio)
        np.testing.assert_allclose(actual.to_numpy(), expected, atol=1e-12)
        assert actual.index.equals(returns.index), "Le calendrier doit être celui des rendements en CAD"

    def test_single_asset_equals_asset_returns(self):
        actual = portfolio_daily_returns(_from_pairs([("XIU.TO", 1.0)]))
        expected = daily_cad_returns(tickers=["XIU.TO"])["XIU.TO"]
        np.testing.assert_allclose(actual.to_numpy(), expected.to_numpy(), atol=1e-12)

    def test_zero_weight_asset_has_no_effect(self):
        with_zero = portfolio_daily_returns(_from_pairs([("XIU.TO", 1.0), ("GLD", 0.0)]))
        without = portfolio_daily_returns(_from_pairs([("XIU.TO", 1.0)]))
        np.testing.assert_allclose(with_zero.to_numpy(), without.to_numpy(), atol=1e-12)

    def test_as_of_is_respected(self):
        portfolio = _from_pairs([("XIU.TO", 0.6), ("XBB.TO", 0.4)])
        actual = portfolio_daily_returns(portfolio, as_of=AS_OF)
        assert actual.index.max() <= pd.Timestamp(AS_OF), "Aucun rendement postérieur à as_of"
        full = portfolio_daily_returns(portfolio)
        assert len(actual) < len(full)
        returns = daily_cad_returns(as_of=AS_OF, tickers=["XIU.TO", "XBB.TO"])
        expected = returns[["XIU.TO", "XBB.TO"]].to_numpy() @ np.array([0.6, 0.4])
        np.testing.assert_allclose(actual.to_numpy(), expected, atol=1e-12)

    def test_series_named_after_portfolio_id(self):
        assert portfolio_daily_returns(_from_pairs([("XIU.TO", 1.0)])).name == "test"


# ---------- build_snapshot ----------

class TestSnapshot:
    def test_all_contract_keys_present(self, snapshot):
        assert check_keys(snapshot, PortfolioSnapshot) == [], "Toutes les clés du contrat sont requises"

    def test_subject_is_kept(self, snapshot):
        assert snapshot["subject"] == "portfolio_before"

    def test_native_python_types_only(self, snapshot):
        assert not _contains_numpy(snapshot), "Aucun type numpy dans l'instantané"
        for key in ("volatility_ann", "max_drawdown", "top_asset_weight", "defensive_share"):
            assert type(snapshot[key]) is float, key
        for key in ("subject", "max_drawdown_start", "max_drawdown_end", "top_asset"):
            assert type(snapshot[key]) is str, key
        assert snapshot["recovery_days"] is None or type(snapshot["recovery_days"]) is int
        assert snapshot["largest_correlated_group_weight"] is None

    def test_no_nan_anywhere(self, snapshot):
        for value in _all_floats(snapshot):
            assert math.isfinite(value), "Aucune valeur NaN ou infinie attendue"

    def test_json_serializable(self, snapshot):
        json.dumps(snapshot)

    @pytest.mark.parametrize("key", ["weights", "weight_by_asset_class", "weight_by_sector", "currency_exposure"])
    def test_groupings_sum_to_one(self, snapshot, key):
        assert sum(snapshot[key].values()) == pytest.approx(1.0), f"{key} doit totaliser 100 %"

    def test_defensive_share_robert(self, snapshot):
        # XBB.TO 0,20 + AGG 0,15 + ZST.TO 0,20 + GLD 0,10
        assert snapshot["defensive_share"] == pytest.approx(0.65)

    def test_asset_class_weights_robert(self, snapshot):
        assert snapshot["weight_by_asset_class"] == pytest.approx(
            {"etf_bond": 0.55, "etf_equity": 0.35, "etf_commodity": 0.10}
        )

    def test_currency_exposure_robert(self, snapshot):
        # CAD : XIU.TO 0,15 + XBB.TO 0,20 + ZST.TO 0,20 ; USD : SPY 0,20 + AGG 0,15 + GLD 0,10
        assert snapshot["currency_exposure"] == pytest.approx({"CAD": 0.55, "USD": 0.45})

    def test_currency_keys_always_present(self):
        only_cad = build_snapshot(_from_pairs([("XIU.TO", 1.0)]), "x")
        assert only_cad["currency_exposure"] == pytest.approx({"CAD": 1.0, "USD": 0.0})
        only_usd = build_snapshot(_from_pairs([("SPY", 1.0)]), "x")
        assert only_usd["currency_exposure"] == pytest.approx({"CAD": 0.0, "USD": 1.0})

    def test_sectors_come_from_universe(self):
        snapshot = build_snapshot(_from_pairs([("RY.TO", 0.5), ("TD.TO", 0.3), ("ENB.TO", 0.2)]), "x")
        assert snapshot["weight_by_sector"] == pytest.approx({"Financials": 0.8, "Energy": 0.2})

    def test_weights_sorted_desc(self, snapshot):
        values = list(snapshot["weights"].values())
        assert values == sorted(values, reverse=True)

    def test_top_asset_robert_tie_broken_alphabetically(self, snapshot):
        # SPY, XBB.TO et ZST.TO pèsent tous 0,20 : le premier par ordre alphabétique gagne
        assert snapshot["top_asset"] == "SPY"
        assert snapshot["top_asset_weight"] == pytest.approx(0.20)

    def test_top_asset_tie_not_dependent_on_input_order(self):
        a = build_snapshot(_from_pairs([("ZST.TO", 0.5), ("XBB.TO", 0.5)]), "x")
        b = build_snapshot(_from_pairs([("XBB.TO", 0.5), ("ZST.TO", 0.5)]), "x")
        assert a["top_asset"] == b["top_asset"] == "XBB.TO"

    def test_single_asset_metrics_match_metrics_module(self):
        snapshot = build_snapshot(_from_pairs([("XIU.TO", 1.0)]), "x")
        returns = daily_cad_returns(tickers=["XIU.TO"])["XIU.TO"]
        expected = compute_return_metrics(returns, returns_base_date())
        assert snapshot["volatility_ann"] == pytest.approx(expected.volatility_ann, abs=1e-12)
        assert snapshot["max_drawdown"] == pytest.approx(expected.max_drawdown, abs=1e-12)
        assert snapshot["max_drawdown_start"] == expected.max_drawdown_start
        assert snapshot["max_drawdown_end"] == expected.max_drawdown_end
        assert snapshot["recovery_days"] == expected.recovery_days
        assert snapshot["top_asset"] == "XIU.TO"
        assert snapshot["top_asset_weight"] == pytest.approx(1.0)

    def test_as_of_changes_period(self):
        early = build_snapshot(_from_pairs([("XIU.TO", 1.0)]), "x", as_of=AS_OF)
        assert early["max_drawdown_end"] <= AS_OF, "Le creux ne peut pas être postérieur à as_of"


# ---------- apply_idea : pro_rata ----------

class TestApplyIdeaProRata:
    def test_robert_plus_25_tsla(self, robert):
        after = _as_dict(apply_idea(robert, _idea("TSLA", 0.25)))
        assert after["TSLA"] == pytest.approx(0.25)
        for position in robert["positions"]:
            assert after[position["ticker"]] == pytest.approx(position["weight"] * 0.75)
        assert sum(after.values()) == pytest.approx(1.0)

    def test_held_ticker_set_to_target_and_others_rescaled(self):
        portfolio = _from_pairs([("XIU.TO", 0.5), ("XBB.TO", 0.3), ("GLD", 0.2)])
        after = _as_dict(apply_idea(portfolio, _idea("XIU.TO", 0.3)))
        assert after["XIU.TO"] == pytest.approx(0.3)
        # les autres pesaient 0,5 au total et passent à 0,7 : facteur 1,4
        assert after["XBB.TO"] == pytest.approx(0.3 * 1.4)
        assert after["GLD"] == pytest.approx(0.2 * 1.4)
        assert sum(after.values()) == pytest.approx(1.0)

    def test_target_zero_removes_position(self):
        portfolio = _from_pairs([("XIU.TO", 0.5), ("XBB.TO", 0.3), ("GLD", 0.2)])
        after = _as_dict(apply_idea(portfolio, _idea("XIU.TO", 0.0)))
        assert "XIU.TO" not in after
        assert after["XBB.TO"] == pytest.approx(0.6)
        assert after["GLD"] == pytest.approx(0.4)

    def test_target_one_leaves_only_ticker(self):
        portfolio = _from_pairs([("XIU.TO", 0.5), ("XBB.TO", 0.5)])
        after = _as_dict(apply_idea(portfolio, _idea("TSLA", 1.0)))
        assert after == pytest.approx({"TSLA": 1.0})

    def test_no_other_position_cannot_fund(self):
        with pytest.raises(PortfolioError):
            apply_idea(_from_pairs([("XIU.TO", 1.0)]), _idea("XIU.TO", 0.5))


# ---------- apply_idea : from_ticker ----------

class TestApplyIdeaFromTicker:
    @pytest.fixture
    def portfolio(self):
        return _from_pairs([("XIU.TO", 0.5), ("XBB.TO", 0.3), ("GLD", 0.2)])

    def test_cash_taken_only_from_funding_ticker(self, portfolio):
        after = _as_dict(apply_idea(portfolio, _idea("TSLA", 0.1, "from_ticker", "XBB.TO")))
        assert after["TSLA"] == pytest.approx(0.1)
        assert after["XBB.TO"] == pytest.approx(0.2)
        assert after["XIU.TO"] == pytest.approx(0.5), "Les autres positions ne bougent pas"
        assert after["GLD"] == pytest.approx(0.2)
        assert sum(after.values()) == pytest.approx(1.0)

    def test_reducing_target_gives_weight_back_to_funding(self, portfolio):
        after = _as_dict(apply_idea(portfolio, _idea("XIU.TO", 0.3, "from_ticker", "GLD")))
        assert after["XIU.TO"] == pytest.approx(0.3)
        assert after["GLD"] == pytest.approx(0.4)
        assert after["XBB.TO"] == pytest.approx(0.3)

    def test_funding_exhausted_exactly_drops_position(self, portfolio):
        after = _as_dict(apply_idea(portfolio, _idea("TSLA", 0.2, "from_ticker", "GLD")))
        assert "GLD" not in after, "Une source épuisée doit être retirée"
        assert after["TSLA"] == pytest.approx(0.2)
        assert sum(after.values()) == pytest.approx(1.0)

    def test_insufficient_funding_raises(self, portfolio):
        with pytest.raises(PortfolioError, match="financer"):
            apply_idea(portfolio, _idea("TSLA", 0.25, "from_ticker", "GLD"))

    def test_missing_funding_ticker_raises(self, portfolio):
        with pytest.raises(PortfolioError, match="funding_ticker"):
            apply_idea(portfolio, _idea("TSLA", 0.1, "from_ticker", None))

    def test_funding_equal_to_ticker_raises(self, portfolio):
        with pytest.raises(PortfolioError):
            apply_idea(portfolio, _idea("XIU.TO", 0.3, "from_ticker", "XIU.TO"))

    def test_funding_not_held_raises(self, portfolio):
        with pytest.raises(PortfolioError, match="aucun poids dans le portefeuille"):
            apply_idea(portfolio, _idea("TSLA", 0.1, "from_ticker", "AAPL"))


# ---------- apply_idea : validations et propriétés générales ----------

class TestApplyIdeaValidation:
    @pytest.fixture
    def portfolio(self):
        return _from_pairs([("XIU.TO", 0.5), ("XBB.TO", 0.5)])

    @pytest.mark.parametrize("target", [-0.01, 1.01, float("nan"), float("inf")])
    def test_invalid_target_rejected(self, portfolio, target):
        with pytest.raises(PortfolioError):
            apply_idea(portfolio, _idea("TSLA", target))

    def test_unknown_ticker_rejected(self, portfolio):
        with pytest.raises(PortfolioError, match="FAKE"):
            apply_idea(portfolio, _idea("FAKE", 0.1))

    def test_unknown_funding_source_rejected(self, portfolio):
        with pytest.raises(PortfolioError, match="inconnue"):
            apply_idea(portfolio, _idea("TSLA", 0.1, funding="sell_everything"))

    def test_original_portfolio_unchanged(self, robert):
        before = copy.deepcopy(robert)
        apply_idea(robert, _idea("TSLA", 0.25))
        apply_idea(robert, _idea("TSLA", 0.1, "from_ticker", "SPY"))
        assert robert == before, "Le portefeuille d'origine ne doit pas être modifié"

    def test_result_metadata(self, robert):
        after = apply_idea(robert, _idea("TSLA", 0.25))
        assert after["is_fictional"] is True
        assert after["base_currency"] == "CAD"
        assert after["portfolio_id"] != robert["portfolio_id"]

    def test_positions_sorted_by_weight_desc(self, robert):
        weights = [p["weight"] for p in apply_idea(robert, _idea("TSLA", 0.25))["positions"]]
        assert weights == sorted(weights, reverse=True)

    def test_result_is_valid_portfolio(self, robert):
        after = apply_idea(robert, _idea("TSLA", 0.25))
        assert portfolio_weights(after).sum() == pytest.approx(1.0)


# ---------- intégration légère avec la gouvernance ----------

def test_robert_tsla_pro_rata_is_flagged_by_governance(robert, robert_profile):
    after = apply_idea(robert, _idea("TSLA", 0.25))
    snapshot = build_snapshot(after, "portfolio_after")
    result = governance.evaluate(robert_profile, snapshot)
    assert result["overall_status"] == "conflict"
    r1 = next(check for check in result["checks"] if check["rule_id"] == "R1")
    assert r1["status"] == "conflict", "25 % dans TSLA doit être un conflit de concentration (R1)"
    assert r1["value"] == pytest.approx(0.25)


# --- Ajouts après relecture de code -------------------------------------------

def _robert_portfolio():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "data" / "external" / "investor_profiles.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["personas"]["robert"]["portfolio"]


def test_idee_incomplete_erreur_claire():
    """Une idée sans champ obligatoire lève PortfolioError, pas KeyError."""
    with pytest.raises(PortfolioError, match="champs manquants"):
        apply_idea(_robert_portfolio(), {"ticker": "TSLA", "target_weight": 0.25})


@pytest.mark.parametrize("bad", [True, "0.2", None])
def test_poids_vise_non_numerique_refuse(bad):
    """Un booléen ou une chaîne n'est pas accepté comme poids visé."""
    with pytest.raises(PortfolioError, match="nombre"):
        apply_idea(_robert_portfolio(), {"ticker": "TSLA", "target_weight": bad,
                                         "funding_source": "pro_rata", "funding_ticker": None})


def test_poids_de_position_non_numerique_refuse():
    """Un poids de position en chaîne ou booléen est refusé."""
    from alphaforge.portfolio import portfolio_weights

    with pytest.raises(PortfolioError, match="nombre"):
        portfolio_weights({"positions": [{"ticker": "SPY", "weight": "1.0"}]})
    with pytest.raises(PortfolioError):
        portfolio_weights({"positions": [{"ticker": "SPY"}]})


def test_suffixe_distingue_les_variantes():
    """Le suffixe nomme le portefeuille résultant (trace et interface)."""
    result = apply_idea(_robert_portfolio(), {"ticker": "TSLA", "target_weight": 0.1,
                                              "funding_source": "pro_rata", "funding_ticker": None},
                        suffix="variant:V1", label_fr="Variante 1")
    assert result["portfolio_id"] == "portfolio_robert:variant:V1"
    assert result["label_fr"] == "Variante 1"


def test_snapshot_et_metriques_coherents():
    """La radiographie et les métriques renvoyées ensemble concordent."""
    from alphaforge.portfolio import build_snapshot, build_snapshot_with_metrics

    snapshot, metrics = build_snapshot_with_metrics(_robert_portfolio(), "portfolio_before")
    assert snapshot == build_snapshot(_robert_portfolio(), "portfolio_before")
    assert snapshot["max_drawdown"] == metrics.max_drawdown
    assert snapshot["volatility_ann"] == metrics.volatility_ann
    assert metrics.period_start == "2021-11-12"
    assert metrics.n_observations == 1227


def test_max_feasible_target():
    """Borne du poids visé selon la source des fonds."""
    from alphaforge.portfolio import max_feasible_target

    robert = _robert_portfolio()
    assert max_feasible_target(robert, {"ticker": "TSLA", "funding_source": "pro_rata"}) == 1.0
    bound = max_feasible_target(robert, {"ticker": "TSLA", "funding_source": "from_ticker",
                                         "funding_ticker": "GLD"})
    assert bound == 0.1
    apply_idea(robert, {"ticker": "TSLA", "target_weight": bound, "funding_source": "from_ticker",
                        "funding_ticker": "GLD"})


def test_poids_publies_sans_bruit_flottant():
    """Les poids publiés sont arrondis : pas de 0.19999999999999996."""
    from alphaforge.portfolio import build_snapshot

    after = apply_idea(_robert_portfolio(), {"ticker": "TSLA", "target_weight": 0.25,
                                             "funding_source": "pro_rata", "funding_ticker": None})
    snapshot = build_snapshot(after, "portfolio_after")
    for value in list(snapshot["weights"].values()) + list(snapshot["weight_by_asset_class"].values()):
        assert value == round(value, 10)
