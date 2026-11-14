"""Tests de scripts/try_bedrock_run.py : pipeline et garde-fou simulés, aucun appel AWS."""
from pathlib import Path
import json
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import try_bedrock_run as tbr  # noqa: E402

# Valeurs inventées, construites par concaténation : aucun secret réel dans le source.
FAKE_ACCOUNT = "0" * 12
FAKE_KEY = "AKIA" + "X" * 16
FAKE_GUARDRAIL_ID = "fakeguard" + "01"
ENV = {
    "AWS_REGION": "us-east-1",
    "ALPHAFORGE_ANALYST_MODEL_ID": "provider.model-fictif-v1",
    "ALPHAFORGE_EXPLAINER_MODEL_ID": "provider.model-fictif-v1",
    "ALPHAFORGE_GUARDRAIL_ID": FAKE_GUARDRAIL_ID,
    "ALPHAFORGE_GUARDRAIL_VERSION": "3",
    "ALPHAFORGE_TRACE_BUCKET": "alphaforge-traces-" + "abcd1234",
}
TWELVE_DIGITS = re.compile(r"(?<!\d)\d{12}(?!\d)")
PERSONAS = {
    name: {"profile": {"profile_id": name, "default_level": "novice"},
           "portfolio": {"portfolio_id": f"pf-{name}", "positions": []}}
    for name in ("robert", "amira", "mateo")
}


def fake_result(mode="bedrock", step_status="ok", actor="agent", fallback=None):
    details = {"mode_requested": "bedrock", "mode_effective": mode, "turns": 2, "stop_reason": "end_turn",
               "tool_calls": [{"tool_name": "analyze_portfolio", "params": {}},
                              {"tool_name": "simulate_portfolio_change", "params": {"ticker": "TSLA"}}]}
    if fallback:
        details["fallback_reason"] = fallback
    return {
        "run_id": "run0001", "created_at": "2026-11-14T00:00:00+00:00", "mode": mode, "is_fixture": False,
        "trace": [
            {"step": 1, "name": "analysis", "actor": actor, "status": step_status, "details": details},
            {"step": 2, "name": "governance", "actor": "code", "status": "ok", "details": {}},
            {"step": 3, "name": "brief", "actor": "code", "status": "ok",
             "details": {"trace_saved": {"saved": True, "location": "traces/2026-11-14/run0001.json",
                                         "reason": None}}},
        ],
    }


def fake_explanation(level, origin="llm", guard_status="ok"):
    return {
        "output": {"level": level, "origin": origin},
        "validation": {"is_valid": True, "rejections": []},
        "guardrail": {"check": "output_grounding", "action": "none", "denied_topics": [],
                      "grounding_score": 0.91, "relevance_score": 0.88, "mode": "detect"},
        "trace": [
            {"step": 4, "name": "explanation", "actor": "agent" if origin == "llm" else "code",
             "status": "ok" if origin == "llm" else "fallback",
             "details": {} if origin == "llm" else {"fallback_reason": "BedrockAuthError: jeton expire"}},
            {"step": 5, "name": "validation", "actor": "code", "status": "ok", "details": {}},
            {"step": 6, "name": "guardrail", "actor": "guardrail", "status": guard_status,
             "details": {"trace_saved": {"saved": False, "location": None, "reason": "bucket_non_configure"}}},
        ],
    }


class Recorder:
    def __init__(self, result=None, explanation=None, error=None):
        self.analyses = []
        self.explanations = []
        self.result = result or fake_result()
        self.explanation = explanation or fake_explanation
        self.error = error

    def run_analysis(self, profile, portfolio, idea, **kwargs):
        self.analyses.append((profile["profile_id"], idea, kwargs))
        if self.error:
            raise self.error
        return self.result

    def explain(self, result, level, **kwargs):
        self.explanations.append((level, kwargs))
        return self.explanation(level)


