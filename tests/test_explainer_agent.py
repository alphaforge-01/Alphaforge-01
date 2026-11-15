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
    # le message JSON invalide porte maintenant la cause et la position : on verifie son debut
    assert output is None and (problem == message or (message == "JSON invalide." and problem.startswith("JSON invalide (")))


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
    assert output["model_id"] == MODEL and output["prompt_version"] == "explainer_v4"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["tool_config"] is None and "toolConfig" not in call["kwargs"]
    assert call["system"] == load_prompt("explainer_v4") and call["system"]
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


# ---- retour de correction precis et prompt version 2 ----

def test_describe_rejections_lists_slot_code_excerpt_and_advice():
    from alphaforge.explainer_agent import describe_rejections
    text = describe_rejections([
        {"code": "forbidden_term", "slot": "summary", "excerpt": "...solide..."},
        {"code": "too_long", "slot": "variants", "excerpt": "500 caracteres pour 400 permis"},
        {"code": "forbidden_term", "slot": "factors[0]", "excerpt": "...gardez..."},
    ])
    assert "summary : forbidden_term" in text and "variants : too_long" in text and "factors[0]" in text
    assert text.count("Consignes") == 1 and "neutre" in text and "raccourcis" in text


def test_describe_rejections_is_bounded_and_masks_secrets():
    from alphaforge.explainer_agent import describe_rejections
    many = [{"code": "unknown_reference", "slot": "summary", "excerpt": f"[X{i}]"} for i in range(40)]
    assert describe_rejections(many).count("unknown_reference (") == 12
    leaked = describe_rejections([{"code": "forbidden_term", "slot": "s", "excerpt": "AKIA" + "Q" * 16}])
    assert "AKIA" + "Q" * 16 not in leaked


def test_prompt_v2_states_the_validator_rules():
    prompt = load_prompt("explainer_v4")
    for needle in ("REGLE 1", "REGLE 2", "REGLE 3", "REGLE 4", "REGLE 5", "max_chars_per_slot", "[LM1]", "il faut"):
        assert needle in prompt
    assert chr(0x2014) not in prompt   # regle 1 : aucun tiret cadratin dans le prompt


def test_trace_records_the_slot_of_each_rejection_without_any_model_text():
    from dataclasses import replace
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.fixture_collaborators import fixture_deps

    deps = fixture_deps()
    config = BedrockConfig(mode="bedrock", analyst_model_id="m", explainer_model_id="m",
                           guardrail_id="g-test", guardrail_version="1")
    profile = json.loads((Path(__file__).parent / "fixtures" / "profile_robert.json").read_text(encoding="utf-8"))
    portfolio = json.loads((Path(__file__).parent / "fixtures" / "portfolio_robert.json").read_text(encoding="utf-8"))
    idea = json.loads((Path(__file__).parent / "fixtures" / "idea_tsla_25.json").read_text(encoding="utf-8"))
    result = run_analysis(profile, portfolio, idea, deps=deps, config=BedrockConfig())

    def runner(client, model_id, brief, validate):
        output = deps.render_template(brief)
        output.update({"origin": "llm", "attempt": 2, "summary": "Il faut vendre MARQUEUR-SECRET maintenant."})
        return output

    client_config = config

    class Client:
        config = client_config
        last_grounding_flags = {}

    bad = replace(deps, validate=lambda output, brief: (
        {"is_valid": False, "checked_references": [],
         "rejections": [{"code": "forbidden_term", "slot": "summary", "excerpt": "MARQUEUR-SECRET"}]}
        if output["origin"] == "llm" else {"is_valid": True, "rejections": [], "checked_references": []}))
    explanation = explain(result, "novice", mode="bedrock", config=config, client=Client(), deps=bad,
                          explainer_runner=runner)
    details = explanation["trace"][0]["details"]
    assert details["rejection_slots"] == ["summary:forbidden_term"]
    # seul le court extrait du validateur est conserve pour le diagnostic, jamais la phrase complete du modele
    assert "Il faut vendre MARQUEUR-SECRET maintenant." not in json.dumps(explanation["trace"])
    assert details["rejection_excerpts"] == ["summary:forbidden_term:MARQUEUR-SECRET"]


def test_prompt_v4_forbids_naming_variants_by_identifier():
    prompt = load_prompt("explainer_v4")
    assert "REGLE 6" in prompt and "V1" in prompt and "UNE seule phrase" in prompt


def test_guardrail_checks_only_the_model_sentences_not_the_long_rendered_text():
    from dataclasses import replace
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.fixture_collaborators import fixture_deps

    fixtures = Path(__file__).parent / "fixtures"
    load = lambda name: json.loads((fixtures / name).read_text(encoding="utf-8"))
    deps = replace(fixture_deps(), render_markdown=lambda output, brief: "tableau " * 1500)   # 12000 caracteres
    config = BedrockConfig(mode="bedrock", analyst_model_id="m", explainer_model_id="m",
                           guardrail_id="g-test", guardrail_version="1")
    result = run_analysis(load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json"),
                          deps=deps, config=BedrockConfig())
    received = {}

    class Guard:
        last_grounding_flags = {}

        def __init__(self):
            self.config = config

        def check_output_grounding(self, source, query, answer):
            received["answer"] = answer
            return {"check": "output_grounding", "action": "none", "denied_topics": [],
                    "grounding_score": 0.9, "relevance_score": 0.9, "mode": "detect"}

    def runner(client, model_id, brief, validate):
        output = deps.render_template(brief)
        output.update({"origin": "llm", "attempt": 1, "model_id": model_id, "prompt_version": "explainer_v4",
                       "summary": "PHRASE-DU-MODELE [G1]."})
        return output

    explanation = explain(result, "novice", mode="bedrock", config=config, client=Guard(), deps=deps,
                          explainer_runner=runner)
    assert "PHRASE-DU-MODELE" in received["answer"] and "tableau" not in received["answer"]
    assert len(received["answer"]) < 5000
    assert explanation["output"]["origin"] == "llm"                     # verifie, donc conserve
    assert explanation["trace"][2]["details"]["checked_chars"] == len(received["answer"])


def test_prompt_v4_states_the_scope_of_measures_and_forbids_additions():
    prompt = load_prompt("explainer_v4")
    assert "REGLE 7" in prompt and "PORTEFEUILLE ENTIER" in prompt and "de la position" in prompt
    assert "REGLE 8" in prompt and "rien d'ajoute" in prompt
