"""Réponse du code de l'agent conversationnel (issue 78), sans modèle ni appel AWS.

`build_fallback_reply(brief)` rédige une réponse courte et déterministe à partir du seul dossier de
conversation (`ConversationBrief`), pour chaque type de question (`answer_kind`) et chaque niveau
(novice, pro). Elle suit les mêmes règles que le modèle : des renvois [E#] [G#] [T#] que le code remplace
par les valeurs du registre, aucun chiffre en clair, aucun conseil, ordre ni prédiction, le statut exact de
chaque règle citée, et ce qui manque dit comme tel. La question de l'utilisateur n'est jamais recopiée.

Chaque phrase n'est gardée que si la réponse reste valide pour `explanation_validator.validate_reply` :
une phrase qui ferait rejeter la réponse (libellé inattendu, par exemple) est écartée. Sans aucun fait
citable, la réponse dit que l'information n'est pas disponible dans ce prototype.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .contracts import ConversationReply
from .explanation_validator import REPLY_MAX_SENTENCES, validate_reply

# Ordre de lecture des faits déclarés du profil (sujet "profile", outil get_profile_facts).
PROFILE_METRICS = ("profile_objective", "profile_horizon", "profile_risk_tolerance", "profile_experience",
                   "profile_esg_preference", "profile_crypto_allowed")
# Mesures du portefeuille fictif lues pour une question de radiographie, dans cet ordre.
XRAY_METRICS = ("volatility_ann", "max_drawdown", "top_asset_weight", "defensive_share")
# Portefeuille fictif actuel d'abord : la radiographie décrit le portefeuille avant toute idée.
XRAY_SUBJECTS = ("portfolio_before", "portfolio_after")
SCOPE_SUFFIXES = (" (portefeuille avant l'ajout)", " (portefeuille après l'ajout)")
SEVERITY = {"conflict": 0, "tension": 1, "missing_info": 2, "compliant": 3}

STATUS_PHRASE = {
    "compliant": "est conforme",
    "tension": "est en tension",
    "conflict": "est en conflit",
    "missing_info": "reste en information manquante",
}
STATUS_SHORT = {
    "compliant": "conforme",
    "tension": "en tension",
    "conflict": "en conflit",
    "missing_info": "information manquante",
}
# Nom simple de chaque règle du profil, affiché à la place du nom technique (niveau novice).
NOVICE_RULE_LABELS = {
    "max_single_asset_weight": "Pas trop d'argent sur un seul placement",
    "max_asset_class_weight": "Pas trop d'argent sur un même type de placement",
    "max_portfolio_volatility": "Des hauts et des bas de valeur limités",
    "max_portfolio_drawdown": "Une plus forte baisse passée limitée",
    "min_defensive_share": "Assez de placements calmes",
    "excluded_asset_class": "Types de placements exclus par le profil",
    "max_correlated_group_weight": "Pas trop de placements qui bougent ensemble",
    "esg_exclusion": "Respect de l'environnement et de la société",
}


def plain_brief(brief: Mapping[str, Any]) -> Dict[str, Any]:
    """Copie du dossier où les règles portent un nom simple au niveau novice ; inchangé au niveau pro.

    Seul le libellé affiché change : statut, valeurs et preuves restent ceux du code.
    """
    if brief.get("level") != "novice":
        return dict(brief)
    checks = []
    for check in brief.get("checks") or []:
        label = NOVICE_RULE_LABELS.get(str(check.get("rule_type")))
        checks.append({**check, "label_fr": label} if label else dict(check))
    return {**brief, "checks": checks}


# Sens simple de chaque statut, ajouté après le mot exact (niveau novice).
NOVICE_STATUS_HINT = {
    "compliant": ", c'est-à-dire dans les limites prévues pour ce profil",
    "tension": ", c'est-à-dire proche de la limite prévue pour ce profil",
    "conflict": ", c'est-à-dire au-delà de la limite prévue pour ce profil",
    "missing_info": "",
}
PROFILE_PHRASES = {
    "novice": {
        "profile_objective": "Ce que le profil fictif veut faire de son argent : [{ref}].",
        "profile_horizon": "Le temps prévu avant d'avoir besoin de cet argent : [{ref}].",
        "profile_risk_tolerance": "Les hauts et les bas de valeur que le profil accepte : [{ref}].",
        "profile_experience": "Son expérience des placements : [{ref}].",
        "profile_esg_preference": "Son souci de l'environnement et de la société dans ses placements : [{ref}].",
        "profile_crypto_allowed": "Les monnaies numériques comme le bitcoin, pour ce profil : [{ref}].",
    },
    "pro": {
        "profile_objective": "Objectif déclaré : [{ref}].",
        "profile_horizon": "Horizon déclaré : [{ref}].",
        "profile_risk_tolerance": "Tolérance au risque déclarée : [{ref}].",
        "profile_experience": "Expérience déclarée : [{ref}].",
        "profile_esg_preference": "Préférence ESG déclarée : [{ref}].",
        "profile_crypto_allowed": "Cryptoactifs : [{ref}].",
    },
}
# Informations absentes connues (champ "missing"), dites telles quelles ; les autres, par une phrase générale.
MISSING_PHRASES = {
    "loss_capacity": "La capacité à absorber une perte n'est pas disponible dans ce prototype : "
                     "elle ne se déduit pas de la tolérance au risque déclarée.",
}
# Niveau novice : chaque mesure dite avec des mots de tous les jours (clé : début du nom de la mesure).
NOVICE_METRIC_LABELS = (
    ("volatility_ann", "à quel point la valeur monte et descend sur une année"),
    ("max_drawdown_cad", "la plus forte baisse passée, appliquée au capital fictif"),
    ("max_drawdown_start", "le début de la plus forte baisse passée"),
    ("max_drawdown_end", "le point le plus bas de cette baisse"),
    ("max_drawdown", "la plus forte baisse passée"),
    ("recovery_days", "le temps qu'il a fallu pour revenir au niveau d'avant"),
    ("underwater_days", "le temps passé sous le niveau le plus haut"),
    ("total_return", "ce que l'ensemble a rapporté sur toute la période"),
    ("return_ann", "ce que l'ensemble a rapporté en moyenne par année"),
    ("top_asset_weight", "la part du plus gros placement"),
    ("defensive_share", "la part des placements plus calmes"),
    ("weight_by_asset_class.etf_bond", "la part des paniers de prêts à des États ou des entreprises"),
    ("weight_by_asset_class.etf_equity", "la part des paniers de parts d'entreprises"),
    ("weight_by_asset_class.etf_commodity", "la part des paniers de matières comme l'or"),
    ("weight_by_asset_class.equity", "la part des entreprises prises une à une"),
    ("weight_by_asset_class.crypto", "la part des monnaies numériques"),
    ("currency_exposure.USD", "la part qui dépend du dollar américain"),
    ("currency_exposure.CAD", "la part en dollars canadiens"),
    ("largest_correlated_group_weight", "la part des placements qui montent et baissent en même temps"),
)
NOVICE_MISSING_PHRASES = {
    "loss_capacity": "Ce prototype ne sait pas quelle baisse le profil pourrait supporter sans difficulté : "
                     "ce n'est pas la même chose que les hauts et les bas qu'il dit accepter.",
}
MISSING_GENERIC = "Une partie de l'information demandée n'est pas disponible dans ce prototype."
NOTHING_CITABLE = "Cette information n'est pas disponible dans ce prototype."


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _level(brief: Mapping[str, Any]) -> str:
    return "pro" if brief.get("level") == "pro" else "novice"


def _usable_evidence(brief: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    """Preuves affichables (valeur et texte présents), par identifiant."""
    return {e["evidence_id"]: e for e in brief.get("evidence") or []
            if e.get("evidence_id") and e.get("value") is not None and e.get("display_value")}


def _focus(brief: Mapping[str, Any], prefix: str) -> List[str]:
    return [ref for ref in brief.get("focus") or [] if isinstance(ref, str) and ref.startswith(prefix)]


def _ordered_checks(brief: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Règles du focus d'abord, puis les plus graves (conflit, tension, information manquante, conforme)."""
    checks = [c for c in brief.get("checks") or [] if c.get("check_id") and c.get("status") in STATUS_PHRASE]
    focus = _focus(brief, "G")
    return sorted(checks, key=lambda c: (c["check_id"] not in focus,
                                         focus.index(c["check_id"]) if c["check_id"] in focus else 0,
                                         SEVERITY[c["status"]], c["check_id"]))


