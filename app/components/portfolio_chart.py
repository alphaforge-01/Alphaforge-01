"""Petit graphique de la composition du portefeuille fictif, en tête de la simulation.

Une barre par position, triée du plus gros poids au plus petit. Les longueurs sont
les valeurs du registre de la radiographie (clés "weights.<ticker>:portfolio_before")
et les étiquettes leur texte affiché.

Deux vues au choix :
- Barres : une seule série, donc une seule couleur et pas de légende (le titre la nomme) ;
  barres fines à bout arrondi depuis une ligne de base commune ; valeur au bout de chaque
  barre ; axe et grille effacés ; info-bulle au survol.
Une seule valeur calculée ici : la part "Autres" quand il y a plus de huit positions (somme
des poids du registre, `_fold_small`, testée dans tests/test_ui_charts.py). Le reste est relu tel quel.

- Composition : graphique circulaire (choix de l'équipe), une part par position. Couleurs
  catégorielles dans l'ordre fixe de la palette validée, filet blanc de 2 px entre parts,
  poids écrit à côté de chaque part et légende toujours visible (ticker et poids) : rien ne
  dépend du survol ni de la couleur seule.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import altair as alt
import pandas as pd
import streamlit as st

import ui_texts as texts
from formatting import format_pct

# Série 1 de la palette validée (contraste >= 3:1 sur fond blanc, vérifié avec le validateur).
BAR_COLOR = "#2a78d6"
INK_SECONDARY = "#52514e"
BAR_SIZE = 18          # épaisseur, sous le plafond de 24 px
ROW_HEIGHT = 30
# Palette catégorielle validée (validate_palette.js, mode clair), ordre fixe, jamais recyclée.
# Contraste sous 3:1 pour certains tons : compensé par la légende chiffrée et la vue tableau.
# Au-delà de huit positions, les plus petites sont regroupées dans une part "Autres" (gris neutre) :
# jamais de neuvième couleur générée.
CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
PIE_SIZE = 300         # hauteur : le cercle et les poids écrits autour y tiennent avec une marge
PIE_RADIUS = 100
LABEL_RADIUS = PIE_RADIUS + 22
VIEW_KEY = "portfolio_view"


def weight_rows(xray_data: Optional[Mapping[str, Any]], names: Mapping[str, str]) -> List[Dict[str, Any]]:
    """Positions du portefeuille de départ lues dans le registre, triées par poids décroissant."""
    if not xray_data:
        return []
    rows = []
    for entry in xray_data.get("evidence", {}).values():
        metric, _, subject = str(entry.get("evidence_key", "")).partition(":")
        if not metric.startswith("weights.") or subject != "portfolio_before":
            continue
        value, display = entry.get("value"), entry.get("display_value")
        if not isinstance(value, (int, float)) or not display:
            continue
        ticker = metric[len("weights."):]
        rows.append({"ticker": ticker, "name": names.get(ticker, ticker), "value": float(value),
                     "display": display})
    return sorted(rows, key=lambda row: (-row["value"], row["ticker"]))


def _tooltip() -> List[alt.Tooltip]:
    return [alt.Tooltip("ticker:N", title=texts.CHART_TOOLTIP_TICKER),
            alt.Tooltip("name:N", title=texts.CHART_TOOLTIP_NAME),
            alt.Tooltip("display:N", title=texts.CHART_TOOLTIP_WEIGHT)]


OTHERS_COLOR = "#8a8984"


def _fold_small(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Garde les sept plus gros poids et regroupe le reste dans "Autres" (somme des poids du registre)."""
    if len(rows) <= len(CATEGORICAL):
        return rows
    keep, rest = rows[:len(CATEGORICAL) - 1], rows[len(CATEGORICAL) - 1:]
    total = sum(row["value"] for row in rest)
    label = texts.CHART_OTHERS.format(count=len(rest))
    return keep + [{"ticker": label, "name": ", ".join(row["ticker"] for row in rest),
                    "value": total, "display": format_pct(total)}]


def _composition_chart(rows: List[Dict[str, Any]]) -> alt.Chart:
    """Graphique circulaire : une part par position, dans l'ordre des poids, légende à droite."""
    shown = _fold_small(rows)
    data = pd.DataFrame(shown)
    data["order"] = range(len(data))
    data["legend"] = data["ticker"] + "  " + data["display"]
    legend_order = list(data["legend"])
    folded = shown is not rows
    colors = list(CATEGORICAL[:len(shown) - 1]) + [OTHERS_COLOR] if folded else list(CATEGORICAL[:len(shown)])
    color = alt.Color("legend:N", sort=legend_order, title=None,
                      scale=alt.Scale(domain=legend_order, range=colors),
                      legend=alt.Legend(orient="right", direction="vertical", labelColor="#1a2332",
                                        labelFontSize=13, symbolType="circle", symbolSize=160,
                                        rowPadding=8, offset=28))
    base = alt.Chart(data).encode(theta=alt.Theta("value:Q", stack=True), order=alt.Order("order:Q"))
    slices = base.mark_arc(outerRadius=PIE_RADIUS, stroke="#ffffff", strokeWidth=2).encode(
        color=color, tooltip=_tooltip())
    labels = base.mark_text(radius=LABEL_RADIUS, fontSize=12, color=INK_SECONDARY).encode(
        text="display:N")
    # Marge en objet (top, bottom...) : Streamlit complète ce champ, un nombre seul le fait planter.
    return (slices + labels).properties(height=PIE_SIZE, padding={"top": 16, "bottom": 16, "left": 16, "right": 16}).configure_view(stroke=None)


def render_portfolio_chart(xray_data: Optional[Mapping[str, Any]], names: Mapping[str, str],
                           profile_name: str) -> None:
    rows = weight_rows(xray_data, names)
    if not rows:
        return
    with st.container(border=True, key="portfolio-chart"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{texts.CHART_TITLE.format(name=profile_name)}**")
            st.space("stretch")
            views = list(texts.CHART_VIEW_LABELS)
            view = st.segmented_control(texts.CHART_VIEW_LABEL, options=views,
                                        format_func=texts.CHART_VIEW_LABELS.get, default="bars",
                                        key=VIEW_KEY, label_visibility="collapsed")
            view = view if view in views else "bars"
        if view == "composition":
            st.altair_chart(_composition_chart(rows), width="stretch")
            st.caption(texts.CHART_COMPOSITION_CAPTION)
        else:
            st.altair_chart(_bars_chart(rows), width="stretch")
            st.caption(texts.CHART_CAPTION)


def _bars_chart(rows: List[Dict[str, Any]]) -> alt.Chart:
    """Une barre par position, du plus gros poids au plus petit."""
    data = pd.DataFrame(rows)
    order = list(data["ticker"])
    y = alt.Y("ticker:N", sort=order, title=None,
              axis=alt.Axis(labelColor=INK_SECONDARY, labelFontSize=12, ticks=False, domain=False,
                            labelPadding=8))
    tooltip = _tooltip()
    bars = alt.Chart(data).mark_bar(size=BAR_SIZE, color=BAR_COLOR, cornerRadiusEnd=4).encode(
        x=alt.X("value:Q", title=None, axis=None, scale=alt.Scale(domain=[0, max(data["value"]) * 1.18])),
        y=y, tooltip=tooltip)
    labels = alt.Chart(data).mark_text(align="left", dx=6, color=INK_SECONDARY, fontSize=12).encode(
        x="value:Q", y=alt.Y("ticker:N", sort=order), text="display:N", tooltip=tooltip)
    return (bars + labels).properties(height=ROW_HEIGHT * len(rows)).configure_view(stroke=None)
