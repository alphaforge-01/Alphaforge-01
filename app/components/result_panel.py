"""Résultat d'une idée : verdict, avant/après, règles, faits sur l'actif, variantes (US-05 à US-09).

Le verdict est toujours visible en tête : un désaccord avec le profil (cas de
Robert) n'est jamais caché derrière un onglet. Le détail est réparti en
onglets, chacun dans sa zone (simulation, hypothèses, faits).
"""
from __future__ import annotations

from dataclasses import replace
from html import escape
from typing import Any, Callable, Dict, Mapping, Optional

import streamlit as st

import data_source
import ui_texts as texts
from components.evidence import ProofContext, index_by_key, lookup, render_card, render_value
from components.idea_panel import describe_idea
from components.rules import render_checks, sort_checks, status_badge, counterfactual_text
from components.style import html, pill, zone
from components.xray import render_composition


def split_verdict_html(governance: Mapping[str, Any]) -> str:
    """Pastilles "Financier" et "ESG" si le profil a une règle ESG, sinon rien (verdict global seul)."""
    verdicts = data_source.split_verdicts(dict(governance))
    if verdicts.get("esg") is None:
        return ""
    parts = [f'<span class="af-split-item">{escape(label)} {pill(status)}</span>'
             for label, status in ((texts.VERDICT_SPLIT_FINANCIAL, verdicts.get("financial")),
                                   (texts.VERDICT_SPLIT_ESG, verdicts.get("esg")))
             if status]
    return (f'<div class="af-split" title="{escape(texts.VERDICT_SPLIT_HELP)}">{"".join(parts)}</div>'
            if parts else "")


def render_verdict(result: Mapping[str, Any]) -> None:
    """Statut global après l'idée, avant l'idée, et les règles qui posent problème."""
    after = result["governance_after"]["overall_status"]
    before = result["governance_before"]["overall_status"]
    problems = [check for check in sort_checks(result["governance_after"]["checks"])
                if check["status"] != "compliant"]
    items = []
    for check in problems:
        line = texts.VERDICT_RULE.format(label=check["label_fr"],
                                         status=texts.STATUS_LABELS.get(check["status"], check["status"]))
        counterfactual = counterfactual_text(check)
        if counterfactual:
            line = f"{line} {counterfactual}"
        items.append(f"<li>{escape(line)}</li>")
    rules_html = f"<ul>{''.join(items)}</ul>" if items else ""
    html(
        f'<div class="af-verdict af-verdict--{escape(after)}">'
        f'<div class="af-verdict-head">{pill(after)}'
        f'<span>{escape(texts.VERDICT_HEADLINES.get(after, ""))}</span></div>'
        f'<div class="af-verdict-sub">'
        f'{escape(texts.VERDICT_TITLE.format(status=texts.STATUS_LABELS.get(after, after)))}. '
        f'{escape(texts.VERDICT_BEFORE.format(status=texts.STATUS_LABELS.get(before, before)))}.</div>'
        f'{split_verdict_html(result["governance_after"])}'
        f'{rules_html}'
        f'<div class="af-verdict-note">{escape(texts.VERDICT_FOOTNOTE)}</div></div>'
    )


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
    widths = [4, 2, 2, 2]
    for column, title in zip(st.columns(widths), (texts.COLUMN_MEASURE, texts.COLUMN_BEFORE,
                                                  texts.COLUMN_AFTER, texts.COLUMN_DELTA)):
        column.caption(title)
    for metric in texts.COMPARE_METRICS:
        before = lookup(index, metric, "portfolio_before")
        after = lookup(index, metric, "portfolio_after")
        delta = lookup(index, f"{metric}_delta", "portfolio_after")
        label_col, before_col, after_col, delta_col = st.columns(widths, vertical_alignment="center")
        # Un libellé qui nomme les titres d'un groupe serait faux pour l'autre colonne.
        label_col.markdown(texts.METRIC_LABELS.get(metric)
                           or (after or before or {}).get("label_fr", metric))
        for column, entry, subject in ((before_col, before, "portfolio_before"),
                                       (after_col, after, "portfolio_after")):
            with column:
                render_value(entry, ctx, key=f"cmp_{metric}_{subject}")
                if metric == "top_asset_weight" and top.get(subject):
                    st.caption(top[subject])
                if metric == "largest_correlated_group_weight":
                    snapshot = result["snapshot_before" if subject == "portfolio_before" else "snapshot_after"]
                    members = snapshot.get("correlated_group_members")
                    if members:
                        st.caption(", ".join(members))
        with delta_col:
            if delta is not None:
                render_value(delta, ctx, key=f"cmp_{metric}_delta")
    st.caption(texts.RESULT_AMOUNT_NOTE)
    with st.expander(texts.RESULT_COMPOSITION):
        render_composition(index, result["snapshot_after"], "portfolio_after", ctx, names, key_prefix="after_mix")


