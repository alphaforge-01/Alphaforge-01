"""Shared JSON-serializable contracts for all AlphaForge streams.

Flux B owns this file. Keep its schemas synchronized with docs/sprint_plan.md.
All percentage values are fractions: 0.25 means 25%.
"""
from __future__ import annotations

from typing import ForwardRef, Literal, NotRequired, TypedDict, get_origin

Level = Literal["novice", "pro"]
RuleStatus = Literal["compliant", "tension", "conflict", "missing_info"]
RuleType = Literal[
    "max_single_asset_weight", "max_asset_class_weight", "max_portfolio_volatility",
    "max_portfolio_drawdown", "min_defensive_share", "excluded_asset_class",
    "max_correlated_group_weight", "esg_exclusion",   # les deux derniers : P2
]
ReasonCode = Literal["reduce_weight", "change_funding_source", "spread_across_existing"]

class Rule(TypedDict):
    rule_id: str            # "R1"
    rule_type: RuleType
    params: dict            # ex. {"asset_class": "crypto"}
    direction: Literal["max", "min"]
    warn_threshold: float | None    # au-delà : tension
    limit_threshold: float | None   # au-delà : conflit
    unit: Literal["pct", "ratio", "bool"]
    label_fr: str
    origin: Literal["persona", "checkbox"]
    is_assumption: bool     # toujours True : seuil = hypothèse de l'équipe

class InvestorProfile(TypedDict):
    profile_id: str         # "robert", "amira", "mateo", "custom"
    display_name: str
    is_fictional: bool      # toujours True
    objective: str
    horizon_years_min: int
    horizon_years_max: int
    risk_tolerance: Literal["low", "low_moderate", "moderate", "high"]
    experience: Literal["beginner", "intermediate", "advanced"]
    esg_preference: Literal["none", "moderate", "strong"]
    crypto_allowed: bool
    capital_cad: float
    default_level: Level
    rules: list[Rule]

class Position(TypedDict):
    ticker: str
    weight: float           # somme des poids = 1.0

class Portfolio(TypedDict):
    portfolio_id: str
    label_fr: str
    is_fictional: bool
    base_currency: Literal["CAD"]
    positions: list[Position]

class InvestmentIdea(TypedDict):
    ticker: str
    target_weight: float
    funding_source: Literal["pro_rata", "from_ticker"]
    funding_ticker: str | None

class EvidenceEntry(TypedDict):
    evidence_id: str        # "E1", attribué par le registre
    evidence_key: str       # stable : "<metric>:<subject>"
    tool_name: str
    metric: str             # "volatility_ann", "max_drawdown", "recovery_days", ...
    subject: str            # ticker, "portfolio_before", "portfolio_after", "variant:V1"
    label_fr: str
    value: float | str | None
    unit: Literal["pct", "cad", "days", "ratio", "count", "text"]
    display_value: str
    qualifier: Literal["low", "moderate", "high"] | None   # réservé : toujours None, aucun seuil global de risque ; les jugements viennent de la gouvernance, par profil
    period_start: str | None    # ISO
    period_end: str | None
    as_of: str
    currency: Literal["CAD", "USD"] | None
    source_ids: list[str]       # identifiants de data/raw/sources_metadata.csv ou sources.md
    transformation: str         # phrase courte en français
    n_observations: int | None
    limit_ids: list[str]        # "L1", ...

class ToolResult(TypedDict):
    tool_name: str
    call_id: str
    params: dict
    status: Literal["ok", "missing_info", "error"]
    error_message: str | None
    data: dict                  # forme propre à l'outil, voir plus bas
    evidence: list[EvidenceEntry]

class PortfolioSnapshot(TypedDict):   # data de analyze_portfolio
    subject: str
    weights: dict[str, float]
    volatility_ann: float
    max_drawdown: float
    max_drawdown_start: str
    max_drawdown_end: str
    recovery_days: int | None   # None = pas encore récupéré dans la fenêtre
    top_asset: str
    top_asset_weight: float
    weight_by_sector: dict[str, float]
    weight_by_asset_class: dict[str, float]
    currency_exposure: dict[str, float]   # {"CAD": .., "USD": ..}
    defensive_share: float
    largest_correlated_group_weight: float | None   # P2 : voir diversification.py ; None = trop peu d'observations
    correlated_group_members: NotRequired[list[str]]   # titres du plus gros groupe corrélé (vide : aucun groupe)

