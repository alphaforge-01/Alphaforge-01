"""Choix du profil fictif : cartes des personas (US-01) et profil construit (US-02).

Le profil construit passe uniquement par des cases, curseurs et listes fermées :
aucun texte libre, aucune donnée personnelle. Les règles et leurs seuils sont
produits par le flux B (`build_profile_from_answers`), jamais par l'interface.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any, Callable, Dict, List, Optional

import streamlit as st

import data_source
import ui_texts as texts
from components.persistence import KEEP_PREFIX
from components.rules import threshold_text
from components.style import PERSONA_CARD_KEY, html
from formatting import format_cad, format_horizon

LOGGER = logging.getLogger("alphaforge.ui")

# Ordre d'affichage : Robert d'abord, c'est la scène 1 de la démo.
PERSONA_ORDER = ("robert", "amira", "mateo")


def ordered_ids(personas: Dict[str, Any]) -> List[str]:
    known = [pid for pid in PERSONA_ORDER if pid in personas]
    others = sorted(pid for pid in personas if pid not in PERSONA_ORDER)
    return known + others


def _identity_line(persona: Dict[str, Any]) -> Optional[str]:
    parts = []
    if persona.get("age") is not None:
        parts.append(texts.PERSONA_AGE.format(age=persona["age"]))
    if persona.get("occupation_fr"):
        parts.append(persona["occupation_fr"])
    return ", ".join(parts) if parts else None


# Position du carrousel des personas (hors widget : survit au changement de page).
CAROUSEL_KEY = "persona_carousel_index"
# Couleur d'accent de chaque persona fictif (initiale et liseré de la carte).
PERSONA_ACCENTS = {"robert": "#1d4e89", "amira": "#7b4fc0", "mateo": "#2e7d4f"}
DEFAULT_ACCENT = "#5b6675"


def _card_html(profile_id: str, persona: Dict[str, Any], is_selected: bool) -> str:
    """Carte d'un persona fictif : initiale, identité, résumé et trois repères (risque, horizon, objectif)."""
    profile = persona["profile"]
    accent = PERSONA_ACCENTS.get(profile_id, DEFAULT_ACCENT)
    name = escape(profile["display_name"])
    identity = _identity_line(persona)
    facts = (
        (texts.PERSONA_RISK, texts.RISK_LABELS[profile["risk_tolerance"]]),
        (texts.PERSONA_HORIZON, format_horizon(profile["horizon_years_min"], profile["horizon_years_max"])),
        (texts.PERSONA_OBJECTIVE, profile["objective"]),
    )
    tiles = "".join(f'<div class="af-pc-tile"><div class="af-pc-tile-label">{escape(label)}</div>'
                    f'<div class="af-pc-tile-value">{escape(str(value))}</div></div>' for label, value in facts)
    selected = (f'<span class="af-pc-selected">{escape(texts.SELECTED_PROFILE)}</span>' if is_selected else "")
    footer = (f'{escape(texts.PERSONA_EXPERIENCE)} : {escape(texts.EXPERIENCE_LABELS[profile["experience"]])}'
              f', {escape(texts.PERSONA_CAPITAL.lower())} : {escape(format_cad(profile["capital_cad"]))}')
    return (
        f'<div class="af-pc" style="--af-accent: {accent}">'
        f'<div class="af-pc-head"><div class="af-pc-avatar">{escape(name[:1])}</div>'
        f'<div class="af-pc-id"><div class="af-pc-name">{name}'
        f'<span class="af-pc-badge">{escape(texts.FICTIONAL_BADGE)}</span>{selected}</div>'
        f'<div class="af-pc-sub">{escape(identity or "")}</div></div></div>'
        f'<div class="af-pc-summary">{escape(persona.get("summary_fr") or "")}</div>'
        f'<div class="af-pc-tiles">{tiles}</div>'
        f'<div class="af-pc-foot">{footer}</div></div>'
    )


def _move(step: int, count: int) -> None:
    st.session_state[CAROUSEL_KEY] = (st.session_state.get(CAROUSEL_KEY, 0) + step) % count