def _check_evidence(check: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]) -> Optional[str]:
    return next((ref for ref in check.get("evidence_ids") or [] if ref in evidence), None)


def _profile_sentences(brief: Mapping[str, Any]) -> List[str]:
    evidence = _usable_evidence(brief)
    by_metric = {e.get("metric"): ref for ref, e in evidence.items() if e.get("subject") == "profile"}
    phrases = PROFILE_PHRASES[_level(brief)]
    focused = [evidence[ref].get("metric") for ref in _focus(brief, "E") if ref in evidence]
    order = [m for m in focused if m in phrases] + [m for m in PROFILE_METRICS if m not in focused]
    return [phrases[m].format(ref=by_metric[m]) for m in order if m in by_metric]


def _novice_label(entry: Mapping[str, Any]) -> Optional[str]:
    """Libellé sans jargon d'une mesure, ou None si la mesure n'a pas de libellé simple connu."""
    metric = str(entry.get("metric") or "")
    for prefix, label in NOVICE_METRIC_LABELS:
        if metric == prefix or metric.startswith(prefix + "."):
            return label
    return None


def _xray_sentences(brief: Mapping[str, Any]) -> List[str]:
    """Mesures du portefeuille fictif : chaque mesure lue sur le portefeuille actuel, sinon après l'idée."""
    evidence = _usable_evidence(brief)
    novice = _level(brief) == "novice"
    refs = [ref for ref in _focus(brief, "E") if ref in evidence]
    for metric in XRAY_METRICS:
        for subject in XRAY_SUBJECTS:
            found = [ref for ref, e in evidence.items()
                     if e.get("subject") == subject and e.get("metric") == metric and ref not in refs]
            if found:
                refs.append(found[0])
                break
    template = "Pour l'ensemble de vos placements fictifs, {label} : [{ref}]." if novice else "{label} : [{ref}]."
    sentences = []
    for ref in refs:
        label = str(evidence[ref].get("label_fr") or "").strip()
        plain = _novice_label(evidence[ref]) if novice else None
        if plain:
            sentences.append(template.format(label=plain, ref=ref))
            continue
        # Le portefeuille actuel est le sujet par défaut ; "après l'ajout" reste écrit quand c'est le cas.
        suffix = SCOPE_SUFFIXES[0]
        label = label[: -len(suffix)] if label.endswith(suffix) else label
        if label:
            sentences.append(template.format(label=_lower_first(label) if novice else label, ref=ref))
    return sentences


