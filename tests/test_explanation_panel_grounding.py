"""Signal d'ancrage faible dans la section de l'explication (le texte du modele reste affiche)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from streamlit.testing.v1 import AppTest  # noqa: E402

SCRIPT = """
import sys
sys.path.insert(0, {root!r})
from components.explanation_panel import render_grounding_note
render_grounding_note({explanation!r})
"""


def _run(origin, details):
    explanation = {"output": {"origin": origin}, "trace": [{"name": "guardrail", "details": details}]}
    app = AppTest.from_string(SCRIPT.format(root=str(ROOT / "app"), explanation=explanation))
    app.run()
    assert not app.exception
    return [w.value for w in app.warning]


def test_weak_grounding_shows_a_warning_with_the_score():
    warnings = _run("llm", {"grounding_weak": True, "grounding_score": 0.34})
    assert len(warnings) == 1 and "Ancrage faible (score 0.34)" in warnings[0]


def test_very_weak_grounding_shows_the_stronger_warning():
    warnings = _run("llm", {"grounding_weak": True, "grounding_very_weak": True, "grounding_score": 0.14})
    assert len(warnings) == 1 and "Ancrage très faible (score 0.14)" in warnings[0]


@pytest.mark.parametrize("origin,details", [
    ("llm", {"grounding_score": 0.9}),                                   # bien ancre : aucun signal
    ("template", {"grounding_weak": True, "grounding_score": 0.2}),      # gabarit : le texte n'est pas celui du modele
])
def test_no_warning_when_well_grounded_or_when_the_template_is_shown(origin, details):
    assert _run(origin, details) == []
