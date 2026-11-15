"""Graphiques de l'interface v2 (PR-3) : trois visualisations lisibles par un novice.

1. Composition du portefeuille avant et après l'idée.
2. Mesures financières comparées aux seuils du profil.
3. Idée initiale comparée aux variantes proposées.

Les graphiques lisent seulement les structures de `view_models.py` (`WeightRow`,
`ThresholdBar`, `VariantRow`). Aucun chiffre n'est calculé ici : chaque longueur de
barre est une valeur déjà présente dans le registre de preuves ou dans la gouvernance,
et chaque étiquette est le texte déjà affiché.

Valeurs manquantes. Une valeur `None` reste inconnue. Elle n'est jamais convertie en
zéro : la barre correspondante est omise et une phrase "Non disponible dans les
données" nomme ce qui manque.

Chaque graphique a une fonction `*_records` (données tracées, testables) et une fonction
`*_chart` (spécification Altair). Les fonctions `render_*` ajoutent le titre, la légende
en texte et l'affichage Streamlit. Ce module n'est branché dans aucune page : l'interface
v2 reste désactivée.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import altair as alt
import pandas as pd
import streamlit as st

import ui_labels as labels
import ui_texts as texts
from view_models import ThresholdBar, VariantRow, WeightRow

Record = Dict[str, Any]

# Couleurs contrastées sur fond blanc. Le sens n'est jamais porté par la couleur seule :
# légende, libellés et valeurs affichées l'accompagnent.
COLOR_BEFORE = "#7b8794"
COLOR_AFTER = "#2a78d6"
COLOR_VOLATILITY = "#2a78d6"
COLOR_DRAWDOWN = "#0f8b8d"
STATUS_COLORS_HEX = {
    "compliant": "#2f855a",
    "tension": "#e0a100",
    "conflict": "#c53030",
    "missing_info": "#718096",
}
COLOR_MARK_WARN = "#7c4a03"
COLOR_MARK_LIMIT = "#111827"
INK_SECONDARY = "#52514e"

BAR_SIZE = 12
LABEL_FONT = 12
WEIGHT_ROW_HEIGHT = 48
THRESHOLD_ROW_HEIGHT = 44
VARIANT_ROW_HEIGHT = 56
DOMAIN_MARGIN = 1.2


def _axis_style() -> alt.Axis:
    return alt.Axis(labelColor=INK_SECONDARY, labelFontSize=LABEL_FONT, ticks=False, domain=False,
                    labelPadding=8, labelLimit=260)


def _percent_ticks(maximum: float) -> List[float]:
    """Repères de l'axe tous les 5 points (10 au-delà de 60 %), jusqu'au maximum tracé. Mise en page seulement."""
    step = 0.05 if maximum <= 0.6 else 0.10
    count = int(maximum / step) + 1
    return [round(index * step, 4) for index in range(count + 1)]


PERCENT_LABEL_EXPR = "round(datum.value * 100) + ' %'"


# --- 1. Composition avant et après --------------------------------------------------

def weight_records(rows: Sequence[WeightRow]) -> Tuple[List[Record], List[str], List[str]]:
    """Données tracées, tickers sans poids avant, tickers sans poids après.

    Une ligne par (titre, série). Un poids `None` n'a pas de ligne : la barre est omise.
    """
    records: List[Record] = []
    missing_before: List[str] = []
    missing_after: List[str] = []
    for row in rows:
        for series, value, display, missing in (
            (labels.SERIES_BEFORE, row.before, row.before_display, missing_before),
            (labels.SERIES_AFTER, row.after, row.after_display, missing_after),
        ):
            if value is None or not display:
                missing.append(row.ticker)
                continue
            records.append({"ticker": row.ticker, "name": row.name, "series": series,
                            "value": value, "display": display})
    return records, missing_before, missing_after


def weight_chart(rows: Sequence[WeightRow]) -> Optional[alt.LayerChart]:
    records, _, _ = weight_records(rows)
    if not records:
        return None
    order = [row.ticker for row in rows]
    series_order = [labels.SERIES_BEFORE, labels.SERIES_AFTER]
    data = pd.DataFrame(records)
    tooltip = [alt.Tooltip("ticker:N", title=labels.TOOLTIP_TICKER),
               alt.Tooltip("name:N", title=labels.TOOLTIP_NAME),
               alt.Tooltip("series:N", title=labels.TOOLTIP_SERIES),
               alt.Tooltip("display:N", title=labels.TOOLTIP_VALUE)]
    y = alt.Y("ticker:N", sort=order, title=None, axis=_axis_style())
    offset = alt.YOffset("series:N", sort=series_order)
    x = alt.X("value:Q", title=None, axis=None,
              scale=alt.Scale(domain=[0, max(data["value"]) * DOMAIN_MARGIN]))
    color = alt.Color("series:N", sort=series_order, title=labels.SERIES_LEGEND_TITLE,
                      scale=alt.Scale(domain=series_order, range=[COLOR_BEFORE, COLOR_AFTER]),
                      legend=alt.Legend(orient="top", labelFontSize=LABEL_FONT))
    bars = alt.Chart(data).mark_bar(size=BAR_SIZE, cornerRadiusEnd=3).encode(
        x=x, y=y, yOffset=offset, color=color, tooltip=tooltip)
    values = alt.Chart(data).mark_text(align="left", dx=6, color=INK_SECONDARY, fontSize=LABEL_FONT).encode(
        x=alt.X("value:Q"), y=alt.Y("ticker:N", sort=order), yOffset=offset, text="display:N",
        tooltip=tooltip)
    return (bars + values).properties(height=WEIGHT_ROW_HEIGHT * len(rows)).configure_view(stroke=None)


def render_weight_comparison(rows: Sequence[WeightRow]) -> None:
    with st.container(border=True):
        st.markdown(f"**{labels.WEIGHTS_TITLE}**")
        chart = weight_chart(rows)
        if chart is None:
            st.caption(labels.WEIGHTS_EMPTY)
            return
        st.altair_chart(chart, width="stretch")
        st.caption(labels.WEIGHTS_CAPTION)
        _, missing_before, missing_after = weight_records(rows)
        for side, tickers in ((labels.WEIGHTS_MISSING_BEFORE, missing_before),
                              (labels.WEIGHTS_MISSING_AFTER, missing_after)):
            if tickers:
                st.caption(labels.WEIGHTS_MISSING.format(side=side, tickers=", ".join(tickers)))


# --- 2. Mesures face aux seuils -----------------------------------------------------

def threshold_records(bars: Sequence[ThresholdBar]) -> Tuple[List[Record], List[Record]]:
    """(barres de mesure, repères de seuil). Un seuil d'avertissement `None` n'a pas de repère."""
    measures: List[Record] = []
    marks: List[Record] = []
    for bar in bars:
        measures.append({
            "label": bar.label, "value": bar.value, "display": bar.value_display,
            "status": bar.status_label, "direction": labels.THRESHOLD_DIRECTION.get(bar.direction, ""),
        })
        if bar.warn is not None and bar.warn_display:
            marks.append({"label": bar.label, "value": bar.warn, "display": bar.warn_display,
                          "mark": labels.THRESHOLD_WARN})
        marks.append({"label": bar.label, "value": bar.limit, "display": bar.limit_display,
                      "mark": labels.THRESHOLD_LIMIT})
    return measures, marks


def threshold_chart(bars: Sequence[ThresholdBar]) -> Optional[alt.LayerChart]:
    measures, marks = threshold_records(bars)
    if not measures:
        return None
    order = [bar.label for bar in bars]
    maximum = max(record["value"] for record in measures + marks) * DOMAIN_MARGIN
    statuses = [texts.STATUS_LABELS[s] for s in ("compliant", "tension", "conflict")
                if texts.STATUS_LABELS[s] in {m["status"] for m in measures}]
    status_colors = [STATUS_COLORS_HEX[s] for s in ("compliant", "tension", "conflict")
                     if texts.STATUS_LABELS[s] in {m["status"] for m in measures}]
    other = sorted({m["status"] for m in measures} - set(statuses))
    statuses += other
    status_colors += [STATUS_COLORS_HEX["missing_info"]] * len(other)
    x = alt.X("value:Q", title=None,
              scale=alt.Scale(domain=[0, maximum]),
              axis=alt.Axis(values=_percent_ticks(maximum), labelExpr=PERCENT_LABEL_EXPR,
                            labelColor=INK_SECONDARY, labelFontSize=LABEL_FONT, grid=True,
                            gridColor="#e6e6e3", domain=False, ticks=False))
    y = alt.Y("label:N", sort=order, title=None, axis=_axis_style())
    bar_layer = alt.Chart(pd.DataFrame(measures)).mark_bar(size=16, cornerRadiusEnd=3).encode(
        x=x, y=y,
        color=alt.Color("status:N", title=labels.THRESHOLD_STATUS_LEGEND_TITLE,
                        scale=alt.Scale(domain=statuses, range=status_colors),
                        legend=alt.Legend(orient="top", labelFontSize=LABEL_FONT)),
        tooltip=[alt.Tooltip("label:N", title=labels.TOOLTIP_RULE),
                 alt.Tooltip("display:N", title=labels.TOOLTIP_VALUE),
                 alt.Tooltip("status:N", title=labels.TOOLTIP_STATUS),
                 alt.Tooltip("direction:N", title=labels.TOOLTIP_DIRECTION)])
    mark_names = [labels.THRESHOLD_WARN, labels.THRESHOLD_LIMIT]
    mark_layer = alt.Chart(pd.DataFrame(marks)).mark_tick(thickness=3, size=28).encode(
        x=alt.X("value:Q"), y=alt.Y("label:N", sort=order),
        color=alt.Color("mark:N", title=labels.THRESHOLD_LEGEND_TITLE,
                        scale=alt.Scale(domain=mark_names, range=[COLOR_MARK_WARN, COLOR_MARK_LIMIT]),
                        legend=alt.Legend(orient="top", labelFontSize=LABEL_FONT)),
        tooltip=[alt.Tooltip("label:N", title=labels.TOOLTIP_RULE),
                 alt.Tooltip("mark:N", title=labels.THRESHOLD_LEGEND_TITLE),
                 alt.Tooltip("display:N", title=labels.TOOLTIP_VALUE)])
    value_labels = alt.Chart(pd.DataFrame(measures)).mark_text(
        align="left", dx=8, dy=-14, color=INK_SECONDARY, fontSize=LABEL_FONT).encode(
        x=alt.X("value:Q"), y=alt.Y("label:N", sort=order), text="display:N")
    layered = alt.layer(bar_layer, mark_layer, value_labels).resolve_scale(color="independent")
    return layered.properties(height=THRESHOLD_ROW_HEIGHT * len(order)).configure_view(stroke=None)


def render_threshold_chart(bars: Sequence[ThresholdBar]) -> None:
    with st.container(border=True):
        st.markdown(f"**{labels.THRESHOLDS_TITLE}**")
        chart = threshold_chart(bars)
        if chart is None:
            st.caption(labels.THRESHOLDS_EMPTY)
            return
        st.altair_chart(chart, width="stretch")
        st.caption(labels.THRESHOLDS_CAPTION)


# --- 3. Idée initiale et variantes --------------------------------------------------

def variant_row_label(row: VariantRow) -> str:
    """Étiquette d'une ligne : nom, poids cible de l'idée et statut, par exemple "V1 : réduire le poids (17 %), Conforme"."""
    if row.row_id == "initial":
        name = labels.VARIANTS_INITIAL
    elif row.reason_label:
        name = f"{row.row_id} : {row.reason_label}"
    else:
        name = row.row_id
    label = (labels.VARIANT_ROW_LABEL.format(name=name, weight=row.target_weight_display)
             if row.target_weight_display else name)
    return labels.VARIANT_ROW_WITH_STATUS.format(label=label, status=row.status_label)


def variant_records(rows: Sequence[VariantRow]) -> Tuple[List[Record], Dict[str, List[str]]]:
    """(données tracées, lignes sans mesure par nom de mesure). Une mesure `None` n'a pas de ligne."""
    records: List[Record] = []
    missing: Dict[str, List[str]] = {labels.VARIANT_VOLATILITY: [], labels.VARIANT_DRAWDOWN: []}
    for row in rows:
        row_label = variant_row_label(row)
        for measure, value, display in (
            (labels.VARIANT_VOLATILITY, row.volatility, row.volatility_display),
            (labels.VARIANT_DRAWDOWN, row.max_drawdown, row.max_drawdown_display),
        ):
            if value is None or not display:
                missing[measure].append(row.row_id)
                continue
            records.append({"row": row_label, "measure": measure, "value": value, "display": display,
                            "status": row.status_label})
    return records, missing


