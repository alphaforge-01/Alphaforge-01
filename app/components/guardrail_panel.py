"""Test du garde-fou Bedrock avec des requêtes prédéfinies (US-14).

Aucun texte libre : les requêtes viennent de tests/fixtures/guardrail_prompts.json
(flux C). Le verdict vient du garde-fou (`check_request`), jamais de l'interface.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping

import streamlit as st

import ui_texts as texts

PENDING_KEY = "guardrail_pending"
HISTORY_KEY = "guardrail_history"


def _queue(prompt: Mapping[str, Any]) -> None:
    st.session_state[PENDING_KEY] = dict(prompt)


def _clear() -> None:
    st.session_state[HISTORY_KEY] = []


def _render_verdict(result: Mapping[str, Any]) -> None:
    action = result.get("action")
    if action == "intervened":
        topics = ", ".join(texts.GUARDRAIL_TOPIC_LABELS.get(topic, topic)
                           for topic in result.get("denied_topics") or []) or texts.GUARDRAIL_NO_TOPIC
        st.error(texts.GUARDRAIL_RESULT_DENIED.format(topics=topics))
    elif action == "none":
        st.success(texts.GUARDRAIL_RESULT_ALLOWED)
    else:
        st.info(texts.GUARDRAIL_RESULT_NOT_RUN)


def _render_prompt_list(title: str, prompts: List[Dict[str, Any]]) -> None:
    st.markdown(f"**{title}**")
    for prompt in prompts:
        text_col, button_col = st.columns([5, 1], vertical_alignment="center")
        text_col.markdown(prompt["text"])
        button_col.button(texts.GUARDRAIL_TEST, key=f"guard_{prompt['id']}", on_click=_queue, args=(prompt,))


def render_guardrail_panel(mode: str, prompts: List[Dict[str, Any]],
                           run_check: Callable[[str], Dict[str, Any]]) -> None:
    """`run_check(text)` interroge le garde-fou dans le mode courant et rend un GuardrailResult."""
    st.session_state.setdefault(HISTORY_KEY, [])
    st.caption(texts.GUARDRAIL_INTRO)
    if mode != "bedrock":
        st.info(texts.GUARDRAIL_OFFLINE)

    pending = st.session_state.pop(PENDING_KEY, None)
    if pending is not None:
        with st.spinner(texts.GUARDRAIL_SPINNER):
            result = run_check(pending["text"])
        st.session_state[HISTORY_KEY].append({"prompt": pending, "result": result})

    allowed = [p for p in prompts if p.get("expected") == "allowed"]
    denied = [p for p in prompts if p.get("expected") != "allowed"]
    left, right = st.columns(2)
    with left:
        _render_prompt_list(texts.GUARDRAIL_ALLOWED, allowed)
    with right:
        _render_prompt_list(texts.GUARDRAIL_DENIED, denied)

    history = st.session_state[HISTORY_KEY]
    if history:
        st.subheader(texts.GUARDRAIL_HISTORY)
        st.button(texts.GUARDRAIL_CLEAR, key="guard_clear", on_click=_clear)
        for item in reversed(history):
            with st.chat_message("user"):
                st.write(item["prompt"]["text"])
            with st.chat_message("assistant"):
                _render_verdict(item["result"])
                st.caption(texts.GUARDRAIL_EXPECTED.get(item["prompt"].get("expected"), ""))
