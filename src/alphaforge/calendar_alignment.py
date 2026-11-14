"""Alignement des calendriers et matrice de rendements quotidiens en CAD.

Conventions retenues par l'équipe :

- Calendrier commun : seulement les jours où **tous** les actifs hors crypto
  (actions et FNB, TSX et marchés américains) ont un prix. Les jours ouverts
  sur un seul marché sont écartés : aucun prix n'est inventé.
- Crypto : ramenée à ce calendrier. On prend le prix de la journée UTC de même
  date ; les mouvements du week-end et des jours fériés s'accumulent donc dans
  le rendement du jour ouvrable suivant.
- Rendements : rendements simples à partir de `adj_close` (dividendes et
  fractionnements déjà inclus), après conversion en CAD au taux du même jour.
  Les mouvements des jours écartés (ouverts sur un seul marché) ne sont pas
  perdus : ils s'ajoutent au rendement du jour commun suivant. L'écart entre
  deux dates communes consécutives va jusqu'à 6 jours.

Décalage horaire à documenter : la journée crypto UTC de date D se termine à
minuit UTC, soit vers 19 h ou 20 h (heure de l'Est) le jour D, après la clôture
américaine (16 h) et le taux de la Banque du Canada (16 h 30). Ce n'est pas une
fuite d'information à la résolution quotidienne, mais cela touche légèrement
les corrélations entre crypto et actions.

Attention aux niveaux de prix : `adj_close` est rétro-ajusté depuis la date de
téléchargement (2026). Un niveau à une date passée intègre donc les dividendes
et fractionnements postérieurs. Seuls les rapports entre deux valeurs
(rendements, variations, pertes maximales) sont valides à une date `as_of`.
Ne jamais afficher ni utiliser ces niveaux comme des prix observés.

Le calendrier est toujours calculé sur l'ensemble de l'univers hors crypto,
quel que soit le portefeuille, pour que les chiffres d'un même actif soient
identiques d'une analyse à l'autre.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from alphaforge.data_loading import (
    AsOf,
    clear_caches as clear_raw_caches,
    crypto_tickers,
    currency_by_ticker,
    load_fx,
    load_prices,
    load_universe,
    normalize_tickers,
    parse_as_of,
)
from alphaforge.fx_conversion import (
    BASE_CURRENCY,
    MAX_FX_CARRY_DAYS,
    convert_prices_to_cad,
    fx_filled_dates,
    usdcad_on_calendar,
)

PRICE_COLUMN = "adj_close"


class MissingPriceError(ValueError):
    """Un actif n'a pas de prix à une date du calendrier commun."""


def common_trading_calendar(prices: pd.DataFrame, reference_tickers: list[str]) -> pd.DatetimeIndex:
    """Dates où chacun des `reference_tickers` a un prix (intersection des calendriers)."""
    if not reference_tickers:
        raise ValueError("Aucun actif de référence pour construire le calendrier")
    calendar: pd.DatetimeIndex | None = None
    for ticker in reference_tickers:
        dates = pd.DatetimeIndex(prices.loc[prices["ticker"] == ticker, "date"])
        if dates.empty:
            raise MissingPriceError(f"Aucun prix pour {ticker}")
        calendar = dates if calendar is None else calendar.intersection(dates)
    return calendar.sort_values().rename("date")


def pivot_on_calendar(
    prices: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    tickers: list[str],
    column: str = PRICE_COLUMN,
) -> pd.DataFrame:
    """Matrice des prix (dates du calendrier en lignes, tickers en colonnes).

    Lève `MissingPriceError` si un actif n'a pas de prix à une date du
    calendrier : on ne bouche jamais un trou par un prix inventé.
    """
    subset = prices.loc[prices["ticker"].isin(tickers)]
    wide = subset.pivot(index="date", columns="ticker", values=column)
    wide = wide.reindex(index=calendar, columns=tickers)
    if wide.isna().any().any():
        ticker = wide.columns[wide.isna().any()][0]
        first_gap = wide.index[wide[ticker].isna()][0]
        raise MissingPriceError(f"Prix manquant pour {ticker} au {first_gap.date()}")
    wide.columns.name = "ticker"
    return wide


def _reference_tickers() -> list[str]:
    universe = load_universe()
    return universe.loc[universe["asset_class"] != "crypto", "ticker"].tolist()


