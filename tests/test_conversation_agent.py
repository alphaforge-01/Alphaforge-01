"""Agent conversationnel (issue 78) : appel Bedrock sous controle, replis du code, garde-fou, trace."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alphaforge import conversation_agent as ca  # noqa: E402
from alphaforge.analysis_pipeline import CONVERSATION_UNAVAILABLE, answer_question, run_analysis  # noqa: E402
from alphaforge.bedrock_client import BedrockConfig, BedrockError  # noqa: E402
from alphaforge.fixture_collaborators import fixture_deps  # noqa: E402
from alphaforge.prompt_loader import load_prompt  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
QUESTION = "Pourquoi mon idee est-elle en conflit ? MARQUEUR-QUESTION"
CONFIG = BedrockConfig(mode="bedrock", analyst_model_id="m", explainer_model_id="m", conversation_model_id="m-conv",
                       guardrail_id="g-test", guardrail_version="1")


PASSED = {"check": "request_topic", "action": "none", "denied_topics": [], "grounding_score": None,
          "relevance_score": None, "mode": "block"}


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def brief():
    deps = fixture_deps()
    result = run_analysis(_load("profile_robert.json"), _load("portfolio_robert.json"), _load("idea_tsla_25.json"),
                          deps=deps, config=BedrockConfig())
    explanation_brief = deps.build_brief(result, "novice")
    return {
        "brief_id": "conv-test", "level": "novice", "answer_kind": "explanation",
        "focus": [explanation_brief["checks"][0]["check_id"]], "question": QUESTION,
        "profile_context": explanation_brief.get("profile_context"),
        "evidence": explanation_brief["evidence"], "checks": explanation_brief["checks"],
        "idea": explanation_brief["idea"], "glossary": explanation_brief["glossary"],
        "limits": explanation_brief["limits"], "cards": [], "missing": [],
    }


def _evidence_id(brief):
    return next(e["evidence_id"] for e in brief["evidence"] if e.get("display_value") and e.get("value") is not None)


def validate_ok(reply, brief):
    bad = "INVALIDE" in reply["answer"]
    return {"is_valid": not bad, "checked_references": ["E1"],
            "rejections": [{"code": "forbidden_term", "slot": "answer", "excerpt": "INVALIDE"}] if bad else []}


def code_fallback(brief):
    return {"brief_id": brief["brief_id"], "answer": "REPONSE-DU-CODE.", "origin": "template",
            "model_id": None, "prompt_version": None, "attempt": 0}


@pytest.fixture()
def without_flux_b(monkeypatch):
    """Simule l'absence des modules du flux B : un `None` passé reste absent (sans import des vrais)."""
    from alphaforge import analysis_pipeline
    monkeypatch.setattr(analysis_pipeline, "_conversation_collaborators", lambda validate, fallback: (validate, fallback))


def converse_response(text, stop="end_turn"):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": stop}


class FakeClient:
    """Client Bedrock simule : reponses Converse en file, resultat du garde-fou au choix."""

    def __init__(self, texts=(), action="none", score=0.9, flags=None, config=CONFIG, request_check=PASSED):
        self.config = config
        self.texts = list(texts)
        self.calls = []
        self.guard_calls = []
        self.action, self.score = action, score
        self.last_grounding_flags = flags or {}

    def converse(self, model_id, messages, system=None, inference_config=None):
        self.calls.append({"model_id": model_id, "messages": copy.deepcopy(messages), "system": system})
        return converse_response(self.texts.pop(0))

    def check_output_grounding(self, source, query, answer):
        self.guard_calls.append({"source": source, "query": query, "answer": answer})
        return {"check": "output_grounding", "action": self.action, "denied_topics": [],
                "grounding_score": self.score, "relevance_score": 0.9, "mode": "detect"}


# ---- prompt et dossier envoye ----

def test_prompt_states_the_rules_and_treats_the_question_as_data():
    prompt = load_prompt("conversation_v1")
    for needle in ("REGLE 1", "REGLE 2", "REGLE 4", "REGLE 5", "REGLE 7", "REGLE 8", "REGLE 9", "grave",
                   "bonne idee", "a votre place", '{"answer"', "profile_context", "missing"):
        assert needle in prompt
    assert chr(0x2014) not in prompt
    assert ca.PROMPT_NAME == "conversation_v1"


def test_model_brief_truncates_the_question_without_touching_the_original(brief):
    long_brief = {**brief, "question": "x" * 1000}
    sent = ca.model_brief(long_brief)
    assert len(sent["question"]) == ca.MAX_QUESTION_CHARS and len(long_brief["question"]) == 1000
    assert ca.model_brief({**brief, "question": None})["question"] == ""


