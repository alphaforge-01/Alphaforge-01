"""Routage des questions vers l'agent conversationnel (issue 78) : des regles lisibles, sans modele.

`classify_question(text)` rend le type de question (`answer_kind`) d'un message que les regles du chat
(`request_parsing.py`) n'ont pas compris, ou `None`. Il n'est appele qu'apres le garde-fou d'entree, le
controle local des sujets refuses et la traduction en idee : un refus, une idee, une salutation ou une
definition du glossaire ne passent jamais par ici. Une question de diversification ou de risque que les regles
prennent pour la liste des positions peut etre reprise (type "xray") ; la liste elle-meme reste au code.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple

from .contracts import AnswerKind


def _normalize(text: str) -> str:
    """Minuscules, sans accents, apostrophes unifiees : les regles restent simples a lire."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# Mots qui rattachent une question au resultat affiche : sans eux, "pourquoi le marche a baisse ?" reste hors sujet.
_OBJECT = r"(idee|verdict|conflit|tension|regle|statut|portefeuille|risque|perte|volatilite|concentration|conforme|resultat|reponse)"

# Ordre de priorite : ce qui changerait la reponse, puis le "pourquoi", puis le profil, puis le portefeuille.
_RULES: Tuple[Tuple[AnswerKind, re.Pattern], ...] = (
    ("what_changes", re.compile(
        r"(qu'est-ce qui|qu'est ce qui|que faudrait-il|qu'est-ce qu'il faudrait|ce qui)\b.*"
        r"\b(changer|changerait|changeraient|changement|conforme)\b"
        r"|\brendre (mon idee |l'idee |le portefeuille )?conforme"
        r"|\bpour (que ce soit|que ca soit|etre) conforme"
        r"|\bchanger (le|la|ce|cette) (verdict|statut|resultat|reponse)")),
    ("explanation", re.compile(
        r"\bpourquoi\b.*\b" + _OBJECT + r"|\b(c'est|est-ce) grave\b"
        r"|\bexplique(-moi|z|z-moi)?\b.*\b(verdict|conflit|tension|resultat|statut|regle|reponse)\b"
        r"|\b(que veut dire|que signifie|veut dire quoi)\b.*\b(verdict|conflit|tension|resultat|statut|regle|reponse)\b"
        r"|\ben (conflit|tension)\b")),
    ("profile", re.compile(
        r"\bmon (horizon|profil|objectif)\b|\bma (tolerance|capacite|preference)\b|\bmes (preferences|objectifs)\b"
        r"|\bhorizon de placement\b|\bcapacite\b.*\bperte\b|\bperte\b.*\b(absorber|supporter|encaisser)\b"
        r"|\bquel(le)? (risque|perte)\b.*\b(puis-je|je peux|accepter)\b")),
    ("xray", re.compile(
        r"\bdiversifi|\bconcentr|\bexposition\b"
        r"|\bmon portefeuille est(-il)? (risque|equilibre|prudent)|\b(risque|volatilite|perte maximale) de mon portefeuille\b")),
)
# Seconde barrière, après le contrôle local : un message qui parle d'acheter, de vendre, de choisir un titre ou de
# l'avenir n'est jamais envoyé à l'agent, même si le contrôle local l'a laissé passer.
_NEVER_TO_AGENT = re.compile(
    r"\b(achet\w*|vend(s|re|ez|ons|u|ue|ant|rait)?|choisir|faut-il|demain|bientot|sera|seront|futur\w*|prevoi\w*"
    r"|predi\w*|conseil\w*|recommand\w*|\w+(era|eront))\b"
    r"|\b(va|vont)(-t-(il|elle))?\s+(augmenter|diminuer|monter|baisser|remonter|chuter|grimper|empirer|s'aggraver)\b")
# Une seule proposition : une seconde question accolee ("..., je garde ou pas ?") n'est jamais envoyee a l'agent,
# quelle que soit sa formulation. Une virgule decimale ("0,25") ne coupe pas la phrase.
_CLAUSE_BREAK = re.compile(r"[?!;:]|[.,](?=\s|$)")
_BARE_WHY = re.compile(r"^\W*pourquoi\W*$|\bpourquoi (ca|cela|c'est)\b")


def classify_question(text: str, *, has_analysis: bool = False) -> Optional[AnswerKind]:
    """Type de question pour l'agent conversationnel, ou `None` si aucune regle ne la reconnait.

    `has_analysis` : une idee a deja ete analysee. Un "pourquoi ?" sans objet ne vise alors que ce resultat.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = _normalize(text)
    if _NEVER_TO_AGENT.search(normalized):
        return None
    if len([clause for clause in _CLAUSE_BREAK.split(normalized) if clause.strip()]) > 1:
        return None
    for kind, pattern in _RULES:
        if pattern.search(normalized):
            return kind
    if has_analysis and _BARE_WHY.search(normalized):
        return "explanation"
    return None
