"""Statut par règle du profil (US-03, US-06, US-07).

Le statut, la marge et le contrefactuel viennent de la gouvernance du flux B
(`GovernanceResult`), jamais de l'interface. La mesure vient du registre de
preuves. Les seuils sont des paramètres du profil, étiquetés comme hypothèses.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import streamlit as st

import data_source
import ui_texts as texts
from components.evidence import ProofContext, index_by_key, lookup, render_value
from formatting import format_pct, format_pts

# Règles par classe d'actifs : une classe absente du portefeuille n'a pas de preuve
# dans le registre, et la gouvernance la compte à 0.
_CLASS_RULES = ("max_asset_class_weight", "excluded_asset_class")


def threshold_text(rule: Mapping[str, Any], threshold: Optional[float]) -> str:
    """Seuil d'une règle (paramètre du profil, pas un résultat de calcul)."""
    if threshold is None:
        return texts.RULE_NONE
    if rule.get("unit") == "bool":
        return texts.RULE_EXCLUDED
    if rule.get("direction") == "min" and threshold <= 0:
        return texts.RULE_NONE  # un plancher à 0 ne peut jamais être franchi
    template = texts.RULE_BELOW if rule.get("direction") == "min" else texts.RULE_ABOVE
    return template.format(value=format_pct(threshold))


def sort_checks(checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Conflits d'abord, puis tensions, informations manquantes et règles conformes."""
    order = {status: rank for rank, status in enumerate(texts.STATUS_ORDER)}
    return sorted(checks, key=lambda check: (order.get(check["status"], len(order)), check["check_id"]))


def _value_entry(check: Dict[str, Any], rule: Mapping[str, Any], evidence: Mapping[str, Dict[str, Any]],
                 index: Mapping[str, Dict[str, Any]], subject: str) -> Optional[Dict[str, Any]]:
    for evidence_id in check.get("evidence_ids") or []:
        if evidence_id in evidence:
            return evidence[evidence_id]
    asset_class = (rule.get("params") or {}).get("asset_class")
    if asset_class:
        return lookup(index, f"weight_by_asset_class.{asset_class}", subject)
    # Correspondance règle -> métrique tenue par le flux B (governance.rule_metric).
    metric = data_source.rule_metric(check.get("rule_type", ""))
    return lookup(index, metric, subject) if metric else None


def _margin_text(check: Dict[str, Any]) -> Optional[str]:
    margin = check.get("margin")
    if margin is None or check.get("unit") != "pct":
        return None
    if check["status"] == "conflict":
        return texts.RULE_BEYOND_LIMIT.format(margin=format_pts(abs(margin)))
    if check["status"] == "tension" or check.get("warn_threshold") is None:
        return texts.RULE_MARGIN_TO_CONFLICT.format(margin=format_pts(margin))
    if check["status"] == "compliant":
        return texts.RULE_MARGIN_TO_TENSION.format(margin=format_pts(margin))
    return None


def counterfactual_text(check: Dict[str, Any]) -> Optional[str]:
    counterfactual = check.get("counterfactual")
    if not counterfactual or check["status"] not in ("tension", "conflict"):
        return None
    if counterfactual.get("compliant_at_or_below") is None:
        return texts.RULE_NO_COUNTERFACTUAL
    return texts.RULE_COUNTERFACTUAL.format(value=counterfactual["display_value"])


def status_badge(status: str) -> None:
    st.badge(texts.STATUS_LABELS.get(status, status), color=texts.STATUS_COLORS.get(status, "gray"))


def render_checks(checks: List[Dict[str, Any]], evidence: Mapping[str, Dict[str, Any]], subject: str,
                  rules_by_id: Mapping[str, Dict[str, Any]], ctx: ProofContext, key_prefix: str,
                  show_counterfactual: bool = True) -> None:
    """Une ligne par règle : statut, libellé, mesure vérifiable, seuils, marge, contrefactuel."""
    index = index_by_key(evidence)
    for check in sort_checks(checks):
        rule = {**(rules_by_id.get(check["rule_id"]) or {}), "unit": check.get("unit")}
        with st.container(border=True):
            head, measure, detail = st.columns([4, 2, 5], vertical_alignment="center")
            with head:
                status_badge(check["status"])
                st.markdown(f"**{check['label_fr']}**")
            with measure:
                entry = _value_entry(check, rule, evidence, index, subject)
                if entry is None and check.get("rule_type") in _CLASS_RULES and check.get("value") == 0:
                    st.markdown(texts.RULE_NO_POSITION)
                else:
                    render_value(entry, ctx, key=f"{key_prefix}_{check['check_id']}")
            with detail:
                if check["status"] == "missing_info":
                    st.markdown(texts.RULE_MISSING.format(reason=check.get("missing_reason") or ""))
                if show_counterfactual:
                    counterfactual = counterfactual_text(check)
                    if counterfactual:
                        st.markdown(f"**{counterfactual}**")
                lines = [texts.RULE_THRESHOLDS.format(
                    warn=threshold_text(rule, check.get("warn_threshold")),
                    limit=threshold_text(rule, check.get("limit_threshold")))]
                margin = _margin_text(check)
                if margin:
                    lines.append(margin)
                # Seuils : paramètres du profil, hypothèses de l'équipe (info-bulle).
                st.caption(" ".join(lines), help=texts.RULE_THRESHOLDS_HELP)


def render_key_points(checks: List[Dict[str, Any]], evidence: Mapping[str, Dict[str, Any]], subject: str,
                      rules_by_id: Mapping[str, Dict[str, Any]], ctx: ProofContext, key_prefix: str,
                      limit: int = 3) -> None:
    """Deux ou trois points clés : règles les plus graves, chiffre cliquable, contrefactuel ou marge."""
    index = index_by_key(evidence)
    for check in sort_checks(checks)[:limit]:
        rule = {**(rules_by_id.get(check["rule_id"]) or {}), "unit": check.get("unit")}
        status_col, label_col, value_col = st.columns([2, 5, 2], vertical_alignment="center")
        with status_col:
            status_badge(check["status"])
        with label_col:
            st.markdown(check["label_fr"])
            # Le contrefactuel est déjà dans le verdict : ici, la marge, sans répétition.
            note = _margin_text(check)
            if check["status"] == "missing_info":
                note = texts.RULE_MISSING.format(reason=check.get("missing_reason") or "")
            if note:
                st.caption(note)
        with value_col:
            entry = _value_entry(check, rule, evidence, index, subject)
            if entry is None and check.get("rule_type") in _CLASS_RULES and check.get("value") == 0:
                st.markdown(texts.RULE_NO_POSITION)
            else:
                render_value(entry, ctx, key=f"{key_prefix}_{check['check_id']}")
