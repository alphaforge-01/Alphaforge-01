"""État de session et chargements protégés, partagés par toutes les pages.

L'état (profil, idée, niveau, caches) vit dans `st.session_state` et survit
donc à la navigation entre pages. Toute donnée calculée passe par
`cached_load` : la page ne plante jamais, un échec est mémorisé (quotas
Bedrock partagés) et un bouton "Réessayer" l'efface. Aucun calcul financier
ici : on compose les appels à `data_source`.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import streamlit as st

import data_source
import navigation
import ui_texts as texts
from components import idea_panel, persistence
from components.evidence import ProofContext

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
    # Fil de la conversation : demandes, réglages manuels et réponses (voir components/conversation.py).
    "chat_history": [],
    # Demande explicite d'explication (message, "Simuler", bouton "Rédiger") : en mode bedrock,
    # l'explicateur n'est appelé que dans l'exécution qui suit un clic (quotas partagés).
    "explanation_request": False,
    # Vrai dès qu'un curseur de niveau a été touché : le choix d'un profil ne l'écrase plus.
    "level_chosen": False,
}
# Résultats et échecs mémorisés par session : (type) -> {clé -> valeur}.
CACHE_KINDS = ("xray", "analysis", "explanation", "asset")
# Clés propres à une exécution, remises à zéro à chaque passage du point d'entrée.
PERSONAS_KEY = "_run_personas"
PERSONAS_ERROR_KEY = "_run_personas_error"
FIXTURE_SHOWN_KEY = "_run_fixture_shown"
GO_SIMULATION_KEY = "_go_simulation"
CHAT_INPUT_KEY = "chat_text"


def init_state() -> None:
    for key, value in SESSION_DEFAULTS.items():
        # Copie : une liste par défaut partagée mêlerait les fils de deux sessions.
        st.session_state.setdefault(key, copy.deepcopy(value))
    st.session_state.setdefault("mode", data_source.resolve_mode(os.environ.get("ALPHAFORGE_MODE")))
    for kind in CACHE_KINDS:
        st.session_state.setdefault(f"{kind}_cache", {})
        st.session_state.setdefault(f"{kind}_failures", {})
    st.session_state[FIXTURE_SHOWN_KEY] = False


# --- Rappels des widgets ------------------------------------------------------

def _append(entry: Dict[str, Any]) -> None:
    st.session_state.chat_history.append(entry)


def _analysis_entry_key(persona: Dict[str, Any], idea: Dict[str, Any]) -> Tuple:
    """Clé d'analyse complète d'une réponse : mode, profil, portefeuille et idée adaptée."""
    effective = idea_panel.effective_idea(idea, persona["portfolio"])[0]
    return (st.session_state.mode, fingerprint(persona["profile"]), fingerprint(persona["portfolio"]),
            fingerprint(effective))


def _append_analysis(guard_action: Optional[str] = None, persona: Optional[Dict[str, Any]] = None) -> None:
    """Réponse à venir pour l'idée courante et le profil actif (analysée à l'affichage).

    L'entrée garde sa propre clé d'analyse et le nom du profil : une réponse ancienne
    montre toujours le verdict de son profil, jamais celui du profil actif.
    """
    if st.session_state.idea is None:
        return
    persona = persona or active_persona()
    entry: Dict[str, Any] = {"role": "assistant", "type": "analysis", "idea": dict(st.session_state.idea),
                             "guard_action": guard_action}
    if persona is not None:
        entry["key"] = _analysis_entry_key(persona, st.session_state.idea)
        entry["profile_name"] = display_name(persona["profile"])
    _append(entry)


def _reset_simulation() -> None:
    """Nouveau profil, nouvelle simulation : fil vidé, idée oubliée, sélecteurs remis par défaut.

    Choix de l'équipe (remplace la reprise de l'idée de US-09) : rien d'un profil précédent
    ne reste affiché. Les caches restent : revenir à un profil et refaire une idée déjà vue
    est instantané, sans nouvel appel aux agents.
    """
    st.session_state.chat_history = []
    st.session_state.idea = None
    for key in (idea_panel.ASSET_KEY, idea_panel.WEIGHT_KEY, idea_panel.FUNDING_KEY,
                idea_panel.FUNDING_TICKER_KEY):
        st.session_state.pop(key, None)
    for key in [k for k in st.session_state
                if str(k).startswith(("details_", persistence.KEEP_PREFIX + "details_"))]:
        del st.session_state[key]


def _clear_requests() -> None:
    """Un changement de profil ou de mode n'est pas une demande d'analyse (quotas partagés)."""
    st.session_state.analysis_request = False
    st.session_state.explanation_request = False


def select_profile(profile_id: str, personas: Dict[str, Any]) -> None:
    """Rappel du bouton d'une carte : change de profil et préremplit le niveau."""
    changed = st.session_state.profile_id != profile_id
    st.session_state.profile_id = profile_id
    _clear_requests()
    if not st.session_state.level_chosen:
        st.session_state.level = personas[profile_id]["profile"]["default_level"]
    if changed:
        _reset_simulation()


