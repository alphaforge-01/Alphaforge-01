"""Gouvernance déterministe (flux B, tâche B2).

`evaluate` compare un instantané de portefeuille aux règles d'un profil et
rend un `GovernanceResult` : un statut par règle, une marge et le pire statut.
Aucun modèle de langage n'intervient. Aucune valeur manquante n'est inventée.

Conventions (hypothèses de l'équipe, voir `profiles.py` pour les seuils) :
- Règle "max" : tension au-delà de `warn_threshold`, conflit au-delà de
  `limit_threshold`. Une valeur exactement égale à un seuil ne le franchit pas.
- Règle "min" : tension en dessous de `warn_threshold`, conflit en dessous de
  `limit_threshold`. Même principe pour l'égalité.
- Les comparaisons tolèrent un bruit de calcul flottant de `EPSILON`.
- `margin` est la distance au prochain seuil, signée : positive s'il reste de
  la place avant le prochain changement de statut, négative si la limite est
  dépassée (conflit). Conforme : distance au seuil de tension. Tension et
  conflit : distance à la limite. Elle est `None` s'il n'y a plus de seuil.
- Pire statut : conflict > tension > missing_info > compliant. Un statut connu
  mais défavorable prime sur une information manquante, et l'information
  manquante prime sur "conforme" : l'absence de donnée ne vaut jamais conformité.
  Sans aucune règle, le résultat global est `missing_info`.
- Le contrefactuel complet (balayage du poids avec `simulate_fn`) relève de B5.
  Ici `counterfactual` vaut toujours `None`.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Union

from alphaforge.contracts import (
    Counterfactual, EvidenceEntry, GovernanceResult, InvestmentIdea, InvestorProfile,
    Rule, RuleCheck, RuleStatus,
)

EPSILON = 1e-9
MARGIN_DECIMALS = 6

# Gravité croissante. Réutilisable par le classement des facteurs (B4).
STATUS_SEVERITY: Dict[str, int] = {
    "compliant": 0,
    "missing_info": 1,
    "tension": 2,
    "conflict": 3,
}

# Champ de `PortfolioSnapshot` qui alimente chaque type de règle. Ce nom sert aussi
# de `metric` pour retrouver les preuves (`evidence_key` = "<metric>:<subject>").
# Les règles par classe d'actifs lisent `weight_by_asset_class[classe]`. Le contrat
# ne prévoit pas de métrique de preuve propre à une classe : elles n'ont donc
# aucune preuve associée tant que le contrat ne la définit pas.
_SNAPSHOT_FIELD = {
    "max_single_asset_weight": "top_asset_weight",
    "max_portfolio_volatility": "volatility_ann",
    "max_portfolio_drawdown": "max_drawdown",
    "min_defensive_share": "defensive_share",
    "max_correlated_group_weight": "largest_correlated_group_weight",
}

def rule_metric(rule_type: str) -> Optional[str]:
    """Métrique de preuve associée à un type de règle, ou `None` (règles par classe d'actifs)."""
    return _SNAPSHOT_FIELD.get(rule_type)


EvidenceInput = Union[Mapping[str, EvidenceEntry], Iterable[EvidenceEntry], None]


def _is_valid_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), MARGIN_DECIMALS)


def _extract_value(rule: Rule, snapshot: Mapping[str, Any]):
    """Retourne `(valeur, métrique, raison_manquante)` pour une règle."""
    rule_type = rule["rule_type"]

    if rule_type in _SNAPSHOT_FIELD:
        field = _SNAPSHOT_FIELD[rule_type]
        value = snapshot.get(field)
        if not _is_valid_number(value):
            return None, field, f"Valeur indisponible dans l'instantané : {field}."
        return float(value), field, None

    if rule_type in ("max_asset_class_weight", "excluded_asset_class"):
        asset_class = (rule.get("params") or {}).get("asset_class")
        if not asset_class:
            return None, None, "Classe d'actifs absente des paramètres de la règle."
        metric = None  # pas de métrique de preuve par classe dans le contrat
        by_class = snapshot.get("weight_by_asset_class")
        if not isinstance(by_class, Mapping):
            return None, metric, "Répartition par classe d'actifs indisponible dans l'instantané."
        # La répartition couvre toutes les positions : une classe absente pèse 0.
        value = by_class.get(asset_class, 0.0)
        if not _is_valid_number(value):
            return None, metric, f"Poids invalide pour la classe d'actifs : {asset_class}."
        return float(value), metric, None

    if rule_type == "esg_exclusion":
        return None, None, "Aucune preuve ESG disponible : la règle ne peut pas être évaluée."
    return None, None, f"Type de règle non pris en charge : {rule_type}."


def _thresholds_error(rule: Rule) -> Optional[str]:
    warn, limit = rule.get("warn_threshold"), rule.get("limit_threshold")
    for name, value in (("avertissement", warn), ("limite", limit)):
        if value is not None and not _is_valid_number(value):
            return f"Seuil de {name} invalide."
    if warn is None and limit is None:
        return "Aucun seuil défini pour cette règle."
    if rule["direction"] not in ("max", "min"):
        return "Sens de la règle inconnu."
    if warn is not None and limit is not None:
        if rule["direction"] == "max" and warn > limit + EPSILON:
            return "Seuils incohérents : l'avertissement dépasse la limite."
        if rule["direction"] == "min" and warn < limit - EPSILON:
            return "Seuils incohérents : l'avertissement est sous la limite."
    return None


