"""Profils investisseurs fictifs (flux B, tâche B1).

Deux entrées :
- `load_personas()` : les trois personas (Amira, Mateo, Robert) et leur
  portefeuille fictif, lus dans `data/external/investor_profiles.json`.
- `build_profile_from_answers(answers)` : profil "custom" construit à partir de
  cases et de curseurs, sans texte libre.

Tous les seuils de risque sont des HYPOTHESES DE L'EQUIPE (`is_assumption=True`).
Ils ne sont ni des normes ni des conseils. Les pourcentages sont des fractions
(0.25 = 25 %). Le module ne lit aucune donnée de marché et n'appelle pas AWS.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alphaforge.contracts import InvestorProfile, Level, Rule

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PERSONAS_PATH = PROJECT_ROOT / "data" / "external" / "investor_profiles.json"

ASSUMPTION_NOTICE_FR = (
    "Les seuils de risque sont des hypothèses de l'équipe AlphaForge, "
    "réglables, et non des normes ni des conseils personnalisés."
)

RISK_TOLERANCES = ("low", "low_moderate", "moderate", "high")
EXPERIENCES = ("beginner", "intermediate", "advanced")
ESG_PREFERENCES = ("none", "moderate", "strong")

# Hypothèses de l'équipe : seuils (avertissement, limite) par tolérance au risque.
# Pour une règle "max", la tension commence au-delà de `warn` et le conflit
# au-delà de `limit`. Pour une règle "min", c'est en dessous.
VOLATILITY_THRESHOLDS = {
    "low": (0.10, 0.15),
    "low_moderate": (0.16, 0.25),
    "moderate": (0.22, 0.32),
    "high": (0.30, 0.45),
}
DRAWDOWN_THRESHOLDS = {
    "low": (0.12, 0.20),
    "low_moderate": (0.20, 0.35),
    "moderate": (0.30, 0.50),
    "high": (0.40, 0.65),
}
MIN_DEFENSIVE_THRESHOLDS = {
    "low": (0.60, 0.45),
    "low_moderate": (0.40, 0.30),
    "moderate": (0.25, 0.15),
    "high": (0.05, 0.0),
}
EQUITY_CLASS_THRESHOLDS = {
    "low": (0.50, 0.65),
    "low_moderate": (0.65, 0.80),
    "moderate": (0.70, 0.85),
    "high": (0.70, 0.85),
}
CRYPTO_CLASS_THRESHOLDS = {  # utilisé seulement si les cryptoactifs sont permis
    "low": (0.02, 0.05),
    "low_moderate": (0.05, 0.10),
    "moderate": (0.10, 0.20),
    "high": (0.20, 0.35),
}
# Plafond par titre : valeur par défaut si l'utilisateur n'en donne pas.
DEFAULT_SINGLE_ASSET_CAP = {
    "low": 0.10,
    "low_moderate": 0.20,
    "moderate": 0.25,
    "high": 0.35,
}
SINGLE_ASSET_LIMIT_MARGIN = 0.05   # limite = plafond + 5 points
CAP_CONTRADICTION_MARGIN = 0.10    # plafond jugé incohérent au-delà de défaut + 10 points

REQUIRED_ANSWERS = (
    "objective", "horizon_years_min", "horizon_years_max", "risk_tolerance",
    "experience", "esg_preference", "crypto_allowed", "capital_cad",
)
OPTIONAL_ANSWERS = ("max_single_asset_weight",)


class ProfileValidationError(ValueError):
    """Réponses invalides ou incomplètes. `issues` contient le détail."""

    def __init__(self, issues: List[Dict[str, Any]]):
        self.issues = issues
        messages = "; ".join(i["message_fr"] for i in issues if i["severity"] == "error")
        super().__init__(messages)


def _issue(code: str, severity: str, fields: List[str], message_fr: str) -> Dict[str, Any]:
    return {"code": code, "severity": severity, "fields": fields, "message_fr": message_fr}


def load_personas() -> Dict[str, Dict[str, Any]]:
    """Charge les trois personas fictifs, indexés par `profile_id`.

    Chaque entrée contient : `profile` (InvestorProfile), `portfolio` (Portfolio),
    `age`, `occupation_fr` et `summary_fr` (pour les cartes de l'interface).
    Retourne une copie profonde : l'appelant peut la modifier sans effet de bord.
    """
    raw = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(raw["personas"])


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_answers(answers: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Contrôle du profil : champs manquants, valeurs invalides, contradictions.

    Retourne une liste de problèmes `{code, severity, fields, message_fr}` :
    - "error" : champ manquant ou invalide, la construction est refusée ;
    - "warning" : contradiction, le profil reste construit mais elle est signalée ;
    - "info" : point à connaître, sans incohérence.
    """
    if not isinstance(answers, dict):
        return [_issue("answers_not_dict", "error", [], "Les réponses doivent être un dictionnaire.")]

    issues: List[Dict[str, Any]] = []
    for key in REQUIRED_ANSWERS:
        if answers.get(key) is None:
            issues.append(_issue("missing_field", "error", [key], f"Champ obligatoire manquant : {key}."))
    unknown = sorted(set(answers) - set(REQUIRED_ANSWERS) - set(OPTIONAL_ANSWERS))
    for key in unknown:
        issues.append(_issue("unknown_field", "error", [key], f"Champ non pris en charge : {key}."))
    if any(i["severity"] == "error" for i in issues):
        return issues

    for key, allowed in (("risk_tolerance", RISK_TOLERANCES), ("experience", EXPERIENCES),
                         ("esg_preference", ESG_PREFERENCES)):
        if answers[key] not in allowed:
            issues.append(_issue("invalid_value", "error", [key],
                                 f"Valeur invalide pour {key} : choisir parmi {', '.join(allowed)}."))
    if not isinstance(answers["objective"], str) or not answers["objective"].strip():
        issues.append(_issue("invalid_value", "error", ["objective"], "L'objectif doit être un texte non vide."))
    if not isinstance(answers["crypto_allowed"], bool):
        issues.append(_issue("invalid_value", "error", ["crypto_allowed"], "crypto_allowed doit être vrai ou faux."))
    for key in ("horizon_years_min", "horizon_years_max"):
        value = answers[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            issues.append(_issue("invalid_value", "error", [key], f"{key} doit être un entier positif ou nul."))
    if not _is_number(answers["capital_cad"]) or answers["capital_cad"] <= 0:
        issues.append(_issue("invalid_value", "error", ["capital_cad"], "Le capital fictif doit être supérieur à 0."))
    cap = answers.get("max_single_asset_weight")
    if cap is not None and (not _is_number(cap) or not 0 < cap <= 1):
        issues.append(_issue("invalid_value", "error", ["max_single_asset_weight"],
                             "Le plafond par titre doit être une fraction entre 0 (exclu) et 1."))
    if any(i["severity"] == "error" for i in issues):
        return issues
    if answers["horizon_years_min"] > answers["horizon_years_max"]:
        return [_issue("horizon_inverted", "error", ["horizon_years_min", "horizon_years_max"],
                       "L'horizon minimum dépasse l'horizon maximum.")]

    issues.extend(_contradictions(answers))
    return issues


def _contradictions(answers: Dict[str, Any]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    risk = answers["risk_tolerance"]
    cap = answers.get("max_single_asset_weight")

    if risk in ("low", "low_moderate") and answers["crypto_allowed"]:
        found.append(_issue(
            "crypto_vs_low_risk", "warning", ["risk_tolerance", "crypto_allowed"],
            "Tolérance au risque faible ou faible à modérée, mais cryptoactifs permis : "
            "vérifier que c'est voulu."))
    if cap is not None and cap > DEFAULT_SINGLE_ASSET_CAP[risk] + CAP_CONTRADICTION_MARGIN:
        found.append(_issue(
            "single_cap_vs_risk", "warning", ["risk_tolerance", "max_single_asset_weight"],
            "Le plafond par titre est nettement plus élevé que l'hypothèse de l'équipe "
            "pour cette tolérance au risque."))
    if risk == "high" and answers["horizon_years_max"] < 5:
        found.append(_issue(
            "short_horizon_vs_high_risk", "warning", ["risk_tolerance", "horizon_years_max"],
            "Tolérance au risque élevée, mais horizon de moins de 5 ans : "
            "une perte importante aurait peu de temps pour se résorber."))
    if risk == "high" and answers["experience"] == "beginner":
        found.append(_issue(
            "beginner_vs_high_risk", "warning", ["risk_tolerance", "experience"],
            "Tolérance au risque élevée avec une expérience débutante : "
            "vérifier que les pertes possibles sont bien comprises."))
    if answers["esg_preference"] != "none":
        found.append(_issue(
            "esg_not_evaluated", "info", ["esg_preference"],
            "La préférence ESG est enregistrée, mais aucune règle ESG n'est évaluée "
            "dans cette version du prototype."))
    if cap is None:
        found.append(_issue(
            "default_single_cap_used", "info", ["max_single_asset_weight"],
            "Aucun plafond par titre indiqué : l'hypothèse de l'équipe pour cette "
            "tolérance au risque est utilisée."))
    return found


def _rule(rule_id: str, rule_type: str, params: Dict[str, Any], direction: str,
          warn: Optional[float], limit: Optional[float], unit: str, label_fr: str) -> Rule:
    return {
        "rule_id": rule_id, "rule_type": rule_type, "params": params,  # type: ignore[typeddict-item]
        "direction": direction, "warn_threshold": warn, "limit_threshold": limit,  # type: ignore[typeddict-item]
        "unit": unit, "label_fr": label_fr, "origin": "checkbox",  # type: ignore[typeddict-item]
        "is_assumption": True,
    }


def _build_rules(answers: Dict[str, Any]) -> List[Rule]:
    risk = answers["risk_tolerance"]
    cap = answers.get("max_single_asset_weight")
    if cap is None:
        cap = DEFAULT_SINGLE_ASSET_CAP[risk]
    single: Tuple[float, float] = (float(cap), round(min(1.0, cap + SINGLE_ASSET_LIMIT_MARGIN), 4))

    rules = [
        _rule("R1", "max_single_asset_weight", {}, "max", single[0], single[1], "pct",
              "Concentration par actif"),
        _rule("R2", "max_portfolio_volatility", {}, "max", *VOLATILITY_THRESHOLDS[risk], "pct",
              "Volatilité annuelle"),
        _rule("R3", "max_portfolio_drawdown", {}, "max", *DRAWDOWN_THRESHOLDS[risk], "pct",
              "Perte maximale historique"),
        _rule("R4", "min_defensive_share", {}, "min", *MIN_DEFENSIVE_THRESHOLDS[risk], "pct",
              "Part défensive minimale"),
    ]
    if answers["crypto_allowed"]:
        rules.append(_rule("R5", "max_asset_class_weight", {"asset_class": "crypto"}, "max",
                           *CRYPTO_CLASS_THRESHOLDS[risk], "pct", "Concentration en cryptoactifs"))
    else:
        rules.append(_rule("R5", "excluded_asset_class", {"asset_class": "crypto"}, "max",
                           None, 0.0, "bool", "Cryptoactifs exclus"))
    rules.append(_rule("R6", "max_asset_class_weight", {"asset_class": "equity"}, "max",
                       *EQUITY_CLASS_THRESHOLDS[risk], "pct", "Concentration par catégorie"))
    return rules


def build_profile_from_answers(answers: Dict[str, Any]) -> InvestorProfile:
    """Construit un profil fictif "custom" à partir de réponses par cases.

    Champs obligatoires : objective, horizon_years_min, horizon_years_max,
    risk_tolerance, experience, esg_preference, crypto_allowed, capital_cad.
    Champ facultatif : max_single_asset_weight (fraction).

    Lève `ProfileValidationError` si un champ est manquant ou invalide. Les
    contradictions ne bloquent pas : les obtenir avec `check_answers(answers)`.
    Le niveau par défaut suit l'expérience : débutant vers "novice", sinon "pro".
    """
    issues = check_answers(answers)
    if any(i["severity"] == "error" for i in issues):
        raise ProfileValidationError(issues)

    level: Level = "novice" if answers["experience"] == "beginner" else "pro"
    return {
        "profile_id": "custom",
        "display_name": "Profil fictif",
        "is_fictional": True,
        "objective": answers["objective"].strip(),
        "horizon_years_min": answers["horizon_years_min"],
        "horizon_years_max": answers["horizon_years_max"],
        "risk_tolerance": answers["risk_tolerance"],
        "experience": answers["experience"],
        "esg_preference": answers["esg_preference"],
        "crypto_allowed": answers["crypto_allowed"],
        "capital_cad": float(answers["capital_cad"]),
        "default_level": level,
        "rules": _build_rules(answers),
    }
