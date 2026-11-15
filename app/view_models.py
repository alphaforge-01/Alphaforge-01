"""Structures de présentation pour les composants de l'interface v2 (PR-1).

Ce module transforme un `AnalysisResult` existant en objets simples (dataclasses
immuables) que les futurs composants Streamlit n'auront qu'à afficher. Il suit
les règles d'affichage de docs/ui_spec.md :

- aucune dépendance à Streamlit, donc testable sans interface ;
- aucun calcul financier : chaque chiffre vient du registre de preuves
  (`value` et `display_value`), de la gouvernance (flux B) ou d'un paramètre de
  l'idée ou du profil ;
- aucune donnée inventée : une valeur absente du résultat reste `None` et la
  ligne ou la carte correspondante est omise, jamais complétée par une valeur
  par défaut ;
- aucune lecture de fichier, aucun appel réseau.

Point d'entrée : `build_result_view(result)`. Les fonctions `build_*` sont aussi
publiques pour qu'un composant n'en utilise qu'une.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import ui_texts as texts
from alphaforge.explanation_brief import build_profile_context
from alphaforge.governance import rule_metric, split_verdicts, worst_status
from formatting import format_cad, format_horizon, format_pct
from ui_labels import (  # noqa: F401  (HEADLINE_METRICS est ré-exporté pour les composants)
    CHIP_CAPITAL, CHIP_CRYPTO, CHIP_HORIZON, CRYPTO_ALLOWED, CRYPTO_EXCLUDED, HEADLINE_METRICS,
    PROFILE_CHIP_LABELS,
)

SUBJECT_BEFORE = "portfolio_before"
SUBJECT_AFTER = "portfolio_after"
WEIGHT_PREFIX = "weights."


# --- Structures -----------------------------------------------------------------

@dataclass(frozen=True)
class MetricCard:
    """Une mesure du portefeuille après l'idée, avec l'avant et l'écart quand ils existent."""
    metric: str
    label: str
    value: float
    value_display: str
    before_display: Optional[str]
    delta_display: Optional[str]   # texte du registre, signe inclus ("+11,11 pts")
    status: Optional[str] = None   # pire statut des règles du profil sur cette mesure, sinon None


@dataclass(frozen=True)
class VerdictBadge:
    status: str            # compliant, tension, conflict, missing_info
    label: str
    color: str             # couleur nommée de Streamlit


@dataclass(frozen=True)
class Verdicts:
    """Verdicts séparés (P1-9). `financial` ou `esg` vaut None si le profil n'a pas ces règles."""
    overall: Optional[VerdictBadge]
    financial: Optional[VerdictBadge]
    esg: Optional[VerdictBadge]


@dataclass(frozen=True)
class ThresholdBar:
    """Une règle chiffrée en pourcentage : la valeur mesurée face à ses deux seuils."""
    check_id: str
    label: str
    value: float
    value_display: str
    warn: Optional[float]
    limit: float
    warn_display: Optional[str]
    limit_display: str
    direction: str         # "max" : mauvais au-dessus du seuil ; "min" : mauvais en dessous
    status: str
    status_label: str


@dataclass(frozen=True)
class WeightRow:
    """Poids d'un titre avant et après l'idée, tels que le registre les donne.

    Un côté absent du registre vaut None (par exemple le titre ajouté n'a pas de
    poids "avant" dans le registre). Le composant décide de l'affichage, pas ce module.
    """
    ticker: str
    name: str
    before: Optional[float]
    before_display: Optional[str]
    after: Optional[float]
    after_display: Optional[str]


@dataclass(frozen=True)
class VariantRow:
    """Une ligne de comparaison : l'idée initiale (row_id "initial") ou une variante (V1, V2)."""
    row_id: str
    reason_code: Optional[str]
    reason_label: Optional[str]
    target_weight_display: str      # paramètre de l'idée, pas un résultat
    status: str
    status_label: str
    volatility: Optional[float]
    volatility_display: Optional[str]
    max_drawdown: Optional[float]
    max_drawdown_display: Optional[str]


@dataclass(frozen=True)
class ProfileChip:
    label: str
    value: str