def _classify(rule: Rule, value: float):
    """Retourne `(statut, marge)` pour une valeur connue et des seuils valides."""
    warn, limit = rule["warn_threshold"], rule["limit_threshold"]
    sign = 1.0 if rule["direction"] == "max" else -1.0
    # En orientant le sens, "au-delà" devient toujours "supérieur à".
    oriented = sign * value
    oriented_warn = None if warn is None else sign * warn
    oriented_limit = None if limit is None else sign * limit

    if oriented_limit is not None and oriented > oriented_limit + EPSILON:
        return "conflict", oriented_limit - oriented
    if oriented_warn is not None and oriented > oriented_warn + EPSILON:
        margin = None if oriented_limit is None else oriented_limit - oriented
        return "tension", margin
    next_threshold = oriented_warn if oriented_warn is not None else oriented_limit
    return "compliant", next_threshold - oriented


def _find_evidence_ids(entries: List[EvidenceEntry], metric: Optional[str], subject: str) -> List[str]:
    if metric is None:
        return []
    ids = [e["evidence_id"] for e in entries
           if e.get("metric") == metric and e.get("subject") == subject and e.get("evidence_id")]
    return sorted(set(ids), key=lambda i: (len(i), i))


def _normalize_evidence(evidence: EvidenceInput) -> List[EvidenceEntry]:
    if evidence is None:
        return []
    if isinstance(evidence, Mapping):
        return list(evidence.values())
    return list(evidence)


def _compute_counterfactual(
    rule: Rule,
    status: RuleStatus,
    simulate_fn: Optional[Callable[..., Any]],
    idea: Optional[InvestmentIdea],
) -> Optional[Counterfactual]:
    """Emplacement du contrefactuel (tâche B5, balayage du poids de l'idée).

    B2 ne calcule rien : retourne toujours `None`.
    """
    return None


def _build_check(index: int, rule: Rule, snapshot: Mapping[str, Any], subject: str,
                 entries: List[EvidenceEntry],
                 simulate_fn: Optional[Callable[..., Any]],
                 idea: Optional[InvestmentIdea]) -> RuleCheck:
    value, metric, missing_reason = _extract_value(rule, snapshot)
    if missing_reason is None:
        missing_reason = _thresholds_error(rule)

    status: RuleStatus
    margin: Optional[float] = None
    if missing_reason is not None:
        status = "missing_info"
        shown_value: Optional[float] = None
    else:
        status, margin = _classify(rule, value)  # type: ignore[arg-type]
        shown_value = value

    evidence_ids = _find_evidence_ids(entries, metric, subject)
    counterfactual = (_compute_counterfactual(rule, status, simulate_fn, idea)
                      if status in ("tension", "conflict") else None)
    return {
        "check_id": f"G{index}",
        "rule_id": rule["rule_id"],
        "rule_type": rule["rule_type"],
        "label_fr": rule["label_fr"],
        "status": status,
        "value": shown_value,
        "warn_threshold": rule.get("warn_threshold"),
        "limit_threshold": rule.get("limit_threshold"),
        "margin": _round(margin),
        "unit": rule["unit"],
        "evidence_ids": evidence_ids,
        "counterfactual": counterfactual,
        "missing_reason": missing_reason,
    }


def worst_status(statuses: Iterable[str]) -> RuleStatus:
    """Pire statut selon `STATUS_SEVERITY`. Liste vide : `missing_info`."""
    statuses = list(statuses)
    if not statuses:
        return "missing_info"
    return max(statuses, key=lambda s: STATUS_SEVERITY[s])  # type: ignore[return-value]


def evaluate(
    profile: InvestorProfile,
    snapshot: Mapping[str, Any],
    simulate_fn: Optional[Callable[..., Any]] = None,
    idea: Optional[InvestmentIdea] = None,
    *,
    evidence: EvidenceInput = None,
) -> GovernanceResult:
    """Évalue chaque règle du profil sur un `PortfolioSnapshot`.

    - `snapshot["subject"]` devient le `subject` du résultat.
    - `simulate_fn` et `idea` sont réservés au contrefactuel (B5) : sans effet ici.
    - `evidence` (facultatif, ajout rétrocompatible) : registre de preuves, dict
      `evidence_id -> entrée` ou liste d'entrées. Une règle reçoit les preuves
      dont `metric` et `subject` correspondent. Sans correspondance : liste vide.

    Lève `ValueError` si le profil n'a pas de `profile_id` ou si l'instantané
    n'est pas un dictionnaire avec un `subject` texte.
    """
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("subject"), str):
        raise ValueError("L'instantané doit être un dictionnaire avec un 'subject' texte.")
    if not isinstance(profile, Mapping) or not profile.get("profile_id"):
        raise ValueError("Le profil doit contenir un 'profile_id'.")

    subject = snapshot["subject"]
    entries = _normalize_evidence(evidence)
    checks = [
        _build_check(i, rule, snapshot, subject, entries, simulate_fn, idea)
        for i, rule in enumerate(profile.get("rules") or [], start=1)
    ]
    return {
        "profile_id": profile["profile_id"],
        "subject": subject,
        "overall_status": worst_status(c["status"] for c in checks),
        "checks": checks,
    }
