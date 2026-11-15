"""Dossier d'explication (flux B, tâche B4).

`build_brief(result, level)` transforme un `AnalysisResult` en `ExplanationBrief`,
seule entrée de l'explicateur (agent ou gabarit). Le dossier est construit par le
code, sans modèle, et ne contient que ce qui a été calculé :

- `checks` : contrôles de gouvernance de `governance_after`, avec leurs preuves ;
- `ranked_factors` : contrôles non conformes classés par gravité, puis par marge ;
- `evidence` : preuves du registre réellement utilisées, copiées telles quelles ;
- `limits` : limites obligatoires du catalogue `reference/limits.json` (toujours
  présentes, texte fixe du niveau), puis les limites du résultat ;
- `glossary` : termes fermés du glossaire utiles aux règles présentes, au niveau ;
- `variants` : motif (code fermé), statut global et preuves de chaque variante ;
- `profile_context` (facultatif) : objectif, horizon, tolérance au risque, expérience, préférence
  ESG et cryptoactifs du profil fictif, copiés du profil sans rien déduire.

Ne rien inventer : une preuve ou une limite référencée mais absente du registre
est une erreur (`ValueError`), jamais une valeur par défaut. Le texte libre de
l'utilisateur (`unsupported_requests`) et l'identité du profil n'entrent pas dans
le dossier. Le contrefactuel (B5) et le validateur (B6) ne sont pas ici.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from alphaforge.contracts import AnalysisResult, ExplanationBrief, Level, ProfileContext, check_keys
from alphaforge.explanation_validator import has_unsafe_markup
from alphaforge.governance import STATUS_SEVERITY, rule_metric
from alphaforge.reference_texts import merge_mandatory_limits, mandatory_limits

LEVELS = ("novice", "pro")
MAX_CHARS_PER_SLOT = 400
MAX_OBJECTIVE_CHARS = 120

# Traduction des valeurs fermées du profil (`contracts.InvestorProfile`). Aucune interprétation :
# "faible à modérée" dit seulement `low_moderate`. Une valeur hors table n'a pas de libellé et
# n'est pas transmise.
RISK_TOLERANCE_FR = {"low": "faible", "low_moderate": "faible à modérée", "moderate": "modérée", "high": "élevée"}
EXPERIENCE_FR = {"beginner": "débutant", "intermediate": "intermédiaire", "advanced": "avancé"}
ESG_PREFERENCE_FR = {"none": "aucune", "moderate": "modérée", "strong": "forte"}
GLOSSARY_PATH = Path(__file__).resolve().parent / "reference" / "glossary.json"


def _numeric_key(identifier: str):
    """Ordre naturel : E2 avant E10."""
    digits = "".join(ch for ch in identifier if ch.isdigit())
    return (identifier[:1], int(digits) if digits else 0, identifier)


def _margin_key(check: Mapping[str, Any]):
    margin = check.get("margin")
    return (margin is None, margin if margin is not None else 0.0)


def rank_checks(checks: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Classe les contrôles non conformes : gravité décroissante, puis marge croissante.

    La marge la plus petite (ou la plus négative) vient d'abord : c'est le point le
    plus proche du changement de statut ou le plus dépassé. Marge absente : en
    dernier dans son statut. Égalité : ordre des contrôles (`G2` avant `G10`).
    """
    flagged = [c for c in checks if c["status"] != "compliant"]
    flagged.sort(key=lambda c: (-STATUS_SEVERITY[c["status"]], _margin_key(c),
                                _numeric_key(c["check_id"])))
    return [
        {"rank": position, "check_id": c["check_id"], "status": c["status"],
         "evidence_ids": list(c.get("evidence_ids") or [])}
        for position, c in enumerate(flagged, start=1)
    ]