@pytest.mark.parametrize("text,problem", [
    ("pas de json", "Aucun objet JSON"),
    ('{"answer": ""}', "manquant ou vide"),
    ('{"autre": "x"}', "manquant ou vide"),
    ('{"answer": "voir https://exemple.test"}', "lien"),
    ('{"answer": "<img src=x>"}', "lien"),
])
def test_parse_rejects_unusable_replies(brief, text, problem):
    reply, found = ca.parse_reply(text, brief, model_id="m", attempt=1)
    assert reply is None and problem in found


def test_parse_accepts_a_fenced_json_reply(brief):
    reply, problem = ca.parse_reply('```json\n{"answer": "La regle [G1] est en conflit."}\n```', brief,
                                    model_id="m", attempt=1)
    assert problem is None and reply["origin"] == "llm" and reply["answer"] == "La regle [G1] est en conflit."
    assert reply["prompt_version"] == "conversation_v1" and reply["brief_id"] == "conv-test"


# ---- boucle de l'agent ----

def test_reply_with_llm_sends_the_brief_and_retries_once_after_a_rejection(brief):
    client = FakeClient(['{"answer": "INVALIDE [G1]"}', '{"answer": "La regle [G1] est en conflit."}'])
    reply = ca.reply_with_llm(client, "m-conv", brief, validate_ok)
    assert reply["attempt"] == 2 and "INVALIDE" not in reply["answer"]
    assert len(client.calls) == 2 and client.calls[0]["system"] == load_prompt("conversation_v1")
    first_message = client.calls[0]["messages"][0]["content"][0]["text"]
    assert "MARQUEUR-QUESTION" in first_message                 # la question est transmise au modele
    feedback = client.calls[1]["messages"][-1]["content"][0]["text"]
    assert "rejetee" in feedback and "forbidden_term" in feedback


def test_reply_with_llm_fails_without_model_id_or_without_any_parsable_reply(brief):
    with pytest.raises(ca.ConversationFailure):
        ca.reply_with_llm(FakeClient(), None, brief, validate_ok)
    with pytest.raises(ca.ConversationFailure):
        ca.reply_with_llm(FakeClient(["rien", "toujours rien"]), "m", brief, validate_ok)


def test_reply_with_llm_handles_a_truncated_answer(brief):
    class Truncated(FakeClient):
        def converse(self, model_id, messages, system=None, inference_config=None):
            self.calls.append(messages)
            return converse_response('{"answer": "coupe', stop="max_tokens") if len(self.calls) == 1 \
                else converse_response('{"answer": "La regle [G1] est en conflit."}')

    reply = ca.reply_with_llm(Truncated(), "m", brief, validate_ok)
    assert reply["attempt"] == 2


# ---- pipeline : chemins du texte du modele et replis ----

def test_offline_uses_the_code_reply_without_calling_bedrock(brief):
    result = answer_question(brief, "offline", validate=validate_ok, fallback=code_fallback)
    assert result["reply"]["origin"] == "template" and result["rendered_answer"] == "REPONSE-DU-CODE."
    assert [s["name"] for s in result["trace"]] == ["explanation", "validation", "guardrail"]
    assert result["trace"][2]["status"] == "skipped"


def test_without_any_code_reply_a_fixed_sentence_is_shown(brief, without_flux_b):
    result = answer_question(brief, "offline", validate=validate_ok, fallback=None)
    assert result["reply"]["answer"] == CONVERSATION_UNAVAILABLE
    assert not any(ch.isdigit() for ch in CONVERSATION_UNAVAILABLE)


def test_bedrock_happy_path_substitutes_references_and_keeps_the_question_out_of_the_trace(brief):
    evidence_id = _evidence_id(brief)
    shown = next(e["display_value"] for e in brief["evidence"] if e["evidence_id"] == evidence_id)
    client = FakeClient([json.dumps({"answer": f"La mesure atteint [{evidence_id}]."})])
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    assert result["reply"]["origin"] == "llm" and shown in result["rendered_answer"]
    assert client.calls[0]["model_id"] == "m-conv"
    guard = client.guard_calls[0]
    assert shown in guard["answer"] and "MARQUEUR-QUESTION" in guard["query"]
    assert "MARQUEUR-QUESTION" not in guard["source"]           # la source est le dossier, pas la question
    assert "MARQUEUR-QUESTION" not in json.dumps(result["trace"])
    assert result["trace"][0]["actor"] == "agent" and result["trace"][0]["model_id"] == "m-conv"


def test_a_reply_rejected_twice_is_replaced_by_the_code_reply(brief):
    client = FakeClient(['{"answer": "INVALIDE un"}', '{"answer": "INVALIDE deux"}'])
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    assert result["reply"]["origin"] == "template" and result["rendered_answer"] == "REPONSE-DU-CODE."
    step = result["trace"][0]
    assert step["status"] == "fallback" and step["details"]["fallback_reason"] == "rejet_du_validateur"
    assert result["validation"]["is_valid"] is True


