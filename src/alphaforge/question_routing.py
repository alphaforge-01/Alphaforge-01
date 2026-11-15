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


# Ordre de priorite : ce qui changerait la reponse, puis le "pourquoi", puis le profil, puis le portefeuille.
_RULES: Tuple[Tuple[AnswerKind, re.Pattern], ...] = (
    ("what_changes", re.compile(
        r"(qu'est-ce qui|qu'est ce qui|que faudrait-il|qu'est-ce qu'il faudrait|ce qui)\b.*\b(chang|conforme)"
        r"|\brendre (mon idee |l'idee |le portefeuille )?conforme"
        r"|\bpour (que ce soit|que ca soit|etre) conforme"
        r"|\bchanger (le|la|ce|cette) (verdict|statut|resultat|reponse)")),
    ("explanation", re.compile(
        r"\bpourquoi\b|\bc'est grave\b|\best-ce grave\b|\bca veut dire quoi\b|\bque (veut dire|signifie)\b"
        r"|\bexplique(-moi|z)?\b.*\b(verdict|conflit|tension|resultat|statut|regle)"
        r"|\ben (conflit|tension)\b")),
    ("profile", re.compile(
        r"\bmon (horizon|profil|objectif)\b|\bma (tolerance|capacite|preference)\b|\bmes (preferences|objectifs)\b"
        r"|\bhorizon de placement\b|\bcapacite\b.*\bperte\b|\bperte\b.*\b(absorber|supporter|encaisser)\b"
        r"|\bquel(le)? (risque|perte)\b.*\b(puis-je|je peux|accepter)\b")),
    ("xray", re.compile(
        r"\bdiversifi|\bconcentr|\bexposition\b"
        r"|\bmon portefeuille est(-il)? (risque|equilibre|prudent)|\b(risque|volatilite|perte maximale) de mon portefeuille\b")),
)


def classify_question(text: str) -> Optional[AnswerKind]:
    """Type de question pour l'agent conversationnel, ou `None` si aucune regle ne la reconnait."""
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = _normalize(text)
    for kind, pattern in _RULES:
        if pattern.search(normalized):
            return kind
    return None
