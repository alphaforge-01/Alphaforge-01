"""Explication de secours à gabarit fixe (flux B, tâche B3).

`render_template(brief)` produit un `ExplainerOutput` sans modèle de langage ni
appel AWS. Il sert de filet quand l'explicateur échoue, de mode hors ligne et de
référence de comparaison.

Garanties par construction :
- aucun chiffre écrit en clair : les valeurs passent par des renvois `[E1]`
  (preuve), `[G1]` (contrôle de gouvernance) et `[T1]` (glossaire), remplacés
  plus tard par `explanation_rendering.render_markdown` ;
- les statuts viennent des contrôles du dossier (`governance.py`), jamais
  recalculés ni adoucis ;
- aucune recommandation, aucune prévision, aucune promesse de rendement ;
- une règle sans donnée est dite "information manquante", jamais conforme ;
- chaque contrôle non conforme est cité dans le résumé ;
- chaque emplacement respecte `max_chars_per_slot`.

Les deux niveaux ont des formulations distinctes : novice (mots simples,
glossaire) et pro (termes techniques, marge, seuils). Les chiffres sont les mêmes.
"""
from __future__ import annotations

from typing import Any, List, Mapping, Optional, Sequence

from alphaforge.contracts import ExplainerOutput, ExplanationBrief, check_keys
from alphaforge.governance import STATUS_SEVERITY, worst_status

LEVELS = ("novice", "pro")
DEFAULT_MAX_CHARS = 400

# Verdict global, dit sous forme de nom.
VERDICT_FR = {
    "compliant": "conforme",
    "tension": "tension",
    "conflict": "conflit",
    "missing_info": "information manquante",
}

# Règles où la limite est un plancher (la mesure doit rester au-dessus).
_MIN_RULE_TYPES = {"min_defensive_share"}

# Sujet de chaque type de règle : (novice, pro).
_TOPICS = {
    "max_single_asset_weight": ("la part d'un seul placement dans le portefeuille",
                                "le poids du plus gros actif"),
    "max_portfolio_volatility": ("l'amplitude des variations du portefeuille",
                                 "la volatilité annualisée du portefeuille"),
    "max_portfolio_drawdown": ("la pire baisse observée dans le passé",
                               "la perte maximale historique (drawdown)"),
    "min_defensive_share": ("la part de placements plus stables",
                            "la part défensive"),
    "excluded_asset_class": ("la présence d'une catégorie que le profil exclut",
                             "l'exposition à une classe d'actifs exclue"),
    "max_asset_class_weight": ("le poids d'une même catégorie de placements",
                               "le poids de la classe d'actifs"),
    "max_correlated_group_weight": ("les placements qui bougent ensemble",
                                    "le poids du plus grand groupe corrélé"),
    "esg_exclusion": ("le critère ESG du profil", "l'exclusion ESG"),
}
_DEFAULT_TOPIC = ("cette règle du profil", "cette règle")

# Terme de glossaire cherché pour chaque type de règle (comparaison sans accents).
_GLOSSARY_KEYWORDS = {
    "max_portfolio_volatility": ("volatilite",),
    "max_portfolio_drawdown": ("perte maximale", "drawdown", "baisse"),
    "max_single_asset_weight": ("concentration",),
    "max_asset_class_weight": ("concentration", "diversification"),
    "min_defensive_share": ("defensi",),
    "max_correlated_group_weight": ("correlation", "diversification"),
    "esg_exclusion": ("esg",),
}

_REASON_PHRASES = {
    "reduce_weight": ("réduit la part de l'idée", "réduction du poids cible"),
    "change_funding_source": ("change l'origine des fonds", "changement de source de financement"),
    "spread_across_existing": ("répartit l'idée sur des placements déjà détenus",
                               "répartition sur les positions existantes"),
}
_ORDINALS = ("première", "deuxième", "troisième")


def _fold(text: str) -> str:
    table = str.maketrans("éèêëàâîïôùûç", "eeeeaaiiouuc")
    return text.lower().translate(table)


def _fit(candidates: Sequence[str], max_chars: int) -> str:
    """Premier candidat qui tient dans `max_chars`, sinon le plus court."""
    for text in candidates:
        if len(text) <= max_chars:
            return text
    return min(candidates, key=len)