@dataclass(frozen=True)
class ResultView:
    """Tout ce que la page de simulation v2 affiche pour un résultat d'analyse."""
    is_fixture: bool
    ticker: str
    target_weight_display: str
    profile_name: str
    objective: Optional[str]
    profile_chips: List[ProfileChip]
    verdicts: Verdicts
    metric_cards: List[MetricCard]
    threshold_bars: List[ThresholdBar]
    weight_rows: List[WeightRow]
    variant_rows: List[VariantRow]


# --- Aides ----------------------------------------------------------------------

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _entries(evidence: Any) -> Iterable[Mapping[str, Any]]:
    """Entrées du registre, qu'il soit un dict {evidence_id: entrée} ou une liste (dossier)."""
    if isinstance(evidence, Mapping):
        return [entry for entry in evidence.values() if isinstance(entry, Mapping)]
    if isinstance(evidence, (list, tuple)):
        return [entry for entry in evidence if isinstance(entry, Mapping)]
    return []


def index_evidence(evidence: Any) -> Dict[Tuple[str, str], Mapping[str, Any]]:
    """(sujet, métrique) -> entrée du registre. La première entrée gagne si un doublon existe."""
    index: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    for entry in _entries(evidence):
        key = (str(entry.get("subject", "")), str(entry.get("metric", "")))
        index.setdefault(key, entry)
    return index


def _numeric_entry(index: Mapping[Tuple[str, str], Mapping[str, Any]], subject: str,
                   metric: str) -> Optional[Mapping[str, Any]]:
    """Entrée utilisable (valeur numérique et texte affiché), sinon None."""
    entry = index.get((subject, metric))
    if entry is None or not _is_number(entry.get("value")) or not entry.get("display_value"):
        return None
    return entry


def _badge(status: Optional[str]) -> Optional[VerdictBadge]:
    if status is None:
        return None
    return VerdictBadge(
        status=status,
        label=texts.STATUS_LABELS.get(status, status),
        color=texts.STATUS_COLORS.get(status, "gray"),
    )


# --- Constructeurs --------------------------------------------------------------

def _metric_status(governance: Optional[Mapping[str, Any]], metric: str) -> Optional[str]:
    """Pire statut des règles qui portent sur `metric` (association `governance.rule_metric`), sinon None."""
    if not isinstance(governance, Mapping):
        return None
    statuses = [str(check["status"]) for check in governance.get("checks") or []
                if check.get("status") and rule_metric(str(check.get("rule_type"))) == metric]
    return worst_status(statuses) if statuses else None


def build_metric_cards(evidence: Any, after_subject: str = SUBJECT_AFTER,
                       before_subject: str = SUBJECT_BEFORE,
                       governance: Optional[Mapping[str, Any]] = None) -> List[MetricCard]:
    """Cartes de tête. Une mesure sans valeur "après" dans le registre est omise.

    Avec `governance`, chaque carte reçoit le pire statut des règles du profil sur cette
    mesure ; sans règle correspondante, `status` reste None (aucun statut n'est deviné).
    """
    index = index_evidence(evidence)
    cards: List[MetricCard] = []
    for metric, label in HEADLINE_METRICS:
        after = _numeric_entry(index, after_subject, metric)
        if after is None:
            continue
        before = _numeric_entry(index, before_subject, metric)
        delta = _numeric_entry(index, after_subject, f"{metric}_delta")
        cards.append(MetricCard(
            metric=metric,
            label=label,
            value=float(after["value"]),
            value_display=str(after["display_value"]),
            before_display=str(before["display_value"]) if before else None,
            delta_display=str(delta["display_value"]) if delta else None,
            status=_metric_status(governance, metric),
        ))
    return cards


def build_verdicts(governance: Optional[Mapping[str, Any]]) -> Verdicts:
    """Verdicts global, financier et ESG, par `governance.split_verdicts` (flux B)."""
    if not isinstance(governance, Mapping):
        return Verdicts(None, None, None)
    split = split_verdicts(governance)
    return Verdicts(_badge(split.get("overall")), _badge(split.get("financial")),
                    _badge(split.get("esg")))


