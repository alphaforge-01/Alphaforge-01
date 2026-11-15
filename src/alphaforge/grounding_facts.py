"""Source du contrôle d'ancrage : le dossier d'explication réécrit en phrases de faits.

Le contrôle d'ancrage de Bedrock Guardrails vérifie que chaque affirmation du
texte de l'explicateur se retrouve dans une « source ». Envoyer le dossier en
JSON brut (identifiants, seuils en fractions comme 0.22 alors que le texte dit
« 22 % », structure imbriquée) rend ce rapprochement difficile.

Ce module produit une source en texte simple, une phrase par ligne :

- chaque preuve dit **de quoi** elle parle (portefeuille avant l'ajout, après
  l'ajout, variante simulée, actif), avec la **même valeur affichée** que celle
  que le code insère dans le texte (`display_value`) et sa période ;
- chaque contrôle de règle dit son statut, le sens de la règle (plafond ou
  plancher), la valeur, les seuils, la marge et le contrefactuel, dans les mots
  et les formats du texte rendu ;
- les définitions du glossaire et les limites sont reprises telles quelles, dans
  des sections séparées des faits (les seuils sont des hypothèses de l'équipe).

Le module ne calcule rien et n'invente rien : il reformule le dossier construit
par le code (flux B) à partir des preuves (flux A), avec les mêmes tables de
mots que le rendu et le gabarit. Les seules phrases de méthode ajoutées sont
vraies par construction du code (contrefactuel). Il est déterministe, testable
hors ligne et ne dépend pas d'AWS.

Usage (flux C) : `grounding_source_text(brief)` à la place de
`json.dumps(brief)` comme source dans `check_output_grounding`.
"""

from __future__ import annotations

from typing import Any, Mapping

from alphaforge.explanation_fallback import _ORDINALS, _REASON_PHRASES, VERDICT_FR
from alphaforge.explanation_rendering import STATUS_FR, format_percent, format_points
from alphaforge.governance import worst_status

MISSING_FR = "information manquante"
FUNDING_FR = {
    "pro_rata": "financement au prorata des positions existantes",
    "from_ticker": "financement par la vente de {funding}",
}
DIRECTION_FR = {
    "max": "plafond : la valeur doit rester sous les seuils",
    "min": "plancher : la valeur doit rester au-dessus des seuils",
}
SERIES_UNITS = {"pct", "cad", "days"}
COUNTERFACTUAL_STATUSES = ("tension", "conflict")

# Suffixes de périmètre ajoutés aux libellés par le pipeline (flux C) : retirés pour ne pas les doubler
SCOPE_SUFFIXES = (" (portefeuille avant l'ajout)", " (portefeuille après l'ajout)",
                  " (variante simulée)", " (simulation explorée)")


def subject_phrase(subject: str) -> str:
    """Ce dont parle une preuve, avec le vocabulaire des libellés du pipeline (flux C)."""
    if subject == "portfolio_before":
        return "du portefeuille avant l'ajout"
    if subject == "portfolio_after":
        return "du portefeuille après l'ajout"
    if subject.startswith("variant:"):
        return f"de la variante simulée {subject.split(':', 1)[1]}"
    if subject.startswith("explored:"):
        return f"de la simulation explorée par l'analyste ({subject.split(':', 1)[1]})"
    return f"de l'actif {subject}"


def _base_label(entry: Mapping[str, Any]) -> str:
    label = str(entry.get("label_fr") or entry.get("metric") or "Mesure")
    for suffix in SCOPE_SUFFIXES:
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _percent(value: Any) -> str | None:
    return format_percent(float(value)) if _is_number(value) else None


def fact_sentence(entry: Mapping[str, Any]) -> str:
    """Une preuve en une phrase : libellé, sujet, valeur affichée, période et devise."""
    metric = str(entry.get("metric") or "")
    subject = str(entry.get("subject", ""))
    about = ("entre le portefeuille avant l'ajout et le portefeuille après l'ajout"
             if metric.endswith("_delta") else subject_phrase(subject))
    shown = entry.get("display_value")
    value = MISSING_FR if shown is None or shown == "" else shown
    sentence = f"{_base_label(entry)} {about} : {value}"
    start, end, currency = entry.get("period_start"), entry.get("period_end"), entry.get("currency")
    if start and end and entry.get("unit") in SERIES_UNITS:
        sentence += f" (période du {start} au {end}" + (f", devise {currency})" if currency else ")")
    return sentence + "."


