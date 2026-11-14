"""Tests B7 : glossaire, limites et avertissements fixes. Aucun appel AWS ni modèle."""
import copy
import json
import re
import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge import explanation_validator  # noqa: E402
from alphaforge.explanation_brief import build_brief, load_glossary  # noqa: E402
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import render_markdown  # noqa: E402
from alphaforge.reference_texts import (  # noqa: E402
    REQUIRED_LIMIT_TOPICS, REQUIRED_WARNING_TOPICS, disclaimer_text, disclaimers, load_fixed_texts,
    load_limits, mandatory_limits, merge_mandatory_limits, threshold_assumption,
)
FIXTURES = Path(__file__).parent / "fixtures"
REFERENCE = ROOT / "src" / "alphaforge" / "reference"
LEVELS = ("novice", "pro")
def robert():
    return json.loads((FIXTURES / "analysis_result_robert_tsla.json").read_text(encoding="utf-8"))
def all_texts():
    texts = []
    for item in load_limits():
        texts += [item["text_novice"], item["text_pro"]]
    fixed = load_fixed_texts()
    for item in fixed["disclaimers"]:
        texts += [item["text_novice"], item["text_pro"]]
    texts += list(fixed["threshold_assumption"].values())
    for term in load_glossary():
        for level in LEVELS:
            texts += [term["term"], term[level]["definition"], term[level]["analogy"]]
    return texts
# ---------- limites ----------
def test_all_required_limit_topics_are_present():
    assert {i["topic"] for i in load_limits()} >= set(REQUIRED_LIMIT_TOPICS)
def test_limits_have_distinct_texts_per_level():
    for item in load_limits():
        assert item["text_novice"] != item["text_pro"]
        assert re.fullmatch(r"LM\d+", item["limit_id"])
def test_limit_content_covers_the_mandatory_subjects():
    by_topic = {i["topic"]: i for i in load_limits()}
    for level in LEVELS:
        field = "text_" + level
        assert "survivant" in by_topic["survivorship_bias"][field].lower() or "choisis" in by_topic["survivorship_bias"][field]
        assert "cinq ans" in by_topic["limited_history"][field]
        assert "dollars canadiens" in by_topic["dates_and_currencies"][field]
        assert "hypoth" in by_topic["simulation_assumptions"][field]
        assert "information manquante" in by_topic["data_quality_availability"][field]
@pytest.mark.parametrize("level", LEVELS)
def test_brief_always_contains_mandatory_limits_first(level):
    brief = build_brief(robert(), level)
    ids = [i["limit_id"] for i in brief["limits"]]
    assert ids[:5] == ["LM1", "LM2", "LM3", "LM4", "LM5"] and ids[5:] == ["L1"]
    assert brief["limits"][:5] == mandatory_limits(level)
def test_brief_limits_differ_by_level_but_ids_are_identical():
    novice, pro = build_brief(robert(), "novice")["limits"], build_brief(robert(), "pro")["limits"]
    assert [i["limit_id"] for i in novice] == [i["limit_id"] for i in pro]
    assert all(a["text"] != b["text"] for a, b in zip(novice[:5], pro[:5]))
def test_result_may_carry_mandatory_limits_with_same_text():
    result = robert()
    fixed = {i["limit_id"]: i for i in load_limits()}
    result["limits"].append(fixed["LM1"])
    assert [i["limit_id"] for i in build_brief(result, "novice")["limits"]].count("LM1") == 1
def test_conflicting_mandatory_limit_text_is_rejected():
    result = robert()
    result["limits"].append({"limit_id": "LM2", "text_novice": "autre", "text_pro": "autre"})
    with pytest.raises(ValueError, match="LM2"):
        build_brief(result, "novice")
def test_evidence_may_reference_a_catalog_limit():
    result = robert()
    result["evidence"]["E1"]["limit_ids"] = ["L1", "LM3"]
    assert build_brief(result, "pro")["evidence"][0]["limit_ids"] == ["L1", "LM3"]
def test_merge_keeps_order_and_adds_missing_limits():
    merged = merge_mandatory_limits([{"limit_id": "L9", "text": "neuf"}], "pro")
    assert [i["limit_id"] for i in merged] == ["LM1", "LM2", "LM3", "LM4", "LM5", "L9"]
# ---------- avertissements ----------
@pytest.mark.parametrize("level", LEVELS)
def test_all_four_warnings_exist_per_level(level):
    items = disclaimers(level)
    assert [i["topic"] for i in items] == list(REQUIRED_WARNING_TOPICS)
    assert disclaimer_text(level) == " ".join(i["text"] for i in items)
def test_warning_content():
    for level in LEVELS:
        text = disclaimer_text(level).lower()
        for expected in ("fictif", "éducatif" if level == "pro" else "apprendre",
                         "conseil financier personnalisé", "aucune transaction réelle"):
            assert expected in text, (level, expected)
