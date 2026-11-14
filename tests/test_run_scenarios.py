"""Tests de scripts/run_scenarios.py avec des bouchons : aucun pipeline réel, aucun AWS."""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_scenarios", PROJECT_ROOT / "scripts" / "run_scenarios.py")
rs = importlib.util.module_from_spec(_spec)
sys.modules["run_scenarios"] = rs
_spec.loader.exec_module(rs)

PORTFOLIO = {"positions": [
    {"ticker": "AAA", "weight": 0.4},
    {"ticker": "BBB", "weight": 0.4},
    {"ticker": "NVDA", "weight": 0.2},
]}
DATA = {"profile": {"profile_id": "x"}, "portfolio": PORTFOLIO}


def fake_analysis(profile, portfolio, idea, as_of=None, mode="offline"):
    return {
        "is_fixture": True,
        "mode": "offline",
        "trace": [{"name": "analysis", "actor": "analyste_test",
                   "details": {"fallback_reason": "configuration_incomplete"}}],
        "governance_before": {"overall_status": "compliant", "checks": []},
        "governance_after": {"overall_status": "violation", "checks": [
            {"rule_id": "R1", "label_fr": "Plafond", "status": "violation",
             "counterfactual": {"display_value": "5 %"}},
            {"rule_id": "R2", "label_fr": "Diversification", "status": "compliant"},
        ]},
        "variants": [{"variant_id": "v1", "reason_code": "reduced", "idea": {"target_weight": 0.05},
                      "governance": {"overall_status": "compliant"}}],
    }


def make_explain(details=None, displayed="llm", valid=True, final_codes=None):
    """Explication factice ; `details` reproduit l'étape de trace 'explanation'."""
    def fake_explain(result, level, mode="offline"):
        return {
            "output": {"origin": displayed},
            "validation": {"is_valid": valid, "rejections": [{"code": c} for c in (final_codes or [])]},
            "guardrail": {"action": "NONE", "grounding_score": 0.9},
            "trace": [{"name": "explanation", "details": details if details is not None else {}}],
            "rendered_markdown": f"# Texte {level}",
        }
    return fake_explain


LLM_OK = {"origin": "llm", "attempt": 1, "rejection_codes": []}
LLM_RETRY = {"origin": "llm", "attempt": 2, "rejection_codes": ["c1"]}
LLM_TWICE = {"origin": "llm", "attempt": 2, "rejection_codes": ["c1", "c2"], "fallback_reason": "rejet_du_validateur"}
EXPLAINER_FAIL = {"origin": "template", "attempt": 1, "fallback_reason": "BedrockError: panne"}


def scenario(idea=None):
    return rs.Scenario("s1", "Scénario", idea or {"ticker": "TSLA", "target_weight": 0.1,
                                                  "funding_source": "pro_rata", "funding_ticker": None})


def run(details, displayed="llm", **kw):
    return rs.run_one("p", DATA, scenario(), "offline", None, fake_analysis, make_explain(details, displayed, **kw))


def test_scenarios_shape_and_unique_ids():
    assert [s.scenario_id for s in rs.SCENARIOS] == ["tsla_25", "btc_20", "nvda_20_from_largest", "xom_10"]
    for s in rs.SCENARIOS:
        assert {"ticker", "target_weight", "funding_source", "funding_ticker"} <= set(s.idea)
        assert 0 < s.idea["target_weight"] < 1
        assert s.label_fr.startswith("Demande fictive :"), "libellé de demande fictive attendu"


def test_resolve_idea_largest_holding_excludes_idea_ticker_and_no_mutation():
    idea = {"ticker": "AAA", "target_weight": 0.1, "funding_source": "from_ticker",
            "funding_ticker": rs.LARGEST_HOLDING}
    resolved = rs.resolve_idea(idea, PORTFOLIO)
    assert resolved["funding_ticker"] == "BBB", "AAA exclu, égalité résolue par ordre alphabétique"
    assert idea["funding_ticker"] == rs.LARGEST_HOLDING, "l'entrée ne doit pas être modifiée"
    idea["ticker"] = "ZZZ"
    assert rs.resolve_idea(idea, PORTFOLIO)["funding_ticker"] == "AAA"


def test_resolve_idea_tie_alphabetical_and_unchanged_others():
    idea = {"ticker": "TSLA", "target_weight": 0.1, "funding_source": "pro_rata", "funding_ticker": None}
    out = rs.resolve_idea(idea, PORTFOLIO)
    assert out == idea and out is not idea
    idea2 = {**idea, "funding_source": "from_ticker", "funding_ticker": rs.LARGEST_HOLDING}
    assert rs.resolve_idea(idea2, PORTFOLIO)["funding_ticker"] == "AAA"


