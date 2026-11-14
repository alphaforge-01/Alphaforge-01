"""Tests B3 : explication de secours. Chiffres inventés, aucun appel AWS ni modèle."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge import explanation_fallback  # noqa: E402
from alphaforge.contracts import ExplainerOutput, check_keys  # noqa: E402
from alphaforge.explanation_fallback import VERDICT_FR, render_template  # noqa: E402
from alphaforge.governance import evaluate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
REF = re.compile(r"\[([EGT]\d+)\]")
FORBIDDEN = ("recommand", "conseill", "devriez", "devrait", "achet", "vend", "garanti", "prévoi",
             "prédi", "gagnera", "perdrez", "sans risque", "certain", "profitez", "il faut")
SLOTS = ("summary", "counterfactual", "variants", "limits_context")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_brief(level="novice", **overrides):
    brief = copy.deepcopy(load("explanation_brief_robert_novice.json"))
    brief["level"] = level
    brief.update(overrides)
    return brief


def make_check(check_id, status, rule_type="max_portfolio_volatility", rule_id=None, **kw):
    check = {
        "check_id": check_id, "rule_id": rule_id or "R" + check_id[1:], "rule_type": rule_type,
        "label_fr": "Règle d'essai", "status": status, "value": 0.2, "warn_threshold": 0.1,
        "limit_threshold": 0.3, "margin": 0.1, "unit": "pct", "evidence_ids": [],
        "counterfactual": None, "missing_reason": None,
    }
    check.update(kw)
    return check


def brief_with(level, checks, ranked=None, **overrides):
    ranked = ranked if ranked is not None else [
        {"rank": i, "check_id": c["check_id"], "status": c["status"], "evidence_ids": c["evidence_ids"]}
        for i, c in enumerate(checks, start=1)]
    overrides.setdefault("profile_rules", [])
    return make_brief(level, checks=checks, ranked_factors=ranked, **overrides)


def all_texts(output):
    return [output[s] for s in SLOTS] + [f["text"] for f in output["factors"]]


def strip_refs(text):
    return REF.sub("", text)


# ---------- contrat ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_output_respects_contract(level):
    brief = make_brief(level)
    out = render_template(brief)
    assert check_keys(out, ExplainerOutput) == []
    assert set(out) == set(ExplainerOutput.__annotations__)
    assert out["brief_id"] == brief["brief_id"] and out["level"] == level
    assert (out["origin"], out["model_id"], out["prompt_version"], out["attempt"]) == ("template", None, None, 0)
    assert all(isinstance(out[s], str) and out[s] for s in SLOTS)


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_factors_follow_ranked_order(level):
    brief = make_brief(level)
    out = render_template(brief)
    assert [f["check_id"] for f in out["factors"]] == [r["check_id"] for r in brief["ranked_factors"]]
    assert all(set(f) == {"check_id", "text"} for f in out["factors"])


def test_factor_without_matching_check_is_skipped_not_invented():
    brief = make_brief()
    brief["ranked_factors"].append({"rank": 3, "check_id": "G99", "status": "conflict", "evidence_ids": []})
    assert [f["check_id"] for f in render_template(brief)["factors"]] == ["G1", "G2"]


# ---------- aucun chiffre en clair, références valides ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_no_digit_outside_references(level):
    out = render_template(make_brief(level))
    for text in all_texts(out):
        assert not re.search(r"\d", strip_refs(text)), text


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_all_references_exist_in_brief(level):
    brief = make_brief(level)
    out = render_template(brief)
    known = ({e["evidence_id"] for e in brief["evidence"]} | {c["check_id"] for c in brief["checks"]}
             | {g["term_id"] for g in brief["glossary"]})
    refs = {r for text in all_texts(out) for r in REF.findall(text)}
    assert refs and refs <= known


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_every_non_compliant_check_is_cited_in_summary(level):
    checks = [make_check("G1", "conflict"), make_check("G2", "tension"),
              make_check("G3", "missing_info"), make_check("G4", "compliant")]
    # Le classement du dossier peut être incomplet : le résumé cite quand même tout.
    out = render_template(brief_with(level, checks, ranked=[]))
    cited = set(REF.findall(out["summary"]))
    assert {"G1", "G2", "G3"} <= cited and "G4" not in cited


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_no_forbidden_terms(level):
    for status in ("conflict", "tension", "compliant", "missing_info"):
        out = render_template(brief_with(level, [make_check("G1", status)]))
        blob = " ".join(all_texts(out)).lower()
        assert not any(term in blob for term in FORBIDDEN), (status, blob)


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_slots_respect_max_chars(level):
    for max_chars in (400, 250):
        checks = [make_check(f"G{i}", "conflict", evidence_ids=[f"E{i}"]) for i in range(1, 7)]
        variants = [{"variant_id": "V1", "reason_code": "reduce_weight", "overall_status": "tension",
                     "evidence_ids": ["E1", "E2"]},
                    {"variant_id": "V2", "reason_code": "spread_across_existing",
                     "overall_status": "compliant", "evidence_ids": []}]
        brief = brief_with(level, checks, variants=variants, max_chars_per_slot=max_chars)
        out = render_template(brief)
        for text in all_texts(out):
            assert len(text) <= max_chars, (max_chars, len(text), text)


# ---------- statuts conservés ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_verdict_is_worst_status_of_checks(level):
    cases = [
        (["compliant", "missing_info"], "missing_info"),
        (["missing_info", "tension"], "tension"),
        (["tension", "conflict"], "conflict"),
    ]
    for statuses, worst in cases:
        checks = [make_check(f"G{i}", s) for i, s in enumerate(statuses, start=1)]
        out = render_template(brief_with(level, checks))
        assert VERDICT_FR[worst] in out["summary"], (statuses, out["summary"])


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_all_compliant_says_so_and_cites_nothing(level):
    out = render_template(brief_with(level, [make_check("G1", "compliant"), make_check("G2", "compliant")]))
    assert "respecte" in out["summary"] or "conformes" in out["summary"]
    assert REF.findall(out["summary"]) == []
    assert "aucun contrefactuel" in out["counterfactual"]


def test_statuses_come_from_governance_not_recomputed():
    """Un contrôle 'conforme' donné par le dossier n'est jamais présenté comme un problème."""
    snapshot = load("analysis_result_robert_tsla.json")["snapshot_after"]
    profile = load("profile_robert.json")
    checks = evaluate(profile, snapshot)["checks"]
    brief = brief_with("pro", checks, profile_rules=profile["rules"])
    out = render_template(brief)
    cited = set(REF.findall(out["summary"]))
    assert cited == {c["check_id"] for c in checks if c["status"] != "compliant"}


