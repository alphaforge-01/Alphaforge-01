"""Tests des schemas d'outils et du dispatcheur borne. Chiffres inventes."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.pipeline_deps import PipelineDeps
from alphaforge.tool_specs import (
    MAX_HIGHLIGHTS, MAX_TOOL_CALLS, MAX_VARIANTS, TOOL_SPECS, ToolBox, ToolBudgetExceeded,
    normalize_idea, tool_config,
)

PORTFOLIO = {"portfolio_id": "p_test", "label_fr": "Test", "is_fictional": True,
             "base_currency": "CAD", "positions": [{"ticker": "AAA", "weight": 1.0}]}
SECRET_DETAIL = "detail interne " + "AKIA" + "X" * 16


def evidence(eid):
    return {"evidence_id": eid, "metric": "m", "subject": "s", "as_of": "2025-01-01"}


class Registry:
    def __init__(self):
        self.registered = []

    def register(self, tool_result):
        self.registered.append(tool_result["tool_name"])
        return tool_result


def make_deps(registry=None, **overrides):
    registry = registry if registry is not None else Registry()

    def result(name, status="ok", ev=(), **extra):
        return {"tool_name": name, "params": {}, "status": status, "error_message": None,
                "data": {}, "evidence": [evidence(e) for e in ev], **extra}

    funcs = dict(
        analyze_portfolio=lambda portfolio, as_of=None, capital_cad=None: result("analyze_portfolio", ev=["E1"]),
        get_asset_facts=lambda ticker, as_of=None: result("get_asset_facts", ev=["E2"]),
        simulate_portfolio_change=lambda portfolio, idea, as_of=None, capital_cad=None: result(
            "simulate_portfolio_change", ev=["E3"]),
    )
    funcs.update(overrides)
    deps = PipelineDeps(
        make_registry=lambda: registry,
        evaluate=None, build_brief=None, render_template=None, validate=None, render_markdown=None,
        **funcs)
    return deps, registry


def make_toolbox(deps, **kwargs):
    return ToolBox(deps, PORTFOLIO, as_of="2025-01-01", capital_cad=1000.0, **kwargs)


VALID_IDEA = {"ticker": "tsla", "target_weight": 0.25, "funding_source": "pro_rata"}


# ---- normalize_idea ----

def test_normalize_valid_uppercases_and_defaults():
    idea, problem = normalize_idea(VALID_IDEA)
    assert problem is None
    assert idea == {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata",
                    "funding_ticker": None}


def test_normalize_from_ticker_valid():
    idea, _ = normalize_idea({"ticker": " aaa ", "target_weight": 1, "funding_source": "from_ticker",
                              "funding_ticker": " bbb "})
    assert idea["ticker"] == "AAA" and idea["funding_ticker"] == "BBB" and idea["target_weight"] == 1.0


def test_normalize_pro_rata_clears_funding_ticker():
    idea, _ = normalize_idea({**VALID_IDEA, "funding_ticker": "bbb"})
    assert idea["funding_ticker"] is None


@pytest.mark.parametrize("raw, fragment", [
    ("pas un dict", "objet"),
    ({**VALID_IDEA, "ticker": ""}, "ticker manquant"),
    ({**VALID_IDEA, "ticker": 5}, "ticker manquant"),
    ({**VALID_IDEA, "target_weight": 0}, "target_weight"),
    ({**VALID_IDEA, "target_weight": 1.01}, "target_weight"),
    ({**VALID_IDEA, "target_weight": -0.1}, "target_weight"),
    ({**VALID_IDEA, "target_weight": True}, "target_weight"),
    ({**VALID_IDEA, "target_weight": "0.2"}, "target_weight"),
    ({**VALID_IDEA, "funding_source": "autre"}, "funding_source doit valoir"),
    ({**VALID_IDEA, "funding_source": "from_ticker"}, "funding_ticker est requis"),
    ({**VALID_IDEA, "funding_source": "from_ticker", "funding_ticker": "  "}, "funding_ticker est requis"),
])
def test_normalize_errors(raw, fragment):
    idea, problem = normalize_idea(raw)
    assert idea is None and fragment in problem


# ---- TOOL_SPECS ----

def spec_names():
    return [s["toolSpec"]["name"] for s in TOOL_SPECS]


def test_tool_specs_exact_set_and_no_order_tool():
    assert sorted(spec_names()) == [
        "analyze_portfolio", "get_asset_facts", "simulate_portfolio_change", "submit_analysis"]
    for forbidden in ("order", "trade", "buy", "sell", "execute", "broker"):
        assert not any(forbidden in name for name in spec_names())


def test_submit_analysis_caps():
    spec = next(s for s in TOOL_SPECS if s["toolSpec"]["name"] == "submit_analysis")
    props = spec["toolSpec"]["inputSchema"]["json"]["properties"]
    assert MAX_VARIANTS == 2 and MAX_HIGHLIGHTS == 2
    assert props["variants"]["maxItems"] == 2
    assert props["highlight_evidence_ids"]["maxItems"] == 2


def test_tool_config_returns_copy():
    config = tool_config()
    config["tools"][0]["toolSpec"]["name"] = "modifie"
    config["tools"].pop()
    assert spec_names()[0] == "analyze_portfolio" and len(TOOL_SPECS) == 4
    assert tool_config()["tools"][0]["toolSpec"]["name"] == "analyze_portfolio"


# ---- ToolBox ----

def test_budget_exceeded_at_13th_call():
    deps, _ = make_deps()
    box = make_toolbox(deps)
    for _ in range(MAX_TOOL_CALLS):
        box.call("analyze_portfolio")
    assert box.calls_used == 12
    with pytest.raises(ToolBudgetExceeded):
        box.call("analyze_portfolio")
    assert box.calls_used == 12


def test_custom_budget():
    deps, _ = make_deps()
    box = make_toolbox(deps, max_calls=1)
    box.call("analyze_portfolio")
    with pytest.raises(ToolBudgetExceeded):
        box.call("analyze_portfolio")


def test_unknown_tool_is_error_and_counts():
    deps, registry = make_deps()
    box = make_toolbox(deps)
    result = box.call("place_order", {"ticker": "AAA"})
    assert result["status"] == "error" and "inconnu" in result["error_message"]
    assert box.calls[0]["status"] == "error" and registry.registered == []


def test_get_asset_facts_missing_ticker():
    deps, _ = make_deps()
    box = make_toolbox(deps)
    for params in (None, {}, {"ticker": "  "}, {"ticker": 3}):
        assert box.call("get_asset_facts", params)["status"] == "error"


def test_get_asset_facts_uppercases_ticker():
    seen = []
    deps, _ = make_deps(get_asset_facts=lambda ticker, as_of=None: seen.append((ticker, as_of)) or {
        "tool_name": "get_asset_facts", "params": {}, "status": "ok", "error_message": None,
        "data": {}, "evidence": []})
    make_toolbox(deps).call("get_asset_facts", {"ticker": "aaa"})
    assert seen == [("AAA", "2025-01-01")]


def test_simulate_invalid_idea_is_error_and_not_forwarded():
    forwarded = []
    deps, _ = make_deps(simulate_portfolio_change=lambda *a, **k: forwarded.append(1))
    result = make_toolbox(deps).call("simulate_portfolio_change", {"ticker": "AAA", "target_weight": 5,
                                                                     "funding_source": "pro_rata"})
    assert result["status"] == "error" and "target_weight" in result["error_message"]
    assert forwarded == []


def test_failing_tool_becomes_error_without_detail():
    def boom(*args, **kwargs):
        raise RuntimeError(SECRET_DETAIL)

    deps, registry = make_deps(analyze_portfolio=boom)
    box = make_toolbox(deps)
    result = box.call("analyze_portfolio")
    assert result["status"] == "error" and result["evidence"] == []
    assert "RuntimeError" in result["error_message"]
    assert SECRET_DETAIL not in result["error_message"] and "AKIA" not in result["error_message"]
    assert registry.registered == []
    assert box.calls[0]["status"] == "error"


def test_calls_results_and_evidence_consistent():
    deps, registry = make_deps()
    box = make_toolbox(deps)
    box.call("analyze_portfolio")
    box.call("get_asset_facts", {"ticker": "aaa"})
    box.call("simulate_portfolio_change", VALID_IDEA)
    assert [c["tool_name"] for c in box.calls] == [
        "analyze_portfolio", "get_asset_facts", "simulate_portfolio_change"]
    assert [c["evidence_ids"] for c in box.calls] == [["E1"], ["E2"], ["E3"]]
    assert len(box.results) == 3 and box.calls_used == 3
    assert sorted(box.evidence()) == ["E1", "E2", "E3"]
    assert registry.registered == ["analyze_portfolio", "get_asset_facts", "simulate_portfolio_change"]


def test_default_call_id_and_existing_call_id_kept():
    deps, _ = make_deps(get_asset_facts=lambda ticker, as_of=None: {
        "tool_name": "get_asset_facts", "call_id": "mon-id", "params": {}, "status": "ok",
        "error_message": None, "data": {}, "evidence": []})
    box = make_toolbox(deps)
    first = box.call("analyze_portfolio")
    second = box.call("get_asset_facts", {"ticker": "aaa"})
    assert first["call_id"] == "call-1" and second["call_id"] == "mon-id"


def test_registry_only_called_for_ok_results():
    deps, registry = make_deps(analyze_portfolio=lambda *a, **k: {
        "tool_name": "analyze_portfolio", "params": {}, "status": "missing_info",
        "error_message": "donnee absente", "data": {}, "evidence": []})
    box = make_toolbox(deps)
    result = box.call("analyze_portfolio")
    assert result["status"] == "missing_info" and registry.registered == []


def test_tool_output_not_mutated_between_calls():
    shared = {"tool_name": "analyze_portfolio", "params": {}, "status": "ok", "error_message": None,
              "data": {}, "evidence": [evidence("E1")]}
    deps, _ = make_deps(analyze_portfolio=lambda *a, **k: shared)
    make_toolbox(deps).call("analyze_portfolio")
    assert "call_id" not in shared
