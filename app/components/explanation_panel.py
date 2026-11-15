"""Explication au niveau choisi, novice ou pro (US-10, US-11).

Le texte vient du pipeline du flux C (`explain`) : agent explicateur ou gabarit,
avec les renvois déjà remplacés par les valeurs du registre. L'interface
l'affiche tel quel et liste les preuves citées, chacune vérifiable.
"""
from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

import ui_texts as texts
from formatting import escape_dollars
from components.evidence import ProofContext, display, render_proof


def _without_title(markdown: str) -> str:
    """Retire le titre H1 du texte rendu : la section a déjà son titre."""
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).lstrip("\n")
    return markdown


def subject_label(subject: str) -> str:
    """"portfolio_after" -> "après", "variant:V1" -> "variante V1"."""
    if subject.startswith("variant:"):
        return texts.SUBJECT_VARIANT.format(variant_id=subject.split(":", 1)[1])
    return texts.SUBJECT_LABELS.get(subject, subject)


def render_cited_evidence(explanation: Mapping[str, Any], result: Mapping[str, Any], ctx: ProofContext) -> None:
    evidence = result["evidence"]
    cited = [ref for ref in explanation["validation"].get("checked_references", []) if ref in evidence]
    if not cited:
        return
    st.caption(texts.EXPLANATION_EVIDENCE)
    columns = st.columns(3)
    for position, evidence_id in enumerate(cited):
        entry = evidence[evidence_id]
        with columns[position % 3]:
            label = (f"{evidence_id} : {entry.get('label_fr', '')} "
                     f"({subject_label(entry.get('subject', ''))}), {display(entry)}")
            with st.popover(label, help=texts.PROOF_HELP, key=f"expl_{evidence_id}", width="stretch"):
                render_proof(entry, ctx)


def render_fallback_note(explanation: Mapping[str, Any]) -> None:
    """Le repli sur le gabarit est dit dans la section, pas seulement dans la trace (US-10)."""
    step = next((s for s in explanation.get("trace") or [] if s.get("name") == "explanation"), None)
    if step and step.get("status") == "fallback":
        reason = (step.get("details") or {}).get("fallback_reason", "")
        st.info(texts.EXPLANATION_FALLBACK.format(reason=texts.REASON_CODES_FR.get(reason, reason)))


def render_origin(explanation: Mapping[str, Any]) -> None:
    """Origine du texte : agent explicateur ou gabarit, avec le badge "texte de repli" (US-10)."""
    origin = explanation["output"].get("origin", "template")
    render_fallback_note(explanation)
    st.badge(texts.EXPLANATION_ORIGIN.get(origin, origin), color="violet" if origin == "llm" else "gray",
             help=texts.EXPLANATION_ORIGIN_HELP.get(origin))


def render_explanation(explanation: Mapping[str, Any], result: Mapping[str, Any], ctx: ProofContext) -> None:
    with st.container(border=True):
        st.markdown(escape_dollars(_without_title(explanation["rendered_markdown"])))
    render_cited_evidence(explanation, result, ctx)
