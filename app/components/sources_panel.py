"""Sources et méthode (US-11) : provenance des données, limites fixes, univers d'actifs."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

import streamlit as st

import ui_texts as texts


def _relabel(rows: List[Mapping[str, Any]], columns: Mapping[str, str]) -> List[Dict[str, Any]]:
    return [{label: row.get(key, "") for key, label in columns.items()} for row in rows]


def render_sources_panel(sources: List[Dict[str, Any]], limits: List[Dict[str, Any]],
                         threshold_notice: str, universe: List[Dict[str, Any]], level: str) -> None:
    st.subheader(texts.SOURCES_TITLE)
    st.dataframe(_relabel(sources, texts.SOURCES_COLUMNS), hide_index=True, width="stretch")
    st.caption(texts.SOURCES_NOTE)

    st.subheader(texts.METHOD_TITLE)
    st.caption(texts.METHOD_INTRO)
    text_key = "text_pro" if level == "pro" else "text_novice"
    for limit in limits:
        st.markdown(f"- **{limit['limit_id']}** : {limit.get(text_key, '')}")
    if threshold_notice:
        st.markdown(f"- {threshold_notice}")

    with st.expander(texts.UNIVERSE_TITLE):
        rows = [{**asset,
                 "asset_class": texts.ASSET_CLASS_LABELS.get(asset["asset_class"], asset["asset_class"]),
                 "sector": texts.SECTOR_LABELS.get(asset["sector"], asset["sector"])}
                for asset in universe]
        st.dataframe(_relabel(rows, texts.UNIVERSE_COLUMNS), hide_index=True, width="stretch")