def render_asset_facts(facts: Mapping[str, Any], ticker: str, ctx: ProofContext) -> None:
    """Chiffres de l'actif seul : identiques pour tous les profils (US-09)."""
    ctx = replace(ctx, show_id=False)  # registre propre aux faits de l'actif
    index = index_by_key(facts["evidence"])
    metrics = texts.ASSET_FACTS_METRICS
    for column, metric in zip(st.columns(len(metrics)), metrics):
        with column:
            render_card(lookup(index, metric, ticker), ctx, key=f"asset_{ticker}_{metric}")
    st.caption(texts.ASSET_FACTS_NOTE)


def describe_variant(idea: Mapping[str, Any]) -> str:
    return describe_idea(idea)


def render_variants(result: Mapping[str, Any], rules_by_id: Mapping[str, Dict[str, Any]],
                    ctx: ProofContext) -> None:
    variants = result.get("variants") or []
    if not variants:
        st.caption(texts.VARIANTS_NONE)
        return
    st.caption(texts.VARIANTS_NOTICE)
    index = index_by_key(result["evidence"])
    for column, variant in zip(st.columns(len(variants)), variants):
        subject = f"variant:{variant['variant_id']}"
        with column, st.container(border=True):
            reason = texts.REASON_LABELS.get(variant["reason_code"], variant["reason_code"])
            st.markdown(f"**{texts.VARIANT_HEADER.format(variant_id=variant['variant_id'], reason=reason)}**")
            st.caption(describe_variant(variant["idea"]))
            status_badge(variant["governance"]["overall_status"])
            split = split_verdict_html(variant["governance"])
            if split:
                html(split)
            metrics = ("volatility_ann", "max_drawdown", "top_asset_weight", "defensive_share")
            for row_start in (0, 2):
                for cell, metric in zip(st.columns(2), metrics[row_start:row_start + 2]):
                    with cell:
                        entry = lookup(index, metric, subject)
                        st.caption((entry or {}).get("label_fr", metric))
                        render_value(entry, ctx, key=f"var_{variant['variant_id']}_{metric}")
            with st.expander(texts.VARIANT_RULES):
                render_checks(variant["governance"]["checks"], result["evidence"], subject, rules_by_id,
                              ctx, key_prefix=f"var_{variant['variant_id']}_rule", show_counterfactual=False)


def render_details(result: Mapping[str, Any], rules_by_id: Mapping[str, Dict[str, Any]],
                   ctx: ProofContext, names: Mapping[str, str],
                   load_asset_facts: Callable[[], Optional[Mapping[str, Any]]],
                   threshold_notice: str = "") -> None:
    """Détail d'une réponse, en onglets. `load_asset_facts()` est appelé dans l'onglet des faits."""
    ticker = result["idea"]["ticker"]
    variants = result.get("variants") or []
    variants_title = f"{texts.TAB_VARIANTS} ({len(variants)})" if variants else texts.TAB_VARIANTS
    # Zones distinctes (US-12) : simulation, hypothèses de l'équipe, faits sur l'actif.
    compare_tab, rules_tab, facts_tab, variants_tab = st.tabs(
        [texts.TAB_COMPARE, texts.TAB_RULES, texts.TAB_FACTS.format(ticker=ticker), variants_title])
    with compare_tab, zone("simulation", "compare"):
        render_comparison(result, ctx, names)
    with rules_tab, zone("assumptions", "rules"):
        if threshold_notice:
            st.caption(threshold_notice)
        render_checks(result["governance_after"]["checks"], result["evidence"], "portfolio_after",
                      rules_by_id, ctx, key_prefix="result_rule", show_counterfactual=True)
    with facts_tab, zone("facts", "asset"):
        asset_facts = load_asset_facts()
        if asset_facts is not None:
            render_asset_facts(asset_facts, ticker, ctx)
    with variants_tab, zone("simulation", "variants"):
        render_variants(result, rules_by_id, ctx)
