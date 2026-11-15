"""Source du contrôle d'ancrage écrite en phrases françaises, tirée du seul dossier d'explication.

Pourquoi : le contrôle d'ancrage de Bedrock Guardrails compare des phrases françaises
(le texte de l'explicateur, renvois remplacés) à une source. Aujourd'hui, la source est
le dossier en JSON : clés anglaises (`warn_threshold`), codes de statut anglais
(`conflict`, `compliant`), nombres bruts (`0.17596769539961174`). Les faits y sont, mais
sous une forme qu'un modèle d'implication textuelle relie mal au texte : "conflit" et
"conforme" n'y apparaissent jamais, "seuil d'attention" s'y écrit `"warn_threshold": 0.2`.

Ce module réécrit le même dossier en phrases, de façon déterministe, sans ajouter de
fait : statuts, marges et contrefactuels viennent de la gouvernance (flux B), valeurs
affichées du registre de preuves (flux A), vocabulaire des statuts et format des nombres
de `explanation_rendering` (flux B), avertissements des textes fixes du flux B. Le seul
calcul est le verdict d'ensemble, le pire statut, avec `governance.worst_status`.
L'explicateur, lui, reçoit toujours le dossier JSON : seule la source du contrôle change.

Les phrases suivent les conventions de la gouvernance : une valeur égale à un seuil ne le
franchit pas, et la marge est la distance au seuil suivant, négative au-delà de la limite.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from alphaforge.explanation_rendering import FUNDING_FR, STATUS_FR, format_percent, format_points
from alphaforge.governance import worst_status
from alphaforge.reference_texts import disclaimers

# Mêmes phrases que le gabarit (explanation_fallback._REASON_PHRASES, niveau novice).
REASON_FR = {
    "reduce_weight": "réduit la part de l'idée",
    "change_funding_source": "change l'origine des fonds",
    "spread_across_existing": "répartit l'idée sur des placements déjà détenus",
}
RULE_STATE_FR = {
    "compliant": "est conforme",
    "tension": "est en tension",
    "conflict": "est en conflit",
    "missing_info": "n'a pas pu être vérifiée (information manquante)",
}
# Seuls ces types de règle ont un sens "toute position exclue" (valeur booléenne).
EXCLUSION_RULES = ("excluded_asset_class",)


def _pct(value: Optional[float]) -> Optional[str]:
    return None if value is None else format_percent(value)


def _idea_sentence(idea: Mapping[str, Any]) -> str:
    """Même formulation que l'idée affichée (`explanation_rendering._idea_line`)."""
    if idea.get("funding_source") == "from_ticker" and idea.get("funding_ticker"):
        funding = f"financé par {idea['funding_ticker']}"
    else:
        funding = f"financé {FUNDING_FR.get(idea.get('funding_source'), 'selon la source choisie')}"
    weight = idea.get("target_weight")
    weight_text = f" avec un poids cible de {format_percent(weight)} du portefeuille" if weight is not None else ""
    return f"Idée simulée : ajouter {idea.get('ticker', '?')}{weight_text}, {funding}."


def _threshold_sentence(rule: Mapping[str, Any], check: Mapping[str, Any]) -> Optional[str]:
    """Seuils de la règle, seulement s'ils existent et si leur sens est connu."""
    if check.get("unit") == "bool":
        if check.get("rule_type") in EXCLUSION_RULES:
            return (f"Toute position dans la catégorie exclue par la règle {check['label_fr']} "
                    "met cette règle en conflit.")
        return None
    if check.get("unit") != "pct" or rule.get("direction") not in ("max", "min"):
        return None
    warn, limit = _pct(check.get("warn_threshold")), _pct(check.get("limit_threshold"))
    side = "en dessous" if rule["direction"] == "min" else "au-delà"
    parts = []
    if warn:
        parts.append(f"seuil d'attention du profil de {warn} (tension {side})")
    if limit:
        parts.append(f"limite fixée pour ce profil de {limit} (conflit {side})")
    if not parts:
        return None
    prefix = "Seuils (hypothèses de l'équipe) : " if rule.get("is_assumption") else "Seuils : "
    return prefix + ", ".join(parts) + "."


def _meaning_sentence(rule: Mapping[str, Any], check: Mapping[str, Any]) -> Optional[str]:
    """Ce que dit le statut, d'après les seuils présents. Égalité à un seuil : non franchi."""
    direction, status = rule.get("direction"), check["status"]
    if check.get("unit") != "pct" or direction not in ("max", "min"):
        return None
    has_warn = check.get("warn_threshold") is not None
    has_limit = check.get("limit_threshold") is not None
    crossed, not_crossed = (("dépasse", "ne dépasse pas") if direction == "max"
                            else ("descend sous", "ne descend pas sous"))
    if status == "conflict" and has_limit:
        return f"La mesure {crossed} la limite fixée pour ce profil."
    if status == "tension" and has_warn:
        rest = (f", sans {'dépasser' if direction == 'max' else 'descendre sous'} la limite"
                if has_limit else "")
        return f"La mesure {crossed} le seuil d'attention du profil{rest}."
    if status == "compliant":
        if has_warn:
            return f"La mesure {not_crossed} le seuil d'attention du profil."
        if has_limit:
            return f"La mesure {not_crossed} la limite fixée pour ce profil."
    return None


