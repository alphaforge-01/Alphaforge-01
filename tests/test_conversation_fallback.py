"""Réponse du code de l'agent conversationnel (issue 78) : déterministe, valide, sans appel AWS."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from alphaforge import conversation_fallback as cf  # noqa: E402
from alphaforge.analysis_pipeline import CONVERSATION_UNAVAILABLE, answer_question  # noqa: E402
from alphaforge.bedrock_client import BedrockConfig  # noqa: E402
from alphaforge.contracts import ConversationReply, check_keys  # noqa: E402
from alphaforge.conversation_agent import render_answer  # noqa: E402
from alphaforge.explanation_validator import validate_reply  # noqa: E402
from conversation_briefs import QUESTION, make_brief, reply  # noqa: E402

KINDS = ("profile", "xray", "explanation", "what_changes", "concept")
LEVELS = ("novice", "pro")


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", KINDS)
def test_fallback_is_valid_and_follows_the_contract_for_every_kind_and_level(kind, level):
    brief = make_brief(kind, level)
    answer = cf.build_fallback_reply(brief)
    check_keys(answer, ConversationReply)
    assert answer["origin"] == "template" and answer["attempt"] == 0
    assert answer["model_id"] is None and answer["prompt_version"] is None
    assert answer["brief_id"] == brief["brief_id"]
    result = validate_reply(answer, brief)
    assert result["is_valid"], (kind, level, answer["answer"], result["rejections"])
    assert answer["answer"] != cf.NOTHING_CITABLE, (kind, level)
    assert not re.search(r"\d", re.sub(r"\[[EGT]\d+\]", "", answer["answer"]))   # aucun chiffre en clair
    assert "MARQUEUR-QUESTION" not in answer["answer"]                           # question jamais recopiée


def test_fallback_is_deterministic():
    brief = make_brief("explanation")
    assert cf.build_fallback_reply(brief) == cf.build_fallback_reply(make_brief("explanation"))


def test_explanation_states_each_flagged_rule_with_its_exact_status():
    brief = make_brief("explanation")
    text = cf.build_fallback_reply(brief)["answer"]
    for check in brief["checks"]:
        if check["status"] != "compliant":
            assert f"[{check['check_id']}] {cf.STATUS_PHRASE[check['status']]}" in text
    # les règles conformes ne sont pas citées quand d'autres sont en cause
    compliant = [c["check_id"] for c in brief["checks"] if c["status"] == "compliant"]
    assert all(f"[{ref}]" not in text for ref in compliant)


def test_focus_brings_a_compliant_rule_forward():
    brief = make_brief("explanation")
    compliant = next(c for c in brief["checks"] if c["status"] == "compliant")
    brief["focus"] = [compliant["check_id"]]
    text = cf.build_fallback_reply(brief)["answer"]
    assert text.startswith(f"La règle [{compliant['check_id']}] est conforme")


def test_profile_cites_declared_facts_and_says_what_is_missing():
    brief = make_brief("profile", missing=["loss_capacity"])
    text = cf.build_fallback_reply(brief)["answer"]
    assert "[E90]" in text and "[E91]" in text                       # objectif et horizon déclarés
    assert cf.MISSING_PHRASES["loss_capacity"] in text               # tolérance n'est pas capacité


def test_unknown_missing_item_gets_a_generic_sentence():
    brief = make_brief("profile", missing=["autre_information"])
    assert cf.MISSING_GENERIC in cf.build_fallback_reply(brief)["answer"]


def test_concept_uses_the_glossary_and_the_analogy_only_for_novice():
    novice = make_brief("concept", "novice")
    term = novice["glossary"][0]
    novice["focus"] = [term["term_id"]]
    text_novice = render_answer(cf.build_fallback_reply(novice), novice)
    assert f"**{term['term']}** désigne ceci" in text_novice
    if term.get("analogy"):
        assert "Une image pour" in text_novice
    pro = make_brief("concept", "pro")
    pro["focus"] = [pro["glossary"][0]["term_id"]]
    assert "Une image pour" not in cf.build_fallback_reply(pro)["answer"]


def test_rendered_answer_shows_registry_values_without_raw_references():
    brief = make_brief("explanation", "novice")
    rendered = render_answer(cf.build_fallback_reply(brief), brief)
    assert not re.search(r"\[[EGT]\d+\]", rendered) and "(voir" not in rendered


def test_empty_or_broken_brief_still_gives_a_valid_safe_sentence():
    empty = make_brief("explanation", evidence=[], checks=[], glossary=[])
    answer = cf.build_fallback_reply(empty)
    assert answer["answer"] == cf.NOTHING_CITABLE and validate_reply(answer, empty)["is_valid"]
    broken = make_brief("explanation", checks=[{"check_id": "G1"}])   # statut absent
    assert validate_reply(cf.build_fallback_reply(broken), broken)["is_valid"]
    unknown_kind = make_brief("autre")
    assert validate_reply(cf.build_fallback_reply(unknown_kind), unknown_kind)["is_valid"]


def test_a_sentence_that_would_be_rejected_is_dropped():
    """Un libellé de preuve inattendu (chiffre, mot interdit) ne fait jamais rejeter la réponse du code."""
    brief = make_brief("xray")
    for entry in brief["evidence"]:
        if entry.get("metric") == "volatility_ann":
            entry["label_fr"] = "Volatilité garantie sur 3 ans"
    answer = cf.build_fallback_reply(brief)
    assert validate_reply(answer, brief)["is_valid"] and "garantie" not in answer["answer"]


# ---- intégration avec le pipeline de l'agent conversationnel (analysis_pipeline.answer_question) ----

CONFIG = BedrockConfig(mode="bedrock", analyst_model_id="m", explainer_model_id="m", conversation_model_id="m-conv",
                       guardrail_id="g-test", guardrail_version="1")
PASSED = {"check": "request_topic", "action": "none", "denied_topics": [], "grounding_score": None,
          "relevance_score": None, "mode": "block"}


class FakeClient:
    """Bedrock simulé : réponses Converse en file, garde-fou qui rend un score sans intervenir."""

    def __init__(self, texts):
        self.config = CONFIG
        self.texts = list(texts)
        self.calls = 0
        self.last_grounding_flags = {}

    def converse(self, model_id, messages, system=None, inference_config=None):
        self.calls += 1
        text = self.texts.pop(0)
        return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": "end_turn"}

    def check_output_grounding(self, source, query, answer):
        return {"check": "output_grounding", "action": "none", "denied_topics": [], "grounding_score": 0.9,
                "relevance_score": 0.9, "mode": "detect"}


def test_offline_pipeline_now_answers_with_the_code_reply_and_validates_it():
    brief = make_brief("explanation")
    result = answer_question(brief, "offline", config=CONFIG)
    assert result["reply"]["origin"] == "template"
    assert result["reply"]["answer"] != CONVERSATION_UNAVAILABLE
    assert result["validation"]["is_valid"] and "validation_skipped" not in result
    assert QUESTION not in str(result["trace"])


def test_bedrock_pipeline_calls_the_model_now_that_the_validator_exists():
    brief = make_brief("explanation")
    good = '{"answer": "La regle [G1] est en conflit : la mesure atteint [E1]."}'
    client = FakeClient([good])
    result = answer_question(brief, "bedrock", config=CONFIG, client=client, request_check=PASSED)
    assert client.calls == 1
    assert result["reply"]["origin"] == "llm" and result["validation"]["is_valid"]


def test_bedrock_pipeline_replaces_advice_by_the_code_reply():
    brief = make_brief("explanation")
    advice = '{"answer": "Je vous recommande de vendre TSLA [E1]."}'
    client = FakeClient([advice, advice])
    result = answer_question(brief, "bedrock", config=CONFIG, client=client, request_check=PASSED)
    assert client.calls == 2                                   # un nouvel essai, puis le code
    assert result["reply"]["origin"] == "template"
    assert result["reply"]["answer"] == cf.build_fallback_reply(brief)["answer"]
    assert "forbidden_term" in result["trace"][0]["details"]["rejection_codes"]
    assert result["validation"]["is_valid"]


def test_bedrock_pipeline_rejects_a_changed_status():
    brief = make_brief("explanation")
    lie = '{"answer": "La regle [G1] est conforme : tout va bien [E1]."}'
    result = answer_question(brief, "bedrock", config=CONFIG, client=FakeClient([lie, lie]), request_check=PASSED)
    assert result["reply"]["origin"] == "template"
    assert "wrong_status" in result["trace"][0]["details"]["rejection_codes"]


def test_refused_request_never_reaches_the_model():
    brief = make_brief("explanation")
    refused = {**PASSED, "action": "intervened", "denied_topics": ["conseil_personnalise"]}
    client = FakeClient([])
    result = answer_question(brief, "bedrock", config=CONFIG, client=client, request_check=refused)
    assert client.calls == 0 and result["reply"]["origin"] == "template"
    assert validate_reply(result["reply"], brief)["is_valid"]


def test_validator_accepts_its_own_code_reply_for_the_example_reply_form():
    brief = make_brief("explanation")
    sample = reply("La regle [G3] est en tension : la perte maximale du portefeuille atteint [E3].", brief)
    assert validate_reply(sample, brief)["is_valid"]
