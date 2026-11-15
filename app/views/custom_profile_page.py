"""Créer un profil fictif : formulaire existant, inchangé (US-02)."""
from __future__ import annotations

import streamlit as st

import navigation
import session
import ui_texts as texts
from components import profile_panel


def render() -> None:
    navigation.heading("custom")
    personas = session.personas()
    if not personas:
        session.show_personas_error()
        return
    is_custom = st.session_state.profile_id == session.CUSTOM_ID
    profile_panel.render_custom_profile_form(
        personas, st.session_state.custom_persona if is_custom else None, on_use=session.use_custom_profile)
    if is_custom:
        st.success(texts.CUSTOM_ACTIVE)
    navigation.next_step("custom")


session.guarded(render)