class Counterfactual(TypedDict):
    parameter: Literal["target_weight"]
    compliant_at_or_below: float | None   # None = aucun poids conforme
    display_value: str

class RuleCheck(TypedDict):
    check_id: str               # "G1"
    rule_id: str
    rule_type: RuleType
    label_fr: str
    status: RuleStatus
    value: float | None
    warn_threshold: float | None
    limit_threshold: float | None
    margin: float | None        # distance au prochain seuil
    unit: str
    evidence_ids: list[str]
    counterfactual: Counterfactual | None
    missing_reason: str | None

class GovernanceResult(TypedDict):
    profile_id: str
    subject: str                # "portfolio_before", "portfolio_after", "variant:V1"
    overall_status: RuleStatus  # le pire statut
    checks: list[RuleCheck]
    # Ajouts facultatifs (P1-9) : `overall_status` reste le pire statut de TOUTES les règles.
    financial_status: NotRequired[RuleStatus | None]   # pire statut des règles financières ; None si le profil n'en a pas
    esg_status: NotRequired[RuleStatus | None]         # pire statut des règles ESG (`esg_exclusion`) ; None sans règle ESG

class AnalystSubmission(TypedDict):     # paramètres de submit_analysis
    understood_idea: InvestmentIdea
    variants: list[dict]        # au plus 2 : {"reason_code": ReasonCode, "idea": InvestmentIdea}
    highlight_evidence_ids: list[str]   # au plus 2 choisies par l'analyste, puis les faits de l'actif ajoutes par le code
    unsupported_requests: list[str]

class Variant(TypedDict):
    variant_id: str             # "V1"
    reason_code: ReasonCode
    idea: InvestmentIdea
    snapshot: PortfolioSnapshot
    governance: GovernanceResult

class TraceStep(TypedDict):
    step: int                   # 1 à 6
    name: Literal["analysis", "governance", "brief", "explanation", "validation", "guardrail"]
    actor: Literal["agent", "code", "guardrail"]
    status: Literal["ok", "fallback", "skipped", "error"]
    model_id: str | None
    duration_ms: int
    details: dict               # ex. tool_calls: [{tool_name, params, status, evidence_ids}], turns

class AnalysisResult(TypedDict):
    run_id: str
    created_at: str
    as_of: str
    mode: Literal["bedrock", "offline"]
    is_fixture: bool            # True : chiffres inventés, bandeau "données d'essai"
    profile: InvestorProfile
    portfolio_before: Portfolio
    idea: InvestmentIdea
    snapshot_before: PortfolioSnapshot
    snapshot_after: PortfolioSnapshot
    governance_before: GovernanceResult
    governance_after: GovernanceResult
    variants: list[Variant]
    evidence: dict[str, EvidenceEntry]
    limits: list[dict]          # {limit_id, text_novice, text_pro}
    submission: AnalystSubmission
    trace: list[TraceStep]      # étapes 1 à 3

class ProfileContext(TypedDict, total=False):
    """Contexte du profil fictif lu par l'explicateur (ajout facultatif, voir `ExplanationBrief`).

    Chaque clé est copiée du `InvestorProfile` du résultat, jamais déduite : une clé dont la valeur
    est absente ou invalide dans le profil est omise. Les libellés `*_fr` traduisent les valeurs
    fermées du profil (table fixe de `explanation_brief.py`). Ni nom, ni capital, ni seuil.
    """
    objective: str                  # objectif du profil, tel quel (une ligne, sans balise)
    horizon_years_min: int
    horizon_years_max: int
    risk_tolerance: str             # valeur de `InvestorProfile.risk_tolerance`
    risk_tolerance_fr: str          # "faible", "faible à modérée", "modérée", "élevée"
    experience: str
    experience_fr: str              # "débutant", "intermédiaire", "avancé"
    esg_preference: str
    esg_preference_fr: str          # "aucune", "modérée", "forte"
    crypto_allowed: bool


class ExplanationBrief(TypedDict):      # seule entrée de l'explicateur
    brief_id: str               # empreinte du contenu, sert de clé de cache
    run_id: str
    level: Level
    profile_rules: list[Rule]
    idea: InvestmentIdea
    ranked_factors: list[dict]  # {rank, check_id, status, evidence_ids}, ordre fixé par le code
    checks: list[RuleCheck]
    variants: list[dict]        # {variant_id, reason_code, overall_status, evidence_ids}
    evidence: list[EvidenceEntry]
    limits: list[dict]          # {limit_id, text} pour le niveau
    glossary: list[dict]        # {term_id "T1", term, definition, analogy}
    max_chars_per_slot: int
    profile_context: NotRequired[ProfileContext]   # facultatif : horizon, objectif, préférences du profil fictif

