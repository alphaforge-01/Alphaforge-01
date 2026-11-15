"""Rendu Markdown d'une explication (flux B, tâche B3).

`render_markdown(output, brief)` remplace les renvois du texte par les valeurs
vérifiables du dossier :
- `[E3]` : valeur affichée de la preuve (`display_value` du registre) ;
- `[G1]` : libellé de la règle et statut déterminé par la gouvernance, sauf si le texte
  dit déjà ce statut juste à côté du renvoi (voir `_status_already_stated`) : le statut
  n'est alors pas répété ;
- `[T2]` : terme du glossaire.

Il ajoute, sans aucun texte de modèle, les éléments factuels : idée simulée, contexte déclaré
du profil (`profile_context`, section absente si le dossier n'en a pas),
détail des contrôles (valeur, seuils, marge), poids de conformité du
contrefactuel, limites, preuves citées avec source, période, devise et
transformation, glossaire des termes cités, et les avertissements fixes par niveau
(`reference/fixed_texts.json`). Les limites obligatoires (`reference/limits.json`)
sont toujours affichées, même si le dossier ne les contient pas.
Un renvoi inconnu n'est jamais deviné : il est signalé dans le texte.

`render_sections(output, brief)` rend les mêmes éléments sous forme structurée (`RenderedSections`),
pour qu'une interface présente chaque section à sa façon (cartes, onglets, tableaux). Il utilise les
mêmes fonctions que `render_markdown` : mêmes remplacements de renvois, mêmes valeurs, mêmes limites
et avertissements, sans aucun texte ni chiffre de plus. Les avertissements fixes y sont fournis une
seule fois, séparés des limites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

from alphaforge.contracts import ExplainerOutput, ExplanationBrief
from alphaforge.explanation_validator import has_unsafe_markup
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
# Longueur minimale des mots qui nomment déjà une règle juste avant son renvoi (écarte "la", "des").
MIN_NAMED_CHARS = 4
FUNDING_FR = {"pro_rata": "au prorata des positions existantes"}
MISSING_FR = "information manquante"
NOT_DEFINED_FR = "non défini"


@dataclass(frozen=True)
class FactorSection:
    """Un facteur du verdict : texte rendu, et règle citée si le facteur en désigne une."""
    check_id: Optional[str]
    text: str
    label: Optional[str]      # libellé de la règle dans le dossier, sinon None
    status: Optional[str]     # statut de la gouvernance (compliant, tension, conflict, missing_info)


@dataclass(frozen=True)
class CounterfactualItem:
    check_id: str
    label: str
    bound: Optional[float]    # None : aucun poids testé n'est conforme
    text: str                 # phrase après "<libellé> : ", identique à celle du Markdown


@dataclass(frozen=True)
class CheckRow:
    """Une ligne du détail des contrôles, textes déjà formatés. Rien n'est recalculé."""
    check_id: str
    label: str
    status: str
    status_fr: str
    rule_text: str            # "R1 (type, sens)", utile au niveau pro
    value_text: str
    warn_text: str
    limit_text: str
    margin_text: str
    evidence_ids: Tuple[str, ...]


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    label: str
    value_text: str
    details: Tuple[str, ...]  # période, devise, sources, transformation, et détails du niveau pro


@dataclass(frozen=True)
class GlossaryItem:
    term: str
    definition: str
    analogy: Optional[str]    # seulement au niveau novice


@dataclass(frozen=True)
class ProfileContextSection:
    notice: str
    items: Tuple[Tuple[str, str], ...]   # (libellé, valeur) recopiés du dossier


