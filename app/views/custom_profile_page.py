"""Créer un profil fictif : colonne centrée, quatre étapes et récapitulatif en direct (US-02).

Le bouton de l'aperçu active le profil puis ouvre la simulation. Comme sur l'accueil,
le passage de page se fait hors du rappel du bouton : le rappel pose un drapeau, que
l'exécution suivante lit.
"""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

import navigation
import session
import ui_texts as texts
from components import profile_panel
from components.banners import render_page_heading


def _use_and_go(persona: Dict[str, Any]) -> None:
    session.use_custom_profile(persona)
    st.session_state[session.GO_SIMULATION_KEY] = True


def render() -> None:
    if st.session_state.pop(session.GO_SIMULATION_KEY, False):
        st.switch_page(navigation.ALL_PAGES["simulation"].path)
    # Une colonne étroite et centrée (style dans components/style.py).
    with st.container(key="custom-wrap"):
        # Titre accrocheur ; le nom court de la page reste celui de la barre du haut.
        render_page_heading(texts.CUSTOM_HERO_TITLE, texts.PAGE_INTROS["custom"])
        personas = session.personas()
        if not personas:
            session.show_personas_error()
            return
        is_custom = st.session_state.profile_id == session.CUSTOM_ID
        profile_panel.render_custom_profile_form(
            personas, st.session_state.custom_persona if is_custom else None, on_use=_use_and_go)


session.guarded(render)