def run(argv, recorder=None, env=ENV, **extra):
    recorder = recorder or Recorder()
    kwargs = dict(
        environ=env, deps_factory=lambda: type("Deps", (), {"is_fixture": False})(),
        client_factory=lambda config: object(), personas_loader=lambda: PERSONAS,
        run_analysis_fn=recorder.run_analysis, explain_fn=recorder.explain,
    )
    kwargs.update(extra)
    return tbr.main(argv, **kwargs), recorder


def assert_clean(text):
    assert FAKE_KEY not in text
    assert FAKE_ACCOUNT not in text
    assert not TWELVE_DIGITS.search(text)
    assert FAKE_GUARDRAIL_ID not in text
    assert "\u2014" not in text


# ---------------------------------------------------------------------------
# Simulation et configuration
# ---------------------------------------------------------------------------

def test_dry_run_calls_nothing(capsys, monkeypatch):
    import boto3

    def forbidden(*args, **kwargs):
        raise AssertionError("aucun appel réseau en simulation")
    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(boto3, "Session", forbidden)
    calls = []
    code, recorder = run([], client_factory=lambda c: calls.append(c),
                         deps_factory=lambda: calls.append("deps"),
                         check_request_fn=lambda *a, **k: calls.append("check"))
    assert code == tbr.EXIT_OK
    assert calls == [] and recorder.analyses == [] and recorder.explanations == []
    out = capsys.readouterr().out
    assert "Mode simulation" in out
    assert "robert, amira" in out
    assert "ALPHAFORGE_GUARDRAIL_ID : défini" in out
    assert_clean(out)


def test_dry_run_reports_missing_variables(capsys):
    env = {k: v for k, v in ENV.items() if k != "ALPHAFORGE_GUARDRAIL_VERSION"}
    code, _ = run(["--dry-run"], env=env)
    assert code == tbr.EXIT_CONFIG_ERROR
    assert "ALPHAFORGE_GUARDRAIL_VERSION" in capsys.readouterr().out


def test_run_refused_when_variables_missing():
    code, recorder = run(["--run"], env={"AWS_REGION": "us-east-1"})
    assert code == tbr.EXIT_CONFIG_ERROR
    assert recorder.analyses == []


def test_budget_refused_beyond_three_personas(capsys):
    code, recorder = run(["--run", "--personas", "robert,amira,mateo,custom"])
    assert code == tbr.EXIT_CONFIG_ERROR
    assert recorder.analyses == []
    assert "Budget dépassé" in capsys.readouterr().out


def test_duplicates_do_not_count_against_budget():
    assert tbr.parse_personas("Robert, robert,amira") == ["robert", "amira"]
    assert tbr.check_budget(["robert", "amira", "mateo"]) is None
    assert tbr.MAX_PIPELINE_CALLS == 9


def test_unknown_persona_is_refused():
    code, recorder = run(["--run", "--personas", "inconnu"])
    assert code == tbr.EXIT_CONFIG_ERROR
    assert recorder.analyses == []


# ---------------------------------------------------------------------------
# Exécution simulée
# ---------------------------------------------------------------------------