def _explanation_sentences(brief: Mapping[str, Any]) -> List[str]:
    evidence = _usable_evidence(brief)
    novice = _level(brief) == "novice"
    checks = _ordered_checks(brief)
    focus = _focus(brief, "G")
    # Les règles en cause (ou celles du focus) d'abord ; les règles conformes seulement s'il n'y en a pas d'autre.
    flagged = [c for c in checks if c["status"] != "compliant" or c["check_id"] in focus]
    sentences = []
    for check in flagged or checks:
        ref, status = check["check_id"], check["status"]
        measure = _check_evidence(check, evidence)
        if status == "missing_info":
            sentences.append(f"La règle [{ref}] {STATUS_PHRASE[status]} : la preuve nécessaire "
                             "n'est pas disponible dans ce prototype.")
        elif measure and novice:
            sentences.append(f"La règle [{ref}] {STATUS_PHRASE[status]}{NOVICE_STATUS_HINT[status]} : "
                             f"la valeur observée est [{measure}].")
        elif measure:
            sentences.append(f"[{ref}] ({STATUS_SHORT[status]}) : mesure observée [{measure}].")
        else:
            sentences.append(f"La règle [{ref}] {STATUS_PHRASE[status]}.")
    return sentences


def _what_changes_sentences(brief: Mapping[str, Any]) -> List[str]:
    novice = _level(brief) == "novice"
    sentences = []
    for check in _ordered_checks(brief):
        ref, status = check["check_id"], check["status"]
        if status == "compliant":
            continue
        if status == "missing_info":
            sentences.append(f"La règle [{ref}] reste en information manquante tant que sa preuve "
                             "n'est pas disponible dans ce prototype.")
        elif check.get("counterfactual"):
            sentences.append(
                f"Pour la règle [{ref}], aujourd'hui {STATUS_SHORT[status]}, un poids plus faible pour l'idée "
                "changerait ce statut : le poids testé est affiché sous la réponse." if novice else
                f"[{ref}] ({STATUS_SHORT[status]}) : le statut dépend du poids cible de l'idée, "
                "dont la simulation est affichée sous la réponse.")
        else:
            sentences.append(f"Pour la règle [{ref}], {STATUS_SHORT[status]}, aucune simulation de poids "
                             "n'est disponible dans ce prototype.")
    if not sentences:
        compliant = [c["check_id"] for c in _ordered_checks(brief) if c["status"] == "compliant"]
        if compliant:
            sentences.append(f"La règle [{compliant[0]}] est conforme, comme les autres règles du profil.")
    return sentences


