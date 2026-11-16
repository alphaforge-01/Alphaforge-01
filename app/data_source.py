"""Seul point de contact entre l'interface et le reste du projet.

Trois sources de données (docs/ui_spec.md, section 3) :
- "offline" : vrais outils et vraie gouvernance de src/alphaforge/, séquence
  d'outils scriptée et explication par gabarit, sans aucun appel réseau ;
- "bedrock" : mêmes fonctions, avec les agents sur Amazon Bedrock. Le pipeline
  du flux C revient de lui-même au mode hors ligne si Bedrock est indisponible,
  et la trace l'indique ;
- "fixture" : fichiers de tests/fixtures/, chiffres inventés, filet de secours.

Le reste de l'interface ne sait pas d'où viennent les données. Ce module ne
calcule rien : il lit des fichiers ou appelle les fonctions des autres flux.
"""
from __future__ import annotations

import copy
import dataclasses
import functools
import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Mapping, Optional

import ui_texts as texts
from formatting import summary_section

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
GUARDRAIL_PROMPTS_PATH = FIXTURES_DIR / "guardrail_prompts.json"

MODES = ("offline", "bedrock", "fixture")
DEFAULT_MODE = "offline"


class DataUnavailable(Exception):
    """Donnée absente dans le mode choisi. Le message, en français, s'affiche tel quel."""


def resolve_mode(raw: Optional[str]) -> str:
    """Valeur initiale du mode, lue dans ALPHAFORGE_MODE. Absente ou inconnue : hors ligne."""
    value = (raw or "").strip().lower()
    return value if value in MODES else DEFAULT_MODE


def _src_module(name: str, missing_message: str) -> ModuleType:
    """Importe alphaforge.<name>. Seul un module du projet absent devient DataUnavailable.

    Une dépendance tierce absente (par exemple botocore) reste une vraie erreur :
    le message "module non fusionné" serait faux.
    """
    try:
        return importlib.import_module(f"alphaforge.{name}")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".")[0] == "alphaforge":
            raise DataUnavailable(missing_message) from exc
        raise


def _pipeline_mode(mode: str) -> str:
    """Mode transmis au pipeline du flux C, qui ne connaît que offline et bedrock."""
    return "bedrock" if mode == "bedrock" else "offline"


def _pipeline_config(mode: str) -> Any:
    """Configuration Bedrock lue dans l'environnement, avec le mode choisi dans l'interface.

    `BedrockConfig.can_call_models` exige `mode == "bedrock"`. Sans cette surcharge,
    choisir Bedrock dans la barre latérale ne servirait à rien si l'application a
    été lancée sans `ALPHAFORGE_MODE=bedrock`. Les autres valeurs (modèles,
    garde-fou, compartiment) restent celles de l'environnement.
    """
    bedrock_client = _src_module("bedrock_client", texts.MSG_PIPELINE_NOT_READY)
    return dataclasses.replace(bedrock_client.BedrockConfig.from_env(), mode=_pipeline_mode(mode))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_results() -> Dict[str, Dict[str, Any]]:
    """profile_id -> AnalysisResult, lu dans tests/fixtures/analysis_result_<id>_tsla.json."""
    results: Dict[str, Dict[str, Any]] = {}
    for path in sorted(FIXTURES_DIR.glob("analysis_result_*_tsla.json")):
        result = _read_json(path)
        results[result["profile"]["profile_id"]] = result
    return results


