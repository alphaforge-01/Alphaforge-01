"""Mise en forme des paramètres au format français.

À utiliser seulement pour des paramètres : seuils des règles, poids choisi par
l'utilisateur, capital fictif, horizon. Un chiffre calculé (métrique, poids après
simulation, montant) s'affiche toujours avec le `display_value` du registre de
preuves, jamais avec ces fonctions (docs/ui_spec.md, règle d'affichage 1).
"""
from __future__ import annotations


def format_pct(fraction: float, decimals: int = 0) -> str:
    """0.25 -> "25 %". Virgule décimale, espace avant le signe."""
    text = f"{fraction * 100:.{decimals}f}".replace(".", ",")
    return f"{text} %"


def format_cad(amount: float) -> str:
    """100000 -> "100 000 $". Espace comme séparateur de milliers."""
    text = f"{amount:,.0f}".replace(",", " ")
    return f"{text} $"


def format_horizon(min_years: int, max_years: int) -> str:
    """(3, 5) -> "3 à 5 ans", (10, 10) -> "10 ans"."""
    if min_years == max_years:
        return f"{min_years} ans"
    return f"{min_years} à {max_years} ans"