def test_warnings_differ_by_level():
    assert disclaimer_text("novice") != disclaimer_text("pro")
def test_threshold_assumption_per_level():
    for level in LEVELS:
        assert "hypothèses de l'équipe" in threshold_assumption(level)
@pytest.mark.parametrize("level", LEVELS)
def test_rendering_shows_warnings_and_all_mandatory_limits(level):
    brief = build_brief(robert(), level)
    text = render_markdown(render_template(brief), brief)
    for item in disclaimers(level):
        assert item["text"] in text
    for item in mandatory_limits(level):
        assert f"**{item['limit_id']}** : {item['text']}" in text
def test_rendering_adds_mandatory_limits_to_an_old_brief():
    brief = json.loads((FIXTURES / "explanation_brief_robert_novice.json").read_text(encoding="utf-8"))
    brief["limits"] = [{"limit_id": "L1", "text": "Donnée d'essai."}]
    text = render_markdown(render_template(brief), brief)
    assert all(item["text"] in text for item in mandatory_limits("novice"))
    assert "**L1** : Donnée d'essai." in text
# ---------- qualité des textes ----------
def test_no_digit_in_reference_texts():
    for text in all_texts():
        assert not re.search(r"\d", text), text
def test_ascii_punctuation_only_in_reference_files():
    for name in ("glossary.json", "limits.json", "fixed_texts.json"):
        for char in (REFERENCE / name).read_text(encoding="utf-8"):
            assert ord(char) < 128 or char.isalpha(), (name, repr(char))
def test_limits_and_glossary_avoid_forbidden_terms():
    texts = [t for item in load_limits() for t in (item["text_novice"], item["text_pro"])]
    texts += [t for term in load_glossary() for lv in LEVELS for t in term[lv].values()]
    for text in texts:
        folded = explanation_validator._fold(text)
        for pattern in explanation_validator._FORBIDDEN:
            assert not pattern.search(folded), (text, pattern.pattern)
def test_glossary_has_both_levels_with_expected_shape():
    for term in load_glossary():
        assert term["novice"]["definition"] != term["pro"]["definition"]
        assert term["novice"]["analogy"].strip() and term["pro"]["analogy"] == ""
# ---------- chargement ----------
def test_invalid_files_raise(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_limits(bad)
    with pytest.raises(ValueError):
        load_fixed_texts(tmp_path / "absent.json")
def test_missing_required_topic_raises(tmp_path):
    data = json.loads((REFERENCE / "limits.json").read_text(encoding="utf-8"))
    data["limits"] = [i for i in data["limits"] if i["topic"] != "limited_history"]
    path = tmp_path / "limits.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="limited_history"):
        load_limits(path)
    fixed = json.loads((REFERENCE / "fixed_texts.json").read_text(encoding="utf-8"))
    fixed["disclaimers"] = fixed["disclaimers"][:3]
    path = tmp_path / "fixed.json"
    path.write_text(json.dumps(fixed), encoding="utf-8")
    with pytest.raises(ValueError, match="no_real_transactions"):
        load_fixed_texts(path)
def test_empty_text_and_duplicate_id_raise(tmp_path):
    data = json.loads((REFERENCE / "limits.json").read_text(encoding="utf-8"))
    empty = copy.deepcopy(data)
    empty["limits"][0]["text_pro"] = " "
    path = tmp_path / "a.json"
    path.write_text(json.dumps(empty), encoding="utf-8")
    with pytest.raises(ValueError):
        load_limits(path)
    dup = copy.deepcopy(data)
    dup["limits"][1]["limit_id"] = dup["limits"][0]["limit_id"]
    path = tmp_path / "b.json"
    path.write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(ValueError, match="double"):
        load_limits(path)
def test_unknown_level_raises():
    for func in (mandatory_limits, disclaimers, threshold_assumption, disclaimer_text):
        with pytest.raises(ValueError):
            func("expert")
# ---------- intégration (B8) ----------
@pytest.mark.parametrize("level", LEVELS)
def test_no_duplicate_warning_or_limit_in_rendered_text(level):
    brief = build_brief(robert(), level)
    text = render_markdown(render_template(brief), brief)
    for item in disclaimers(level):
        assert text.count(item["text"]) == 1
    for item in brief["limits"]:
        assert text.count(f"**{item['limit_id']}** :") == 1
def test_volatility_is_stated_as_one_indicator_among_others():
    texts = {i["limit_id"]: i for i in load_limits()}["LM2"]
    assert "indicateur de risque parmi d'autres" in texts["text_novice"]
    assert "indicateur de risque parmi d'autres" in texts["text_pro"]