def select_profile_and_go(profile_id: str, personas: Dict[str, Any]) -> None:
    """Carte de l'accueil : choisit le profil puis ouvre la page de simulation."""
    select_profile(profile_id, personas)
    st.session_state[GO_SIMULATION_KEY] = True


def use_custom_profile(persona: Dict[str, Any]) -> None:
    """Rappel du bouton du formulaire : active le profil construit."""
    st.session_state.custom_persona = persona
    st.session_state.profile_id = CUSTOM_ID
    _clear_requests()
    if not st.session_state.level_chosen:
        st.session_state.level = persona["profile"]["default_level"]
    _reset_simulation()


def _set_idea(idea: Dict[str, Any]) -> None:
    st.session_state.idea = idea
    # Un clic ou un message : demande explicite, pour l'analyse et pour l'explication.
    st.session_state.analysis_request = True
    st.session_state.explanation_request = True
    idea_panel.sync_widgets(idea)


def submit_idea(idea: Dict[str, Any], label: Optional[str] = None) -> None:
    """Réglage manuel, idée en un clic ou choix proposé par l'agent : s'inscrit dans le fil."""
    _append({"role": "user", "origin": "manual",
             "text": label or texts.CHAT_MANUAL_CHANGE.format(idea=idea_panel.describe_idea(idea))})
    _set_idea(idea)
    _append_analysis()


def ask(text: Optional[str] = None) -> None:
    """Demande en langage naturel (champ de saisie ou exemple cliqué).

    Ordre fixe : garde-fou Bedrock (check_request), contrôle local des sujets interdits,
    puis traduction déterministe en idée. Rien n'est deviné : une demande ambiguë
    reçoit une question.
    """
    text = (text if text is not None else st.session_state.get(CHAT_INPUT_KEY) or "").strip()
    if not text:
        return
    _append({"role": "user", "origin": "chat", "text": text})
    persona = active_persona()
    if persona is None:
        _append({"role": "assistant", "type": "note", "text": texts.NEED_PROFILE})
        return
    mode = st.session_state.mode
    try:
        guard = data_source.check_request(mode, text)
    except Exception:  # le contrôle reste affiché comme non exécuté, la demande continue
        LOGGER.exception("Contrôle du garde-fou impossible")
        guard = {"action": "not_run", "denied_topics": []}
    if guard.get("action") == "intervened":
        _append({"role": "assistant", "type": "refused", "by": "guardrail",
                 "topics": list(guard.get("denied_topics") or [])})
        return
    try:
        universe = data_source.get_universe()
        held = idea_panel.held_tickers(persona["portfolio"])
        parsed = data_source.parse_request(text, universe, held)
    except data_source.DataUnavailable as exc:
        _append({"role": "assistant", "type": "info", "text": str(exc)})
        return
    except Exception as exc:  # la page ne plante jamais
        LOGGER.exception("Analyse de la demande impossible")
        _append({"role": "assistant", "type": "note",
                 "text": texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__)})
        return
    if parsed["status"] == "refused":
        _append({"role": "assistant", "type": "refused", "by": "local", "topics": [parsed["reason"]],
                 "guard_action": guard.get("action")})
    elif parsed["status"] == "clarify":
        _append({"role": "assistant", "type": "clarify", "parsed": parsed})
    else:
        _set_idea(parsed["idea"])
        _append_analysis(guard.get("action"), persona)


def request_analysis() -> None:
    """Rappel du bouton "Analyser cette idée pour ce profil" (mode bedrock)."""
    st.session_state.analysis_request = True
    st.session_state.explanation_request = True


def request_explanation() -> None:
    """Rappel du bouton "Rédiger l'explication" (mode bedrock, après un changement de niveau)."""
    st.session_state.explanation_request = True


def on_mode_change() -> None:
    """Un profil construit garde le portefeuille de son mode : on le retire au changement."""
    st.session_state.custom_persona = None
    if st.session_state.profile_id == CUSTOM_ID:
        st.session_state.profile_id = None
        st.session_state.level = None
    st.session_state.level_reset = True
    _clear_requests()
    _append({"role": "assistant", "type": "note",
             "text": texts.CHAT_MODE_CHANGED.format(mode=texts.MODE_LABELS.get(st.session_state.mode))})
    # Les personas de l'exécution précédente sont ceux de l'ancien mode : la clé de la
    # réponse est posée à son premier affichage (simulation_page).
    if st.session_state.profile_id is not None and st.session_state.idea is not None:
        _append({"role": "assistant", "type": "analysis", "idea": dict(st.session_state.idea),
                 "guard_action": None})