def test_run_success_summary(capsys):
    code, recorder = run(["--run"])
    assert code == tbr.EXIT_OK
    assert [a[0] for a in recorder.analyses] == ["robert", "amira"]
    idea = recorder.analyses[0][1]
    assert idea == {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    assert all(kw["mode"] == "bedrock" for _, _, kw in recorder.analyses)
    assert recorder.analyses[0][2]["config"].mode == "bedrock"
    assert [lvl for lvl, _ in recorder.explanations] == ["novice", "pro", "novice", "pro"]
    out = capsys.readouterr().out
    assert "mode effectif : bedrock" in out
    assert "analyze_portfolio, simulate_portfolio_change" in out
    assert "1. analysis : ok (acteur agent)" in out
    assert "ancrage 0.91" in out
    assert "traces/2026-11-14/run0001.json" in out
    assert "bucket_non_configure" in out
    assert_clean(out)


def test_effective_mode_not_bedrock_gives_nonzero(capsys):
    recorder = Recorder(result=fake_result(mode="offline", step_status="fallback", actor="code",
                                           fallback="BedrockAuthError: " + FAKE_KEY + " compte " + FAKE_ACCOUNT))
    code, _ = run(["--run", "--personas", "robert"], recorder)
    assert code == tbr.EXIT_RUN_FAILED
    out = capsys.readouterr().out
    assert "mode offline au lieu de bedrock" in out
    assert_clean(out)


def test_step_in_error_gives_nonzero(capsys):
    recorder = Recorder(explanation=lambda level: fake_explanation(level, guard_status="error"))
    code, _ = run(["--run", "--personas", "amira"], recorder)
    assert code == tbr.EXIT_RUN_FAILED
    assert "guardrail en erreur" in capsys.readouterr().out


def test_explanation_outside_bedrock_gives_nonzero(capsys):
    recorder = Recorder(explanation=lambda level: fake_explanation(level, origin="template"))
    code, _ = run(["--run", "--personas", "robert"], recorder)
    assert code == tbr.EXIT_RUN_FAILED
    assert "explication hors Bedrock" in capsys.readouterr().out


def test_pipeline_exception_is_masked(capsys):
    recorder = Recorder(error=RuntimeError("echec arn:aws:iam::" + FAKE_ACCOUNT + ":role/x " + FAKE_KEY))
    code, _ = run(["--run", "--personas", "robert"], recorder)
    assert code == tbr.EXIT_RUN_FAILED
    assert_clean(capsys.readouterr().out)


def test_save_local_writes_three_documents_per_persona(tmp_path, capsys, monkeypatch):
    import alphaforge.trace_store as ts

    monkeypatch.setattr(ts, "build_trace_document",
                        lambda result, explanation=None: {
                            "analysis": {"run_id": result["run_id"], "created_at": result["created_at"]},
                            **({"explanation": {"level": explanation["output"]["level"]}} if explanation else {})})
    code, _ = run(["--run", "--personas", "robert", "--save-local"], local_dir=tmp_path)
    assert code == tbr.EXIT_OK
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["run0001-explication-novice.json", "run0001-explication-pro.json", "run0001.json"]
    assert "Copie locale" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Tableau --check-requests
# ---------------------------------------------------------------------------

PROMPTS = [
    {"id": "A01", "text": "requete permise fictive", "expected": "allowed"},
    {"id": "D01", "text": "requete refusee fictive", "expected": "denied"},
    {"id": "D02", "text": "autre requete refusee", "expected": "denied"},
]


def test_check_requests_table_matches(capsys):
    seen = []

    def check(text, **kwargs):
        seen.append(kwargs["mode"])
        return {"action": "intervened" if "refusee" in text else "none"}
    code, _ = run(["--run", "--personas", "robert", "--check-requests"],
                  check_request_fn=check, prompts_loader=lambda: PROMPTS)
    assert code == tbr.EXIT_OK
    assert seen == ["bedrock"] * 3
    out = capsys.readouterr().out
    assert "Concordance : 3/3" in out
    assert "requete" not in out  # le texte des requêtes n'est jamais affiché


def test_check_requests_mismatch_and_not_run(capsys):
    actions = iter(["none", "none", "not_run"])
    code, _ = run(["--run", "--personas", "robert", "--check-requests"],
                  check_request_fn=lambda text, **k: {"action": next(actions)},
                  prompts_loader=lambda: PROMPTS)
    assert code == tbr.EXIT_REQUEST_MISMATCH
    out = capsys.readouterr().out
    assert "Concordance : 1/3" in out
    assert "non vérifiée" in out


def test_real_prompt_fixture_is_loadable():
    prompts = tbr.load_prompts()
    assert prompts and all({"id", "text", "expected"} <= set(p) for p in prompts)
    assert len(prompts) <= tbr.MAX_REQUEST_CHECKS


def test_script_source_has_no_hardcoded_ids():
    source = (ROOT / "scripts" / "try_bedrock_run.py").read_text(encoding="utf-8")
    assert not TWELVE_DIGITS.search(source)
    assert "AKIA" not in source and "ASIA" not in source
    assert "\u2014" not in source
    json.dumps(tbr.TRIAL_IDEA)
