"""Tests de l'agent explicateur. Aucun appel reseau ni AWS : client Converse scripte ecrit a la main."""
from pathlib import Path
import copy
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.bedrock_client import BedrockError
from alphaforge.explainer_agent import (
    INFERENCE_CONFIG, PROMPT_VERSION, explain_with_llm, parse_output,
)
from alphaforge.prompt_loader import load_prompt
from alphaforge.tool_specs import AgentFailure, ExplainerFailure

FIXTURES = Path(__file__).parent / "fixtures"
MODEL = "model-test"
BRIEF = json.loads((FIXTURES / "explanation_brief_robert_novice.json").read_text(encoding="utf-8"))


def good_slots(**overrides):
    slots = {
        "summary": "La regle [G1] est en conflit selon [E1].",
        "factors": [{"check_id": "G1", "text": "La regle [G1] est en conflit."}],
        "counterfactual": "Voir le seuil de la regle [G1].",
        "variants": "Aucune variante.",
        "limits_context": "Donnees fictives.",
    }
    slots.update(overrides)
    return slots


def reply(text, *, extra_blocks=()):
    content = list(extra_blocks) + [{"text": text}]
    return {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": "end_turn"}


class ScriptedClient:
    """Client Converse factice : rend les reponses de la file et enregistre chaque appel."""

    def __init__(self, responses):
        self._queue = list(responses)
        self.calls = []

    def converse(self, model_id, messages, *, system=None, tool_config=None, inference_config=None, **kwargs):
        self.calls.append({"model_id": model_id, "messages": copy.deepcopy(messages), "system": system,
                           "tool_config": tool_config, "inference_config": inference_config, "kwargs": kwargs})
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def accept(output, brief):
    return {"is_valid": True, "rejections": [], "checked_references": []}


def reject(output, brief):
    return {"is_valid": False, "rejections": [{"code": "number_outside_registry", "excerpt": "99 %"},
                                              {"code": "unknown_reference", "excerpt": "E9"}],
            "checked_references": []}


def parse(text):
    return parse_output(text, BRIEF, model_id=MODEL, attempt=1)


# ---- parse_output ----

def test_parse_bare_json():
    output, problem = parse(json.dumps(good_slots()))
    assert problem is None
    assert output["summary"] == good_slots()["summary"]
    assert output["brief_id"] == BRIEF["brief_id"] and output["level"] == BRIEF["level"]
    assert output["origin"] == "llm" and output["model_id"] == MODEL
    assert output["prompt_version"] == PROMPT_VERSION and output["attempt"] == 1
    assert output["factors"] == [{"check_id": "G1", "text": "La regle [G1] est en conflit."}]


def test_parse_json_in_fenced_block():
    output, problem = parse("```json\n" + json.dumps(good_slots()) + "\n```")
    assert problem is None and output["counterfactual"] == good_slots()["counterfactual"]


def test_parse_text_around_object():
    output, problem = parse("Voici ma reponse :\n" + json.dumps(good_slots()) + "\nBonne journee.")
    assert problem is None and output is not None


@pytest.mark.parametrize("text, message", [
    ("Aucune accolade ici.", "Aucun objet JSON trouve dans la reponse."),
    ("{ ceci n'est pas du json }", "JSON invalide."),
    ("{}", "Emplacement manquant ou invalide : summary."),
])
def test_parse_error_messages(text, message):
    output, problem = parse(text)
    assert output is None and problem == message


def test_parse_array_without_braces_is_not_found():
    # le message "doit etre un objet JSON" est inatteignable : l'extraction entre accolades rend toujours un objet
    output, problem = parse("[1, 2]")
    assert output is None and problem == "Aucun objet JSON trouve dans la reponse."


def test_parse_missing_string_slot_names_the_slot():
    for slot in ("summary", "counterfactual", "variants", "limits_context"):
        slots = good_slots()
        del slots[slot]
        output, problem = parse(json.dumps(slots))
        assert output is None and problem == f"Emplacement manquant ou invalide : {slot}."
    output, problem = parse(json.dumps(good_slots(summary=12)))
    assert output is None and "summary" in problem


@pytest.mark.parametrize("factors", [
    "pas une liste", [{"check_id": "G1"}], [{"check_id": 1, "text": "x"}], ["texte"], None,
])
def test_parse_invalid_factors(factors):
    output, problem = parse(json.dumps(good_slots(factors=factors)))
    assert output is None and problem == "Emplacement factors invalide : liste de {check_id, text}."


def test_parse_empty_factors_list_is_accepted():
    output, problem = parse(json.dumps(good_slots(factors=[])))
    assert problem is None and output["factors"] == []


# ---- explain_with_llm ----

def test_first_attempt_success():
    client = ScriptedClient([reply(json.dumps(good_slots()), extra_blocks=[{"reasoningContent": {"x": 1}}])])
    output = explain_with_llm(client, MODEL, BRIEF, accept)
    assert output["origin"] == "llm" and output["attempt"] == 1
    assert output["model_id"] == MODEL and output["prompt_version"] == "explainer_v1"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["tool_config"] is None and "toolConfig" not in call["kwargs"]
    assert call["system"] == load_prompt("explainer_v1") and call["system"]
    assert call["inference_config"] == INFERENCE_CONFIG
    user_text = call["messages"][0]["content"][0]["text"]
    assert call["messages"][0]["role"] == "user"
    assert json.dumps(BRIEF, ensure_ascii=False) in user_text


def test_validator_rejects_then_accepts_on_second_attempt():
    verdicts = [reject, accept]
    seen = []

    def validate(output, brief):
        seen.append(output["attempt"])
        return verdicts.pop(0)(output, brief)

    first = reply(json.dumps(good_slots(summary="Gain de 99 % [E9].")))
    second = reply(json.dumps(good_slots()))
    client = ScriptedClient([first, second])
    output = explain_with_llm(client, MODEL, BRIEF, validate)
    assert output["attempt"] == 2 and seen == [1, 2]
    messages = client.calls[1]["messages"]
    assert len(messages) == 3
    assert messages[1] == first["output"]["message"]
    correction = messages[2]
    assert correction["role"] == "user"
    text = correction["content"][0]["text"]
    assert "number_outside_registry" in text and "unknown_reference" in text


def test_rejected_twice_returns_second_output_anyway():
    client = ScriptedClient([reply(json.dumps(good_slots())), reply(json.dumps(good_slots(summary="Autre.")))])
    output = explain_with_llm(client, MODEL, BRIEF, reject)
    assert output["attempt"] == 2 and output["summary"] == "Autre."
    assert len(client.calls) == 2


def test_invalid_json_twice_raises_explainer_failure():
    client = ScriptedClient([reply("pas de json"), reply("{ casse }")])
    with pytest.raises(ExplainerFailure) as info:
        explain_with_llm(client, MODEL, BRIEF, accept)
    assert "JSON invalide" in str(info.value)
    assert len(client.calls) == 2


def test_invalid_json_then_valid_succeeds_with_correction_message():
    client = ScriptedClient([reply("pas de json"), reply(json.dumps(good_slots()))])
    output = explain_with_llm(client, MODEL, BRIEF, accept)
    assert output["attempt"] == 2
    assert "Aucun objet JSON" in client.calls[1]["messages"][2]["content"][0]["text"]


@pytest.mark.parametrize("model_id", [None, ""])
def test_missing_model_id_raises_without_call(model_id):
    client = ScriptedClient([])
    with pytest.raises(ExplainerFailure):
        explain_with_llm(client, model_id, BRIEF, accept)
    assert client.calls == []


def test_client_bedrock_error_propagates():
    client = ScriptedClient([BedrockError("panne")])
    with pytest.raises(BedrockError):
        explain_with_llm(client, MODEL, BRIEF, accept)


def test_explainer_failure_is_an_agent_failure():
    assert issubclass(ExplainerFailure, AgentFailure)