def render_persona_carousel(personas: Dict[str, Any], selected_id: Optional[str],
                            on_select: Callable[[str], None]) -> None:
    """Un persona à la fois : flèches (ou touches gauche et droite) pour passer au suivant.

    `on_select(profile_id)` est appelé par le bouton "Choisir ce profil".
    """
    ids = ordered_ids(personas)
    if not ids:
        return
    if CAROUSEL_KEY not in st.session_state:
        st.session_state[CAROUSEL_KEY] = ids.index(selected_id) if selected_id in ids else 0
    position = st.session_state[CAROUSEL_KEY] % len(ids)
    profile_id = ids[position]
    with st.container(horizontal=True, horizontal_alignment="center", vertical_alignment="center",
                      key="persona-carousel"):
        st.button("", key="persona_prev", icon=":material/chevron_left:", help=texts.CAROUSEL_PREV,
                  shortcut="left", on_click=_move, args=(-1, len(ids)))
        with st.container(key=f"{PERSONA_CARD_KEY}{profile_id}", width=560):
            try:
                html(_card_html(profile_id, personas[profile_id], profile_id == selected_id))
                st.button(
                    texts.SELECTED_PROFILE if profile_id == selected_id else texts.CHOOSE_THIS_PROFILE,
                    key=f"choose_profile_{profile_id}", type="primary", width="stretch",
                    icon=":material/check:" if profile_id == selected_id else ":material/arrow_forward:",
                    on_click=on_select, args=(profile_id,))
            except Exception as exc:  # une carte invalide ne doit pas casser la page
                LOGGER.exception("Carte du persona %s impossible à afficher", profile_id)
                st.error(texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
        st.button("", key="persona_next", icon=":material/chevron_right:", help=texts.CAROUSEL_NEXT,
                  shortcut="right", on_click=_move, args=(1, len(ids)))
    dots = "".join(f'<span class="af-dot{" af-dot--on" if i == position else ""}"></span>'
                   for i in range(len(ids)))
    html(f'<div class="af-dots" aria-label="{escape(texts.CAROUSEL_POSITION.format(n=position + 1, total=len(ids)))}">'
         f'{dots}</div>')


# Réponses du formulaire : clé du widget -> valeur par défaut. Streamlit efface l'état
# d'un widget absent de la page affichée ; une copie le garde entre les pages.
FORM_DEFAULTS: Dict[str, Any] = {
    "custom_objective": texts.OBJECTIVE_OPTIONS[2],
    "custom_horizon": (5, 10),
    "custom_risk": "moderate",
    "custom_capital": 100_000,
    "custom_experience": "intermediate",
    "custom_esg": "none",
    "custom_crypto": False,
    "custom_own_cap": False,
    "custom_cap": 20,
    "custom_portfolio": None,
}
_KEEP_PREFIX = KEEP_PREFIX


def _restore_form() -> None:
    """Avant les widgets : reprend les réponses gardées (ou les valeurs par défaut)."""
    for key, default in FORM_DEFAULTS.items():
        if key not in st.session_state:
            value = st.session_state.get(_KEEP_PREFIX + key, default)
            if value is not None:
                st.session_state[key] = value


def _keep_form() -> None:
    """Après les widgets : copie les réponses hors de l'état des widgets."""
    for key in FORM_DEFAULTS:
        if key in st.session_state:
            st.session_state[_KEEP_PREFIX + key] = st.session_state[key]


def _collect_answers() -> Dict[str, Any]:
    """Réponses du formulaire, au format attendu par profiles.check_answers."""
    left, right = st.columns(2)
    with left:
        objective = st.selectbox(texts.CUSTOM_OBJECTIVE, texts.OBJECTIVE_OPTIONS, key="custom_objective")
        horizon = st.slider(texts.CUSTOM_HORIZON, min_value=1, max_value=30, key="custom_horizon")
        risk = st.select_slider(texts.CUSTOM_RISK, options=list(texts.RISK_LABELS),
                                format_func=texts.RISK_LABELS.get, key="custom_risk")
        capital = st.number_input(texts.CUSTOM_CAPITAL, min_value=1_000, max_value=10_000_000,
                                  step=1_000, help=texts.CUSTOM_CAPITAL_HELP, key="custom_capital")
    with right:
        experience = st.radio(texts.CUSTOM_EXPERIENCE, list(texts.EXPERIENCE_LABELS),
                              format_func=texts.EXPERIENCE_LABELS.get, horizontal=True,
                              key="custom_experience")
        esg = st.radio(texts.CUSTOM_ESG, list(texts.ESG_LABELS),
                       format_func=texts.ESG_LABELS.get, horizontal=True, key="custom_esg")
        crypto = st.checkbox(texts.CUSTOM_CRYPTO, key="custom_crypto")
        own_cap = st.checkbox(texts.CUSTOM_OWN_CAP, help=texts.CUSTOM_OWN_CAP_HELP, key="custom_own_cap")
        cap_pct = (st.slider(texts.CUSTOM_CAP, min_value=1, max_value=100, key="custom_cap")
                   if own_cap else None)

    answers: Dict[str, Any] = {
        "objective": objective,
        "horizon_years_min": int(horizon[0]),
        "horizon_years_max": int(horizon[1]),
        "risk_tolerance": risk,
        "experience": experience,
        "esg_preference": esg,
        "crypto_allowed": bool(crypto),
        "capital_cad": float(capital),
    }
    if cap_pct is not None:
        answers["max_single_asset_weight"] = cap_pct / 100
    return answers


def _render_issues(issues: List[Dict[str, Any]]) -> None:
    """Erreurs (bloquantes), puis contradictions, puis points d'information."""
    show = {"error": st.error, "warning": st.warning, "info": st.info}
    for severity in ("error", "warning", "info"):
        for issue in issues:
            if issue["severity"] == severity:
                show[severity](issue["message_fr"])


def render_rules_table(rules: List[Dict[str, Any]]) -> None:
    """Règles du profil et leurs seuils, chacun étiqueté comme hypothèse de l'équipe."""
    rows = [
        {
            texts.RULE_COLUMN: rule["label_fr"],
            texts.RULE_TENSION: threshold_text(rule, rule["warn_threshold"]),
            texts.RULE_CONFLICT: threshold_text(rule, rule["limit_threshold"]),
            texts.RULE_THRESHOLD_STATUS: texts.RULE_ASSUMPTION if rule["is_assumption"] else "",
        }
        for rule in rules
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def render_custom_profile_form(personas: Dict[str, Any], active_persona: Optional[Dict[str, Any]],
                               on_use: Callable[[Dict[str, Any]], None]) -> None:
    """Formulaire du profil construit. `on_use(persona)` est appelé au clic sur le bouton.

    Le contrôle du profil (flux B) est relancé à chaque changement : les
    contradictions s'affichent tout de suite, avant même de valider.
    `active_persona` est le profil construit actuellement utilisé, ou None.
    """
    is_active = active_persona is not None
    st.caption(texts.CUSTOM_REMINDER)
    _restore_form()
    answers = _collect_answers()
    ids = ordered_ids(personas)
    labels = [personas[pid]["portfolio"]["label_fr"] for pid in ids]

    def portfolio_option(pid: str) -> str:
        label = personas[pid]["portfolio"]["label_fr"]
        if labels.count(label) > 1:  # libellés identiques : on ajoute le persona
            return f"{label} ({personas[pid]['profile']['display_name']})"
        return label

    if st.session_state.get("custom_portfolio") not in ids:
        st.session_state["custom_portfolio"] = ids[0]
    portfolio_id = st.selectbox(
        texts.CUSTOM_PORTFOLIO, ids, key="custom_portfolio", format_func=portfolio_option,
    )
    _keep_form()
    try:
        issues = data_source.check_profile_answers(answers)
    except data_source.DataUnavailable as exc:
        st.info(str(exc))
        return
    except Exception as exc:  # la démo ne doit jamais afficher une trace Python
        st.error(texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
        return
    _render_issues(issues)
    if any(issue["severity"] == "error" for issue in issues):
        return

    try:
        persona = data_source.build_custom_persona(answers, personas[portfolio_id]["portfolio"])
    except data_source.DataUnavailable as exc:
        st.info(str(exc))
        return
    except Exception as exc:  # la démo ne doit jamais afficher une trace Python
        st.error(texts.MSG_UNEXPECTED_ERROR.format(error_type=type(exc).__name__))
        return
    st.markdown(f"**{texts.CUSTOM_RULES_TITLE}**")
    render_rules_table(persona["profile"]["rules"])
    if is_active and persona != active_persona:
        st.caption(texts.CUSTOM_DRAFT_CHANGED)
    st.button(
        texts.CUSTOM_UPDATE if is_active else texts.CUSTOM_USE,
        key="custom_use",
        type="primary",
        on_click=on_use,
        args=(persona,),
    )
