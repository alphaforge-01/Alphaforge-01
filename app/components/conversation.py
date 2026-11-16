"""Fil de la conversation : demandes en langage naturel, réglages manuels et réponses de l'agent.

Chaque réponse est courte (verdict, points clés cliquables, résumé de l'explication,
avertissement), puis dépliable : détail par zones, explication complète, sources et
limites, trace. Le texte d'une analyse vient de `get_explanation` (agent ou gabarit), celui
d'une question de profil ou d'un "pourquoi" de `answer_question` (agent conversationnel sous contrôle,
ou réponse du code), et les chiffres du registre de preuves : ce module n'invente ni ne calcule rien.
Seule la réponse la plus récente est détaillée ; les précédentes restent compactes.
"""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Dict, List, Mapping, Optional

import streamlit as st

import data_source
import ui_texts as texts
from components import explanation_panel, idea_panel, result_panel, trace_panel
from components.evidence import ProofContext
from components.persistence import kept_toggle
from components.rules import render_key_points
from components.style import html, pill
from formatting import escape_dollars, format_pct, summary_section


# Interrupteur du menu de paramètres (démo et jury) : affiche l'onglet Trace des réponses.
SHOW_TRACE_KEY = "show_trace"


def _guard_caption(action: Optional[str]) -> Optional[str]:
    if action is None:
        return None
    return texts.CHAT_GUARD_STATUS.get(action, texts.CHAT_GUARD_STATUS["not_run"])


def _topics(topics: List[str]) -> str:
    return ", ".join(texts.GUARDRAIL_TOPIC_LABELS.get(topic, topic) for topic in topics) or texts.GUARDRAIL_NO_TOPIC


def render_welcome(on_example: Callable[[str], None]) -> None:
    with st.chat_message("assistant"):
        st.markdown(texts.CHAT_WELCOME)
        with st.container(horizontal=True):
            for position, example in enumerate(texts.CHAT_EXAMPLES):
                st.button(example, key=f"chat_example_{position}", on_click=on_example, args=(example,))


def _render_refused(entry: Mapping[str, Any], index: int = 0,
                    on_choice: Optional[Callable[..., None]] = None) -> None:
    idea = entry.get("reformulation")
    if idea and on_choice is not None:
        # Refus du garde-fou, mais une idée fictive précise dans le message : avertir, puis proposer
        # la simulation (rien n'est simulé avant le clic, le message n'est envoyé à aucun modèle).
        label = idea_panel.describe_idea(idea)
        st.warning(texts.CHAT_REFUSED_WARNING.format(topics=_topics(entry.get("topics") or [])))
        st.caption(texts.CHAT_REFUSED_BY[entry.get("by", "local")])
        st.markdown(texts.CHAT_REFORMULATION.format(idea=label))
        st.button(texts.CHAT_CONFIRM_YES, key=f"reformulate_{index}", type="primary", on_click=on_choice,
                  args=(idea, texts.CHAT_CHOICE.format(choice=label)))
        return
    st.error(texts.CHAT_REFUSED.format(topics=_topics(entry.get("topics") or [])))
    st.caption(texts.CHAT_REFUSED_BY[entry.get("by", "local")])
    guard = _guard_caption(entry.get("guard_action"))
    if guard and entry.get("by") == "local":
        st.caption(guard)
    st.markdown(texts.CHAT_REFUSED_HELP)


def _render_clarify(entry: Mapping[str, Any], index: int, on_choice: Callable[..., None]) -> None:
    parsed = entry["parsed"]
    reason = parsed.get("reason")
    tickers = parsed.get("tickers") or []
    weight = parsed.get("target_weight")
    funding = parsed.get("funding_ticker")
    question = texts.CHAT_CLARIFY.get(reason, texts.CHAT_CLARIFY["not_an_idea"])
    st.markdown(question.format(
        tickers=", ".join(tickers), unknown=", ".join(parsed.get("unknown_tokens") or []) or "?",
        funding=funding or ""))
    funding_source = "from_ticker" if funding else "pro_rata"
    choices = []
    # Poids manquant, ou décimal (arrondi proposé) : un bouton par poids, même actif et même financement.
    if reason in ("missing_weight", "weight_out_of_range", "relative_weight") and len(tickers) == 1:
        choices = [idea_panel.make_idea(tickers[0], option, funding_source, funding)
                   for option in parsed.get("suggested_weights") or []]
    elif reason == "several_assets" and weight is not None and 0 < weight <= 1:
        choices = [idea_panel.make_idea(ticker, weight, funding_source, funding)
                   for ticker in tickers if ticker != funding]
    if choices:
        with st.container(horizontal=True):
            for position, idea in enumerate(choices):
                # Le libellé montre la source des fonds : le choix n'en perd aucune.
                label = idea_panel.describe_idea(idea)
                st.button(label, key=f"clarify_{index}_{position}", on_click=on_choice,
                          args=(idea, texts.CHAT_CHOICE.format(choice=label)))
    else:
        st.caption(texts.CHAT_CLARIFY_MANUAL)


