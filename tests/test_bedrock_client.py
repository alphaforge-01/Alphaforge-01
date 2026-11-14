"""Tests du client Bedrock. Aucun appel reseau : doubles ecrits a la main."""
from pathlib import Path
import sys

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.bedrock_client import (
    GROUNDING_ANSWER_MAX_CHARS, GROUNDING_QUERY_MAX_CHARS, GROUNDING_SOURCE_MAX_CHARS,
    BedrockAuthError, BedrockClient, BedrockConfig, BedrockError, BedrockThrottledError,
    extract_text, extract_tool_uses, parse_guardrail_response,
    redact, redact_text, tool_result_message,
)

FAKE_ACCOUNT = "1111" + "2222" + "3333"
FAKE_ARN = f"arn:aws:iam::{FAKE_ACCOUNT}:role/fake-role"


def client_error(code, message="erreur", operation="Converse"):
    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


class FakeRuntime:
    """Double de bedrock-runtime : rend ou leve la sequence fournie."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def _next(self, name, kwargs):
        self.calls.append((name, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def converse(self, **kwargs):
        return self._next("converse", kwargs)

    def apply_guardrail(self, **kwargs):
        return self._next("apply_guardrail", kwargs)


def make_client(outcomes, config=None, **kwargs):
    sleeps = []
    client = BedrockClient(
        config or BedrockConfig(), FakeRuntime(outcomes),
        sleep=sleeps.append, jitter=lambda: 1.0, **kwargs)
    return client, sleeps


# ---- configuration ----

def test_config_defaults():
    config = BedrockConfig.from_env({})
    assert config.region == "us-east-1"
    assert config.mode == "offline"
    assert config.analyst_model_id is None and config.explainer_model_id is None
    assert not config.can_call_models and not config.has_guardrail


def test_config_explainer_falls_back_on_analyst():
    config = BedrockConfig.from_env({"ALPHAFORGE_ANALYST_MODEL_ID": "model-a"})
    assert config.explainer_model_id == "model-a"
    config = BedrockConfig.from_env({
        "ALPHAFORGE_ANALYST_MODEL_ID": "model-a", "ALPHAFORGE_EXPLAINER_MODEL_ID": "model-b"})
    assert config.explainer_model_id == "model-b"


def test_config_mode_lowercase_and_empty_values_ignored():
    config = BedrockConfig.from_env({
        "ALPHAFORGE_MODE": " BEDROCK ", "ALPHAFORGE_ANALYST_MODEL_ID": "m",
        "AWS_REGION": "  ", "ALPHAFORGE_GUARDRAIL_ID": "", "ALPHAFORGE_GUARDRAIL_VERSION": "1",
    })
    assert config.mode == "bedrock"
    assert config.region == "us-east-1"
    assert config.guardrail_id is None
    assert config.can_call_models
    assert not config.has_guardrail


def test_config_guardrail_needs_id_and_version():
    config = BedrockConfig.from_env({
        "ALPHAFORGE_GUARDRAIL_ID": "g", "ALPHAFORGE_GUARDRAIL_VERSION": "2", "AWS_REGION": "us-west-2"})
    assert config.has_guardrail and config.region == "us-west-2"


# ---- extraction ----

def test_extract_text_ignores_blocks_without_text():
    response = {"output": {"message": {"content": [
        {"reasoningContent": {"x": 1}}, {"toolUse": {"name": "t"}},
        {"text": "Bonjour "}, {"text": "monde"}]}}}
    assert extract_text(response) == "Bonjour monde"


def test_extract_text_missing_structure():
    assert extract_text({}) == ""
    assert extract_text({"output": {"message": {"content": []}}}) == ""


def test_extract_tool_uses():
    response = {"output": {"message": {"content": [
        {"text": "x"}, {"toolUse": {"toolUseId": "u1", "name": "a", "input": {}}},
        {"toolUse": {"toolUseId": "u2", "name": "b", "input": {"k": 1}}}]}}}
    uses = extract_tool_uses(response)
    assert [u["toolUseId"] for u in uses] == ["u1", "u2"]
    assert extract_tool_uses({}) == []


def test_tool_result_message_json_vs_text_and_error():
    message = tool_result_message("u1", {"a": 1})
    assert message["role"] == "user"
    block = message["content"][0]["toolResult"]
    assert block["toolUseId"] == "u1" and block["content"] == [{"json": {"a": 1}}]
    assert "status" not in block
    block = tool_result_message("u2", "texte", is_error=True)["content"][0]["toolResult"]
    assert block["content"] == [{"text": "texte"}] and block["status"] == "error"


# ---- delai exponentiel ----

def test_throttling_then_success_with_capped_delays():
    ok = {"output": {}}
    client, sleeps = make_client(
        [client_error("ThrottlingException")] * 6 + [ok], max_retries=6)
    assert client.converse("m", []) == ok
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 20.0]
    assert client.retry_count == 6


def test_delay_uses_jitter_factor():
    sleeps = []
    client = BedrockClient(
        BedrockConfig(), FakeRuntime([client_error("ThrottlingException"), {}]),
        sleep=sleeps.append, jitter=lambda: 0.0)
    client.converse("m", [])
    assert sleeps == [0.5]


def test_throttling_exhausted_raises():
    client, sleeps = make_client([client_error("ThrottlingException")] * 3, max_retries=2)
    with pytest.raises(BedrockThrottledError) as info:
        client.converse("m", [])
    assert len(client.runtime.calls) == 3 and len(sleeps) == 2
    assert info.value.code == "ThrottlingException"


@pytest.mark.parametrize("code", ["ExpiredTokenException", "AccessDeniedException"])
def test_auth_errors_not_retried(code):
    client, sleeps = make_client([client_error(code), {}])
    with pytest.raises(BedrockAuthError) as info:
        client.converse("m", [])
    assert len(client.runtime.calls) == 1 and sleeps == []
    assert info.value.code == code


def test_no_credentials_raises_auth_error():
    client, sleeps = make_client([NoCredentialsError()])
    with pytest.raises(BedrockAuthError):
        client.converse("m", [])
    assert sleeps == []


def test_other_client_error_is_bedrock_error_not_retried():
    client, sleeps = make_client([client_error("ValidationException")])
    with pytest.raises(BedrockError) as info:
        client.converse("m", [])
    assert not isinstance(info.value, (BedrockAuthError, BedrockThrottledError))
    assert info.value.code == "ValidationException" and sleeps == []


def test_error_message_does_not_leak_account_or_arn():
    message = f"User {FAKE_ARN} in account {FAKE_ACCOUNT} is not authorized"
    for code in ("ValidationException", "AccessDeniedException", "ThrottlingException"):
        client, _ = make_client([client_error(code, message)] * 5, max_retries=1)
        with pytest.raises(BedrockError) as info:
            client.converse("m", [])
        text = str(info.value)
        assert FAKE_ACCOUNT not in text and "arn:aws" not in text


def test_bedrock_error_redacts_its_own_message():
    error = BedrockError(f"echec {FAKE_ARN} compte {FAKE_ACCOUNT}")
    assert FAKE_ACCOUNT not in str(error) and "arn:aws" not in str(error)


def test_converse_builds_request():
    client, _ = make_client([{"ok": 1}])
    client.converse("model-x", [{"role": "user"}], system="sys", tool_config={"tools": []},
                    inference_config={"maxTokens": 5})
    name, kwargs = client.runtime.calls[0]
    assert name == "converse"
    assert kwargs["modelId"] == "model-x" and kwargs["system"] == [{"text": "sys"}]
    assert kwargs["inferenceConfig"] == {"maxTokens": 5}


# ---- masquage ----

def test_redact_text_patterns():
    akia = "AKIA" + "X" * 16
    asia = "ASIA" + "Z" * 16
    api = "bedrock-api-key-" + "Y" * 20
    text = f"{akia} {asia} {api} {FAKE_ARN} compte {FAKE_ACCOUNT} fin"
    out = redact_text(text)
    for secret in (akia, asia, api, FAKE_ARN, FAKE_ACCOUNT):
        assert secret not in out
    assert "[CLE_AWS_MASQUEE]" in out and "[CLE_BEDROCK_MASQUEE]" in out
    assert "[ARN_MASQUE]" in out and "[COMPTE_MASQUE]" in out


def test_redact_text_keeps_innocent_numbers():
    assert redact_text("capital 100000 et 1234567890123") == "capital 100000 et 1234567890123"


def test_redact_text_session_token_assignment():
    out = redact_text("aws_session_token=" + "q" * 30)
    assert "q" * 30 not in out


def test_redact_nested_structure_and_sensitive_keys():
    akia = "AKIA" + "X" * 16
    data = {
        "api_key": "valeur", "SecretAccessKey": "v2", "note": f"cle {akia}",
        "items": [{"password": "p", "ok": 3}, f"compte {FAKE_ACCOUNT}"],
        "token": None,
    }
    out = redact(data)
    assert out["api_key"] == "[MASQUE]" and out["SecretAccessKey"] == "[MASQUE]"
    assert akia not in out["note"]
    assert out["items"][0] == {"password": "[MASQUE]", "ok": 3}
    assert FAKE_ACCOUNT not in out["items"][1]
    assert out["token"] is None
    assert data["api_key"] == "valeur"  # l'entree n'est pas modifiee


# ---- garde-fou ----

def test_parse_guardrail_none_and_no_assessments():
    result = parse_guardrail_response({"action": "NONE"}, check="request_topic")
    assert result == {
        "check": "request_topic", "action": "none", "denied_topics": [],
        "grounding_score": None, "relevance_score": None, "mode": "detect"}
    assert parse_guardrail_response({"assessments": None}, check="output_grounding")["action"] == "none"


def test_parse_guardrail_topics_deduplicated_sorted():
    response = {"action": "GUARDRAIL_INTERVENED", "assessments": [
        {"topicPolicy": {"topics": [
            {"name": "trade_execution", "action": "BLOCKED"},
            {"name": "personal_advice", "action": "BLOCKED"},
            {"name": "personal_advice", "action": "DETECTED"},
            {"name": "ignore", "action": "NONE"}]}}]}
    result = parse_guardrail_response(response, check="request_topic", mode="block")
    assert result["action"] == "intervened" and result["mode"] == "block"
    assert result["denied_topics"] == ["personal_advice", "trade_execution"]


def test_parse_guardrail_scores_keep_minimum():
    response = {"action": "NONE", "assessments": [
        {"contextualGroundingPolicy": {"filters": [
            {"type": "GROUNDING", "score": 0.9}, {"type": "RELEVANCE", "score": 0.8}]}},
        {"contextualGroundingPolicy": {"filters": [
            {"type": "GROUNDING", "score": 0.4}, {"type": "RELEVANCE", "score": 0.95},
            {"type": "GROUNDING"}]}}]}
    result = parse_guardrail_response(response, check="output_grounding")
    assert result["grounding_score"] == 0.4 and result["relevance_score"] == 0.8


def test_grounding_not_run_over_limits_without_calling_double():
    cases = [
        ("s" * (GROUNDING_SOURCE_MAX_CHARS + 1), "q", "a"),
        ("s", "q" * (GROUNDING_QUERY_MAX_CHARS + 1), "a"),
        ("s", "q", "a" * (GROUNDING_ANSWER_MAX_CHARS + 1)),
    ]
    for source, query, answer in cases:
        client, _ = make_client([], config=BedrockConfig(guardrail_id="g", guardrail_version="1"))
        result = client.check_output_grounding(source, query, answer)
        assert result["action"] == "not_run" and result["check"] == "output_grounding"
        assert client.runtime.calls == []


def test_grounding_builds_three_blocks_with_qualifiers():
    config = BedrockConfig(guardrail_id="g1", guardrail_version="3")
    response = {"action": "NONE", "assessments": [
        {"contextualGroundingPolicy": {"filters": [{"type": "GROUNDING", "score": 0.7}]}}]}
    client, _ = make_client([response], config=config)
    result = client.check_output_grounding("dossier", "question", "reponse")
    name, kwargs = client.runtime.calls[0]
    assert name == "apply_guardrail" and kwargs["source"] == "OUTPUT"
    assert kwargs["guardrailIdentifier"] == "g1" and kwargs["guardrailVersion"] == "3"
    assert [b["text"]["qualifiers"] for b in kwargs["content"]] == [
        ["grounding_source"], ["query"], ["guard_content"]]
    assert [b["text"]["text"] for b in kwargs["content"]] == ["dossier", "question", "reponse"]
    assert result["grounding_score"] == 0.7


def test_check_request_topic_uses_input_source():
    client, _ = make_client(
        [{"action": "GUARDRAIL_INTERVENED", "assessments": [
            {"topicPolicy": {"topics": [{"name": "x", "action": "BLOCKED"}]}}]}],
        config=BedrockConfig(guardrail_id="g", guardrail_version="1"))
    result = client.check_request_topic("texte")
    assert client.runtime.calls[0][1]["source"] == "INPUT"
    assert result["action"] == "intervened" and result["denied_topics"] == ["x"]


def test_apply_guardrail_without_configuration_raises():
    client, _ = make_client([])
    with pytest.raises(BedrockError):
        client.apply_guardrail("INPUT", [])
    assert client.runtime.calls == []