@pytest.mark.parametrize("action,score,reason", [
    ("intervened", None, "garde_fou_sortie"),
    ("none", None, "garde_fou_indisponible"),
    ("not_run", None, "garde_fou_indisponible"),
])
def test_an_intervention_or_no_score_replaces_the_model_reply(brief, action, score, reason):
    client = FakeClient(['{"answer": "La regle [G1] est en conflit."}'], action=action, score=score)
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    assert result["reply"]["origin"] == "template"
    assert result["trace"][0]["details"]["fallback_reason"] == reason
    assert result["trace"][2]["details"]["replaced_by_template"] is True


def test_a_weak_grounding_keeps_the_model_reply_with_a_signal(brief):
    client = FakeClient(['{"answer": "La regle [G1] est en conflit."}'], score=0.12,
                        flags={"below_threshold": True, "filters": ["GROUNDING"]})
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    details = result["trace"][2]["details"]
    assert result["reply"]["origin"] == "llm"
    assert details["grounding_weak"] is True and details["grounding_very_weak"] is True
    assert "replaced_by_template" not in details


def test_without_guardrail_or_validator_no_model_text_is_produced(brief, without_flux_b):
    called = []

    def runner(*args):
        called.append(args)
        return {"brief_id": "conv-test", "answer": "texte", "origin": "llm", "model_id": "m",
                "prompt_version": "conversation_v1", "attempt": 1}

    no_guard = BedrockConfig(mode="bedrock", analyst_model_id="m", conversation_model_id="m")
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=FakeClient(),
                             config=no_guard, runner=runner, request_check=PASSED)
    assert result["trace"][0]["details"]["fallback_reason"] == "garde_fou_non_configure"
    result = answer_question(brief, "bedrock", validate=None, fallback=code_fallback, client=FakeClient(),
                             config=CONFIG, runner=runner, request_check=PASSED)
    assert result["trace"][0]["details"]["fallback_reason"] == "validateur_indisponible"
    assert called == [] and result["reply"]["origin"] == "template"


def test_an_agent_error_falls_back_to_the_code_with_a_masked_reason(brief):
    def runner(*args):
        raise BedrockError("ThrottlingException AKIA" + "Q" * 16)

    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=FakeClient(),
                             config=CONFIG, runner=runner, request_check=PASSED)
    reason = result["trace"][0]["details"]["fallback_reason"]
    assert result["reply"]["origin"] == "template" and reason.startswith("BedrockError")
    assert "AKIA" + "Q" * 16 not in reason


def test_a_failing_code_fallback_still_gives_the_fixed_sentence(brief):
    def broken(brief):
        raise RuntimeError("boom")

    assert answer_question(brief, "offline", validate=validate_ok, fallback=broken)["reply"]["answer"] \
        == CONVERSATION_UNAVAILABLE


# ---- source d'ancrage et configuration ----

def test_grounding_source_without_idea_uses_profile_evidence_and_missing_items(brief):
    profile_brief = {**brief, "idea": None, "answer_kind": "profile", "missing": ["capacite a absorber une perte"],
                     "profile_context": {"objective": "Preserver le capital", "horizon_years_min": 3,
                                         "horizon_years_max": 5}}
    source, kind = ca.grounding_source(profile_brief)
    assert kind == "sentences"
    assert "Preserver le capital" in source and "capacite a absorber une perte" in source
    assert "MARQUEUR-QUESTION" not in source


def test_grounding_source_with_an_idea_reuses_the_explanation_source(brief):
    source, kind = ca.grounding_source(brief)
    assert kind == "sentences" and "MARQUEUR-QUESTION" not in source and len(source) > 200


def test_conversation_model_is_read_from_the_environment_with_a_fallback():
    env = {"ALPHAFORGE_ANALYST_MODEL_ID": "a", "ALPHAFORGE_EXPLAINER_MODEL_ID": "e"}
    assert BedrockConfig.from_env(env).conversation_model_id == "e"
    assert BedrockConfig.from_env({**env, "ALPHAFORGE_CONVERSATION_MODEL_ID": "c"}).conversation_model_id == "c"


# ---- cas ajoutes apres la revue de code ----

def _raising_validate(reply, brief):
    raise RuntimeError("validateur casse")


