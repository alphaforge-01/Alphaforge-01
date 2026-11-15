"""Tests du script de diagnostic de l'ancrage (scripts/diagnose_grounding.py).

Aucun appel AWS : le client Bedrock est remplacé par un faux client, et l'explicateur
par une fonction qui rend le gabarit du code.
"""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import diagnose_grounding as dg  # noqa: E402
from alphaforge import explainer_agent  # noqa: E402
from alphaforge.bedrock_client import BedrockError  # noqa: E402
from alphaforge.tool_specs import ExplainerFailure  # noqa: E402

# Lue une seule fois, avant tout remplacement de `from_env` par les tests.
BASE_CONFIG = dg.BedrockConfig.from_env({})


class FakeClient:
    """Faux client : enregistre les appels, rend une réponse fixe."""
    calls = []
    action = "none"

    def __init__(self, config):
        self.config = config

    def check_output_grounding(self, source, query, answer):
        FakeClient.calls.append((source, query, answer))
        return {"check": "output_grounding", "action": FakeClient.action, "denied_topics": [],
                "grounding_score": 0.5, "relevance_score": 0.9, "mode": "detect"}


class ForbiddenClient:
    def __init__(self, config):
        raise AssertionError("aucun client Bedrock ne doit être créé dans ce mode")


class FailingClient(FakeClient):
    def check_output_grounding(self, source, query, answer):
        raise BedrockError("Limitation du débit (ThrottlingException).")


def _config(guardrail=True, explainer=None):
    config = BASE_CONFIG
    if guardrail:
        config = replace(config, guardrail_id="garde-fou-fictif", guardrail_version="1")
    if explainer:
        config = replace(config, explainer_model_id=explainer)
    return config


@pytest.fixture
def fake_bedrock(monkeypatch):
    FakeClient.calls = []
    FakeClient.action = "none"
    monkeypatch.setattr(dg, "BedrockClient", FakeClient)

    def use(config):
        monkeypatch.setattr(dg.BedrockConfig, "from_env", classmethod(lambda cls, env=None: config))
    return use


def test_fold_removes_accents_and_case():
    assert dg.fold("Été CONFORME") == "ete conforme"


def test_falsify_turns_flagged_rules_compliant():
    text = "La règle est en conflit. Une autre est en tension. Conflit d'ensemble. Information manquante."
    assert dg.falsify(text) == "La règle est conforme. Une autre est conforme. conforme d'ensemble. Information manquante."
    assert dg.falsify("Le seuil d'attention est atteint.") == "Le seuil d'attention est atteint."


def test_lexical_report_flags_missing_statuses_and_numbers():
    report = dg.lexical_report("La règle est en conflit, mesure 25 %.", "Statut conflict, valeur 0.25")
    assert report["statuses_missing"] == ["conflit"]
    assert report["numbers_missing"] == ["25 %"]
    complete = dg.lexical_report("La règle est en conflit, mesure 25 %.", "La règle est en conflit, mesure 25 %.")
    assert complete["statuses_missing"] == [] and complete["numbers_missing"] == []


def test_query_matches_pipeline_literal():
    pipeline = (ROOT / "src" / "alphaforge" / "analysis_pipeline.py").read_text(encoding="utf-8")
    assert f'"{dg.QUERY}"' in pipeline


@pytest.mark.parametrize("argv", [
    ["--personas", "robert,amira,mateo,custom"],
    ["--personas", "inconnu"],
    ["--personas", " , "],
    ["--explainer"],
])
def test_configuration_errors_exit_2_without_client(monkeypatch, argv):
    monkeypatch.setattr(dg, "BedrockClient", ForbiddenClient)
    assert dg.main(argv) == dg.EXIT_CONFIG_ERROR


def test_apply_without_guardrail_is_refused(monkeypatch, fake_bedrock):
    monkeypatch.setattr(dg, "BedrockClient", ForbiddenClient)
    fake_bedrock(_config(guardrail=False))
    assert dg.main(["--apply", "--personas", "robert"]) == dg.EXIT_CONFIG_ERROR


