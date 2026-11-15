"""Radiographie du portefeuille fictif avant toute idée (US-03)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

import streamlit as st

import ui_texts as texts
from components.evidence import ProofContext, index_by_key, lookup, render_card, render_value
from components.rules import render_checks
from formatting import format_date

SUBJECT = "portfolio_before"


def period_caption(index: Mapping[str, Dict[str, Any]], subject: str) -> Optional[str]:
    """Période et devise lues dans la preuve de volatilité, jamais supposées."""
    entry = lookup(index, "volatility_ann", subject)
    if not entry or not entry.get("period_start") or not entry.get("period_end"):
        return None
    return texts.XRAY_PERIOD.format(
        start=format_date(entry["period_start"]), end=format_date(entry["period_end"]),
        currency=entry.get("currency") or texts.NOT_AVAILABLE)


def drawdown_caption(index: Mapping[str, Dict[str, Any]], subject: str) -> Optional[str]:
    start = lookup(index, "max_drawdown_start", subject)
    end = lookup(index, "max_drawdown_end", subject)
    if not start or not end:
        return None
    return texts.XRAY_DRAWDOWN_DATES.format(
        start=format_date(start["display_value"]), end=format_date(end["display_value"]))


def correlation_caption(index: Mapping[str, Dict[str, Any]], subject: str) -> Optional[str]:
    """Période et méthode du groupe corrélé, lues dans sa preuve (US-18), jamais supposées."""
    entry = lookup(index, "largest_correlated_group_weight", subject)
    if not entry or not entry.get("period_start") or not entry.get("period_end"):
        return None
    head = texts.XRAY_CORRELATION.format(
        start=format_date(entry["period_start"]), end=format_date(entry["period_end"]),
        count=entry.get("n_observations") or texts.NOT_AVAILABLE,
        currency=entry.get("currency") or texts.NOT_AVAILABLE)
    return f"{head} {entry.get('transformation') or ''}".strip()


def render_metric_cards(index: Mapping[str, Dict[str, Any]], snapshot: Mapping[str, Any], subject: str,
                        ctx: ProofContext, key_prefix: str) -> None:
    captions = {
        "max_drawdown": drawdown_caption(index, subject),
        "top_asset_weight": (texts.XRAY_TOP_ASSET.format(ticker=snapshot["top_asset"])
                             if snapshot.get("top_asset") else None),
        "largest_correlated_group_weight": ", ".join(snapshot.get("correlated_group_members") or []) or None,
    }
    metrics = list(texts.XRAY_METRICS)
    for start in range(0, len(metrics), 4):
        row = metrics[start:start + 4]
        for column, metric in zip(st.columns(4), row):
            with column:
                render_card(lookup(index, metric, subject), ctx, key=f"{key_prefix}_{metric}",
                            label=texts.METRIC_LABELS.get(metric), caption=captions.get(metric))


def _weight_rows(index: Mapping[str, Dict[str, Any]], snapshot: Mapping[str, Any], field: str,
                 prefix: str, subject: str, labels: Mapping[str, str]) -> List[Tuple[str, Dict[str, Any]]]:
    weights = snapshot.get(field) or {}
    rows = []
    # Tri par poids décroissant pour la lecture ; aucune valeur n'est recalculée.
    for name in sorted(weights, key=lambda item: weights[item], reverse=True):
        entry = lookup(index, f"{prefix}.{name}", subject)
        if entry is not None:
            rows.append((labels.get(name, name), entry))
    return rows


def render_weight_list(title: str, rows: List[Tuple[str, Dict[str, Any]]], ctx: ProofContext,
                       key_prefix: str) -> None:
    st.markdown(f"**{title}**")
    for position, (label, entry) in enumerate(rows):
        name, value = st.columns([3, 2], vertical_alignment="center")
        name.markdown(label)
        with value:
            render_value(entry, ctx, key=f"{key_prefix}_{position}")


def render_composition(index: Mapping[str, Dict[str, Any]], snapshot: Mapping[str, Any], subject: str,
                       ctx: ProofContext, names: Mapping[str, str], key_prefix: str) -> None:
    positions, classes, sectors = st.columns(3)
    ticker_labels = {ticker: f"{ticker}, {name}" for ticker, name in names.items()}
    with positions:
        render_weight_list(texts.XRAY_POSITIONS,
                           _weight_rows(index, snapshot, "weights", "weights", subject, ticker_labels),
                           ctx, f"{key_prefix}_pos")
    with classes:
        render_weight_list(texts.XRAY_CLASSES,
                           _weight_rows(index, snapshot, "weight_by_asset_class", "weight_by_asset_class",
                                        subject, texts.ASSET_CLASS_LABELS),
                           ctx, f"{key_prefix}_cls")
    with sectors:
        render_weight_list(texts.XRAY_SECTORS,
                           _weight_rows(index, snapshot, "weight_by_sector", "weight_by_sector",
                                        subject, texts.SECTOR_LABELS),
                           ctx, f"{key_prefix}_sec")


def render_xray(xray: Mapping[str, Any], rules_by_id: Mapping[str, Dict[str, Any]], ctx: ProofContext,
                names: Mapping[str, str]) -> None:
    index = index_by_key(xray["evidence"])
    st.caption(texts.XRAY_INTRO)
    period = period_caption(index, SUBJECT)
    if period:
        st.caption(period)
    render_metric_cards(index, xray["snapshot"], SUBJECT, ctx, key_prefix="xray")
    correlation = correlation_caption(index, SUBJECT)
    if correlation:
        st.caption(correlation)
    st.subheader(texts.XRAY_RULES)
    render_checks(xray["governance"]["checks"], xray["evidence"], SUBJECT, rules_by_id, ctx,
                  key_prefix="xray_rule", show_counterfactual=False)
    with st.expander(f"{texts.XRAY_POSITIONS}, {texts.XRAY_CLASSES.lower()}, {texts.XRAY_SECTORS.lower()}"):
        render_composition(index, xray["snapshot"], SUBJECT, ctx, names, key_prefix="xray_mix")
    st.caption(texts.XRAY_HYPOTHESIS)
