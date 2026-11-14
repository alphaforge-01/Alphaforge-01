"""B0 checks. All finance figures in tests/fixtures/ are invented."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.contracts import (
    check_keys, InvestorProfile, Portfolio, InvestmentIdea, ToolResult,
    AnalysisResult, ExplanationBrief, ExplainerOutput
)

FIXTURES = Path(__file__).parent / "fixtures"
CASES = {
    "profile_robert.json": InvestorProfile,
    "profile_amira.json": InvestorProfile,
    "portfolio_robert.json": Portfolio,
    "idea_tsla_25.json": InvestmentIdea,
    "analysis_result_robert_tsla.json": AnalysisResult,
    "analysis_result_amira_tsla.json": AnalysisResult,
    "explanation_brief_robert_novice.json": ExplanationBrief,
    "explainer_output_robert_novice.json": ExplainerOutput,
    "explainer_output_robert_pro.json": ExplainerOutput,
    "explainer_output_invalid.json": ExplainerOutput,
}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_fixture_required_keys():
    for name, contract in CASES.items():
        assert check_keys(load(name), contract) == [], name
    for row in load("tool_results_robert_tsla.json"):
        assert check_keys(row, ToolResult) == []


def test_fixture_flags_and_weights():
    for name in ("analysis_result_robert_tsla.json", "analysis_result_amira_tsla.json"):
        result = load(name)
        assert result["is_fixture"] is True
        assert abs(sum(p["weight"] for p in result["portfolio_before"]["positions"]) - 1.0) < 1e-9
        assert all(rule["is_assumption"] is True for rule in result["profile"]["rules"])


def test_check_keys_detects_missing():
    assert "profile_id" in check_keys({}, InvestorProfile)
# ---------- ExplanationResult.brief facultatif ----------
def _explanation_result(with_brief):
    from alphaforge.explanation_brief import build_brief
    from alphaforge.explanation_fallback import render_template
    from alphaforge.explanation_rendering import render_markdown
    from alphaforge.explanation_validator import validate
    brief = build_brief(load("analysis_result_robert_tsla.json"), "novice")
    output = render_template(brief)
    guardrail = {"check": "output_grounding", "action": "not_run", "denied_topics": [],
                 "grounding_score": None, "relevance_score": None, "mode": "detect"}
    result = {"output": output, "validation": validate(output, brief), "guardrail": guardrail,
              "rendered_markdown": render_markdown(output, brief), "trace": []}
    if with_brief:
        result["brief"] = brief
    return result
def test_explanation_result_without_brief_is_valid():
    from alphaforge.contracts import ExplanationResult
    assert "brief" not in _explanation_result(False)
    assert check_keys(_explanation_result(False), ExplanationResult) == []
def test_explanation_result_with_brief_is_valid():
    from alphaforge.contracts import ExplanationResult
    result = _explanation_result(True)
    assert check_keys(result, ExplanationResult) == []
    assert check_keys(result["brief"], ExplanationBrief) == []
def test_brief_is_optional_but_other_keys_stay_required():
    from alphaforge.contracts import ExplanationResult
    for with_brief in (False, True):
        result = _explanation_result(with_brief)
        del result["rendered_markdown"], result["trace"]
        assert check_keys(result, ExplanationResult) == ["rendered_markdown", "trace"]
def test_check_keys_reports_brief_only_when_declared_required():
    from typing import TypedDict
    class Other(TypedDict):
        brief: dict
    assert check_keys({}, Other) == ["brief"]
def test_pipeline_explain_result_stays_compatible_with_or_without_brief():
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.contracts import ExplanationResult
    from alphaforge.fixture_collaborators import fixture_deps
    from alphaforge.pipeline_deps import PipelineDeps  # noqa: F401
    deps = fixture_deps()
    profile = load("profile_robert.json")
    portfolio = load("portfolio_robert.json")
    analysis = run_analysis(profile, portfolio, load("idea_tsla_25.json"), deps=deps, config=BedrockConfig())
    explanation = explain(analysis, "novice", deps=deps, config=BedrockConfig())
    assert check_keys(explanation, ExplanationResult) == []
    explanation["brief"] = deps.build_brief(analysis, "novice")
    assert check_keys(explanation, ExplanationResult) == []
