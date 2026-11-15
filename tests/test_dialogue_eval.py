"""Tests du jeu de phrases de dialogue et de sa mesure (`dialogue_eval`, `scripts/measure_dialogue.py`)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from alphaforge import dialogue_eval as de
from alphaforge.data_loading import load_universe
from alphaforge.profiles import load_personas

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "measure_dialogue.py"
spec = importlib.util.spec_from_file_location("measure_dialogue", SCRIPT)
measure = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = measure
spec.loader.exec_module(measure)

STATUSES = {"idea", "confirm", "clarify", "refused", "answer"}
ANSWER_KINDS = {"greeting", "portfolio", "definition", "out_of_scope", "profile", "xray", "explanation"}


@pytest.fixture(scope="module")
def phrases():
    return de.load_phrases()


@pytest.fixture(scope="module")
def universe():
    return load_universe().to_dict("records")


@pytest.fixture(scope="module")
def report(phrases, universe):
    held = [p["ticker"] for p in load_personas()[phrases["persona"]]["portfolio"]["positions"]]
    return de.evaluate(de.rules_understand, universe, held, phrases)


def test_fixture_is_well_formed(phrases, universe):
    tickers = {asset["ticker"] for asset in universe}
    assert len(phrases["phrases"]) == 60
    for phrase in phrases["phrases"]:
        assert phrase["category"] in phrases["categories"]
        expected = phrase["expected"]
        assert set(expected) <= set(de.EXPECTED_FIELDS)
        assert expected["status"] in STATUSES
        if "answer_kind" in expected:
            assert expected["answer_kind"] in ANSWER_KINDS
        if expected.get("ticker"):
            assert expected["ticker"] in tickers, "les phrases ne visent que des actifs de l'univers"
        if expected.get("target_weight") is not None:
            assert 0 < expected["target_weight"] <= 1


def test_fixture_has_no_em_dash():
    assert chr(0x2014) not in de.PHRASES_PATH.read_text(encoding="utf-8")


def test_duplicate_ids_are_refused(tmp_path, phrases):
    data = dict(phrases)
    data["phrases"] = phrases["phrases"] + [phrases["phrases"][0]]
    path = tmp_path / "phrases.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        de.load_phrases(path)


@pytest.mark.parametrize("expected,observed,differences", [
    ({"status": "idea", "ticker": "TSLA", "target_weight": 0.25},
     {"status": "idea", "ticker": "TSLA", "target_weight": 0.25000000001}, []),
    ({"status": "idea", "ticker": "TSLA"}, {"status": "confirm", "ticker": "TSLA"}, ["status"]),
    ({"status": "answer", "term_id": None}, {"status": "answer", "term_id": "T1"}, ["term_id"]),
    ({"status": "clarify"}, {"status": "clarify", "ticker": "SPY", "reason": "x"}, []),
])
def test_compare_checks_only_expected_fields(expected, observed, differences):
    assert de.compare(expected, observed) == differences


def test_safety_categories_stay_perfect(report):
    """Garde-fou de non-régression : refus, idées explicites et pièges toujours à 100 %."""
    for category in measure.SAFETY_CATEGORIES:
        stats = report["by_category"][category]
        assert stats["ok"] == stats["total"], [row["id"] for row in report["rows"]
                                              if row["category"] == category and not row["ok"]]


def test_rules_never_turn_a_refusal_into_something_else(report):
    for row in report["rows"]:
        if row["expected"]["status"] == "refused":
            assert row["observed"]["status"] == "refused", row["id"]


def test_rules_never_guess_an_asset_or_weight(report):
    """Aucune phrase dont l'idéal est une question ou une confirmation ne devient une analyse directe."""
    for row in report["rows"]:
        if row["expected"]["status"] in ("clarify", "confirm"):
            assert row["observed"]["status"] != "idea", row["id"]


def test_script_writes_deterministic_reports(tmp_path):
    assert measure.main(["--out-dir", str(tmp_path)]) == 0
    first = (tmp_path / "dialogue_eval.md").read_bytes()
    assert measure.main(["--out-dir", str(tmp_path)]) == 0
    assert (tmp_path / "dialogue_eval.md").read_bytes() == first
    text = first.decode("utf-8")
    assert "Simulation éducative" in text and "phrases sur 60" in text
    assert chr(0x2014) not in text
    payload = json.loads((tmp_path / "dialogue_eval.json").read_text(encoding="utf-8"))
    assert payload["total"] == 60
