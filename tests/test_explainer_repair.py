"""Tests de la reparation par emplacement, des libelles explicites et de la robustesse du format JSON.

Aucun appel reseau ni AWS.
"""
from dataclasses import replace
from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.analysis_pipeline import (
    MAX_REPAIRED_SLOTS, _excerpts, _repair_slots, _scope_evidence_labels, explain, run_analysis,
)
from alphaforge.bedrock_client import BedrockConfig
from alphaforge.explainer_agent import explain_with_llm, parse_output
from alphaforge.fixture_collaborators import fixture_deps
from alphaforge.tool_specs import ExplainerFailure

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


PROFILE, PORTFOLIO, IDEA = load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json")
CONFIG = BedrockConfig(mode="bedrock", analyst_model_id="m", explainer_model_id="m",
                       guardrail_id="g-test", guardrail_version="1")


# ---- reparation par emplacement ----

def template_output(deps=None):
    deps = deps or fixture_deps()
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps, config=BedrockConfig())
    return deps, result, deps.render_template(deps.build_brief(result, "novice"))


def test_repair_replaces_only_the_rejected_slot():
    _, _, template = template_output()
    llm = {**template, "origin": "llm", "variants": "texte du modele", "summary": "RESUME-DU-MODELE [G1]"}
    repaired, slots = _repair_slots(llm, template, [{"code": "number_outside_registry", "slot": "variants",
                                                     "excerpt": "17"}])
    assert slots == ["variants"]
    assert repaired["variants"] == template["variants"] and repaired["summary"] == "RESUME-DU-MODELE [G1]"
    assert llm["variants"] == "texte du modele"          # l'entree n'est pas modifiee


def test_repair_can_replace_a_factor_by_the_template_factor_of_the_same_check():
    _, _, template = template_output()
    llm = {**template, "origin": "llm",
           "factors": [{"check_id": f["check_id"], "text": "TEXTE-MODELE"} for f in template["factors"]]}
    repaired, slots = _repair_slots(llm, template, [{"code": "forbidden_term", "slot": "factors[1]", "excerpt": "x"}])
    assert slots == ["factors[1]"]
    assert repaired["factors"][1] == template["factors"][1] and repaired["factors"][0]["text"] == "TEXTE-MODELE"


@pytest.mark.parametrize("rejection", [
    {"code": "slot_missing", "slot": "variants", "excerpt": ""},                 # emplacement manquant
    {"code": "too_long", "slot": "factors", "excerpt": ""},                      # structure des facteurs
    {"code": "forbidden_term", "slot": "output", "excerpt": ""},                 # sortie non structuree
    {"code": "too_long", "slot": "inconnu", "excerpt": ""},
])
def test_repair_refuses_structural_rejections(rejection):
    _, _, template = template_output()
    assert _repair_slots({**template, "origin": "llm"}, template, [rejection]) == (None, [])


def test_repair_refuses_too_many_slots_or_an_unknown_factor():
    _, _, template = template_output()
    llm = {**template, "origin": "llm"}
    many = [{"code": "too_long", "slot": s, "excerpt": ""} for s in ("summary", "counterfactual", "variants", "limits_context")]
    assert len(many) > MAX_REPAIRED_SLOTS and _repair_slots(llm, template, many) == (None, [])
    unknown = {**llm, "factors": [{"check_id": "G99", "text": "x"}]}
    assert _repair_slots(unknown, template, [{"code": "too_long", "slot": "factors[0]", "excerpt": ""}]) == (None, [])


def explained_with(llm_output_factory, validate_fn):
    deps = replace(fixture_deps(), validate=validate_fn)
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps, config=BedrockConfig())

    class Guard:
        last_grounding_flags = {}
        config = CONFIG

        def check_output_grounding(self, source, query, answer):
            return {"check": "output_grounding", "action": "none", "denied_topics": [],
                    "grounding_score": 0.9, "relevance_score": 0.9, "mode": "detect"}

    def runner(client, model_id, brief, validate):
        output = deps.render_template(brief)
        output.update({"origin": "llm", "attempt": 2, "model_id": model_id, "prompt_version": "explainer_v4"})
        return llm_output_factory(output)

    return explain(result, "novice", mode="bedrock", config=CONFIG, client=Guard(), deps=deps,
                   explainer_runner=runner)


def validator_rejecting_marker(marker, slot, code="number_outside_registry"):
    base = fixture_deps().validate

    def validate(output, brief):
        texts = [output["summary"], output["variants"], output["counterfactual"], output["limits_context"]]
        if any(marker in str(t) for t in texts):
            return {"is_valid": False, "checked_references": [],
                    "rejections": [{"code": code, "slot": slot, "excerpt": marker}]}
        return base(output, brief)
    return validate


def test_one_bad_slot_keeps_the_rest_of_the_model_text():
    explanation = explained_with(
        lambda o: {**o, "variants": "variante MARQUEUR-CHIFFRE", "summary": "RESUME-DU-MODELE [G1]."},
        validator_rejecting_marker("MARQUEUR-CHIFFRE", "variants"))
    assert explanation["output"]["origin"] == "llm"
    assert explanation["output"]["summary"] == "RESUME-DU-MODELE [G1]."
    assert "MARQUEUR-CHIFFRE" not in json.dumps(explanation["output"])
    details = explanation["trace"][0]["details"]
    assert details["repaired_slots"] == ["variants"] and explanation["trace"][0]["status"] == "ok"
    assert details["rejection_slots"] == ["variants:number_outside_registry"]
    assert details["rejection_excerpts"] == ["variants:number_outside_registry:MARQUEUR-CHIFFRE"]
    assert explanation["validation"]["is_valid"] is True