@lru_cache(maxsize=8)
def _aligned_cad_prices_cached(cutoff: pd.Timestamp | None) -> pd.DataFrame:
    prices = load_prices(as_of=cutoff)
    if prices.empty:
        first = load_prices()["date"].min().date()
        raise ValueError(f"Aucune donnée au {cutoff.date()} ou avant (début des données : {first})")
    calendar = common_trading_calendar(prices, _reference_tickers())
    tickers = load_universe()["ticker"].tolist()
    local = pivot_on_calendar(prices, calendar, tickers)
    usdcad = usdcad_on_calendar(load_fx(as_of=cutoff), calendar)
    return convert_prices_to_cad(local, currency_by_ticker(), usdcad)


def clear_caches() -> None:
    """Vide les caches de lecture et d'alignement (si les fichiers de data/raw/ changent)."""
    clear_raw_caches()
    _aligned_cad_prices_cached.cache_clear()


def aligned_cad_prices(as_of: AsOf = None, tickers: str | list[str] | None = None) -> pd.DataFrame:
    """Prix ajustés (`adj_close`) en CAD sur le calendrier commun, jusqu'à `as_of` inclus.

    Ces niveaux servent uniquement à calculer des rapports (rendements, pertes
    maximales) : voir l'avertissement sur les niveaux en tête du module.
    """
    tickers = normalize_tickers(tickers)
    prices = _aligned_cad_prices_cached(parse_as_of(as_of))
    if tickers is not None:
        unknown = sorted(set(tickers) - set(prices.columns))
        if unknown:
            raise ValueError(f"Tickers absents de l'univers : {unknown}")
        prices = prices[tickers]
    return prices.copy()


def returns_base_date(as_of: AsOf = None) -> pd.Timestamp:
    """Date de la valeur de départ des rendements : la première date du calendrier commun.

    `daily_cad_returns` retire cette date (elle n'a pas de rendement) : il faut
    la passer à `metrics` comme `base_date` pour ne pas ignorer une baisse dès
    le premier jour.
    """
    return _aligned_cad_prices_cached(parse_as_of(as_of)).index[0]


def daily_cad_returns(as_of: AsOf = None, tickers: str | list[str] | None = None) -> pd.DataFrame:
    """Rendements simples quotidiens en CAD sur le calendrier commun.

    La première date du calendrier n'a pas de rendement et est retirée.
    Lève `ValueError` s'il y a moins de deux dates (aucun rendement calculable).
    """
    prices = aligned_cad_prices(as_of=as_of, tickers=tickers)
    if len(prices) < 2:
        raise ValueError("Moins de deux dates disponibles : aucun rendement calculable")
    return prices.pct_change().iloc[1:]


def alignment_summary(as_of: AsOf = None) -> dict:
    """Description de l'alignement, pour la traçabilité et les limites affichées."""
    cutoff = parse_as_of(as_of)
    prices = load_prices(as_of=cutoff)
    reference = _reference_tickers()
    calendar = common_trading_calendar(prices, reference)
    universe = load_universe()
    non_crypto = universe.loc[universe["asset_class"] != "crypto"]
    tsx_tickers = non_crypto.loc[non_crypto["market"] == "TSX", "ticker"].tolist()
    us_tickers = non_crypto.loc[non_crypto["market"] != "TSX", "ticker"].tolist()
    tsx_calendar = common_trading_calendar(prices, tsx_tickers)
    us_calendar = common_trading_calendar(prices, us_tickers)
    fx = load_fx(as_of=cutoff)
    return {
        "calendar_start": calendar[0].date().isoformat(),
        "calendar_end": calendar[-1].date().isoformat(),
        "n_days": len(calendar),
        "n_return_days": len(calendar) - 1,
        "n_tsx_only_days_dropped": len(tsx_calendar.difference(us_calendar)),
        "n_us_only_days_dropped": len(us_calendar.difference(tsx_calendar)),
        "n_fx_days_carried_forward": len(fx_filled_dates(fx, calendar)),
        "fx_source": "Banque du Canada, série FXUSDCAD (API Valet)",
        "fx_start": fx["date"].min().date().isoformat(),
        "fx_end": fx["date"].max().date().isoformat(),
        "crypto_tickers": crypto_tickers(),
        "base_currency": BASE_CURRENCY,
        "price_column": PRICE_COLUMN,
        "calendar_rule": "jours où toutes les actions et tous les FNB (TSX et marchés américains) ont un prix",
        "fx_convention": (
            "taux USD/CAD de la Banque du Canada du même jour, dernier taux connu "
            f"les jours sans publication (au plus {MAX_FX_CARRY_DAYS} jours)"
        ),
        "crypto_rule": "journée UTC de même date, mouvements du week-end cumulés au jour ouvrable suivant",
    }
