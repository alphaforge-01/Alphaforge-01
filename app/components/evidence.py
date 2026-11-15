"""Chiffres vérifiables (US-11) : chaque chiffre affiché ouvre sa preuve au clic.

Un chiffre calculé vient toujours du registre de preuves (`EvidenceEntry`) :
l'interface affiche son `display_value` tel quel et ne le recalcule jamais.
Sans entrée dans le registre, elle affiche "non disponible".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import streamlit as st

import ui_texts as texts
from formatting import format_date


@dataclass
class ProofContext:
    """Ce qu'il faut pour afficher une preuve : sources, limites et niveau de lecture."""
    level: str = "novice"
    # Les numéros E1, E2... sont propres à un registre : ils ne sont montrés que pour celui du résultat.
    show_id: bool = True
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # fichier -> ligne de sources_metadata
    limits: Dict[str, Dict[str, Any]] = field(default_factory=dict)    # limit_id -> limite


def index_by_key(evidence: Mapping[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """evidence_key ("<metric>:<subject>") -> entrée du registre."""
    return {entry["evidence_key"]: entry for entry in evidence.values()}


def lookup(index: Mapping[str, Dict[str, Any]], metric: str, subject: str) -> Optional[Dict[str, Any]]:
    return index.get(f"{metric}:{subject}")


def display(entry: Optional[Dict[str, Any]]) -> str:
    if entry is None or entry.get("display_value") in (None, ""):
        return texts.NOT_AVAILABLE
    return str(entry["display_value"])


def _source_line(source_id: str, ctx: ProofContext) -> str:
    row = ctx.sources.get(source_id)
    if not row:
        return f"`{source_id}`"
    parts = [f"`{source_id}`", str(row.get("source") or "")]
    if row.get("retrieved_on"):
        parts.append(f"({row['retrieved_on']})")
    return " ".join(part for part in parts if part)


def render_proof(entry: Dict[str, Any], ctx: ProofContext) -> None:
    """Contenu du clic sur un chiffre : calcul, source, période, devise, limites."""
    st.markdown(f"**{entry.get('label_fr', '')}**")
    lines: List[str] = [
        f"- {texts.PROOF_VALUE} : {display(entry)}",
        (f"- {texts.PROOF_ID} : `{entry.get('evidence_id', '')}`" if ctx.show_id
         else f"- {texts.PROOF_KEY} : `{entry.get('evidence_key', '')}`"),
        f"- {texts.PROOF_TOOL} : `{entry.get('tool_name', '')}`",
    ]
    if entry.get("period_start") and entry.get("period_end"):
        period = texts.PROOF_PERIOD_VALUE.format(
            start=format_date(entry["period_start"]), end=format_date(entry["period_end"]))
        lines.append(f"- {texts.PROOF_PERIOD} : {period}")
    if entry.get("as_of"):
        lines.append(f"- {texts.PROOF_DATA_AS_OF} : {format_date(entry['as_of'])}")
    if entry.get("currency"):
        lines.append(f"- {texts.PROOF_CURRENCY} : {entry['currency']}")
    if entry.get("n_observations") is not None:
        lines.append(f"- {texts.PROOF_OBSERVATIONS} : {entry['n_observations']}")
    if entry.get("qualifier"):
        qualifier = texts.QUALIFIER_LABELS.get(entry["qualifier"], entry["qualifier"])
        lines.append(f"- {texts.PROOF_QUALIFIER} : {qualifier}")
    sources = entry.get("source_ids") or []
    lines.append(f"- {texts.PROOF_SOURCES} : "
                 + (", ".join(_source_line(s, ctx) for s in sources) if sources else texts.PROOF_NONE))
    st.markdown("\n".join(lines))
    if entry.get("transformation"):
        st.caption(f"{texts.PROOF_TRANSFORMATION} : {entry['transformation']}")
    limit_ids = entry.get("limit_ids") or []
    if limit_ids:
        st.markdown(f"**{texts.PROOF_LIMITS}**")
        text_key = "text_pro" if ctx.level == "pro" else "text_novice"
        for limit_id in limit_ids:
            limit = ctx.limits.get(limit_id)
            text = limit.get(text_key) if limit else None
            st.caption(f"{limit_id} : {text}" if text else limit_id)


def render_value(entry: Optional[Dict[str, Any]], ctx: ProofContext, key: str) -> None:
    """Le chiffre lui-même est le bouton : un clic ouvre sa preuve."""
    if entry is None:
        st.markdown(texts.NOT_AVAILABLE)
        return
    with st.popover(display(entry), help=texts.PROOF_HELP, key=key):
        render_proof(entry, ctx)


def render_card(entry: Optional[Dict[str, Any]], ctx: ProofContext, key: str,
                label: Optional[str] = None, caption: Optional[str] = None) -> None:
    """Carte de métrique : libellé du registre, chiffre cliquable, note facultative."""
    with st.container(border=True):
        st.caption(label or (entry or {}).get("label_fr") or texts.NOT_AVAILABLE)
        render_value(entry, ctx, key)
        if caption:
            st.caption(caption)
