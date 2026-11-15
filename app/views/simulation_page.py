"""Simulation : radiographie repliable, réglages manuels et conversation avec l'agent (US-03 à US-13).

Deux façons de soumettre une idée, un seul état : le champ de saisie (langage
naturel, filtré par le garde-fou puis traduit par des règles déterministes) et
les réglages manuels. Les deux écrivent dans le même fil et passent par le même
pipeline (get_analysis puis get_explanation).
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import streamlit as st

import data_source
import navigation
import session
import ui_texts as texts
from components import conversation, idea_panel, portfolio_chart, xray
from components.persistence import kept_toggle

SHOW_XRAY_KEY = "show_xray"


def render_chart(active: session.Active) -> None:
    """Composition du portefeuille de départ, dès le choix du profil (code déterministe, aucun agent)."""
    xray_data = session.load_xray(active)
    portfolio_chart.render_portfolio_chart(xray_data, active.names, session.display_name(active.profile))


def render_xray(active: session.Active) -> None:
    if not kept_toggle(texts.SIM_SHOW_XRAY, SHOW_XRAY_KEY):
        return
    xray_data = session.load_xray(active)
    if xray_data is not None:
        ctx = session.proof_context(xray_data["limits"])
        ctx.show_id = False  # registre propre à la radiographie
        session.guarded(lambda: xray.render_xray(xray_data, active.rules_by_id, ctx, active.names))


def render_manual(active: session.Active) -> None:
    with st.expander(texts.SIM_MANUAL, icon=":material/tune:"):
        if active.universe:
            current_weights = session.current_weight_displays(session.peek_xray(active))
            idea_panel.render_idea_panel(active.universe, active.portfolio, st.session_state.idea,
                                         session.submit_idea, current_weights)


def make_analysis_renderer(active: session.Active):
    """Réponse détaillée de la dernière idée, pour le profil actif."""
    def render_analysis(entry: Dict[str, Any], index: int) -> None:
        idea, adapted_message = idea_panel.effective_idea(entry["idea"], active.portfolio)
        key = session.analysis_key(active, idea)
        if entry.get("key") not in (None, key):
            # Réponse d'un autre profil ou d'un autre mode : son propre verdict, en compact.
            conversation.render_compact(entry, st.session_state.analysis_cache.get(entry["key"]))
            return
        # Clé posée au premier affichage si elle manquait (changement de mode).
        entry["key"] = key
        entry.setdefault("profile_name", session.display_name(active.profile))
        if adapted_message:
            st.info(adapted_message)
        if session.bedrock_waiting(active, idea):
            # Changement de profil ou de mode : aucun agent n'est lancé sans clic (quotas partagés).
            st.info(texts.RESULT_BEDROCK_PENDING)
            st.button(texts.RESULT_BEDROCK_RUN, key="run_bedrock_analysis", type="primary",
                      on_click=session.request_analysis)
            return
        result = session.load_analysis(active, idea)
        if result is None:
            return
        level = st.session_state.level or "novice"
        ctx = session.proof_context(result.get("limits"))
        ctx.level = level
        explanation = None
        if session.explanation_waiting(active, result, level):
            # Mode bedrock, niveau changé sans clic : l'explicateur attend une demande (quotas partagés).
            st.button(texts.EXPLANATION_RUN.format(level=texts.LEVEL_LABELS.get(level, level)),
                      key="run_bedrock_explanation", on_click=session.request_explanation)
        else:
            explanation = session.load_explanation(active, result, level)
        notice = session.safe_reference(lambda: data_source.get_threshold_notice(level), "", quiet=True)
        conversation.render_reply(
            entry, index, result, explanation, ctx, active.rules_by_id, active.names,
            lambda: session.load_asset_facts(active, idea["ticker"]), notice)
    return render_analysis


def cached_result(entry: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """Verdict d'une réponse ancienne, lu à sa propre clé (son profil, son mode), jamais au profil actif."""
    return st.session_state.analysis_cache.get(entry.get("key"))


def render() -> None:
    navigation.heading("simulation")
    active = session.require_profile()
    if active is None:
        return
    session.guarded(lambda: render_chart(active))
    session.guarded(lambda: render_xray(active))
    session.guarded(lambda: render_manual(active))
    history = st.session_state.chat_history
    analyses = [index for index, entry in enumerate(history) if entry.get("type") == "analysis"]
    latest = analyses[-1] if analyses else None
    # Accueil et exemples tant que l'utilisateur n'a rien demandé (les notes de profil ne comptent pas).
    if not any(entry.get("role") == "user" for entry in history):
        conversation.render_welcome(session.ask)
    render_analysis = make_analysis_renderer(active)
    for index, entry in enumerate(history):
        session.guarded(lambda: conversation.render_entry(
            entry, index, index == latest, render_analysis,
            cached_result, session.submit_idea))
    st.chat_input(texts.CHAT_PLACEHOLDER, key=session.CHAT_INPUT_KEY, on_submit=session.ask)
    navigation.next_step("simulation")


session.guarded(render)
