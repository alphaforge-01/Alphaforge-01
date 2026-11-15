"""Idée de placement par sélecteurs, sans texte libre (US-04, US-09).

L'interface ne fait que composer une `InvestmentIdea`. Sa validation complète
(poids, source des fonds) est faite par le pipeline du flux C.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import streamlit as st

import ui_texts as texts
from formatting import format_pct

ASSET_KEY = "idea_asset"
WEIGHT_KEY = "idea_weight"
FUNDING_KEY = "idea_funding"
FUNDING_TICKER_KEY = "idea_funding_ticker"


def make_idea(ticker: str, target_weight: float, funding_source: str = "pro_rata",
              funding_ticker: Optional[str] = None) -> Dict[str, Any]:
    return {
        "ticker": ticker,
        "target_weight": round(float(target_weight), 4),
        "funding_source": funding_source,
        "funding_ticker": funding_ticker if funding_source == "from_ticker" else None,
    }


def held_tickers(portfolio: Mapping[str, Any]) -> List[str]:
    return [position["ticker"] for position in portfolio.get("positions", [])]


def effective_idea(idea: Dict[str, Any], portfolio: Mapping[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """L'idée gardée au changement de profil (US-09), adaptée à ce portefeuille.

    Si le titre qui finance l'idée n'est pas détenu, l'idée est financée au prorata
    et un message l'explique. L'idée saisie, elle, n'est pas modifiée.
    """
    funding = idea.get("funding_ticker")
    if idea.get("funding_source") == "from_ticker" and funding not in held_tickers(portfolio):
        adapted = make_idea(idea["ticker"], idea["target_weight"])
        return adapted, texts.IDEA_FUNDING_RESET.format(ticker=funding)
    return idea, None


def describe_idea(idea: Mapping[str, Any]) -> str:
    funding = texts.IDEA_FUNDING_SHORT[idea["funding_source"]].format(ticker=idea.get("funding_ticker"))
    return texts.IDEA_CURRENT.format(
        weight=format_pct(idea["target_weight"]), ticker=idea["ticker"], funding=funding)


def sync_widgets(idea: Mapping[str, Any]) -> None:
    """Met les sélecteurs sur l'idée donnée. À appeler avant leur affichage (rappel de bouton)."""
    st.session_state[ASSET_KEY] = idea["ticker"]
    st.session_state[WEIGHT_KEY] = int(round(idea["target_weight"] * 100))
    st.session_state[FUNDING_KEY] = idea["funding_source"]
    if idea.get("funding_ticker"):
        st.session_state[FUNDING_TICKER_KEY] = idea["funding_ticker"]


def _init_widgets(idea: Optional[Mapping[str, Any]], tickers: List[str]) -> None:
    default = idea or make_idea("TSLA" if "TSLA" in tickers else tickers[0], 0.25)
    st.session_state.setdefault(ASSET_KEY, default["ticker"])
    st.session_state.setdefault(WEIGHT_KEY, int(round(default["target_weight"] * 100)))
    st.session_state.setdefault(FUNDING_KEY, default["funding_source"])


def _submit_from_widgets(on_submit: Callable[[Dict[str, Any]], None]) -> None:
    """Lit les sélecteurs au moment du clic, pas ceux du rendu précédent."""
    funding = st.session_state[FUNDING_KEY]
    on_submit(make_idea(
        st.session_state[ASSET_KEY], st.session_state[WEIGHT_KEY] / 100, funding,
        st.session_state.get(FUNDING_TICKER_KEY) if funding == "from_ticker" else None))


def render_idea_panel(universe: List[Dict[str, Any]], portfolio: Mapping[str, Any],
                      idea: Optional[Dict[str, Any]], on_submit: Callable[[Dict[str, Any]], None],
                      current_weights: Optional[Mapping[str, str]] = None) -> None:
    """Idées en un clic et sélecteurs. `on_submit(idea)` lance l'analyse.

    `current_weights` : ticker -> poids actuel affiché (display_value du registre).
    """
    tickers = [asset["ticker"] for asset in universe]
    names = {asset["ticker"]: asset["name"] for asset in universe}

    st.caption(texts.IDEA_SUGGESTIONS)
    presets = [preset for preset in texts.IDEA_PRESETS if preset["ticker"] in names]
    with st.container(horizontal=True):
        for preset in presets:
            preset_idea = make_idea(preset["ticker"], preset["target_weight"])
            st.button(preset["label"], key=f"idea_preset_{preset['ticker']}_{round(preset['target_weight'] * 100)}",
                      type="primary" if preset_idea == idea else "secondary",
                      on_click=on_submit, args=(preset_idea,))

    _init_widgets(idea, tickers)
    left, middle, right = st.columns([3, 3, 4])
    with left:
        ticker = st.selectbox(texts.IDEA_ASSET, tickers, key=ASSET_KEY,
                              format_func=lambda t: f"{t}, {names.get(t, '')}")
    with middle:
        st.slider(texts.IDEA_WEIGHT, min_value=1, max_value=100, step=1, key=WEIGHT_KEY)
    with right:
        funding = st.radio(texts.IDEA_FUNDING, list(texts.IDEA_FUNDING_LABELS), key=FUNDING_KEY,
                           format_func=texts.IDEA_FUNDING_LABELS.get, horizontal=True)
        funding_ticker = None
        if funding == "from_ticker":
            candidates = [held for held in held_tickers(portfolio) if held != ticker]
            if candidates:
                if st.session_state.get(FUNDING_TICKER_KEY) not in candidates:
                    st.session_state[FUNDING_TICKER_KEY] = candidates[0]
                funding_ticker = st.selectbox(texts.IDEA_FUNDING_TICKER, candidates, key=FUNDING_TICKER_KEY)
                if current_weights and funding_ticker in current_weights:
                    st.caption(texts.IDEA_FUNDING_WEIGHT.format(
                        ticker=funding_ticker, weight=current_weights[funding_ticker]))
            else:
                st.info(texts.IDEA_NO_FUNDING_CANDIDATE)
    can_submit = funding == "pro_rata" or funding_ticker is not None
    # Un curseur ne lance rien : seule la validation explicite simule (quotas Bedrock partagés).
    st.button(texts.IDEA_SUBMIT, key="idea_submit", type="primary", disabled=not can_submit,
              on_click=_submit_from_widgets, args=(on_submit,))
