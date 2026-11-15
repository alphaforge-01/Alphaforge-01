"""Résultat d'une idée : avant/après, règles, contrefactuel, variantes (US-05 à US-09)."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import streamlit as st

import ui_texts as texts
from components.evidence import ProofContext, index_by_key, lookup, render_card, render_value
from components.idea_panel import describe_idea
from components.rules import render_checks, status_badge
from components.xray import render_composition
from formatting import format_pct

_STATUS_BOX = {"conflict": st.error, "tension": st.warning, "missing_info": st.info, "compliant": st.success}


def render_overall(result: Mapping[str, Any]) -> None:
    after = result["governance_after"]["overall_status"]
    before = result["governance_before"]["overall_status"]
    _STATUS_BOX.get(after, st.info)(texts.RESULT_OVERALL.format(status=texts.STATUS_LABELS[after]))
    st.caption(texts.RESULT_OVERALL_BEFORE.format(status=texts.STATUS_LABELS[before]))


def render_mode_note(result: Mapping[str, Any]) -> None:
    """Dit clairement si Bedrock a été demandé mais pas utilisé (repli du pipeline)."""
    details = (result.get("trace") or [{}])[0].get("details", {})
    reason = details.get("fallback_reason")
    if details.get("mode_requested") == "bedrock" and reason:
        st.info(texts.RESULT_MODE_FALLBACK.format(reason=texts.REASON_CODES_FR.get(reason, reason)))


def render_comparison(result: Mapping[str, Any], ctx: ProofContext, names: Mapping[str, str]) -> None:
    """Mêmes mesures que la radiographie, avant et après, avec l'écart du registre."""
    index = index_by_key(result["evidence"])
    top = {"portfolio_before": result["snapshot_before"].get("top_asset"),
           "portfolio_after": result["snapshot_after"].get("top_asset")}
    st.subheader(texts.RESULT_COMPARE)
    widths = [4, 2, 2, 2]
    for column, title in zip(st.columns(widths), (texts.COLUMN_MEASURE, texts.COLUMN_BEFORE,
                                                  texts.COLUMN_AFTER, texts.COLUMN_DELTA)):
        column.markdown(f"**{title}**")
    for metric in texts.COMPARE_METRICS:
        before = lookup(index, metric, "portfolio_before")
        after = lookup(index, metric, "portfolio_after")
        delta = lookup(index, f"{metric}_delta", "portfolio_after")
        label_col, before_col, after_col, delta_col = st.columns(widths, vertical_alignment="center")
        label_col.markdown((after or before or {}).get("label_fr", metric))
        for column, entry, subject in ((before_col, before, "portfolio_before"),
                                       (after_col, after, "portfolio_after")):
            with column:
                render_value(entry, ctx, key=f"cmp_{metric}_{subject}")
                if metric == "top_asset_weight" and top.get(subject):
                    st.caption(top[subject])
        with delta_col:
            if delta is not None:
                render_value(delta, ctx, key=f"cmp_{metric}_delta")
    st.caption(texts.RESULT_AMOUNT_NOTE)
    with st.expander(texts.RESULT_COMPOSITION):
        render_composition(index, result["snapshot_after"], "portfolio_after", ctx, names, key_prefix="after_mix")


def render_asset_facts(facts: Mapping[str, Any], ticker: str, ctx: ProofContext) -> None:
    """Chiffres de l'actif seul : identiques pour tous les profils (US-09)."""
    st.subheader(texts.ASSET_FACTS_TITLE.format(ticker=ticker))
    index = index_by_key(facts["evidence"])
    metrics = texts.ASSET_FACTS_METRICS
    for column, metric in zip(st.columns(len(metrics)), metrics):
        with column:
            render_card(lookup(index, metric, ticker), ctx, key=f"asset_{ticker}_{metric}")
    st.caption(texts.ASSET_FACTS_NOTE)


def describe_variant(idea: Mapping[str, Any]) -> str:
    funding = texts.IDEA_FUNDING_SHORT[idea["funding_source"]].format(ticker=idea.get("funding_ticker"))
    return texts.VARIANT_IDEA.format(weight=format_pct(idea["target_weight"]), ticker=idea["ticker"],
                                     funding=funding)


def render_variants(result: Mapping[str, Any], rules_by_id: Mapping[str, Dict[str, Any]],
                    ctx: ProofContext) -> None:
    st.subheader(texts.VARIANTS_TITLE)
    variants = result.get("variants") or []
    if not variants:
        st.caption(texts.VARIANTS_NONE)
        return
    st.caption(texts.VARIANTS_NOTICE)
    index = index_by_key(result["evidence"])
    for variant in variants:
        subject = f"variant:{variant['variant_id']}"
        with st.container(border=True):
            reason = texts.REASON_LABELS.get(variant["reason_code"], variant["reason_code"])
            st.markdown(f"**{texts.VARIANT_HEADER.format(variant_id=variant['variant_id'], reason=reason)}**")
            st.caption(describe_variant(variant["idea"]))
            status_badge(variant["governance"]["overall_status"])
            metrics = ("volatility_ann", "max_drawdown", "top_asset_weight", "defensive_share")
            for column, metric in zip(st.columns(len(metrics)), metrics):
                with column:
                    entry = lookup(index, metric, subject)
                    st.caption((entry or {}).get("label_fr", metric))
                    render_value(entry, ctx, key=f"var_{variant['variant_id']}_{metric}")
            with st.expander(texts.RESULT_RULES):
                render_checks(variant["governance"]["checks"], result["evidence"], subject, rules_by_id,
                              ctx, key_prefix=f"var_{variant['variant_id']}_rule", show_counterfactual=False)


def render_result(result: Mapping[str, Any], rules_by_id: Mapping[str, Dict[str, Any]],
                  ctx: ProofContext, names: Mapping[str, str],
                  asset_facts: Optional[Mapping[str, Any]] = None) -> None:
    st.caption(describe_idea(result["idea"]))
    render_mode_note(result)
    render_overall(result)
    render_comparison(result, ctx, names)
    if asset_facts is not None:
        render_asset_facts(asset_facts, result["idea"]["ticker"], ctx)
    st.subheader(texts.RESULT_RULES)
    render_checks(result["governance_after"]["checks"], result["evidence"], "portfolio_after",
                  rules_by_id, ctx, key_prefix="result_rule", show_counterfactual=True)
    render_variants(result, rules_by_id, ctx)
