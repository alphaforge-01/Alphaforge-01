"""Métriques de risque et de rendement historiques, calculées par du code déterministe.

Ces fonctions décrivent le passé sur une période explicite. Elles ne prédisent
rien : un rendement ou une volatilité observés ne disent pas ce qui se passera.

Entrée : une série de rendements simples quotidiens (par exemple une colonne de
`calendar_alignment.daily_cad_returns`) et sa `base_date`, la date de la valeur
de départ (première date du calendrier commun, voir
`calendar_alignment.returns_base_date`). La `base_date` est **obligatoire** pour
les pertes maximales : sans elle, une baisse dès le premier jour serait ignorée.

Conventions :

- Annualisation sur `TRADING_DAYS_PER_YEAR` = 252 jours, pour tous les actifs,
  crypto comprise (elle est ramenée au calendrier boursier commun).
- Rendement annualisé géométrique : (produit des 1 + r) ^ (252 / n) - 1. Il
  vaut None si la période compte moins de 252 rendements : annualiser une
  période courte produirait un chiffre trompeur. Utiliser alors `total_return`
  avec sa période.
- Volatilité annualisée : écart-type des rendements quotidiens (n - 1) x racine de 252.
- Perte maximale : plus forte baisse entre un sommet et le creux qui suit,
  exprimée en **fraction positive** (0,29 pour une baisse de 29 %), comme dans
  `contracts.PortfolioSnapshot`.
- `recovery_days` : nombre de **jours civils** entre le creux et la première
  date où la valeur retrouve le niveau du sommet ; None si ce niveau n'est pas
  retrouvé avant la fin de la période ; 0 s'il n'y a eu aucune baisse.
- `underwater_days` : nombre de jours civils passés sous le sommet, du sommet
  jusqu'à la récupération, ou jusqu'à la fin de la période si la valeur n'a
  pas récupéré (alors `recovered` vaut False). C'est la mesure la plus parlante
  face à un horizon de placement.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
MIN_OBSERVATIONS = 2
# En dessous d'un an de rendements, le rendement annualisé n'est pas affiché
MIN_OBSERVATIONS_FOR_ANNUAL_RETURN = TRADING_DAYS_PER_YEAR
# Tolérance pour considérer qu'un niveau est retrouvé malgré les arrondis
RECOVERY_TOLERANCE = 1e-12

DateLike = pd.Timestamp | str


class InsufficientDataError(ValueError):
    """Pas assez de rendements pour calculer une métrique."""


@dataclass(frozen=True)
class DrawdownInfo:
    """Perte maximale et ses dates (fraction positive, dates ISO)."""

    max_drawdown: float
    peak_date: str
    trough_date: str
    recovered: bool
    recovery_date: str | None
    recovery_days: int | None
    underwater_days: int


@dataclass(frozen=True)
class ReturnMetrics:
    """Résumé des métriques d'une série de rendements sur une période explicite."""

    period_start: str
    period_end: str
    n_observations: int
    total_return: float
    return_ann: float | None
    volatility_ann: float
    max_drawdown: float
    max_drawdown_start: str
    max_drawdown_end: str
    recovered: bool
    recovery_date: str | None
    recovery_days: int | None
    underwater_days: int

    def to_dict(self) -> dict:
        """Dictionnaire de types Python simples (float, int, str, bool, None)."""
        return asdict(self)


def _validate_returns(returns: pd.Series) -> pd.Series:
    if not isinstance(returns, pd.Series):
        raise TypeError("Les rendements doivent être une pandas Series indexée par date")
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise TypeError("L'index des rendements doit être un DatetimeIndex")
    if returns.index.tz is not None:
        raise ValueError("L'index des rendements doit être sans fuseau horaire")
    if not returns.index.is_monotonic_increasing or returns.index.has_duplicates:
        raise ValueError("Les dates des rendements doivent être croissantes et uniques")
    if len(returns) < MIN_OBSERVATIONS:
        raise InsufficientDataError(
            f"Au moins {MIN_OBSERVATIONS} rendements sont nécessaires (reçu : {len(returns)})"
        )
    values = returns.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Les rendements contiennent des valeurs manquantes ou infinies")
    if (values <= -1).any():
        raise ValueError("Un rendement inférieur ou égal à -100 % est impossible pour un actif")
    return returns.astype(float)


def _parse_base_date(base_date: DateLike, returns: pd.Series) -> pd.Timestamp:
    if base_date is None:
        raise ValueError(
            "`base_date` est obligatoire : utiliser la première date du calendrier "
            "(calendar_alignment.returns_base_date)"
        )
    base = pd.Timestamp(base_date)
    if base.tzinfo is not None:
        base = base.tz_localize(None)
    if base >= returns.index[0]:
        raise ValueError("`base_date` doit précéder le premier rendement")
    return base


def wealth_index(returns: pd.Series, base_date: DateLike) -> pd.Series:
    """Valeur de 1 investi : 1 à `base_date`, puis rendements cumulés.

    `base_date` doit être la date précédant le premier rendement sur le
    calendrier commun ; le code vérifie seulement qu'elle est antérieure.
    """
    returns = _validate_returns(returns)
    base = _parse_base_date(base_date, returns)
    wealth = pd.concat([pd.Series([1.0], index=pd.DatetimeIndex([base])), (1.0 + returns).cumprod()])
    wealth.name = "wealth"
    return wealth