def sync_level(widget_key: str) -> None:
    """Rappel des curseurs Novice / Pro : le niveau vit dans st.session_state.level."""
    st.session_state.level = st.session_state[widget_key]
    st.session_state.level_chosen = True


def resolve_level(profiles: Dict[str, Any]) -> None:
    """Niveau prérempli par le profil actif, et repris de lui après un changement de mode."""
    profile_id = st.session_state.profile_id
    if profile_id not in profiles:
        return
    level_valid = st.session_state.level in texts.LEVEL_LABELS
    if level_valid and st.session_state.level_chosen:
        st.session_state.level_reset = False
        return
    if st.session_state.level_reset or not level_valid:
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


def safe_reference(loader: Callable[[], Any], default: Any, quiet: bool = False) -> Any:
    """Données de référence facultatives (sources, limites) : absentes, la page continue."""
    try:
        return loader()
    except data_source.DataUnavailable as exc:
        if not quiet:
            st.info(str(exc))
    except Exception:  # la démo ne doit jamais afficher une trace Python
        LOGGER.exception("Données de référence indisponibles")
    return default


def mark_shown(item: Optional[Dict[str, Any]]) -> None:
    """Retient qu'un objet affiché vient des fixtures : le bandeau de données d'essai suivra."""
    if item and item.get("is_fixture"):
        st.session_state[FIXTURE_SHOWN_KEY] = True


def fixture_shown() -> bool:
    return st.session_state.mode == "fixture" or bool(st.session_state.get(FIXTURE_SHOWN_KEY))


# --- Profils ----------------------------------------------------------------------

def load_personas() -> None:
    """Lus une fois par exécution par le point d'entrée ; l'erreur est montrée par les pages."""
    st.session_state[PERSONAS_KEY] = None
    st.session_state[PERSONAS_ERROR_KEY] = None
    try:
        st.session_state[PERSONAS_KEY] = data_source.get_personas(st.session_state.mode)
    except data_source.DataUnavailable as exc:
        st.session_state[PERSONAS_ERROR_KEY] = ("info", str(exc))
    except Exception as exc:  # la démo ne doit jamais afficher une trace Python
        LOGGER.exception("Chargement des personas impossible")
        st.session_state[PERSONAS_ERROR_KEY] = (
            "error", texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))


def personas() -> Optional[Dict[str, Any]]:
    return st.session_state.get(PERSONAS_KEY)


def show_personas_error() -> None:
    error = st.session_state.get(PERSONAS_ERROR_KEY)
    if error:
        getattr(st, error[0])(error[1])


def available_profiles() -> Dict[str, Any]:
    """Personas du mode courant, plus le profil construit s'il existe."""
    available = dict(personas() or {})
    if st.session_state.custom_persona is not None:
        available[CUSTOM_ID] = st.session_state.custom_persona
    return available


def display_name(profile: Dict[str, Any]) -> str:
    if profile["profile_id"] == CUSTOM_ID:
        return texts.CUSTOM_DISPLAY_NAME
    return profile["display_name"]


def active_persona() -> Optional[Dict[str, Any]]:
    return available_profiles().get(st.session_state.profile_id)


@dataclass
class Active:
    """Ce dont une page a besoin pour le profil actif."""
    mode: str
    profile: Dict[str, Any]
    portfolio: Dict[str, Any]
    rules_by_id: Dict[str, Dict[str, Any]]
    universe: List[Dict[str, Any]]

    @property
    def names(self) -> Dict[str, str]:
        return {asset["ticker"]: asset["name"] for asset in self.universe}


def require_profile() -> Optional[Active]:
    """Profil actif, ou un message court avec le lien vers la page Profil."""
    if not personas():
        show_personas_error()
        return None
    if st.session_state.profile_id is None:
        navigation.missing(texts.NEED_PROFILE, "home")
        return None
    persona = active_persona()
    if persona is None:
        navigation.missing(texts.PROFILE_NOT_IN_MODE, "home")
        return None
    profile = persona["profile"]
    return Active(
        mode=st.session_state.mode,
        profile=profile,
        portfolio=persona["portfolio"],
        rules_by_id={rule["rule_id"]: rule for rule in profile.get("rules", [])},
        universe=safe_reference(data_source.get_universe, []),
    )


