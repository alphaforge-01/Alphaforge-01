"""Point d'entrée de l'interface AlphaForge (flux D).

Lancer depuis la racine du projet :
    streamlit run app/streamlit_app.py

Parcours de l'onglet Analyse, dans l'ordre de la démo : profil, radiographie,
idée, résultat, explication, trace. La logique métier reste dans src/alphaforge/ :
l'interface lit les objets du contrat par app/data_source.py et les affiche
(docs/ui_spec.md).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
for import_path in (APP_DIR, PROJECT_ROOT / "src"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import streamlit as st  # noqa: E402

import data_source  # noqa: E402
import ui_texts as texts  # noqa: E402
from components import (  # noqa: E402
    banners, explanation_panel, guardrail_panel, idea_panel, profile_panel, result_panel,
    sources_panel, trace_panel, xray,
)
from components.evidence import ProofContext  # noqa: E402
from formatting import format_horizon  # noqa: E402

LOGGER = logging.getLogger("alphaforge.ui")
CUSTOM_ID = "custom"

SESSION_DEFAULTS: Dict[str, Any] = {
    "profile_id": None,
    "level": None,
    # Dernière idée soumise, gardée au changement de profil (US-09).
    "idea": None,
    # Persona "custom" construit par le formulaire, ou None.
    "custom_persona": None,
    # Au changement de mode, le niveau est repris du persona du nouveau mode.
    "level_reset": False,
    # Vrai après un clic sur une idée : en mode bedrock, seule une demande explicite
    # lance les agents (quotas partagés).
    "analysis_request": False,
}
# Résultats et échecs mémorisés par session : (type) -> {clé -> valeur}.
CACHE_KINDS = ("xray", "analysis", "explanation", "asset")


def init_state() -> None:
    for key, value in SESSION_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("mode", data_source.resolve_mode(os.environ.get("ALPHAFORGE_MODE")))
    for kind in CACHE_KINDS:
        st.session_state.setdefault(f"{kind}_cache", {})
        st.session_state.setdefault(f"{kind}_failures", {})


# --- Rappels des widgets ------------------------------------------------------

def _sync_idea_widgets(portfolio: Dict[str, Any]) -> None:
    """Les sélecteurs montrent l'idée telle qu'elle sera analysée pour ce portefeuille (US-09)."""
    if st.session_state.idea is not None:
        idea_panel.sync_widgets(idea_panel.effective_idea(st.session_state.idea, portfolio)[0])


def select_profile(profile_id: str, personas: Dict[str, Any]) -> None:
    """Rappel du bouton d'une carte : change de profil et préremplit le niveau."""
    st.session_state.profile_id = profile_id
    st.session_state.level = personas[profile_id]["profile"]["default_level"]
    _sync_idea_widgets(personas[profile_id]["portfolio"])


def use_custom_profile(persona: Dict[str, Any]) -> None:
    """Rappel du bouton du formulaire : active le profil construit."""
    st.session_state.custom_persona = persona
    st.session_state.profile_id = CUSTOM_ID
    st.session_state.level = persona["profile"]["default_level"]
    _sync_idea_widgets(persona["portfolio"])


def submit_idea(idea: Dict[str, Any]) -> None:
    """Rappel des boutons d'idée : l'idée devient celle analysée, les sélecteurs la reflètent."""
    st.session_state.idea = idea
    st.session_state.analysis_request = True
    idea_panel.sync_widgets(idea)


def request_analysis() -> None:
    """Rappel du bouton "Analyser cette idée pour ce profil" (mode bedrock)."""
    st.session_state.analysis_request = True


def on_mode_change() -> None:
    """Un profil construit garde le portefeuille de son mode : on le retire au changement."""
    st.session_state.custom_persona = None
    if st.session_state.profile_id == CUSTOM_ID:
        st.session_state.profile_id = None
        st.session_state.level = None
    st.session_state.level_reset = True


def resolve_level(profiles: Dict[str, Any]) -> None:
    """Niveau prérempli par le profil actif, et repris de lui après un changement de mode."""
    profile_id = st.session_state.profile_id
    if profile_id not in profiles:
        return
    if st.session_state.level_reset or st.session_state.level not in texts.LEVEL_LABELS:
        st.session_state.level = profiles[profile_id]["profile"]["default_level"]
        st.session_state.level_reset = False


