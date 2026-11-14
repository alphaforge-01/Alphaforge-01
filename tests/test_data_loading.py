"""Tests du chargement et de l'alignement sur les vraies données (data/raw/, lecture seule)."""

from datetime import date

import pandas as pd
import pytest

from alphaforge import calendar_alignment as ca
from alphaforge import data_loading as dl


@pytest.fixture(scope="module")
def universe():
    return dl.load_universe()


# ---------- chargement ----------


def test_universe_has_31_assets(universe):
    assert len(universe) == 31
    assert universe["ticker"].is_unique


def test_each_non_crypto_asset_has_1255_rows_and_crypto_1827(universe):
    counts = dl.load_prices().groupby("ticker").size()
    crypto = set(dl.crypto_tickers())
    assert crypto, "Il doit y avoir au moins une crypto"
    for ticker in universe["ticker"]:
        expected = 1827 if ticker in crypto else 1255
        assert counts[ticker] == expected, f"Nombre de lignes inattendu pour {ticker}"


def test_currency_by_ticker_follows_suffix_rule():
    currencies = dl.currency_by_ticker()
    assert len(currencies) == 31
    for ticker, currency in currencies.items():
        assert currency == ("CAD" if ticker.endswith(".TO") else "USD"), ticker


def test_usdcad_is_cad_per_usd():
    fx = dl.load_fx()
    assert fx["usdcad"].between(1.2, 1.5).all(), "usdcad doit valoir entre 1,2 et 1,5 CAD par USD"
    assert fx["date"].is_unique


def test_prices_as_of_never_returns_later_rows():
    prices = dl.load_prices(as_of="2023-06-30")
    assert prices["date"].max() <= pd.Timestamp("2023-06-30")
    assert prices["date"].max() > pd.Timestamp("2023-06-01")


def test_as_of_accepts_str_date_and_timestamp():
    a = dl.load_prices(as_of="2023-06-30")
    b = dl.load_prices(as_of=date(2023, 6, 30))
    c = dl.load_prices(as_of=pd.Timestamp("2023-06-30 15:00"))
    assert len(a) == len(b) == len(c), "Les formats de date doivent être équivalents"


def test_as_of_is_inclusive():
    prices = dl.load_prices(as_of="2023-06-30", tickers=["AAPL"])
    assert prices["date"].max() == pd.Timestamp("2023-06-30")


def test_fx_as_of_filters():
    fx = dl.load_fx(as_of="2022-01-31")
    assert fx["date"].max() <= pd.Timestamp("2022-01-31")


def test_load_prices_ticker_filter():
    prices = dl.load_prices(tickers=["AAPL", "RY.TO"])
    assert set(prices["ticker"]) == {"AAPL", "RY.TO"}


def test_unknown_ticker_raises_value_error():
    with pytest.raises(ValueError, match="ZZZZ"):
        dl.load_prices(tickers=["AAPL", "ZZZZ"])


def test_adj_close_is_positive_and_present():
    prices = dl.load_prices()
    assert (prices["adj_close"] > 0).all()
    assert not prices["adj_close"].isna().any()


def test_prices_are_copies():
    first = dl.load_prices(tickers=["AAPL"])
    first.loc[:, "adj_close"] = -1.0
    second = dl.load_prices(tickers=["AAPL"])
    assert (second["adj_close"] > 0).all(), "Modifier un résultat ne doit pas affecter l'appel suivant"


def test_fx_universe_and_sources_are_copies():
    fx = dl.load_fx()
    fx.loc[:, "usdcad"] = 0.0
    assert (dl.load_fx()["usdcad"] > 1).all()
    first_ticker = dl.load_universe()["ticker"].iloc[0]
    uni = dl.load_universe()
    uni.loc[:, "ticker"] = "X"
    assert dl.load_universe()["ticker"].iloc[0] == first_ticker
    src = dl.load_sources_metadata()
    n_rows = len(src)
    assert n_rows > 0
    src.loc[:, src.columns[0]] = "modifie"
    assert (dl.load_sources_metadata().iloc[:, 0] != "modifie").all()


def test_crypto_tickers_are_marked_in_universe(universe):
    expected = universe.loc[universe["asset_class"] == "crypto", "ticker"].tolist()
    assert dl.crypto_tickers() == expected


# ---------- intégration : alignement sur les vraies données ----------


def test_alignment_summary_real_numbers():
    s = ca.alignment_summary()
    assert s["n_days"] == 1228
    assert s["calendar_start"] == "2021-11-12"
    assert s["calendar_end"] == "2026-11-12"
    assert s["n_tsx_only_days_dropped"] == 27
    assert s["n_us_only_days_dropped"] == 27
    assert s["n_fx_days_carried_forward"] == 10
    assert s["base_currency"] == "CAD"
    assert s["price_column"] == "adj_close"


def test_aligned_prices_cover_all_assets_without_gaps():
    prices = ca.aligned_cad_prices()
    assert prices.shape == (1228, 31)
    assert not prices.isna().any().any()
    assert (prices > 0).all().all()


def test_returns_drop_first_date_and_have_no_nan():
    prices = ca.aligned_cad_prices()
    returns = ca.daily_cad_returns()
    assert len(returns) == len(prices) - 1
    assert returns.index[0] == prices.index[1], "La première date du calendrier est retirée"
    assert not returns.isna().any().any()


