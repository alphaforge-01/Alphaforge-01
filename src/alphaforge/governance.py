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
- Règle `esg_exclusion` : sans preuve ESG (aucune n'existe dans le dépôt), elle rend toujours
  `missing_info`, jamais `compliant`. Le pire statut global d'un profil à exigence ESG est donc
  au mieux `missing_info`, même si toutes les règles financières sont conformes.
- Pire statut : conflict > tension > missing_info > compliant. Un statut connu
  mais défavorable prime sur une information manquante, et l'information
  manquante prime sur "conforme" : l'absence de donnée ne vaut jamais conformité.
  Sans aucune règle, le résultat global est `missing_info`.
- Verdicts séparés (P1-9) : `overall_status` reste le pire statut de toutes les règles. S'y ajoutent
  `financial_status` (règles financières seulement) et `esg_status` (règles `esg_exclusion` seulement),
  avec les mêmes priorités. Une famille sans règle vaut `None` : pas de verdict ESG inventé pour un profil
  sans règle ESG. Tant qu'aucune preuve ESG n'existe, la règle ESG rend toujours `missing_info`,
  donc `esg_status` ne vaut jamais `compliant`. `split_verdicts` lit aussi les anciens résultats.
- Le contrefactuel (balayage du poids avec `simulate_fn`) est calculé par
  `counterfactual.py` (B5) pour les contrôles en tension ou en conflit, seulement si
  `simulate_fn` et `idea` sont fournis. Sinon, ou si la simulation est indisponible,
  `counterfactual` vaut `None`.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Union

from alphaforge.contracts import (
    EvidenceEntry, GovernanceResult, InvestmentIdea, InvestorProfile,
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
# Les règles par classe d'actifs lisent `weight_by_asset_class[classe]` et retrouvent
# leur preuve par la métrique composée `weight_by_asset_class.<classe>` (voir
# `docs/evidence_keys.md`). Le flux A ne produit pas de preuve pour une classe
# absente du portefeuille (son poids est 0) : la liste de preuves reste alors vide.
_SNAPSHOT_FIELD = {
    "max_single_asset_weight": "top_asset_weight",
    "max_portfolio_volatility": "volatility_ann",
    "max_portfolio_drawdown": "max_drawdown",
    "min_defensive_share": "defensive_share",
    "max_correlated_group_weight": "largest_correlated_group_weight",
}

ASSET_CLASS_METRIC_PREFIX = "weight_by_asset_class"
_ASSET_CLASS_RULE_TYPES = ("max_asset_class_weight", "excluded_asset_class")


def asset_class_metric(asset_class: str) -> str:
    """Métrique de preuve du poids d'une classe d'actifs : `weight_by_asset_class.<classe>`."""
    return f"{ASSET_CLASS_METRIC_PREFIX}.{asset_class}"


def rule_metric(rule_type: str, params: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """Métrique de preuve associée à une règle, ou `None` si aucune n'est définie.

    Les règles par classe d'actifs demandent `params["asset_class"]` : sans classe, `None`
    (aucune preuve n'est devinée). Les autres types de règle ignorent `params`.
    """
    if rule_type in _ASSET_CLASS_RULE_TYPES:
        asset_class = (params or {}).get("asset_class")
        return asset_class_metric(asset_class) if asset_class else None
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
        metric = asset_class_metric(asset_class)
        by_class = snapshot.get("weight_by_asset_class")
        if not isinstance(by_class, Mapping):
            return None, metric, "Répartition par classe d'actifs indisponible dans l'instantané."
        # La répartition couvre toutes les positions : une classe absente pèse 0.
        value = by_class.get(asset_class, 0.0)
        if not _is_valid_number(value):
            return None, metric, f"Poids invalide pour la classe d'actifs : {asset_class}."
        return float(value), metric, None

    if rule_type == "esg_exclusion":
        return None, None, ("Aucune preuve ESG disponible : la vérification ESG est impossible, "
                            "aucun verdict ESG n'est donné.")
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


def _build_check(index: int, rule: Rule, snapshot: Mapping[str, Any], subject: str,
                 entries: List[EvidenceEntry]) -> RuleCheck:
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
        "counterfactual": None,   # rempli par `evaluate` si une simulation est fournie
        "missing_reason": missing_reason,
    }


def _attach_counterfactuals(profile: InvestorProfile, checks: List[RuleCheck],
                            simulate_fn: Optional[Callable[..., Any]],
                            idea: Optional[InvestmentIdea]) -> None:
    """Ajoute le contrefactuel (B5) aux contrôles en tension ou en conflit.

    Sans `simulate_fn` ou sans idée, ou si la simulation est indisponible ou peu
    fiable, `counterfactual` reste `None` : rien n'est inventé.
    """
    flagged = [c["rule_id"] for c in checks if c["status"] in ("tension", "conflict")]
    if simulate_fn is None or idea is None or not flagged:
        return
    from alphaforge.counterfactual import compute_counterfactuals   # import tardif (cycle)
    results = compute_counterfactuals(profile, idea, simulate_fn, rule_ids=flagged)
    for check in checks:
        if check["rule_id"] in results:
            check["counterfactual"] = results[check["rule_id"]]


def worst_status(statuses: Iterable[str]) -> RuleStatus:
    """Pire statut selon `STATUS_SEVERITY`. Liste vide : `missing_info`."""
    statuses = list(statuses)
    if not statuses:
        return "missing_info"
    return max(statuses, key=lambda s: STATUS_SEVERITY[s])  # type: ignore[return-value]


ESG_RULE_TYPES = frozenset({"esg_exclusion"})


def is_esg_rule_type(rule_type: Any) -> bool:
    """Vrai pour un type de règle ESG. Toutes les autres règles sont financières."""
    return rule_type in ESG_RULE_TYPES


def partition_statuses(checks: Iterable[Mapping[str, Any]]):
    """`(statut financier, statut ESG)` : pire statut de chaque famille de contrôles.

    Une famille sans contrôle donne `None` : aucun verdict n'est inventé pour un profil sans règle ESG
    (ou sans règle financière). Mêmes priorités que le verdict global (`STATUS_SEVERITY`).
    """
    financial, esg = [], []
    for check in checks:
        (esg if is_esg_rule_type(check.get("rule_type")) else financial).append(check["status"])
    return (worst_status(financial) if financial else None, worst_status(esg) if esg else None)


def split_verdicts(governance: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    """Les trois verdicts d'un `GovernanceResult`, aussi pour un ancien résultat sans les champs P1-9.

    Rend `{"overall": ..., "financial": ..., "esg": ...}`. `financial` et `esg` sont recalculés depuis
    `checks` quand il y en a (source de vérité), sinon lus dans `financial_status` et `esg_status`, sinon
    `None`. `overall` est `overall_status` tel quel, sans recalcul. À utiliser pour afficher deux verdicts.
    """
    checks = governance.get("checks") or []
    if checks:
        financial, esg = partition_statuses(checks)
    else:
        financial, esg = governance.get("financial_status"), governance.get("esg_status")
    return {"overall": governance.get("overall_status"), "financial": financial, "esg": esg}


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
    - `simulate_fn(idea) -> ToolResult | PortfolioSnapshot` et `idea` : voir
      `counterfactual.py`. Sans eux, aucun contrefactuel n'est calculé.
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
        _build_check(i, rule, snapshot, subject, entries)
        for i, rule in enumerate(profile.get("rules") or [], start=1)
    ]
    _attach_counterfactuals(profile, checks, simulate_fn, idea)
    financial_status, esg_status = partition_statuses(checks)
    return {
        "profile_id": profile["profile_id"],
        "subject": subject,
        "overall_status": worst_status(c["status"] for c in checks),   # inchangé : toutes les règles
        "checks": checks,
        "financial_status": financial_status,
        "esg_status": esg_status,
    }
