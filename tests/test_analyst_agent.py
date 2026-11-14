"""Tests de l'agent analyste du flux C. Aucun appel reseau ni AWS : client Converse scripte ecrit a la main."""
from pathlib import Path
import copy
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge import analyst_agent
from alphaforge.analysis_pipeline import run_analysis
from alphaforge.analyst_agent import (
    INFERENCE_CONFIG, MAX_TURNS, MAX_UNSUPPORTED, MAX_UNSUPPORTED_CHARS, _tool_payload,
    build_user_message, parse_submission, run_analyst,
)
from alphaforge.bedrock_client import BedrockAuthError, BedrockConfig, BedrockError
from alphaforge.fixture_collaborators import fixture_deps
from alphaforge.prompt_loader import load_prompt
from alphaforge.tool_specs import AnalystFailure, AnalystOutcome, ToolBox, TOOL_SPECS

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_KEY = "AKIA" + "X" * 16
FAKE_ACCOUNT = "1234" + "5678" + "9012"
MODEL = "model-test"
IDEA = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


PROFILE = load("profile_robert.json")
PORTFOLIO = load("portfolio_robert.json")


def tool_use(use_id, name, params=None):
    return {"toolUse": {"toolUseId": use_id, "name": name, "input": params if params is not None else {}}}


def reply(*blocks, stop="tool_use"):
    return {"output": {"message": {"role": "assistant", "content": list(blocks)}}, "stopReason": stop}


def valid_submit(**overrides):
    params = {"understood_idea": dict(IDEA), "variants": [], "highlight_evidence_ids": [],
              "unsupported_requests": []}
    params.update(overrides)
    return params


class ScriptedClient:
    """Client Converse factice : rend les reponses de la file et enregistre chaque appel."""

    def __init__(self, responses, config=None):
        self.config = config or BedrockConfig(mode="bedrock", analyst_model_id=MODEL)
        self._queue = list(responses)
        self.calls = []

    def converse(self, model_id, messages, *, system=None, tool_config=None, inference_config=None, **kwargs):
        self.calls.append({"model_id": model_id, "messages": copy.deepcopy(messages), "system": system,
                           "tool_config": tool_config, "inference_config": inference_config})
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_toolbox(max_calls=12):
    return ToolBox(fixture_deps(), PORTFOLIO, as_of=None, capital_cad=PROFILE["capital_cad"], max_calls=max_calls)


def run(responses, toolbox=None, **kwargs):
    client = ScriptedClient(responses)
    toolbox = toolbox or make_toolbox()
    outcome = run_analyst(client, MODEL, toolbox, dict(IDEA), PROFILE, **kwargs)
    return outcome, client, toolbox


def result_blocks(message):
    return [b["toolResult"] for b in message["content"] if "toolResult" in b]


# ---- chemin nominal ----

def test_nominal_three_turns():
    submit = valid_submit()
    outcome, client, toolbox = run([
        reply(tool_use("t1", "analyze_portfolio")),
        reply(tool_use("t2", "simulate_portfolio_change", dict(IDEA))),
        reply(tool_use("t3", "submit_analysis", submit)),
    ])
    assert isinstance(outcome, AnalystOutcome)
    assert (outcome.actor, outcome.turns, outcome.model_id, outcome.stop_reason) == ("agent", 3, MODEL, "submitted")
    assert outcome.submission["understood_idea"] == IDEA
    assert len(client.calls) == 3
    first = client.calls[0]
    assert first["model_id"] == MODEL
    assert first["system"] == load_prompt("analyst_v1")
    assert [t["toolSpec"]["name"] for t in first["tool_config"]["tools"]] == [
        "analyze_portfolio", "get_asset_facts", "simulate_portfolio_change", "submit_analysis"]
    assert first["tool_config"]["tools"] == TOOL_SPECS
    assert first["inference_config"]["temperature"] == 0 and first["inference_config"] == INFERENCE_CONFIG
    assert [c["tool_name"] for c in toolbox.calls] == ["analyze_portfolio", "simulate_portfolio_change"]
    assert toolbox.calls[1]["params"] == IDEA


