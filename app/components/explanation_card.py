"""Carte d'explication structurée de l'interface v2 (PR-4).

La carte affiche une explication par sections : résumé, contexte du profil fictif, raisons
du verdict, contrefactuels calculés, variantes, détail des contrôles, preuves citées, glossaire,
limites et avertissements. Les sections viennent de `explanation_rendering.render_sections`
(flux B) : mêmes renvois remplacés, mêmes valeurs que le texte Markdown déjà validé. La carte
n'ajoute ni texte financier ni chiffre.

- Niveaux novice et pro : le niveau est celui du résultat, la carte ne le change pas. Le niveau pro
  ajoute des colonnes au détail des contrôles et des champs techniques aux preuves.
- Origine du texte : le badge "Rédigé par l'agent explicateur" ou "Texte standard" (gabarit de
  secours), le repli et l'ancrage faible sont affichés par `explanation_panel.render_origin`.
- Avertissements : les avertissements fixes s'affichent une fois, les limites une fois. Un texte
  identique à un autre déjà affiché n'est pas répété (`warning_blocks`).
- Données manquantes : sans dossier (`brief`) ou si les sections ne peuvent pas être construites,
  la carte retombe sur le texte Markdown déjà rendu, sans titre répété.

Branchée dans l'onglet "Explication complète" des réponses (explanation_panel.render_explanation).
Les intertitres sont des blocs HTML à classe (af-expl-h) : la feuille de style les met en forme.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, List, Mapping, Optional, Tuple

import pandas as pd
import streamlit as st

import ui_labels as labels
from alphaforge.explanation_rendering import CheckRow, RenderedSections, render_sections
from components.cards import status_style
from components.explanation_panel import render_origin
from components.style import html
from formatting import escape_dollars

LEVELS = ("novice", "pro")


# --- Données de la carte ----------------------------------------------------------

def build_sections(explanation: Mapping[str, Any]) -> Optional[RenderedSections]:
    """Sections de l'explication, ou None si le dossier manque ou ne permet pas de les construire."""
    output, brief = explanation.get("output"), explanation.get("brief")
    if not isinstance(output, Mapping) or not isinstance(brief, Mapping):
        return None
    try:
        sections = render_sections(output, brief)  # type: ignore[arg-type]
    except (ValueError, KeyError, TypeError):
        return None
    # Le Markdown déjà rendu et validé fait foi : si le dossier ne couvre pas les renvois du texte
    # (dossier d'un autre résultat, dossier incomplet), les sections montreraient des renvois
    # inconnus que le Markdown n'a pas. On retombe alors sur le Markdown.
    markdown = explanation.get("rendered_markdown")
    if isinstance(markdown, str) and _unknown_references(sections) > markdown.count(UNKNOWN_REFERENCE):
        return None
    return sections


UNKNOWN_REFERENCE = "[référence inconnue"


def _unknown_references(sections: RenderedSections) -> int:
    """Nombre de renvois inconnus signalés dans les textes des sections."""
    texts = [sections.summary, sections.counterfactual, sections.variants, sections.limits_context,
             *[factor.text for factor in sections.factors]]
    return sum(text.count(UNKNOWN_REFERENCE) for text in texts)


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split()).rstrip(".")


@dataclass(frozen=True)
class WarningBlocks:
    """Avertissements et limites à afficher, sans texte en double."""
    disclaimers: Tuple[str, ...]
    threshold_notice: Optional[str]
    limits: Tuple[Tuple[str, str], ...]
    limits_context: str


def warning_blocks(sections: RenderedSections) -> WarningBlocks:
    """Avertissements fixes, phrase sur les seuils, limites et texte de contexte, chacun une seule fois.

    Un texte dont la forme normalisée (casse, espaces, point final) a déjà été retenue est omis. L'ordre
    de priorité est celui de l'affichage : avertissements, seuils, limites, puis texte de contexte.
    """
    seen: set = set()

    def fresh(text: str) -> bool:
        key = _normalized(text)
        if not key or key in seen:
            return False
        seen.add(key)
        return True

    disclaimers = tuple(text for _, text in sections.disclaimers if fresh(text))
    notice = sections.threshold_notice if sections.threshold_notice and fresh(sections.threshold_notice) else None
    limits = tuple((limit_id, text) for limit_id, text in sections.limits if fresh(text))
    context = sections.limits_context if fresh(sections.limits_context) else ""
    return WarningBlocks(disclaimers, notice, limits, context)


def check_table(sections: RenderedSections) -> pd.DataFrame:
    """Tableau du détail des contrôles, textes tels que fournis par `render_sections`."""
    columns = labels.EXPL_CHECK_COLUMNS["pro" if sections.level == "pro" else "novice"]

    def row(item: CheckRow) -> List[str]:
        if sections.level == "pro":
            return [item.check_id, item.rule_text, item.status_fr, item.value_text, item.warn_text,
                    item.limit_text, item.margin_text, ", ".join(item.evidence_ids) or labels.EXPL_NO_EVIDENCE]
        return [item.label, item.status_fr, item.value_text, item.warn_text, item.limit_text]

    return pd.DataFrame([row(item) for item in sections.check_rows], columns=list(columns))


# --- Rendu -----------------------------------------------------------------------

def _text(markdown: str) -> None:
    st.markdown(escape_dollars(markdown))


