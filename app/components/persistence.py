"""Widgets dont l'état survit à la navigation entre pages.

Streamlit efface l'état d'un widget absent de la page affichée. Comme pour le
formulaire du profil construit (components/profile_panel.py), une copie sous
une clé préfixée "_keep_" garde la valeur et la remet au retour sur la page.
"""
from __future__ import annotations

import streamlit as st

KEEP_PREFIX = "_keep_"


def kept_toggle(label: str, key: str) -> bool:
    """Interrupteur qui reste ouvert quand on revient sur la page."""
    if key not in st.session_state and KEEP_PREFIX + key in st.session_state:
        st.session_state[key] = st.session_state[KEEP_PREFIX + key]
    value = st.toggle(label, key=key)
    st.session_state[KEEP_PREFIX + key] = value
    return value
