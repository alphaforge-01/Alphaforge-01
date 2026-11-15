"""Cartes de mesures et verdicts de l'interface v2 (PR-2).

Composants d'affichage seulement : ils reçoivent les structures de `view_models.py`
(`MetricCard`, `Verdicts`) et n'ajoutent aucune logique financière. Un chiffre est
toujours le texte déjà affiché par le registre de preuves. Une valeur absente
(`None`) reste inconnue : la carte écrit "Non disponible" au lieu d'un zéro.

Les textes sont préparés par des fonctions pures (`card_texts`, `status_style`) pour
être testés sans interface. Les écarts s'affichent en gris (`delta_color="off"`) :
l'interface ne dit pas qu'une hausse est bonne ou mauvaise, c'est le statut de la
règle du profil qui porte le jugement.

Ce module n'est branché dans aucune page : l'interface v2 reste désactivée.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import streamlit as st

import ui_labels as labels
import ui_texts as texts
from view_models import MetricCard, VerdictBadge, Verdicts

# Statut utilisé quand un statut inconnu arrive : la carte reste lisible, sans couleur de jugement.
FALLBACK_STATUS = "missing_info"


@dataclass(frozen=True)
class StatusStyle:
    """Présentation d'un statut : libellé, couleur nommée de Streamlit, icône et phrase d'aide."""
    status: str
    label: str
    color: str
    icon: str
    help: str


@dataclass(frozen=True)
class CardTexts:
    """Textes d'une carte de mesure, prêts à afficher."""
    label: str
    value: str
    delta: Optional[str]           # None : pas d'écart dans le registre
    before_line: str               # "Avant : 6,49 %" ou "Avant : Non disponible"
    delta_note: Optional[str]      # phrase affichée seulement quand `delta` est None
    help: Optional[str]
    status: Optional[StatusStyle]


def status_style(status: Optional[str]) -> StatusStyle:
    """Style d'un statut. Un statut inconnu prend le style neutre de `missing_info`, avec son texte brut."""
    if status in texts.STATUS_LABELS:
        key = status
        label = texts.STATUS_LABELS[key]
    else:
        key = FALLBACK_STATUS
        label = str(status) if status else texts.STATUS_LABELS[FALLBACK_STATUS]
    return StatusStyle(
        status=key,
        label=label,
        color=texts.STATUS_COLORS[key],
        icon=labels.STATUS_ICONS[key],
        help=labels.STATUS_HELP[key],
    )


def card_texts(card: MetricCard) -> CardTexts:
    """Textes d'une carte. Aucune valeur manquante n'est remplacée par un nombre."""
    before = card.before_display if card.before_display else labels.NOT_AVAILABLE
    return CardTexts(
        label=card.label,
        value=card.value_display,
        delta=card.delta_display or None,
        before_line=labels.CARD_BEFORE_LINE.format(value=before),
        delta_note=None if card.delta_display else labels.CARD_DELTA_UNAVAILABLE,
        help=labels.METRIC_HELP.get(card.metric),
        status=status_style(card.status) if card.status else None,
    )


def render_metric_card(card: MetricCard) -> None:
    content = card_texts(card)
    with st.container(border=True):
        st.metric(content.label, content.value, delta=content.delta, delta_color="off",
                  help=content.help, border=False)
        st.caption(content.before_line)
        if content.delta_note:
            st.caption(content.delta_note)
        if content.status:
            st.badge(content.status.label, color=content.status.color, icon=content.status.icon,
                     help=content.status.help)


def render_metric_cards(cards: Sequence[MetricCard]) -> None:
    """Rangée de cartes. Les colonnes passent à la ligne sur un écran étroit (`wrap`)."""
    if not cards:
        return
    columns = st.columns(len(cards), gap="small", wrap=True)
    for column, card in zip(columns, cards):
        with column:
            render_metric_card(card)
    st.caption(labels.CARDS_CAPTION)


def _render_verdict(title: str, badge: Optional[VerdictBadge], help_text: str) -> None:
    st.caption(title)
    _render_verdict_badge(badge)
    st.caption(help_text)


def render_verdicts(verdicts: Verdicts, show_missing_esg: bool = False) -> None:
    """Verdict global en pleine largeur, puis financier et ESG côte à côte.

    Le verdict ESG n'est affiché que si le profil a des règles ESG (`esg` non None).
    Avec `show_missing_esg`, une phrase neutre indique l'absence de règle ESG.
    """
    with st.container(border=True):
        st.markdown(f"**{labels.VERDICT_OVERALL}**")
        _render_verdict_badge(verdicts.overall)
        st.caption(labels.VERDICT_OVERALL_HELP)
    show_esg = verdicts.esg is not None
    columns = st.columns(2 if show_esg else 1, gap="small", wrap=True)
    with columns[0]:
        with st.container(border=True):
            _render_verdict(labels.VERDICT_FINANCIAL, verdicts.financial, labels.VERDICT_FINANCIAL_HELP)
    if show_esg:
        with columns[1]:
            with st.container(border=True):
                _render_verdict(labels.VERDICT_ESG, verdicts.esg, labels.VERDICT_ESG_HELP)
    elif show_missing_esg:
        st.caption(labels.VERDICT_ESG_NONE)


def _render_verdict_badge(badge: Optional[VerdictBadge]) -> None:
    if badge is None:
        st.caption(labels.VERDICT_UNAVAILABLE)
        return
    style = status_style(badge.status)
    st.badge(style.label, color=style.color, icon=style.icon, help=style.help)