def _example_buttons(index: int, on_ask: Optional[Callable[[str], None]]) -> None:
    if on_ask is None:
        return
    with st.container(horizontal=True):
        for position, example in enumerate(texts.CHAT_HELP_EXAMPLES):
            st.button(example, key=f"help_{index}_{position}", on_click=on_ask, args=(example,))


def _render_portfolio(entry: Mapping[str, Any]) -> None:
    label = str(entry.get("portfolio_label") or texts.CHAT_PORTFOLIO_DEFAULT)
    st.markdown(texts.CHAT_PORTFOLIO_TITLE.format(label=escape_dollars(label[:1].lower() + label[1:])))
    positions = sorted(entry.get("positions") or [], key=lambda p: (-float(p["weight"]), p["ticker"]))
    st.markdown("\n".join(texts.CHAT_PORTFOLIO_LINE.format(
        ticker=escape_dollars(p["ticker"]), name=escape_dollars(str(p["name"])), weight=format_pct(p["weight"]))
        for p in positions) or texts.PROOF_NONE)
    st.caption(texts.CHAT_PORTFOLIO_HINT)


def _render_definition(term_id: Optional[str]) -> None:
    glossary = data_source.get_glossary()
    if not glossary:
        st.info(texts.CHAT_GLOSSARY_MISSING)
        return
    term = glossary.get(term_id) if term_id else None
    if term is None:
        st.markdown(texts.CHAT_DEFINITION_UNKNOWN.format(
            terms=escape_dollars(", ".join(t["term"] for t in glossary.values()))))
        return
    level = st.session_state.get("level") if st.session_state.get("level") in ("novice", "pro") else "novice"
    texts_for_level = term[level]
    st.markdown(texts.CHAT_DEFINITION.format(term=escape_dollars(term["term"]),
                                             definition=escape_dollars(texts_for_level["definition"])))
    if texts_for_level.get("analogy"):
        st.markdown(texts.CHAT_ANALOGY.format(analogy=escape_dollars(texts_for_level["analogy"])))
    st.caption(texts.CHAT_DEFINITION_SOURCE.format(level=texts.LEVEL_LABELS[level].lower()))


def _render_answer(entry: Mapping[str, Any], index: int, on_ask: Optional[Callable[[str], None]]) -> None:
    """Réponse produite par le code (accueil, portefeuille, définition, hors périmètre) : aucun modèle."""
    kind = entry["parsed"].get("answer_kind")
    if kind == "portfolio":
        _render_portfolio(entry)
    elif kind == "definition":
        _render_definition(entry["parsed"].get("term_id"))
    elif kind == "greeting":
        st.markdown(texts.CHAT_GREETING)
        _example_buttons(index, on_ask)
    else:
        st.markdown(texts.CHAT_OUT_OF_SCOPE)
        _example_buttons(index, on_ask)


def _render_notice(entry: Mapping[str, Any]) -> None:
    """Signalement du garde-fou (texte du code), avant la réponse reformulée de l'agent."""
    notice = entry.get("notice") or []
    if notice:
        st.warning(texts.CHAT_GUARDRAIL_NOTICE.format(topics=_topics(notice)))


def _render_conversation_answer(entry: Mapping[str, Any]) -> None:
    """Réponse de l'agent : la version du niveau courant, sinon la dernière rédigée (avec son niveau)."""
    _render_notice(entry)
    level = st.session_state.get("level") if st.session_state.get("level") in ("novice", "pro") else "novice"
    versions = entry.get("versions") or {}
    if not versions:
        return
    shown_level = level if level in versions else next(reversed(versions))
    _render_conversation_version(versions[shown_level])
    if shown_level != level:
        st.caption(texts.CHAT_OTHER_LEVEL.format(level=texts.LEVEL_LABELS[shown_level].lower()))


def _render_conversation_version(entry: Mapping[str, Any]) -> None:
    origin = entry.get("origin", "template")
    is_llm = origin == "llm"
    badge = texts.CHAT_ORIGIN_BEDROCK if is_llm else texts.CHAT_ORIGIN_FALLBACK
    badge_class = "" if is_llm else " af-chat-badge--fallback"
    proofs = [e for e in entry.get("evidence") or []
              if e.get("evidence_id") in set(entry.get("cited_evidence") or [])]
    with st.container():
        html(f'<div class="af-chat-answer{" af-chat-answer--fallback" if not is_llm else ""}>'
             f'<div class="af-chat-meta"><span class="af-chat-badge{badge_class}">{escape(badge)}</span>'
             f'<span>{escape(texts.CHAT_PROOFS)} : {len(proofs)}</span></div>'
             f'<div>{entry["answer"]}</div></div>')
        if proofs:
            with st.expander(texts.CHAT_PROOFS):
                for evidence in proofs:
                    evidence_id = evidence.get("evidence_id")
                    with st.container(border=True):
                        st.markdown(f"**{evidence_id} - {evidence.get('label_fr', '')}**")
                        st.caption(evidence.get("display_value", ""))
                        if evidence.get("as_of"):
                            st.caption(f"Date de référence : {evidence['as_of']}")
        with st.expander(texts.CHAT_TRACE):
            trace_panel.render_trace({"trace": entry.get("trace") or []}, None)