@dataclass(frozen=True)
class RenderedSections:
    """Une explication découpée en sections. Un champ vide ou None signifie "rien à afficher"."""
    level: str
    origin: Optional[str]                      # "llm" (agent) ou "template" (gabarit de secours)
    disclaimers: Tuple[Tuple[str, str], ...]   # (warning_id, texte), fixes par niveau, une seule fois
    idea_line: Optional[str]
    profile_context: Optional[ProfileContextSection]
    summary: str
    factors: Tuple[FactorSection, ...]
    counterfactual: str
    counterfactual_items: Tuple[CounterfactualItem, ...]
    variants: str
    check_rows: Tuple[CheckRow, ...]
    check_notes: Tuple[Tuple[str, str], ...]   # (libellé, raison) des règles à information manquante
    threshold_notice: Optional[str]
    limits_context: str
    limits: Tuple[Tuple[str, str], ...]        # (limit_id, texte), limites obligatoires d'abord
    evidence: Tuple[EvidenceItem, ...]
    glossary: Tuple[GlossaryItem, ...]


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
        """Remplace les renvois par ce que lit l'utilisateur, sans répéter ce que le texte dit déjà.

        - le statut d'un `[G..]` n'est pas répété s'il est déjà dit à côté ;
        - si le texte vient de nommer la règle ("la volatilité [G2]", "la règle de concentration
          par actif [G1]"), ces mots deviennent le libellé en gras au lieu d'être suivis du libellé ;
        - un terme du glossaire placé en fin de proposition devient "(voir **Terme**)".
        """
        text = text or ""
        pieces: List[str] = []
        cursor = 0
        for match in REFERENCE_PATTERN.finditer(text):
            ref = match.group(1)
            before = text[cursor:match.start()]
            check = self.checks.get(ref) if ref[0] == "G" else None
            if check is not None:
                stated = _status_already_stated(text, match.start(), match.end(), check["status"])
                named = _named_just_before(before, check["label_fr"])
                if named:
                    # Le texte nomme déjà la règle : on met ses mots en gras, complétés par le libellé exact.
                    label = check["label_fr"]
                    if before[len(before.rstrip()) - named].islower():
                        label = label[0].lower() + label[1:]
                    kept = before.rstrip()[:-named]
                    status = "" if stated else f" ({STATUS_FR[check['status']]})"
                    pieces.append(f"{kept}**{label}**{status}")
                else:
                    pieces.append(before + self.resolve(ref, show_status=not stated))
            elif ref[0] == "T" and ref in self.glossary and _ends_clause(text, match.end()) \
                    and not before.lower().rstrip().endswith("voir"):
                pieces.append(f"{before.rstrip()} (voir {self.resolve(ref)})")
            else:
                pieces.append(before + self.resolve(ref))
            cursor = match.end()
        pieces.append(text[cursor:])
        return "".join(pieces)


def _named_just_before(before: str, label: str) -> int:
    """Nombre de caractères, à la fin de `before`, qui nomment déjà la règle `label` (0 sinon).

    Reconnaît le libellé entier ("concentration par actif") ou son début d'au moins un mot long
    ("volatilité" pour "Volatilité annuelle"), sans tenir compte des accents ni de la casse, et
    seulement juste avant le renvoi. Un mot court ou un mot différent ne compte pas.
    """
    folded = before.rstrip().lower().translate(_FOLD)
    words = label.lower().translate(_FOLD).split()
    for count in range(len(words), 0, -1):
        prefix = " ".join(words[:count])
        if len(prefix) < MIN_NAMED_CHARS or not folded.endswith(prefix):
            continue
        cut = len(folded) - len(prefix)
        if cut == 0 or not folded[cut - 1].isalnum():   # début de mot, pas la fin d'un autre mot
            return len(prefix)
    return 0


def _ends_clause(text: str, end: int) -> bool:
    """Vrai si rien ne suit le renvoi dans sa proposition (fin du texte ou ponctuation)."""
    rest = text[end:].lstrip()
    return not rest or rest[0] in ".,;:!?)"


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


