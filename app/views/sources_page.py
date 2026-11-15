"""Page de vérification : sources des données, limites fixes et univers des actifs (US-11, US-12)."""
from __future__ import annotations

import streamlit as st

import data_source
import navigation
import session
from components import sources_panel


def render() -> None:
    navigation.heading("sources")
    level = st.session_state.level or "novice"
    sources_panel.render_sources_panel(
        session.safe_reference(data_source.get_sources, []),
        session.safe_reference(data_source.get_reference_limits, []),
        session.safe_reference(lambda: data_source.get_threshold_notice(level), ""),
        session.safe_reference(data_source.get_universe, []),
        level,
    )


session.guarded(render)
