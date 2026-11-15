"""Rendu Markdown d'une explication (flux B, tâche B3).

`render_markdown(output, brief)` remplace les renvois du texte par les valeurs
vérifiables du dossier :
- `[E3]` : valeur affichée de la preuve (`display_value` du registre) ;
- `[G1]` : libellé de la règle et statut déterminé par la gouvernance, sauf si le texte
  dit déjà ce statut juste à côté du renvoi (voir `_status_already_stated`) : le statut
  n'est alors pas répété ;
- `[T2]` : terme du glossaire.

Il ajoute, sans aucun texte de modèle, les éléments factuels : idée simulée,
détail des contrôles (valeur, seuils, marge), poids de conformité du
contrefactuel, limites, preuves citées avec source, période, devise et
transformation, glossaire des termes cités, et les avertissements fixes par niveau
(`reference/fixed_texts.json`). Les limites obligatoires (`reference/limits.json`)
sont toujours affichées, même si le dossier ne les contient pas.
Un renvoi inconnu n'est jamais deviné : il est signalé dans le texte.
"""
from __future__ import annotations

import re
from typing import Any, List, Mapping, Optional

from alphaforge.contracts import ExplainerOutput, ExplanationBrief
from alphaforge.reference_texts import (
    disclaimers, merge_mandatory_limits, threshold_assumption,
)

REFERENCE_PATTERN = re.compile(r"\[([EGT]\d+)\]")

STATUS_FR = {
    "compliant": "conforme",
    "tension": "en tension",
    "conflict": "en conflit",
    "missing_info": "information manquante",
}
# Façons de dire chaque statut dans un texte (comparaison sans accents ni casse). "non conforme"
# et "pas conforme" ne comptent pas comme "conforme". Un statut n'est jamais retiré à cause du
# mot d'un autre statut : seul le statut propre à la règle citée compte.
_STATUS_WORDS = {
    "compliant": re.compile(r"(?<!non )(?<!pas )\bconform\w*"),
    "tension": re.compile(r"\btensions?\b"),
    "conflict": re.compile(r"\bconflits?\b"),
    "missing_info": re.compile(r"\binformations? manquantes?\b|\bmanque d'information"),
}
_FOLD = str.maketrans("éèêëàâäîïôöùûüç’", "eeeeaaaiioouuuc'")
_SENTENCE_END = ".;!?\n"
STATUS_WINDOW_BEFORE = 30
STATUS_WINDOW_AFTER = 50
FUNDING_FR = {"pro_rata": "au prorata des positions existantes"}
MISSING_FR = "information manquante"
NOT_DEFINED_FR = "non défini"


def format_percent(value: float) -> str:
    """Fraction vers pourcentage français : 0.4125 devient "41,25 %"."""
    number = f"{round(value * 100, 2):.2f}".rstrip("0").rstrip(".")
    if number in ("-0", ""):
        number = "0"
    return number.replace(".", ",") + " %"


def format_points(value: float) -> str:
    """Écart en points de pourcentage : -0.03 devient "-3 pts"."""
    number = f"{round(value * 100, 2):.2f}".rstrip("0").rstrip(".")
    if number in ("-0", ""):
        number = "0"
    return number.replace(".", ",") + " pts"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_value(value: Optional[float], unit: str) -> str:
    if not _is_number(value):
        return MISSING_FR
    if unit in ("pct", "bool"):
        return format_percent(value)
    return f"{value:g}".replace(".", ",")


def _cell(text: Any) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


class _Registry:
    """Accès en lecture au dossier : preuves, contrôles, glossaire."""

    def __init__(self, brief: Mapping[str, Any]):
        self.evidence = {e["evidence_id"]: e for e in brief.get("evidence") or []}
        self.checks = {c["check_id"]: c for c in brief.get("checks") or []}
        self.glossary = {g["term_id"]: g for g in brief.get("glossary") or []}
        self.cited_evidence: List[str] = []
        self.cited_terms: List[str] = []

    def _remember(self, bucket: List[str], key: str) -> None:
        if key not in bucket:
            bucket.append(key)

    def resolve(self, ref: str, show_status: bool = True) -> str:
        kind = ref[0]
        if kind == "E" and ref in self.evidence:
            entry = self.evidence[ref]
            self._remember(self.cited_evidence, ref)
            shown = entry.get("display_value")
            if entry.get("value") is None or not shown:
                return MISSING_FR
            return str(shown)
        if kind == "G" and ref in self.checks:
            check = self.checks[ref]
            if not show_status:
                return f"**{check['label_fr']}**"
            return f"**{check['label_fr']}** ({STATUS_FR[check['status']]})"
        if kind == "T" and ref in self.glossary:
            self._remember(self.cited_terms, ref)
            return f"**{self.glossary[ref]['term']}**"
        return f"[référence inconnue : {ref}]"

    def substitute(self, text: str) -> str:
        """Remplace les renvois ; le statut d'un `[G..]` n'est pas répété s'il est déjà dit à côté."""
        text = text or ""

        def replace(match: "re.Match[str]") -> str:
            ref = match.group(1)
            check = self.checks.get(ref) if ref[0] == "G" else None
            if check is not None and _status_already_stated(text, match.start(), match.end(), check["status"]):
                return self.resolve(ref, show_status=False)
            return self.resolve(ref)

        return REFERENCE_PATTERN.sub(replace, text)