def test_unrepairable_rejection_still_falls_back_to_the_full_template():
    explanation = explained_with(
        lambda o: {**o, "variants": "MARQUEUR-CHIFFRE"},
        validator_rejecting_marker("MARQUEUR-CHIFFRE", "variants", code="slot_missing"))
    assert explanation["output"]["origin"] == "template"
    details = explanation["trace"][0]["details"]
    assert details["fallback_reason"] == "rejet_du_validateur" and "repaired_slots" not in details
    assert explanation["trace"][0]["status"] == "fallback"


def test_repair_that_still_fails_validation_falls_back_to_the_full_template():
    def always_bad(output, brief):
        if output["origin"] == "llm":
            return {"is_valid": False, "checked_references": [],
                    "rejections": [{"code": "too_long", "slot": "summary", "excerpt": "x"}]}
        return {"is_valid": True, "checked_references": [], "rejections": []}

    explanation = explained_with(lambda o: {**o, "summary": "texte"}, always_bad)
    # la reparation est revalidee : le validateur la rejette encore, donc le gabarit complet prend le relais
    assert explanation["output"]["origin"] == "template"
    assert "repaired_slots" not in explanation["trace"][0]["details"]
    assert explanation["trace"][0]["status"] == "fallback" and explanation["validation"]["is_valid"] is True


def test_excerpts_are_short_bounded_and_masked():
    fake_key = "AKIA" + "Q" * 16
    items = [{"code": "forbidden_term", "slot": "summary", "excerpt": "e" * 100}] * 20
    result = _excerpts(items)
    assert len(result) == 8 and all(len(line) <= 70 for line in result)
    assert fake_key not in _excerpts([{"code": "c", "slot": "s", "excerpt": fake_key}])[0]


# ---- libelles explicites ----

def test_labels_state_their_scope_and_the_scoping_is_idempotent():
    evidence = {
        "E1": {"label_fr": "Perte maximale historique", "subject": "portfolio_before"},
        "E2": {"label_fr": "Perte maximale historique", "subject": "portfolio_after"},
        "E3": {"label_fr": "Perte maximale historique", "subject": "variant:V1"},
        "E4": {"label_fr": "Perte maximale historique", "subject": "explored:simulate-1"},
        "E5": {"label_fr": "Rendement de TSLA", "subject": "TSLA"},
    }
    _scope_evidence_labels(evidence)
    _scope_evidence_labels(evidence)
    labels = {key: entry["label_fr"] for key, entry in evidence.items()}
    assert labels["E1"].endswith("(portefeuille avant l'ajout)") and labels["E2"].endswith("(portefeuille après l'ajout)")
    assert labels["E3"].endswith("(variante simulée)") and labels["E4"].endswith("(simulation explorée)")
    assert labels["E5"] == "Rendement de TSLA"
    assert len(set(labels[k] for k in ("E1", "E2", "E3", "E4"))) == 4        # plus aucun libelle en double
    assert labels["E1"].count("(") == 1                                       # pas de doublon de suffixe


def test_run_analysis_returns_scoped_labels_without_digits():
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=fixture_deps(), config=BedrockConfig())
    after = [e for e in result["evidence"].values() if e["subject"] == "portfolio_after"]
    assert after and all(e["label_fr"].endswith("(portefeuille après l'ajout)") for e in after)
    assert not any(char.isdigit() for e in after for char in e["label_fr"])     # le validateur refuse les chiffres


# ---- format JSON robuste ----

def brief_for_parsing():
    deps = fixture_deps()
    result = run_analysis(PROFILE, PORTFOLIO, IDEA, deps=deps, config=BedrockConfig())
    return deps.build_brief(result, "novice")


GOOD = ('{"summary": "a", "factors": [{"check_id": "G1", "text": "b"}], "counterfactual": "c", '
        '"variants": "d", "limits_context": "e"}')


def test_parse_accepts_a_raw_newline_inside_a_string():
    text = GOOD.replace('"a"', '"ligne un\nligne deux"')
    output, problem = parse_output(text, brief_for_parsing(), model_id="m", attempt=1)
    assert problem is None and output["summary"] == "ligne un\nligne deux"


def test_parse_error_message_names_the_cause_and_position():
    output, problem = parse_output(GOOD.replace('"b"}', '"b" }}').replace('"d"', '"d" "x"'),
                                   brief_for_parsing(), model_id="m", attempt=1)
    assert output is None and problem.startswith("JSON invalide (") and "ligne" in problem and "colonne" in problem


class ScriptedClient:
    def __init__(self, responses):
        self.queue = list(responses)
        self.calls = 0

    def converse(self, model_id, messages, **kwargs):
        self.calls += 1
        return self.queue.pop(0)


def reply(text, stop="end_turn"):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": stop}


def test_truncated_reply_is_reported_exactly_and_retried():
    brief = brief_for_parsing()
    client = ScriptedClient([reply(GOOD[:60], stop="max_tokens"), reply(GOOD)])
    output = explain_with_llm(client, "m", brief, lambda o, b: {"is_valid": True, "rejections": []})
    assert client.calls == 2 and output["attempt"] == 2


def test_two_truncated_replies_raise_with_the_exact_reason():
    brief = brief_for_parsing()
    client = ScriptedClient([reply("{", stop="max_tokens"), reply("{", stop="max_tokens")])
    with pytest.raises(ExplainerFailure, match="tronquee"):
        explain_with_llm(client, "m", brief, lambda o, b: {"is_valid": True, "rejections": []})


def test_explainer_allows_enough_tokens_for_the_pro_level():
    from alphaforge.explainer_agent import INFERENCE_CONFIG
    assert INFERENCE_CONFIG["maxTokens"] >= 2500 and "temperature" not in INFERENCE_CONFIG