def total_return(returns: pd.Series) -> float:
    """Rendement cumulé sur toute la période (0,25 pour +25 %)."""
    returns = _validate_returns(returns)
    return float(np.prod(1.0 + returns.to_numpy()) - 1.0)


def annualized_return(
    returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float | None:
    """Rendement annualisé géométrique, ou None si la période fait moins d'un an."""
    returns = _validate_returns(returns)
    if len(returns) < MIN_OBSERVATIONS_FOR_ANNUAL_RETURN:
        return None
    growth = float(np.prod(1.0 + returns.to_numpy()))
    return growth ** (periods_per_year / len(returns)) - 1.0


def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Volatilité annualisée (écart-type échantillon x racine du nombre de périodes)."""
    returns = _validate_returns(returns)
    return float(returns.std(ddof=1) * math.sqrt(periods_per_year))


def drawdown_series(returns: pd.Series, base_date: DateLike) -> pd.Series:
    """Baisse depuis le plus haut précédent à chaque date (fraction positive, 0 au sommet)."""
    wealth = wealth_index(returns, base_date)
    drawdown = 1.0 - wealth / wealth.cummax()
    drawdown.name = "drawdown"
    return drawdown


def max_drawdown(returns: pd.Series, base_date: DateLike) -> DrawdownInfo:
    """Perte maximale, date du sommet, date du creux et récupération éventuelle.

    En cas d'égalité, le premier creux le plus profond est retenu. Sans aucune
    baisse, la perte vaut 0, sommet et creux sont `base_date`, et les durées valent 0.
    """
    wealth = wealth_index(returns, base_date)
    running_peak = wealth.cummax()
    drawdown = 1.0 - wealth / running_peak

    trough_date = drawdown.idxmax()
    depth = float(drawdown.loc[trough_date])
    if depth <= RECOVERY_TOLERANCE:
        first = wealth.index[0].date().isoformat()
        return DrawdownInfo(0.0, first, first, True, first, 0, 0)

    peak_level = float(running_peak.loc[trough_date])
    threshold = peak_level * (1.0 - RECOVERY_TOLERANCE)
    before_trough = wealth.loc[:trough_date]
    peak_date = before_trough.index[before_trough.to_numpy() >= threshold][-1]

    after_trough = wealth.loc[trough_date:]
    recovered_dates = after_trough.index[after_trough.to_numpy() >= threshold]
    if len(recovered_dates) > 0:
        recovery_date = recovered_dates[0]
        return DrawdownInfo(
            max_drawdown=depth,
            peak_date=peak_date.date().isoformat(),
            trough_date=trough_date.date().isoformat(),
            recovered=True,
            recovery_date=recovery_date.date().isoformat(),
            recovery_days=int((recovery_date - trough_date).days),
            underwater_days=int((recovery_date - peak_date).days),
        )
    return DrawdownInfo(
        max_drawdown=depth,
        peak_date=peak_date.date().isoformat(),
        trough_date=trough_date.date().isoformat(),
        recovered=False,
        recovery_date=None,
        recovery_days=None,
        underwater_days=int((wealth.index[-1] - peak_date).days),
    )


def compute_return_metrics(
    returns: pd.Series,
    base_date: DateLike,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> ReturnMetrics:
    """Toutes les métriques d'une série de rendements, avec la période couverte."""
    returns = _validate_returns(returns)
    drawdown = max_drawdown(returns, base_date)
    return ReturnMetrics(
        period_start=_parse_base_date(base_date, returns).date().isoformat(),
        period_end=returns.index[-1].date().isoformat(),
        n_observations=len(returns),
        total_return=total_return(returns),
        return_ann=annualized_return(returns, periods_per_year),
        volatility_ann=annualized_volatility(returns, periods_per_year),
        max_drawdown=drawdown.max_drawdown,
        max_drawdown_start=drawdown.peak_date,
        max_drawdown_end=drawdown.trough_date,
        recovered=drawdown.recovered,
        recovery_date=drawdown.recovery_date,
        recovery_days=drawdown.recovery_days,
        underwater_days=drawdown.underwater_days,
    )


def metrics_table(
    returns: pd.DataFrame,
    base_date: DateLike,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Métriques de chaque colonne d'une matrice de rendements (une ligne par ticker).

    Pour l'affichage et l'exploration. Les valeurs absentes restent None (colonnes
    de type objet), sans conversion en NaN. Pour alimenter la gouvernance ou les
    preuves, utiliser `compute_return_metrics(...).to_dict()`, qui garantit des
    types Python simples.
    """
    rows = {
        column: compute_return_metrics(returns[column], base_date, periods_per_year).to_dict()
        for column in returns.columns
    }
    # Construit colonne par colonne en type objet : garde les int, bool et None d'origine
    columns = list(next(iter(rows.values())).keys()) if rows else []
    table = pd.DataFrame(
        {name: pd.Series([row[name] for row in rows.values()], index=list(rows), dtype=object)
         for name in columns}
    )
    table.index.name = "ticker"
    return table