def _same_idea(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    keys = ("ticker", "target_weight", "funding_source", "funding_ticker")
    return all(left.get(key) == right.get(key) for key in keys)


# --- Profils ---------------------------------------------------------------

def get_personas(mode: str) -> Dict[str, Dict[str, Any]]:
    """profile_id -> {profile, portfolio, age, occupation_fr, summary_fr}.

    En mode fixture, tout vient des fixtures d'analyse, pour que le profil affiché
    et l'analyse restent cohérents. L'âge, le métier et le résumé y sont absents.
    """
    if mode == "fixture":
        return {
            profile_id: {
                "profile": result["profile"],
                "portfolio": result["portfolio_before"],
                "age": None,
                "occupation_fr": None,
                "summary_fr": None,
            }
            for profile_id, result in _fixture_results().items()
        }
    profiles = _src_module("profiles", texts.MSG_PROFILES_NOT_READY)
    return profiles.load_personas()


def check_profile_answers(answers: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Problèmes {code, severity, fields, message_fr} du profil construit (flux B)."""
    profiles = _src_module("profiles", texts.MSG_PROFILE_BUILDER_NOT_READY)
    return profiles.check_answers(answers)


def build_custom_persona(answers: Dict[str, Any], portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Persona "custom" : profil construit par le flux B et portefeuille fictif choisi.

    Lève ProfileValidationError (flux B) si une réponse est invalide.
    """
    profiles = _src_module("profiles", texts.MSG_PROFILE_BUILDER_NOT_READY)
    return {
        "profile": profiles.build_profile_from_answers(answers),
        "portfolio": copy.deepcopy(portfolio),
        "age": None,
        "occupation_fr": None,
        "summary_fr": None,
    }


# --- Données de référence (fichiers statiques, lus une fois) -----------------

@functools.lru_cache(maxsize=1)
def get_universe() -> List[Dict[str, Any]]:
    """Univers des actifs (flux A) : ticker, name, asset_class, currency, sector."""
    data_loading = _src_module("data_loading", texts.MSG_UNIVERSE_NOT_READY)
    frame = data_loading.load_universe()
    columns = ["ticker", "name", "asset_class", "currency", "sector"]
    return frame[columns].sort_values("ticker").to_dict(orient="records")


@functools.lru_cache(maxsize=1)
def get_sources() -> List[Dict[str, Any]]:
    """Provenance des fichiers de données (data/raw/sources_metadata.csv, flux A)."""
    data_loading = _src_module("data_loading", texts.MSG_UNIVERSE_NOT_READY)
    return data_loading.load_sources_metadata().fillna("").to_dict(orient="records")


@functools.lru_cache(maxsize=1)
def get_reference_limits() -> List[Dict[str, Any]]:
    """Catalogue fermé des limites (flux B) : limit_id, text_novice, text_pro."""
    reference_texts = _src_module("reference_texts", texts.MSG_REFERENCE_NOT_READY)
    return reference_texts.load_limits()


def get_threshold_notice(level: str) -> str:
    """Texte fixe du flux B sur les seuils (hypothèses de l'équipe)."""
    reference_texts = _src_module("reference_texts", texts.MSG_REFERENCE_NOT_READY)
    return reference_texts.threshold_assumption(level)


@functools.lru_cache(maxsize=1)
def get_guardrail_prompts() -> List[Dict[str, Any]]:
    """Requêtes prédéfinies du flux C (permises et refusées) pour l'onglet du garde-fou."""
    try:
        return _read_json(GUARDRAIL_PROMPTS_PATH)
    except (OSError, ValueError) as exc:
        raise DataUnavailable(texts.MSG_GUARDRAIL_PROMPTS_MISSING) from exc


def get_bedrock_status() -> Dict[str, bool]:
    """Ce que le mode bedrock pourra utiliser (oui ou non). Aucun identifiant n'est rendu."""
    config = _pipeline_config("bedrock")
    return {
        "can_call_models": bool(config.can_call_models),
        "has_guardrail": bool(config.has_guardrail),
        "has_trace_bucket": bool(config.trace_bucket),
    }


def split_verdicts(governance: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Verdicts global, financier et ESG d'un résultat de gouvernance (flux B, P1-9).

    `esg` vaut None quand le profil n'a pas de règle ESG : aucune pastille ESG n'est
    alors affichée. Sans le module de gouvernance, seul le verdict global est rendu.
    """
    try:
        governance_module = _src_module("governance", texts.MSG_PIPELINE_NOT_READY)
    except DataUnavailable:
        return {"overall": governance.get("overall_status"), "financial": None, "esg": None}
    return governance_module.split_verdicts(governance)


def rule_metric(rule_type: str) -> Optional[str]:
    """Métrique du registre associée à un type de règle (flux B), ou None."""
    try:
        governance = _src_module("governance", texts.MSG_PIPELINE_NOT_READY)
    except DataUnavailable:
        return None
    return governance.rule_metric(rule_type)


# --- Analyse ---------------------------------------------------------------

def get_xray(mode: str, profile: Dict[str, Any], portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Radiographie avant toute idée : {snapshot, governance, evidence, limits, is_fixture}.

    Code déterministe seulement (outil analyze_portfolio du flux A, gouvernance du
    flux B), sans agent : le résultat est le même dans les modes offline et bedrock.
    """
    if mode == "fixture":
        result = _fixture_results().get(profile["profile_id"])
        if result is None:
            raise DataUnavailable(texts.MSG_FIXTURE_PROFILE_MISSING)
        return {
            "snapshot": result["snapshot_before"],
            "governance": result["governance_before"],
            "evidence": result["evidence"],
            "limits": result["limits"],
            "is_fixture": True,
        }
    pipeline_deps = _src_module("pipeline_deps", texts.MSG_PIPELINE_NOT_READY)
    tool_specs = _src_module("tool_specs", texts.MSG_PIPELINE_NOT_READY)
    deps = pipeline_deps.resolve_deps()
    toolbox = tool_specs.ToolBox(deps, portfolio, as_of=None, capital_cad=profile.get("capital_cad"))
    tool_result = toolbox.call("analyze_portfolio")
    if tool_result["status"] != "ok":
        raise DataUnavailable(texts.MSG_XRAY_FAILED.format(
            reason=tool_result.get("error_message") or tool_result["status"]))
    snapshot = tool_result["data"]
    evidence = toolbox.evidence()
    governance = deps.evaluate(profile, snapshot, evidence=evidence)
    used = {lid for entry in evidence.values() for lid in entry.get("limit_ids", [])}
    limits = [limit for limit in get_reference_limits() if limit["limit_id"] in used]
    return {
        "snapshot": snapshot,
        "governance": governance,
        "evidence": evidence,
        "limits": limits,
        "is_fixture": bool(deps.is_fixture),
    }


def get_analysis(mode: str, profile: Dict[str, Any], portfolio: Dict[str, Any],
                 idea: Dict[str, Any]) -> Dict[str, Any]:
    """AnalysisResult pour un profil, son portefeuille et une idée."""
    if mode == "fixture":
        result = _fixture_results().get(profile["profile_id"])
        if result is None:
            raise DataUnavailable(texts.MSG_FIXTURE_PROFILE_MISSING)
        if not _same_idea(idea, result["idea"]):
            raise DataUnavailable(texts.MSG_FIXTURE_IDEA_ONLY)
        return result
    pipeline = _src_module("analysis_pipeline", texts.MSG_PIPELINE_NOT_READY)
    try:
        return pipeline.run_analysis(profile, portfolio, idea, mode=_pipeline_mode(mode),
                                     config=_pipeline_config(mode))
    except pipeline.AnalysisError as exc:
        reason = _simulation_problem(profile, portfolio, idea) or str(exc)
        raise DataUnavailable(texts.MSG_ANALYSIS_REFUSED.format(reason=reason)) from exc


def _simulation_problem(profile: Dict[str, Any], portfolio: Dict[str, Any],
                        idea: Dict[str, Any]) -> Optional[str]:
    """Message précis de l'outil de simulation (flux A) quand l'idée est impossible.

    Le pipeline ne garde qu'un message général : on redemande à l'outil, qui est
    déterministe et rapide, la raison exacte (par exemple un titre trop léger
    pour financer le poids visé). Aucune règle n'est réécrite ici.
    """
    try:
        agent_tools = _src_module("agent_tools", texts.MSG_PIPELINE_NOT_READY)
        outcome = agent_tools.simulate_portfolio_change(
            portfolio, idea, capital_cad=profile.get("capital_cad"))
    except Exception:  # le message général du pipeline reste disponible
        return None
    if outcome.get("status") == "ok":
        return None
    return outcome.get("error_message")


def get_explanation(mode: str, result: Dict[str, Any], level: str) -> Dict[str, Any]:
    """ExplanationResult au niveau demandé. Seul l'explicateur est relancé, jamais l'analyse."""
    pipeline = _src_module("analysis_pipeline", texts.MSG_PIPELINE_NOT_READY)
    try:
        return pipeline.explain(result, level, mode=_pipeline_mode(mode), config=_pipeline_config(mode))
    except pipeline.AnalysisError as exc:
        raise DataUnavailable(texts.MSG_EXPLANATION_REFUSED.format(reason=exc)) from exc


def get_conversation_answer(
    mode: str,
    persona: Dict[str, Any],
    question: str,
    level: str,
    answer_kind: str,
    request_check: Mapping[str, Any],
    result: Optional[Dict[str, Any]] = None,
    focus: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Construit le dossier ferme transmis a l'agent conversationnel."""
    pipeline = _src_module("analysis_pipeline", texts.MSG_PIPELINE_NOT_READY)
    brief_builder = _src_module("explanation_brief", texts.MSG_PIPELINE_NOT_READY)
    tools = _src_module("agent_tools", texts.MSG_PIPELINE_NOT_READY)
    profile = persona["profile"]
    brief: Dict[str, Any] = {
        "brief_id": f"conversation-{profile['profile_id']}-{answer_kind}",
        "level": level,
        "answer_kind": answer_kind,
        "focus": list(focus or []),
        "question": question,
        "profile_context": brief_builder.build_profile_context(profile),
        "evidence": [],
        "checks": [],
        "idea": None,
        "glossary": [],
        "limits": [],
        "cards": [],
        "missing": [],
    }
    if answer_kind in ("explanation", "what_changes"):
        if result is None:
            raise DataUnavailable(texts.MSG_EXPLANATION_REFUSED.format(reason="analyse absente"))
        brief.update(brief_builder.build_brief(result, level))
        brief["answer_kind"] = answer_kind
        brief["focus"] = list(focus or [])
        brief["question"] = question
    elif answer_kind == "profile":
        profile_result = tools.get_profile_facts(profile)
        if profile_result["status"] != "ok":
            raise DataUnavailable(texts.MSG_PROFILE_FACTS_FAILED.format(
                reason=profile_result.get("error_message") or profile_result["status"]))
        brief["evidence"] = [
            {**entry, "evidence_id": f"E{index}"}
            for index, entry in enumerate(profile_result["evidence"], start=1)
        ]
        brief["missing"] = list(profile_result["data"].get("missing") or [])
    elif answer_kind == "xray":
        xray = get_xray(mode, profile, persona["portfolio"])
        brief["evidence"] = list(xray["evidence"].values())
        brief["checks"] = list(xray["governance"].get("checks") or [])
    elif answer_kind == "concept":
        for term in brief_builder.load_glossary():
            level_text = term.get(level) or {}
            brief["glossary"].append({
                "term_id": term["term_id"],
                "term": term["term"],
                "definition": level_text.get("definition", ""),
                "analogy": level_text.get("analogy", ""),
            })
    else:
        raise DataUnavailable(texts.MSG_UNEXPECTED_ERROR.format(error_type="question_inconnue"))
    return pipeline.answer_question(
        brief,
        mode=_pipeline_mode(mode),
        config=_pipeline_config(mode),
        request_check=dict(request_check),
    )


def _conversation_providers(mode: str, persona: Dict[str, Any], result: Optional[Dict[str, Any]]) -> Any:
    """Données des outils de l'agent conversationnel, calculées par le code (aucun agent ici)."""
    tools_module = _src_module("conversation_tools", texts.MSG_PIPELINE_NOT_READY)
    brief_builder = _src_module("explanation_brief", texts.MSG_PIPELINE_NOT_READY)
    agent_tools = _src_module("agent_tools", texts.MSG_PIPELINE_NOT_READY)
    profile, portfolio = persona["profile"], persona["portfolio"]
    return tools_module.ConversationProviders(
        profile=profile,
        profile_context=lambda: brief_builder.build_profile_context(profile),
        profile_facts=lambda: agent_tools.get_profile_facts(profile),
        xray=lambda: get_xray(mode, profile, portfolio),
        asset_facts=lambda ticker: get_asset_facts(mode, ticker, portfolio),
        universe=get_universe,
        glossary=brief_builder.load_glossary,
        analysis_brief=lambda level: brief_builder.build_brief(result, level) if result is not None else None,
    )


def converse(mode: str, persona: Dict[str, Any], question: str, level: str,
             request_check: Mapping[str, Any], result: Optional[Dict[str, Any]] = None,
             flagged_topics: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Message traité par l'agent avec outils ; None si l'agent n'est pas disponible (règles).

    Un message signalé (garde-fou ou contrôle local) va aussi à l'agent, qui reformule vers le permis.
    """
    pipeline = _src_module("analysis_pipeline", texts.MSG_PIPELINE_NOT_READY)
    return pipeline.converse_with_tools(
        question, level, _conversation_providers(mode, persona, result), _pipeline_mode(mode),
        profile_label=str(persona["profile"].get("display_name") or persona["profile"].get("profile_id")),
        has_analysis=result is not None, request_check=dict(request_check), config=_pipeline_config(mode),
        flagged_topics=list(flagged_topics or []))


def converse_at_level(mode: str, persona: Dict[str, Any], question: str, level: str,
                      request_check: Mapping[str, Any], calls: List[Dict[str, Any]],
                      result: Optional[Dict[str, Any]] = None,
                      notice: Optional[List[str]] = None) -> Dict[str, Any]:
    """Même réponse à un autre niveau : les outils sont rejoués par le code, seul le texte est réécrit."""
    pipeline = _src_module("analysis_pipeline", texts.MSG_PIPELINE_NOT_READY)
    tools_module = _src_module("conversation_tools", texts.MSG_PIPELINE_NOT_READY)
    brief = tools_module.replay(_conversation_providers(mode, persona, result), level, calls, question)
    if notice:
        brief["guardrail_notice"] = list(notice)
    return pipeline.answer_question(brief, mode=_pipeline_mode(mode), config=_pipeline_config(mode),
                                    request_check=dict(request_check))


def get_asset_facts(mode: str, ticker: str, portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Faits historiques sur un actif (outil get_asset_facts du flux A), sans agent.

    Ils ne dépendent pas du profil : la même idée donne les mêmes chiffres de l'actif
    pour tous les profils (US-09). Rend {"evidence": ..., "data": ...}.
    """
    if mode == "fixture":
        raise DataUnavailable(texts.MSG_FIXTURE_NO_ASSET_FACTS)
    pipeline_deps = _src_module("pipeline_deps", texts.MSG_PIPELINE_NOT_READY)
    tool_specs = _src_module("tool_specs", texts.MSG_PIPELINE_NOT_READY)
    toolbox = tool_specs.ToolBox(pipeline_deps.resolve_deps(), portfolio, as_of=None, capital_cad=None)
    tool_result = toolbox.call("get_asset_facts", {"ticker": ticker})
    if tool_result["status"] != "ok":
        raise DataUnavailable(texts.MSG_ASSET_FACTS_FAILED.format(
            ticker=ticker, reason=tool_result.get("error_message") or tool_result["status"]))
    return {"evidence": toolbox.evidence(), "data": tool_result["data"]}


def check_request(mode: str, text: str) -> Dict[str, Any]:
    """GuardrailResult d'une requête prédéfinie (sujets refusés du garde-fou Bedrock)."""
    pipeline = _src_module("analysis_pipeline", texts.MSG_PIPELINE_NOT_READY)
    return pipeline.check_request(text, mode=_pipeline_mode(mode), config=_pipeline_config(mode))


# --- Demandes en langage naturel et aperçu des niveaux -----------------------------

DEMO_TRACES_DIR = PROJECT_ROOT / "outputs" / "reports" / "demo_traces"
# Profils qui ont une trace réelle de l'explicateur ; les autres montrent celle de Robert.
PREVIEW_PERSONAS = ("robert", "amira")


def parse_request(text: str, universe: List[Dict[str, Any]], held_tickers: List[str],
                  previous_idea: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Demande en langage naturel -> idée, idée à confirmer, réponse du code, question ou refus.

    Règles déterministes, sans modèle. `previous_idea` : dernière idée analysée, pour les relances.
    """
    request_parsing = _src_module("request_parsing", texts.MSG_PIPELINE_NOT_READY)
    return dataclasses.asdict(request_parsing.parse_request(
        text, universe, held_tickers=held_tickers, previous_idea=previous_idea))


@functools.lru_cache(maxsize=1)
def get_glossary() -> Dict[str, Dict[str, Any]]:
    """Glossaire fermé du projet (flux B), par identifiant de terme. Lu tel quel, jamais complété."""
    explanation_brief = _src_module("explanation_brief", texts.MSG_PIPELINE_NOT_READY)
    return {term["term_id"]: term for term in explanation_brief.load_glossary()}


@functools.lru_cache(maxsize=4)
def get_level_preview(profile_id: str) -> Dict[str, Any]:
    """Même passage d'explication aux niveaux novice et pro, tiré des traces réelles de démonstration.

    Textes produits par l'agent explicateur sur Bedrock (outputs/reports/demo_traces/),
    jamais inventés par l'interface.
    """
    persona = profile_id if profile_id in PREVIEW_PERSONAS else PREVIEW_PERSONAS[0]
    preview: Dict[str, Any] = {"persona": persona}
    for level in ("novice", "pro"):
        path = DEMO_TRACES_DIR / f"{persona}_explanation_{level}.json"
        try:
            explanation = _read_json(path)["explanation"]
        except (OSError, KeyError, ValueError) as exc:
            raise DataUnavailable(texts.MSG_PREVIEW_MISSING) from exc
        preview[level] = summary_section(explanation.get("rendered_markdown", ""))
        preview[f"{level}_source"] = str(path.relative_to(PROJECT_ROOT))
        preview["model_id"] = explanation.get("model_id")
        preview["origin"] = explanation.get("origin")
    return preview