# ---------- informations manquantes ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_missing_info_is_never_presented_as_compliant(level):
    check = make_check("G1", "missing_info", value=None, margin=None,
                       missing_reason="Valeur indisponible dans l'instantané : volatility_ann.")
    out = render_template(brief_with(level, [check]))
    text = out["factors"][0]["text"].lower()
    assert "manquante" in text
    assert "conforme" not in text and "respecté" not in text
    assert VERDICT_FR["missing_info"] in out["summary"]
    assert "manque d'information" in out["counterfactual"]


def test_missing_evidence_does_not_invent_value():
    out = render_template(brief_with("novice", [make_check("G1", "conflict", evidence_ids=[])]))
    assert "[E" not in out["factors"][0]["text"]


def test_no_checks_gives_missing_info_summary():
    out = render_template(brief_with("novice", []))
    assert "information manquante" in out["summary"] and out["factors"] == []


# ---------- contrefactuel et variantes ----------

def test_counterfactual_mentions_checks_with_and_without_value():
    out = render_template(make_brief("novice"))
    assert "[G1]" in out["counterfactual"] and "[G2]" in out["counterfactual"]
    assert not re.search(r"\d", strip_refs(out["counterfactual"]))


def test_variants_slot_uses_reason_and_status_without_digits():
    variants = [{"variant_id": "V1", "reason_code": "reduce_weight", "overall_status": "tension",
                 "evidence_ids": ["E1"]},
                {"variant_id": "V2", "reason_code": "change_funding_source",
                 "overall_status": "compliant", "evidence_ids": []}]
    for level in ("novice", "pro"):
        out = render_template(make_brief(level, variants=variants))
        text = out["variants"]
        assert "première" in text and "deuxième" in text
        assert VERDICT_FR["tension"] in text and VERDICT_FR["compliant"] in text
        assert "[E1]" in text
        assert not re.search(r"\d", strip_refs(text))


def test_no_variants_message():
    assert "Aucune variante" in render_template(make_brief("pro"))["variants"]


# ---------- niveaux ----------

def test_novice_and_pro_texts_really_differ():
    novice = render_template(make_brief("novice"))
    pro = render_template(make_brief("pro"))
    for slot in ("summary", "counterfactual", "limits_context"):
        assert novice[slot] != pro[slot], slot
    for n, p in zip(novice["factors"], pro["factors"]):
        assert n["check_id"] == p["check_id"] and n["text"] != p["text"]
    assert [f["check_id"] for f in novice["factors"]] == [f["check_id"] for f in pro["factors"]]


def test_novice_uses_glossary_pro_uses_technical_terms():
    novice = render_template(make_brief("novice"))
    pro = render_template(make_brief("pro"))
    assert "[T1]" in novice["factors"][1]["text"]
    assert not any("[T" in f["text"] for f in pro["factors"])
    assert "annualisée" in pro["factors"][1]["text"] and "marge" in pro["factors"][1]["text"]


def test_no_glossary_term_means_no_term_reference():
    out = render_template(make_brief("novice", glossary=[]))
    assert "[T" not in " ".join(all_texts(out))


def test_levels_cite_same_evidence_for_same_checks():
    n = render_template(make_brief("novice"))
    p = render_template(make_brief("pro"))
    for a, b in zip(n["factors"], p["factors"]):
        assert set(re.findall(r"\[[EG]\d+\]", a["text"])) == set(re.findall(r"\[[EG]\d+\]", b["text"]))


# ---------- robustesse ----------

def test_deterministic_and_no_mutation():
    brief = make_brief("pro")
    snapshot = copy.deepcopy(brief)
    assert render_template(brief) == render_template(brief)
    assert brief == snapshot


def test_invalid_level_and_incomplete_brief_raise():
    with pytest.raises(ValueError):
        render_template(make_brief("expert"))
    brief = make_brief()
    del brief["checks"]
    with pytest.raises(ValueError):
        render_template(brief)
    with pytest.raises(ValueError):
        render_template({})  # type: ignore[arg-type]


def test_min_rule_wording_uses_below():
    check = make_check("G1", "conflict", rule_type="min_defensive_share", evidence_ids=["E4"])
    brief = brief_with("pro", [check])
    brief["profile_rules"] = [{"rule_id": "R1", "direction": "min"}]
    assert "sous la limite" in render_template(brief)["factors"][0]["text"]


def test_module_has_no_network_or_model_dependency():
    source = Path(explanation_fallback.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(boto3|botocore|requests|urllib|anthropic)", source, re.M)
    assert "\u2014" not in source
