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

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .bedrock_client import BedrockClient, BedrockConfig, BedrockError, redact_text
from .contracts import (
    AnalysisResult, AnalystSubmission, ExplanationResult, GovernanceResult, GuardrailResult,
    InvestmentIdea, InvestorProfile, Level, Portfolio, PortfolioSnapshot, TraceStep, Variant,
)
from .pipeline_deps import PipelineDeps, resolve_deps
from .tool_specs import (
    MAX_HIGHLIGHTS, MAX_VARIANTS, REASON_CODES, AnalystFailure, AnalystOutcome, ToolBox,
    ToolBudgetExceeded, normalize_idea,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIMITS_FILE = PROJECT_ROOT / "src" / "alphaforge" / "reference" / "limits.json"
VALID_MODES = ("offline", "bedrock")
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
        step=step, name=name, actor=actor, status=status, model_id=model_id,  # type: ignore[typeddict-item]
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
        others = [p for p in portfolio["positions"] if p["ticker"] != idea["ticker"]]
        if others:
            largest = max(others, key=lambda p: p["weight"])["ticker"]
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


def _load_limits(deps: PipelineDeps, limit_ids: list[str]) -> list[dict]:
    if deps.limits_for is not None:
        return deps.limits_for(limit_ids)
    if LIMITS_FILE.exists():
        raw = json.loads(LIMITS_FILE.read_text(encoding="utf-8"))
        items = list(raw.values()) if isinstance(raw, dict) else raw
        wanted = set(limit_ids)
        return [item for item in items if not wanted or item.get("limit_id") in wanted]
    return []


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
            except (BedrockError, AnalystFailure, ToolBudgetExceeded) as error:
                fallback_reason = f"{type(error).__name__}: {redact_text(str(error))}"
                outcome = None
                toolbox = ToolBox(deps, portfolio, as_of=as_of, capital_cad=capital)
    if outcome is None:
        outcome = scripted_sequence(toolbox, idea)
    if not any(r["tool_name"] == "simulate_portfolio_change" and r["status"] == "ok" for r in toolbox.results):
        toolbox.call("simulate_portfolio_change", _idea_params(idea))
    if not any(r["tool_name"] == "analyze_portfolio" and r["status"] == "ok" for r in toolbox.results):
        toolbox.call("analyze_portfolio")
    understood, _ = normalize_idea(outcome.submission.get("understood_idea"))
    simulation = next(
        (r for r in toolbox.results if r["tool_name"] == "simulate_portfolio_change" and r["status"] == "ok"
         and r["params"].get("ticker") == (understood or idea)["ticker"]
         and r["params"].get("target_weight") == (understood or idea)["target_weight"]),
        None,
    ) or next((r for r in toolbox.results if r["tool_name"] == "simulate_portfolio_change" and r["status"] == "ok"), None)
    if simulation is None:
        raise AnalysisError("La simulation de l'idee n'a pas abouti : aucun resultat exploitable.")
    snapshot_before, snapshot_after = _snapshots_from_simulation(simulation)
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

    governance_before = deps.evaluate(profile, snapshot_before)
    governance_after = deps.evaluate(profile, snapshot_after, simulate_fn=simulate_fn, idea=idea)

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
        simulated = toolbox.call("simulate_portfolio_change", _idea_params(variant_idea))
        if simulated["status"] != "ok":
            continue
        variant_id = f"V{len(variants) + 1}"
        snapshot = {**_snapshots_from_simulation(simulated)[1], "subject": f"variant:{variant_id}"}
        variants.append(Variant(
            variant_id=variant_id, reason_code=raw["reason_code"], idea=variant_idea,
            snapshot=snapshot, governance=deps.evaluate(profile, snapshot, simulate_fn=simulate_fn, idea=variant_idea),
        ))
    trace.append(_step(2, "governance", "code", "ok", started, {
        "overall_before": governance_before["overall_status"], "overall_after": governance_after["overall_status"],
        "checks": [{"check_id": c["check_id"], "status": c["status"], "margin": c["margin"]}
                   for c in governance_after["checks"]],
        "variants": [{"variant_id": v["variant_id"], "overall_status": v["governance"]["overall_status"]}
                     for v in variants],
    }))

    evidence = toolbox.evidence()
    limit_ids = sorted({lid for entry in evidence.values() for lid in entry.get("limit_ids", [])})
    submission = AnalystSubmission(
        understood_idea=idea,
        variants=[{"reason_code": v["reason_code"], "idea": v["idea"]} for v in variants],
        highlight_evidence_ids=[e for e in outcome.submission.get("highlight_evidence_ids", []) if e in evidence][:MAX_HIGHLIGHTS],
        unsupported_requests=list(outcome.submission.get("unsupported_requests", [])),
    )
    as_of_value = as_of or next((e["as_of"] for e in evidence.values() if e.get("as_of")), None) \
        or datetime.now(timezone.utc).date().isoformat()
    result = AnalysisResult(
        run_id=uuid.uuid4().hex[:12], created_at=_now_iso(), as_of=as_of_value,
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
) -> ExplanationResult:
    """Explication au niveau demande : dossier, texte, validation, controle du garde-fou.

    Le texte vient du gabarit si l'explicateur Bedrock est indisponible, rejete
    par le validateur ou en erreur. Le repli est signale dans la trace.
    """
    deps = deps or resolve_deps()
    config = config or BedrockConfig.from_env()
    effective_mode, config_fallback = _resolve_mode(mode, config, client)
    brief = deps.build_brief(result, level)

    # Etape 4 : explication
    started = time.perf_counter()
    output: dict[str, Any] | None = None
    fallback_reason = config_fallback
    model_id: str | None = None
    if effective_mode == "bedrock":
        runner = explainer_runner or _load_explainer_runner()
        if runner is None:
            fallback_reason = "explicateur_indisponible"
        else:
            try:
                bedrock_client = client or BedrockClient(config)
                output = runner(bedrock_client, config.explainer_model_id, brief, deps.validate)
                model_id = config.explainer_model_id
            except (BedrockError, AnalystFailure) as error:
                fallback_reason = f"{type(error).__name__}: {redact_text(str(error))}"
    if output is None:
        output = deps.render_template(brief)
    details: dict[str, Any] = {
        "level": level, "origin": output["origin"], "attempt": output["attempt"], "brief_id": brief["brief_id"],
    }
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
    if not validation["is_valid"]:
        rejected = [r["code"] for r in validation["rejections"]]
        output = deps.render_template(brief)
        validation = deps.validate(output, brief)
        status = "fallback"
        trace[0]["status"] = "fallback"
        trace[0]["details"]["fallback_reason"] = "rejet_du_validateur"
        trace[0]["details"]["rejection_codes"] = rejected
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
    guard_details: dict[str, Any] = {"reason": "mode_offline" if effective_mode == "offline" else "non_execute"}
    if effective_mode == "bedrock" and config.has_guardrail:
        try:
            bedrock_client = client or BedrockClient(config)
            guardrail = bedrock_client.check_output_grounding(
                json.dumps(brief, ensure_ascii=False), "Explique le resultat de l'analyse.", markdown)
            guard_status = "ok" if guardrail["action"] != "not_run" else "skipped"
            guard_details = {
                "action": guardrail["action"], "grounding_score": guardrail["grounding_score"],
                "relevance_score": guardrail["relevance_score"], "mode": guardrail["mode"],
            }
        except BedrockError as error:
            guard_status = "error"
            guard_details = {"error": type(error).__name__}
    elif effective_mode == "bedrock":
        guard_details = {"reason": "garde_fou_non_configure"}
    trace.append(_step(6, "guardrail", "guardrail", guard_status, started, guard_details))

    return ExplanationResult(
        output=output, validation=validation, guardrail=guardrail, rendered_markdown=markdown, trace=trace)  # type: ignore[typeddict-item]


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
