"""Onglet Trace des réponses : absent par défaut, présent avec l'interrupteur de démo (règle 8)."""
from __future__ import annotations

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def _reply_tabs(show_trace: bool):
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.button(key="choose_profile_robert").click().run()
    at.run()
    at.button(key="idea_preset_TSLA_25").click().run()
    for toggle in at.toggle:
        if toggle.key and toggle.key.startswith("details_"):
            toggle.set_value(True)
    at.run()
    if show_trace:
        at.toggle(key="show_trace").set_value(True).run()
    assert not at.exception
    return [tab.label for tab in at.tabs]


def test_trace_tab_hidden_by_default():
    assert "Trace" not in _reply_tabs(show_trace=False)


def test_trace_tab_shown_with_demo_toggle():
    labels = _reply_tabs(show_trace=True)
    assert "Trace" in labels
    assert "Explication complète" in labels
