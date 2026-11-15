"""Fil de la conversation : demandes en langage naturel, réglages manuels et réponses de l'agent.

Chaque réponse est courte (verdict, points clés cliquables, résumé de l'explication,
avertissement), puis dépliable : détail par zones, explication complète, sources et
limites, trace. Le texte vient toujours de `get_explanation` (agent ou gabarit) et
les chiffres du registre de preuves : ce module n'invente ni ne calcule rien.
Seule la réponse la plus récente est détaillée ; les précédentes restent compactes.
"""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Dict, List, Mapping, Optional

import streamlit as st

import ui_texts as texts
from components import explanation_panel, idea_panel, result_panel, trace_panel
from components.evidence import ProofContext, source_line
from components.persistence import kept_toggle
from components.rules import render_key_points
from components.style import html, pill
from formatting import escape_dollars, summary_section


def _guard_caption(action: Optional[str]) -> Optional[str]:
    if action is None:
        return None
    return texts.CHAT_GUARD_STATUS.get(action, texts.CHAT_GUARD_STATUS["not_run"])


def _topics(topics: List[str]) -> str:
    return ", ".join(texts.GUARDRAIL_TOPIC_LABELS.get(topic, topic) for topic in topics) or texts.GUARDRAIL_NO_TOPIC


def render_welcome(on_example: Callable[[str], None]) -> None:
    with st.chat_message("assistant"):
        st.markdown(texts.CHAT_WELCOME)
        with st.container(horizontal=True):
            for position, example in enumerate(texts.CHAT_EXAMPLES):
                st.button(example, key=f"chat_example_{position}", on_click=on_example, args=(example,))


def _render_refused(entry: Mapping[str, Any]) -> None:
    st.error(texts.CHAT_REFUSED.format(topics=_topics(entry.get("topics") or [])))
    st.caption(texts.CHAT_REFUSED_BY[entry.get("by", "local")])
    guard = _guard_caption(entry.get("guard_action"))
    if guard and entry.get("by") == "local":
        st.caption(guard)
    st.markdown(texts.CHAT_REFUSED_HELP)


def _render_clarify(entry: Mapping[str, Any], index: int, on_choice: Callable[..., None]) -> None:
    parsed = entry["parsed"]
    reason = parsed.get("reason")
    tickers = parsed.get("tickers") or []
    weight = parsed.get("target_weight")
    funding = parsed.get("funding_ticker")
    question = texts.CHAT_CLARIFY.get(reason, texts.CHAT_CLARIFY["not_an_idea"])
    st.markdown(question.format(
        tickers=", ".join(tickers), unknown=", ".join(parsed.get("unknown_tokens") or []) or "?",
        funding=funding or ""))
    funding_source = "from_ticker" if funding else "pro_rata"
    choices = []
    # Poids manquant, ou décimal (arrondi proposé) : un bouton par poids, même actif et même financement.
    if reason in ("missing_weight", "weight_out_of_range") and len(tickers) == 1:
        choices = [idea_panel.make_idea(tickers[0], option, funding_source, funding)
                   for option in parsed.get("suggested_weights") or []]
    elif reason == "several_assets" and weight is not None and 0 < weight <= 1:
        choices = [idea_panel.make_idea(ticker, weight, funding_source, funding)
                   for ticker in tickers if ticker != funding]
    if choices:
        with st.container(horizontal=True):
            for position, idea in enumerate(choices):
                # Le libellé montre la source des fonds : le choix n'en perd aucune.
                label = idea_panel.describe_idea(idea)
                st.button(label, key=f"clarify_{index}_{position}", on_click=on_choice,
                          args=(idea, texts.CHAT_CHOICE.format(choice=label)))
    else:
        st.caption(texts.CHAT_CLARIFY_MANUAL)


def render_compact(entry: Mapping[str, Any], result: Optional[Mapping[str, Any]]) -> None:
    """Réponse ancienne : son propre verdict (lu à sa clé), son profil et son idée."""
    describe = texts.CHAT_COMPACT.format(idea=idea_panel.describe_idea(entry["idea"]),
                                         name=entry.get("profile_name") or texts.HEADER_NONE)
    if result is None:
        st.caption(texts.CHAT_PREVIOUS.format(idea=describe))
        return
    status = result["governance_after"]["overall_status"]
    html(f'{pill(status)} <span>{escape(describe)}</span>'
         f'{result_panel.split_verdict_html(result["governance_after"])}')


