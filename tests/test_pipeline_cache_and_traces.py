"""Tests du cache d'explications et de la persistance des traces dans le pipeline. Aucun reseau ni AWS."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.analysis_pipeline import explain, persist_trace, run_analysis
from alphaforge.bedrock_client import BedrockConfig
from alphaforge.explanation_cache import ExplanationCache
from alphaforge.fixture_collaborators import fixture_deps
from alphaforge.tool_specs import AnalystOutcome
from alphaforge.trace_store import TraceStoreError

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_KEY = "AKIA" + "X" * 16
CONFIG = BedrockConfig(mode="bedrock", analyst_model_id="model-test", explainer_model_id="model-test",
                       trace_bucket="bucket-test")
CONFIG_NO_BUCKET = BedrockConfig(mode="bedrock", analyst_model_id="model-test", explainer_model_id="model-test")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeClient:
    """Client Bedrock factice : sans garde-fou configure, aucune methode n'est appelee."""

    def __init__(self, config=CONFIG):
        self.config = config


class FakeStore:
    """Double de TraceStore : enregistre les documents, peut lever une erreur."""

    def __init__(self, error=None):
        self.error = error
        self.documents = []

    def save(self, document):
        self.documents.append(document)
        if self.error:
            raise self.error
        analysis = document["analysis"]
        suffix = f"-explication-{document['explanation']['level']}" if "explanation" in document else ""
        return f"traces/{analysis['created_at'][:10]}/{analysis['run_id']}{suffix}.json"


def agent_runner(client, model_id, toolbox, idea, profile):
    toolbox.call("analyze_portfolio")
    toolbox.call("simulate_portfolio_change", dict(idea))
    return AnalystOutcome(
        submission={"understood_idea": idea, "variants": [], "highlight_evidence_ids": [],
                    "unsupported_requests": []},
        actor="agent", model_id=model_id, turns=2, stop_reason="submitted")


def analysis(deps, mode="offline", **kwargs):
    kwargs.setdefault("config", BedrockConfig())
    return run_analysis(load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json"),
                        mode=mode, deps=deps, **kwargs)


def llm_output(deps, result, level="novice"):
    output = deps.render_template(deps.build_brief(result, level))
    output["origin"] = "llm"
    output["attempt"] = 1
    return output


class CountingRunner:
    def __init__(self, factory):
        self.factory = factory
        self.calls = 0

    def __call__(self, client, model_id, brief, validate):
        self.calls += 1
        return self.factory()


# ---- persist_trace ----

def test_persist_trace_without_bucket():
    deps = fixture_deps()
    result = analysis(deps)
    assert persist_trace(result, config=BedrockConfig()) == {
        "saved": False, "location": None, "reason": "bucket_non_configure"}


def test_persist_trace_with_store_returns_key():
    deps = fixture_deps()
    result = analysis(deps)
    store = FakeStore()
    outcome = persist_trace(result, config=BedrockConfig(), store=store)
    assert outcome["saved"] is True and outcome["reason"] is None
    assert outcome["location"] == f"traces/{result['created_at'][:10]}/{result['run_id']}.json"
    assert len(store.documents) == 1 and "explanation" not in store.documents[0]


def test_persist_trace_store_error_does_not_raise_and_masks_secret():
    deps = fixture_deps()
    result = analysis(deps)
    store = FakeStore(TraceStoreError("echec " + FAKE_KEY))
    outcome = persist_trace(result, config=BedrockConfig(), store=store)
    assert outcome["saved"] is False and outcome["location"] is None
    assert FAKE_KEY not in json.dumps(outcome)


# ---- run_analysis ----

def test_run_analysis_bedrock_records_trace_saved_in_step_3():
    deps = fixture_deps()
    store = FakeStore()
    result = analysis(deps, "bedrock", config=CONFIG, client=FakeClient(), analyst_runner=agent_runner,
                      trace_store=store)
    step3 = result["trace"][2]
    assert step3["step"] == 3
    saved = step3["details"]["trace_saved"]
    assert saved["saved"] is True and saved["location"].endswith(f"{result['run_id']}.json")
    assert len(store.documents) == 1
    assert store.documents[0]["analysis"]["run_id"] == result["run_id"]


def test_run_analysis_bedrock_store_failure_does_not_break_analysis():
    deps = fixture_deps()
    store = FakeStore(TraceStoreError("echec"))
    result = analysis(deps, "bedrock", config=CONFIG, client=FakeClient(), analyst_runner=agent_runner,
                      trace_store=store)
    assert result["trace"][2]["details"]["trace_saved"]["saved"] is False


def test_run_analysis_offline_never_touches_store():
    deps = fixture_deps()
    store = FakeStore()
    result = analysis(deps, "offline", config=CONFIG, trace_store=store)
    assert store.documents == []
    assert "trace_saved" not in result["trace"][2]["details"]