def test_nominal_messages_return_one_tool_result_per_tool_use():
    _, client, _ = run([
        reply(tool_use("t1", "analyze_portfolio")),
        reply(tool_use("t2", "simulate_portfolio_change", dict(IDEA))),
        reply(tool_use("t3", "submit_analysis", valid_submit())),
    ])
    last = client.calls[2]["messages"]
    # user, assistant, user(results), assistant, user(results)
    assert [m["role"] for m in last] == ["user", "assistant", "user", "assistant", "user"]
    assert [b["toolUseId"] for b in result_blocks(last[2])] == ["t1"]
    assert [b["toolUseId"] for b in result_blocks(last[4])] == ["t2"]
    for message in (last[2], last[4]):
        assert all(set(block) == {"toolResult"} for block in message["content"])
    assert "text" in last[0]["content"][0]


def test_several_tool_uses_in_one_turn_give_single_user_message():
    _, client, toolbox = run([
        reply(tool_use("a", "analyze_portfolio"), tool_use("b", "get_asset_facts", {"ticker": "tsla"})),
        reply(tool_use("c", "submit_analysis", valid_submit())),
    ])
    message = client.calls[1]["messages"][2]
    assert message["role"] == "user"
    assert [b["toolUseId"] for b in result_blocks(message)] == ["a", "b"]
    assert len(message["content"]) == 2
    assert [c["tool_name"] for c in toolbox.calls] == ["analyze_portfolio", "get_asset_facts"]


# ---- soumissions invalides ----

BAD_SUBMISSIONS = {
    "reason_code": valid_submit(variants=[{"reason_code": "inconnu", "idea": dict(IDEA)}]),
    "three_variants": valid_submit(variants=[{"reason_code": "reduce_weight", "idea": dict(IDEA)}] * 3),
    "bad_idea": valid_submit(understood_idea={"ticker": "TSLA", "target_weight": 7, "funding_source": "pro_rata"}),
    "three_highlights": valid_submit(highlight_evidence_ids=["E1", "E2", "E3"]),
}


@pytest.mark.parametrize("key", list(BAD_SUBMISSIONS))
def test_invalid_submission_is_returned_as_error_then_valid_one_succeeds(key):
    outcome, client, _ = run([
        reply(tool_use("s1", "submit_analysis", BAD_SUBMISSIONS[key])),
        reply(tool_use("s2", "submit_analysis", valid_submit())),
    ])
    assert outcome.turns == 2 and outcome.stop_reason == "submitted"
    (block,) = result_blocks(client.calls[1]["messages"][2])
    assert block["toolUseId"] == "s1" and block["status"] == "error"
    assert block["content"][0]["json"]["status"] == "error"
    assert block["content"][0]["json"]["error_message"]


def test_two_invalid_submissions_in_a_row_raise():
    client = ScriptedClient([
        reply(tool_use("s1", "submit_analysis", BAD_SUBMISSIONS["reason_code"])),
        reply(tool_use("s2", "submit_analysis", BAD_SUBMISSIONS["reason_code"])),
        reply(tool_use("s3", "submit_analysis", valid_submit())),
    ])
    with pytest.raises(AnalystFailure):
        run_analyst(client, MODEL, make_toolbox(), dict(IDEA), PROFILE)
    assert len(client.calls) == 2


# ---- relance, tours, arrets ----

def test_no_tool_use_nudges_once_then_succeeds():
    outcome, client, _ = run([
        reply({"text": "Voici mon avis."}, stop="end_turn"),
        reply(tool_use("s1", "submit_analysis", valid_submit())),
    ])
    assert outcome.turns == 2
    nudge = client.calls[1]["messages"][-1]
    assert nudge["role"] == "user"
    assert nudge["content"] == [{"text": "Termine maintenant avec l'outil submit_analysis."}]


