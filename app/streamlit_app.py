"""Point d'entrée de l'interface AlphaForge (flux D).

Lancer depuis la racine du projet :
    streamlit run app/streamlit_app.py

Ce fichier pose le cadre commun à toutes les pages : thème, barre de navigation du haut
et menu de paramètres (style d'explication, mode, trace de démo),
en-tête compact et bandeau de données d'essai. Chaque page vit dans app/views/ et suit l'ordre de la démo :
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
from components import banners, conversation, style  # noqa: E402


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


def render_settings(menu) -> None:
    """Rendu avant toute donnée : le mode reste modifiable même si tout le reste échoue (US-15).

    Vit dans le menu de l'icône de paramètres (barre du haut) ; le mode actif reste visible
    dans l'en-tête.
    """
    with menu:
        st.radio(texts.SIDEBAR_MODE_LABEL, options=data_source.MODES, format_func=texts.MODE_LABELS.get,
                 key="mode", on_change=session.on_mode_change, help=texts.SIDEBAR_MODE_HELP)
        if st.session_state.mode == "bedrock":
            session.guarded(render_bedrock_status)
        st.toggle(texts.SHOW_TRACE_LABEL, key=conversation.SHOW_TRACE_KEY, help=texts.SHOW_TRACE_HELP)
        navigation.render_check_links()


LEVEL_WIDGET_KEY = "level_choice"


def render_sidebar_level() -> None:
    """Style d'explication, accessible sur chaque page depuis le menu des paramètres avancés.

    Changer de style ne relance que l'explicateur.
    """
    st.session_state[LEVEL_WIDGET_KEY] = st.session_state.level or "novice"
    st.select_slider(texts.EXPLANATION_LEVEL, options=list(texts.EXPLANATION_STYLE_LABELS),
                     format_func=texts.EXPLANATION_STYLE_LABELS.get, key=LEVEL_WIDGET_KEY,
                     on_change=session.sync_level, args=(LEVEL_WIDGET_KEY,),
                     help=texts.EXPLANATION_LEVEL_HELP)


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
    settings_menu, context_slot = navigation.render_top_nav(navigation.current_key(page),
                                              has_profile=bool(st.session_state.get("profile_id")))
    # Place du style d'explication réservée en tête du menu de paramètres, rendu avant toute donnée.
    level_slot = settings_menu.container()
    render_settings(settings_menu)
    session.load_personas()
    session.guarded(lambda: session.resolve_level(session.available_profiles()))
    # Le style d'explication reste réglable dans le menu sur toutes les pages, accueil compris :
    # les deux contrôles de l'accueil lisent et écrivent le même st.session_state.level.
    with level_slot:
        session.guarded(render_sidebar_level)

    # Au-dessus de chaque page : avertissement toujours visible (US-12) et mode actif (US-15).
    with context_slot:
        session.guarded(render_header)
    banners.render_disclaimer()
    # Rempli après la page : un résultat is_fixture peut venir de n'importe quel mode.
    fixture_slot = st.empty()
    session.guarded(page.run)
    if session.fixture_shown():
        with fixture_slot.container():
            banners.render_fixture_banner()


main()
