"""Source du contrôle d'ancrage écrite en phrases françaises, tirée du seul dossier d'explication.

Pourquoi : le contrôle d'ancrage de Bedrock Guardrails compare des phrases françaises
(le texte de l'explicateur, renvois remplacés) à une source. Aujourd'hui, la source est
le dossier en JSON : clés anglaises (`warn_threshold`), codes de statut anglais
(`conflict`, `compliant`), nombres bruts (`0.17596769539961174`). Les faits y sont, mais
sous une forme qu'un modèle d'implication textuelle relie mal au texte : "conflit" et
"conforme" n'y apparaissent jamais, "seuil d'attention" s'y écrit `"warn_threshold": 0.2`.

Ce module réécrit le même dossier en phrases, de façon déterministe. Il n'ajoute aucun
fait et ne calcule rien : statuts, marges et contrefactuels viennent de la gouvernance
(flux B), valeurs affichées du registre de preuves (flux A), vocabulaire des statuts et
format des nombres de `explanation_rendering` (flux B). L'explicateur, lui, reçoit
toujours le dossier JSON : seule la source du contrôle change.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from alphaforge.explanation_rendering import STATUS_FR, format_percent, format_points
from alphaforge.governance import worst_status

FUNDING_FR = {
    "pro_rata": "au prorata des positions existantes",
    "from_ticker": "en vendant {ticker}",
}
REASON_FR = {
    "reduce_weight": "réduit le poids de l'idée",
    "change_funding_source": "change la source des fonds",
    "spread_across_existing": "répartit le financement sur les positions existantes",
}
RULE_STATE_FR = {
    "compliant": "est conforme",
    "tension": "est en tension",
    "conflict": "est en conflit",
    "missing_info": "n'a pas pu être vérifiée (information manquante)",
}
# Ce que signifie chaque statut, tel que la gouvernance le définit (seuil d'attention,
# puis limite du profil), pour une règle plafond ("max") et une règle plancher ("min").
STATUS_MEANING_FR = {
    ("max", "conflict"): "La mesure dépasse la limite fixée pour ce profil.",
    ("max", "tension"): "La mesure dépasse le seuil d'attention du profil, sans atteindre la limite.",
    ("max", "compliant"): "La mesure reste sous le seuil d'attention du profil.",
    ("min", "conflict"): "La mesure est sous la limite fixée pour ce profil.",
    ("min", "tension"): "La mesure est sous le seuil d'attention du profil, sans atteindre la limite.",
    ("min", "compliant"): "La mesure reste au-dessus du seuil d'attention du profil.",
}


def _pct(value: Optional[float]) -> Optional[str]:
    return None if value is None else format_percent(value)


def _idea_sentence(idea: Mapping[str, Any]) -> str:
    funding = FUNDING_FR.get(idea.get("funding_source"), "").format(ticker=idea.get("funding_ticker"))
    return (f"Idée simulée : ajouter {idea['ticker']} avec un poids cible de "
            f"{format_percent(idea['target_weight'])} du portefeuille, financé {funding}.")


def _threshold_sentence(rule: Mapping[str, Any], check: Mapping[str, Any]) -> Optional[str]:
    if check.get("unit") == "bool":
        return "Toute position dans cette catégorie met la règle en conflit."
    warn, limit = _pct(check.get("warn_threshold")), _pct(check.get("limit_threshold"))
    side = "en dessous" if rule.get("direction") == "min" else "au-delà"
    parts = []
    if warn:
        parts.append(f"seuil d'attention du profil de {warn} (tension {side})")
    if limit:
        parts.append(f"limite fixée pour ce profil de {limit} (conflit {side})")
    if not parts:
        return None
    return "Seuils (hypothèses de l'équipe) : " + ", ".join(parts) + "."


def _margin_sentence(check: Mapping[str, Any]) -> Optional[str]:
    """Marge calculée par la gouvernance : distance au seuil suivant, négative au-delà de la limite."""
    margin = check.get("margin")
    if margin is None or check.get("unit") != "pct":
        return None
    if check["status"] == "conflict":
        return f"La mesure est au-delà de la limite de {format_points(abs(margin))}."
    if check["status"] == "tension" or check.get("warn_threshold") is None:
        return f"Marge avant la limite : {format_points(margin)}."
    if check["status"] == "compliant":
        return f"Marge avant le seuil d'attention : {format_points(margin)}."
    return None


def _check_lines(check: Mapping[str, Any], rule: Mapping[str, Any],
                 evidence: Mapping[str, Mapping[str, Any]]) -> List[str]:
    status = check["status"]
    lines = [f"Contrôle {check['label_fr']} : {STATUS_FR[status]}. "
             f"La règle {check['label_fr']} {RULE_STATE_FR[status]}."]
    for evidence_id in check.get("evidence_ids") or []:
        entry = evidence.get(evidence_id)
        if entry and entry.get("display_value"):
            lines.append(f"Mesure pour la règle {check['label_fr']} : {entry['label_fr']}, "
                         f"{entry['display_value']}.")
    threshold = _threshold_sentence(rule, check)
    if threshold:
        lines.append(threshold)
    meaning = STATUS_MEANING_FR.get((rule.get("direction", "max"), status))
    if meaning and check.get("unit") != "bool":
        lines.append(meaning)
    if status == "missing_info" and check.get("missing_reason"):
        lines.append(f"Information manquante : {check['missing_reason']}")
    margin = _margin_sentence(check)
    if margin:
        lines.append(margin)
    counterfactual = check.get("counterfactual")
    if counterfactual:
        if counterfactual.get("compliant_at_or_below") is None:
            lines.append(f"Aucun poids testé pour l'idée ne respecte la règle {check['label_fr']}.")
        else:
            lines.append(f"Le plus grand poids testé pour l'idée qui respecte la règle {check['label_fr']} "
                         f"seule est {counterfactual['display_value']}.")
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


def build_grounding_source(brief: Mapping[str, Any]) -> str:
    """Le dossier d'explication en phrases françaises, pour la source du contrôle d'ancrage."""
    evidence: Dict[str, Mapping[str, Any]] = {e["evidence_id"]: e for e in brief.get("evidence", [])}
    rules = {rule["rule_id"]: rule for rule in brief.get("profile_rules", [])}
    checks = list(brief.get("checks", []))
    lines: List[str] = [
        "Dossier d'explication d'une simulation éducative. Le profil, le portefeuille et le capital sont fictifs. "
        "Les données décrivent le passé sur une période explicite.",
        _idea_sentence(brief["idea"]),
    ]
    if checks:
        lines.append(f"Verdict d'ensemble des règles du profil : {STATUS_FR[worst_status(c['status'] for c in checks)]}.")
    order = {f["check_id"]: f["rank"] for f in brief.get("ranked_factors", [])}
    for check in sorted(checks, key=lambda c: (order.get(c["check_id"], len(order) + 1), c["check_id"])):
        lines.extend(_check_lines(check, rules.get(check["rule_id"], {}), evidence))
    lines.append("Les seuils des règles sont des hypothèses de l'équipe, pas des normes.")
    for variant in brief.get("variants", []):
        reason = REASON_FR.get(variant.get("reason_code"), variant.get("reason_code", ""))
        measures = [evidence[e]["display_value"] for e in variant.get("evidence_ids", [])
                    if e in evidence and evidence[e].get("display_value")]
        sentence = (f"Variante simulée qui {reason} : verdict d'ensemble "
                    f"{STATUS_FR.get(variant.get('overall_status'), variant.get('overall_status'))}.")
        if measures:
            sentence += " Mesures de la variante : " + ", ".join(measures) + "."
        lines.append(sentence)
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