def _check_rows(brief: Mapping[str, Any], level: str, reg: _Registry) -> List[CheckRow]:
    """Lignes du détail des contrôles. Marque les preuves des contrôles comme citées."""
    rules = {r["rule_id"]: r for r in brief.get("profile_rules") or []}
    rows: List[CheckRow] = []
    for check in brief.get("checks") or []:
        unit = check.get("unit", "pct")
        warn = check.get("warn_threshold")
        limit = check.get("limit_threshold")
        margin = check.get("margin")
        rule = rules.get(check.get("rule_id"), {})
        for evidence_id in check.get("evidence_ids") or []:
            reg._remember(reg.cited_evidence, evidence_id)
        rows.append(CheckRow(
            check_id=check["check_id"],
            label=check["label_fr"],
            status=check["status"],
            status_fr=STATUS_FR[check["status"]],
            rule_text=f"{check.get('rule_id', '?')} ({check.get('rule_type', '?')}, {rule.get('direction', '?')})",
            value_text=_format_value(check.get("value"), unit),
            warn_text=_format_value(warn, unit) if warn is not None else NOT_DEFINED_FR,
            limit_text=_format_value(limit, unit) if limit is not None else NOT_DEFINED_FR,
            margin_text=format_points(margin) if _is_number(margin) else NOT_DEFINED_FR,
            evidence_ids=tuple(check.get("evidence_ids") or []),
        ))
    return rows


def _check_notes(brief: Mapping[str, Any], reg: _Registry) -> List[Tuple[str, str]]:
    """(libellé, raison) des règles à information manquante qui donnent une raison."""
    return [(reg.checks[c["check_id"]]["label_fr"], c["missing_reason"]) for c in brief.get("checks") or []
            if c["status"] == "missing_info" and c.get("missing_reason")]


def _threshold_notice(brief: Mapping[str, Any], level: str) -> Optional[str]:
    """Phrase fixe sur les seuils, seulement si une règle du profil est une hypothèse."""
    if any(r.get("is_assumption") for r in brief.get("profile_rules") or []):
        return threshold_assumption(level)
    return None


