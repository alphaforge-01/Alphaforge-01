"""Trace à six étapes (US-13), construite par le code du flux C à partir des appels réels.

Étapes 1 à 3 : `AnalysisResult.trace`. Étapes 4 à 6 : `ExplanationResult.trace`.
Aucun raisonnement interne de modèle n'existe dans la trace, et rien n'en est déduit ici.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import streamlit as st

import ui_texts as texts
from formatting import format_pct


def _reason(code: Optional[str]) -> str:
    return texts.REASON_CODES_FR.get(code or "", code or "")


def _params_text(params: Mapping[str, Any]) -> str:
    if not params:
        return texts.TRACE_NO_PARAMS
    parts = []
    for key, value in params.items():
        if value is None:
            continue
        if key == "target_weight" and isinstance(value, (int, float)):
            value = format_pct(value)
        elif key == "funding_source":
            value = texts.IDEA_FUNDING_LABELS.get(value, value)
        parts.append(f"{key} = {value}")
    return ", ".join(parts) or texts.TRACE_NO_PARAMS


def _evidence_text(evidence_ids: List[str]) -> str:
    if not evidence_ids:
        return texts.PROOF_NONE
    if len(evidence_ids) <= 3:
        return ", ".join(evidence_ids)
    return f"{evidence_ids[0]} à {evidence_ids[-1]} ({len(evidence_ids)})"


def _render_tool_calls(details: Mapping[str, Any]) -> None:
    calls = details.get("tool_calls") or []
    if not calls:
        return
    st.markdown(f"**{texts.TRACE_TOOL_CALLS}**")
    rows = [
        {
            texts.COLUMN_TOOL: texts.TOOL_LABELS.get(call.get("tool_name"), call.get("tool_name")),
            texts.COLUMN_CALLER: texts.TRACE_ACTORS.get(call.get("caller"), call.get("caller") or "-"),
            texts.COLUMN_PARAMS: _params_text(call.get("params") or {}),
            texts.COLUMN_STATUS: texts.TRACE_STATUSES.get(
                call.get("status"), texts.STATUS_LABELS.get(call.get("status"), call.get("status"))),
            texts.COLUMN_EVIDENCE: _evidence_text(call.get("evidence_ids") or []),
        }
        for call in calls
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def _status_label(status: Optional[str]) -> str:
    return texts.STATUS_LABELS.get(status or "", status or "")


def _step_lines(step: Mapping[str, Any]) -> List[str]:
    details = step.get("details") or {}
    name = step.get("name")
    lines: List[str] = []
    if step.get("model_id"):
        lines.append(f"{texts.TRACE_MODEL} : `{step['model_id']}`")
    if name == "analysis" and details.get("turns"):
        lines.append(f"{texts.TRACE_TURNS} : {details['turns']}")
    if name == "governance":
        lines.append(texts.TRACE_BEFORE_AFTER.format(
            before=_status_label(details.get("overall_before")), after=_status_label(details.get("overall_after"))))
    if name == "brief":
        lines.append(texts.TRACE_BRIEF.format(
            brief_id=details.get("brief_id", ""), factors=", ".join(details.get("ranked_factors") or []) or "-",
            limits=", ".join(details.get("limit_ids") or []) or "-"))
    if name == "explanation":
        lines.append(texts.TRACE_EXPLANATION.format(
            level=texts.LEVEL_LABELS.get(details.get("level"), details.get("level")),
            origin=texts.TRACE_ORIGINS.get(details.get("origin"), details.get("origin")),
            attempt=details.get("attempt", 0), cache=texts.YES if details.get("from_cache") else texts.NO))
    if name == "validation":
        codes = details.get("rejection_codes") or []
        if details.get("is_valid") and not codes:
            lines.append(texts.TRACE_VALIDATION_OK.format(count=details.get("checked_references", 0)))
        else:
            lines.append(texts.TRACE_VALIDATION_KO.format(codes=", ".join(codes) or "-"))
    if name == "guardrail":
        if "action" in details:
            scores = {key: details.get(key) for key in ("grounding_score", "relevance_score")}
            lines.append(texts.TRACE_GUARDRAIL.format(
                action=texts.TRACE_GUARDRAIL_ACTIONS.get(details["action"], details["action"]),
                grounding="-" if scores["grounding_score"] is None else f"{scores['grounding_score']:.2f}",
                relevance="-" if scores["relevance_score"] is None else f"{scores['relevance_score']:.2f}"))
        if details.get("denied_topics"):
            topics = ", ".join(texts.GUARDRAIL_TOPIC_LABELS.get(t, t) for t in details["denied_topics"])
            lines.append(texts.TRACE_GUARDRAIL_DENIED.format(topics=topics))
        if details.get("grounding_below_threshold") and not details.get("replaced_by_template"):
            lines.append(texts.TRACE_GUARDRAIL_BELOW_THRESHOLD)
        if details.get("error"):
            lines.append(texts.TRACE_GUARDRAIL_ERROR.format(error=details["error"]))
        if details.get("replaced_by_template"):
            lines.append(texts.TRACE_GUARDRAIL_REPLACED)
        if details.get("grounding_score") is not None:
            lines.append(texts.TRACE_GUARDRAIL_SCORE_NOTE)
    if details.get("fallback_reason"):
        lines.append(f"{texts.TRACE_REASON} : {_reason(details['fallback_reason'])}")
    elif name == "guardrail" and details.get("reason"):
        lines.append(texts.TRACE_GUARDRAIL_NOT_RUN.format(reason=_reason(details["reason"])))
    saved = details.get("trace_saved")
    if isinstance(saved, dict):
        lines.append(texts.TRACE_SAVED.format(location=saved.get("location")) if saved.get("saved")
                     else texts.TRACE_NOT_SAVED.format(reason=_reason(saved.get("reason"))))
    return lines


def _status_badge(step: Mapping[str, Any]) -> tuple:
    """Libellé et couleur de l'état. Une intervention du garde-fou n'est jamais "réussi" (règle 8)."""
    details = step.get("details") or {}
    if step.get("name") == "guardrail":
        if details.get("action") == "intervened" or details.get("replaced_by_template"):
            return texts.TRACE_STATUS_INTERVENTION, "orange"
        if details.get("grounding_below_threshold"):   # signalé, mais le texte du modèle reste affiché
            return texts.TRACE_STATUS_FLAGGED, "orange"
    status = step.get("status")
    return (texts.TRACE_STATUSES.get(status, status),
            "orange" if status in ("fallback", "error") else "gray")


def render_step(step: Mapping[str, Any], brief: Optional[Mapping[str, Any]]) -> None:
    with st.container(border=True):
        head, actor, status, duration = st.columns([4, 2, 2, 2], vertical_alignment="center")
        head.markdown("**" + texts.TRACE_STEP.format(
            step=step.get("step"), name=texts.TRACE_STEP_NAMES.get(step.get("name"), step.get("name"))) + "**")
        with actor:
            st.badge(texts.TRACE_ACTORS.get(step.get("actor"), step.get("actor")),
                     color="violet" if step.get("actor") == "agent" else
                     "blue" if step.get("actor") == "guardrail" else "gray")
        with status:
            label, color = _status_badge(step)
            st.badge(label, color=color)
        duration.caption(texts.TRACE_DURATION_VALUE.format(ms=step.get("duration_ms", 0)))
        lines = _step_lines(step)
        if lines:
            st.caption("  \n".join(lines))
        if step.get("name") == "analysis":
            _render_tool_calls(step.get("details") or {})
        # Le dossier affiché est celui que l'explicateur a reçu à l'étape 4 (niveau courant).
        if step.get("name") == "explanation" and brief is not None:
            with st.popover(texts.TRACE_EXPLAINER_SAW, help=texts.TRACE_EXPLAINER_SAW_HELP):
                st.json(dict(brief), expanded=1)


def render_trace(result: Mapping[str, Any], explanation: Optional[Mapping[str, Any]]) -> None:
    st.caption(texts.TRACE_INTRO)
    steps: List[Dict[str, Any]] = list(result.get("trace") or [])
    brief = None
    if explanation is not None:
        steps += list(explanation.get("trace") or [])
        brief = explanation.get("brief")
    for step in sorted(steps, key=lambda item: item.get("step", 0)):
        render_step(step, brief)
