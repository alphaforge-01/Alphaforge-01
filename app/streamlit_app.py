"""Point d'entrée de l'interface AlphaForge (flux D).

Lancer depuis la racine du projet :
    streamlit run app/streamlit_app.py

La logique métier reste dans src/alphaforge/. L'interface lit les objets du
contrat par app/data_source.py et les affiche (docs/ui_spec.md).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
for import_path in (APP_DIR, PROJECT_ROOT / "src"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import streamlit as st  # noqa: E402

import data_source  # noqa: E402
import ui_texts as texts  # noqa: E402
from components import banners, profile_panel  # noqa: E402
from formatting import format_horizon  # noqa: E402

SESSION_DEFAULTS: Dict[str, Any] = {
    "profile_id": None,
    "level": None,
    "idea": None,
}


def init_state() -> None:
    for key, value in SESSION_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("mode", data_source.resolve_mode(os.environ.get("ALPHAFORGE_MODE")))
    # Résultats déjà obtenus : (mode, profile_id, idée) -> AnalysisResult.
    st.session_state.setdefault("analysis", {})


def select_profile(profile_id: str, personas: Dict[str, Any]) -> None:
    """Rappel du bouton d'une carte : change de profil et préremplit le niveau."""
    st.session_state.profile_id = profile_id
    st.session_state.level = personas[profile_id]["profile"]["default_level"]


def render_sidebar(personas: Optional[Dict[str, Any]]) -> None:
    with st.sidebar:
        st.header(texts.SIDEBAR_TITLE)
        st.radio(
            texts.SIDEBAR_MODE_LABEL,
            options=data_source.MODES,
            format_func=texts.MODE_LABELS.get,
            key="mode",
        )
        st.subheader(texts.SIDEBAR_ACTIVE_PROFILE)
        profile_id = st.session_state.profile_id
        if personas and profile_id in personas:
            profile = personas[profile_id]["profile"]
            st.markdown(
                f"**{profile['display_name']}** ({texts.FICTIONAL_BADGE.lower()})  \n"
                f"{texts.PERSONA_RISK} : {texts.RISK_LABELS[profile['risk_tolerance']]}  \n"
                f"{texts.PERSONA_HORIZON} : "
                f"{format_horizon(profile['horizon_years_min'], profile['horizon_years_max'])}  \n"
                f"{texts.SIDEBAR_LEVEL} : {texts.LEVEL_LABELS[st.session_state.level]}"
            )
        else:
            st.caption(texts.SIDEBAR_NO_PROFILE)
        st.divider()
        st.caption(texts.DISCLAIMER)


def idea_key(idea: Dict[str, Any]) -> tuple:
    return (idea["ticker"], idea["target_weight"], idea["funding_source"], idea.get("funding_ticker"))


def load_analysis(mode: str, persona: Dict[str, Any], idea: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Lit le résultat en cache de session, sinon le demande à data_source.

    Une donnée absente affiche un message d'information, une autre erreur un
    message d'erreur : la page ne plante jamais (US-15).
    """
    cache_key = (mode, persona["profile"]["profile_id"], idea_key(idea))
    cache = st.session_state.analysis
    if cache_key in cache:
        return cache[cache_key]
    try:
        result = data_source.get_analysis(mode, persona["profile"], persona["portfolio"], idea)
    except data_source.DataUnavailable as exc:
        st.info(str(exc))
        return None
    except Exception as exc:  # la démo ne doit jamais afficher une trace Python
        st.error(texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
        return None
    cache[cache_key] = result
    return result


def render_analysis_tab(mode: str, personas: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Onglet principal, dans l'ordre de la démo. Retourne l'analyse affichée, s'il y en a une."""
    st.header(texts.SECTION_PROFILE)
    if not personas:
        return None
    profile_panel.render_persona_cards(
        personas,
        st.session_state.profile_id,
        on_select=lambda profile_id: select_profile(profile_id, personas),
    )
    profile_id = st.session_state.profile_id
    if profile_id not in personas:
        st.info(texts.NO_PROFILE_SELECTED)
        return None

    # Sprint 1 : l'idée de démonstration sert à lire la fixture. Sélecteurs en D4.
    if st.session_state.idea is None:
        st.session_state.idea = data_source.get_fixture_idea()
    result = load_analysis(mode, personas[profile_id], st.session_state.idea)

    st.header(texts.SECTION_XRAY)
    if result is not None:
        st.caption(texts.ANALYSIS_LOADED.format(run_id=result["run_id"], as_of=result["as_of"]))
    st.caption(texts.COMING_SOON.format(task="D3"))
    st.header(texts.SECTION_IDEA)
    st.caption(texts.COMING_SOON.format(task="D4"))
    st.header(texts.SECTION_RESULT)
    st.caption(texts.COMING_SOON.format(task="D4"))
    st.header(texts.SECTION_EXPLANATION)
    st.caption(texts.COMING_SOON.format(task="D5"))
    with st.expander(texts.SECTION_TRACE):
        st.caption(texts.COMING_SOON.format(task="D6"))
    return result


def load_personas_safely(mode: str) -> Optional[Dict[str, Any]]:
    try:
        return data_source.get_personas(mode)
    except data_source.DataUnavailable as exc:
        st.info(str(exc))
    except Exception as exc:  # la démo ne doit jamais afficher une trace Python
        st.error(texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
    return None


def main() -> None:
    st.set_page_config(page_title=texts.PAGE_TITLE, layout="wide")
    init_state()
    mode = st.session_state.mode

    st.title(texts.APP_TITLE)
    st.caption(texts.APP_SUBTITLE)
    # Au-dessus des onglets : visibles sur chaque écran (US-12).
    banners.render_disclaimer()
    # Rempli plus bas, une fois l'analyse connue : un résultat is_fixture peut
    # aussi venir du mode hors ligne (outils bouchons du flux C).
    fixture_banner_slot = st.empty()

    tab_analysis, tab_guardrail, tab_sources = st.tabs(
        [texts.TAB_ANALYSIS, texts.TAB_GUARDRAIL, texts.TAB_SOURCES]
    )
    with tab_analysis:
        personas = load_personas_safely(mode)
        result = render_analysis_tab(mode, personas)
    with tab_guardrail:
        st.caption(texts.COMING_SOON.format(task="D7"))
    with tab_sources:
        st.caption(texts.COMING_SOON.format(task="D8"))
    render_sidebar(personas)

    if mode == "fixture" or (result is not None and result.get("is_fixture")):
        with fixture_banner_slot.container():
            banners.render_fixture_banner()


main()
