"""Routage des questions vers l'agent conversationnel (issue 78) : regles sans modele."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alphaforge.question_routing import classify_question  # noqa: E402


@pytest.mark.parametrize("text,kind", [
    ("Pourquoi mon idée est-elle en conflit ?", "explanation"),
    ("c'est grave une perte de 26 % ?", "explanation"),
    ("Explique-moi ce verdict", "explanation"),
    ("Qu'est-ce qui changerait la réponse ?", "what_changes"),
    ("que faudrait-il pour que ce soit conforme ?", "what_changes"),
    ("Quel est mon horizon ?", "profile"),
    ("Quelle perte puis-je absorber ?", "profile"),
    ("quelle est ma tolérance au risque ?", "profile"),
    ("Mon portefeuille est-il diversifié ?", "xray"),
    ("mon portefeuille est-il risqué ?", "xray"),
    ("POURQUOI c’est en tension ?", "explanation"),     # majuscules et apostrophe typographique
])
def test_questions_are_routed_to_the_right_kind(text, kind):
    assert classify_question(text) == kind


@pytest.mark.parametrize("text", [
    "hey", "parle-moi de la météo", "quels sont mes actifs actuels ?", "quel est mon portefeuille actuel ?",
    "composition de mon portefeuille", "", "   ", None,
])
def test_other_messages_are_left_to_the_code(text):
    assert classify_question(text) is None