# ---- explain et cache ----

def test_explain_first_call_runs_and_caches_second_reads_cache():
    deps = fixture_deps()
    result = analysis(deps)
    cache = ExplanationCache()
    runner = CountingRunner(lambda: llm_output(deps, result))
    first = explain(result, "novice", "bedrock", deps=deps, client=FakeClient(), config=CONFIG_NO_BUCKET,
                    explainer_runner=runner, cache=cache)
    assert runner.calls == 1 and len(cache) == 1
    assert first["trace"][0]["details"]["from_cache"] is False
    second = explain(result, "novice", "bedrock", deps=deps, client=FakeClient(), config=CONFIG_NO_BUCKET,
                     explainer_runner=runner, cache=cache)
    assert runner.calls == 1
    step4 = second["trace"][0]
    assert step4["details"]["from_cache"] is True and step4["actor"] == "agent"
    assert step4["status"] == "ok" and step4["model_id"] == "model-test"
    assert second["output"] == first["output"]


def test_explain_cache_key_depends_on_level():
    deps = fixture_deps()
    result = analysis(deps)
    cache = ExplanationCache()
    runner = CountingRunner(lambda: llm_output(deps, result))
    explain(result, "novice", "bedrock", deps=deps, client=FakeClient(), config=CONFIG_NO_BUCKET,
            explainer_runner=runner, cache=cache)
    explain(result, "pro", "bedrock", deps=deps, client=FakeClient(), config=CONFIG_NO_BUCKET,
            explainer_runner=runner, cache=cache)
    assert runner.calls == 2 and len(cache) == 2


def test_explain_invalid_text_is_not_cached():
    deps = fixture_deps()
    result = analysis(deps)

    def invalid():
        output = load("explainer_output_invalid.json")
        output["origin"] = "llm"
        return output

    cache = ExplanationCache()
    runner = CountingRunner(invalid)
    explanation = explain(result, "novice", "bedrock", deps=deps, client=FakeClient(), config=CONFIG_NO_BUCKET,
                          explainer_runner=runner, cache=cache)
    assert explanation["output"]["origin"] == "template" and len(cache) == 0
    explain(result, "novice", "bedrock", deps=deps, client=FakeClient(), config=CONFIG_NO_BUCKET,
            explainer_runner=runner, cache=cache)
    assert runner.calls == 2


def test_explain_without_cache_runner_called_every_time():
    deps = fixture_deps()
    result = analysis(deps)
    runner = CountingRunner(lambda: llm_output(deps, result))
    for _ in range(2):
        explain(result, "novice", "bedrock", deps=deps, client=FakeClient(), config=CONFIG_NO_BUCKET,
                explainer_runner=runner)
    assert runner.calls == 2


def test_explain_does_not_use_cache_in_offline_mode():
    deps = fixture_deps()
    result = analysis(deps)
    cache = ExplanationCache()
    explanation = explain(result, "novice", "offline", deps=deps, config=BedrockConfig(), cache=cache)
    assert len(cache) == 0 and explanation["trace"][0]["details"]["from_cache"] is False


# ---- explain et traces ----

def test_explain_bedrock_writes_trace_with_suffixed_key_and_step_6_status():
    deps = fixture_deps()
    result = analysis(deps)
    store = FakeStore()
    explanation = explain(
        result, "pro", "bedrock", deps=deps, client=FakeClient(), config=CONFIG, trace_store=store,
        explainer_runner=lambda c, m, brief, validate: llm_output(deps, result, "pro"))
    saved = explanation["trace"][2]["details"]["trace_saved"]
    assert explanation["trace"][2]["step"] == 6
    assert saved["saved"] is True
    assert saved["location"] == f"traces/{result['created_at'][:10]}/{result['run_id']}-explication-pro.json"
    assert store.documents[0]["explanation"]["level"] == "pro"
    assert store.documents[0]["explanation"]["origin"] == "llm"


def test_explain_store_failure_does_not_crash():
    deps = fixture_deps()
    result = analysis(deps)
    store = FakeStore(TraceStoreError("echec " + FAKE_KEY))
    explanation = explain(
        result, "novice", "bedrock", deps=deps, client=FakeClient(), config=CONFIG, trace_store=store,
        explainer_runner=lambda c, m, brief, validate: llm_output(deps, result))
    saved = explanation["trace"][2]["details"]["trace_saved"]
    assert saved["saved"] is False and FAKE_KEY not in json.dumps(explanation["trace"])
    assert explanation["validation"]["is_valid"] is True


def test_explain_offline_does_not_write_trace():
    deps = fixture_deps()
    result = analysis(deps)
    store = FakeStore()
    explanation = explain(result, "novice", "offline", deps=deps, config=CONFIG, trace_store=store)
    assert store.documents == [] and "trace_saved" not in explanation["trace"][2]["details"]
