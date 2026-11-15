"""Petit graphique de la composition du portefeuille fictif, en tête de la simulation.

Une barre par position, triée du plus gros poids au plus petit. Les longueurs sont
les valeurs du registre de la radiographie (clés "weights.<ticker>:portfolio_before")
et les étiquettes leur texte affiché : l'interface ne calcule rien.

Mise en forme (méthode dataviz) : une seule série, donc une seule couleur et pas de
légende (le titre la nomme) ; barres fines à bout arrondi depuis une ligne de base
commune ; valeur au bout de chaque barre ; axe et grille effacés ; info-bulle au survol.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import altair as alt
import pandas as pd
import streamlit as st

import ui_texts as texts

# Série 1 de la palette validée (contraste >= 3:1 sur fond blanc, vérifié avec le validateur).
BAR_COLOR = "#2a78d6"
INK_SECONDARY = "#52514e"
BAR_SIZE = 18          # épaisseur, sous le plafond de 24 px
ROW_HEIGHT = 30


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


def render_portfolio_chart(xray_data: Optional[Mapping[str, Any]], names: Mapping[str, str],
                           profile_name: str) -> None:
    rows = weight_rows(xray_data, names)
    if not rows:
        return
    data = pd.DataFrame(rows)
    order = list(data["ticker"])
    y = alt.Y("ticker:N", sort=order, title=None,
              axis=alt.Axis(labelColor=INK_SECONDARY, labelFontSize=12, ticks=False, domain=False,
                            labelPadding=8))
    tooltip = [alt.Tooltip("ticker:N", title=texts.CHART_TOOLTIP_TICKER),
               alt.Tooltip("name:N", title=texts.CHART_TOOLTIP_NAME),
               alt.Tooltip("display:N", title=texts.CHART_TOOLTIP_WEIGHT)]
    bars = alt.Chart(data).mark_bar(size=BAR_SIZE, color=BAR_COLOR, cornerRadiusEnd=4).encode(
        x=alt.X("value:Q", title=None, axis=None, scale=alt.Scale(domain=[0, max(data["value"]) * 1.18])),
        y=y, tooltip=tooltip)
    labels = alt.Chart(data).mark_text(align="left", dx=6, color=INK_SECONDARY, fontSize=12).encode(
        x="value:Q", y=alt.Y("ticker:N", sort=order), text="display:N", tooltip=tooltip)
    chart = (bars + labels).properties(height=ROW_HEIGHT * len(rows)).configure_view(stroke=None)
    with st.container(border=True, key="portfolio-chart"):
        st.markdown(f"**{texts.CHART_TITLE.format(name=profile_name)}**")
        st.altair_chart(chart, width="stretch")
        st.caption(texts.CHART_CAPTION)