def _heading(title: str) -> None:
    """Intertitre de section (mise en forme par la classe af-expl-h)."""
    html(f'<div class="af-expl-h">{escape(title, quote=False)}</div>')


def _render_header(explanation: Mapping[str, Any], level: str) -> None:
    _heading(labels.EXPL_TITLE)
    if level in labels.EXPL_LEVEL_BADGE:
        st.badge(labels.EXPL_LEVEL_BADGE[level], color="blue", help=labels.EXPL_LEVEL_HELP)
    if isinstance(explanation.get("output"), Mapping):
        render_origin(explanation)  # type: ignore[arg-type]


def _render_profile_context(sections: RenderedSections) -> None:
    context = sections.profile_context
    if context is None:
        return
    with st.expander(labels.EXPL_PROFILE_TITLE, expanded=False):
        st.caption(context.notice)
        for label, value in context.items:
            _text(f"- **{label}** : {value}")


def _render_factors(sections: RenderedSections) -> None:
    if not sections.factors:
        return
    _heading(labels.EXPL_FACTORS_TITLE)
    for position, factor in enumerate(sections.factors):
        with st.container(key=f"af-expl-factor-{position}"):
            if factor.status:
                style = status_style(factor.status)
                st.badge(style.label, color=style.color, icon=style.icon, help=style.help)
            _text(factor.text)


def _render_counterfactual(sections: RenderedSections) -> None:
    if not sections.counterfactual:
        return
    _heading(labels.EXPL_COUNTERFACTUAL_TITLE)
    _text(sections.counterfactual)
    for item in sections.counterfactual_items:
        _text(f"- {item.label} : {item.text}")


def _render_checks(sections: RenderedSections, blocks: WarningBlocks) -> None:
    if not sections.check_rows:
        return
    with st.expander(labels.EXPL_CHECKS_TITLE, expanded=sections.level == "pro"):
        st.dataframe(check_table(sections), hide_index=True, width="stretch")
        for label, reason in sections.check_notes:
            _text(f"- {label} : {reason}")
        if blocks.threshold_notice:
            st.caption(blocks.threshold_notice)


def _render_evidence(sections: RenderedSections) -> None:
    if not sections.evidence:
        return
    with st.expander(labels.EXPL_EVIDENCE_TITLE.format(count=len(sections.evidence)), expanded=False):
        for item in sections.evidence:
            _text(f"**{item.evidence_id}** : {item.label} = **{item.value_text}**")
            for detail in item.details:
                st.caption(escape_dollars(detail))


def _render_glossary(sections: RenderedSections) -> None:
    if not sections.glossary:
        return
    with st.expander(labels.EXPL_GLOSSARY_TITLE.format(count=len(sections.glossary)), expanded=False):
        for entry in sections.glossary:
            line = f"**{entry.term}** : {entry.definition}."
            if entry.analogy:
                line += " " + labels.EXPL_GLOSSARY_IMAGE.format(text=entry.analogy)
            _text(line)


def _render_limits(blocks: WarningBlocks) -> None:
    if not blocks.limits and not blocks.limits_context:
        return
    _heading(labels.EXPL_LIMITS_TITLE)
    if blocks.limits_context:
        _text(blocks.limits_context)
    with st.container(key="af-expl-limits"):
        for limit_id, text in blocks.limits:
            _text(f"- **{limit_id}** : {text}")


def _render_plain(explanation: Mapping[str, Any]) -> None:
    """Texte Markdown déjà rendu (sans son titre), quand les sections ne sont pas disponibles."""
    markdown = explanation.get("rendered_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        st.caption(labels.EXPL_NOT_AVAILABLE)
        return
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        markdown = "\n".join(lines[1:]).lstrip("\n")
    st.caption(labels.EXPL_PLAIN_NOTE)
    _text(markdown)


def render_explanation_card(explanation: Optional[Mapping[str, Any]]) -> None:
    """Affiche une explication (`ExplanationResult`) en sections. Sans explication : "Non disponible"."""
    with st.container(key="af-expl-card"):
        if not isinstance(explanation, Mapping):
            st.caption(labels.EXPL_NOT_AVAILABLE)
            return
        sections = build_sections(explanation)
        output = explanation.get("output") if isinstance(explanation.get("output"), Mapping) else {}
        level = sections.level if sections else str(output.get("level", ""))
        _render_header(explanation, level)
        if sections is None:
            _render_plain(explanation)
            return
        blocks = warning_blocks(sections)
        if blocks.disclaimers:
            with st.container(key="af-expl-warnings"):
                st.caption(labels.EXPL_WARNINGS_TITLE)
                for text in blocks.disclaimers:
                    _text(f"- {text}")
        if sections.idea_line:
            st.caption(escape_dollars(sections.idea_line))
        if sections.summary:
            _heading(labels.EXPL_SUMMARY_TITLE)
            with st.container(key="af-expl-summary"):
                _text(sections.summary)
        _render_profile_context(sections)
        _render_factors(sections)
        _render_counterfactual(sections)
        if sections.variants:
            _heading(labels.EXPL_VARIANTS_TITLE)
            _text(sections.variants)
        _render_checks(sections, blocks)
        _render_evidence(sections)
        _render_glossary(sections)
        _render_limits(blocks)