def _render_sources_and_limits(result: Mapping[str, Any], ctx: ProofContext, threshold_notice: str) -> None:
    sources = sorted({source for entry in result["evidence"].values() for source in entry.get("source_ids") or []})
    st.markdown(f"**{texts.CHAT_SOURCES}**")
    st.markdown("\n".join(f"- {source_line(source, ctx)}" for source in sources) or texts.PROOF_NONE)
    st.markdown(f"**{texts.CHAT_LIMITS}**")
    text_key = "text_pro" if ctx.level == "pro" else "text_novice"
    lines = [f"- {limit.get(text_key) or limit.get('limit_id')}" for limit in result.get("limits") or []]
    if threshold_notice:
        lines.append(f"- {threshold_notice}")
    st.markdown("\n".join(lines) or texts.PROOF_NONE)


def render_reply(entry: Mapping[str, Any], index: int, result: Mapping[str, Any],
                 explanation: Optional[Mapping[str, Any]], ctx: ProofContext,
                 rules_by_id: Mapping[str, Dict[str, Any]], names: Mapping[str, str],
                 load_asset_facts: Callable[[], Optional[Mapping[str, Any]]],
                 threshold_notice: str) -> None:
    """Réponse détaillée : courte d'abord, le reste derrière un interrupteur et des onglets."""
    result_panel.render_mode_note(result)
    result_panel.render_verdict(result)
    st.caption(texts.CHAT_KEY_POINTS)
    render_key_points(result["governance_after"]["checks"], result["evidence"], "portfolio_after",
                      rules_by_id, ctx, key_prefix=f"kp{index}")
    if explanation is not None:
        explanation_panel.render_origin(explanation)
        summary = summary_section(explanation.get("rendered_markdown", ""))
        if summary:
            st.markdown(escape_dollars(summary))
    st.caption(texts.DISCLAIMER)
    if not kept_toggle(texts.CHAT_SHOW_DETAILS, f"details_{index}"):
        return
    details_tab, text_tab, sources_tab, trace_tab = st.tabs(
        [texts.CHAT_TAB_DETAILS, texts.CHAT_TAB_TEXT, texts.CHAT_TAB_SOURCES, texts.CHAT_TAB_TRACE])
    with details_tab:
        result_panel.render_details(result, rules_by_id, ctx, names, load_asset_facts, threshold_notice)
    with text_tab:
        if explanation is not None:
            explanation_panel.render_explanation(explanation, result, ctx)
    with sources_tab:
        _render_sources_and_limits(result, ctx, threshold_notice)
    with trace_tab:
        trace_panel.render_trace(result, explanation)


def render_entry(entry: Mapping[str, Any], index: int, is_latest_analysis: bool,
                 render_analysis: Callable[[Mapping[str, Any], int], None],
                 cached_result: Callable[[Mapping[str, Any]], Optional[Mapping[str, Any]]],
                 on_choice: Callable[..., None]) -> None:
    role = entry.get("role")
    if role == "user":
        avatar = ":material/tune:" if entry.get("origin") == "manual" else "user"
        with st.chat_message("user", avatar=avatar):
            st.markdown(entry["text"])
        return
    with st.chat_message("assistant", avatar=":material/neurology:"):
        kind = entry.get("type")
        if kind == "note":
            st.caption(entry["text"])
        elif kind == "info":
            st.info(entry["text"])
        elif kind == "refused":
            _render_refused(entry)
        elif kind == "clarify":
            _render_clarify(entry, index, on_choice)
        elif kind == "analysis":
            st.caption(texts.CHAT_UNDERSTOOD.format(idea=idea_panel.describe_idea(entry["idea"])))
            guard = _guard_caption(entry.get("guard_action"))
            if guard:
                st.caption(guard)
            if is_latest_analysis:
                render_analysis(entry, index)
            else:
                render_compact(entry, cached_result(entry))
