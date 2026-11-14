"""Tests B4 : dossier d'explication. Chiffres inventés, aucun appel AWS ni modèle."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge import explanation_brief  # noqa: E402
from alphaforge.contracts import ExplanationBrief, RuleCheck, check_keys  # noqa: E402
from alphaforge.explanation_brief import (  # noqa: E402
    MAX_CHARS_PER_SLOT, build_brief, load_glossary, rank_checks,
)
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import render_markdown  # noqa: E402
from alphaforge.governance import evaluate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
REF = re.compile(r"\[([EGT]\d+)\]")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def robert():
    return load("analysis_result_robert_tsla.json")


def amira():
    return load("analysis_result_amira_tsla.json")


def make_check(check_id, status, margin=None, rule_type="max_portfolio_volatility", evidence_ids=None):
    return {
        "check_id": check_id, "rule_id": "R" + check_id[1:], "rule_type": rule_type,
        "label_fr": "Règle d'essai", "status": status, "value": 0.2, "warn_threshold": 0.1,
        "limit_threshold": 0.3, "margin": margin, "unit": "pct", "evidence_ids": evidence_ids or [],
        "counterfactual": None, "missing_reason": None,
    }


def entry(evidence_id, metric="volatility_ann", subject="portfolio_after", limit_ids=("L1",)):
    return {
        "evidence_id": evidence_id, "evidence_key": f"{metric}:{subject}", "tool_name": "analyze_portfolio",
        "metric": metric, "subject": subject, "label_fr": "Preuve d'essai", "value": 0.2, "unit": "pct",
        "display_value": "20 %", "qualifier": None, "period_start": "2021-11-12",
        "period_end": "2026-11-12", "as_of": "2026-11-12", "currency": "CAD", "source_ids": ["prices_daily.csv"],
        "transformation": "Chiffres fictifs pour tests uniquement", "n_observations": 1000,
        "limit_ids": list(limit_ids),
    }


# ---------- contrat ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_brief_respects_contract(level):
    brief = build_brief(robert(), level)
    assert check_keys(brief, ExplanationBrief) == []
    assert set(brief) == set(ExplanationBrief.__annotations__)
    assert brief["level"] == level and brief["run_id"] == robert()["run_id"]
    assert brief["max_chars_per_slot"] == MAX_CHARS_PER_SLOT == 400
    for check in brief["checks"]:
        assert check_keys(check, RuleCheck) == []
    assert all(set(f) == {"rank", "check_id", "status", "evidence_ids"} for f in brief["ranked_factors"])
    assert all(set(v) == {"variant_id", "reason_code", "overall_status", "evidence_ids"}
               for v in brief["variants"])
    assert all(set(g) == {"term_id", "term", "definition", "analogy"} for g in brief["glossary"])
    assert all(set(item) == {"limit_id", "text"} for item in brief["limits"])


def test_brief_content_comes_from_result():
    result = robert()
    brief = build_brief(result, "pro")
    assert brief["profile_rules"] == result["profile"]["rules"]
    assert brief["idea"] == result["idea"]
    assert brief["checks"] == result["governance_after"]["checks"]   # statuts, marges et valeurs intacts


def test_invalid_level_and_incomplete_result_raise():
    with pytest.raises(ValueError):
        build_brief(robert(), "expert")
    result = robert()
    del result["governance_after"]
    with pytest.raises(ValueError):
        build_brief(result, "novice")
    with pytest.raises(ValueError):
        build_brief({}, "novice")


def test_profile_and_governance_mismatch_raises():
    result = robert()
    result["governance_after"]["profile_id"] = "amira"
    with pytest.raises(ValueError):
        build_brief(result, "novice")


# ---------- classement des facteurs ----------

def test_ranking_by_severity_then_margin():
    checks = [
        make_check("G1", "tension", margin=0.06),
        make_check("G2", "conflict", margin=-0.01),
        make_check("G3", "tension", margin=0.02),
        make_check("G4", "conflict", margin=-0.05),
        make_check("G5", "missing_info", margin=None),
        make_check("G6", "compliant", margin=0.3),
    ]
    ranked = rank_checks(checks)
    assert [f["check_id"] for f in ranked] == ["G4", "G2", "G3", "G1", "G5"]
    assert [f["rank"] for f in ranked] == [1, 2, 3, 4, 5]
    assert "G6" not in [f["check_id"] for f in ranked]


def test_ranking_missing_margin_last_within_status_and_natural_tiebreak():
    checks = [make_check("G10", "tension", 0.1), make_check("G2", "tension", 0.1),
              make_check("G3", "tension", None), make_check("G1", "tension", 0.05)]
    assert [f["check_id"] for f in rank_checks(checks)] == ["G1", "G2", "G10", "G3"]


def test_missing_info_ranks_below_tension_and_above_nothing():
    checks = [make_check("G1", "missing_info"), make_check("G2", "tension", 0.2)]
    assert [f["check_id"] for f in rank_checks(checks)] == ["G2", "G1"]


def test_ranking_is_independent_of_input_order():
    checks = [make_check("G1", "tension", 0.06), make_check("G2", "conflict", -0.01),
              make_check("G3", "tension", 0.02)]
    expected = [f["check_id"] for f in rank_checks(checks)]
    assert [f["check_id"] for f in rank_checks(list(reversed(checks)))] == expected


def test_robert_ranked_factors():
    brief = build_brief(robert(), "novice")
    assert [(f["check_id"], f["status"]) for f in brief["ranked_factors"]] == [
        ("G1", "conflict"), ("G2", "tension"), ("G3", "tension")]
    assert [f["evidence_ids"] for f in brief["ranked_factors"]] == [["E1"], ["E2"], ["E3"]]


def test_all_compliant_has_no_factor():
    brief = build_brief(amira(), "pro")
    assert brief["ranked_factors"] == []
    assert [c["status"] for c in brief["checks"]] == ["compliant"]


# ---------- preuves ----------

def test_checks_are_linked_to_registry_evidence():
    brief = build_brief(robert(), "novice")
    registry = robert()["evidence"]
    by_check = {c["check_id"]: c["evidence_ids"] for c in brief["checks"]}
    assert by_check == {"G1": ["E1"], "G2": ["E2"], "G3": ["E3"], "G4": ["E4"]}
    for entry_ in brief["evidence"]:
        assert entry_ == registry[entry_["evidence_id"]]   # copie fidèle, rien d'ajouté


def test_evidence_contains_only_used_entries_in_natural_order():
    brief = build_brief(robert(), "novice")
    ids = [e["evidence_id"] for e in brief["evidence"]]
    assert ids == ["E1", "E2", "E3", "E4"]          # E5 (avant l'idée) n'est ni citée ni mise en avant
    result = robert()
    result["evidence"].update({"E10": entry("E10", metric="max_drawdown"), "E9": entry("E9", metric="x")})
    result["submission"]["highlight_evidence_ids"] = ["E10", "E9"]
    ids = [e["evidence_id"] for e in build_brief(result, "novice")["evidence"]]
    assert ids == ["E1", "E2", "E3", "E4", "E9", "E10"]


def test_missing_evidence_link_is_completed_by_metric_and_subject():
    result = robert()
    for check in result["governance_after"]["checks"]:
        check["evidence_ids"] = []
    brief = build_brief(result, "novice")
    assert {c["check_id"]: c["evidence_ids"] for c in brief["checks"]} == {
        "G1": ["E1"], "G2": ["E2"], "G3": ["E3"], "G4": ["E4"]}


def test_no_evidence_available_stays_empty_not_invented():
    result = robert()
    result["evidence"] = {}
    result["submission"]["highlight_evidence_ids"] = []
    for check in result["governance_after"]["checks"]:
        check["evidence_ids"] = []
    brief = build_brief(result, "novice")
    assert brief["evidence"] == [] and all(c["evidence_ids"] == [] for c in brief["checks"])
    assert [f["evidence_ids"] for f in brief["ranked_factors"]] == [[], [], []]


def test_asset_class_rules_have_no_automatic_evidence_link():
    result = robert()
    check = make_check("G5", "tension", 0.05, rule_type="max_asset_class_weight")
    result["governance_after"]["checks"].append(check)
    result["evidence"]["E7"] = entry("E7", metric="weight_by_asset_class")
    brief = build_brief(result, "novice")
    assert next(c for c in brief["checks"] if c["check_id"] == "G5")["evidence_ids"] == []


def test_dangling_references_raise():
    result = robert()
    result["governance_after"]["checks"][0]["evidence_ids"] = ["E99"]
    with pytest.raises(ValueError, match="E99"):
        build_brief(result, "novice")
    result = robert()
    result["submission"]["highlight_evidence_ids"] = ["E98"]
    with pytest.raises(ValueError, match="E98"):
        build_brief(result, "novice")
    result = robert()
    result["evidence"]["E1"]["evidence_id"] = "E7"
    with pytest.raises(ValueError):
        build_brief(result, "novice")


def test_sources_and_assumptions_are_kept():
    brief = build_brief(robert(), "pro")
    for item in brief["evidence"]:
        assert item["source_ids"] and item["period_start"] and item["currency"] and item["transformation"]
    assert all(rule["is_assumption"] is True for rule in brief["profile_rules"])
    assert [r["rule_id"] for r in brief["profile_rules"]] == ["R1", "R2", "R3", "R4", "R5", "R6"]


# ---------- variantes ----------

def variant_result():
    result = robert()
    result["evidence"]["E6"] = entry("E6", metric="top_asset_weight", subject="variant:V1")
    result["evidence"]["E7"] = entry("E7", metric="volatility_ann", subject="variant:V1")
    idea = {"ticker": "TSLA", "target_weight": 0.1, "funding_source": "pro_rata", "funding_ticker": None}
    governance = {
        "profile_id": "robert", "subject": "variant:V1", "overall_status": "tension",
        "checks": [make_check("G1", "compliant", 0.1, "max_single_asset_weight", ["E6"]),
                   make_check("G2", "tension", 0.04, "max_portfolio_volatility")],
    }
    result["variants"] = [{"variant_id": "V1", "reason_code": "reduce_weight", "idea": idea,
                           "snapshot": result["snapshot_after"], "governance": governance}]
    return result


def test_variants_use_code_reason_status_and_evidence():
    brief = build_brief(variant_result(), "novice")
    assert brief["variants"] == [{"variant_id": "V1", "reason_code": "reduce_weight",
                                  "overall_status": "tension", "evidence_ids": ["E6", "E7"]}]
    ids = [e["evidence_id"] for e in brief["evidence"]]
    assert "E6" in ids and "E7" in ids


def test_no_variants_gives_empty_list():
    assert build_brief(robert(), "novice")["variants"] == []


# ---------- limites ----------

def test_limits_use_level_text():
    result = robert()
    assert build_brief(result, "novice")["limits"] == [
        {"limit_id": "L1", "text": result["limits"][0]["text_novice"]}]
    assert build_brief(result, "pro")["limits"] == [
        {"limit_id": "L1", "text": result["limits"][0]["text_pro"]}]


def test_all_result_limits_are_kept_in_natural_order():
    result = robert()
    result["limits"] += [{"limit_id": "L10", "text_novice": "dix", "text_pro": "ten"},
                         {"limit_id": "L2", "text_novice": "deux", "text_pro": "two"}]
    assert [i["limit_id"] for i in build_brief(result, "novice")["limits"]] == ["L1", "L2", "L10"]


def test_evidence_limit_missing_from_result_raises():
    result = robert()
    result["evidence"]["E1"]["limit_ids"] = ["L1", "L7"]
    with pytest.raises(ValueError, match="L7"):
        build_brief(result, "novice")


def test_limit_text_missing_for_level_raises():
    result = robert()
    del result["limits"][0]["text_pro"]
    assert build_brief(result, "novice")["limits"]
    with pytest.raises(ValueError, match="L1"):
        build_brief(result, "pro")


def test_every_evidence_limit_is_listed():
    brief = build_brief(robert(), "novice")
    listed = {i["limit_id"] for i in brief["limits"]}
    assert {lid for e in brief["evidence"] for lid in e["limit_ids"]} <= listed


# ---------- glossaire ----------

def test_glossary_matches_rule_types_present():
    brief = build_brief(robert(), "novice")
    assert [g["term"] for g in brief["glossary"]] == [
        "Volatilité", "Perte maximale historique", "Concentration", "Part défensive"]
    only = amira()          # un seul contrôle : concentration par actif
    assert [g["term"] for g in build_brief(only, "novice")["glossary"]] == ["Concentration"]


def test_glossary_adapts_to_level():
    novice = {g["term_id"]: g for g in build_brief(robert(), "novice")["glossary"]}
    pro = {g["term_id"]: g for g in build_brief(robert(), "pro")["glossary"]}
    assert set(novice) == set(pro)
    for term_id in novice:
        assert novice[term_id]["analogy"] and pro[term_id]["analogy"] == ""
        assert novice[term_id]["definition"] != pro[term_id]["definition"]
        assert novice[term_id]["term"] == pro[term_id]["term"]


def test_glossary_catalog_is_closed_and_clean():
    catalog = load_glossary()
    ids = [t["term_id"] for t in catalog]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"T\d+", i) for i in ids)
    forbidden = ("recommand", "conseill", "devriez", "garanti", "prévoi", "achet", "vend")
    for term in catalog:
        for level in ("novice", "pro"):
            text = " ".join(str(v) for v in term[level].values()).lower()
            assert not re.search(r"\d", text), (term["term_id"], level)
            assert not any(word in text for word in forbidden), (term["term_id"], level)


def test_glossary_ids_are_stable_catalog_ids():
    catalog = {t["term"]: t["term_id"] for t in load_glossary()}
    for g in build_brief(robert(), "pro")["glossary"]:
        assert catalog[g["term"]] == g["term_id"]


def test_custom_catalog_and_missing_or_bad_file(tmp_path):
    custom = [{"term_id": "T9", "term": "Terme d'essai", "rule_types": ["max_portfolio_volatility"],
               "novice": {"definition": "simple", "analogy": "image"}, "pro": {"definition": "technique"}}]
    brief = build_brief(robert(), "pro", glossary_catalog=custom)
    assert brief["glossary"] == [{"term_id": "T9", "term": "Terme d'essai", "definition": "technique",
                                  "analogy": ""}]
    assert build_brief(robert(), "pro", glossary_catalog=[])["glossary"] == []
    assert load_glossary(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_glossary(bad)
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"terms": [{"term_id": "T1"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_glossary(incomplete)


# ---------- empreinte ----------

def test_brief_id_is_deterministic_and_level_dependent():
    a, b = build_brief(robert(), "novice"), build_brief(robert(), "novice")
    assert a["brief_id"] == b["brief_id"] and a == b
    assert re.fullmatch(r"brief-[0-9a-f]{16}", a["brief_id"])
    assert build_brief(robert(), "pro")["brief_id"] != a["brief_id"]


def test_brief_id_changes_when_any_content_changes():
    base = build_brief(robert(), "novice")["brief_id"]
    result = robert()
    result["governance_after"]["checks"][0]["status"] = "tension"
    assert build_brief(result, "novice")["brief_id"] != base
    result = robert()
    result["evidence"]["E1"]["display_value"] = "26 %"
    assert build_brief(result, "novice")["brief_id"] != base
    result = robert()
    result["limits"][0]["text_novice"] = "Autre limite."
    assert build_brief(result, "novice")["brief_id"] != base


def test_brief_id_ignores_content_outside_brief():
    base = build_brief(robert(), "novice")["brief_id"]
    result = robert()
    result["created_at"] = "2030-01-01T00:00:00Z"
    result["trace"] = []
    result["profile"]["display_name"] = "Autre nom"
    assert build_brief(result, "novice")["brief_id"] == base


# ---------- confidentialité et isolation ----------

def test_free_text_and_identity_never_enter_the_brief():
    result = robert()
    result["submission"]["unsupported_requests"] = ["Je veux gagner beaucoup d'argent vite"]
    result["profile"]["display_name"] = "NomUnique"
    dump = json.dumps(build_brief(result, "pro"), ensure_ascii=False)
    assert "gagner beaucoup" not in dump and "NomUnique" not in dump
    assert "snapshot" not in dump and "portfolio_before" not in dump


def test_build_does_not_mutate_result_and_brief_is_independent():
    result = robert()
    snapshot = copy.deepcopy(result)
    brief = build_brief(result, "novice")
    assert result == snapshot
    brief["checks"][0]["status"] = "compliant"
    brief["evidence"][0]["display_value"] = "0 %"
    brief["profile_rules"][0]["warn_threshold"] = 0.99
    assert result == snapshot


# ---------- compatibilité B3 et gouvernance ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("make_result", [robert, amira, variant_result])
def test_brief_feeds_b3_fallback_and_rendering(level, make_result):
    brief = build_brief(make_result(), level)
    output = render_template(brief)
    assert [f["check_id"] for f in output["factors"]] == [f["check_id"] for f in brief["ranked_factors"]]
    known = ({e["evidence_id"] for e in brief["evidence"]} | {c["check_id"] for c in brief["checks"]}
             | {g["term_id"] for g in brief["glossary"]})
    text = " ".join([output["summary"], output["counterfactual"], output["variants"],
                     output["limits_context"]] + [f["text"] for f in output["factors"]])
    assert set(REF.findall(text)) <= known
    markdown = render_markdown(output, brief)
    assert "référence inconnue" not in markdown and not REF.search(markdown)
    assert len(brief["limits"]) and brief["limits"][0]["text"] in markdown


def test_novice_and_pro_briefs_share_numbers_and_statuses():
    novice, pro = build_brief(robert(), "novice"), build_brief(robert(), "pro")
    for key in ("checks", "ranked_factors", "evidence", "variants", "idea", "profile_rules"):
        assert novice[key] == pro[key], key
    assert novice["limits"] != pro["limits"] and novice["glossary"] != pro["glossary"]


def test_statuses_follow_governance_evaluate():
    data = robert()
    result = evaluate(data["profile"], data["snapshot_after"], evidence=data["evidence"])
    data["governance_after"] = result
    brief = build_brief(data, "pro")
    assert [c["status"] for c in brief["checks"]] == [c["status"] for c in result["checks"]]
    flagged = {c["check_id"] for c in result["checks"] if c["status"] != "compliant"}
    assert {f["check_id"] for f in brief["ranked_factors"]} == flagged
    assert result["overall_status"] == "conflict"


def test_missing_info_check_is_ranked_and_cited():
    data = robert()
    snapshot = copy.deepcopy(data["snapshot_after"])
    snapshot["volatility_ann"] = None
    data["governance_after"] = evaluate(data["profile"], snapshot, evidence=data["evidence"])
    brief = build_brief(data, "novice")
    statuses = {f["check_id"]: f["status"] for f in brief["ranked_factors"]}
    assert statuses["G2"] == "missing_info"
    order = [f["check_id"] for f in brief["ranked_factors"]]
    assert order.index("G1") < order.index("G3") < order.index("G2")   # conflit, tension, puis manquant
    output = render_template(brief)
    assert "G2" in re.findall(r"\[(G\d+)\]", output["summary"])


def test_module_has_no_network_or_model_dependency():
    source = Path(explanation_brief.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(boto3|botocore|requests|urllib|anthropic)", source, re.M)
    assert "\u2014" not in source
