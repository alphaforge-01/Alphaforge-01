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