def _details_table(brief: Mapping[str, Any], level: str, reg: _Registry) -> List[str]:
    rows = _check_rows(brief, level, reg)
    if not rows:
        return []
    lines: List[str] = []
    if level == "pro":
        lines += ["| Contrôle | Règle | Statut | Valeur | Seuil d'avertissement | Limite | Marge | Preuves |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    else:
        # Le seuil d'attention explique un statut "en tension" : sans lui, une mesure sous la limite
        # affichée "en tension" paraît contradictoire.
        lines += ["| Règle | Statut | Mesure | Seuil d'attention | Limite du profil |",
                  "| --- | --- | --- | --- | --- |"]
    for row in rows:
        if level == "pro":
            evidence_text = ", ".join(row.evidence_ids) or "aucune"
            lines.append(f"| {row.check_id} | {_cell(row.rule_text)} | {row.status_fr} | {row.value_text} "
                         f"| {row.warn_text} | {row.limit_text} | {row.margin_text} | {evidence_text} |")
        else:
            lines.append(f"| {_cell(row.label)} | {row.status_fr} | {row.value_text} | {row.warn_text} "
                         f"| {row.limit_text} |")
    notes = _check_notes(brief, reg)
    if notes:
        lines.append("")
        for label, reason in notes:
            lines.append(f"- {label} : {reason}")
    notice = _threshold_notice(brief, level)
    if notice:
        lines += ["", notice]
    return lines


def _counterfactual_items(brief: Mapping[str, Any]) -> List[CounterfactualItem]:
    """Contrefactuels calculés par la gouvernance, pour les règles en tension ou en conflit."""
    items = []
    for check in brief.get("checks") or []:
        cf = check.get("counterfactual")
        if not cf or check["status"] not in ("tension", "conflict"):
            continue
        bound = cf.get("compliant_at_or_below")
        if bound is None:
            text = "aucun poids testé n'est conforme à cette règle."
        else:
            shown = cf.get("display_value") or format_percent(bound)
            text = f"le plus grand poids testé conforme à cette règle est {shown}."
        items.append(CounterfactualItem(check["check_id"], check["label_fr"], bound, text))
    return items


def _counterfactual_lines(brief: Mapping[str, Any]) -> List[str]:
    return [f"- {item.label} : {item.text}" for item in _counterfactual_items(brief)]


def _evidence_items(brief: Mapping[str, Any], level: str, reg: _Registry) -> List[EvidenceItem]:
    items = []
    for evidence_id in sorted(reg.cited_evidence, key=lambda i: (len(i), i)):
        entry = reg.evidence.get(evidence_id)
        if entry is None:
            continue
        shown = entry.get("display_value") if entry.get("value") is not None else MISSING_FR
        details: List[str] = []
        if entry.get("period_start") and entry.get("period_end"):
            details.append(f"période {entry['period_start']} au {entry['period_end']}")
        if entry.get("currency"):
            details.append(f"devise {entry['currency']}")
        if entry.get("source_ids"):
            details.append("sources " + ", ".join(entry["source_ids"]))
        if entry.get("transformation"):
            details.append(f"transformation : {entry['transformation']}")
        if level == "pro":
            details.append(f"outil {entry.get('tool_name', '?')}, clé {entry.get('evidence_key', '?')}")
            if entry.get("n_observations") is not None:
                details.append(f"{entry['n_observations']} observations")
            if entry.get("as_of"):
                details.append(f"à la date {entry['as_of']}")
            if entry.get("limit_ids"):
                details.append("limites " + ", ".join(entry["limit_ids"]))
        items.append(EvidenceItem(evidence_id, entry.get("label_fr", ""), shown or MISSING_FR, tuple(details)))
    return items


def _evidence_lines(brief: Mapping[str, Any], level: str, reg: _Registry) -> List[str]:
    return ["- " + "; ".join([f"**{item.evidence_id}** : {item.label} = {item.value_text}", *item.details]) + "."
            for item in _evidence_items(brief, level, reg)]


def _glossary_items(reg: _Registry, level: str) -> List[GlossaryItem]:
    terms = [reg.glossary[t] for t in sorted(reg.cited_terms, key=lambda i: (len(i), i))]
    return [GlossaryItem(
        term=entry["term"],
        definition=str(entry.get("definition", "")).rstrip("."),
        analogy=str(entry["analogy"]).rstrip(".") if level == "novice" and entry.get("analogy") else None,
    ) for entry in terms]


PROFILE_CONTEXT_TITLE = "## Contexte déclaré du profil fictif"
PROFILE_CONTEXT_NOTICE = {
    "novice": "Ce que le profil fictif déclare, recopié tel quel. Ce n'est ni une conclusion de l'analyse "
              "ni une recommandation.",
    "pro": "Champ `profile_context` du dossier, recopié sans interprétation : valeurs déclarées du profil "
           "fictif, ni conclusion de l'analyse ni recommandation.",
}


def _years(value: int) -> str:
    return f"{value} an" if value <= 1 else f"{value} ans"


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.isprintable()


def _profile_context_pairs(brief: Mapping[str, Any], level: str) -> List[Tuple[str, str]]:
    """(libellé, valeur) du contexte déclaré du profil, écrits par le code d'après `profile_context`.

    Montre seulement ce que le dossier contient : objectif, horizon, tolérance au risque,
    préférence ESG, cryptoactifs. Une clé absente ou invalide n'est pas rendue.
    L'expérience et l'identité ne sont pas rendues. Aucun chiffre n'est calculé : l'horizon
    est celui du profil. Le texte de l'objectif repasse le filtre des liens et balises.
    """
    context = brief.get("profile_context")
    if not isinstance(context, Mapping):
        return []
    items: List[Tuple[str, str]] = []
    objective = context.get("objective")
    if _is_text(objective) and not has_unsafe_markup(objective):
        items.append(("Objectif", objective.strip().rstrip(".")))
    low, high = context.get("horizon_years_min"), context.get("horizon_years_max")
    if all(isinstance(v, int) and not isinstance(v, bool) for v in (low, high)) and 0 <= low <= high:
        horizon = _years(high) if low == high else f"de {low} à {_years(high)}"
        items.append(("Horizon d'investissement", horizon))
    for key, label in (("risk_tolerance", "Tolérance au risque"), ("esg_preference", "Préférence ESG")):
        text = context.get(f"{key}_fr")
        if _is_text(text):
            raw = context.get(key)
            suffix = f" (`{raw}`)" if level == "pro" and _is_text(raw) else ""
            items.append((label, f"{text.strip()}{suffix}"))
    if isinstance(context.get("crypto_allowed"), bool):
        items.append(("Cryptoactifs", "permis" if context["crypto_allowed"] else "non permis"))
    return items


def _profile_context_lines(brief: Mapping[str, Any], level: str) -> List[str]:
    """Section "Contexte déclaré du profil fictif" en Markdown. Sans contexte exploitable : aucune ligne."""
    pairs = _profile_context_pairs(brief, level)
    if not pairs:
        return []
    return [PROFILE_CONTEXT_TITLE, "", PROFILE_CONTEXT_NOTICE["pro" if level == "pro" else "novice"], "",
            *[f"- {label} : {value}." for label, value in pairs], ""]


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
    out += _profile_context_lines(brief, level)

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

    terms = _glossary_items(reg, level)
    if terms:
        out += ["## Glossaire", ""]
        for entry in terms:
            line = f"- **{entry.term}** : {entry.definition}."
            if entry.analogy:
                line += f" Image : {entry.analogy}."
            out.append(line)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def render_sections(output: ExplainerOutput, brief: ExplanationBrief) -> RenderedSections:
    """Rend une explication en sections structurées, avec les mêmes valeurs que `render_markdown`.

    Les renvois `[E..]`, `[G..]`, `[T..]` sont remplacés comme dans `render_markdown`. Chaque section
    est une donnée déjà calculée et validée du dossier : rien n'est ajouté, deviné ou recalculé. Les
    avertissements fixes du niveau (`disclaimers`) sont donnés une fois, séparés des limites. Fonctionne
    pour une sortie de gabarit comme pour une sortie de modèle (`origin` les distingue). Les emplacements
    absents donnent des valeurs vides. Ne modifie ni `output` ni `brief`.
    """
    level = output.get("level") or brief.get("level") or "novice"
    reg = _Registry(brief)
    sub = reg.substitute

    pairs = _profile_context_pairs(brief, level)
    profile_context = ProfileContextSection(
        notice=PROFILE_CONTEXT_NOTICE["pro" if level == "pro" else "novice"], items=tuple(pairs),
    ) if pairs else None

    # Même ordre que render_markdown : les preuves citées sont recensées dans l'ordre de lecture.
    summary = sub(output["summary"]) if output.get("summary") else ""
    factors = []
    for factor in output.get("factors") or []:
        check = reg.checks.get(factor.get("check_id"))
        factors.append(FactorSection(
            check_id=factor.get("check_id"),
            text=sub(factor.get("text", "")),
            label=check["label_fr"] if check else None,
            status=check["status"] if check else None,
        ))
    counterfactual = sub(output["counterfactual"]) if output.get("counterfactual") else ""
    variants = sub(output["variants"]) if output.get("variants") else ""
    check_rows = _check_rows(brief, level, reg)
    check_notes = _check_notes(brief, reg) if check_rows else []
    limits_context = sub(output["limits_context"]) if output.get("limits_context") else ""
    limits = merge_mandatory_limits(brief.get("limits") or [], level)
    evidence = _evidence_items(brief, level, reg)

    return RenderedSections(
        level=level,
        origin=output.get("origin"),
        disclaimers=tuple((item["warning_id"], item["text"]) for item in disclaimers(level)),
        idea_line=_idea_line(brief["idea"]) if brief.get("idea") else None,
        profile_context=profile_context,
        summary=summary,
        factors=tuple(factors),
        counterfactual=counterfactual,
        counterfactual_items=tuple(_counterfactual_items(brief)) if counterfactual else (),
        variants=variants,
        check_rows=tuple(check_rows),
        check_notes=tuple(check_notes),
        threshold_notice=_threshold_notice(brief, level) if check_rows else None,
        limits_context=limits_context,
        limits=tuple((item["limit_id"], item["text"]) for item in limits),
        evidence=tuple(evidence),
        glossary=tuple(_glossary_items(reg, level)),
    )