def check_sentence(check: Mapping[str, Any], idea_ticker: str | None = None,
                   direction: str | None = None) -> str:
    """Un contrôle de règle en une phrase, avec les mots du rendu affiché."""
    label = check.get("label_fr") or check.get("rule_id")
    status_code = str(check.get("status"))
    status = STATUS_FR.get(status_code, status_code)
    parts = [f"Contrôle {label} ({check.get('rule_id')}) : {status}"]
    if direction in DIRECTION_FR:
        parts.append(DIRECTION_FR[direction])
    # Les règles en pourcentage et les exclusions (unité "bool") portent des fractions de portefeuille
    if check.get("unit") in ("pct", "bool"):
        value, warn, limit = (_percent(check.get(k)) for k in ("value", "warn_threshold", "limit_threshold"))
        if value is not None:
            parts.append(f"valeur observée {value}")
        if warn is not None:
            parts.append(f"seuil d'attention {warn}")
        if limit is not None:
            parts.append(f"limite du profil {limit}")
        if _is_number(check.get("margin")):
            parts.append(f"marge {format_points(float(check['margin']))}")
    counterfactual = check.get("counterfactual") or {}
    if status_code in COUNTERFACTUAL_STATUSES and counterfactual:
        who = f" pour {idea_ticker}" if idea_ticker else ""
        if counterfactual.get("compliant_at_or_below") is None:
            parts.append(f"aucun poids testé{who} n'est conforme à cette règle")
        else:
            parts.append(f"le plus grand poids testé{who} conforme à cette règle seule est "
                         f"{counterfactual.get('display_value')} (balayage du seul poids de l'idée par pas "
                         "de 1 point ; les autres règles ne sont pas garanties)")
    if check.get("missing_reason"):
        parts.append(str(check["missing_reason"]).rstrip("."))
    return " ; ".join(parts) + "."


def idea_sentence(idea: Mapping[str, Any]) -> str:
    """L'idée simulée en une phrase (sans rien inventer si un champ manque)."""
    ticker = idea.get("ticker")
    target = _percent(idea.get("target_weight"))
    sentence = "Idée simulée (demande fictive)"
    if ticker and target:
        sentence += f" : porter {ticker} à {target} du portefeuille"
    elif ticker:
        sentence += f" sur {ticker}"
    funding = FUNDING_FR.get(str(idea.get("funding_source")))
    if funding and ("{funding}" not in funding or idea.get("funding_ticker")):
        sentence += ", " + funding.format(funding=idea.get("funding_ticker"))
    return sentence + "."


def variant_sentence(variant: Mapping[str, Any], position: int = 0) -> str:
    """Une variante simulée en une phrase, avec les mots du gabarit (novice et pro)."""
    ordinal = _ORDINALS[position] if 0 <= position < len(_ORDINALS) else "autre"
    reasons = _REASON_PHRASES.get(str(variant.get("reason_code")))
    status_code = str(variant.get("overall_status"))
    status = VERDICT_FR.get(status_code, status_code)
    sentence = f"Variante simulée {variant.get('variant_id')} ({ordinal} variante)"
    if reasons:
        sentence += f" : elle {reasons[0]} ({reasons[1]})"
    return sentence + f" ; verdict d'ensemble {status}."


def grounding_source_text(brief: Mapping[str, Any]) -> str:
    """Le dossier d'explication sous forme de phrases, une par ligne.

    Ordre : idée, verdict, contrôles, preuves, variantes ; puis, séparés des
    faits, les définitions du glossaire et les limites et hypothèses.
    """
    idea = brief.get("idea") or {}
    ticker = idea.get("ticker")
    checks = brief.get("checks") or []
    directions = {rule.get("rule_id"): rule.get("direction") for rule in brief.get("profile_rules") or []}
    target = f"l'idée simulée sur {ticker}" if ticker else "l'idée simulée"
    verdict_code = worst_status(c.get("status") for c in checks if c.get("status"))
    lines = ["Faits établis par le code pour cette analyse (simulation éducative sur un profil fictif).",
             idea_sentence(idea) if idea else "",
             f"Verdict d'ensemble (pire statut des règles évaluées) de {target} : "
             f"{VERDICT_FR.get(verdict_code, verdict_code)}."]
    lines += [check_sentence(check, ticker, directions.get(check.get("rule_id"))) for check in checks]
    lines += [fact_sentence(entry) for entry in brief.get("evidence") or []]
    lines += [variant_sentence(variant, i) for i, variant in enumerate(brief.get("variants") or [])]
    glossary = brief.get("glossary") or []
    if glossary:
        lines.append("Définitions du glossaire :")
        for term in glossary:
            line = f"{term.get('term')} : {str(term.get('definition', '')).rstrip('.')}."
            if term.get("analogy"):
                line += f" Image : {str(term['analogy']).rstrip('.')}."
            lines.append(line)
    limits = [str(limit.get("text", "")).strip() for limit in brief.get("limits") or []]
    if any(limits):
        lines.append("Limites et hypothèses (les seuils des règles sont des hypothèses de l'équipe) :")
        lines += limits
    return "\n".join(line for line in lines if line)