def forget_failure(kind: str, cache_key: Tuple) -> None:
    st.session_state[f"{kind}_failures"].pop(cache_key, None)
    if kind == "analysis":  # en mode bedrock, "Réessayer" relance sans second clic
        st.session_state.analysis_request = True


# --- Chargement avec mémoire des échecs ------------------------------------------

def fingerprint(obj: Any) -> str:
    """Clé stable d'un objet JSON : un profil reconstruit avec d'autres règles change de clé."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def cached_load(kind: str, cache_key: Tuple, loader: Callable[[], Any], spinner: str) -> Optional[Any]:
    """Valeur en cache de session, sinon `loader()`. La page ne plante jamais (US-15).

    Un échec est mémorisé aussi : sans cela, chaque interaction relancerait l'appel
    (quotas Bedrock partagés). Le bouton "Réessayer" l'efface.
    """
    cache = st.session_state[f"{kind}_cache"]
    failures = st.session_state[f"{kind}_failures"]
    if cache_key in cache:
        return cache[cache_key]
    if cache_key not in failures:
        try:
            with st.spinner(spinner):
                cache[cache_key] = loader()
            return cache[cache_key]
        except data_source.DataUnavailable as exc:
            LOGGER.info("Donnée non disponible (%s) : %s", kind, exc)
            failures[cache_key] = ("info", str(exc))
        except Exception as exc:  # la démo ne doit jamais afficher une trace Python
            LOGGER.exception("Échec du chargement (%s)", kind)
            failures[cache_key] = ("error", texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
    severity, message = failures[cache_key]
    getattr(st, severity)(message)
    if severity == "error":  # une donnée absente ne change pas en réessayant
        st.button(texts.RETRY, key=f"retry_{kind}", on_click=forget_failure, args=(kind, cache_key))
    return None


def guarded(render: Callable[[], Any]) -> Any:
    """Affiche une erreur à la place d'une section qui échoue, sans casser le reste de la page."""
    try:
        return render()
    except Exception as exc:  # la démo ne doit jamais afficher une trace Python
        LOGGER.exception("Erreur dans une section de l'interface")
        st.error(texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
        return None


def safe_reference(loader: Callable[[], Any], default: Any) -> Any:
    """Données de référence facultatives (sources, limites) : absentes, la page continue."""
    try:
        return loader()
    except data_source.DataUnavailable as exc:
        st.info(str(exc))
    except Exception:  # la démo ne doit jamais afficher une trace Python
        LOGGER.exception("Données de référence indisponibles")
    return default


# --- Barre latérale ---------------------------------------------------------------

def available_profiles(personas: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Personas du mode courant, plus le profil construit s'il existe."""
    available = dict(personas or {})
    if st.session_state.custom_persona is not None:
        available[CUSTOM_ID] = st.session_state.custom_persona
    return available


def display_name(profile: Dict[str, Any]) -> str:
    if profile["profile_id"] == CUSTOM_ID:
        return texts.CUSTOM_DISPLAY_NAME
    return profile["display_name"]


def render_bedrock_status() -> None:
    status = safe_reference(data_source.get_bedrock_status, None)
    if status is None:
        return
    st.subheader(texts.SIDEBAR_BEDROCK)
    yes_no = {True: texts.YES, False: texts.NO}
    st.markdown(
        f"{texts.SIDEBAR_BEDROCK_MODELS} : {yes_no[status['can_call_models']]}  \n"
        f"{texts.SIDEBAR_BEDROCK_GUARDRAIL} : {yes_no[status['has_guardrail']]}  \n"
        f"{texts.SIDEBAR_BEDROCK_TRACES} : {yes_no[status['has_trace_bucket']]}"
    )
    if not status["can_call_models"]:
        st.warning(texts.SIDEBAR_BEDROCK_FALLBACK)


def render_sidebar_mode() -> None:
    """Rendu en premier, sans aucune donnée : le mode reste modifiable même si tout le reste échoue."""
    with st.sidebar:
        st.header(texts.SIDEBAR_TITLE)
        st.radio(texts.SIDEBAR_MODE_LABEL, options=data_source.MODES, format_func=texts.MODE_LABELS.get,
                 key="mode", on_change=on_mode_change)


def render_sidebar_details(profiles: Dict[str, Any]) -> None:
    with st.sidebar:
        if st.session_state.mode == "bedrock":
            render_bedrock_status()
        st.subheader(texts.SIDEBAR_ACTIVE_PROFILE)
        profile_id = st.session_state.profile_id
        if profile_id in profiles and st.session_state.level in texts.LEVEL_LABELS:
            profile = profiles[profile_id]["profile"]
            st.markdown(
                f"**{display_name(profile)}** ({texts.FICTIONAL_BADGE.lower()})  \n"
                f"{texts.PERSONA_RISK} : {texts.RISK_LABELS.get(profile['risk_tolerance'], '')}  \n"
                f"{texts.PERSONA_HORIZON} : "
                f"{format_horizon(profile['horizon_years_min'], profile['horizon_years_max'])}  \n"
                f"{texts.SIDEBAR_LEVEL} : {texts.LEVEL_LABELS[st.session_state.level]}"
            )
        else:
            st.caption(texts.SIDEBAR_NO_PROFILE)


def render_sidebar_disclaimer() -> None:
    with st.sidebar:
        st.divider()
        st.caption(texts.DISCLAIMER)


# --- Onglet Analyse ------------------------------------------------------------------

def proof_context(evidence_limits: Optional[list]) -> ProofContext:
    """Sources et limites utiles pour vérifier un chiffre (catalogue du flux B et limites du résultat)."""
    sources = safe_reference(data_source.get_sources, [])
    limits = {limit["limit_id"]: limit for limit in safe_reference(data_source.get_reference_limits, [])}
    limits.update({limit["limit_id"]: limit for limit in evidence_limits or []})
    return ProofContext(
        level=st.session_state.level or "novice",
        sources={row.get("file"): row for row in sources},
        limits=limits,
    )


def current_weight_displays(xray_data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """ticker -> poids actuel tel qu'affiché par le registre (clés "weights.<ticker>:portfolio_before")."""
    if xray_data is None:
        return {}
    displays: Dict[str, str] = {}
    for entry in xray_data["evidence"].values():
        metric, _, subject = entry["evidence_key"].partition(":")
        if metric.startswith("weights.") and subject == "portfolio_before" and entry.get("display_value"):
            displays[metric[len("weights."):]] = entry["display_value"]
    return displays


def render_profile_section(personas: Dict[str, Any]) -> None:
    st.header(texts.SECTION_PROFILE)
    profile_panel.render_persona_cards(
        personas, st.session_state.profile_id,
        on_select=lambda profile_id: select_profile(profile_id, personas))
    is_custom = st.session_state.profile_id == CUSTOM_ID
    with st.expander(texts.CUSTOM_EXPANDER, expanded=is_custom):
        guarded(lambda: profile_panel.render_custom_profile_form(
            personas, st.session_state.custom_persona if is_custom else None, on_use=use_custom_profile))
    if is_custom:
        st.success(texts.CUSTOM_ACTIVE)


def render_analysis_tab(mode: str, personas: Optional[Dict[str, Any]], shown: Dict[str, Any]) -> None:
    """Onglet principal. `shown` reçoit ce qui est affiché, pour le bandeau de données d'essai."""
    if not personas:
        st.header(texts.SECTION_PROFILE)
        return
    render_profile_section(personas)

    profiles = available_profiles(personas)
    profile_id = st.session_state.profile_id
    if profile_id is None:
        st.info(texts.NO_PROFILE_SELECTED)
        return
    if profile_id not in profiles:
        st.info(texts.PROFILE_NOT_IN_MODE)
        return
    persona = profiles[profile_id]
    profile, portfolio = persona["profile"], persona["portfolio"]
    rules_by_id = {rule["rule_id"]: rule for rule in profile.get("rules", [])}
    universe = safe_reference(data_source.get_universe, [])
    names = {asset["ticker"]: asset["name"] for asset in universe}

    st.header(texts.SECTION_XRAY)
    xray_data = cached_load(
        "xray", (mode, fingerprint(profile), fingerprint(portfolio)),
        lambda: data_source.get_xray(mode, profile, portfolio), texts.XRAY_SPINNER)
    if xray_data is not None:
        shown["xray"] = xray_data
        xray_ctx = proof_context(xray_data["limits"])
        xray_ctx.show_id = False  # registre propre à la radiographie
        guarded(lambda: xray.render_xray(xray_data, rules_by_id, xray_ctx, names))

    st.header(texts.SECTION_IDEA)
    if universe:
        current_weights = current_weight_displays(xray_data)
        guarded(lambda: idea_panel.render_idea_panel(
            universe, portfolio, st.session_state.idea, submit_idea, current_weights))
    if st.session_state.idea is None:
        st.caption(texts.IDEA_NONE_YET)
        return
    idea, adapted_message = idea_panel.effective_idea(st.session_state.idea, portfolio)
    if adapted_message:
        st.info(adapted_message)

    st.header(texts.SECTION_RESULT)
    analysis_key = (mode, fingerprint(profile), fingerprint(portfolio), fingerprint(idea))
    known = (analysis_key in st.session_state.analysis_cache
             or analysis_key in st.session_state.analysis_failures)
    if mode == "bedrock" and not known and not st.session_state.analysis_request:
        # Changement de profil ou de mode : aucun agent n'est lancé sans clic (quotas partagés).
        st.caption(idea_panel.describe_idea(idea))
        st.info(texts.RESULT_BEDROCK_PENDING)
        st.button(texts.RESULT_BEDROCK_RUN, key="run_bedrock_analysis", type="primary",
                  on_click=request_analysis)
        return
    result = cached_load(
        "analysis", analysis_key,
        lambda: data_source.get_analysis(mode, profile, portfolio, idea), texts.RESULT_SPINNER)
    st.session_state.analysis_request = False
    if result is None:
        return
    shown["result"] = result
    ctx = proof_context(result.get("limits"))
    asset_facts = cached_load(
        "asset", (mode, idea["ticker"]),
        lambda: data_source.get_asset_facts(mode, idea["ticker"], portfolio), texts.ASSET_FACTS_SPINNER)
    notice = safe_reference(lambda: data_source.get_threshold_notice(st.session_state.level or "novice"), "")
    guarded(lambda: result_panel.render_result(result, rules_by_id, ctx, names, asset_facts, notice))

    st.header(texts.SECTION_EXPLANATION)
    level = explanation_panel.render_level_choice()
    ctx.level = level
    explanation = cached_load(
        "explanation", (mode, result["run_id"], level),
        lambda: data_source.get_explanation(mode, result, level), texts.EXPLANATION_SPINNER)
    if explanation is not None:
        guarded(lambda: explanation_panel.render_explanation(explanation, result, ctx))

    st.header(texts.SECTION_TRACE)
    guarded(lambda: trace_panel.render_trace(result, explanation))


def render_guardrail_tab(mode: str) -> None:
    prompts = safe_reference(data_source.get_guardrail_prompts, [])
    guardrail_panel.render_guardrail_panel(mode, prompts, lambda text: data_source.check_request(mode, text))


def render_sources_tab() -> None:
    level = st.session_state.level or "novice"
    sources_panel.render_sources_panel(
        safe_reference(data_source.get_sources, []),
        safe_reference(data_source.get_reference_limits, []),
        safe_reference(lambda: data_source.get_threshold_notice(level), ""),
        safe_reference(data_source.get_universe, []),
        level,
    )


def load_personas_safely(mode: str) -> Optional[Dict[str, Any]]:
    try:
        return data_source.get_personas(mode)
    except data_source.DataUnavailable as exc:
        st.info(str(exc))
    except Exception as exc:  # la démo ne doit jamais afficher une trace Python
        LOGGER.exception("Chargement des personas impossible")
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
    # Rempli plus bas, une fois les données connues : un résultat is_fixture peut
    # aussi venir des modes offline et bedrock (bouchons du flux C).
    fixture_banner_slot = st.empty()

    render_sidebar_mode()
    personas = load_personas_safely(mode)
    guarded(lambda: resolve_level(available_profiles(personas)))
    guarded(lambda: render_sidebar_details(available_profiles(personas)))
    render_sidebar_disclaimer()

    tab_analysis, tab_guardrail, tab_sources = st.tabs(
        [texts.TAB_ANALYSIS, texts.TAB_GUARDRAIL, texts.TAB_SOURCES])
    # Rempli au fil de l'affichage : le bandeau reste juste même si une section échoue ensuite.
    shown: Dict[str, Any] = {}
    with tab_analysis:
        guarded(lambda: render_analysis_tab(mode, personas, shown))
    with tab_guardrail:
        guarded(lambda: render_guardrail_tab(mode))
    with tab_sources:
        guarded(render_sources_tab)

    if mode == "fixture" or any(item.get("is_fixture") for item in shown.values()):
        with fixture_banner_slot.container():
            banners.render_fixture_banner()


main()
