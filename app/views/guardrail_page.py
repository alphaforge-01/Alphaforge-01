"""Page de vérification : test du garde-fou Bedrock avec des requêtes prédéfinies (US-14)."""
from __future__ import annotations

import streamlit as st

import data_source
import navigation
import session
from components import guardrail_panel


def render() -> None:
    navigation.heading("guardrail")
    mode = st.session_state.mode
    prompts = session.safe_reference(data_source.get_guardrail_prompts, [])
    guardrail_panel.render_guardrail_panel(mode, prompts, lambda text: data_source.check_request(mode, text))
    navigation.next_step("guardrail")


session.guarded(render)
