"""Choix du profil fictif : cartes des personas (US-01).

Le formulaire de profil construit (US-02, tâche D2b) viendra ici.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import streamlit as st

import ui_texts as texts
from formatting import format_cad, format_horizon

# Ordre d'affichage : Robert d'abord, c'est la scène 1 de la démo.
PERSONA_ORDER = ("robert", "amira", "mateo")


def ordered_ids(personas: Dict[str, Any]) -> List[str]:
    known = [pid for pid in PERSONA_ORDER if pid in personas]
    others = sorted(pid for pid in personas if pid not in PERSONA_ORDER)
    return known + others


def _identity_line(persona: Dict[str, Any]) -> Optional[str]:
    parts = []
    if persona.get("age") is not None:
        parts.append(texts.PERSONA_AGE.format(age=persona["age"]))
    if persona.get("occupation_fr"):
        parts.append(persona["occupation_fr"])
    return ", ".join(parts) if parts else None


def _render_card(profile_id: str, persona: Dict[str, Any], is_selected: bool,
                 on_select: Callable[[str], None]) -> None:
    profile = persona["profile"]
    with st.container(border=True):
        st.subheader(profile["display_name"])
        st.badge(texts.FICTIONAL_BADGE, color="gray")
        identity = _identity_line(persona)
        if identity:
            st.caption(identity)
        if persona.get("summary_fr"):
            st.write(persona["summary_fr"])
        st.markdown(
            f"**{texts.PERSONA_RISK}** : {texts.RISK_LABELS[profile['risk_tolerance']]}  \n"
            f"**{texts.PERSONA_HORIZON}** : "
            f"{format_horizon(profile['horizon_years_min'], profile['horizon_years_max'])}  \n"
            f"**{texts.PERSONA_OBJECTIVE}** : {profile['objective']}  \n"
            f"**{texts.PERSONA_EXPERIENCE}** : {texts.EXPERIENCE_LABELS[profile['experience']]}  \n"
            f"**{texts.PERSONA_CAPITAL}** : {format_cad(profile['capital_cad'])}"
        )
        st.button(
            texts.SELECTED_PROFILE if is_selected else texts.CHOOSE_PROFILE,
            key=f"choose_profile_{profile_id}",
            type="primary" if is_selected else "secondary",
            width="stretch",
            on_click=on_select,
            args=(profile_id,),
        )


def render_persona_cards(personas: Dict[str, Any], selected_id: Optional[str],
                         on_select: Callable[[str], None]) -> None:
    """Une carte par persona, côte à côte. `on_select(profile_id)` est appelé au clic."""
    ids = ordered_ids(personas)
    for column, profile_id in zip(st.columns(len(ids)), ids):
        with column:
            _render_card(profile_id, personas[profile_id], profile_id == selected_id, on_select)