def _status_already_stated(text: str, start: int, end: int, status: str) -> bool:
    """Vrai si le texte dit déjà `status` tout près du renvoi `[G..]` situé entre `start` et `end`.

    On regarde seulement le voisinage immédiat : quelques mots avant et après le renvoi, sans
    franchir la fin de la phrase ni un autre renvoi. Ainsi "[G1] et [G2] sont en conflit" ne
    retire pas le statut de [G1], dont le voisinage ne le dit pas.
    """
    pattern = _STATUS_WORDS.get(status)
    if pattern is None:
        return False
    folded = text.lower().translate(_FOLD)
    before = folded[max(0, start - STATUS_WINDOW_BEFORE):start]
    after = folded[end:end + STATUS_WINDOW_AFTER]
    last = max(before.rfind(ch) for ch in _SENTENCE_END + "]")
    before = before[last + 1:]
    cut = [after.find(ch) for ch in _SENTENCE_END + "[" if after.find(ch) >= 0]
    if cut:
        after = after[:min(cut)]
    return bool(pattern.search(before) or pattern.search(after))


def _idea_line(idea: Mapping[str, Any]) -> str:
    weight = idea.get("target_weight")
    funding = idea.get("funding_source")
    if funding == "from_ticker" and idea.get("funding_ticker"):
        source = f"financé par « {idea['funding_ticker']} »"
    else:
        source = f"financé {FUNDING_FR.get(funding, 'selon la source choisie')}"
    return f"Idée simulée : « {idea.get('ticker', '?')} », poids cible {_format_value(weight, 'pct')}, {source}."