def _join_refs(ids: Sequence[str]) -> str:
    refs = [f"[{i}]" for i in ids]
    if len(refs) <= 1:
        return "".join(refs)
    return ", ".join(refs[:-1]) + " et " + refs[-1]


def _is_min_rule(check: Mapping[str, Any], rules: Mapping[str, Mapping[str, Any]]) -> bool:
    rule = rules.get(check.get("rule_id"))
    if rule is not None:
        return rule.get("direction") == "min"
    return check.get("rule_type") in _MIN_RULE_TYPES


def _topic(check: Mapping[str, Any], level: str) -> str:
    novice, pro = _TOPICS.get(check.get("rule_type"), _DEFAULT_TOPIC)
    return novice if level == "novice" else pro


def _glossary_ref(check: Mapping[str, Any], glossary: Sequence[Mapping[str, Any]]) -> Optional[str]:
    for keyword in _GLOSSARY_KEYWORDS.get(check.get("rule_type"), ()):
        for entry in glossary:
            if keyword in _fold(str(entry.get("term", ""))):
                return entry.get("term_id")
    return None


def _factor_text(check: Mapping[str, Any], level: str, is_min: bool,
                 glossary: Sequence[Mapping[str, Any]], max_chars: int) -> str:
    gid = f"[{check['check_id']}]"
    evidence = _join_refs(check.get("evidence_ids") or [])
    topic = _topic(check, level)
    status = check["status"]
    term = _glossary_ref(check, glossary) if level == "novice" else None
    term_note = f" (voir {_join_refs([term])})" if term else ""
    side = "sous" if is_min else "au-delà de"
    measure = f"la mesure {evidence}" if evidence else "la mesure"

    if status == "missing_info" and check.get("rule_type") == "esg_exclusion":
        if level == "novice":
            long = (f"Pour {topic}, aucune preuve ESG n'est disponible : la vérification est impossible. "
                    f"L'idée n'est ni validée ni écartée sur ce point. Contrôle : {gid}.")
            short = f"Sur {topic}, aucune preuve ESG : vérification impossible. Contrôle : {gid}."
        else:
            subject = topic[0].upper() + topic[1:]
            long = (f"{subject} : aucune preuve ESG disponible, vérification impossible, statut information "
                    f"manquante. Aucun verdict ESG, distinct des verdicts financiers. Contrôle : {gid}.")
            short = f"{subject} : aucune preuve ESG, information manquante. Contrôle : {gid}."
        return _fit([long, short], max_chars)

    if level == "novice":
        if status == "conflict":
            long = (f"Pour {topic}{term_note}, {measure} franchit la limite fixée pour ce profil. "
                    f"Contrôle : {gid}.")
            short = f"Sur {topic}, la limite du profil est franchie. Contrôle : {gid}."
        elif status == "tension":
            long = (f"Pour {topic}{term_note}, {measure} passe le seuil d'attention du profil, "
                    f"sans atteindre la limite. Contrôle : {gid}.")
            short = f"Sur {topic}, le seuil d'attention est passé. Contrôle : {gid}."
        elif status == "compliant":
            long = f"Pour {topic}{term_note}, {measure} reste dans les repères du profil. Contrôle : {gid}."
            short = f"Sur {topic}, le profil est respecté. Contrôle : {gid}."
        else:
            long = (f"Pour {topic}, le contrôle n'a pas pu être fait : information manquante. "
                    f"Aucun verdict n'est donné sur ce point. Contrôle : {gid}.")
            short = f"Sur {topic}, information manquante, aucun verdict. Contrôle : {gid}."
    else:
        subject = topic[0].upper() + topic[1:]
        if status == "conflict":
            long = (f"{subject} : {evidence or 'valeur'} {side} la limite du profil, "
                    f"marge négative. Contrôle : {gid}.")
            short = f"{subject} : limite franchie. Contrôle : {gid}."
        elif status == "tension":
            where = "sous le seuil d'avertissement" if is_min else "au-delà du seuil d'avertissement"
            long = (f"{subject} : {evidence or 'valeur'} {where}, limite non atteinte, "
                    f"marge positive. Contrôle : {gid}.")
            short = f"{subject} : seuil d'avertissement franchi. Contrôle : {gid}."
        elif status == "compliant":
            where = "au-dessus du seuil d'avertissement" if is_min else "sous le seuil d'avertissement"
            long = f"{subject} : {evidence or 'valeur'} {where}. Contrôle : {gid}."
            short = f"{subject} : conforme. Contrôle : {gid}."
        else:
            long = (f"{subject} : valeur non calculable, statut information manquante, "
                    f"aucun verdict. Contrôle : {gid}.")
            short = f"{subject} : information manquante. Contrôle : {gid}."
    return _fit([long, short], max_chars)