def _direction(check: Mapping[str, Any], rules: Mapping[str, Mapping[str, Any]]) -> str:
    """Sens de la règle : lu dans le profil, sinon déduit de l'ordre des seuils (min : avertir > limite)."""
    rule = rules.get(str(check.get("rule_id")))
    if rule and rule.get("direction") in ("max", "min"):
        return str(rule["direction"])
    warn, limit = check.get("warn_threshold"), check.get("limit_threshold")
    if _is_number(warn) and _is_number(limit) and warn > limit:
        return "min"
    return "max"


def build_threshold_bars(governance: Optional[Mapping[str, Any]], evidence: Any = None,
                         profile: Optional[Mapping[str, Any]] = None) -> List[ThresholdBar]:
    """Règles en pourcentage avec une valeur et une limite, dans l'ordre de la gouvernance.

    Sont omises : les règles booléennes ou sans seuil, et celles dont la valeur est
    absente (information manquante). Le texte de la valeur est celui du registre quand
    la règle y renvoie une preuve de même valeur ; sinon il est formaté depuis la valeur.
    """
    if not isinstance(governance, Mapping):
        return []
    rules = {str(rule.get("rule_id")): rule for rule in (profile or {}).get("rules", [])
             if isinstance(rule, Mapping)}
    by_id = {str(entry.get("evidence_id")): entry for entry in _entries(evidence)}
    bars: List[ThresholdBar] = []
    for check in governance.get("checks") or []:
        value, limit, warn = check.get("value"), check.get("limit_threshold"), check.get("warn_threshold")
        if check.get("unit") != "pct" or not _is_number(value) or not _is_number(limit):
            continue
        if check.get("status") == "missing_info":
            continue
        display = None
        for evidence_id in check.get("evidence_ids") or []:
            entry = by_id.get(str(evidence_id))
            if entry and entry.get("value") == value and entry.get("display_value"):
                display = str(entry["display_value"])
                break
        status = str(check.get("status"))
        bars.append(ThresholdBar(
            check_id=str(check.get("check_id")),
            label=str(check.get("label_fr")),
            value=float(value),
            value_display=display or format_pct(value),
            warn=float(warn) if _is_number(warn) else None,
            limit=float(limit),
            warn_display=format_pct(warn) if _is_number(warn) else None,
            limit_display=format_pct(limit),
            direction=_direction(check, rules),
            status=status,
            status_label=texts.STATUS_LABELS.get(status, status),
        ))
    return bars


def build_weight_rows(evidence: Any, names: Optional[Mapping[str, str]] = None,
                      before_subject: str = SUBJECT_BEFORE,
                      after_subject: str = SUBJECT_AFTER) -> List[WeightRow]:
    """Poids avant et après par titre, lus dans les preuves `weights.<ticker>`.

    Triés par le plus grand des deux poids, puis par ticker. Rien n'est comblé : un
    titre absent d'un côté du registre garde `None` de ce côté.
    """
    names = names or {}
    index = index_evidence(evidence)
    tickers = sorted({metric[len(WEIGHT_PREFIX):] for (subject, metric) in index
                      if subject in (before_subject, after_subject) and metric.startswith(WEIGHT_PREFIX)})
    rows: List[WeightRow] = []
    for ticker in tickers:
        before = _numeric_entry(index, before_subject, WEIGHT_PREFIX + ticker)
        after = _numeric_entry(index, after_subject, WEIGHT_PREFIX + ticker)
        if before is None and after is None:
            continue
        rows.append(WeightRow(
            ticker=ticker,
            name=names.get(ticker, ticker),
            before=float(before["value"]) if before else None,
            before_display=str(before["display_value"]) if before else None,
            after=float(after["value"]) if after else None,
            after_display=str(after["display_value"]) if after else None,
        ))
    return sorted(rows, key=lambda row: (-max(row.before or 0.0, row.after or 0.0), row.ticker))


