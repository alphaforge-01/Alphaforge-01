"""Mise en forme au format français, sans aucun calcul financier.

Deux usages seulement (docs/ui_spec.md, règles d'affichage 1 et 2) :
- les paramètres : seuils des règles, poids choisi par l'utilisateur, capital
  fictif, horizon, dates ;
- les valeurs déjà calculées par la gouvernance du flux B qui n'ont pas de texte
  prêt dans le contrat (marge d'une règle).
Un chiffre du registre de preuves s'affiche toujours avec son `display_value`.
Les pourcentages et les points utilisent les fonctions de l'explication
(src/alphaforge/explanation_rendering.py), pour un format identique partout.
"""
from __future__ import annotations

from datetime import date

from alphaforge.evidence import format_cad as evidence_format_cad
from alphaforge.explanation_rendering import format_percent, format_points

MONTHS_FR = ("janv.", "févr.", "mars", "avr.", "mai", "juin",
             "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def escape_dollars(markdown: str) -> str:
    """Streamlit lit $...$ comme une formule : deux montants dans un paragraphe seraient mal rendus."""
    return markdown.replace("$", "\\$")


def format_pct(fraction: float) -> str:
    """0.25 -> "25 %", 0.125 -> "12,5 %". Même règle que l'explication (src/alphaforge)."""
    return format_percent(fraction)


def format_pts(fraction: float) -> str:
    """0.074 -> "7,4 pts". Écart en points de pourcentage."""
    return format_points(fraction)


def format_cad(amount: float) -> str:
    """100000 -> "100 000 $". Espace comme séparateur de milliers."""
    return evidence_format_cad(amount)


def format_horizon(min_years: int, max_years: int) -> str:
    """(3, 5) -> "3 à 5 ans", (10, 10) -> "10 ans", (1, 1) -> "1 an"."""
    unit = "an" if max_years == 1 else "ans"
    if min_years == max_years:
        return f"{min_years} {unit}"
    return f"{min_years} à {max_years} {unit}"


def format_date(iso_date: str) -> str:
    """"2021-11-12" -> "12 nov. 2021". Une valeur illisible est rendue telle quelle."""
    try:
        day = date.fromisoformat(str(iso_date)[:10])
    except ValueError:
        return str(iso_date)
    return f"{day.day} {MONTHS_FR[day.month - 1]} {day.year}"


def summary_section(markdown: str) -> str:
    """Section "Résumé" d'une explication rendue, sans son titre. Lecture du texte, aucun calcul."""
    lines = markdown.splitlines()
    for start, line in enumerate(lines):
        if line.startswith("## ") and line[3:].strip().lower() in ("résumé", "resume"):
            body = []
            for following in lines[start + 1:]:
                if following.startswith("## "):
                    break
                body.append(following)
            return "\n".join(body).strip()
    return ""
