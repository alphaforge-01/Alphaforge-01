"""Accueil : niveau d'explication avec aperçu réel, puis choix d'un profil du datathon (US-01, US-10)."""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

import data_source
import navigation
import session
import ui_texts as texts
from components import profile_panel, style

HOME_LEVEL_KEY = "home_level"


def _set_level_from_toggle() -> None:
    """Interrupteur : éteint = Novice, allumé = Pro. Le niveau vit dans st.session_state.level."""
    st.session_state.level = "pro" if st.session_state[HOME_LEVEL_KEY] else "novice"
    st.session_state.level_chosen = True


def _bubble_item(level: str, preview: Dict[str, Any], active: str) -> Dict[str, Any]:
    return {
        "label": texts.LEVEL_LABELS[level],
        "title": texts.HOME_PREVIEW_TITLE.format(level=texts.LEVEL_LABELS[level]),
        "description": texts.HOME_LEVEL_DESCRIPTIONS[level],
        "example": preview.get(level) or texts.NOT_AVAILABLE,
        "source": texts.HOME_PREVIEW_SOURCE.format(
            persona=preview["persona"].capitalize(), model=preview.get("model_id") or texts.NOT_AVAILABLE,
            source=preview[f"{level}_source"]),
        "active": level == active,
    }


def render_level_preview() -> None:
    """Interrupteur Novice / Pro centré ; au survol d'un niveau, une bulle montre un passage réel."""
    st.subheader(texts.HOME_LEVEL_TITLE, anchor=False)
    st.caption(texts.HOME_LEVEL_HOVER_HINT)
    preview = session.safe_reference(
        lambda: data_source.get_level_preview(st.session_state.profile_id or ""), None)
    active = st.session_state.level if st.session_state.level in texts.LEVEL_LABELS else "novice"
    st.session_state[HOME_LEVEL_KEY] = active == "pro"
    with st.container(horizontal=True, horizontal_alignment="center", vertical_alignment="center",
                      gap="small", key="home-level-row"):
        if preview:
            style.level_bubble(_bubble_item("novice", preview, active), "left")
        st.toggle(texts.SIDEBAR_LEVEL, key=HOME_LEVEL_KEY, on_change=_set_level_from_toggle,
                  help=texts.EXPLANATION_LEVEL_HELP, label_visibility="collapsed")
        if preview:
            style.level_bubble(_bubble_item("pro", preview, active), "right")


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
