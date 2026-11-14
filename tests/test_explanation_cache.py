"""Tests du cache des explications. Aucun reseau : fichiers sous tmp_path seulement."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.explanation_cache import ExplanationCache

OUTPUT = {"summary": "Texte [G1].", "factors": [{"check_id": "G1", "text": "x"}], "attempt": 1}


def test_make_key_joins_parts_in_order():
    key = ExplanationCache.make_key("b1", "novice", "m1", "explainer_v1")
    assert key == "b1|novice|m1|explainer_v1"
    assert key != ExplanationCache.make_key("b1", "pro", "m1", "explainer_v1")
    assert key != ExplanationCache.make_key("b2", "novice", "m1", "explainer_v1")


def test_get_put_and_missing_key():
    cache = ExplanationCache()
    assert cache.get("absente") is None and len(cache) == 0
    cache.put("k", OUTPUT)
    assert cache.get("k") == OUTPUT and len(cache) == 1
    cache.put("k", {**OUTPUT, "attempt": 2})
    assert len(cache) == 1 and cache.get("k")["attempt"] == 2


def test_deep_copy_on_get_and_put():
    cache = ExplanationCache()
    source = json.loads(json.dumps(OUTPUT))
    cache.put("k", source)
    source["factors"][0]["text"] = "mute apres put"
    assert cache.get("k")["factors"][0]["text"] == "x"
    read = cache.get("k")
    read["factors"].append({"check_id": "G9", "text": "ajout"})
    read["summary"] = "mute"
    assert cache.get("k") == OUTPUT


def test_file_persistence_reloaded_in_new_instance(tmp_path):
    path = tmp_path / "sous" / "cache.json"
    cache = ExplanationCache(path)
    cache.put("k", OUTPUT)
    assert path.is_file()
    again = ExplanationCache(path)
    assert len(again) == 1 and again.get("k") == OUTPUT


def test_corrupted_file_is_ignored(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{ pas du json", encoding="utf-8")
    cache = ExplanationCache(path)
    assert len(cache) == 0 and cache.get("k") is None
    cache.put("k", OUTPUT)
    assert ExplanationCache(path).get("k") == OUTPUT


def test_missing_file_gives_empty_cache(tmp_path):
    assert len(ExplanationCache(tmp_path / "nope.json")) == 0


def test_cache_stores_only_what_is_put(tmp_path):
    path = tmp_path / "cache.json"
    cache = ExplanationCache(path)
    cache.put("k", OUTPUT)
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": OUTPUT}
    assert "AKIA" not in path.read_text(encoding="utf-8")
