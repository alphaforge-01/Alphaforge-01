"""Tests B : liens entre les règles R5 et R6 et les preuves par classe d'actifs, avec les vrais outils.

Données réelles de `data/raw/`, mode hors ligne, aucun appel AWS.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# ---------- preuves R5 et R6 avec les vrais outils (flux A) ----------

def test_real_pipeline_links_asset_class_rules_to_class_evidence():
    from alphaforge.analysis_pipeline import run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.profiles import load_personas
    persona = load_personas()["amira"]
    idea = {"ticker": "BTC-USD", "target_weight": 0.2, "funding_source": "pro_rata", "funding_ticker": None}
    result = run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline", config=BedrockConfig())
    assert result["is_fixture"] is False
    checks = {c["rule_id"]: c for c in result["governance_after"]["checks"]}
    for rule_id, asset_class in (("R5", "crypto"), ("R6", "equity")):
        ids = checks[rule_id]["evidence_ids"]
        assert ids, rule_id
        for evidence_id in ids:
            entry = result["evidence"][evidence_id]
            assert entry["metric"] == f"weight_by_asset_class.{asset_class}"
            assert entry["subject"] == "portfolio_after"
            assert entry["display_value"] and entry["value"] == checks[rule_id]["value"]


def test_real_pipeline_absent_asset_class_has_no_evidence_and_is_not_invented():
    from alphaforge.analysis_pipeline import run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.profiles import load_personas
    persona = load_personas()["robert"]       # aucune crypto, avant comme après un ajout de TSLA
    idea = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    result = run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline", config=BedrockConfig())
    r5 = next(c for c in result["governance_after"]["checks"] if c["rule_id"] == "R5")
    assert r5["status"] == "compliant" and r5["value"] == 0.0 and r5["evidence_ids"] == []
    assert not any(e["metric"] == "weight_by_asset_class.crypto" for e in result["evidence"].values())