def test_has_no_effect():
    assert rs.has_no_effect({"ticker": "NVDA", "target_weight": 0.2}, PORTFOLIO) is True
    assert rs.has_no_effect({"ticker": "NVDA", "target_weight": 0.25}, PORTFOLIO) is False
    assert rs.has_no_effect({"ticker": "NEW", "target_weight": 0.1}, PORTFOLIO) is False
    idea = {"ticker": "NVDA", "target_weight": 0.2, "funding_source": "pro_rata", "funding_ticker": None}
    o = rs.run_one("p", DATA, rs.Scenario("s", "L", idea), "offline", None, fake_analysis, make_explain(LLM_OK))
    assert o.no_effect is True
    assert "(sans effet)" in rs.render_summary([o], "offline", None, "t")


def test_run_one_maps_fields():
    o = run(LLM_RETRY)
    assert o.ok and o.error is None and o.no_effect is False
    assert o.is_fixture is True and o.effective_mode == "offline"
    assert o.analyst_actor == "analyste_test"
    assert o.analyst_fallback_reason == "configuration_incomplete"
    assert (o.status_before, o.status_after) == ("compliant", "violation")
    assert o.non_compliant == ["R1 Plafond : violation"]
    assert o.counterfactuals == {"R1": "5 %"}
    assert o.variants == [{"variant_id": "v1", "reason_code": "reduced", "target_weight": 0.05,
                           "funding_ticker": None, "status": "compliant"}]
    assert set(o.explanations) == {"novice", "pro"}
    e = o.explanations["pro"]
    assert e["displayed_origin"] == "llm" and e["llm_produced"] is True and e["llm_attempt"] == 2
    assert e["llm_rejection_codes"] == ["c1"] and e["first_attempt_not_kept"] is True
    assert e["rejected_twice"] is False and e["explainer_failed"] is False
    assert e["is_valid"] is True and e["guardrail_action"] == "NONE" and e["grounding_score"] == 0.9
    assert e["rendered_markdown"] == "# Texte pro"
    for old in ("origin", "first_attempt_rejected", "rejection_codes"):
        assert old not in e, f"ancienne clé {old} supprimée"


def test_summarize_four_cases():
    ok = run(LLM_OK).explanations["pro"]
    assert ok["llm_produced"] and not ok["first_attempt_not_kept"] and not ok["rejected_twice"]
    retry = run(LLM_RETRY).explanations["pro"]
    assert retry["first_attempt_not_kept"] and not retry["rejected_twice"]
    twice = run(LLM_TWICE, displayed="template", final_codes=["z"]).explanations["pro"]
    assert twice["llm_produced"] and twice["rejected_twice"] and twice["first_attempt_not_kept"]
    assert twice["displayed_origin"] == "template" and twice["final_rejection_codes"] == ["z"]
    fail = run(EXPLAINER_FAIL, displayed="template").explanations["pro"]
    assert not fail["llm_produced"] and fail["explainer_failed"] and fail["llm_attempt"] is None


def test_explainer_failure_prefixes():
    for reason in ("ExplainerFailure x", "AgentFailure", "BedrockError", "explicateur_indisponible",
                   "configuration_incomplete"):
        assert rs._is_explainer_failure(reason)
    assert not rs._is_explainer_failure("rejet_du_validateur")
    assert not rs._is_explainer_failure(None)


def test_run_one_exceptions_not_propagated_truncated_and_redacted(capsys):
    def boom(*a, **k):
        raise ValueError("x" * 1000)

    o = rs.run_one("p", DATA, scenario(), "offline", None, boom, make_explain(LLM_OK))
    assert o.ok is False and o.error.startswith("ValueError : ")
    assert len(o.error) <= len("ValueError : ") + 300
    assert "Traceback" in capsys.readouterr().err, "la trace va sur stderr"

    fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"

    def leak(*a, **k):
        raise RuntimeError(f"cle {fake_key} exposee")

    o2 = rs.run_one("p", DATA, scenario(), "offline", None, leak, make_explain(LLM_OK))
    assert fake_key not in o2.error, "le motif de clé AWS doit être masqué"

    def boom_explain(*a, **k):
        raise RuntimeError("panne")

    o3 = rs.run_one("p", DATA, scenario(), "offline", None, fake_analysis, boom_explain)
    assert o3.ok is False and o3.error == "RuntimeError : panne"


def test_rejection_rate_four_cases_and_llm_used():
    outcomes = [run(LLM_OK), run(LLM_RETRY), run(LLM_TWICE, displayed="template"),
                run(EXPLAINER_FAIL, displayed="template")]
    # 3 scénarios avec texte modèle x 2 niveaux = 6 ; non retenus : retry (2) + twice (2) = 4
    assert rs.rejection_rate(outcomes) == (4, 6)
    assert rs.llm_used(outcomes) is True
    assert rs.llm_used([run(EXPLAINER_FAIL, displayed="template")]) is False
    assert rs.rejection_rate([run(EXPLAINER_FAIL, displayed="template")]) == (0, 0)


