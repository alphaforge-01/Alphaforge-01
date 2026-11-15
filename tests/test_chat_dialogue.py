"""Dialogue de la page Simulation, joué dans la vraie interface sans navigateur (lot 1, issue #78).

Mode hors ligne, données réelles, profil fictif de Robert. Les réponses viennent du code : aucun modèle.
"""
from __future__ import annotations

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


@pytest.fixture()
def app():
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    at.button(key="choose_profile_robert").click().run()
    at.switch_page("views/simulation_page.py").run()
    assert not at.exception
    return at


def _send(at, message):
    at.chat_input[0].set_value(message).run()
    assert not at.exception, [e.value for e in at.exception]
    last = at.chat_message[-1]
    return " ".join([m.value for m in last.markdown] + [c.value for c in last.caption]), last


def test_greeting_offers_clickable_examples(app):
    text, last = _send(app, "hey")
    assert "Bonjour" in text and "sans jamais vous dire quoi acheter" in text
    assert len(last.button) == 3


def test_portfolio_lists_positions_of_the_fictional_portfolio(app):
    text, _ = _send(app, "quels sont mes actifs actuels ?")
    assert "portefeuille fictif de Robert" in text
    assert "**SPY**" in text and "20 %" in text


def test_definition_comes_from_the_glossary(app):
    text, _ = _send(app, "c'est quoi la volatilité ?")
    assert "**Volatilité**" in text and "glossaire du projet" in text


def test_weight_without_percent_needs_a_click_before_any_analysis(app):
    text, last = _send(app, "0.25 NVIDIA")
    assert "Voulez-vous simuler" in text and "25 % dans NVDA" in text
    assert not any(entry.get("type") == "analysis" for entry in app.session_state["chat_history"])
    next(button for button in last.button if button.label == "Oui, simuler").click().run()
    assert not app.exception
    assert app.session_state["chat_history"][-1]["type"] == "analysis"
    assert app.session_state["idea"]["ticker"] == "NVDA"


def test_follow_up_uses_the_last_analysed_idea_after_a_click(app):
    app.button(key="idea_preset_TSLA_25").click().run()
    text, last = _send(app, "et à 10 % ?")
    assert "10 % dans TSLA" in text and "Même actif" in text
    assert app.session_state["idea"]["target_weight"] == 0.25  # rien n'est simulé avant le clic
    next(button for button in last.button if button.label == "Oui, simuler").click().run()
    assert app.session_state["idea"]["ticker"] == "TSLA"
    assert app.session_state["idea"]["target_weight"] == 0.1


def test_relative_follow_up_asks_for_the_total_weight(app):
    app.button(key="idea_preset_TSLA_25").click().run()
    text, _ = _send(app, "réduis de 5 %")
    assert "poids total" in text
    assert app.session_state["idea"]["target_weight"] == 0.25


def test_refusal_still_wins(app):
    text, _ = _send(app, "bonjour, achète TSLA pour moi")
    assert "Refus du contrôle local" in text
    assert not any(entry.get("type") == "analysis" for entry in app.session_state["chat_history"])