def test_a_validator_error_never_lets_the_model_text_through(brief):
    client = FakeClient(['{"answer": "La regle [G1] est en conflit."}'])

    def runner(c, model_id, b, validate):
        return {"brief_id": "conv-test", "answer": "La regle [G1] est en conflit.", "origin": "llm",
                "model_id": "m", "prompt_version": "conversation_v1", "attempt": 1}

    result = answer_question(brief, "bedrock", validate=_raising_validate, fallback=code_fallback, client=client,
                             config=CONFIG, runner=runner, request_check=PASSED)
    assert result["reply"]["origin"] == "template" and result["rendered_answer"] == "REPONSE-DU-CODE."
    assert result["trace"][0]["details"]["rejection_codes"] == ["validator_error"]
    # la reponse du code n'a pas pu etre validee non plus : le resultat le dit, sans pretendre un controle
    assert result["validation"]["is_valid"] is False
    assert result["validation"]["rejections"][0]["code"] == "validator_error"


def test_the_guardrail_on_a_code_reply_after_a_rejection_keeps_the_first_reason(brief):
    client = FakeClient(['{"answer": "INVALIDE un"}', '{"answer": "INVALIDE deux"}'], action="intervened", score=None)
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    assert result["reply"]["origin"] == "template"
    assert result["trace"][0]["details"]["fallback_reason"] == "rejet_du_validateur"
    assert result["trace"][0]["details"]["llm_attempt"] == 2          # l'essai du modele reste mesurable
    assert "replaced_by_template" not in result["trace"][2]["details"]


def test_the_fixed_sentence_is_not_validated_and_says_so(brief, without_flux_b):
    result = answer_question(brief, "offline", validate=validate_ok, fallback=None)
    assert result["validation_skipped"] == "reponse_fixe"
    assert result["trace"][1]["status"] == "skipped"
    assert result["trace"][1]["details"]["skipped_reason"] == "reponse_fixe"


def test_low_relevance_is_reported_apart_from_weak_grounding(brief):
    client = FakeClient(['{"answer": "La regle [G1] est en conflit."}'], score=0.8,
                        flags={"below_threshold": True, "filters": ["RELEVANCE"]})
    details = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                              config=CONFIG, request_check=PASSED)["trace"][2]["details"]
    assert details["relevance_weak"] is True
    assert "grounding_weak" not in details and "grounding_below_threshold" not in details


def test_cited_evidence_is_returned_for_the_interface_sections(brief):
    evidence_id = _evidence_id(brief)
    client = FakeClient([json.dumps({"answer": f"La mesure atteint [{evidence_id}]."})])
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    assert result["cited_evidence"] == [evidence_id] and result["cited_terms"] == []


def test_a_malformed_brief_never_breaks_the_final_render(brief):
    broken = {**brief, "evidence": [{"label_fr": "sans identifiant"}]}
    result = answer_question(broken, "offline", validate=validate_ok, fallback=code_fallback)
    assert result["rendered_answer"] == "REPONSE-DU-CODE." and result["cited_evidence"] == []


def test_grounding_source_without_idea_states_the_check_statuses(brief):
    source, kind = ca.grounding_source({**brief, "idea": None, "answer_kind": "xray"})
    assert kind == "sentences" and "Contrôle " in source and "fictif" in source   # statuts et avertissement


# ---- cas ajoutes apres l'audit de securite ----

def test_a_rejected_reply_quoting_the_question_never_reaches_the_trace(brief):
    client = FakeClient(['{"answer": "INVALIDE MARQUEUR-QUESTION"}', '{"answer": "INVALIDE MARQUEUR-QUESTION"}'])
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    assert result["reply"]["origin"] == "template"
    assert "MARQUEUR-QUESTION" not in json.dumps(result["trace"])
    assert "rejection_excerpts" not in result["trace"][0]["details"]


@pytest.mark.parametrize("check,reason", [
    (None, "controle_entree_absent"),
    ({**PASSED, "action": "not_run"}, "controle_entree_absent"),
    ({**PASSED, "action": "intervened", "denied_topics": ["order_execution"]}, "demande_refusee"),
])
def test_the_model_is_never_called_without_a_passed_input_check(brief, check, reason):
    client = FakeClient(['{"answer": "La regle [G1] est en conflit."}'])
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=check)
    assert client.calls == [] and result["reply"]["origin"] == "template"
    assert result["trace"][0]["details"]["fallback_reason"] == reason


def test_a_detected_denied_topic_replaces_the_model_reply_even_without_intervention(brief):
    class TopicClient(FakeClient):
        def check_output_grounding(self, source, query, answer):
            result = super().check_output_grounding(source, query, answer)
            return {**result, "denied_topics": ["personalized_advice"]}

    client = TopicClient(['{"answer": "La regle [G1] est en conflit."}'])
    result = answer_question(brief, "bedrock", validate=validate_ok, fallback=code_fallback, client=client,
                             config=CONFIG, request_check=PASSED)
    assert result["reply"]["origin"] == "template"
    assert result["trace"][2]["details"]["denied_topics"] == ["personalized_advice"]