def test_no_tool_use_twice_raises():
    client = ScriptedClient([reply({"text": "a"}, stop="end_turn"), reply({"text": "b"}, stop="end_turn")])
    with pytest.raises(AnalystFailure):
        run_analyst(client, MODEL, make_toolbox(), dict(IDEA), PROFILE)
    assert len(client.calls) == 2


def test_default_six_turns_without_submission_raise():
    assert MAX_TURNS == 6
    client = ScriptedClient([reply(tool_use(f"t{i}", "analyze_portfolio")) for i in range(10)])
    with pytest.raises(AnalystFailure, match="6 tours"):
        run_analyst(client, MODEL, make_toolbox(), dict(IDEA), PROFILE)
    assert len(client.calls) == 6


def test_max_turns_is_configurable():
    client = ScriptedClient([reply(tool_use(f"t{i}", "analyze_portfolio")) for i in range(10)])
    with pytest.raises(AnalystFailure, match="2 tours"):
        run_analyst(client, MODEL, make_toolbox(), dict(IDEA), PROFILE, max_turns=2)
    assert len(client.calls) == 2
    outcome, _, _ = run([reply(tool_use("t1", "analyze_portfolio")),
                         reply(tool_use("t2", "submit_analysis", valid_submit()))], max_turns=2)
    assert outcome.turns == 2


def test_max_tokens_raises():
    client = ScriptedClient([reply(tool_use("t1", "analyze_portfolio"), stop="max_tokens")])
    with pytest.raises(AnalystFailure, match="max_tokens"):
        run_analyst(client, MODEL, make_toolbox(), dict(IDEA), PROFILE)


@pytest.mark.parametrize("model_id", [None, ""])
def test_missing_model_id_raises_without_calling_client(model_id):
    client = ScriptedClient([])
    with pytest.raises(AnalystFailure):
        run_analyst(client, model_id, make_toolbox(), dict(IDEA), PROFILE)
    assert client.calls == []


def test_bedrock_error_propagates_unchanged():
    error = BedrockAuthError("acces refuse", code="AccessDeniedException")
    client = ScriptedClient([error])
    with pytest.raises(BedrockError) as raised:
        run_analyst(client, MODEL, make_toolbox(), dict(IDEA), PROFILE)
    assert raised.value is error


# ---- budget et outil inconnu ----

def test_tool_budget_exhausted_returns_error_and_loop_continues():
    toolbox = make_toolbox(max_calls=1)
    outcome, client, _ = run([
        reply(tool_use("a", "analyze_portfolio")),
        reply(tool_use("b", "get_asset_facts", {"ticker": "TSLA"})),
        reply(tool_use("c", "submit_analysis", valid_submit())),
    ], toolbox=toolbox)
    assert outcome.turns == 3 and toolbox.calls_used == 1
    (block,) = result_blocks(client.calls[2]["messages"][4])
    assert block["toolUseId"] == "b" and block["status"] == "error"
    assert "submit_analysis" in block["content"][0]["json"]["error_message"]


def test_unknown_tool_returns_error_without_exception():
    outcome, client, toolbox = run([
        reply(tool_use("x", "place_order", {"ticker": "TSLA"})),
        reply(tool_use("s", "submit_analysis", valid_submit())),
    ])
    assert outcome.turns == 2
    (block,) = result_blocks(client.calls[1]["messages"][2])
    assert block["toolUseId"] == "x" and block["status"] == "error"
    assert toolbox.calls[0]["status"] == "error" and toolbox.calls[0]["tool_name"] == "place_order"


# ---- parse_submission ----