def _details_table(brief: Mapping[str, Any], level: str, reg: _Registry) -> List[str]:
    checks = brief.get("checks") or []
    if not checks:
        return []
    rules = {r["rule_id"]: r for r in brief.get("profile_rules") or []}
    lines: List[str] = []
    if level == "pro":
        lines += ["| Contrôle | Règle | Statut | Valeur | Seuil d'avertissement | Limite | Marge | Preuves |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    else:
        lines += ["| Règle | Statut | Mesure | Limite du profil |", "| --- | --- | --- | --- |"]
    for check in checks:
        unit = check.get("unit", "pct")
        value = _format_value(check.get("value"), unit)
        warn = check.get("warn_threshold")
        limit = check.get("limit_threshold")
        warn_text = _format_value(warn, unit) if warn is not None else NOT_DEFINED_FR
        limit_text = _format_value(limit, unit) if limit is not None else NOT_DEFINED_FR
        status = STATUS_FR[check["status"]]
        for evidence_id in check.get("evidence_ids") or []:
            reg._remember(reg.cited_evidence, evidence_id)
        if level == "pro":
            margin = check.get("margin")
            margin_text = format_points(margin) if _is_number(margin) else NOT_DEFINED_FR
            rule = rules.get(check.get("rule_id"), {})
            rule_text = f"{check.get('rule_id', '?')} ({check.get('rule_type', '?')}, {rule.get('direction', '?')})"
            evidence_text = ", ".join(check.get("evidence_ids") or []) or "aucune"
            lines.append(f"| {check['check_id']} | {_cell(rule_text)} | {status} | {value} | {warn_text} "
                         f"| {limit_text} | {margin_text} | {evidence_text} |")
        else:
            lines.append(f"| {_cell(check['label_fr'])} | {status} | {value} | {limit_text} |")
    reasons = [(c["check_id"], c.get("missing_reason")) for c in checks
               if c["status"] == "missing_info" and c.get("missing_reason")]
    if reasons:
        lines.append("")
        for check_id, reason in reasons:
            label = reg.checks[check_id]["label_fr"]
            lines.append(f"- {label} : {reason}")
    if any(r.get("is_assumption") for r in rules.values()):
        lines += ["", threshold_assumption(level)]
    return lines


def _counterfactual_lines(brief: Mapping[str, Any]) -> List[str]:
    lines = []
    for check in brief.get("checks") or []:
        cf = check.get("counterfactual")
        if not cf or check["status"] not in ("tension", "conflict"):
            continue
        bound = cf.get("compliant_at_or_below")
        if bound is None:
            lines.append(f"- {check['label_fr']} : aucun poids testé n'est conforme à cette règle.")
        else:
            shown = cf.get("display_value") or format_percent(bound)
            lines.append(f"- {check['label_fr']} : le plus grand poids testé conforme à cette règle est {shown}.")
    return lines


def _evidence_lines(brief: Mapping[str, Any], level: str, reg: _Registry) -> List[str]:
    lines = []
    for evidence_id in sorted(reg.cited_evidence, key=lambda i: (len(i), i)):
        entry = reg.evidence.get(evidence_id)
        if entry is None:
            continue
        shown = entry.get("display_value") if entry.get("value") is not None else MISSING_FR
        parts = [f"**{evidence_id}** : {entry.get('label_fr', '')} = {shown or MISSING_FR}"]
        if entry.get("period_start") and entry.get("period_end"):
            parts.append(f"période {entry['period_start']} au {entry['period_end']}")
        if entry.get("currency"):
            parts.append(f"devise {entry['currency']}")
        if entry.get("source_ids"):
            parts.append("sources " + ", ".join(entry["source_ids"]))
        if entry.get("transformation"):
            parts.append(f"transformation : {entry['transformation']}")
        if level == "pro":
            parts.append(f"outil {entry.get('tool_name', '?')}, clé {entry.get('evidence_key', '?')}")
            if entry.get("n_observations") is not None:
                parts.append(f"{entry['n_observations']} observations")
            if entry.get("as_of"):
                parts.append(f"à la date {entry['as_of']}")
            if entry.get("limit_ids"):
                parts.append("limites " + ", ".join(entry["limit_ids"]))
        lines.append("- " + "; ".join(parts) + ".")
    return lines


def render_markdown(output: ExplainerOutput, brief: ExplanationBrief) -> str:
    """Rend une explication en Markdown, renvois remplacés par les valeurs du dossier.

    Fonctionne pour une sortie de gabarit comme pour une sortie de modèle. Les
    emplacements absents sont ignorés. Ne modifie ni `output` ni `brief`.
    """
    level = output.get("level") or brief.get("level") or "novice"
    reg = _Registry(brief)
    sub = reg.substitute
    out: List[str] = [f"# Explication ({'niveau pro' if level == 'pro' else 'niveau novice'})", "",
                      "> **Avertissement**"]
    out += [f"> - {item['text']}" for item in disclaimers(level)]
    out.append("")
    if brief.get("idea"):
        out += [_idea_line(brief["idea"]), ""]

    if output.get("summary"):
        out += ["## Résumé", "", sub(output["summary"]), ""]

    factors = output.get("factors") or []
    if factors:
        out += ["## Ce qui pèse dans le verdict", ""]
        out += [f"{n}. {sub(f.get('text', ''))}" for n, f in enumerate(factors, start=1)]
        out.append("")

    if output.get("counterfactual"):
        out += ["## Ce qui ferait changer le verdict", "", sub(output["counterfactual"])]
        cf_lines = _counterfactual_lines(brief)
        if cf_lines:
            out += [""] + cf_lines
        out.append("")

    if output.get("variants"):
        out += ["## Variantes simulées", "", sub(output["variants"]), ""]

    table = _details_table(brief, level, reg)
    if table:
        out += ["## Détail des contrôles", ""] + table + [""]

    limits = merge_mandatory_limits(brief.get("limits") or [], level)
    if output.get("limits_context") or limits:
        out += ["## Limites", ""]
        if output.get("limits_context"):
            out += [sub(output["limits_context"]), ""]
        out += [f"- **{item['limit_id']}** : {item['text']}" for item in limits]
        out.append("")

    evidence_lines = _evidence_lines(brief, level, reg)
    if evidence_lines:
        out += ["## Preuves citées", ""] + evidence_lines + [""]

    terms = [reg.glossary[t] for t in sorted(reg.cited_terms, key=lambda i: (len(i), i))]
    if terms:
        out += ["## Glossaire", ""]
        for entry in terms:
            line = f"- **{entry['term']}** : {str(entry.get('definition', '')).rstrip('.')}."
            if level == "novice" and entry.get("analogy"):
                line += f" Image : {str(entry['analogy']).rstrip('.')}."
            out.append(line)
        out.append("")

    return "\n".join(out).rstrip() + "\n"