def _variant_row(row_id: str, reason_code: Optional[str], idea: Mapping[str, Any],
                 governance: Optional[Mapping[str, Any]], index: Mapping[Tuple[str, str], Mapping[str, Any]],
                 subject: str) -> VariantRow:
    status = str((governance or {}).get("overall_status", "missing_info"))
    volatility = _numeric_entry(index, subject, "volatility_ann")
    drawdown = _numeric_entry(index, subject, "max_drawdown")
    weight = idea.get("target_weight")
    return VariantRow(
        row_id=row_id,
        reason_code=reason_code,
        reason_label=texts.REASON_LABELS.get(reason_code, reason_code) if reason_code else None,
        target_weight_display=format_pct(weight) if _is_number(weight) else "",
        status=status,
        status_label=texts.STATUS_LABELS.get(status, status),
        volatility=float(volatility["value"]) if volatility else None,
        volatility_display=str(volatility["display_value"]) if volatility else None,
        max_drawdown=float(drawdown["value"]) if drawdown else None,
        max_drawdown_display=str(drawdown["display_value"]) if drawdown else None,
    )


def build_variant_rows(result: Mapping[str, Any]) -> List[VariantRow]:
    """Idée initiale puis variantes du résultat, chacune avec son verdict et ses mesures.

    Une variante sans mesure dans le registre garde `None` pour cette mesure. Sans
    variante, la liste ne contient que l'idée initiale : aucune comparaison à tracer.
    """
    idea = result.get("idea")
    if not isinstance(idea, Mapping):
        return []
    index = index_evidence(result.get("evidence"))
    rows = [_variant_row("initial", None, idea, result.get("governance_after"), index, SUBJECT_AFTER)]
    for variant in result.get("variants") or []:
        variant_id = str(variant.get("variant_id"))
        rows.append(_variant_row(variant_id, variant.get("reason_code"), variant.get("idea") or {},
                                 variant.get("governance"), index, f"variant:{variant_id}"))
    return rows


def build_profile_chips(profile: Optional[Mapping[str, Any]]) -> List[ProfileChip]:
    """Pastilles du contexte déclaré du profil fictif : seulement ce que le profil contient."""
    if not isinstance(profile, Mapping):
        return []
    context = build_profile_context(profile) or {}
    chips: List[ProfileChip] = []
    low, high = context.get("horizon_years_min"), context.get("horizon_years_max")
    if low is not None and high is not None:
        chips.append(ProfileChip(CHIP_HORIZON, format_horizon(low, high)))
    for key, label in PROFILE_CHIP_LABELS:
        if context.get(key):
            chips.append(ProfileChip(label, str(context[key])))
    if "crypto_allowed" in context:
        chips.append(ProfileChip(CHIP_CRYPTO, CRYPTO_ALLOWED if context["crypto_allowed"] else CRYPTO_EXCLUDED))
    capital = profile.get("capital_cad")
    if _is_number(capital):
        chips.append(ProfileChip(CHIP_CAPITAL, format_cad(capital)))
    return chips


def build_result_view(result: Mapping[str, Any],
                      names: Optional[Mapping[str, str]] = None) -> ResultView:
    """Vue complète d'un `AnalysisResult`. Lit seulement `result`, ne le modifie pas."""
    profile = result.get("profile") if isinstance(result.get("profile"), Mapping) else {}
    idea = result.get("idea") if isinstance(result.get("idea"), Mapping) else {}
    evidence = result.get("evidence")
    context = build_profile_context(profile) or {}
    weight = idea.get("target_weight")
    return ResultView(
        is_fixture=bool(result.get("is_fixture")),
        ticker=str(idea.get("ticker", "")),
        target_weight_display=format_pct(weight) if _is_number(weight) else "",
        profile_name=str(profile.get("display_name", "")),
        objective=context.get("objective"),
        profile_chips=build_profile_chips(profile),
        verdicts=build_verdicts(result.get("governance_after")),
        metric_cards=build_metric_cards(evidence, governance=result.get("governance_after")),
        threshold_bars=build_threshold_bars(result.get("governance_after"), evidence, profile),
        weight_rows=build_weight_rows(evidence, names),
        variant_rows=build_variant_rows(result),
    )


__all__: Sequence[str] = (
    "MetricCard", "VerdictBadge", "Verdicts", "ThresholdBar", "WeightRow", "VariantRow",
    "ProfileChip", "ResultView", "build_metric_cards", "build_verdicts", "build_threshold_bars",
    "build_weight_rows", "build_variant_rows", "build_profile_chips", "build_result_view",
    "index_evidence",
)