def _summary(brief: Mapping[str, Any], level: str, max_chars: int) -> str:
    checks = list(brief.get("checks") or [])
    ticker = (brief.get("idea") or {}).get("ticker", "")
    idea = f"« {ticker} »" if ticker else "cette idée"
    if not checks:
        return _fit([
            f"Aucune règle du profil n'a pu être évaluée pour l'idée {idea} : information manquante.",
        ], max_chars)

    overall = worst_status(c["status"] for c in checks)
    flagged = [c for c in checks if c["status"] != "compliant"]
    flagged.sort(key=lambda c: -STATUS_SEVERITY[c["status"]])
    refs = _join_refs([c["check_id"] for c in flagged])
    verdict = VERDICT_FR[overall]

    if overall == "compliant":
        if level == "novice":
            return _fit([f"L'idée simulée sur {idea} respecte toutes les règles évaluées pour ce profil."],
                        max_chars)
        return _fit([f"Toutes les règles évaluées sont conformes pour l'idée {idea} "
                     f"(pire statut : conforme)."], max_chars)

    only_missing = all(c["status"] == "missing_info" for c in flagged)
    if only_missing and any(c["status"] == "compliant" for c in checks):
        # Les autres règles sont conformes : ne pas laisser croire que tout est inconnu.
        unverified = "n'ont pas pu être vérifiés" if len(flagged) > 1 else "n'a pas pu être vérifié"
        if level == "novice":
            long = (f"Pour l'idée simulée sur {idea}, les autres règles évaluées sont respectées, mais "
                    f"{refs} {unverified}. Verdict d'ensemble : {verdict}.")
            short = f"Autres règles respectées. Vérification impossible : {refs}. Verdict : {verdict}."
        else:
            long = (f"Pour l'idée {idea}, les règles évaluables sont conformes. Contrôles sans verdict, "
                    f"information manquante : {refs}. Le pire statut global est : {verdict}.")
            short = f"Règles évaluables conformes. Sans verdict : {refs}. Pire statut : {verdict}."
        return _fit([long, short], max_chars)

    if level == "novice":
        long = (f"Pour l'idée simulée sur {idea}, le verdict d'ensemble est : {verdict}. "
                f"Points à regarder : {refs}.")
        short = f"Verdict d'ensemble : {verdict}. Points à regarder : {refs}."
    else:
        long = (f"Verdict global, pire statut des règles, pour l'idée {idea} : {verdict}. "
                f"Contrôles non conformes : {refs}.")
        short = f"Pire statut : {verdict}. Contrôles non conformes : {refs}."
    return _fit([long, short], max_chars)


def _counterfactual(brief: Mapping[str, Any], level: str, max_chars: int) -> str:
    checks = list(brief.get("checks") or [])
    flagged = [c for c in checks if c["status"] in ("tension", "conflict")]
    with_cf = [c for c in flagged if c.get("counterfactual")]
    without_cf = [c for c in flagged if not c.get("counterfactual")]

    if not flagged:
        if any(c["status"] == "missing_info" for c in checks):
            return _fit(["Aucune règle évaluable n'est en tension ni en conflit : aucun contrefactuel à "
                         "calculer. Au moins une règle manque d'information.",
                         "Aucun contrefactuel : au moins une règle manque d'information."], max_chars)
        return _fit(["Toutes les règles évaluées sont respectées : aucun contrefactuel à calculer."],
                    max_chars)

    parts_long: List[str] = []
    parts_short: List[str] = []
    if with_cf:
        refs = _join_refs([c["check_id"] for c in with_cf])
        if level == "novice":
            parts_long.append(f"Pour {refs}, le plus grand poids testé qui respecte cette règle seule est "
                              f"donné ci-dessous. Respecter une règle n'implique pas de respecter les autres.")
            parts_short.append(f"Pour {refs}, le plus grand poids testé conforme à cette règle seule "
                               f"est donné ci-dessous.")
        else:
            parts_long.append(f"Pour {refs}, plus grand poids cible testé conforme à la règle seule, par "
                              f"balayage du seul poids de l'idée, valeur ci-dessous. Conformité propre à "
                              f"chaque règle, pas à l'ensemble du portefeuille.")
            parts_short.append(f"Pour {refs}, plus grand poids testé conforme à la règle seule, "
                               f"valeur ci-dessous.")
    if without_cf:
        refs = _join_refs([c["check_id"] for c in without_cf])
        parts_long.append(f"Pour {refs}, seule la marge au seuil est disponible.")
        parts_short.append(f"Pour {refs}, marge seule disponible.")
    return _fit([" ".join(parts_long), " ".join(parts_short)], max_chars)