def variant_chart(rows: Sequence[VariantRow]) -> Optional[alt.LayerChart]:
    records, _ = variant_records(rows)
    if not records:
        return None
    order = [variant_row_label(row) for row in rows]
    measures = [labels.VARIANT_VOLATILITY, labels.VARIANT_DRAWDOWN]
    data = pd.DataFrame(records)
    maximum = max(data["value"]) * DOMAIN_MARGIN
    tooltip = [alt.Tooltip("row:N", title=labels.TOOLTIP_ROW),
               alt.Tooltip("measure:N", title=labels.VARIANT_MEASURES_LEGEND_TITLE),
               alt.Tooltip("display:N", title=labels.TOOLTIP_VALUE),
               alt.Tooltip("status:N", title=labels.TOOLTIP_STATUS)]
    y = alt.Y("row:N", sort=order, title=None, axis=_axis_style())
    offset = alt.YOffset("measure:N", sort=measures)
    x = alt.X("value:Q", title=None, scale=alt.Scale(domain=[0, maximum]),
              axis=alt.Axis(values=_percent_ticks(maximum), labelExpr=PERCENT_LABEL_EXPR,
                            labelColor=INK_SECONDARY, labelFontSize=LABEL_FONT, grid=True,
                            gridColor="#e6e6e3", domain=False, ticks=False))
    color = alt.Color("measure:N", sort=measures, title=labels.VARIANT_MEASURES_LEGEND_TITLE,
                      scale=alt.Scale(domain=measures, range=[COLOR_VOLATILITY, COLOR_DRAWDOWN]),
                      legend=alt.Legend(orient="top", labelFontSize=LABEL_FONT))
    bars = alt.Chart(data).mark_bar(size=BAR_SIZE, cornerRadiusEnd=3).encode(
        x=x, y=y, yOffset=offset, color=color, tooltip=tooltip)
    values = alt.Chart(data).mark_text(align="left", dx=6, color=INK_SECONDARY, fontSize=LABEL_FONT).encode(
        x=alt.X("value:Q"), y=alt.Y("row:N", sort=order), yOffset=offset, text="display:N", tooltip=tooltip)
    return (bars + values).properties(height=VARIANT_ROW_HEIGHT * len(rows)).configure_view(stroke=None)


def render_variant_comparison(rows: Sequence[VariantRow]) -> None:
    with st.container(border=True):
        st.markdown(f"**{labels.VARIANTS_TITLE}**")
        if len(rows) < 2:
            st.caption(labels.VARIANTS_NONE_PROPOSED if rows else labels.VARIANTS_EMPTY)
            return
        chart = variant_chart(rows)
        if chart is None:
            st.caption(labels.VARIANTS_EMPTY)
            return
        st.altair_chart(chart, width="stretch")
        st.caption(labels.VARIANTS_CAPTION)
        _, missing = variant_records(rows)
        for measure, row_ids in missing.items():
            if row_ids:
                st.caption(labels.VARIANTS_MISSING.format(measure=measure.lower(), rows=", ".join(row_ids)))
