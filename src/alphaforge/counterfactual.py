"""Contrefactuel de gouvernance (flux B, tâche B5).

Question servie : "À quel poids cible l'idée serait-elle conforme ?"

Principe : on balaie le poids cible de l'idée par pas de 0.01 (1 point de
pourcentage), de 0.01 jusqu'au poids demandé inclus. À chaque poids, `simulate_fn`
donne l'instantané du portefeuille simulé, puis `governance.evaluate` réévalue
toutes les règles. Aucune logique financière n'est dupliquée ici : la simulation
appartient au flux A (`simulate_portfolio_change`), le verdict à `governance.py`.

Interface de `simulate_fn` (à brancher sur le flux A) :

    simulate_fn(idea: InvestmentIdea) -> ToolResult | PortfolioSnapshot

Le portefeuille de départ, `as_of` et le capital sont déjà fixés par l'appelant
(par exemple `functools.partial(simulate_portfolio_change, portfolio, as_of=...)`
adapté pour ne prendre que l'idée). Le résultat est soit un `ToolResult` de statut
"ok" dont `data` est un `PortfolioSnapshot`, soit directement le `PortfolioSnapshot`.

Règles :
- Le plus grand poids conforme est cherché sur toute la grille, sans supposer que
  la conformité est monotone (on ne s'arrête pas au premier échec).
- "Conforme" veut dire statut `compliant`. `missing_info` n'est jamais conforme.
- Un poids dont la simulation ou l'évaluation est indisponible reste inconnu.
  Si un poids inconnu pourrait contredire la réponse (il est plus grand que le
  poids conforme trouvé, ou aucun poids conforme n'a été trouvé), le contrefactuel
  est `None` : rien n'est inventé.
- `Counterfactual` avec `compliant_at_or_below=None` veut dire : la grille a été
  entièrement évaluée et aucun poids n'est conforme. Un contrefactuel `None` veut
  dire : non calculé ou non fiable.
- Le poids 0 (ne pas ajouter l'idée) n'est pas testé.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from alphaforge.contracts import Counterfactual, GovernanceResult, InvestmentIdea, InvestorProfile
from alphaforge.explanation_rendering import format_percent

STEP = 0.01
NO_SOLUTION_FR = "aucun poids conforme"
TOLERANCE = 1e-6

SimulateFn = Callable[[InvestmentIdea], Any]
# Un point de balayage : (poids, résultat de gouvernance ou None, raison d'indisponibilité).
SweepPoint = Tuple[float, Optional[GovernanceResult], Optional[str]]


def weight_grid(target_weight: Any) -> List[float]:
    """Poids testés : 0.01, 0.02, ... jusqu'à `target_weight` inclus (arrondi vers le bas)."""
    if isinstance(target_weight, bool) or not isinstance(target_weight, (int, float)):
        return []
    if not math.isfinite(target_weight) or target_weight <= 0:
        return []
    steps = int(math.floor(min(target_weight, 1.0) / STEP + 1e-9))
    return [round(k * STEP, 2) for k in range(1, steps + 1)]


def _snapshot_from(simulated: Any) -> Tuple[Optional[Mapping[str, Any]], Optional[str]]:
    """Extrait un instantané d'un résultat de simulation, ou explique pourquoi c'est impossible."""
    if not isinstance(simulated, Mapping):
        return None, "résultat de simulation absent ou invalide"
    if "status" in simulated and "tool_name" in simulated:      # ToolResult
        if simulated.get("status") != "ok":
            return None, f"simulation en statut {simulated.get('status')}"
        data = simulated.get("data")
    else:                                                        # PortfolioSnapshot direct
        data = simulated
    if not isinstance(data, Mapping) or not isinstance(data.get("weights"), Mapping):
        return None, "instantané de simulation invalide"
    return data, None


def sweep(profile: InvestorProfile, idea: InvestmentIdea, simulate_fn: SimulateFn) -> List[SweepPoint]:
    """Simule chaque poids de la grille et réévalue la gouvernance.

    Retourne un point par poids, dans l'ordre croissant. Un point sans résultat de
    gouvernance porte la raison de l'indisponibilité. Ne lève pas d'exception.
    """
    from alphaforge.governance import evaluate   # import tardif : governance appelle ce module

    points: List[SweepPoint] = []
    for weight in weight_grid((idea or {}).get("target_weight")):
        candidate = copy.deepcopy(dict(idea))
        candidate["target_weight"] = weight
        try:
            simulated = simulate_fn(candidate)
        except Exception as error:  # la simulation relève d'un autre flux : on ne la fait pas échouer
            points.append((weight, None, f"simulation en erreur : {type(error).__name__}"))
            continue
        snapshot, reason = _snapshot_from(simulated)
        if snapshot is None:
            points.append((weight, None, reason))
            continue
        held = snapshot["weights"].get(idea.get("ticker"))
        if not isinstance(held, (int, float)) or abs(held - weight) > TOLERANCE:
            points.append((weight, None, "le poids simulé ne correspond pas au poids demandé"))
            continue
        try:
            points.append((weight, evaluate(profile, snapshot), None))
        except ValueError as error:
            points.append((weight, None, str(error)))
    return points


def _pick(statuses: Sequence[Tuple[float, Optional[str]]]) -> Optional[Counterfactual]:
    """Construit le contrefactuel à partir de `(poids, statut ou None)` triés par poids."""
    compliant = [w for w, status in statuses if status == "compliant"]
    best = max(compliant) if compliant else None
    unknown_above = any(status in (None, "missing_info") and (best is None or w > best)
                        for w, status in statuses)
    if not statuses or unknown_above:
        return None
    if best is None:
        return {"parameter": "target_weight", "compliant_at_or_below": None,
                "display_value": NO_SOLUTION_FR}
    return {"parameter": "target_weight", "compliant_at_or_below": best,
            "display_value": format_percent(best)}


def _rule_status(result: Optional[GovernanceResult], rule_id: str) -> Optional[str]:
    if result is None:
        return None
    for check in result["checks"]:
        if check["rule_id"] == rule_id:
            return check["status"]
    return None


def compute_counterfactuals(
    profile: InvestorProfile,
    idea: InvestmentIdea,
    simulate_fn: Optional[SimulateFn],
    rule_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Optional[Counterfactual]]:
    """Plus grand poids conforme, règle par règle (une seule série de simulations).

    Retourne `{rule_id: Counterfactual ou None}`. Tout est `None` si `simulate_fn` ou
    `idea` manque. `rule_ids` limite les règles (par défaut, toutes celles du profil).
    """
    wanted = list(rule_ids) if rule_ids is not None else [r["rule_id"] for r in profile.get("rules") or []]
    if simulate_fn is None or not isinstance(idea, Mapping) or not wanted:
        return {rule_id: None for rule_id in wanted}
    points = sweep(profile, idea, simulate_fn)
    return {
        rule_id: _pick([(w, _rule_status(result, rule_id)) for w, result, _ in points])
        for rule_id in wanted
    }


def largest_compliant_weight(
    profile: InvestorProfile, idea: InvestmentIdea, simulate_fn: Optional[SimulateFn],
) -> Optional[Counterfactual]:
    """Plus grand poids où TOUTES les règles du profil sont conformes (même grille).

    `missing_info` sur une règle empêche la conformité d'ensemble à ce poids.
    """
    if simulate_fn is None or not isinstance(idea, Mapping):
        return None
    points = sweep(profile, idea, simulate_fn)
    return _pick([(w, None if result is None else result["overall_status"]) for w, result, _ in points])