def _margin_sentence(rule: Mapping[str, Any], check: Mapping[str, Any]) -> Optional[str]:
    """Marge de la gouvernance : distance au seuil suivant, négative au-delà de la limite."""
    margin, direction = check.get("margin"), rule.get("direction")
    if margin is None or check.get("unit") != "pct" or direction not in ("max", "min"):
        return None
    if check["status"] == "conflict":
        side = "au-dessus de" if direction == "max" else "sous"
        return f"La mesure est {side} la limite de {format_points(abs(margin))}."
    if check["status"] == "tension":
        return f"Marge avant la limite : {format_points(margin)}."
    if check["status"] == "compliant":
        target = "le seuil d'attention" if check.get("warn_threshold") is not None else "la limite"
        return f"Marge avant {target} : {format_points(margin)}."
    return None


def _check_lines(check: Mapping[str, Any], rule: Mapping[str, Any],
                 evidence: Mapping[str, Mapping[str, Any]]) -> List[str]:
    status, label = check["status"], check["label_fr"]
    lines = [f"Contrôle {label} : {STATUS_FR[status]}. La règle {label} {RULE_STATE_FR[status]}."]
    for evidence_id in check.get("evidence_ids") or []:
        entry = evidence.get(evidence_id)
        if entry and entry.get("display_value"):
            lines.append(f"Mesure pour la règle {label} : {entry['label_fr']}, {entry['display_value']}.")
    for sentence in (_threshold_sentence(rule, check), _meaning_sentence(rule, check)):
        if sentence:
            lines.append(sentence)
    if status == "missing_info" and check.get("missing_reason"):
        lines.append(f"Information manquante : {check['missing_reason']}")
    margin = _margin_sentence(rule, check)
    if margin:
        lines.append(margin)
    counterfactual = check.get("counterfactual")
    if counterfactual:
        if counterfactual.get("compliant_at_or_below") is None:
            lines.append(f"Aucun poids testé pour l'idée ne rend la règle {label} conforme.")
        else:
            lines.append(f"Le plus grand poids testé pour l'idée qui rend la règle {label} conforme, "
                         f"à elle seule, est {counterfactual['display_value']}.")
    return lines


def _evidence_lines(entry: Mapping[str, Any]) -> List[str]:
    if not entry.get("display_value"):
        return [f"{entry['label_fr']} : information non disponible."]
    lines = [f"{entry['label_fr']} : {entry['display_value']}."]
    if entry.get("period_start") and entry.get("period_end"):
        currency = f", en {entry['currency']}" if entry.get("currency") else ""
        lines.append(f"Période observée dans le passé : du {entry['period_start']} au {entry['period_end']}{currency}.")
    if entry.get("transformation"):
        lines.append(f"Calcul : {entry['transformation']}")
    return lines


def _variant_sentence(variant: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]) -> str:
    reason = REASON_FR.get(variant.get("reason_code"), "modifie l'idée")
    status = variant.get("overall_status")
    sentence = f"Variante simulée qui {reason} : verdict d'ensemble {STATUS_FR.get(status, status)}."
    measures = [f"{evidence[e]['label_fr']} : {evidence[e]['display_value']}"
                for e in variant.get("evidence_ids", [])
                if e in evidence and evidence[e].get("display_value")]
    if measures:
        sentence += " Mesures de cette variante : " + " ; ".join(measures) + "."
    return sentence


def build_grounding_source(brief: Mapping[str, Any]) -> str:
    """Le dossier d'explication en phrases françaises, pour la source du contrôle d'ancrage."""
    evidence: Dict[str, Mapping[str, Any]] = {e["evidence_id"]: e for e in brief.get("evidence", [])}
    rules = {rule["rule_id"]: rule for rule in brief.get("profile_rules", [])}
    checks = list(brief.get("checks", []))
    lines: List[str] = [item["text"] for item in disclaimers(brief.get("level", "novice"))]
    lines.append(_idea_sentence(brief["idea"]))
    if checks:
        lines.append(f"Verdict d'ensemble des règles du profil : {STATUS_FR[worst_status(c['status'] for c in checks)]}.")
    order = {f["check_id"]: f["rank"] for f in brief.get("ranked_factors", [])}
    for check in sorted(checks, key=lambda c: (order.get(c["check_id"], len(order) + 1), c["check_id"])):
        lines.extend(_check_lines(check, rules.get(check["rule_id"], {}), evidence))
    if any(rule.get("is_assumption") for rule in rules.values()):
        lines.append("Les seuils des règles sont des hypothèses de l'équipe, pas des normes.")
    lines.extend(_variant_sentence(variant, evidence) for variant in brief.get("variants", []))
    for entry in brief.get("evidence", []):
        lines.extend(_evidence_lines(entry))
    for limit in brief.get("limits", []):
        lines.append(f"Limite : {limit.get('text', '')}")
    for term in brief.get("glossary", []):
        sentence = f"{term['term']} : {term['definition']}."
        if term.get("analogy"):
            sentence += f" Analogie : {term['analogy']}."
        lines.append(sentence)
    return "\n".join(line for line in lines if line)