def _variants(brief: Mapping[str, Any], level: str, max_chars: int) -> str:
    variants = list(brief.get("variants") or [])
    if not variants:
        return _fit(["Aucune variante simulée n'est disponible pour cette idée."], max_chars)

    idx = 0 if level == "novice" else 1
    long_parts: List[str] = []
    short_parts: List[str] = []
    for position, variant in enumerate(variants):
        ordinal = _ORDINALS[position] if position < len(_ORDINALS) else "autre"
        phrase = _REASON_PHRASES.get(variant.get("reason_code"), ("une modification",) * 2)[idx]
        verdict = VERDICT_FR.get(variant.get("overall_status"), "information manquante")
        evidence = _join_refs(variant.get("evidence_ids") or [])
        measures = f" Mesures : {evidence}." if evidence else ""
        if level == "novice":
            long_parts.append(f"La {ordinal} variante {phrase} : verdict d'ensemble {verdict}.{measures}")
        else:
            long_parts.append(f"Variante {ordinal} ({phrase}) : pire statut {verdict}.{measures}")
        short_parts.append(f"La {ordinal} variante : {verdict}.")
    return _fit([" ".join(long_parts), " ".join(short_parts)], max_chars)


def _limits_context(level: str, max_chars: int) -> str:
    if level == "novice":
        candidates = [
            "Ces résultats décrivent le passé et reposent sur des hypothèses. Les limites ci-dessous "
            "s'appliquent à tous les chiffres.",
            "Ces résultats décrivent le passé. Voir les limites ci-dessous.",
        ]
    else:
        candidates = [
            "Résultats descriptifs sur données historiques, seuils posés comme hypothèses de l'équipe. "
            "Les limites obligatoires ci-dessous encadrent chaque preuve citée.",
            "Résultats descriptifs, seuils hypothétiques. Limites obligatoires ci-dessous.",
        ]
    return _fit(candidates, max_chars)


def render_template(brief: ExplanationBrief) -> ExplainerOutput:
    """Construit l'explication de secours d'un dossier, au niveau `brief["level"]`.

    Retourne un `ExplainerOutput` avec `origin="template"`, `model_id=None`,
    `prompt_version=None` et `attempt=0`. Lève `ValueError` si le dossier est
    incomplet ou si le niveau est inconnu. Le dossier n'est pas modifié.
    """
    missing = check_keys(brief, ExplanationBrief)
    if missing:
        raise ValueError("Dossier d'explication incomplet : " + ", ".join(missing))
    level = brief["level"]
    if level not in LEVELS:
        raise ValueError(f"Niveau inconnu : {level!r}. Valeurs permises : {', '.join(LEVELS)}.")

    max_chars = brief.get("max_chars_per_slot") or DEFAULT_MAX_CHARS
    checks = {c["check_id"]: c for c in brief["checks"]}
    rules = {r["rule_id"]: r for r in brief["profile_rules"]}
    glossary = brief.get("glossary") or []

    factors = []
    for ranked in brief["ranked_factors"]:
        check = checks.get(ranked["check_id"])
        if check is None:
            continue  # facteur sans contrôle correspondant : rien à écrire, rien d'inventé
        factors.append({
            "check_id": check["check_id"],
            "text": _factor_text(check, level, _is_min_rule(check, rules), glossary, max_chars),
        })

    return {
        "brief_id": brief["brief_id"],
        "level": level,
        "summary": _summary(brief, level, max_chars),
        "factors": factors,
        "counterfactual": _counterfactual(brief, level, max_chars),
        "variants": _variants(brief, level, max_chars),
        "limits_context": _limits_context(level, max_chars),
        "origin": "template",
        "model_id": None,
        "prompt_version": None,
        "attempt": 0,
    }