def test_apply_explainer_without_model_is_refused(monkeypatch, fake_bedrock):
    monkeypatch.setattr(dg, "BedrockClient", ForbiddenClient)
    fake_bedrock(_config())
    assert dg.main(["--apply", "--explainer", "--personas", "robert"]) == dg.EXIT_CONFIG_ERROR


def test_offline_run_creates_no_client(monkeypatch, capsys):
    monkeypatch.setattr(dg, "BedrockClient", ForbiddenClient)
    assert dg.main(["--personas", "robert,robert"]) == dg.EXIT_OK
    out = capsys.readouterr().out
    assert out.count("== robert | niveau novice ==") == 1 and "robert | niveau pro" in out
    assert "source json" in out and "source phrases" in out
    assert "ancrage" not in out and "témoin" not in out


def test_apply_compares_both_sources_and_control(fake_bedrock, capsys):
    fake_bedrock(_config())
    assert dg.main(["--apply", "--personas", "robert"]) == dg.EXIT_OK
    # 2 niveaux x (texte du gabarit + témoin) x 2 sources
    assert len(FakeClient.calls) == 8
    assert all(query == dg.QUERY for _, query, _ in FakeClient.calls)
    sources = {source for source, _, _ in FakeClient.calls}
    assert any(source.startswith("{") for source in sources)
    assert any(not source.startswith("{") and "Contrôle " in source for source in sources)
    out = capsys.readouterr().out
    assert "gabarit faussé (témoin)" in out and "ancrage 0.50" in out


def test_apply_reports_not_run(fake_bedrock, capsys):
    FakeClient.action = "not_run"
    fake_bedrock(_config())
    assert dg.main(["--apply", "--personas", "robert"]) == dg.EXIT_OK
    assert "non exécuté" in capsys.readouterr().out


def test_bedrock_error_stops_with_exit_1(monkeypatch, fake_bedrock, capsys):
    monkeypatch.setattr(dg, "BedrockClient", FailingClient)
    fake_bedrock(_config())
    assert dg.main(["--apply", "--personas", "robert"]) == dg.EXIT_BEDROCK_ERROR
    assert "Erreur Bedrock" in capsys.readouterr().out


def test_explainer_text_and_its_control_are_measured(monkeypatch, fake_bedrock, capsys):
    def fake_explain(client, model_id, brief, validate):
        from alphaforge.pipeline_deps import resolve_deps
        return resolve_deps().render_template(brief)
    monkeypatch.setattr(explainer_agent, "explain_with_llm", fake_explain)
    fake_bedrock(_config(explainer="modele-fictif"))
    assert dg.main(["--apply", "--explainer", "--personas", "robert"]) == dg.EXIT_OK
    # 2 niveaux x (gabarit, témoin, explicateur, témoin) x 2 sources
    assert len(FakeClient.calls) == 16
    out = capsys.readouterr().out
    assert "texte explicateur (" in out and "explicateur faussé (témoin)" in out


def test_explainer_failure_hides_model_excerpts(monkeypatch, fake_bedrock, capsys):
    def failing_explain(client, model_id, brief, validate):
        raise ExplainerFailure("extrait du texte du modèle")
    monkeypatch.setattr(explainer_agent, "explain_with_llm", failing_explain)
    fake_bedrock(_config(explainer="modele-fictif"))
    assert dg.main(["--apply", "--explainer", "--personas", "robert"]) == dg.EXIT_OK
    out = capsys.readouterr().out
    assert "explicateur indisponible : ExplainerFailure" in out
    assert "extrait du texte" not in out


@pytest.mark.parametrize("too_long", ["source", "answer"])
def test_too_long_texts_are_not_sent(too_long):
    FakeClient.calls = []
    client = FakeClient(None)
    source = "x" * (dg.GROUNDING_SOURCE_MAX_CHARS + 1) if too_long == "source" else "x"
    answer = "x" * (dg.GROUNDING_ANSWER_MAX_CHARS + 1) if too_long == "answer" else "x"
    assert dg.grounding_scores(client, source, answer) == "trop long"
    assert FakeClient.calls == []