def test_returns_for_usd_asset_are_simple_pct_change_in_cad():
    # Rendement attendu recalculé à la main : adj_close x usdcad du même jour (report si absent).
    raw = dl.load_prices(tickers=["AAPL"]).set_index("date")["adj_close"]
    fx = dl.load_fx().set_index("date")["usdcad"]
    cal = ca.aligned_cad_prices(tickers=["AAPL"]).index
    rate = fx.reindex(fx.index.union(cal)).ffill().reindex(cal)
    expected = (raw.reindex(cal) * rate).pct_change().iloc[1:]
    actual = ca.daily_cad_returns(tickers=["AAPL"])["AAPL"]
    pd.testing.assert_series_equal(actual, expected, check_names=False, check_freq=False)


def test_cad_asset_is_not_converted():
    raw = dl.load_prices(tickers=["RY.TO"]).set_index("date")["adj_close"]
    aligned = ca.aligned_cad_prices(tickers=["RY.TO"])["RY.TO"]
    pd.testing.assert_series_equal(aligned, raw.reindex(aligned.index), check_names=False, check_freq=False)


def test_crypto_is_brought_onto_the_common_calendar():
    btc = dl.crypto_tickers()[0]
    prices = ca.aligned_cad_prices(tickers=[btc])
    assert len(prices) == 1228
    gaps = prices.index.to_series().diff().dt.days
    assert gaps.max() >= 3, "Le week-end est absent du calendrier : les mouvements s'accumulent"


def test_as_of_invariance_of_returns():
    cutoff = pd.Timestamp("2024-03-15")
    truncated = ca.daily_cad_returns(as_of=cutoff)
    full = ca.daily_cad_returns().loc[:cutoff]
    pd.testing.assert_frame_equal(truncated, full, check_freq=False)
    assert truncated.index.max() <= cutoff


def test_as_of_invariance_of_prices_on_non_trading_day():
    cutoff = pd.Timestamp("2024-03-16")  # un samedi
    truncated = ca.aligned_cad_prices(as_of=cutoff)
    full = ca.aligned_cad_prices().loc[:cutoff]
    pd.testing.assert_frame_equal(truncated, full, check_freq=False)
    assert truncated.index.max() <= cutoff


def test_alignment_summary_respects_as_of():
    s = ca.alignment_summary(as_of="2023-12-31")
    assert s["calendar_end"] <= "2023-12-31"


def test_unknown_ticker_in_aligned_prices_and_returns_raises():
    with pytest.raises(ValueError):
        ca.aligned_cad_prices(tickers=["ZZZZ"])
    with pytest.raises(ValueError):
        ca.daily_cad_returns(tickers=["ZZZZ"])


def test_aligned_results_are_copies_of_the_cache():
    first = ca.aligned_cad_prices(as_of="2023-06-30")
    first.iloc[:, :] = 0.0
    second = ca.aligned_cad_prices(as_of="2023-06-30")
    assert (second > 0).all().all(), "Le cache ne doit pas être modifié par l'appelant"
    r1 = ca.daily_cad_returns(as_of="2023-06-30")
    r1.iloc[:, :] = 99.0
    assert (ca.daily_cad_returns(as_of="2023-06-30") < 99).all().all()


def test_ticker_subset_matches_full_matrix_columns():
    subset = ca.daily_cad_returns(tickers=["AAPL", "RY.TO"])
    full = ca.daily_cad_returns()[["AAPL", "RY.TO"]]
    pd.testing.assert_frame_equal(subset, full, check_freq=False)


def test_as_of_avec_fuseau_horaire_accepte():
    """Une date avec fuseau horaire donne le même résultat que la date simple."""
    import pandas as pd

    from alphaforge.data_loading import load_prices

    aware = load_prices(as_of=pd.Timestamp("2023-01-03", tz="UTC"), tickers=["AAPL"])
    naive = load_prices(as_of="2023-01-03", tickers=["AAPL"])
    assert aware.equals(naive)


def test_ticker_seul_en_chaine_accepte():
    """Un ticker passé comme chaîne n'est pas découpé en lettres."""
    from alphaforge.calendar_alignment import daily_cad_returns
    from alphaforge.data_loading import load_prices

    assert set(load_prices(tickers="AAPL")["ticker"]) == {"AAPL"}
    assert list(daily_cad_returns(tickers="AAPL").columns) == ["AAPL"]


def test_as_of_avant_les_donnees_message_clair():
    """Une date antérieure aux données lève une erreur explicite."""
    import pytest

    from alphaforge.calendar_alignment import aligned_cad_prices, daily_cad_returns

    with pytest.raises(ValueError, match="Aucune donnée"):
        aligned_cad_prices(as_of="2020-01-01")
    with pytest.raises(ValueError, match="Moins de deux dates"):
        daily_cad_returns(as_of="2021-11-12")


def test_clear_caches_puis_relecture_identique():
    """Vider les caches puis relire donne les mêmes rendements."""
    from alphaforge.calendar_alignment import clear_caches, daily_cad_returns

    before = daily_cad_returns(as_of="2022-06-30")
    clear_caches()
    assert daily_cad_returns(as_of="2022-06-30").equals(before)
