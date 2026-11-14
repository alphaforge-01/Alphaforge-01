"""Tests de l'alignement des calendriers (données synthétiques, calculables à la main)."""

import pandas as pd
import pytest

from alphaforge.calendar_alignment import (
    MissingPriceError,
    common_trading_calendar,
    pivot_on_calendar,
)


def _prices(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime([r[0] for r in rows]),
            "ticker": [r[1] for r in rows],
            "adj_close": [r[2] for r in rows],
            "close": [r[2] * 10 for r in rows],
        }
    )


def _cal(*days: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(days)), name="date")


def test_common_calendar_is_intersection_of_reference_dates():
    prices = _prices(
        [
            ("2024-07-01", "RY.TO", 1.0),  # Fête du Canada : seulement le TSX
            ("2024-07-02", "RY.TO", 1.0),
            ("2024-07-03", "RY.TO", 1.0),
            ("2024-07-02", "AAPL", 1.0),
            ("2024-07-03", "AAPL", 1.0),
            ("2024-07-04", "AAPL", 1.0),  # Fête nationale US : seulement les marchés US
        ]
    )
    cal = common_trading_calendar(prices, ["RY.TO", "AAPL"])
    assert list(cal) == list(pd.to_datetime(["2024-07-02", "2024-07-03"]))


def test_common_calendar_is_sorted():
    prices = _prices([("2024-01-03", "A", 1.0), ("2024-01-02", "A", 1.0)])
    assert common_trading_calendar(prices, ["A"]).is_monotonic_increasing


def test_common_calendar_empty_references_raises():
    with pytest.raises(ValueError):
        common_trading_calendar(_prices([("2024-01-02", "A", 1.0)]), [])


def test_common_calendar_ticker_without_price_raises():
    with pytest.raises(MissingPriceError):
        common_trading_calendar(_prices([("2024-01-02", "A", 1.0)]), ["A", "B"])


def test_pivot_has_calendar_rows_and_requested_columns():
    prices = _prices(
        [
            ("2024-01-02", "A", 1.0),
            ("2024-01-02", "B", 2.0),
            ("2024-01-03", "A", 3.0),
            ("2024-01-03", "B", 4.0),
        ]
    )
    wide = pivot_on_calendar(prices, _cal("2024-01-02", "2024-01-03"), ["B", "A"])
    assert list(wide.columns) == ["B", "A"], "L'ordre des colonnes demandé doit être respecté"
    assert wide.loc["2024-01-03", "A"] == 3.0


def test_pivot_uses_adj_close_by_default():
    prices = _prices([("2024-01-02", "A", 1.0)])
    cal = _cal("2024-01-02")
    assert pivot_on_calendar(prices, cal, ["A"]).iloc[0, 0] == 1.0
    assert pivot_on_calendar(prices, cal, ["A"], column="close").iloc[0, 0] == 10.0


def test_pivot_drops_dates_outside_calendar():
    prices = _prices([("2024-01-02", "A", 1.0), ("2024-01-03", "A", 2.0)])
    wide = pivot_on_calendar(prices, _cal("2024-01-03"), ["A"])
    assert len(wide) == 1 and wide.iloc[0, 0] == 2.0


def test_pivot_missing_price_raises_instead_of_filling():
    prices = _prices([("2024-01-02", "A", 1.0), ("2024-01-03", "A", 2.0), ("2024-01-02", "B", 5.0)])
    with pytest.raises(MissingPriceError, match="B"):
        pivot_on_calendar(prices, _cal("2024-01-02", "2024-01-03"), ["A", "B"])


def test_pivot_unknown_ticker_raises_missing_price():
    prices = _prices([("2024-01-02", "A", 1.0)])
    with pytest.raises(MissingPriceError):
        pivot_on_calendar(prices, _cal("2024-01-02"), ["A", "ZZZ"])


def test_weekend_crypto_moves_accumulate_into_monday_return():
    # Vendredi 100, samedi 110, dimanche 120, lundi 132 : calendrier vendredi/lundi.
    prices = _prices(
        [
            ("2024-01-05", "BTC-USD", 100.0),
            ("2024-01-06", "BTC-USD", 110.0),
            ("2024-01-07", "BTC-USD", 120.0),
            ("2024-01-08", "BTC-USD", 132.0),
        ]
    )
    wide = pivot_on_calendar(prices, _cal("2024-01-05", "2024-01-08"), ["BTC-USD"])
    returns = wide.pct_change().iloc[1:]
    assert returns.loc["2024-01-08", "BTC-USD"] == pytest.approx(0.32), "132/100 - 1 = 0.32"