def _render_agent_answer(entry: Mapping[str, Any]) -> None:
    """Réponse de l'agent conversationnel (issue 78) : texte, origine, signaux du garde-fou, données et limites.

    Entrée du fil `{"type": "agent_answer", ...}` écrite par `session._agent_answer` : `answer_kind`,
    `rendered` (texte, renvois remplacés), `origin` ("llm" ou "template"), `fallback_reason`, `guard`
    (détails du garde-fou : `grounding_weak`, `grounding_very_weak`, `grounding_score`, `relevance_weak`),
    `evidence` (preuves citées), `limits` (textes), `counterfactuals` (`label`, `weight`, `none`).
    La question n'y est jamais recopiée.
    """
    st.markdown(escape_dollars(entry.get("rendered", "")))
    origin = entry.get("origin", "template")
    guard = entry.get("guard") or {}
    if origin == "llm" and guard.get("grounding_weak"):
        score = guard.get("grounding_score")
        shown = "-" if score is None else f"{score:.2f}"
        template = (texts.EXPLANATION_GROUNDING_VERY_WEAK if guard.get("grounding_very_weak")
                    else texts.EXPLANATION_GROUNDING_WEAK)
        st.warning(template.format(score=shown))
    if origin == "llm" and guard.get("relevance_weak"):
        st.caption(texts.CHAT_AGENT_RELEVANCE_WEAK)
    for item in entry.get("counterfactuals") or []:
        line = (texts.CHAT_AGENT_COUNTERFACTUAL_NONE.format(label=item["label"]) if item.get("none")
                else texts.CHAT_AGENT_COUNTERFACTUAL.format(label=item["label"], weight=item.get("weight") or "-"))
        st.markdown(escape_dollars(line))
    caption = texts.CHAT_AGENT_ORIGIN.get(origin, "")
    if origin == "template" and entry.get("fallback_reason"):
        reason = texts.REASON_CODES_FR.get(entry["fallback_reason"], entry["fallback_reason"])
        caption = f"{caption} {texts.CHAT_AGENT_FALLBACK.format(reason=reason)}"
    if guard.get("denied_topics"):
        caption = f"{caption} {texts.CHAT_AGENT_DENIED.format(topics=_topics(list(guard['denied_topics'])))}"
    st.caption(caption)
    with st.expander(texts.CHAT_AGENT_DATA):
        evidence = entry.get("evidence") or []
        if not evidence:
            st.caption(texts.CHAT_AGENT_DATA_NONE)
        for item in evidence:
            period = (f" ({item['period_start']} au {item['period_end']}"
                      f"{', ' + item['currency'] if item.get('currency') else ''})"
                      if item.get("period_start") and item.get("period_end") else "")
            st.markdown(escape_dollars(f"- **{item.get('evidence_id')}** {item.get('label_fr', '')} : "
                                       f"{item.get('display_value') or '-'}{period}"))
    with st.expander(texts.CHAT_AGENT_LIMITS):
        for text in entry.get("limits") or []:
            st.markdown(escape_dollars(f"- {text}"))


def _render_confirm(entry: Mapping[str, Any], index: int, on_choice: Callable[..., None]) -> None:
    """Idée proposée (poids lu sans "%", relance) : rien n'est simulé avant le clic."""
    _render_notice(entry)
    parsed = entry["parsed"]
    idea = parsed["idea"]
    label = idea_panel.describe_idea(idea)
    st.markdown(texts.CHAT_CONFIRM.format(idea=label))
    why = texts.CHAT_CONFIRM_WHY.get(parsed.get("reason") or "")
    if why:
        st.caption(why)
    st.button(texts.CHAT_CONFIRM_YES, key=f"confirm_{index}", type="primary", on_click=on_choice,
              args=(idea, texts.CHAT_CHOICE.format(choice=label)))
    st.caption(texts.CHAT_CLARIFY_MANUAL)