def load_glossary(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lit le glossaire fermé. Fichier absent : liste vide (rien n'est inventé)."""
    target = path or GLOSSARY_PATH
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        terms = data["terms"]
        for term in terms:
            for key in ("term_id", "term", "rule_types", "novice", "pro"):
                term[key]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"Glossaire invalide : {target.name} ({error!r})") from error
    return terms


def _glossary_for(rule_types: Sequence[str], level: str,
                  catalog: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    wanted = set(rule_types)
    entries = []
    for term in sorted(catalog, key=lambda t: _numeric_key(t["term_id"])):
        if wanted & set(term["rule_types"]):
            texts = term[level]
            entries.append({
                "term_id": term["term_id"],
                "term": term["term"],
                "definition": texts["definition"],
                "analogy": texts.get("analogy", ""),
            })
    return entries


def _limits_for(result: Mapping[str, Any], level: str, evidence: Sequence[Mapping[str, Any]]):
    """Limites du dossier : catalogue obligatoire d'abord, puis limites du résultat."""
    catalog = {item["limit_id"]: item for item in result.get("limits") or []}
    mandatory_ids = {item["limit_id"] for item in mandatory_limits(level)}
    needed = {lid for entry in evidence for lid in entry.get("limit_ids") or []}
    unknown = sorted(needed - set(catalog) - mandatory_ids, key=_numeric_key)
    if unknown:
        raise ValueError("Limite obligatoire absente du résultat : " + ", ".join(unknown))
    field = "text_novice" if level == "novice" else "text_pro"
    limits = []
    for limit_id in sorted(catalog, key=_numeric_key):
        text = catalog[limit_id].get(field)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Texte de limite manquant pour {limit_id} ({field}).")
        limits.append({"limit_id": limit_id, "text": text})
    return merge_mandatory_limits(limits, level)


def _registry(result: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    registry = result.get("evidence")
    if not isinstance(registry, Mapping):
        raise ValueError("Le registre de preuves du résultat doit être un dictionnaire.")
    return registry


def _link_evidence(check: Mapping[str, Any], subject: str,
                   registry: Mapping[str, Mapping[str, Any]],
                   rules: Optional[Mapping[str, Mapping[str, Any]]] = None) -> List[str]:
    """Preuves d'un contrôle : celles de la gouvernance, sinon par métrique et sujet.

    `rules` (règles du profil par `rule_id`) fournit la classe d'actifs des règles R5 et R6 :
    la preuve cherchée est alors `weight_by_asset_class.<classe>` du même sujet. Sans règle
    ou sans preuve correspondante, la liste reste vide (rien n'est deviné).
    """
    ids = list(check.get("evidence_ids") or [])
    if not ids:
        params = (rules or {}).get(check.get("rule_id"), {}).get("params")
        metric = rule_metric(check["rule_type"], params)
        if metric is not None:
            ids = [eid for eid, entry in registry.items()
                   if entry.get("metric") == metric and entry.get("subject") == subject]
    unknown = [eid for eid in ids if eid not in registry]
    if unknown:
        raise ValueError(f"Preuve introuvable dans le registre pour {check['check_id']} : "
                         + ", ".join(unknown))
    return sorted(set(ids), key=_numeric_key)


def _variant_entries(result: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]],
                     rules: Optional[Mapping[str, Mapping[str, Any]]] = None):
    entries = []
    for variant in result.get("variants") or []:
        governance = variant["governance"]
        ids: List[str] = []
        for check in governance["checks"]:
            ids.extend(_link_evidence(check, governance["subject"], registry, rules))
        entries.append({
            "variant_id": variant["variant_id"],
            "reason_code": variant["reason_code"],
            "overall_status": governance["overall_status"],
            "evidence_ids": sorted(set(ids), key=_numeric_key),
        })
    return entries


def _fingerprint(content: Mapping[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "brief-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _safe_objective(value: Any) -> Optional[str]:
    """Objectif du profil s'il est un texte court d'une ligne, sans lien ni balise ; sinon `None`.

    C'est le seul texte libre du profil que lit l'explicateur : il est borné et filtré, jamais réécrit.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > MAX_OBJECTIVE_CHARS or not text.isprintable() or has_unsafe_markup(text):
        return None
    return text


def build_profile_context(profile: Mapping[str, Any]) -> Optional[ProfileContext]:
    """Contexte du profil pour l'explicateur : seulement ce que le profil contient, sinon rien.

    Chaque clé est copiée du profil si sa valeur est valide ; une valeur absente ou invalide
    omet la clé (rien n'est déduit ni complété). Ni nom, ni capital, ni règles (déjà dans
    `profile_rules`), ni seuil. Rend `None` si aucune clé n'est exploitable.
    """
    if not isinstance(profile, Mapping):
        return None
    context: Dict[str, Any] = {}
    objective = _safe_objective(profile.get("objective"))
    if objective is not None:
        context["objective"] = objective
    low, high = profile.get("horizon_years_min"), profile.get("horizon_years_max")
    if _is_int(low) and _is_int(high) and 0 <= low <= high:
        context["horizon_years_min"], context["horizon_years_max"] = low, high
    for key, labels in (("risk_tolerance", RISK_TOLERANCE_FR), ("experience", EXPERIENCE_FR),
                        ("esg_preference", ESG_PREFERENCE_FR)):
        value = profile.get(key)
        if isinstance(value, str) and value in labels:
            context[key], context[f"{key}_fr"] = value, labels[value]
    if isinstance(profile.get("crypto_allowed"), bool):
        context["crypto_allowed"] = profile["crypto_allowed"]
    return context or None  # type: ignore[return-value]


def build_brief(result: AnalysisResult, level: Level,
                glossary_catalog: Optional[Sequence[Mapping[str, Any]]] = None) -> ExplanationBrief:
    """Construit le dossier d'explication d'un `AnalysisResult` pour un niveau.

    `glossary_catalog` (facultatif) remplace le glossaire fermé du dépôt, utile en test.
    Lève `ValueError` si le niveau est inconnu, si le résultat est incomplet ou
    incohérent (preuve ou limite référencée mais absente). Ne modifie pas `result`.
    """
    if level not in LEVELS:
        raise ValueError(f"Niveau inconnu : {level!r}. Valeurs permises : {', '.join(LEVELS)}.")
    missing = check_keys(result, AnalysisResult)
    if missing:
        raise ValueError("Résultat d'analyse incomplet : " + ", ".join(missing))

    governance = result["governance_after"]
    if governance["profile_id"] != result["profile"]["profile_id"]:
        raise ValueError("La gouvernance et le profil du résultat ne correspondent pas.")

    registry = _registry(result)
    rules = {rule["rule_id"]: rule for rule in result["profile"]["rules"]}
    checks = []
    for check in governance["checks"]:
        item = copy.deepcopy(check)
        item["evidence_ids"] = _link_evidence(check, governance["subject"], registry, rules)
        checks.append(item)

    variants = _variant_entries(result, registry, rules)

    # Preuves utilisées : contrôles, variantes, puis mises en avant par l'analyste.
    used = {eid for c in checks for eid in c["evidence_ids"]}
    used |= {eid for v in variants for eid in v["evidence_ids"]}
    highlights = list((result.get("submission") or {}).get("highlight_evidence_ids") or [])
    unknown = [eid for eid in highlights if eid not in registry]
    if unknown:
        raise ValueError("Preuve mise en avant introuvable dans le registre : " + ", ".join(unknown))
    used |= set(highlights)
    evidence = []
    for eid in sorted(used, key=_numeric_key):
        if registry[eid].get("evidence_id") != eid:
            raise ValueError(f"Identifiant de preuve incohérent dans le registre : {eid}")
        evidence.append(copy.deepcopy(registry[eid]))

    catalog = load_glossary() if glossary_catalog is None else list(glossary_catalog)
    glossary = _glossary_for(sorted({c["rule_type"] for c in checks}), level, catalog)

    content: Dict[str, Any] = {
        "run_id": result["run_id"],
        "level": level,
        "profile_rules": copy.deepcopy(result["profile"]["rules"]),
        "idea": copy.deepcopy(result["idea"]),
        "ranked_factors": rank_checks(checks),
        "checks": checks,
        "variants": variants,
        "evidence": evidence,
        "limits": _limits_for(result, level, evidence),
        "glossary": glossary,
        "max_chars_per_slot": MAX_CHARS_PER_SLOT,
    }
    profile_context = build_profile_context(result["profile"])
    if profile_context is not None:
        content["profile_context"] = profile_context
    brief: Dict[str, Any] = {"brief_id": _fingerprint(content)}
    brief.update(content)
    return brief  # type: ignore[return-value]