def _concept_sentences(brief: Mapping[str, Any]) -> List[str]:
    terms = {t["term_id"]: t for t in brief.get("glossary") or [] if t.get("term_id") and t.get("definition")}
    order = [ref for ref in _focus(brief, "T") if ref in terms] or list(terms)[:1]
    novice = _level(brief) == "novice"
    sentences = []
    for ref in order:
        # Le renvoi n'est jamais en fin de proposition : le rendu l'écrirait "(voir **Terme**)".
        definition = _lower_first(str(terms[ref]["definition"]).strip().rstrip("."))
        sentences.append(f"[{ref}] désigne ceci : {definition}.")
        analogy = _lower_first(str(terms[ref].get("analogy") or "").strip().rstrip("."))
        if novice and analogy:
            sentences.append(f"Une image pour [{ref}] est la suivante : {analogy}.")
    for card in brief.get("cards") or []:
        if card.get("card_id") in (brief.get("focus") or []) and card.get("text"):
            sentences.append(str(card["text"]).strip())
    return sentences


BUILDERS: Dict[str, Callable[[Mapping[str, Any]], List[str]]] = {
    "profile": _profile_sentences,
    "xray": _xray_sentences,
    "explanation": _explanation_sentences,
    "what_changes": _what_changes_sentences,
    "concept": _concept_sentences,
}


def _missing_sentences(brief: Mapping[str, Any]) -> List[str]:
    sentences, generic = [], False
    for item in brief.get("missing") or []:
        phrases = NOVICE_MISSING_PHRASES if _level(brief) == "novice" else {}
        phrase = phrases.get(str(item)) or MISSING_PHRASES.get(str(item))
        if phrase and phrase not in sentences:
            sentences.append(phrase)
        elif not phrase:
            generic = True
    if generic:
        sentences.append(MISSING_GENERIC)
    return sentences


def _reply(brief: Mapping[str, Any], answer: str) -> ConversationReply:
    return ConversationReply(brief_id=brief.get("brief_id", ""), answer=answer, origin="template",
                             model_id=None, prompt_version=None, attempt=0)


def _assemble(brief: Mapping[str, Any], candidates: Sequence[str], missing: Sequence[str]) -> List[str]:
    """Garde les phrases dans l'ordre tant que la réponse reste valide ; place réservée à ce qui manque."""
    room = max(REPLY_MAX_SENTENCES - min(len(missing), 1), 1)
    kept: List[str] = []
    for sentence in candidates:
        if len(kept) >= room:
            break
        if validate_reply(_reply(brief, " ".join([*kept, sentence])), brief)["is_valid"]:
            kept.append(sentence)
    for sentence in missing:
        if len(kept) >= REPLY_MAX_SENTENCES:
            break
        if validate_reply(_reply(brief, " ".join([*kept, sentence])), brief)["is_valid"]:
            kept.append(sentence)
    return kept


def build_fallback_reply(brief: Mapping[str, Any]) -> ConversationReply:
    """Réponse du code pour un dossier de conversation : déterministe, valide, sans appel AWS.

    Contrat (analysis_pipeline._conversation_collaborators) : rend une `ConversationReply` d'origine
    "template", sans modèle ni version de prompt, essai 0.
    """
    builder = BUILDERS.get(str(brief.get("answer_kind")), _explanation_sentences)
    try:
        candidates = builder(brief)
    except (KeyError, TypeError, ValueError, AttributeError):   # dossier incomplet : la phrase sûre suffit
        candidates = []
    kept = _assemble(brief, candidates, _missing_sentences(brief))
    return _reply(brief, " ".join(kept) if kept else NOTHING_CITABLE)
