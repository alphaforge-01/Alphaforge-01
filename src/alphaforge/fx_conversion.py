"""Conversion des prix en dollars canadiens (devise de référence du projet).

Convention retenue par l'équipe : taux du même jour. Le prix de clôture d'un
titre américain à la date D est converti avec le taux USD/CAD publié par la
Banque du Canada à la date D (vers 16 h 30, heure de l'Est). Les jours sans
taux publié (jours fériés de la Banque du Canada), on reprend le dernier taux
connu, au plus `MAX_FX_CARRY_DAYS` jours civils. On ne prend jamais un taux
postérieur.
"""

from __future__ import annotations

import pandas as pd

BASE_CURRENCY = "CAD"
SUPPORTED_CURRENCIES = {"CAD", "USD"}
# Un jour férié prolongé par un week-end donne au plus 4 jours sans taux publié
MAX_FX_CARRY_DAYS = 4


class MissingFxRateError(ValueError):
    """Aucun taux de change connu à une date demandée."""


def usdcad_on_calendar(fx: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.Series:
    """Taux USD/CAD pour chaque date du calendrier, reporté depuis le dernier jour publié.

    `fx` est le résultat de `load_fx` (colonnes `date` et `usdcad`).
    Lève `MissingFxRateError` si une date du calendrier précède le premier taux
    disponible, ou si le dernier taux connu date de plus de `MAX_FX_CARRY_DAYS` jours.
    """
    rates = fx.set_index("date")["usdcad"].sort_index()
    if rates.index.has_duplicates:
        raise ValueError("Plusieurs taux de change pour une même date")
    combined = rates.reindex(rates.index.union(calendar)).ffill()
    result = combined.reindex(calendar)
    missing = result.index[result.isna()]
    if len(missing) > 0:
        raise MissingFxRateError(
            f"Aucun taux USD/CAD connu au {missing[0].date()} ou avant"
        )
    published_on = pd.Series(rates.index, index=rates.index)
    last_published = published_on.reindex(rates.index.union(calendar)).ffill().reindex(calendar)
    carry_days = (calendar - pd.DatetimeIndex(last_published)).days
    too_old = calendar[carry_days > MAX_FX_CARRY_DAYS]
    if len(too_old) > 0:
        raise MissingFxRateError(
            f"Dernier taux USD/CAD trop ancien au {too_old[0].date()} "
            f"(plus de {MAX_FX_CARRY_DAYS} jours sans publication)"
        )
    result.name = "usdcad"
    return result


def fx_filled_dates(fx: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Dates du calendrier pour lesquelles le taux a été reporté d'un jour précédent."""
    published = pd.DatetimeIndex(fx["date"])
    return calendar.difference(published)


def convert_prices_to_cad(
    prices: pd.DataFrame,
    currencies: dict[str, str],
    usdcad: pd.Series,
) -> pd.DataFrame:
    """Convertit une matrice de prix (dates en lignes, tickers en colonnes) en CAD.

    Les colonnes en CAD sont inchangées ; les colonnes en USD sont multipliées
    par le taux USD/CAD de la même date.
    """
    if not prices.index.equals(usdcad.index):
        raise ValueError("Les dates des prix et des taux de change ne correspondent pas")
    converted = prices.copy()
    for ticker in prices.columns:
        currency = currencies.get(ticker)
        if currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Devise non prise en charge pour {ticker} : {currency}")
        if currency == "USD":
            converted[ticker] = prices[ticker] * usdcad
    return converted