class ExplainerOutput(TypedDict):
    brief_id: str
    level: Level
    summary: str                # texte avec renvois [E3] [G1] [T2], aucun chiffre en clair
    factors: list[dict]         # {check_id, text}, même ordre que ranked_factors
    counterfactual: str
    variants: str
    limits_context: str
    origin: Literal["llm", "template"]
    model_id: str | None
    prompt_version: str | None
    attempt: int

class ValidationResult(TypedDict):
    is_valid: bool
    rejections: list[dict]      # {code, slot, excerpt}
    checked_references: list[str]
# codes : unknown_reference, number_outside_registry, forbidden_term,
#         missing_rule_citation, slot_missing, too_long

class GuardrailResult(TypedDict):
    check: Literal["request_topic", "output_grounding"]
    action: Literal["none", "intervened", "not_run"]
    denied_topics: list[str]
    grounding_score: float | None
    relevance_score: float | None
    mode: Literal["detect", "block"]

class ExplanationResult(TypedDict):
    output: ExplainerOutput
    validation: ValidationResult
    guardrail: GuardrailResult
    rendered_markdown: str      # renvois remplacés par les valeurs du registre
    trace: list[TraceStep]      # étapes 4 à 6
    brief: NotRequired[ExplanationBrief]   # dossier lu par l'explicateur, facultatif (ajout rétrocompatible)


# ---- Agent conversationnel (issue 78) : questions de profil et "pourquoi" ----

AnswerKind = Literal["profile", "xray", "explanation", "what_changes", "concept"]


class ConversationBrief(TypedDict):     # seule entrée de l'agent conversationnel, construite par le code
    brief_id: str
    level: Level
    answer_kind: AnswerKind
    focus: list[str]                    # identifiants E#, G# ou T# mis en avant par le code
    question: str                       # question de l'utilisateur, jamais écrite dans les traces
    profile_context: ProfileContext | None
    evidence: list[EvidenceEntry]
    checks: list[RuleCheck]
    idea: InvestmentIdea | None         # None : question sans idée analysée
    glossary: list[dict]
    limits: list[dict]
    cards: list[dict]                   # fiches pédagogiques F#, vides sans accord d'un mentor
    missing: list[str]                  # informations absentes, à dire comme telles


class ConversationReply(TypedDict):
    brief_id: str
    answer: str                         # texte avec renvois [E#] [G#] [T#], aucun chiffre en clair
    origin: Literal["llm", "template"]
    model_id: str | None
    prompt_version: str | None
    attempt: int                        # 0 : texte du code


class ConversationResult(TypedDict):
    reply: ConversationReply
    validation: ValidationResult
    guardrail: GuardrailResult
    rendered_answer: str                # renvois remplacés par les valeurs du registre
    trace: list[TraceStep]              # réponse, validation, garde-fou


def _is_not_required(annotation: object) -> bool:
    """Vrai si l'annotation est `NotRequired[...]`, écrite en texte ou évaluée.

    Ce module utilise `from __future__ import annotations` : `TypedDict` ne voit alors
    pas `NotRequired` et classe la clé comme obligatoire dans `__required_keys__`.
    """
    if isinstance(annotation, ForwardRef):      # TypedDict enveloppe les textes dans un ForwardRef
        annotation = annotation.__forward_arg__
    if isinstance(annotation, str):
        return annotation.replace(" ", "").startswith(("NotRequired[", "typing.NotRequired["))
    return get_origin(annotation) is NotRequired


def check_keys(obj: object, contract: type) -> list[str]:
    """Return missing required top-level keys for a TypedDict contract.

    This is a *key presence* check, not a complete runtime validator.
    Type, range, enum, and nested constraints require separate tests.
    """
    if not isinstance(obj, dict):
        return ["<not a dictionary>"]
    required = getattr(contract, "__required_keys__", frozenset())
    annotations = getattr(contract, "__annotations__", {})
    return sorted(str(key) for key in required
                  if key not in obj and not _is_not_required(annotations.get(key)))
