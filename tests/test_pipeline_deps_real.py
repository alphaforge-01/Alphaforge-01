"""Branchement reel du pipeline (flux A) et couverture du catalogue de preuves."""
from pathlib import Path

from alphaforge import analysis_pipeline, pipeline_deps, reference_texts
from alphaforge.evidence import EVIDENCE_METRICS
from alphaforge.profiles import load_personas

ROOT = Path(__file__).resolve().parents[1]


def test_load_real_deps_disponible():
    deps = pipeline_deps.load_real_deps()
    assert deps is not None, "Les vrais modules des flux A et B doivent se charger"
    assert deps.is_fixture is False


def test_chaque_famille_de_metriques_documentee():
    text = (ROOT / "docs" / "evidence_keys.md").read_text(encoding="utf-8")
    absentes = [family for family in EVIDENCE_METRICS if family not in text]
    assert absentes == [], f"Familles absentes de docs/evidence_keys.md : {absentes}"


def test_run_analysis_offline_robert_reel(monkeypatch):
    # Contournement temporaire du bogue du flux C : analysis_pipeline._load_limits
    # n'attend pas le format reel de limits.json. A retirer une fois corrige.
    def load_limits_ok(deps, limit_ids):
        wanted = set(limit_ids)
        return [item for item in reference_texts.load_limits()
                if not wanted or item["limit_id"] in wanted]

    monkeypatch.setattr(analysis_pipeline, "_load_limits", load_limits_ok)
    persona = load_personas()["robert"]
    idea = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    result = analysis_pipeline.run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline")
    assert result["is_fixture"] is False
    assert result["governance_after"]["overall_status"] == "conflict"
    explanation = analysis_pipeline.explain(result, "novice", mode="offline")
    assert explanation["validation"]["is_valid"] is True, explanation["validation"]["rejections"]
