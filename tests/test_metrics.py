"""Tests des métriques de rendement et de risque (séries synthétiques calculables à la main)."""

from datetime import timedelta
import math

import numpy as np
import pandas as pd
import pytest

from alphaforge.calendar_alignment import daily_cad_returns, returns_base_date
from alphaforge.metrics import (
    MIN_OBSERVATIONS_FOR_ANNUAL_RETURN,
    InsufficientDataError,
    annualized_return,
    annualized_volatility,
    compute_return_metrics,
    drawdown_series,
    max_drawdown,
    metrics_table,
    total_return,
    wealth_index,
)


def _series(values, start="2024-01-02"):
    """Série de rendements sur jours ouvrables consécutifs."""
    index = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=index, dtype=float)


def _from_levels(levels, dates):
    """Rendements simples déduits de niveaux datés (le premier niveau est la base)."""
    prices = pd.Series(levels, index=pd.to_datetime(list(dates)), dtype=float)
    return prices.pct_change().iloc[1:]


# Chemin 100 -> 120 -> 90 -> 130, avec un week-end entre le creux et la récupération.
LEVEL_DATES = ["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]


# ---------- rendement total et annualisé ----------

def test_total_return_known_values():
    assert total_return(_series([0.10, -0.10])) == pytest.approx(1.1 * 0.9 - 1, abs=1e-15)


def test_annualized_return_constant_252_days():
    r = 0.0005
    result = annualized_return(_series([r] * 252))
    assert result == pytest.approx((1 + r) ** 252 - 1, rel=1e-12), "252 rendements constants"


def test_annualized_return_uses_exponent_252_over_n():
    returns = _series([0.1, -0.1] * 126)  # n = 252
    growth = (1.1 * 0.9) ** 126
    assert annualized_return(returns) == pytest.approx(growth - 1, rel=1e-12)
    returns = _series([0.001] * 504)  # n = 504 : exposant 252 / 504
    assert annualized_return(returns) == pytest.approx(1.001 ** 252 - 1, rel=1e-12)


def test_annualized_return_custom_periods_per_year():
    returns = _series([0.001] * 252)
    assert annualized_return(returns, periods_per_year=126) == pytest.approx(1.001 ** 126 - 1, rel=1e-12)


def test_annualized_return_none_below_one_year():
    assert MIN_OBSERVATIONS_FOR_ANNUAL_RETURN == 252
    assert annualized_return(_series([0.001] * 251)) is None
    assert annualized_return(_series([0.001] * 252)) is not None


def test_annualized_return_two_day_case_is_none():
    assert annualized_return(_series([0.03, 0.03])) is None


# ---------- volatilité ----------

def test_volatility_constant_returns_is_zero():
    assert annualized_volatility(_series([0.01] * 10)) == pytest.approx(0.0, abs=1e-12)


def test_volatility_alternating_matches_hand_computation():
    a = 0.01
    # moyenne 0, variance échantillon = 4 a^2 / 3
    expected = a * math.sqrt(4 / 3) * math.sqrt(252)
    assert annualized_volatility(_series([a, -a, a, -a])) == pytest.approx(expected, rel=1e-12)


def test_volatility_uses_sample_std_ddof_1():
    returns = _series([0.02, 0.0])
    # ddof=1 : std = 0.02 / sqrt(2) ; ddof=0 donnerait 0.01
    expected = 0.02 / math.sqrt(2) * math.sqrt(252)
    assert annualized_volatility(returns) == pytest.approx(expected, rel=1e-12)


# ---------- indice de richesse ----------

def test_base_date_none_raises_value_error():
    returns = _series([0.1, 0.1], start="2024-01-03")
    for func in (wealth_index, drawdown_series, max_drawdown, compute_return_metrics):
        with pytest.raises(ValueError, match="obligatoire"):
            func(returns, None)
    with pytest.raises(ValueError, match="obligatoire"):
        metrics_table(returns.to_frame("AAA"), None)


def test_tz_aware_base_date_is_localized():
    returns = _series([0.1, 0.1], start="2024-01-03")
    wealth = wealth_index(returns, base_date=pd.Timestamp("2024-01-02", tz="America/Toronto"))
    assert wealth.index[0] == pd.Timestamp("2024-01-02")
    assert wealth.index.tz is None


def test_tz_aware_returns_index_raises_value_error():
    returns = _series([0.1, 0.1], start="2024-01-03")
    returns.index = returns.index.tz_localize("UTC")
    with pytest.raises(ValueError):
        total_return(returns)


def test_wealth_index_with_base_date_prepends_one():
    returns = _series([0.1, 0.1], start="2024-01-03")
    wealth = wealth_index(returns, base_date="2024-01-02")
    assert wealth.iloc[0] == 1.0
    assert wealth.index[0] == pd.Timestamp("2024-01-02")
    assert len(wealth) == 3


@pytest.mark.parametrize("base", ["2024-01-03", "2024-01-10"])
def test_wealth_index_base_date_not_before_first_return_raises(base):
    with pytest.raises(ValueError):
        wealth_index(_series([0.1, 0.1], start="2024-01-03"), base_date=base)


# ---------- perte maximale ----------

def test_max_drawdown_known_path_with_recovery():
    returns = _from_levels([100, 120, 90, 130], LEVEL_DATES)
    info = max_drawdown(returns, base_date="2024-01-03")
    assert info.max_drawdown == pytest.approx(0.25, abs=1e-12)
    assert info.peak_date == "2024-01-04"
    assert info.trough_date == "2024-01-05"
    assert info.recovery_date == "2024-01-08"
    assert info.recovered is True
    assert info.recovery_days == 3, "jours civils entre le creux (vendredi) et la récupération (lundi)"
    assert info.underwater_days == 4, "jours civils entre le sommet (jeudi) et la récupération (lundi)"


def test_max_drawdown_is_positive_fraction():
    returns = _from_levels([100, 120, 90, 130], LEVEL_DATES)
    assert max_drawdown(returns, base_date="2024-01-03").max_drawdown > 0


def test_max_drawdown_never_recovered():
    returns = _from_levels([100, 120, 90, 110], LEVEL_DATES)
    info = max_drawdown(returns, base_date="2024-01-03")
    assert info.max_drawdown == pytest.approx(0.25, abs=1e-12)
    assert info.recovered is False
    assert info.recovery_date is None
    assert info.recovery_days is None
    assert info.underwater_days == 4, "du sommet (2024-01-04) à la dernière date (2024-01-08)"


def test_max_drawdown_monotonic_rise_with_base_date():
    returns = _series([0.01, 0.01, 0.01], start="2024-01-03")
    info = max_drawdown(returns, base_date="2024-01-02")
    assert info.max_drawdown == 0.0
    assert info.peak_date == info.trough_date == info.recovery_date == "2024-01-02"
    assert info.recovered is True
    assert info.recovery_days == 0
    assert info.underwater_days == 0


def test_first_day_loss_is_captured_with_base_date():
    returns = _from_levels([100, 90, 95], ["2024-01-02", "2024-01-03", "2024-01-04"])
    info = max_drawdown(returns, base_date="2024-01-02")
    assert info.peak_date == "2024-01-02"
    assert info.trough_date == "2024-01-03"
    assert info.max_drawdown == pytest.approx(0.10, abs=1e-12)
    assert info.recovered is False
    assert info.underwater_days == 2


def test_max_drawdown_tie_picks_first_deepest_trough():
    # Niveaux 100, 50, 100, 50 : deux creux de même profondeur (valeurs exactes en binaire)
    returns = _from_levels(
        [100, 50, 100, 50], ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    )
    info = max_drawdown(returns, base_date="2024-01-02")
    assert info.max_drawdown == 0.5
    assert info.peak_date == "2024-01-02"
    assert info.trough_date == "2024-01-03", "le premier creux est retenu"
    assert info.recovery_date == "2024-01-04"


def test_recovery_requires_reaching_peak_level_inclusive():
    # 100 -> 50 -> 100 : la valeur retrouve exactement le sommet (>=)
    returns = _from_levels([100, 50, 100], ["2024-01-02", "2024-01-03", "2024-01-04"])
    info = max_drawdown(returns, base_date="2024-01-02")
    assert info.recovery_date == "2024-01-04"
    assert info.recovery_days == 1
    assert info.recovered is True
    # 100 -> 50 -> 90 : pas de récupération
    returns = _from_levels([100, 50, 90], ["2024-01-02", "2024-01-03", "2024-01-04"])
    assert max_drawdown(returns, base_date="2024-01-02").recovery_date is None


def test_recovery_tolerance_counts_level_within_relative_tolerance():
    # Niveau final 1 - 5e-13 : dans la tolérance de 1e-12, donc récupéré
    returns = pd.Series([-0.5, 1.0 - 1e-12], index=pd.bdate_range("2024-01-03", periods=2))
    wealth_end = float((1.0 + returns).prod())
    assert 0 < 1.0 - wealth_end < 1e-12
    info = max_drawdown(returns, base_date="2024-01-02")
    assert info.recovered is True
    assert info.recovery_date == "2024-01-04"
    # Niveau final 1 - 1e-6 : hors tolérance
    returns = pd.Series([-0.5, 1.0 - 2e-6], index=pd.bdate_range("2024-01-03", periods=2))
    assert max_drawdown(returns, base_date="2024-01-02").recovered is False


def test_max_drawdown_picks_deepest_of_several_drawdowns():
    levels = [100, 110, 99, 120, 60, 80]  # -10 % puis -50 %
    dates = pd.bdate_range("2024-01-02", periods=6)
    info = max_drawdown(_from_levels(levels, dates), base_date=dates[0])
    assert info.max_drawdown == pytest.approx(0.5, abs=1e-12)
    assert info.peak_date == dates[3].date().isoformat()
    assert info.trough_date == dates[4].date().isoformat()
    assert info.recovery_date is None


# ---------- série des baisses ----------

def test_drawdown_series_zero_at_peaks_positive_elsewhere():
    returns = _from_levels([100, 120, 90, 130], LEVEL_DATES)
    dd = drawdown_series(returns, base_date="2024-01-03")
    assert dd.loc["2024-01-03"] == 0.0
    assert dd.loc["2024-01-04"] == 0.0
    assert dd.loc["2024-01-05"] == pytest.approx(0.25, abs=1e-12)
    assert dd.loc["2024-01-08"] == 0.0
    assert (dd >= 0).all()


def test_drawdown_series_max_equals_max_drawdown():
    rng = np.random.default_rng(0)
    returns = _series(rng.normal(0, 0.01, 60))
    base = returns.index[0] - timedelta(days=1)
    assert drawdown_series(returns, base).max() == pytest.approx(
        max_drawdown(returns, base).max_drawdown, abs=1e-15
    )


# ---------- validation des entrées ----------

def test_non_series_raises_type_error():
    with pytest.raises(TypeError):
        total_return([0.1, 0.2])


def test_non_datetime_index_raises_type_error():
    with pytest.raises(TypeError):
        total_return(pd.Series([0.1, 0.2]))


def test_unsorted_dates_raise_value_error():
    series = pd.Series([0.1, 0.2], index=pd.to_datetime(["2024-01-03", "2024-01-02"]))
    with pytest.raises(ValueError):
        total_return(series)


def test_duplicate_dates_raise_value_error():
    series = pd.Series([0.1, 0.2], index=pd.to_datetime(["2024-01-02", "2024-01-02"]))
    with pytest.raises(ValueError):
        annualized_volatility(series)


@pytest.mark.parametrize("values", [[], [0.01]])
def test_fewer_than_two_returns_raise_insufficient_data(values):
    series = pd.Series(values, index=pd.bdate_range("2024-01-02", periods=len(values)), dtype=float)
    with pytest.raises(InsufficientDataError):
        annualized_return(series)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nan_or_inf_raise_value_error(bad):
    with pytest.raises(ValueError):
        total_return(_series([0.01, bad, 0.02]))


@pytest.mark.parametrize("bad", [-1.0, -1.5])
def test_return_at_or_below_minus_one_raises(bad):
    with pytest.raises(ValueError):
        max_drawdown(_series([0.01, bad]), base_date="2024-01-01")


def test_insufficient_data_is_a_value_error():
    assert issubclass(InsufficientDataError, ValueError)


# ---------- résumé et tableau ----------

def test_compute_return_metrics_fields_with_base_date():
    returns = _from_levels([100, 120, 90, 130], LEVEL_DATES)
    result = compute_return_metrics(returns, base_date="2024-01-03")
    assert result.period_start == "2024-01-03"
    assert result.period_end == "2024-01-08"
    assert result.n_observations == 3
    assert result.total_return == pytest.approx(0.30, abs=1e-12)
    assert result.return_ann is None, "moins de 252 rendements"
    assert result.volatility_ann == pytest.approx(annualized_volatility(returns), rel=1e-12)
    assert result.max_drawdown == pytest.approx(0.25, abs=1e-12)
    assert result.max_drawdown_start == "2024-01-04"
    assert result.max_drawdown_end == "2024-01-05"
    assert result.recovered is True
    assert result.recovery_date == "2024-01-08"
    assert result.recovery_days == 3
    assert result.underwater_days == 4


def test_compute_return_metrics_annual_return_with_one_year():
    result = compute_return_metrics(_series([0.0005] * 252, start="2024-01-03"), base_date="2024-01-02")
    assert result.return_ann == pytest.approx(1.0005 ** 252 - 1, rel=1e-12)


def test_compute_return_metrics_period_start_is_base_date():
    returns = _series([0.01, -0.02, 0.03], start="2024-01-03")
    result = compute_return_metrics(returns, base_date="2024-01-02")
    assert result.period_start == "2024-01-02"
    assert result.period_end == returns.index[-1].date().isoformat()


def test_return_metrics_to_dict_has_all_fields():
    result = compute_return_metrics(_series([0.01, -0.02, 0.03], start="2024-01-03"), "2024-01-02")
    assert set(result.to_dict()) == {
        "period_start", "period_end", "n_observations", "total_return", "return_ann",
        "volatility_ann", "max_drawdown", "max_drawdown_start", "max_drawdown_end",
        "recovered", "recovery_date", "recovery_days", "underwater_days",
    }


def test_metrics_table_one_row_per_column():
    frame = pd.DataFrame(
        {"AAA": [0.01, -0.02, 0.03], "BBB": [0.0, 0.01, -0.01]},
        index=pd.bdate_range("2024-01-03", periods=3),
    )
    table = metrics_table(frame, base_date="2024-01-02")
    assert list(table.index) == ["AAA", "BBB"]
    assert table.index.name == "ticker"
    assert table.loc["AAA", "total_return"] == pytest.approx(total_return(frame["AAA"]), rel=1e-12)
    assert (table["period_start"] == "2024-01-02").all()


def test_metrics_table_keeps_native_python_types():
    index = pd.bdate_range("2024-01-03", periods=3)
    frame = pd.DataFrame(
        {"REC": [-0.5, 1.0, 0.1], "UNREC": [-0.5, 0.2, 0.1]},  # REC retrouve son sommet
        index=index,
    )
    table = metrics_table(frame, base_date="2024-01-02")
    assert (table.dtypes == object).all(), "toutes les colonnes en type objet"
    rec, unrec = table.loc["REC"], table.loc["UNREC"]
    assert rec["recovered"] is True and unrec["recovered"] is False
    assert type(rec["recovery_days"]) is int and rec["recovery_days"] == 1
    assert unrec["recovery_days"] is None, "ni NaN ni float"
    assert unrec["recovery_date"] is None
    assert type(rec["underwater_days"]) is int and type(unrec["underwater_days"]) is int
    assert unrec["return_ann"] is None


# ---------- intégration sur les données réelles du dépôt ----------

def test_returns_base_date_precedes_first_return():
    base = returns_base_date()
    assert base == pd.Timestamp("2021-11-12")
    assert base < daily_cad_returns().index[0]


def test_tsla_max_drawdown_matches_price_levels():
    from alphaforge.calendar_alignment import aligned_cad_prices

    prices = aligned_cad_prices(tickers="TSLA")["TSLA"]
    returns = daily_cad_returns(tickers="TSLA")["TSLA"]
    info = max_drawdown(returns, base_date=returns_base_date())
    from_levels = float((1.0 - prices / prices.cummax()).max())
    assert info.max_drawdown == pytest.approx(from_levels, abs=1e-12)


def test_metrics_table_on_all_tickers_has_no_missing_value_except_recovery():
    returns = daily_cad_returns()
    table = metrics_table(returns, base_date=returns_base_date())
    assert len(table) == returns.shape[1] == 31
    others = table.drop(columns=["recovery_date", "recovery_days"])
    assert not others.isna().any().any(), "aucune valeur manquante hors récupération"
    assert (table["max_drawdown"] >= 0).all()
    assert (table["volatility_ann"] > 0).all()
    unrecovered = table[~table["recovered"].astype(bool)]
    assert unrecovered["recovery_days"].isna().all()
    assert unrecovered["recovery_date"].isna().all()
