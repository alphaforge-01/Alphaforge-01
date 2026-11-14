"""Chargement des données brutes du starter (data/raw/).

Toutes les fonctions acceptent un paramètre `as_of` : aucune ligne datée après
cette date n'est renvoyée, pour ne jamais utiliser une information future.
Les fichiers sont lus une seule fois puis gardés en mémoire ; chaque appel
renvoie une copie, que l'appelant peut modifier sans effet de bord. Après une
reconstruction de data/raw/ (ou dans un test qui remplace un fichier), appeler
`clear_caches()` pour relire les fichiers.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

UNIVERSE_FILE = RAW_DIR / "assets_universe.csv"
PRICES_FILE = RAW_DIR / "prices_daily.csv"
FX_FILE = RAW_DIR / "fx_usdcad_daily.csv"
SOURCES_FILE = RAW_DIR / "sources_metadata.csv"

AsOf = str | date | pd.Timestamp | None


def parse_as_of(as_of: AsOf) -> pd.Timestamp | None:
    """Convertit `as_of` en date normalisée (minuit), ou None si absent."""
    if as_of is None:
        return None
    stamp = pd.Timestamp(as_of)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp.normalize()


def normalize_tickers(tickers: str | list[str] | None) -> list[str] | None:
    """Accepte un ticker seul ou une liste ; renvoie une liste (ou None)."""
    if tickers is None:
        return None
    if isinstance(tickers, str):
        return [tickers]
    return list(tickers)


def _filter_as_of(frame: pd.DataFrame, as_of: AsOf, column: str = "date") -> pd.DataFrame:
    cutoff = parse_as_of(as_of)
    if cutoff is None:
        return frame
    return frame.loc[frame[column] <= cutoff]


@lru_cache(maxsize=1)
def _read_universe() -> pd.DataFrame:
    return pd.read_csv(UNIVERSE_FILE)


@lru_cache(maxsize=1)
def _read_prices() -> pd.DataFrame:
    frame = pd.read_csv(PRICES_FILE, parse_dates=["date"])
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def _read_fx() -> pd.DataFrame:
    frame = pd.read_csv(FX_FILE, parse_dates=["date"])
    return frame.sort_values("date").reset_index(drop=True)


@lru_cache(maxsize=1)
def _read_sources() -> pd.DataFrame:
    return pd.read_csv(SOURCES_FILE)


def clear_caches() -> None:
    """Vide les caches de lecture (à appeler si les fichiers de data/raw/ changent)."""
    for reader in (_read_universe, _read_prices, _read_fx, _read_sources):
        reader.cache_clear()


def load_universe() -> pd.DataFrame:
    """Univers des 31 actifs : ticker, nom, classe d'actifs, marché, devise, secteur."""
    return _read_universe().copy()


def load_prices(as_of: AsOf = None, tickers: str | list[str] | None = None) -> pd.DataFrame:
    """Prix quotidiens au format long (une ligne par date et par ticker).

    Les prix sont dans la devise de cotation de chaque actif. Utiliser
    `adj_close` pour les rendements : il est ajusté pour les dividendes et les
    fractionnements.
    """
    frame = _read_prices()
    tickers = normalize_tickers(tickers)
    if tickers is not None:
        unknown = sorted(set(tickers) - set(_read_universe()["ticker"]))
        if unknown:
            raise ValueError(f"Tickers absents de l'univers : {unknown}")
        frame = frame.loc[frame["ticker"].isin(tickers)]
    return _filter_as_of(frame, as_of).reset_index(drop=True).copy()


def load_fx(as_of: AsOf = None) -> pd.DataFrame:
    """Taux de change de la Banque du Canada : `usdcad` = CAD pour 1 USD.

    Le fichier n'a pas de ligne les jours fériés de la Banque du Canada.
    `cadusd` est un inverse arrondi : ne pas l'utiliser pour convertir.
    """
    return _filter_as_of(_read_fx(), as_of).reset_index(drop=True).copy()


def load_sources_metadata() -> pd.DataFrame:
    """Provenance, traitements, limites et conditions de chaque fichier du starter."""
    return _read_sources().copy()


def currency_by_ticker() -> dict[str, str]:
    """Devise de cotation de chaque ticker de l'univers."""
    universe = _read_universe()
    return dict(zip(universe["ticker"], universe["currency"]))


def crypto_tickers() -> list[str]:
    """Tickers de la classe d'actifs `crypto`."""
    universe = _read_universe()
    return universe.loc[universe["asset_class"] == "crypto", "ticker"].tolist()
