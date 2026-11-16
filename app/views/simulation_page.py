"""Simulation : en-tête du profil, contexte en onglets et conversation avec l'agent (US-03 à US-13).

Mise en page : une colonne centrée. En haut, le profil actif et la progression ; puis une
carte à trois onglets (portefeuille, radiographie, réglages manuels) ; puis la conversation.

Deux façons de soumettre une idée, un seul état : le champ de saisie (langage
naturel, filtré par le garde-fou puis traduit par des règles déterministes) et
les réglages manuels. Les deux écrivent dans le même fil et passent par le même
pipeline (get_analysis puis get_explanation).
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict, Mapping, Optional

import streamlit as st

import data_source
import navigation
import session
import ui_texts as texts
from components import conversation, idea_panel, portfolio_chart, profile_panel, xray
from components.style import html
from formatting import format_horizon


def render_profile_header(active: session.Active) -> None:
    """Bande du profil actif : initiale en couleur, titre, objectif et repères, lien pour changer."""
    profile = active.profile
    profile_id = st.session_state.profile_id or ""
    accent = profile_panel.PERSONA_ACCENTS.get(profile_id, profile_panel.CUSTOM_ACCENT)
    name = session.display_name(profile)
    tags = (
        (texts.PERSONA_RISK, texts.RISK_LABELS.get(profile.get("risk_tolerance"), "")),
        (texts.PERSONA_HORIZON, format_horizon(profile["horizon_years_min"], profile["horizon_years_max"])),
    )
    tags_html = "".join(f'<span class="af-pc-tag">{escape(label)} <b>{escape(str(value))}</b></span>'
                        for label, value in tags if value)
    with st.container(horizontal=True, vertical_alignment="center", key="sim-head"):
        html(f'<div class="af-sim-head" style="--af-accent: {accent}">'
             f'<div class="af-pc-avatar" aria-hidden="true">{escape(name[:1])}</div>'
             f'<div><h1>{escape(texts.SIM_HERO_TITLE.format(name=name))}</h1>'
             f'<div class="af-sim-sub">{escape(profile.get("objective", ""))}</div>'
             f'<div class="af-pc-facts">{tags_html}</div></div></div>')
        st.space("stretch")
        navigation.link("home", texts.SIM_CHANGE_PROFILE)


def render_progress(active: session.Active) -> None:
    history = st.session_state.chat_history
    has_idea = any(entry.get("type") == "analysis" for entry in history)
    has_verdict = bool(st.session_state.analysis_cache)
    has_explanation = bool(st.session_state.explanation_cache)
    states = (True, has_idea, has_verdict, has_explanation)
    parts = []
    for index, (label, done) in enumerate(zip(texts.SIM_PROGRESS, states)):
        state = "done" if done else "active" if index == sum(states) else ""
        parts.append(
            f'<span class="af-progress-step af-progress-step--{state}">'
            f'<span class="af-progress-dot"></span>{label}</span>'
        )
        if index < len(texts.SIM_PROGRESS) - 1:
            parts.append('<span class="af-progress-line"></span>')
    html('<div class="af-progress" aria-label="Progression du parcours">' + "".join(parts) + "</div>")


def render_chart(active: session.Active) -> None:
    """Composition du portefeuille de départ, dès le choix du profil (code déterministe, aucun agent)."""
    xray_data = session.load_xray(active)
    portfolio_chart.render_portfolio_chart(xray_data, active.names, session.display_name(active.profile))


def render_xray(active: session.Active) -> None:
    xray_data = session.load_xray(active)
    if xray_data is not None:
        ctx = session.proof_context(xray_data["limits"])
        ctx.show_id = False  # registre propre à la radiographie
        session.guarded(lambda: xray.render_xray(xray_data, active.rules_by_id, ctx, active.names))


def render_manual(active: session.Active) -> None:
    if active.universe:
        current_weights = session.current_weight_displays(session.peek_xray(active))
        idea_panel.render_idea_panel(active.universe, active.portfolio, st.session_state.idea,
                                     session.submit_idea, current_weights)


def render_context(active: session.Active) -> None:
    """Une carte, trois onglets : le portefeuille d'abord, le reste à un clic."""
    with st.container(key="sim-context"):
        chart_tab, xray_tab, manual_tab = st.tabs(list(texts.SIM_TABS))
        with chart_tab:
            session.guarded(lambda: render_chart(active))
        with xray_tab:
            session.guarded(lambda: render_xray(active))
        with manual_tab:
            session.guarded(lambda: render_manual(active))


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


# Longueur du fil au dernier affichage : un fil plus long signifie un nouvel échange.
SEEN_CHAT_KEY = "_chat_seen_len"
_SCROLL_SCRIPT = """<script>(function () {
  var tries = 0;
  function go() {
    var el = document.querySelector(".%s");
    if (el) { el.scrollIntoView({behavior: "smooth", block: "start"}); }
    else if (tries++ < 30) { setTimeout(go, 100); }
  }
  setTimeout(go, 150);
})();</script>"""


def scroll_to_latest_exchange(history) -> None:
    """Après un nouvel échange, fait défiler la page jusqu'au dernier message de l'utilisateur,
    la réponse de l'agent juste dessous. Rien au premier affichage ni quand rien n'a changé."""
    seen = st.session_state.get(SEEN_CHAT_KEY, len(history))
    st.session_state[SEEN_CHAT_KEY] = len(history)
    if len(history) <= seen:
        return
    users = [index for index, entry in enumerate(history) if entry.get("role") == "user"]
    if users:
        # Script fixe, seule la classe générée par le code (index entier) varie : aucun texte saisi n'y entre.
        st.html(_SCROLL_SCRIPT % f"st-key-chat-user-{int(users[-1])}", unsafe_allow_javascript=True)


def cached_result(entry: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """Verdict d'une réponse ancienne, lu à sa propre clé (son profil, son mode), jamais au profil actif."""
    return st.session_state.analysis_cache.get(entry.get("key"))


def render() -> None:
    with st.container(key="sim-wrap"):
        has_profile = _render_page()
    # Champ de saisie hors de la colonne : au niveau de la page, Streamlit le fixe en bas de
    # l'écran, visible sans défiler.
    if has_profile:
        st.chat_input(texts.CHAT_PLACEHOLDER, key=session.CHAT_INPUT_KEY, on_submit=session.ask)


def _render_page() -> bool:
    """Contenu de la colonne centrée ; False si aucun profil n'est actif."""
    active = session.require_profile()
    if active is None:
        return False
    session.guarded(lambda: render_profile_header(active))
    render_progress(active)
    render_context(active)
    html(f'<div class="af-sim-section">{escape(texts.SIM_CHAT_TITLE)}</div>')
    st.caption(texts.PAGE_INTROS["simulation"])
    history = st.session_state.chat_history
    analyses = [index for index, entry in enumerate(history) if entry.get("type") == "analysis"]
    latest = analyses[-1] if analyses else None
    # Accueil et exemples tant que l'utilisateur n'a rien demandé (les notes de profil ne comptent pas).
    if not any(entry.get("role") == "user" for entry in history):
        conversation.render_welcome(session.ask)
    render_analysis = make_analysis_renderer(active)
    if session.rephrase_pending():
        with st.spinner(texts.CHAT_REPHRASE_SPINNER):
            session.guarded(session.rephrase_all)
    for index, entry in enumerate(history):
        session.guarded(lambda: conversation.render_entry(
            entry, index, index == latest, render_analysis,
            cached_result, session.submit_idea, session.ask))
    scroll_to_latest_exchange(history)
    navigation.next_step("simulation")
    return True


session.guarded(render)
