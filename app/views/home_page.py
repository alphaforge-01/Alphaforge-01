"""Accueil : niveau d'explication avec aperçu réel, puis choix d'un profil du datathon (US-01, US-10)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

import data_source
import navigation
import session
import ui_texts as texts
from components import profile_panel
from formatting import escape_dollars

def _choose_level(level: str) -> None:
    """Bouton Novice ou Pro : le niveau vit dans st.session_state.level."""
    st.session_state.level = level
    st.session_state.level_chosen = True


def _level_help(level: str, preview: Optional[Dict[str, Any]]) -> str:
    """Info-bulle du bouton : description du niveau et, si disponible, un passage réel de l'agent."""
    parts = [texts.HOME_LEVEL_DESCRIPTIONS[level]]
    if preview:
        parts.append(f"**{texts.HOME_PREVIEW_TITLE.format(level=texts.LEVEL_LABELS[level])}**")
        parts.append(escape_dollars(preview.get(level) or texts.NOT_AVAILABLE))
        parts.append("*" + texts.HOME_PREVIEW_SOURCE.format(
            persona=preview["persona"].capitalize(), model=preview.get("model_id") or texts.NOT_AVAILABLE,
            source=preview[f"{level}_source"]) + "*")
    return "\n\n".join(parts)


def render_level_preview() -> None:
    """Deux boutons centrés, Novice et Pro ; le survol d'un bouton montre un passage réel à ce niveau."""
    st.subheader(texts.HOME_LEVEL_TITLE, anchor=False)
    st.caption(texts.HOME_LEVEL_HOVER_HINT)
    preview = session.safe_reference(
        lambda: data_source.get_level_preview(st.session_state.profile_id or ""), None)
    # Aucun niveau choisi : aucun bouton mis en avant, le profil choisi ensuite fixera le sien.
    active = st.session_state.level if st.session_state.level in texts.LEVEL_LABELS else None
    with st.container(horizontal=True, horizontal_alignment="center", gap="small", key="home-level-row"):
        for level in texts.LEVEL_LABELS:
            chosen = level == active
            st.button(texts.LEVEL_LABELS[level], key=f"home_level_{level}", help=_level_help(level, preview),
                      type="primary" if chosen else "secondary",
                      icon=":material/check:" if chosen else None,
                      on_click=_choose_level, args=(level,))
    if active is None:
        st.caption(texts.HOME_LEVEL_DEFAULT)


def render() -> None:
    if st.session_state.pop(session.GO_SIMULATION_KEY, False):
        st.switch_page(navigation.ALL_PAGES["simulation"].path)
    navigation.heading("home")
    # Le niveau se règle avant le choix du profil : le choisir ensuite ne l'écrase plus (level_chosen).
    session.guarded(render_level_preview)
    personas = session.personas()
    st.subheader(texts.HOME_PROFILES_TITLE, anchor=False)
    if not personas:
        session.show_personas_error()
    else:
        profile_panel.render_persona_cards(
            personas, st.session_state.profile_id,
            on_select=lambda profile_id: session.select_profile_and_go(profile_id, personas))
    navigation.link("custom", texts.HOME_CUSTOM_LINK)
    navigation.next_step("home")


session.guarded(render)
