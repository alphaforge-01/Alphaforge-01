"""Tests de l'integration de la source d'ancrage en phrases dans le pipeline (flux C).

Le module `grounding_source` appartient a un autre flux : ces tests le remplacent par un double et verifient
seulement le choix de la source, le repli sur le JSON et la trace. Aucun appel reseau ni AWS.
"""
from dataclasses import replace
from pathlib import Path
import json
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.analysis_pipeline import _grounding_source, explain, run_analysis
from alphaforge.bedrock_client import GROUNDING_SOURCE_MAX_CHARS, BedrockConfig
from alphaforge.fixture_collaborators import fixture_deps

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = BedrockConfig(mode="bedrock", analyst_model_id="m", explainer_model_id="m",
                       guardrail_id="g-test", guardrail_version="1")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def install(monkeypatch, builder):
    module = types.ModuleType("alphaforge.grounding_source")
    module.build_grounding_source = builder
    monkeypatch.setitem(sys.modules, "alphaforge.grounding_source", module)


def uninstall(monkeypatch):
    monkeypatch.setitem(sys.modules, "alphaforge.grounding_source", None)   # import impossible


BRIEF = {"brief_id": "b1", "idea": {"ticker": "TSLA"}, "checks": []}


def test_sentences_are_used_when_the_module_provides_them(monkeypatch):
    install(monkeypatch, lambda brief: "Le portefeuille est en conflit.")
    assert _grounding_source(BRIEF) == ("Le portefeuille est en conflit.", "phrases")


def test_json_is_the_fallback_when_the_module_is_missing(monkeypatch):
    uninstall(monkeypatch)
    text, kind = _grounding_source(BRIEF)
    assert kind == "json" and json.loads(text) == BRIEF


@pytest.mark.parametrize("builder", [
    lambda brief: (_ for _ in ()).throw(KeyError("champ")),     # le module plante
    lambda brief: "",                                            # texte vide
    lambda brief: None,                                          # type inattendu
    lambda brief: "x" * (GROUNDING_SOURCE_MAX_CHARS + 1),        # depasse la limite du controle
])
def test_json_is_the_fallback_when_the_module_fails_or_is_unusable(monkeypatch, builder):
    install(monkeypatch, builder)
    assert _grounding_source(BRIEF)[1] == "json"


def explained(monkeypatch, builder):
    deps = fixture_deps()
    result = run_analysis(load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json"),
                          deps=deps, config=BedrockConfig())
    received = {}

    class Guard:
        last_grounding_flags = {}
        config = CONFIG

        def check_output_grounding(self, source, query, answer):
            received["source"] = source
            return {"check": "output_grounding", "action": "none", "denied_topics": [],
                    "grounding_score": 0.85, "relevance_score": 1.0, "mode": "detect"}

    def runner(client, model_id, brief, validate):
        output = deps.render_template(brief)
        output.update({"origin": "llm", "attempt": 1, "model_id": model_id, "prompt_version": "explainer_v4"})
        return output

    if builder is None:
        uninstall(monkeypatch)
    else:
        install(monkeypatch, builder)
    explanation = explain(result, "novice", mode="bedrock", config=CONFIG, client=Guard(), deps=deps,
                          explainer_runner=runner)
    return explanation, received


def test_the_guardrail_receives_the_sentence_source_and_the_trace_says_so(monkeypatch):
    explanation, received = explained(monkeypatch, lambda brief: "SOURCE-EN-PHRASES")
    assert received["source"] == "SOURCE-EN-PHRASES"
    details = explanation["trace"][2]["details"]
    assert details["source_kind"] == "phrases" and details["source_chars"] == len("SOURCE-EN-PHRASES")
    assert explanation["output"]["origin"] == "llm"


def test_the_guardrail_receives_the_json_when_no_module_exists_and_the_trace_says_so(monkeypatch):
    explanation, received = explained(monkeypatch, None)
    assert json.loads(received["source"])["brief_id"] == explanation["brief"]["brief_id"]
    details = explanation["trace"][2]["details"]
    assert details["source_kind"] == "json" and details["source_chars"] == len(received["source"])


def test_the_explainer_still_receives_the_json_dossier(monkeypatch):
    """Seule la source du controle change : l'explicateur lit toujours le dossier JSON."""
    from alphaforge.explainer_agent import explain_with_llm
    seen = {}

    class Client:
        def converse(self, model_id, messages, **kwargs):
            seen["message"] = messages[0]["content"][0]["text"]
            return {"output": {"message": {"role": "assistant", "content": [{"text": "{}"}]}}, "stopReason": "end_turn"}

    install(monkeypatch, lambda brief: "PHRASES")
    brief = {"brief_id": "b1", "level": "novice", "idea": {"ticker": "TSLA"}}
    with pytest.raises(Exception):
        explain_with_llm(Client(), "m", brief, lambda o, b: {"is_valid": True, "rejections": []})
    assert '"brief_id": "b1"' in seen["message"] and "PHRASES" not in seen["message"]