# --- Preuves et chargements --------------------------------------------------------

def proof_context(evidence_limits: Optional[list]) -> ProofContext:
    """Sources et limites utiles pour vérifier un chiffre (catalogue du flux B et limites du résultat)."""
    sources = safe_reference(data_source.get_sources, [], quiet=True)
    limits = {limit["limit_id"]: limit
              for limit in safe_reference(data_source.get_reference_limits, [], quiet=True)}
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


def xray_key(active: Active) -> Tuple:
    return (active.mode, fingerprint(active.profile), fingerprint(active.portfolio))


def load_xray(active: Active) -> Optional[Dict[str, Any]]:
    """Radiographie avant toute idée : code déterministe seulement, aucun agent."""
    xray_data = cached_load(
        "xray", xray_key(active),
        lambda: data_source.get_xray(active.mode, active.profile, active.portfolio), texts.XRAY_SPINNER)
    mark_shown(xray_data)
    return xray_data


def peek_xray(active: Active) -> Optional[Dict[str, Any]]:
    """Radiographie pour un usage secondaire (poids du titre qui finance l'idée), sans message.

    Code déterministe, sans agent. Un échec est mémorisé sans message (pas de nouvel appel
    à chaque exécution) ; la radiographie affichée le montre.
    """
    key = xray_key(active)
    cache = st.session_state.xray_cache
    failures = st.session_state.xray_failures
    if key not in cache and key not in failures:
        try:
            cache[key] = data_source.get_xray(active.mode, active.profile, active.portfolio)
        except data_source.DataUnavailable as exc:
            failures[key] = ("info", str(exc))
        except Exception as exc:  # usage secondaire : la page continue sans ce détail
            LOGGER.exception("Radiographie indisponible pour l'affichage du poids actuel")
            failures[key] = ("error", texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
    return cache.get(key)


def current_idea(active: Active) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Idée gardée, adaptée au portefeuille actif (US-09), et le message d'adaptation éventuel."""
    if st.session_state.idea is None:
        return None, None
    return idea_panel.effective_idea(st.session_state.idea, active.portfolio)


def analysis_key(active: Active, idea: Dict[str, Any]) -> Tuple:
    return (active.mode, fingerprint(active.profile), fingerprint(active.portfolio), fingerprint(idea))


def analysis_known(key: Tuple) -> bool:
    return key in st.session_state.analysis_cache or key in st.session_state.analysis_failures


def bedrock_waiting(active: Active, idea: Dict[str, Any]) -> bool:
    """Vrai si l'analyse demanderait les agents sans clic explicite (quotas partagés)."""
    return (active.mode == "bedrock" and not analysis_known(analysis_key(active, idea))
            and not st.session_state.analysis_request)


def load_analysis(active: Active, idea: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    result = cached_load(
        "analysis", analysis_key(active, idea),
        lambda: data_source.get_analysis(active.mode, active.profile, active.portfolio, idea),
        texts.RESULT_SPINNER)
    st.session_state.analysis_request = False
    mark_shown(result)
    return result


def load_asset_facts(active: Active, ticker: str) -> Optional[Dict[str, Any]]:
    facts = cached_load(
        "asset", (active.mode, ticker),
        lambda: data_source.get_asset_facts(active.mode, ticker, active.portfolio), texts.ASSET_FACTS_SPINNER)
    mark_shown(facts)
    return facts


def explanation_key(active: Active, result: Dict[str, Any], level: str) -> Tuple:
    return (active.mode, result["run_id"], level)


def explanation_waiting(active: Active, result: Dict[str, Any], level: str) -> bool:
    """Vrai si l'explication appellerait l'agent explicateur sans clic (mode bedrock)."""
    key = explanation_key(active, result, level)
    known = key in st.session_state.explanation_cache or key in st.session_state.explanation_failures
    return active.mode == "bedrock" and not known and not st.session_state.explanation_request


def load_explanation(active: Active, result: Dict[str, Any], level: str) -> Optional[Dict[str, Any]]:
    explanation = cached_load(
        "explanation", explanation_key(active, result, level),
        lambda: data_source.get_explanation(active.mode, result, level), texts.EXPLANATION_SPINNER)
    st.session_state.explanation_request = False
    return explanation


def idea_summary() -> Optional[str]:
    """Idée en une ligne pour l'en-tête, telle qu'elle sera analysée pour le profil actif."""
    idea = st.session_state.idea
    if idea is None:
        return None
    persona = active_persona()
    if persona is not None:
        idea = idea_panel.effective_idea(idea, persona["portfolio"])[0]
    return idea_panel.describe_idea(idea)
