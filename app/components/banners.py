"""Bandeaux affichés en haut de chaque écran : avertissement et données d'essai."""
from __future__ import annotations

import streamlit as st

import ui_texts as texts


def render_disclaimer() -> None:
    """Avertissement obligatoire (US-12), au texte fixe."""
    st.info(texts.DISCLAIMER)


def render_fixture_banner() -> None:
    """Bandeau visible dès que les chiffres viennent des fixtures (is_fixture)."""
    st.warning(texts.FIXTURE_BANNER)
