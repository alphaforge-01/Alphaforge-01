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
PROFILE_PHRASES = {
    "novice": {
        "profile_objective": "L'objectif déclaré du profil fictif est : [{ref}].",
        "profile_horizon": "Son horizon de placement déclaré est [{ref}].",
        "profile_risk_tolerance": "Sa tolérance au risque déclarée est [{ref}].",
        "profile_experience": "Son expérience déclarée est [{ref}].",
        "profile_esg_preference": "Sa préférence ESG déclarée est [{ref}].",
        "profile_crypto_allowed": "Les cryptoactifs sont, pour ce profil : [{ref}].",
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
    template = "Pour le portefeuille fictif, {label} atteint [{ref}]." if novice else "{label} : [{ref}]."
    sentences = []
    for ref in refs:
        label = str(evidence[ref].get("label_fr") or "").strip()
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
            sentences.append(f"La règle [{ref}] {STATUS_PHRASE[status]} : la mesure concernée atteint [{measure}].")
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
        phrase = MISSING_PHRASES.get(str(item))
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
