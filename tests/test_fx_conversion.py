"""Tests de la conversion en CAD (taux du même jour, report du dernier taux connu)."""

from datetime import timedelta
import pandas as pd
import pytest

from alphaforge.fx_conversion import (
    MissingFxRateError,
    convert_prices_to_cad,
    fx_filled_dates,
    usdcad_on_calendar,
)


def _fx(rows: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(list(rows)), "usdcad": list(rows.values())})


def _calendar(*days: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(days)), name="date")


def test_same_day_rate_is_used_when_published():
    fx = _fx({"2024-01-02": 1.30, "2024-01-03": 1.40})
    rates = usdcad_on_calendar(fx, _calendar("2024-01-02", "2024-01-03"))
    assert rates.tolist() == [1.30, 1.40], "Le taux du même jour doit être utilisé"


def test_holiday_gap_is_filled_from_previous_day_not_next():
    # Pas de taux le 2024-01-02 (férié) : on reprend celui du 01, jamais celui du 03.
    fx = _fx({"2024-01-01": 1.10, "2024-01-03": 9.99})
    rates = usdcad_on_calendar(fx, _calendar("2024-01-01", "2024-01-02", "2024-01-03"))
    assert rates.loc["2024-01-02"] == 1.10, "Le trou doit être comblé par le taux précédent"
    assert rates.loc["2024-01-03"] == 9.99


def test_no_backfill_before_first_rate_raises():
    fx = _fx({"2024-01-03": 1.30})
    with pytest.raises(MissingFxRateError):
        usdcad_on_calendar(fx, _calendar("2024-01-02", "2024-01-03"))


def test_missing_fx_error_is_a_value_error():
    assert issubclass(MissingFxRateError, ValueError)


def test_duplicate_fx_dates_raise():
    fx = _fx({"2024-01-02": 1.30})
    fx = pd.concat([fx, fx], ignore_index=True)
    with pytest.raises(ValueError):
        usdcad_on_calendar(fx, _calendar("2024-01-02"))


def test_unsorted_fx_input_is_handled():
    fx = _fx({"2024-01-03": 1.40, "2024-01-01": 1.10})
    rates = usdcad_on_calendar(fx, _calendar("2024-01-02"))
    assert rates.iloc[0] == 1.10, "Le résultat ne doit pas dépendre de l'ordre d'entrée"


def test_rate_series_is_indexed_on_calendar_and_named():
    cal = _calendar("2024-01-01", "2024-01-02")
    rates = usdcad_on_calendar(_fx({"2024-01-01": 1.2}), cal)
    assert rates.index.equals(cal)
    assert rates.name == "usdcad"


def test_fx_dates_outside_calendar_add_no_rows():
    fx = _fx({"2024-01-01": 1.2, "2024-01-02": 1.3, "2024-01-03": 1.4})
    rates = usdcad_on_calendar(fx, _calendar("2024-01-01", "2024-01-03"))
    assert len(rates) == 2


def test_fx_filled_dates_lists_only_carried_forward_days():
    fx = _fx({"2024-01-01": 1.1, "2024-01-03": 1.2})
    cal = _calendar("2024-01-01", "2024-01-02", "2024-01-03")
    filled = fx_filled_dates(fx, cal)
    assert list(filled) == [pd.Timestamp("2024-01-02")]


def test_fx_filled_dates_empty_when_all_published():
    fx = _fx({"2024-01-01": 1.1, "2024-01-02": 1.2})
    assert len(fx_filled_dates(fx, _calendar("2024-01-01", "2024-01-02"))) == 0


def test_usd_price_is_multiplied_by_usdcad():
    cal = _calendar("2024-01-02")
    prices = pd.DataFrame({"AAPL": [100.0]}, index=cal)
    usdcad = pd.Series([1.25], index=cal)
    result = convert_prices_to_cad(prices, {"AAPL": "USD"}, usdcad)
    assert result.loc["2024-01-02", "AAPL"] == pytest.approx(125.0), "100 USD x 1.25 = 125 CAD"


def test_cad_price_is_unchanged():
    cal = _calendar("2024-01-02")
    prices = pd.DataFrame({"RY.TO": [100.0]}, index=cal)
    usdcad = pd.Series([1.25], index=cal)
    result = convert_prices_to_cad(prices, {"RY.TO": "CAD"}, usdcad)
    assert result.loc["2024-01-02", "RY.TO"] == 100.0, "Un prix en CAD ne doit pas être converti"


def test_mixed_columns_each_use_their_own_currency():
    cal = _calendar("2024-01-02", "2024-01-03")
    prices = pd.DataFrame({"AAPL": [100.0, 200.0], "RY.TO": [50.0, 60.0]}, index=cal)
    usdcad = pd.Series([1.25, 1.5], index=cal)
    result = convert_prices_to_cad(prices, {"AAPL": "USD", "RY.TO": "CAD"}, usdcad)
    assert result["AAPL"].tolist() == pytest.approx([125.0, 300.0])
    assert result["RY.TO"].tolist() == [50.0, 60.0]


def test_conversion_leaves_input_untouched():
    cal = _calendar("2024-01-02")
    prices = pd.DataFrame({"AAPL": [100.0]}, index=cal)
    usdcad = pd.Series([2.0], index=cal)
    result = convert_prices_to_cad(prices, {"AAPL": "USD"}, usdcad)
    result.iloc[0, 0] = -1.0
    assert prices.loc["2024-01-02", "AAPL"] == 100.0, "L'entrée ne doit pas être modifiée"


def test_unsupported_currency_raises():
    cal = _calendar("2024-01-02")
    prices = pd.DataFrame({"X": [1.0]}, index=cal)
    with pytest.raises(ValueError, match="Devise"):
        convert_prices_to_cad(prices, {"X": "EUR"}, pd.Series([1.25], index=cal))


def test_unknown_ticker_currency_raises():
    cal = _calendar("2024-01-02")
    prices = pd.DataFrame({"X": [1.0]}, index=cal)
    with pytest.raises(ValueError):
        convert_prices_to_cad(prices, {}, pd.Series([1.25], index=cal))


def test_mismatched_dates_raise():
    prices = pd.DataFrame({"AAPL": [100.0]}, index=_calendar("2024-01-02"))
    usdcad = pd.Series([1.25], index=_calendar("2024-01-03"))
    with pytest.raises(ValueError):
        convert_prices_to_cad(prices, {"AAPL": "USD"}, usdcad)


def test_usdcad_on_calendar_refuse_un_taux_trop_ancien():
    """Au-delà de MAX_FX_CARRY_DAYS jours sans publication, on refuse de reporter le taux."""
    import pandas as pd
    import pytest

    from alphaforge.fx_conversion import MAX_FX_CARRY_DAYS, MissingFxRateError, usdcad_on_calendar

    fx = pd.DataFrame({"date": pd.to_datetime(["2024-01-01"]), "usdcad": [1.30]})
    ok_day = pd.Timestamp("2024-01-01") + timedelta(days=MAX_FX_CARRY_DAYS)
    assert usdcad_on_calendar(fx, pd.DatetimeIndex([ok_day])).iloc[0] == 1.30
    too_old = ok_day + timedelta(days=1)
    with pytest.raises(MissingFxRateError, match="trop ancien"):
        usdcad_on_calendar(fx, pd.DatetimeIndex([too_old]))
