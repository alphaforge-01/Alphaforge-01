"""Plus grand groupe d'actifs corrélés d'un portefeuille (P2, user story US-18).

Méthode, simple et vérifiable à la main :
- rendements quotidiens simples en CAD sur le calendrier commun (voir
  `calendar_alignment.daily_cad_returns`), sur toute la fenêtre disponible
  jusqu'à `as_of` ;
- corrélation de Pearson entre chaque paire de titres détenus ;
- deux titres sont liés si leur corrélation est supérieure ou égale à
  `CORRELATION_THRESHOLD` (corrélation positive seulement) ;
- un groupe est une composante connectée de ces liens (liaison simple : A lié
  à B et B lié à C mettent A, B et C dans le même groupe, même si A et C le
  sont moins) ;
- la mesure est la somme des poids du groupe le plus pesant, avec au moins deux
  titres. Sans groupe, elle vaut 0.

Hypothèses de l'équipe, à présenter comme telles : le seuil de 0,80, la fenêtre
complète, la liaison simple. Le seuil a été choisi après examen des données
(voir docs/technical_documentation.md, test de sensibilité). La corrélation
décrit le passé : ce n'est pas une prévision.
"""
from __future__ import annotations

import math
from typing import Mapping

import pandas as pd

from alphaforge.calendar_alignment import daily_cad_returns
from alphaforge.data_loading import AsOf

CORRELATION_THRESHOLD = 0.80
# En dessous, une corrélation est trop instable : la mesure est alors absente (information manquante).
MIN_OBSERVATIONS = 60
WEIGHT_DECIMALS = 10
ZERO_WEIGHT = 1e-12


def largest_correlated_group(
    returns: pd.DataFrame,
    weights: Mapping[str, float],
    threshold: float = CORRELATION_THRESHOLD,
) -> tuple[float | None, list[str]]:
    """Poids et membres du plus pesant groupe corrélé, ou `(None, [])` si trop peu d'observations.

    `returns` : une colonne par titre. `weights` : poids des titres détenus. Les titres
    sans poids sont ignorés. Égalité de poids : le groupe dont la liste triée de
    membres vient en premier.
    """
    held = sorted(ticker for ticker, weight in weights.items() if weight > ZERO_WEIGHT)
    if len(held) < 2:
        return 0.0, []
    if len(returns) < MIN_OBSERVATIONS:
        return None, []
    correlation = returns[held].corr()
    parent = {ticker: ticker for ticker in held}

    def find(ticker: str) -> str:
        while parent[ticker] != ticker:
            parent[ticker] = parent[parent[ticker]]
            ticker = parent[ticker]
        return ticker

    for position, first in enumerate(held):
        for second in held[position + 1:]:
            value = correlation.loc[first, second]
            if not math.isnan(value) and value >= threshold:  # NaN (série plate) : jamais un lien
                parent[find(second)] = find(first)
    groups: dict[str, list[str]] = {}
    for ticker in held:
        groups.setdefault(find(ticker), []).append(ticker)
    best: tuple[float, list[str]] = (0.0, [])
    for members in groups.values():
        if len(members) < 2:
            continue
        weight = sum(float(weights[member]) for member in members)
        if weight > best[0] + ZERO_WEIGHT or (abs(weight - best[0]) <= ZERO_WEIGHT and members < best[1]):
            best = (weight, members)
    return round(float(best[0]), WEIGHT_DECIMALS), sorted(best[1])


def correlated_group(weights: Mapping[str, float], as_of: AsOf = None) -> tuple[float | None, list[str]]:
    """Plus grand groupe corrélé d'un portefeuille, à partir des prix en CAD jusqu'à `as_of`."""
    held = sorted(ticker for ticker, weight in weights.items() if weight > ZERO_WEIGHT)
    if len(held) < 2:
        return 0.0, []
    return largest_correlated_group(daily_cad_returns(as_of=as_of, tickers=held), weights)
