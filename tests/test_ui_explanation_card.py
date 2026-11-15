"""Carte d'explication de l'interface v2 (PR-4) : app/components/explanation_card.py.

Explications réelles du pipeline en mode hors ligne (gabarit, aucun modèle, aucun appel AWS).
Le rendu est joué avec `AppTest`, sans navigateur. Les cas de l'origine "modèle" et du repli
sont construits à partir de la même explication, sans rien inventer d'autre que l'étiquette testée.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
for path in (APP_DIR, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import ui_labels as labels  # noqa: E402
from alphaforge.explanation_rendering import RenderedSections  # noqa: E402
from alphaforge.reference_texts import disclaimers, mandatory_limits  # noqa: E402
from components import explanation_card as card  # noqa: E402

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

SCRIPT = """
import copy, sys
sys.path.insert(0, {app!r}); sys.path.insert(0, {src!r})
from alphaforge.analysis_pipeline import run_analysis, explain
from alphaforge.bedrock_client import BedrockConfig
from alphaforge.profiles import load_personas
from components.explanation_card import render_explanation_card

persona = load_personas()["robert"]
idea = {{"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}}
result = run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline", config=BedrockConfig())
explanation = copy.deepcopy(explain(result, {level!r}, mode="offline", config=BedrockConfig()))
variant = {variant!r}
if variant == "llm":
    explanation["output"]["origin"] = "llm"
elif variant == "fallback":
    for step in explanation["trace"]:
        if step["name"] == "explanation":
            step["status"] = "fallback"
            step["details"] = {{"fallback_reason": "validation_failed"}}
elif variant == "no_brief":
    explanation.pop("brief")
elif variant == "no_brief_no_markdown":
    explanation.pop("brief"); explanation["rendered_markdown"] = ""
elif variant == "broken_brief":
    explanation["brief"] = {{"level": {level!r}}}
elif variant == "none":
    explanation = None
render_explanation_card(explanation)
"""


def play(level="novice", variant="normal"):
    script = SCRIPT.format(app=str(APP_DIR), src=str(ROOT / "src"), level=level, variant=variant)
    at = AppTest.from_string(script, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def all_text(at):
    return [e.value for e in at.markdown] + [e.value for e in at.caption]


def occurrences(at, needle):
    return sum(needle in value for value in all_text(at))


# --- Contenu des sections ------------------------------------------------------

def test_novice_card_shows_every_section():
    at = play("novice")
    text = "\n".join(all_text(at))
    for title in (labels.EXPL_TITLE, labels.EXPL_SUMMARY_TITLE, labels.EXPL_FACTORS_TITLE,
                  labels.EXPL_COUNTERFACTUAL_TITLE, labels.EXPL_LIMITS_TITLE, labels.EXPL_WARNINGS_TITLE):
        assert title in text
    expanders = [e.label for e in at.expander]
    assert labels.EXPL_PROFILE_TITLE in expanders
    assert labels.EXPL_CHECKS_TITLE in expanders
    assert any(label.startswith("Preuves citées") for label in expanders)
    assert "le plus grand poids testé conforme à cette règle est" in text   # contrefactuel calculé


def test_level_badge_follows_the_explanation_level():
    assert ":blue-badge[Niveau novice]" in all_text(play("novice"))
    assert ":blue-badge[Niveau pro]" in all_text(play("pro"))


def test_novice_and_pro_check_tables_differ_but_keep_the_same_checks():
    novice = play("novice").dataframe[0].value
    pro = play("pro").dataframe[0].value
    assert list(novice.columns) == list(labels.EXPL_CHECK_COLUMNS["novice"])
    assert list(pro.columns) == list(labels.EXPL_CHECK_COLUMNS["pro"])
    assert len(novice) == len(pro) > 0
    assert list(novice["Statut"]) == list(pro["Statut"])
    assert list(novice["Mesure"]) == list(pro["Valeur"])


def test_pro_card_opens_the_check_details_novice_does_not():
    novice, pro = play("novice"), play("pro")
    assert next(e for e in novice.expander if e.label == labels.EXPL_CHECKS_TITLE).proto.expanded is False
    assert next(e for e in pro.expander if e.label == labels.EXPL_CHECKS_TITLE).proto.expanded is True


def test_factor_cards_show_the_governance_status():
    at = play("novice")
    badges = [v for v in all_text(at) if "-badge[" in v]
    assert any("Conflit" in b for b in badges)
    assert any("Tension" in b for b in badges)


# --- Origine du texte : modèle ou gabarit de secours -----------------------------

def test_template_origin_badge():
    values = all_text(play("novice", "normal"))
    assert any("Texte standard" in v for v in values)
    assert not any("Rédigé par l'agent explicateur" in v for v in values)


def test_model_origin_badge():
    values = all_text(play("novice", "llm"))
    assert any("Rédigé par l'agent explicateur" in v for v in values)
    assert not any("Texte standard" in v for v in values)


def test_fallback_note_is_shown_in_the_card():
    at = play("novice", "fallback")
    assert any("texte du gabarit" in info.value for info in at.info)


# --- Avertissements sans répétition -----------------------------------------------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_each_fixed_warning_and_limit_is_shown_exactly_once(level):
    at = play(level)
    for item in disclaimers(level):
        assert occurrences(at, item["text"]) == 1, item["text"]
    for item in mandatory_limits(level):
        assert occurrences(at, item["text"]) == 1, item["text"]


def test_threshold_notice_is_shown_once():
    at = play("novice")
    assert occurrences(at, "Les seuils sont des hypothèses de l'équipe") == 1


def _sections(**overrides):
    base = dict(level="novice", origin="template", disclaimers=(), idea_line=None, profile_context=None,
                summary="", factors=(), counterfactual="", counterfactual_items=(), variants="",
                check_rows=(), check_notes=(), threshold_notice=None, limits_context="", limits=(),
                evidence=(), glossary=())
    base.update(overrides)
    return RenderedSections(**base)


def test_warning_blocks_drop_normalized_duplicates():
    sections = _sections(
        disclaimers=(("W1", "Tout est fictif."),),
        threshold_notice="Les seuils sont des hypothèses.",
        limits=(("L1", "tout  est   fictif"), ("L2", "Limite distincte."), ("L3", "Limite distincte")),
        limits_context="Les seuils sont des hypothèses",
    )
    blocks = card.warning_blocks(sections)
    assert blocks.disclaimers == ("Tout est fictif.",)
    assert blocks.threshold_notice == "Les seuils sont des hypothèses."
    assert blocks.limits == (("L2", "Limite distincte."),)
    assert blocks.limits_context == ""


def test_warning_blocks_keep_distinct_texts_in_order():
    sections = _sections(disclaimers=(("W1", "A."), ("W2", "B.")), limits=(("L1", "C."),),
                         limits_context="D.")
    blocks = card.warning_blocks(sections)
    assert blocks.disclaimers == ("A.", "B.") and blocks.limits == (("L1", "C."),)
    assert blocks.limits_context == "D."


def test_warning_blocks_ignore_empty_texts():
    blocks = card.warning_blocks(_sections(disclaimers=(("W1", "  "),), threshold_notice="", limits_context=""))
    assert blocks.disclaimers == () and blocks.threshold_notice is None and blocks.limits_context == ""


# --- Données manquantes ------------------------------------------------------------

def test_without_brief_the_card_shows_the_validated_markdown():
    at = play("novice", "no_brief")
    values = all_text(at)
    assert labels.EXPL_PLAIN_NOTE in values
    assert not at.dataframe
    assert not [e for e in at.expander if e.label == labels.EXPL_CHECKS_TITLE]
    assert any("Résumé" in v for v in values)       # le Markdown déjà rendu reste affiché
    assert not any(v.startswith("# ") for v in values)   # sans son titre H1


def test_broken_brief_falls_back_to_the_markdown_without_exception():
    at = play("pro", "broken_brief")
    assert labels.EXPL_PLAIN_NOTE in all_text(at)


def test_no_brief_and_no_markdown_says_not_available():
    assert labels.EXPL_NOT_AVAILABLE in all_text(play("novice", "no_brief_no_markdown"))


def test_no_explanation_says_not_available():
    assert labels.EXPL_NOT_AVAILABLE in all_text(play("novice", "none"))


def test_build_sections_returns_none_without_usable_input():
    assert card.build_sections({}) is None
    assert card.build_sections({"output": {}, "brief": "x"}) is None
    assert card.build_sections({"output": {"level": "novice"}, "brief": {"checks": [{"x": 1}]}}) is None


def test_unknown_reference_already_in_the_markdown_keeps_the_sections():
    output = {"level": "novice", "summary": "Mesure [E9].", "factors": [], "origin": "template"}
    brief = {"level": "novice", "evidence": [], "checks": [], "glossary": [], "limits": []}
    flagged = "# x\n\n## Résumé\n\nMesure [référence inconnue : E9].\n"
    assert card.build_sections({"output": output, "brief": brief, "rendered_markdown": flagged}) is not None
    assert card.build_sections({"output": output, "brief": brief, "rendered_markdown": "# x\n"}) is None


def test_check_table_has_no_zero_for_missing_values():
    from alphaforge.explanation_rendering import CheckRow

    row = CheckRow("G1", "Concentration", "missing_info", "information manquante", "R1 (t, max)",
                   "information manquante", "non défini", "non défini", "non défini", ())
    table = card.check_table(_sections(check_rows=(row,)))
    assert isinstance(table, pd.DataFrame)
    assert list(table.iloc[0]) == ["Concentration", "information manquante", "information manquante",
                                   "non défini", "non défini"]


def test_card_module_is_not_wired_to_state_or_data():
    source = (APP_DIR / "components" / "explanation_card.py").read_text(encoding="utf-8")
    for forbidden in ("session", "data_source", "boto3", "requests"):
        assert forbidden not in source