def test_parse_submission_valid_cases():
    parsed, problem = parse_submission(valid_submit(
        understood_idea={"ticker": " tsla ", "target_weight": 1, "funding_source": "from_ticker",
                         "funding_ticker": "aaa"},
        variants=[{"reason_code": "reduce_weight", "idea": dict(IDEA, target_weight=0.1)}],
        highlight_evidence_ids=["E1", "E2"]))
    assert problem is None
    assert parsed["understood_idea"] == {"ticker": "TSLA", "target_weight": 1.0,
                                         "funding_source": "from_ticker", "funding_ticker": "AAA"}
    assert parsed["variants"][0]["idea"]["target_weight"] == 0.1
    assert parsed["highlight_evidence_ids"] == ["E1", "E2"]
    minimal, problem = parse_submission({"understood_idea": dict(IDEA)})
    assert problem is None and minimal["variants"] == [] and minimal["unsupported_requests"] == []
    assert parse_submission(valid_submit(variants=None, highlight_evidence_ids=None))[1] is None


def test_parse_submission_error_messages():
    assert "objet" in parse_submission("texte")[1]
    assert parse_submission({})[1].startswith("understood_idea invalide")
    assert parse_submission(valid_submit(understood_idea={"ticker": "A", "target_weight": 0,
                                                          "funding_source": "pro_rata"}))[1].startswith(
        "understood_idea invalide")
    assert parse_submission(valid_submit(variants=["x"]))[1].startswith("reason_code invalide")
    assert parse_submission(valid_submit(variants=[{"reason_code": "zzz", "idea": dict(IDEA)}]))[1].startswith(
        "reason_code invalide")
    bad_variant_idea = parse_submission(valid_submit(variants=[{"reason_code": "reduce_weight", "idea": {}}]))[1]
    assert bad_variant_idea.startswith("idee de variante invalide")
    variant = {"reason_code": "reduce_weight", "idea": dict(IDEA)}
    assert parse_submission(valid_submit(variants=[variant] * 3))[1] == "Au plus 2 variantes."
    for bad in (["E1", "E2", "E3"], "E1", [1]):
        assert parse_submission(valid_submit(highlight_evidence_ids=bad))[1].startswith("highlight_evidence_ids")
    for bad in ("texte", [1], [None]):
        assert parse_submission(valid_submit(unsupported_requests=bad))[1].startswith("unsupported_requests")


def test_parse_submission_cleans_unsupported_requests():
    long_text = "x" * 500
    items = ["  prevois le cours  ", "   ", "", long_text] + [f"demande {i}" for i in range(10)]
    parsed, _ = parse_submission(valid_submit(unsupported_requests=items))
    cleaned = parsed["unsupported_requests"]
    assert cleaned[0] == "prevois le cours"
    assert len(cleaned) == MAX_UNSUPPORTED == 5
    assert cleaned[1] == "x" * MAX_UNSUPPORTED_CHARS
    assert all(item == item.strip() and item for item in cleaned)


def test_parse_submission_redacts_secret_in_unsupported_requests():
    parsed, _ = parse_submission(valid_submit(
        unsupported_requests=[f"utilise la cle {FAKE_KEY} et le compte {FAKE_ACCOUNT}"]))
    text = parsed["unsupported_requests"][0]
    assert FAKE_KEY not in text and FAKE_ACCOUNT not in text


# ---- build_user_message ----

def test_build_user_message_contains_idea_and_robert_rules():
    message = build_user_message(IDEA, PROFILE)
    head, _, body = message.partition("\n")
    assert "hypotheses" in head
    payload = json.loads(body)
    assert payload["idee_a_analyser"] == {"ticker": "TSLA", "target_weight": 0.25,
                                          "funding_source": "pro_rata", "funding_ticker": None}
    profile = payload["profil_fictif"]
    assert profile["profile_id"] == "robert"
    assert profile["horizon_years_min"] == 3 and profile["horizon_years_max"] == 5
    assert [r["rule_id"] for r in profile["regles"]] == [r["rule_id"] for r in PROFILE["rules"]]
    r1 = profile["regles"][0]
    assert r1["warn_threshold"] == 0.2 and r1["limit_threshold"] == 0.22 and r1["direction"] == "max"


