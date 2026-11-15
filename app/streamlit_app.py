"""Point d'entrée de l'interface AlphaForge (flux D).

Lancer depuis la racine du projet :
    streamlit run app/streamlit_app.py

Ce fichier pose le cadre commun à toutes les pages : thème, barre latérale
(navigation, mode, profil actif, avertissement), en-tête compact et bandeau de
données d'essai. Chaque page vit dans app/views/ et suit l'ordre de la démo :
accueil, simulation (conversation et réglages manuels), garde-fou, sources. La logique
métier reste dans src/alphaforge/ : l'interface lit les objets du contrat par
app/data_source.py et les affiche (docs/ui_spec.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
for import_path in (APP_DIR, PROJECT_ROOT / "src"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import streamlit as st  # noqa: E402

import data_source  # noqa: E402
import navigation  # noqa: E402
import session  # noqa: E402
import ui_texts as texts  # noqa: E402
from components import banners, style  # noqa: E402
from formatting import format_horizon  # noqa: E402


def render_bedrock_status() -> None:
    status = session.safe_reference(data_source.get_bedrock_status, None)
    if status is None:
        return
    yes_no = {True: texts.YES, False: texts.NO}
    with st.expander(texts.SIDEBAR_BEDROCK):
        st.markdown(
            f"{texts.SIDEBAR_BEDROCK_MODELS} : {yes_no[status['can_call_models']]}  \n"
            f"{texts.SIDEBAR_BEDROCK_GUARDRAIL} : {yes_no[status['has_guardrail']]}  \n"
            f"{texts.SIDEBAR_BEDROCK_TRACES} : {yes_no[status['has_trace_bucket']]}"
        )
    if not status["can_call_models"]:
        st.warning(texts.SIDEBAR_BEDROCK_FALLBACK)


def render_sidebar_mode() -> None:
    """Rendu avant toute donnée : le mode reste modifiable même si tout le reste échoue (US-15)."""
    with st.sidebar:
        st.radio(texts.SIDEBAR_MODE_LABEL, options=data_source.MODES, format_func=texts.MODE_LABELS.get,
                 key="mode", on_change=session.on_mode_change, help=texts.SIDEBAR_MODE_HELP)


LEVEL_WIDGET_KEY = "level_choice"


def render_sidebar_level() -> None:
    """Niveau d'explication, toujours accessible. Changer de niveau ne relance que l'explicateur."""
    with st.sidebar:
        st.session_state[LEVEL_WIDGET_KEY] = st.session_state.level or "novice"
        st.select_slider(texts.EXPLANATION_LEVEL, options=list(texts.LEVEL_LABELS),
                         format_func=texts.LEVEL_LABELS.get, key=LEVEL_WIDGET_KEY,
                         on_change=session.sync_level, args=(LEVEL_WIDGET_KEY,),
                         help=texts.EXPLANATION_LEVEL_HELP)


def render_sidebar_profile() -> None:
    with st.sidebar:
        if st.session_state.mode == "bedrock":
            render_bedrock_status()
        persona = session.active_persona()
        with st.container(border=True):
            st.caption(texts.SIDEBAR_ACTIVE_PROFILE)
            if persona is None or st.session_state.level not in texts.LEVEL_LABELS:
                st.markdown(texts.SIDEBAR_NO_PROFILE)
                return
            profile = persona["profile"]
            st.markdown(
                f"**{session.display_name(profile)}** ({texts.FICTIONAL_BADGE.lower()})  \n"
                f"{texts.PERSONA_RISK} : {texts.RISK_LABELS.get(profile['risk_tolerance'], '')}  \n"
                f"{texts.PERSONA_HORIZON} : "
                f"{format_horizon(profile['horizon_years_min'], profile['horizon_years_max'])}  \n"
                f"{texts.SIDEBAR_LEVEL} : {texts.LEVEL_LABELS[st.session_state.level]}"
            )


def render_header() -> None:
    persona = session.active_persona()
    banners.render_header(
        st.session_state.mode,
        session.display_name(persona["profile"]) if persona else None,
        session.idea_summary(),
    )


def main() -> None:
    st.set_page_config(page_title=texts.PAGE_TITLE, layout="wide")
    session.init_state()
    style.inject()

    page = navigation.build()
    render_sidebar_mode()
    session.load_personas()
    session.guarded(lambda: session.resolve_level(session.available_profiles()))
    session.guarded(render_sidebar_level)
    session.guarded(render_sidebar_profile)

    # Au-dessus de chaque page : avertissement toujours visible (US-12) et mode actif (US-15).
    session.guarded(render_header)
    banners.render_disclaimer()
    # Rempli après la page : un résultat is_fixture peut venir de n'importe quel mode.
    fixture_slot = st.empty()
    session.guarded(page.run)
    if session.fixture_shown():
        with fixture_slot.container():
            banners.render_fixture_banner()


main()
