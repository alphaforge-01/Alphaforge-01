"""Pipeline d'analyse du flux C : ``run_analysis``, ``explain``, ``check_request``.

Deux modes :
- ``offline`` : sequence d'outils scriptee (etiquetee "code" dans la trace),
  explication par gabarit. Aucun appel reseau. Sert de filet pour la demo.
- ``bedrock`` : l'analyste et l'explicateur sont des agents Bedrock. Toute
  erreur Bedrock bascule sur le mode ``offline`` sans planter, et la trace le
  signale (etape en statut ``fallback`` avec la raison).

Regles tenues par ce module :
- aucun chiffre, verdict ou texte destine a l'utilisateur ne vient d'un modele ;
- la trace est construite par le code a partir des appels reels ;
- aucun raisonnement interne de modele n'est lu ni stocke.
"""
from __future__ import annotations

import copy
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .bedrock_client import (
    GROUNDING_ANSWER_MAX_CHARS, BedrockClient, BedrockConfig, BedrockError, redact_text,
)
from .contracts import (
    AnalysisResult, AnalystSubmission, ConversationBrief, ConversationReply, ConversationResult, ExplanationResult,
    GovernanceResult, GuardrailResult, InvestmentIdea, InvestorProfile, Level, Portfolio, PortfolioSnapshot,
    TraceStep, ValidationResult, Variant,
)
from .conversation_agent import MAX_QUESTION_CHARS, render_answer, reply_with_llm
from .conversation_agent import grounding_source as conversation_grounding_source
from .explainer_agent import PROMPT_VERSION as EXPLAINER_PROMPT_VERSION
from .explanation_cache import ExplanationCache
from .pipeline_deps import PipelineDeps, resolve_deps
from .trace_store import TraceStore, TraceStoreError, build_trace_document
from .tool_specs import (
    MAX_HIGHLIGHTS, MAX_VARIANTS, REASON_CODES, AgentFailure, AnalystOutcome, ToolBox,
    ToolBudgetExceeded, normalize_idea,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALID_MODES = ("offline", "bedrock")
# Sous ce score d'ancrage, le texte du modele reste affiche mais avec la mention "ancrage tres faible" : decision
# de l'equipe (15 novembre), pour que l'utilisateur voie le texte de l'agent et son signal. Un ancrage aussi bas a
# signale, a l'essai reel, une erreur de sens que le validateur ne peut pas voir (mesure rattachee a la mauvaise
# chose) : le signal doit donc rester visible dans l'explication, pas seulement dans la trace. Le texte du modele
# est toujours remplace par le gabarit si le garde-fou intervient (sujet refuse) ou ne rend aucun score.
GROUNDING_FLOOR = 0.3
# Requete fixe du controle d'ancrage (copie verifiee par un test dans scripts/diagnose_grounding.py).
GROUNDING_QUERY = "Explique le resultat de l'analyse."
_SEVERITY = {"conflict": 0, "tension": 1, "missing_info": 2, "compliant": 3}


class AnalysisError(Exception):
    """Erreur d'entree ou de donnees : message en francais, destine a l'interface."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _idea_params(idea: InvestmentIdea) -> dict[str, Any]:
    return {
        "ticker": idea["ticker"], "target_weight": idea["target_weight"],
        "funding_source": idea["funding_source"], "funding_ticker": idea.get("funding_ticker"),
    }


def _step(step: int, name: str, actor: str, status: str, started: float,
          details: dict[str, Any], model_id: str | None = None) -> TraceStep:
    return TraceStep(
        step=step, name=name, actor=actor, status=status,  # type: ignore[typeddict-item]
        model_id=redact_text(model_id) if model_id else None,
        duration_ms=int((time.perf_counter() - started) * 1000), details=details,
    )


def _snapshots_from_simulation(result: dict[str, Any]) -> tuple[PortfolioSnapshot, PortfolioSnapshot]:
    """Extrait (avant, apres) d'un resultat de ``simulate_portfolio_change``.

    Hypothese a confirmer avec le flux A : ``data`` contient les cles ``before`` et ``after``.
    """
    data = result.get("data") or {}
    if result.get("status") != "ok" or "before" not in data or "after" not in data:
        raise AnalysisError(
            f"La simulation n'a pas abouti ({result.get('error_message') or result.get('status')}).")
    return data["before"], data["after"]


def _worst_status(governance: GovernanceResult) -> str:
    return governance["overall_status"]


def _relabel_evidence(tool_result: dict[str, Any], old_subject: str, new_subject: str) -> None:
    """Change le sujet des preuves d'un resultat d'outil, pour qu'un meme couple (metrique, sujet) designe une seule preuve.

    Les simulations d'une variante ou explorees par l'analyste produisent des preuves de sujet
    ``portfolio_after`` : sans reetiquetage, elles se confondraient avec celles de l'idee demandee.
    """
    for entry in tool_result.get("evidence", []) or []:
        if entry.get("subject") != old_subject:
            continue
        entry["subject"] = new_subject
        key = entry.get("evidence_key")
        if isinstance(key, str) and key.endswith(f":{old_subject}"):
            entry["evidence_key"] = key[: -len(old_subject)] + new_subject


def propose_variants(
    governance_after: GovernanceResult, idea: InvestmentIdea, portfolio: Portfolio,
) -> list[dict[str, Any]]:
    """Variantes de la sequence scriptee : au plus deux, motif en code ferme.

    Presentees comme des simulations, jamais comme des recommandations.
    """
    if _worst_status(governance_after) == "compliant":
        return []
    variants: list[dict[str, Any]] = []
    # 1. reduire le poids jusqu'au plus grand poids conforme, sinon moitie du poids demande
    cap = None
    for check in governance_after["checks"]:
        counterfactual = check.get("counterfactual")
        if check["status"] != "compliant" and counterfactual and counterfactual["compliant_at_or_below"]:
            value = counterfactual["compliant_at_or_below"]
            cap = value if cap is None else min(cap, value)
    reduced = cap if cap is not None else round(idea["target_weight"] / 2, 2)
    reduced = round(min(reduced, idea["target_weight"]), 4)
    if 0 < reduced < idea["target_weight"]:
        variants.append({"reason_code": "reduce_weight", "idea": {**idea, "target_weight": reduced}})
    # 2. changer la source des fonds (ou repartir sur les positions existantes)
    if idea["funding_source"] == "pro_rata":
        # Une position ne peut financer l'ajout que si elle pese au moins le poids demande : sinon
        # l'outil refuse la simulation. On ne propose donc que des variantes finançables.
        fundable = [p for p in portfolio["positions"]
                    if p["ticker"] != idea["ticker"] and p["weight"] >= idea["target_weight"]]
        if fundable:
            largest = max(fundable, key=lambda p: p["weight"])["ticker"]
            variants.append({
                "reason_code": "change_funding_source",
                "idea": {**idea, "funding_source": "from_ticker", "funding_ticker": largest},
            })
    else:
        variants.append({
            "reason_code": "spread_across_existing",
            "idea": {**idea, "funding_source": "pro_rata", "funding_ticker": None},
        })
    return variants[:MAX_VARIANTS]


def scripted_sequence(toolbox: ToolBox, idea: InvestmentIdea) -> AnalystOutcome:
    """Sequence d'outils fixe, sans modele : radiographie puis simulation de l'idee."""
    toolbox.call("analyze_portfolio")
    toolbox.call("simulate_portfolio_change", _idea_params(idea))
    highlights = [entry["evidence_id"] for entry in list(toolbox.evidence().values())[:MAX_HIGHLIGHTS]]
    submission = AnalystSubmission(
        understood_idea=idea, variants=[], highlight_evidence_ids=highlights, unsupported_requests=[])
    return AnalystOutcome(submission=submission, actor="code", turns=0, stop_reason="scripted")


ASSET_FACT_METRICS = ("volatility_ann", "max_drawdown")


def _ensure_asset_facts(toolbox: ToolBox, ticker: str) -> tuple[list[str], str]:
    """Preuves de l'actif de l'idee pris seul (volatilite, perte maximale), pour le dossier d'explication.

    Sans elles, l'explication ne cite que des mesures du portefeuille et ne peut pas dire d'ou vient l'ecart
    avec le profil. Reprend l'appel de l'analyste s'il existe, sinon le code appelle ``get_asset_facts``.
    Budget epuise ou outil en echec : aucune preuve ajoutee, l'analyse continue.
    Rend (identifiants de preuves, origine : "agent", "code" ou "absent").
    """
    found, caller = None, "absent"
    for call, result in zip(toolbox.calls, toolbox.results):
        if call["tool_name"] == "get_asset_facts" and result["status"] == "ok" and call["params"].get("ticker") == ticker:
            found, caller = result, "agent"
            break
    if found is None and toolbox.calls_used < toolbox.max_calls:
        result = toolbox.call("get_asset_facts", {"ticker": ticker})
        if result["status"] == "ok":
            found, caller = result, "code"
    if found is None:
        return [], "absent"
    ids = [e["evidence_id"] for e in found.get("evidence", []) or [] if e.get("metric") in ASSET_FACT_METRICS]
    return ids, caller


def _with_callers(calls: list[dict[str, Any]], agent_calls: int) -> list[dict[str, Any]]:
    """Copie des appels avec ``caller`` : "agent" pour les ``agent_calls`` premiers, "code" ensuite."""
    return [{**call, "caller": "agent" if index < agent_calls else "code"} for index, call in enumerate(calls)]


def _with_asset_facts(highlights: list[str], asset_fact_ids: list[str]) -> list[str]:
    return highlights + [e for e in asset_fact_ids if e not in highlights]


def _load_limits(deps: PipelineDeps, limit_ids: list[str]) -> list[dict]:
    """Catalogue des limites du resultat, au format ``{limit_id, text_novice, text_pro}``.

    Sans ``limits_for`` fourni par les dependances, on reprend le catalogue complet du flux B
    (``reference_texts.load_limits``) : le dossier d'explication affiche toutes les limites
    obligatoires, pas seulement celles citees par une preuve.
    """
    if deps.limits_for is not None:
        return deps.limits_for(limit_ids)
    try:
        from .reference_texts import load_limits
    except ImportError:
        return []
    return list(load_limits())


def _load_analyst_runner() -> Callable[..., AnalystOutcome] | None:
    try:
        from . import analyst_agent
    except ImportError:
        return None
    return getattr(analyst_agent, "run_analyst", None)


def _load_explainer_runner() -> Callable[..., Any] | None:
    try:
        from . import explainer_agent
    except ImportError:
        return None
    return getattr(explainer_agent, "explain_with_llm", None)


def _resolve_mode(mode: str, config: BedrockConfig, client: BedrockClient | None) -> tuple[str, str | None]:
    """Rend (mode_effectif, raison_du_repli). Le repli n'est jamais silencieux."""
    if mode not in VALID_MODES:
        raise AnalysisError(f"Mode inconnu : {mode}. Valeurs permises : offline, bedrock.")
    if mode == "offline":
        return "offline", None
    if client is None and not config.can_call_models:
        return "offline", "configuration_incomplete"
    return "bedrock", None


def run_analysis(
    profile: InvestorProfile,
    portfolio: Portfolio,
    idea: InvestmentIdea,
    as_of: str | None = None,
    mode: str = "offline",
    *,
    deps: PipelineDeps | None = None,
    client: BedrockClient | None = None,
    config: BedrockConfig | None = None,
    analyst_runner: Callable[..., AnalystOutcome] | None = None,
    trace_store: TraceStore | None = None,
) -> AnalysisResult:
    """Analyse une idee de placement fictive pour un profil fictif.

    Leve ``AnalysisError`` si l'idee ou la simulation est inutilisable.
    Toute erreur Bedrock bascule sur la sequence scriptee (etape 1 en ``fallback``).
    """
    deps = deps or resolve_deps()
    config = config or BedrockConfig.from_env()
    normalized, problem = normalize_idea(idea)
    if normalized is None:
        raise AnalysisError(problem or "Idee invalide.")
    idea = normalized
    effective_mode, config_fallback = _resolve_mode(mode, config, client)
    capital = profile.get("capital_cad")
    toolbox = ToolBox(deps, portfolio, as_of=as_of, capital_cad=capital)
    trace: list[TraceStep] = []

    # Etape 1 : analyse (agent Bedrock ou sequence scriptee)
    started = time.perf_counter()
    outcome: AnalystOutcome | None = None
    fallback_reason = config_fallback
    if effective_mode == "bedrock":
        runner = analyst_runner or _load_analyst_runner()
        if runner is None:
            fallback_reason = "analyste_indisponible"
        else:
            try:
                bedrock_client = client or BedrockClient(config)
                outcome = runner(bedrock_client, config.analyst_model_id, toolbox, idea, profile)
            except Exception as error:  # US-15 : aucune erreur d'agent ne doit faire planter la page
                known = isinstance(error, (BedrockError, AgentFailure, ToolBudgetExceeded))
                fallback_reason = (
                    f"{type(error).__name__}: {redact_text(str(error))}" if known else type(error).__name__)
                outcome = None
                toolbox = ToolBox(deps, portfolio, as_of=as_of, capital_cad=capital)
    if outcome is None:
        outcome = scripted_sequence(toolbox, idea)
    # Appels faits pendant la boucle de l'agent : les suivants (simulation de controle, variantes, faits
    # de l'actif) sont decides par le code. La trace le dit, au lieu de tout attribuer a l'agent.
    agent_calls = toolbox.calls_used if outcome.actor == "agent" else 0
    def _simulation_of_idea() -> dict[str, Any] | None:
        # Seule la simulation de l'idee EXACTE demandee sert de snapshot "apres" : jamais une variante.
        for call, simulated in zip(toolbox.calls, toolbox.results):
            if call["tool_name"] != "simulate_portfolio_change" or simulated["status"] != "ok":
                continue
            candidate, _ = normalize_idea(call["params"])
            if candidate == idea:
                return simulated
        return None

    try:
        simulation = _simulation_of_idea()
        if simulation is None:
            toolbox.call("simulate_portfolio_change", _idea_params(idea))
            simulation = _simulation_of_idea()
        if not any(r["tool_name"] == "analyze_portfolio" and r["status"] == "ok" for r in toolbox.results):
            toolbox.call("analyze_portfolio")
    except ToolBudgetExceeded as error:
        raise AnalysisError("Budget d'appels d'outils epuise avant la simulation de l'idee.") from error
    if simulation is None:
        raise AnalysisError("La simulation de l'idee n'a pas abouti : aucun resultat exploitable.")
    snapshot_before, snapshot_after = _snapshots_from_simulation(simulation)
    snapshot_before = {**snapshot_before, "subject": "portfolio_before"}
    snapshot_after = {**snapshot_after, "subject": "portfolio_after"}
    for call, explored in zip(toolbox.calls, toolbox.results):
        if call["tool_name"] == "simulate_portfolio_change" and explored["status"] == "ok" and explored is not simulation:
            label = f"explored:{explored['call_id']}"
            _relabel_evidence(explored, "portfolio_after", label)
            _relabel_evidence(explored, "portfolio_before", label)
    step1_status = "fallback" if (mode == "bedrock" and fallback_reason) else "ok"
    details: dict[str, Any] = {
        "tool_calls": list(toolbox.calls), "turns": outcome.turns, "stop_reason": outcome.stop_reason,
        "mode_requested": mode, "mode_effective": "bedrock" if outcome.actor == "agent" else "offline",
    }
    if fallback_reason and mode == "bedrock":
        details["fallback_reason"] = fallback_reason
    trace.append(_step(1, "analysis", outcome.actor, step1_status, started, details, outcome.model_id))

    # Etape 2 : gouvernance (code deterministe)
    started = time.perf_counter()

    def simulate_fn(candidate: InvestmentIdea) -> PortfolioSnapshot:
        return _snapshots_from_simulation(
            deps.simulate_portfolio_change(portfolio, candidate, as_of=as_of, capital_cad=capital))[1]

    governance_before = deps.evaluate(profile, snapshot_before, evidence=toolbox.evidence())
    governance_after = deps.evaluate(
        profile, snapshot_after, simulate_fn=simulate_fn, idea=idea, evidence=toolbox.evidence())

    # Variantes : repassent par les memes outils et la meme gouvernance
    raw_variants = list(outcome.submission.get("variants", []))
    if outcome.actor == "code" and not raw_variants and deps.supports_variants:
        raw_variants = propose_variants(governance_after, idea, portfolio)
    variants: list[Variant] = []
    for raw in raw_variants[:MAX_VARIANTS]:
        variant_idea, _ = normalize_idea(raw.get("idea"))
        if variant_idea is None or raw.get("reason_code") not in REASON_CODES or variant_idea == idea:
            continue
        if toolbox.calls_used >= toolbox.max_calls:
            break
        variant_id = f"V{len(variants) + 1}"
        simulated = toolbox.call("simulate_portfolio_change", _idea_params(variant_idea))
        if simulated["status"] != "ok":
            continue
        _relabel_evidence(simulated, "portfolio_after", f"variant:{variant_id}")
        _relabel_evidence(simulated, "portfolio_before", f"explored:{simulated['call_id']}")
        snapshot = {**_snapshots_from_simulation(simulated)[1], "subject": f"variant:{variant_id}"}
        variants.append(Variant(
            variant_id=variant_id, reason_code=raw["reason_code"], idea=variant_idea, snapshot=snapshot,
            governance=deps.evaluate(
                profile, snapshot, simulate_fn=simulate_fn, idea=variant_idea, evidence=toolbox.evidence()),
        ))
    # Faits de l'actif apres les variantes : ils ne doivent pas consommer le budget d'appels des variantes.
    asset_fact_ids, asset_facts_caller = _ensure_asset_facts(toolbox, idea["ticker"])
    trace[0]["details"]["asset_facts"] = {
        "ticker": idea["ticker"], "caller": asset_facts_caller, "evidence_ids": asset_fact_ids}
    # inclut les simulations de variantes et les faits de l'actif, avec qui a decide chaque appel
    trace[0]["details"]["tool_calls"] = _with_callers(toolbox.calls, agent_calls)
    trace.append(_step(2, "governance", "code", "ok", started, {
        "overall_before": governance_before["overall_status"], "overall_after": governance_after["overall_status"],
        "checks": [{"check_id": c["check_id"], "status": c["status"], "margin": c["margin"]}
                   for c in governance_after["checks"]],
        "variants": [{"variant_id": v["variant_id"], "overall_status": v["governance"]["overall_status"]}
                     for v in variants],
    }))

    evidence = toolbox.evidence()
    _scope_evidence_labels(evidence)
    limit_ids = sorted({lid for entry in evidence.values() for lid in entry.get("limit_ids", [])})
    submission = AnalystSubmission(
        understood_idea=idea,
        variants=[{"reason_code": v["reason_code"], "idea": v["idea"]} for v in variants],
        # au plus MAX_HIGHLIGHTS choisies par l'analyste, puis les faits de l'actif ajoutes par le code
        highlight_evidence_ids=_with_asset_facts(
            [e for e in outcome.submission.get("highlight_evidence_ids", []) if e in evidence][:MAX_HIGHLIGHTS],
            [e for e in asset_fact_ids if e in evidence]),
        unsupported_requests=list(outcome.submission.get("unsupported_requests", [])),
    )
    as_of_value = as_of or next((e["as_of"] for e in evidence.values() if e.get("as_of")), None) or "inconnue"
    result = AnalysisResult(
        run_id=uuid.uuid4().hex[:16], created_at=_now_iso(), as_of=as_of_value,
        mode="bedrock" if outcome.actor == "agent" else "offline",
        is_fixture=deps.is_fixture, profile=profile, portfolio_before=portfolio, idea=idea,
        snapshot_before=snapshot_before, snapshot_after=snapshot_after,
        governance_before=governance_before, governance_after=governance_after,
        variants=variants, evidence=evidence, limits=_load_limits(deps, limit_ids),
        submission=submission, trace=trace,
    )

    # Etape 3 : dossier d'explication (code). Construit au niveau par defaut pour verifier qu'il est constructible.
    started = time.perf_counter()
    try:
        brief = deps.build_brief(result, profile["default_level"])
        trace.append(_step(3, "brief", "code", "ok", started, {
            "brief_id": brief["brief_id"], "level": brief["level"],
            "ranked_factors": [f["check_id"] for f in brief["ranked_factors"]],
            "limit_ids": [l["limit_id"] for l in brief["limits"]],
        }))
    except Exception as error:  # le dossier ne doit pas faire perdre l'analyse deja calculee
        trace.append(_step(3, "brief", "code", "error", started, {"error": type(error).__name__}))
    if mode == "bedrock":
        outcome_store = persist_trace(result, config=config, store=trace_store)
        trace[-1]["details"]["trace_saved"] = outcome_store
    return result


def explain(
    result: AnalysisResult,
    level: Level,
    mode: str = "offline",
    *,
    deps: PipelineDeps | None = None,
    client: BedrockClient | None = None,
    config: BedrockConfig | None = None,
    explainer_runner: Callable[..., Any] | None = None,
    cache: ExplanationCache | None = None,
    trace_store: TraceStore | None = None,
) -> ExplanationResult:
    """Explication au niveau demande : dossier, texte, validation, controle du garde-fou.

    Le texte vient du gabarit si l'explicateur Bedrock est indisponible, rejete
    par le validateur ou en erreur. Le repli est signale dans la trace.
    """
    deps = deps or resolve_deps()
    config = config or BedrockConfig.from_env()
    effective_mode, config_fallback = _resolve_mode(mode, config, client)
    if effective_mode == "bedrock" and not config.has_guardrail:
        # Regle 8 : aucun texte de modele n'est affiche sans garde-fou. Repli sur le gabarit, signale dans la trace.
        effective_mode, config_fallback = "offline", "garde_fou_non_configure"
    try:
        brief = deps.build_brief(result, level)
    except ValueError as error:
        raise AnalysisError(f"Dossier d'explication impossible : {redact_text(str(error))}") from error

    # Etape 4 : explication
    started = time.perf_counter()
    output: dict[str, Any] | None = None
    fallback_reason = config_fallback
    model_id: str | None = None
    from_cache = False
    cache_key: str | None = None
    if effective_mode == "bedrock":
        runner = explainer_runner or _load_explainer_runner()
        if runner is None:
            fallback_reason = "explicateur_indisponible"
        else:
            if cache is not None and config.explainer_model_id:
                cache_key = ExplanationCache.make_key(
                    brief["brief_id"], level, config.explainer_model_id, EXPLAINER_PROMPT_VERSION)
                output = cache.get(cache_key)
                if output is not None:
                    from_cache = True
                    model_id = config.explainer_model_id
            if output is None:
                try:
                    bedrock_client = client or BedrockClient(config)
                    output = runner(bedrock_client, config.explainer_model_id, brief, deps.validate)
                    model_id = config.explainer_model_id
                except Exception as error:  # US-15 : repli sur le gabarit, jamais de plantage
                    known = isinstance(error, (BedrockError, AgentFailure))
                    fallback_reason = (
                        f"{type(error).__name__}: {redact_text(str(error))}" if known else type(error).__name__)
    if output is None:
        output = deps.render_template(brief)
    elif output["origin"] == "llm" and not from_cache:
        # L'emplacement du contrefactuel est ecrit par le code, jamais par le modele : sa phrase decrit un affichage
        # du code (poids detailles dessous), absent du dossier, et le controle d'ancrage la juge non fondee (mesure
        # sur Amira : texte entier a 0,11, puis 0,58 sans cet emplacement). Celle du gabarit est fondee par construction.
        output = {**output, "counterfactual": deps.render_template(brief)["counterfactual"]}
    details: dict[str, Any] = {
        "level": level, "origin": output["origin"], "attempt": output["attempt"], "brief_id": brief["brief_id"],
        "from_cache": from_cache,
    }
    if output["origin"] == "llm":
        details["slots_written_by_code"] = ["counterfactual"]
    wanted_llm = mode == "bedrock"
    if wanted_llm and output["origin"] == "template":
        details["fallback_reason"] = fallback_reason or "rejet_du_validateur"
    trace = [_step(4, "explanation", "agent" if output["origin"] == "llm" else "code",
                   "fallback" if (wanted_llm and output["origin"] == "template") else "ok",
                   started, details, model_id if output["origin"] == "llm" else None)]

    # Etape 5 : validation (code). Un texte invalide est remplace par le gabarit.
    started = time.perf_counter()
    validation = deps.validate(output, brief)
    status = "ok"
    repaired_slots: list[str] = []
    if not validation["is_valid"] and output["origin"] == "llm":
        # Reparation par emplacement : seuls les emplacements rejetes viennent du code, le reste reste au modele.
        candidate, slots = _repair_slots(output, deps.render_template(brief), validation["rejections"])
        if candidate is not None:
            recheck = deps.validate(candidate, brief)
            if recheck["is_valid"]:
                trace[0]["details"]["rejection_slots"] = [f"{r['slot']}:{r['code']}" for r in validation["rejections"]]
                trace[0]["details"]["rejection_excerpts"] = _excerpts(validation["rejections"])
                output, validation, repaired_slots = candidate, recheck, slots
    if repaired_slots:
        trace[0]["details"]["repaired_slots"] = repaired_slots
    if not validation["is_valid"]:
        rejected = [r["code"] for r in validation["rejections"]]
        rejected_slots = [f"{r['slot']}:{r['code']}" for r in validation["rejections"]]
        trace[0]["details"]["rejection_excerpts"] = _excerpts(validation["rejections"])
        output = deps.render_template(brief)
        validation = deps.validate(output, brief)
        status = "fallback"
        trace[0]["status"] = "fallback"
        trace[0]["details"]["fallback_reason"] = "rejet_du_validateur"
        trace[0]["details"]["rejection_codes"] = rejected
        # Emplacement et code de chaque rejet (les courts extraits sont dans rejection_excerpts) : diagnostic.
        trace[0]["details"]["rejection_slots"] = rejected_slots
    trace.append(_step(5, "validation", "code", status, started, {
        "is_valid": validation["is_valid"], "checked_references": len(validation["checked_references"]),
        "rejection_codes": [r["code"] for r in validation["rejections"]],
    }))
    markdown = deps.render_markdown(output, brief)

    # Etape 6 : garde-fou (ancrage du texte rendu contre le dossier)
    started = time.perf_counter()
    guardrail = GuardrailResult(
        check="output_grounding", action="not_run", denied_topics=[],
        grounding_score=None, relevance_score=None, mode="detect")
    guard_status = "skipped"
    guard_details: dict[str, Any] = {
        "reason": (config_fallback if config_fallback == "garde_fou_non_configure"
                   else "mode_offline" if effective_mode == "offline" else "non_execute")}
    if effective_mode == "bedrock" and config.has_guardrail:
        try:
            bedrock_client = client or BedrockClient(config)
            checked_text = _model_text(output, brief)
            source_text, source_kind = _grounding_source(brief)
            guardrail = bedrock_client.check_output_grounding(source_text, GROUNDING_QUERY, checked_text)
            guard_status = "ok" if guardrail["action"] != "not_run" else "skipped"
            guard_details = {
                "action": guardrail["action"], "grounding_score": guardrail["grounding_score"],
                "relevance_score": guardrail["relevance_score"], "mode": guardrail["mode"],
                "checked_chars": len(checked_text),
                # Forme et taille de la source comparee (jamais son texte) : "sentences" ou "json".
                "source_kind": source_kind, "source_chars": len(source_text),
            }
            flags = getattr(bedrock_client, "last_grounding_flags", None)
            if isinstance(flags, dict) and flags.get("below_threshold"):
                guard_details["grounding_below_threshold"] = flags.get("filters", [])
        except Exception as error:  # le controle d'ancrage est accessoire : jamais de plantage
            guard_status = "error"
            guard_details = {"error": type(error).__name__}
    if guard_details.get("grounding_below_threshold"):
        # Plan de sprint : l'ancrage est en mode detection, son score est affiche sans bloquer. Le francais est
        # juge severement par le controle, et la fidelite est deja garantie par le validateur (renvois existants,
        # aucun nombre invente). Un ancrage faible est donc signale dans la trace, sans ecarter le texte.
        guard_details["grounding_weak"] = True
    score = guardrail["grounding_score"]
    # Un controle sans score d'ancrage n'a rien verifie : le texte du modele est alors traite comme non verifiable.
    verified = guardrail["action"] == "none" and score is not None
    very_weak = verified and score < GROUNDING_FLOOR
    if very_weak:
        guard_details["grounding_weak"] = True
        guard_details["grounding_very_weak"] = True
        guard_details["grounding_floor"] = GROUNDING_FLOOR
    if output["origin"] == "llm" and not verified:
        # Le texte du modele n'est affiche que si le garde-fou l'a verifie et ne l'a pas refuse : un sujet interdit
        # (intervention), une erreur ou un controle impossible (taille) donnent le gabarit construit par le code.
        unavailable = guardrail["action"] == "not_run" or (guardrail["action"] == "none" and score is None)
        output = deps.render_template(brief)
        validation = deps.validate(output, brief)
        markdown = deps.render_markdown(output, brief)
        trace[0]["status"] = "fallback"
        trace[0]["details"]["fallback_reason"] = (
            "garde_fou_indisponible" if unavailable else "garde_fou_sortie")
        guard_details["replaced_by_template"] = True
        if guardrail["denied_topics"]:
            guard_details["denied_topics"] = guardrail["denied_topics"]
        if cache is not None and cache_key and from_cache:
            cache.discard(cache_key)
    elif very_weak and cache is not None and cache_key and from_cache:
        cache.discard(cache_key)   # un texte tres peu ancre ne doit pas etre reaffiche tel quel depuis le cache
    elif (cache is not None and cache_key and output["origin"] == "llm" and validation["is_valid"]
          and not from_cache and not very_weak):
        cache.put(cache_key, output)
    trace.append(_step(6, "guardrail", "guardrail", guard_status, started, guard_details))

    # Cle facultative du contrat (PR 25) : le dossier exact transmis a l'explicateur, pour l'interface (US-13).
    explanation = ExplanationResult(
        output=output, validation=validation, guardrail=guardrail, rendered_markdown=markdown, trace=trace,  # type: ignore[typeddict-item]
        brief=brief)
    if mode == "bedrock":
        trace[-1]["details"]["trace_saved"] = persist_trace(
            result, explanation, config=config, store=trace_store)
    return explanation


def persist_trace(
    result: AnalysisResult,
    explanation: ExplanationResult | None = None,
    *,
    config: BedrockConfig | None = None,
    store: TraceStore | None = None,
) -> dict[str, Any]:
    """Ecrit la trace sur S3 prive si un compartiment est configure. Ne leve jamais d'exception.

    Rend ``{"saved": bool, "location": cle ou None, "reason": code ou None}``. Aucun
    identifiant de compte n'est rendu, seulement la cle de l'objet.
    """
    config = config or BedrockConfig.from_env()
    try:
        trace_target = store or (TraceStore(config.trace_bucket, region=config.region) if config.trace_bucket else None)
        if trace_target is None:
            return {"saved": False, "location": None, "reason": "bucket_non_configure"}
        key = trace_target.save(build_trace_document(result, explanation))
        return {"saved": True, "location": key, "reason": None}
    except TraceStoreError as error:
        return {"saved": False, "location": None, "reason": redact_text(str(error))}
    except Exception as error:  # la trace est accessoire : jamais de plantage pour elle
        return {"saved": False, "location": None, "reason": type(error).__name__}


# Codes de rejet qu'on peut reparer en remplacant l'emplacement fautif par la version ecrite par le code.
_REPAIRABLE_CODES = frozenset({
    "number_outside_registry", "too_long", "forbidden_term", "unknown_reference", "missing_rule_citation"})
_TEXT_SLOTS = ("summary", "counterfactual", "variants", "limits_context")
MAX_REPAIRED_SLOTS = 3


def _repair_slots(
    output: dict[str, Any], template: dict[str, Any], rejections: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Remplace les seuls emplacements rejetes par ceux du gabarit, et garde le reste du texte du modele.

    Rend (None, []) si un rejet n'est pas reparable (structure, emplacement manquant, trop d'emplacements) :
    le pipeline utilise alors le gabarit complet. Un seul mauvais chiffre ne doit pas faire jeter toute l'explication.
    """
    slots: list[str] = []
    for rejection in rejections:
        slot = rejection.get("slot", "")
        if rejection.get("code") not in _REPAIRABLE_CODES:
            return None, []
        if slot not in _TEXT_SLOTS and not re.fullmatch(r"factors\[\d+\]", slot):
            return None, []
        if slot not in slots:
            slots.append(slot)
    if not slots or len(slots) > MAX_REPAIRED_SLOTS:
        return None, []
    repaired = copy.deepcopy(output)
    for slot in slots:
        if slot in _TEXT_SLOTS:
            repaired[slot] = template[slot]
            continue
        index = int(slot[len("factors["):-1])
        factors = repaired.get("factors") or []
        if index >= len(factors):
            return None, []
        replacement = next(
            (f for f in template.get("factors", []) if f.get("check_id") == factors[index].get("check_id")), None)
        if replacement is None:
            return None, []
        factors[index] = copy.deepcopy(replacement)
    return repaired, slots


_SCOPE_SUFFIX = (
    ("portfolio_before", " (portefeuille avant l'ajout)"),
    ("portfolio_after", " (portefeuille après l'ajout)"),
    ("variant:", " (variante simulée)"),
    ("explored:", " (simulation explorée)"),
)


def _scope_evidence_labels(evidence: dict[str, Any]) -> None:
    """Ajoute son perimetre au libelle de chaque preuve.

    Plusieurs preuves portent le meme libelle ("Perte maximale historique") et ne se distinguent que par leur
    sujet interne : avant, apres, variante. Le libelle seul ne le disait pas, et le modele pouvait prendre la
    mauvaise ligne ou attribuer la mesure a la mauvaise chose. Le perimetre aide aussi l'utilisateur qui
    ouvre une preuve.
    """
    for entry in evidence.values():
        subject = str(entry.get("subject", ""))
        suffix = next((s for prefix, s in _SCOPE_SUFFIX if subject.startswith(prefix)), None)
        if suffix is None and entry.get("tool_name") == "get_asset_facts" and subject:
            suffix = f" ({subject} seul)"   # faits de l'actif pris seul, pas du portefeuille
        label = str(entry.get("label_fr", ""))
        if suffix and suffix not in label:
            entry["label_fr"] = label + suffix


def _excerpts(rejections: list[dict[str, Any]], limit: int = 8) -> list[str]:
    """Courts extraits des rejets (40 caracteres, masques) : montrent ce qui a ete rejete, pour le diagnostic."""
    return [
        f"{r.get('slot')}:{r.get('code')}:{redact_text(str(r.get('excerpt', '')))[:40]}" for r in rejections[:limit]
    ]


def _grounding_source(brief: dict[str, Any]) -> tuple[str, str]:
    """Source du controle d'ancrage : le dossier reecrit en phrases francaises, sinon son JSON.

    Le controle compare des phrases a une source. Avec le dossier en JSON (statuts en codes anglais, seuils en
    fractions), un texte fidele du modele obtenait 0,15 a 0,42 et pouvait etre remplace a tort par le gabarit ;
    avec les memes faits en phrases, 0,70 a 0,91 (mesures : docs/grounding_diagnosis.md). L'explicateur, lui,
    recoit toujours le dossier JSON. Si la reecriture echoue, on garde le JSON : le controle a toujours lieu.
    Ce score mesure la proximite du texte avec le dossier, pas l'exactitude des statuts (garantie par le code).
    """
    try:
        from .grounding_source import build_grounding_source
        text = build_grounding_source(brief)
        if text.strip():
            return text, "sentences"
    except Exception:  # la reecriture est une amelioration : jamais une cause d'echec
        pass
    return json.dumps(brief, ensure_ascii=False), "json"


def _model_text(output: dict[str, Any], brief: dict[str, Any] | None = None) -> str:
    """Les phrases ecrites par le modele : l'objet que le garde-fou doit verifier.

    Le texte rendu complet (tableaux, preuves) depasse la limite de 5000 caracteres du controle d'ancrage,
    et ses chiffres viennent du code, pas du modele : seules les phrases du modele sont a verifier.
    Si le dossier est fourni, les renvois ([E3], [G1]...) sont remplaces par les memes valeurs que celles que
    voit l'utilisateur : sans cela, le garde-fou lit des reperes opaques et ne peut pas les rattacher au dossier
    (scores d'ancrage mesures de 0,16 a 0,47). Repli sur le texte brut si le remplacement est impossible ou trop long.
    """
    parts = [output["summary"], *(factor["text"] for factor in output["factors"]),
             output["counterfactual"], output["variants"], output["limits_context"]]
    raw = "\n".join(part for part in parts if part)
    if brief is None:
        return raw
    try:
        from .explanation_rendering import _Registry   # meme remplacement que le rendu affiche
        registry = _Registry(brief)
        resolved = "\n".join(registry.substitute(part) for part in parts if part).replace("**", "")
    except Exception:  # le remplacement est une amelioration : jamais une cause d'echec
        return raw
    return resolved if len(resolved) <= GROUNDING_ANSWER_MAX_CHARS else raw


def check_request(
    text: str,
    *,
    mode: str | None = None,
    client: BedrockClient | None = None,
    config: BedrockConfig | None = None,
) -> GuardrailResult:
    """Verifie une requete utilisateur contre les sujets refuses du garde-fou.

    Ne rend jamais ``none`` sans avoir interroge le garde-fou : si le mode est
    ``offline``, si le garde-fou n'est pas configure ou si l'appel echoue, le
    resultat est ``not_run`` et l'interface doit afficher que le controle n'a
    pas eu lieu.
    """
    config = config or BedrockConfig.from_env()
    mode = mode or config.mode
    not_run = GuardrailResult(
        check="request_topic", action="not_run", denied_topics=[],
        grounding_score=None, relevance_score=None, mode="detect")
    if mode != "bedrock" or not (client or config.has_guardrail):
        return not_run
    bedrock_client = client or BedrockClient(config)
    if not bedrock_client.config.has_guardrail:
        return not_run
    try:
        return bedrock_client.check_request_topic(text)
    except BedrockError:
        return not_run


# ---- Agent conversationnel (issue 78) : questions de profil et "pourquoi" ----

# Reponse du code quand aucun texte de repli n'est disponible (module de Samer absent) : sans chiffre ni renvoi.
CONVERSATION_UNAVAILABLE = (
    "Le prototype ne peut pas encore rédiger de réponse à cette question. Les données utilisées et les limites "
    "restent affichées par le code."
)


def _conversation_collaborators(validate: Callable[..., Any] | None, fallback: Callable[..., Any] | None):
    """Validateur et reponse du code (flux B). Contrats attendus :
    ``explanation_validator.validate_reply(reply, brief) -> ValidationResult`` et
    ``conversation_fallback.build_fallback_reply(brief) -> ConversationReply``. Absents : ``None``.
    """
    if validate is None:
        try:
            from .explanation_validator import validate_reply as validate  # type: ignore[attr-defined]
        except ImportError:
            validate = None
    if fallback is None:
        try:
            from .conversation_fallback import build_fallback_reply as fallback  # type: ignore[import-not-found]
        except ImportError:
            fallback = None
    return validate, fallback


def _code_reply(brief: dict[str, Any], fallback: Callable[..., Any] | None) -> ConversationReply:
    """Reponse du code : celle du flux B si elle existe et est exploitable, sinon une phrase fixe."""
    if fallback is not None:
        try:
            reply = fallback(brief)
            if isinstance(reply, dict) and isinstance(reply.get("answer"), str) and reply["answer"].strip():
                return ConversationReply(
                    brief_id=brief["brief_id"], answer=reply["answer"], origin="template",
                    model_id=None, prompt_version=None, attempt=0)
        except Exception:  # la reponse du code ne doit jamais faire planter la page
            pass
    return ConversationReply(brief_id=brief["brief_id"], answer=CONVERSATION_UNAVAILABLE, origin="template",
                             model_id=None, prompt_version=None, attempt=0)


def answer_question(
    brief: ConversationBrief,
    mode: str = "offline",
    *,
    validate: Callable[..., Any] | None = None,
    fallback: Callable[..., Any] | None = None,
    client: BedrockClient | None = None,
    config: BedrockConfig | None = None,
    runner: Callable[..., ConversationReply] | None = None,
) -> ConversationResult:
    """Reponse a une question de profil ou un "pourquoi" : agent Bedrock sous controle, sinon le code.

    A appeler apres le routage de la conversation (garde-fou d'entree, controle local, regles, interprete) :
    jamais pour un refus, une salutation, une liste des positions, une definition du glossaire ou une idee.
    Le texte du modele n'est affiche que s'il passe le validateur et si le garde-fou rend un score sans
    intervenir ; un ancrage faible est signale, sans ecarter le texte (meme regle que l'explication).
    La question n'est jamais ecrite dans la trace. Rien n'est enregistre sur S3.
    """
    config = config or BedrockConfig.from_env()
    validate, fallback = _conversation_collaborators(validate, fallback)
    effective_mode, reason = _resolve_mode(mode, config, client)
    if effective_mode == "bedrock" and not config.has_guardrail:
        effective_mode, reason = "offline", "garde_fou_non_configure"   # regle 8 : aucun texte de modele sans garde-fou
    if effective_mode == "bedrock" and validate is None:
        effective_mode, reason = "offline", "validateur_indisponible"
    wanted_llm = mode == "bedrock"

    # Etape 1 : reponse (agent ou code)
    started = time.perf_counter()
    reply: ConversationReply | None = None
    model_id: str | None = None
    if effective_mode == "bedrock":
        run = runner or reply_with_llm
        try:
            bedrock_client = client or BedrockClient(config)
            reply = run(bedrock_client, config.conversation_model_id, brief, validate)
            model_id = config.conversation_model_id
        except Exception as error:  # repli sur la reponse du code, jamais de plantage
            known = isinstance(error, (BedrockError, AgentFailure))
            reason = f"{type(error).__name__}: {redact_text(str(error))}" if known else type(error).__name__
            reply = None
    if reply is None:
        reply = _code_reply(brief, fallback)
    details: dict[str, Any] = {
        "answer_kind": brief.get("answer_kind"), "level": brief.get("level"), "brief_id": brief.get("brief_id"),
        "origin": reply["origin"], "attempt": reply["attempt"],
    }
    if wanted_llm and reply["origin"] == "template":
        details["fallback_reason"] = reason or "rejet_du_validateur"
    trace = [_step(1, "explanation", "agent" if reply["origin"] == "llm" else "code",
                   "fallback" if (wanted_llm and reply["origin"] == "template") else "ok",
                   started, details, model_id if reply["origin"] == "llm" else None)]

    # Etape 2 : validation (code)
    started = time.perf_counter()
    if validate is None:
        validation = ValidationResult(is_valid=True, rejections=[], checked_references=[])
        trace.append(_step(2, "validation", "code", "skipped", started, {"reason": "validateur_indisponible"}))
    else:
        try:
            validation = validate(reply, brief)
        except Exception as error:  # validateur en erreur : la reponse du modele n'est pas affichee
            validation = ValidationResult(
                is_valid=False, rejections=[{"code": "validator_error", "slot": "answer", "excerpt": type(error).__name__}],
                checked_references=[])
        status = "ok"
        if not validation["is_valid"] and reply["origin"] == "llm":
            trace[0]["details"]["rejection_codes"] = [r.get("code") for r in validation["rejections"]]
            trace[0]["details"]["rejection_excerpts"] = _excerpts(validation["rejections"])
            reply = _code_reply(brief, fallback)
            try:
                validation = validate(reply, brief)
            except Exception:
                validation = ValidationResult(is_valid=True, rejections=[], checked_references=[])
            status = "fallback"
            trace[0]["status"] = "fallback"
            trace[0]["details"].update({"fallback_reason": "rejet_du_validateur", "origin": "template", "attempt": 0})
        trace.append(_step(2, "validation", "code", status, started, {
            "is_valid": validation["is_valid"], "checked_references": len(validation["checked_references"]),
            "rejection_codes": [r.get("code") for r in validation["rejections"]],
        }))

    # Etape 3 : garde-fou (ancrage de la reponse contre le dossier, sans la question dans la source)
    started = time.perf_counter()
    guardrail = GuardrailResult(check="output_grounding", action="not_run", denied_topics=[],
                                grounding_score=None, relevance_score=None, mode="detect")
    guard_status = "skipped"
    guard_details: dict[str, Any] = {"reason": reason if effective_mode == "offline" and reason else
                                     "mode_offline" if effective_mode == "offline" else "non_execute"}
    if effective_mode == "bedrock":
        try:
            bedrock_client = client or BedrockClient(config)
            checked_text = render_answer(reply, brief).replace("**", "")
            source_text, source_kind = conversation_grounding_source(brief)
            question = brief.get("question") if isinstance(brief.get("question"), str) else ""
            query = question[:MAX_QUESTION_CHARS].strip() or GROUNDING_QUERY
            guardrail = bedrock_client.check_output_grounding(source_text, query, checked_text)
            guard_status = "ok" if guardrail["action"] != "not_run" else "skipped"
            guard_details = {
                "action": guardrail["action"], "grounding_score": guardrail["grounding_score"],
                "relevance_score": guardrail["relevance_score"], "mode": guardrail["mode"],
                "checked_chars": len(checked_text), "source_kind": source_kind, "source_chars": len(source_text),
            }
            flags = getattr(bedrock_client, "last_grounding_flags", None)
            if isinstance(flags, dict) and flags.get("below_threshold"):
                guard_details["grounding_below_threshold"] = flags.get("filters", [])
                guard_details["grounding_weak"] = True
        except Exception as error:  # le controle est accessoire pour le code, obligatoire pour le modele
            guard_status = "error"
            guard_details = {"error": type(error).__name__}
    score = guardrail["grounding_score"]
    verified = guardrail["action"] == "none" and score is not None
    if verified and score < GROUNDING_FLOOR:
        guard_details.update({"grounding_weak": True, "grounding_very_weak": True, "grounding_floor": GROUNDING_FLOOR})
    if reply["origin"] == "llm" and not verified:
        unavailable = guardrail["action"] == "not_run" or (guardrail["action"] == "none" and score is None)
        reply = _code_reply(brief, fallback)
        if validate is not None:
            try:
                validation = validate(reply, brief)
            except Exception:
                validation = ValidationResult(is_valid=True, rejections=[], checked_references=[])
        trace[0]["status"] = "fallback"
        trace[0]["details"].update({
            "fallback_reason": "garde_fou_indisponible" if unavailable else "garde_fou_sortie",
            "origin": "template", "attempt": 0})
        guard_details["replaced_by_template"] = True
        if guardrail["denied_topics"]:
            guard_details["denied_topics"] = guardrail["denied_topics"]
    trace.append(_step(3, "guardrail", "guardrail", guard_status, started, guard_details))
    return ConversationResult(reply=reply, validation=validation, guardrail=guardrail,
                              rendered_answer=render_answer(reply, brief), trace=trace)