def test_build_user_message_has_no_data_outside_fictional_profile():
    payload = json.loads(build_user_message(IDEA, PROFILE).partition("\n")[2])
    assert set(payload) == {"idee_a_analyser", "profil_fictif"}
    assert set(payload["profil_fictif"]) == {"profile_id", "horizon_years_min", "horizon_years_max",
                                             "risk_tolerance", "regles"}
    text = json.dumps(payload)
    assert str(PROFILE["capital_cad"]) not in text and "display_name" not in text


# ---- _tool_payload ----

def test_tool_payload_keeps_only_expected_evidence_fields():
    result = {
        "status": "ok", "error_message": None, "tool_name": "x", "call_id": "c1", "params": {"secret": 1},
        "data": {"k": 1},
        "evidence": [{"evidence_id": "E1", "label_fr": "Vol", "display_value": "12 %", "subject": "TSLA",
                      "period_start": "2024-01-01", "period_end": "2024-12-31", "currency": "USD",
                      "metric": "m", "as_of": "2025-01-01", "raw_value": 0.12, "source": "s"}],
    }
    payload = _tool_payload(result)
    assert set(payload) == {"status", "error_message", "data", "evidence"}
    assert set(payload["evidence"][0]) == {"evidence_id", "label_fr", "display_value", "subject",
                                           "period_start", "period_end", "currency"}
    assert payload["data"] == {"k": 1}
    sparse = _tool_payload({"status": "error", "error_message": "m", "evidence": None})
    assert sparse["evidence"] == [] and sparse["data"] == {}


# ---- integration pipeline ----

def run_pipeline(client):
    return run_analysis(PROFILE, PORTFOLIO, dict(IDEA), mode="bedrock", client=client,
                        config=BedrockConfig(mode="bedrock", analyst_model_id=MODEL), deps=fixture_deps())


def test_pipeline_uses_real_run_analyst():
    assert analyst_agent.run_analyst is run_analyst
    client = ScriptedClient([
        reply(tool_use("t1", "analyze_portfolio")),
        reply(tool_use("t2", "simulate_portfolio_change", dict(IDEA))),
        reply(tool_use("t3", "submit_analysis", valid_submit())),
    ])
    result = run_pipeline(client)
    step = result["trace"][0]
    assert result["mode"] == "bedrock"
    assert step["actor"] == "agent" and step["status"] == "ok" and step["model_id"] == MODEL
    assert step["details"]["turns"] == 3 and "fallback_reason" not in step["details"]
    assert len(client.calls) == 3


def test_pipeline_falls_back_when_agent_loop_fails():
    client = ScriptedClient([reply({"text": "a"}, stop="end_turn"), reply({"text": "b"}, stop="end_turn")])
    result = run_pipeline(client)
    step = result["trace"][0]
    assert result["mode"] == "offline" and step["actor"] == "code" and step["status"] == "fallback"
    assert step["details"]["fallback_reason"].startswith("AnalystFailure")
    assert step["details"]["stop_reason"] == "scripted"
    assert [c["tool_name"] for c in step["details"]["tool_calls"]] == [
        "analyze_portfolio", "simulate_portfolio_change"]


def test_pipeline_falls_back_on_auth_error_without_leaking_secrets():
    error = BedrockAuthError(f"refuse pour {FAKE_KEY} compte {FAKE_ACCOUNT}", code="AccessDeniedException")
    result = run_pipeline(ScriptedClient([error]))
    step = result["trace"][0]
    assert step["actor"] == "code" and step["status"] == "fallback"
    assert step["details"]["fallback_reason"].startswith("BedrockAuthError")
    dumped = json.dumps(result["trace"])
    assert FAKE_KEY not in dumped and FAKE_ACCOUNT not in dumped
