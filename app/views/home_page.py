"""Accueil : promesse, trois étapes, l'aisance du visiteur, puis les trois personas côte à côte (US-01, US-10).

Un bouton de carte choisit le profil et ouvre la page Simulation. Le passage de page se
fait hors du rappel du bouton (`st.switch_page` est interdit dans un rappel) : le rappel
pose un drapeau, l'exécution suivante de cette page le lit et change de page.
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict, Optional

import streamlit as st

import data_source
import navigation
import session
import ui_texts as texts
from components import profile_panel
from components.style import html
from formatting import escape_dollars

LEVEL_WIDGET_KEY = "home_level"


def render_hero() -> None:
    """Titre-promesse, phrase d'appui et les trois étapes numérotées."""
    html(f'<div class="af-hero"><h1>{escape(texts.HOME_TITLE)}</h1>'
         f'<p>{escape(texts.HOME_SUBTITLE)}</p></div>')
    steps = "".join(
        f'<li class="af-step" title="{escape(detail)}"><span class="af-step-n" aria-hidden="true">{index}</span>'
        f'{escape(title)}</li>'
        for index, (title, detail) in enumerate(texts.HOME_STEPS, start=1))
    html(f'<ol class="af-steps" aria-label="{escape(texts.HOME_STEPS_LABEL)}">{steps}</ol>')


def _on_level_change() -> None:
    """Rappel du choix d'explication : le niveau vit dans st.session_state.level."""
    value = st.session_state.get(LEVEL_WIDGET_KEY)
    if value in texts.EXPLANATION_STYLE_LABELS:
        session.sync_level(LEVEL_WIDGET_KEY)


def _level_help(preview: Optional[Dict[str, Any]]) -> str:
    """Info-bulle : description des deux styles et, si disponible, un passage réel de l'agent pour chacun."""
    parts = [texts.HOME_LEVEL_HELP]
    for level in texts.EXPLANATION_STYLE_LABELS:
        parts.append(texts.HOME_LEVEL_DESCRIPTIONS[level])
        if preview and preview.get(level):
            label = texts.EXPLANATION_STYLE_LABELS[level].lower()
            parts.append(f"**{texts.HOME_PREVIEW_TITLE.format(level=label)}**")
            parts.append(escape_dollars(preview[level]))
            # Chaque passage cite son propre fichier de trace (un fichier par niveau).
            parts.append("*" + texts.HOME_PREVIEW_SOURCE.format(
                persona=preview["persona"].capitalize(), model=preview.get("model_id") or texts.NOT_AVAILABLE,
                source=preview.get(f"{level}_source", texts.NOT_AVAILABLE)) + "*")
    return "\n\n".join(parts)


def render_level_choice() -> None:
    """Question d'aisance avant les cartes ; la réponse règle le style d'explication (novice ou pro)."""
    preview = session.safe_reference(
        lambda: data_source.get_level_preview(st.session_state.profile_id or ""), None, quiet=True)
    level = st.session_state.level if st.session_state.level in texts.EXPLANATION_STYLE_LABELS else None
    st.session_state[LEVEL_WIDGET_KEY] = level
    with st.container(horizontal=True, vertical_alignment="bottom", gap="medium", key="home-level-row"):
        st.segmented_control(texts.HOME_LEVEL_TITLE, options=list(texts.HOME_COMFORT_LABELS),
                             format_func=texts.HOME_COMFORT_LABELS.get, key=LEVEL_WIDGET_KEY,
                             on_change=_on_level_change, help=_level_help(preview),
                             label_visibility="visible")
        st.caption(texts.HOME_LEVEL_DESCRIPTIONS[level] if level else texts.HOME_LEVEL_DEFAULT)


def render() -> None:
    if st.session_state.pop(session.GO_SIMULATION_KEY, False):
        st.switch_page(navigation.ALL_PAGES["simulation"].path)
    render_hero()
    session.guarded(render_level_choice)
    personas = session.personas()
    if not personas:
        session.show_personas_error()
    else:
        profile_panel.render_persona_cards(
            personas, st.session_state.profile_id,
            on_select=lambda profile_id: session.select_profile_and_go(profile_id, personas))
    with st.container(horizontal=True, horizontal_alignment="right", key="home-foot"):
        navigation.link("custom", texts.HOME_CUSTOM_LINK)


session.guarded(render)
