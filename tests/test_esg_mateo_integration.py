"""Tests B : exigence ESG de Mateo avec les vrais outils (mode hors ligne, aucun appel AWS).

Aucune preuve ESG n'existe : la règle ESG rend `missing_info`, jamais `compliant`.
La conformité financière reste distincte de la vérification ESG impossible.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge.analysis_pipeline import explain, run_analysis  # noqa: E402
from alphaforge.bedrock_client import BedrockConfig  # noqa: E402
from alphaforge.explanation_brief import build_brief  # noqa: E402
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import render_markdown  # noqa: E402
from alphaforge.explanation_validator import validate  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

IDEAS = {
    "tsla_25": ("TSLA", 0.25, "pro_rata"),
    "btc_20": ("BTC-USD", 0.20, "pro_rata"),
    "nvda_20": ("NVDA", 0.20, "from_ticker"),
    "xom_10": ("XOM", 0.10, "pro_rata"),
}
# Verdicts après l'idée, hors ligne, données réelles (les mêmes que `scripts/run_scenarios.py`).
EXPECTED = {
    ("mateo", "tsla_25"): "missing_info", ("mateo", "btc_20"): "conflict",
    ("mateo", "nvda_20"): "missing_info", ("mateo", "xom_10"): "missing_info",
    ("robert", "tsla_25"): "conflict", ("robert", "btc_20"): "conflict",
    ("robert", "nvda_20"): "tension", ("robert", "xom_10"): "compliant",
    ("amira", "tsla_25"): "tension", ("amira", "btc_20"): "tension",
    ("amira", "nvda_20"): "tension", ("amira", "xom_10"): "compliant",
}


def analyse(persona_id, scenario):
    persona = load_personas()[persona_id]
    ticker, weight, funding = IDEAS[scenario]
    funding_ticker = None
    if funding == "from_ticker":
        funding_ticker = max(persona["portfolio"]["positions"], key=lambda p: p["weight"])["ticker"]
    idea = {"ticker": ticker, "target_weight": weight, "funding_source": funding, "funding_ticker": funding_ticker}
    return run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline", config=BedrockConfig())


@pytest.fixture(scope="module")
def results():
    return {key: analyse(*key) for key in EXPECTED}


def test_verdicts_of_the_demo_scenarios(results):
    for key, expected in EXPECTED.items():
        result = results[key]
        assert result["is_fixture"] is False
        assert result["governance_after"]["overall_status"] == expected, key


def test_robert_and_amira_have_no_esg_rule_and_keep_six_rules(results):
    for (persona, _), result in results.items():
        if persona != "mateo":
            assert all(c["rule_type"] != "esg_exclusion" for c in result["governance_after"]["checks"])
            assert len(result["governance_after"]["checks"]) == 6


def test_mateo_esg_check_is_missing_info_before_and_after(results):
    for scenario in IDEAS:
        result = results[("mateo", scenario)]
        for key in ("governance_before", "governance_after"):
            esg = [c for c in result[key]["checks"] if c["rule_type"] == "esg_exclusion"]
            assert len(esg) == 1 and esg[0]["status"] == "missing_info" and esg[0]["value"] is None
            assert esg[0]["evidence_ids"] == [] and esg[0]["counterfactual"] is None
        # Aucune preuve ESG (le libellé de secteur du FNB ESGV n'en est pas une).
        assert not any(e["metric"].lower().startswith("esg") or "esg" in e["tool_name"].lower()
                       for e in result["evidence"].values())


def test_mateo_financial_rules_are_still_evaluated_normally(results):
    xom = results[("mateo", "xom_10")]["governance_after"]["checks"]
    financial = [c for c in xom if c["rule_type"] != "esg_exclusion"]
    assert len(financial) == 6 and all(c["status"] == "compliant" for c in financial)
    btc = {c["rule_id"]: c["status"] for c in results[("mateo", "btc_20")]["governance_after"]["checks"]}
    assert btc["R5"] == "conflict" and btc["R7"] == "missing_info"      # le conflit financier prime


@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("scenario", list(IDEAS))
def test_mateo_explanation_is_valid_and_honest(results, level, scenario):
    result = results[("mateo", scenario)]
    brief = build_brief(result, level)
    esg_check = next(c for c in brief["checks"] if c["rule_type"] == "esg_exclusion")
    assert esg_check["check_id"] in [f["check_id"] for f in brief["ranked_factors"]]
    assert any(t["term"] == "Critère ESG" for t in brief["glossary"])
    output = render_template(brief)
    outcome = validate(output, brief)
    assert outcome["is_valid"] is True, outcome["rejections"]
    assert validate(output, brief, allow_registry_numbers=False)["is_valid"] is True
    assert f"[{esg_check['check_id']}]" in output["summary"]
    esg_factor = next(f for f in output["factors"] if f["check_id"] == esg_check["check_id"])
    text = esg_factor["text"].lower()
    assert "preuve esg" in text and "impossible" in text or "information manquante" in text
    assert "conforme" not in text and "respect" not in text
    markdown = render_markdown(output, brief)
    assert "Exclusion ESG" in markdown and "information manquante" in markdown
    assert not re.search(r"\[[EGT]\d+\]", markdown)


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_financially_compliant_xom_is_not_presented_as_esg_compliant(results, level):
    result = results[("mateo", "xom_10")]
    explanation = explain(result, level, mode="offline", config=BedrockConfig())
    assert explanation["validation"]["is_valid"] is True
    summary = explanation["output"]["summary"]
    assert "[G7]" in summary
    assert "toutes les règles" not in summary.lower()
    if level == "novice":
        assert "autres règles évaluées sont respectées" in summary and "n'a pas pu être vérifié" in summary
    else:
        assert "règles évaluables sont conformes" in summary and "sans verdict" in summary.lower()
    assert "aucune preuve esg" in explanation["rendered_markdown"].lower()


def test_summary_does_not_claim_other_rules_are_met_when_nothing_is_compliant():
    brief = build_brief(analyse("mateo", "xom_10"), "novice")
    for check in brief["checks"]:
        check.update(status="missing_info", value=None, margin=None, missing_reason="Valeur indisponible.")
    brief["ranked_factors"] = [{"rank": i, "check_id": c["check_id"], "status": "missing_info", "evidence_ids": []}
                               for i, c in enumerate(brief["checks"], start=1)]
    summary = render_template(brief)["summary"]
    assert "autres règles évaluées sont respectées" not in summary


def test_robert_and_amira_summaries_keep_their_usual_form(results):
    for key in (("robert", "xom_10"), ("amira", "xom_10")):
        assert "respecte toutes les règles" in render_template(build_brief(results[key], "novice"))["summary"]
    for key in (("robert", "tsla_25"), ("amira", "tsla_25")):
        assert "Verdict global" in render_template(build_brief(results[key], "pro"))["summary"]


def test_limit_lm5_mentions_missing_esg_in_every_mateo_brief(results):
    for level in ("novice", "pro"):
        brief = build_brief(results[("mateo", "xom_10")], level)
        lm5 = next(i for i in brief["limits"] if i["limit_id"] == "LM5")
        assert "ESG" in lm5["text"]
