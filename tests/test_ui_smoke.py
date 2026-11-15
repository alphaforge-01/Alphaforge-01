"""Test de fumée de l'interface Streamlit (PR-0 de la refonte v2).

Joue l'application réelle avec `streamlit.testing.v1.AppTest`, sans navigateur, en
mode "fixture" : les chiffres viennent de tests/fixtures/, aucun outil de marché et
aucun agent ne tourne. Aucun appel AWS n'est possible : `boto3.client` et
`boto3.Session` sont remplacés par des fonctions qui échouent, donc un appel
involontaire fait échouer le test au lieu de joindre le réseau.

Le test ne vérifie pas de texte ni de mise en page : seulement que les pages se
construisent sans exception. Il sert de filet pour les PR suivantes de la refonte.
"""
from __future__ import annotations

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
SIMULATION_PAGE = "views/simulation_page.py"
TIMEOUT = 120


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    """Mode fixture, interface v2 éteinte, aucune identité AWS, aucun client AWS."""
    monkeypatch.setenv("ALPHAFORGE_MODE", "fixture")
    monkeypatch.delenv("ALPHAFORGE_UI", raising=False)
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Appel AWS interdit dans le test de fumée.")

    boto3 = pytest.importorskip("boto3")
    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(boto3, "Session", forbidden)


def _no_exception(at) -> None:
    assert not at.exception, [e.value for e in at.exception]


@pytest.fixture()
def home():
    at = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()
    _no_exception(at)
    return at


@pytest.fixture()
def simulation(home):
    home.button(key="choose_profile_robert").click().run()
    home.switch_page(SIMULATION_PAGE).run()
    _no_exception(home)
    return home


def test_home_page_builds(home):
    assert home.session_state["mode"] == "fixture"
    assert any(b.key == "choose_profile_robert" for b in home.button)


def test_every_page_builds_in_fixture_mode(home):
    pages = ("views/home_page.py", SIMULATION_PAGE, "views/custom_profile_page.py",
             "views/guardrail_page.py", "views/sources_page.py")
    for page in pages:
        home.switch_page(page).run()
        _no_exception(home)


def test_simulation_page_has_chat_input(simulation):
    assert len(simulation.chat_input) == 1


def test_fixture_idea_runs_without_exception(simulation):
    before = len(simulation.chat_message)
    simulation.chat_input[0].set_value("25 % dans TSLA").run()
    _no_exception(simulation)
    assert len(simulation.chat_message) > before
    assert not simulation.error, [e.value for e in simulation.error]


def test_refused_request_runs_without_exception(simulation):
    before = len(simulation.chat_message)
    simulation.chat_input[0].set_value("conseille-moi un titre").run()
    _no_exception(simulation)
    assert len(simulation.chat_message) > before