def render_compact(entry: Mapping[str, Any], result: Optional[Mapping[str, Any]]) -> None:
    """Réponse ancienne : son propre verdict (lu à sa clé), son profil et son idée."""
    describe = texts.CHAT_COMPACT.format(idea=idea_panel.describe_idea(entry["idea"]),
                                         name=entry.get("profile_name") or texts.HEADER_NONE)
    if result is None:
        st.caption(texts.CHAT_PREVIOUS.format(idea=describe))
        return
    status = result["governance_after"]["overall_status"]
    html(f'{pill(status)} <span>{escape(describe)}</span>'
         f'{result_panel.split_verdict_html(result["governance_after"])}')


def render_reply(entry: Mapping[str, Any], index: int, result: Mapping[str, Any],
                 explanation: Optional[Mapping[str, Any]], ctx: ProofContext,
                 rules_by_id: Mapping[str, Dict[str, Any]], names: Mapping[str, str],
                 load_asset_facts: Callable[[], Optional[Mapping[str, Any]]],
                 threshold_notice: str) -> None:
    """Réponse détaillée : courte d'abord, le reste derrière un interrupteur et des onglets."""
    result_panel.render_mode_note(result)
    result_panel.render_verdict(result)
    st.caption(texts.CHAT_KEY_POINTS)
    render_key_points(result["governance_after"]["checks"], result["evidence"], "portfolio_after",
                      rules_by_id, ctx, key_prefix=f"kp{index}")
    if explanation is not None:
        if explanation["output"].get("origin") == "llm":
            # Texte de l'agent : son résumé apporte une formulation propre au niveau choisi.
            explanation_panel.render_origin(explanation)
            summary = summary_section(explanation.get("rendered_markdown", ""))
            if summary:
                st.markdown(escape_dollars(summary))
        else:
            # Texte standard : il redirait le verdict. Il reste dans l'onglet "Explication complète" ;
            # seul un repli en mode Bedrock est signalé ici.
            explanation_panel.render_fallback_note(explanation)
    # L'avertissement reste visible en permanence dans le bandeau du haut (règle 8).
    if not kept_toggle(texts.CHAT_SHOW_DETAILS, f"details_{index}"):
        return
    # Trace (outils, contrôles, interventions du garde-fou, règle 8) : onglet présent seulement
    # quand l'interrupteur de démo du menu de paramètres est activé.
    show_trace = bool(st.session_state.get(SHOW_TRACE_KEY))
    # Sources et limites : déjà dans l'explication complète (sections Limites et Preuves citées).
    labels = [texts.CHAT_TAB_DETAILS, texts.CHAT_TAB_TEXT]
    tabs = st.tabs(labels + [texts.CHAT_TAB_TRACE] if show_trace else labels)
    details_tab, text_tab = tabs[:2]
    with details_tab:
        result_panel.render_details(result, rules_by_id, ctx, names, load_asset_facts, threshold_notice)
    with text_tab:
        if explanation is not None:
            explanation_panel.render_explanation(explanation, result, ctx)
    if show_trace:
        with tabs[2]:
            trace_panel.render_trace(result, explanation)


def render_entry(entry: Mapping[str, Any], index: int, is_latest_analysis: bool,
                 render_analysis: Callable[[Mapping[str, Any], int], None],
                 cached_result: Callable[[Mapping[str, Any]], Optional[Mapping[str, Any]]],
                 on_choice: Callable[..., None], on_ask: Optional[Callable[[str], None]] = None) -> None:
    role = entry.get("role")
    if role == "user":
        avatar = ":material/tune:" if entry.get("origin") == "manual" else "user"
        # Conteneur à clé : la feuille de style place les messages de l'utilisateur à droite.
        with st.container(key=f"chat-user-{index}"), st.chat_message("user", avatar=avatar):
            st.markdown(entry["text"])
        return
    with st.chat_message("assistant", avatar=":material/neurology:"):
        kind = entry.get("type")
        if kind == "note":
            st.caption(entry["text"])
        elif kind == "info":
            st.info(entry["text"])
        elif kind == "refused":
            _render_refused(entry, index, on_choice)
        elif kind == "clarify":
            _render_clarify(entry, index, on_choice)
        elif kind == "confirm":
            _render_confirm(entry, index, on_choice)
        elif kind == "answer":
            _render_answer(entry, index, on_ask)
        elif kind == "conversation_answer":
            _render_conversation_answer(entry)
        elif kind == "agent_answer":
            _render_agent_answer(entry)
        elif kind == "analysis":
            if entry.get("guard_action") is not None:
                # Demande écrite : on montre l'idée comprise. Une idée venue d'un bouton ou des
                # réglages est déjà écrite dans la bulle de l'utilisateur et dans l'en-tête.
                st.caption(texts.CHAT_UNDERSTOOD.format(idea=idea_panel.describe_idea(entry["idea"])))
                guard = _guard_caption(entry.get("guard_action"))
                if guard:
                    st.caption(guard)
            if is_latest_analysis:
                render_analysis(entry, index)
            else:
                render_compact(entry, cached_result(entry))