def test_render_summary_french_counts_and_no_em_dash():
    ok = run(EXPLAINER_FAIL, displayed="template")
    bad = rs.run_one("q", DATA, scenario(), "offline", None, lambda *a, **k: 1 / 0, make_explain(LLM_OK))
    text = rs.render_summary([ok, bad], "offline", None, "2026-01-01 10:00")
    assert "Scénarios : 2 (1 en échec, 0 sans effet)" in text
    assert "sans objet" in text and "fin des données" in text
    assert "Mode demandé : `offline` ; mode effectif : `offline`" in text
    assert "Simulation éducative, pas un conseil personnalisé" in text
    assert "échec" in text and "ZeroDivisionError" in text
    assert "\u2014" not in text
    mixed = rs.render_summary([run(LLM_OK), run(LLM_TWICE, displayed="template"),
                               run(EXPLAINER_FAIL, displayed="template")],
                              "bedrock", "2025-01-01", "t")
    assert "2 sur 4 textes rédigés" in mixed
    assert "Rejeté deux fois, gabarit affiché : 2" in mixed
    assert "hors taux) : 2" in mixed
    assert "sans objet" not in mixed and "**Attention" not in mixed
    assert "\u2014" not in mixed


def test_summary_warns_when_bedrock_without_llm():
    text = rs.render_summary([run(EXPLAINER_FAIL, displayed="template")], "bedrock", None, "t")
    assert "**Attention" in text


def test_write_report(tmp_path):
    ok = run(LLM_OK)
    run_dir = rs.write_report([ok], tmp_path, "offline", None, now=datetime(2026, 1, 2, 3, 4, 5))
    assert run_dir.name == "offline_20260102_030405"
    assert (run_dir / "summary.md").is_file()
    raw = (run_dir / "results.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload[0]["persona"] == "p" and payload[0]["effective_mode"] == "offline"
    assert "rendered_markdown" not in raw
    assert "secret" not in raw.lower() and "token" not in raw.lower()
    assert "Traceback" not in raw
    for level in ("novice", "pro"):
        f = run_dir / "explanations" / f"p__s1__{level}.md"
        assert f.read_text(encoding="utf-8") == f"# Texte {level}"


def test_run_all_order_and_unknown_persona():
    from alphaforge.profiles import load_personas

    names = sorted(load_personas())
    outcomes = rs.run_all(run_analysis=fake_analysis, explain=make_explain(LLM_OK))
    assert len(outcomes) == 12
    assert [(o.persona, o.scenario_id) for o in outcomes] == [
        (n, s.scenario_id) for n in names for s in rs.SCENARIOS]
    assert all(o.ok for o in outcomes)
    with pytest.raises(SystemExit):
        rs.run_all(personas=["inconnu"], run_analysis=fake_analysis, explain=make_explain(LLM_OK))


def test_resolve_out_dir(tmp_path):
    assert rs.resolve_out_dir(Path("rel/dir")) == PROJECT_ROOT / "rel" / "dir"
    assert rs.resolve_out_dir(tmp_path) == tmp_path


def _fake_outcomes(ok=True, llm=True):
    o = rs.ScenarioOutcome(persona="p", scenario_id="s1", idea={}, ok=ok, error=None if ok else "E : x",
                           status_before="compliant", status_after="compliant")
    if ok:
        details = LLM_OK if llm else EXPLAINER_FAIL
        o.explanations = {"novice": rs._summarize_explanation(make_explain(details)(None, "novice"))}
    return [o]


def test_main_exit_codes(tmp_path, monkeypatch):
    state = {"ok": True, "llm": True}

    def fake_run_all(mode, as_of, personas):
        state["mode"] = mode
        return _fake_outcomes(state["ok"], state["llm"])

    monkeypatch.setattr(rs, "run_all", fake_run_all)
    assert rs.main(["--out", str(tmp_path)]) == 0
    assert state["mode"] == "offline", "le mode par défaut doit être hors ligne"
    state["llm"] = False
    assert rs.main(["--out", str(tmp_path)]) == 0, "hors ligne sans texte modèle reste 0"
    assert rs.main(["--mode", "bedrock", "--out", str(tmp_path)]) == rs.EXIT_NO_LLM == 2
    state["llm"] = True
    assert rs.main(["--mode", "bedrock", "--out", str(tmp_path)]) == 0
    state["ok"] = False
    assert rs.main(["--mode", "bedrock", "--out", str(tmp_path)]) == 1, "les échecs sont prioritaires"


def test_main_rejects_unknown_mode(tmp_path):
    with pytest.raises(SystemExit):
        rs.main(["--mode", "nimporte", "--out", str(tmp_path)])
