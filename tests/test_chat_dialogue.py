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


# ---- agent conversationnel (issue 78) : questions de profil et "pourquoi", reponse du code hors ligne ----

def test_why_question_after_an_analysis_explains_the_statuses(app):
    app.button(key="idea_preset_TSLA_25").click().run()
    text, last = _send(app, "pourquoi mon idée est-elle en conflit ?")
    entry = app.session_state["chat_history"][-1]
    assert entry["type"] == "agent_answer" and entry["answer_kind"] == "explanation"
    assert "Concentration par actif" in text and "en conflit" in text and "25 %" in text
    assert "Réponse écrite par le code" in text                    # hors ligne : jamais un texte de modele
    assert "pourquoi mon idée" not in str(entry)                   # la question n'est pas recopiee
    assert [e.label for e in last.expander] == ["Données utilisées", "Limites"]


def test_profile_question_answers_from_the_declared_profile_and_says_what_is_missing(app):
    text, _ = _send(app, "quelle perte puis-je absorber ?")
    assert "faible à modérée" in text and "capacité à absorber une perte n'est pas disponible" in text


def test_what_changes_shows_the_tested_weights_under_the_answer(app):
    app.button(key="idea_preset_TSLA_25").click().run()
    text, _ = _send(app, "qu'est-ce qui changerait la réponse ?")
    assert app.session_state["chat_history"][-1]["answer_kind"] == "what_changes"
    assert "plus grand poids testé conforme" in text


def test_diversification_question_reads_the_current_portfolio(app):
    text, _ = _send(app, "mon portefeuille est-il diversifié ?")
    assert app.session_state["chat_history"][-1]["answer_kind"] == "xray"
    assert "Volatilité annualisée" in text or "volatilité annualisée" in text


def test_out_of_scope_messages_still_get_the_code_answer(app):
    _send(app, "parle-moi de la météo")
    assert app.session_state["chat_history"][-1]["type"] == "answer"


# ---- apres la revue : formulations captees par les regles du chat, radiographie apres une analyse ----

@pytest.mark.parametrize("message", ["Explique-moi le verdict", "Que signifie ce statut ?",
                                     "Ça veut dire quoi ce résultat ?", "c'est grave une perte de 26 % ?",
                                     "pourquoi ?"])
def test_why_phrasings_caught_as_definitions_or_ideas_reach_the_agent(app, message):
    app.button(key="idea_preset_TSLA_25").click().run()
    _send(app, message)
    entry = app.session_state["chat_history"][-1]
    assert entry["type"] == "agent_answer" and entry["answer_kind"] == "explanation"


def test_glossary_terms_and_unrelated_why_keep_their_code_answer(app):
    _send(app, "explique-moi la volatilité")
    assert app.session_state["chat_history"][-1]["parsed"]["term_id"]          # definition du glossaire
    _send(app, "Pourquoi le marché a baissé hier ?")                          # sans analyse ni objet
    assert app.session_state["chat_history"][-1]["type"] == "answer"
    _send(app, "le taux de change m'inquiète")
    assert app.session_state["chat_history"][-1].get("answer_kind") != "what_changes"


def test_diversification_after_an_analysis_still_describes_the_current_portfolio(app):
    app.button(key="idea_preset_TSLA_25").click().run()
    text, _ = _send(app, "mon portefeuille est-il diversifié ?")
    assert app.session_state["chat_history"][-1]["answer_kind"] == "xray"
    assert "(SPY)" in text and "(TSLA)" not in text                          # avant l'idee, pas apres


# ---- apres l'audit de securite : conseil, ordre et prediction jamais envoyes a l'agent ----

AUDIT_MESSAGES = (
    "que faudrait-il acheter pour que ce soit conforme ?",
    "qu'est-ce qui changerait la réponse, faut-il vendre ?",
    "c'est grave une perte de 26 % ? je vends tout ?",
    "pourquoi la perte sera plus forte demain ?",
    "pourquoi ma concentration est elle un probleme, quel titre choisir ?",
)


@pytest.mark.parametrize("message", AUDIT_MESSAGES)
def test_advice_order_and_prediction_requests_are_refused_never_answered(app, message):
    app.button(key="idea_preset_TSLA_25").click().run()
    _send(app, message)
    entry = app.session_state["chat_history"][-1]
    assert entry["type"] == "refused", entry.get("type")


def test_a_named_unknown_asset_keeps_its_clarification(app):
    app.button(key="idea_preset_TSLA_25").click().run()
    _send(app, "pourquoi le risque de GME est en conflit ?")
    assert app.session_state["chat_history"][-1]["type"] == "clarify"
