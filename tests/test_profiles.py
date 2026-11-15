"""Tests B1 : profils investisseurs. Données entièrement fictives, aucun appel AWS."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge.contracts import InvestorProfile, Portfolio, check_keys  # noqa: E402
from alphaforge import profiles  # noqa: E402
from alphaforge.profiles import (  # noqa: E402
    ProfileValidationError, build_profile_from_answers, check_answers, load_personas,
)

FIXTURES = Path(__file__).parent / "fixtures"
RULE_KEYS = {
    "rule_id", "rule_type", "params", "direction", "warn_threshold", "limit_threshold",
    "unit", "label_fr", "origin", "is_assumption",
}
RULE_TYPES = {
    "max_single_asset_weight", "max_asset_class_weight", "max_portfolio_volatility",
    "max_portfolio_drawdown", "min_defensive_share", "excluded_asset_class",
    "max_correlated_group_weight", "esg_exclusion",
}


def valid_answers(**overrides):
    answers = {
        "objective": "Croissance modérée",
        "horizon_years_min": 8,
        "horizon_years_max": 12,
        "risk_tolerance": "moderate",
        "experience": "intermediate",
        "esg_preference": "none",
        "crypto_allowed": False,
        "capital_cad": 50000,
        "max_single_asset_weight": 0.2,
    }
    answers.update(overrides)
    return answers


def codes(issues, severity=None):
    return {i["code"] for i in issues if severity is None or i["severity"] == severity}


def rule_by_id(profile, rule_id):
    return next(r for r in profile["rules"] if r["rule_id"] == rule_id)


# ---------- personas ----------

def test_three_personas_loaded():
    personas = load_personas()
    assert set(personas) == {"amira", "mateo", "robert"}
    for pid, entry in personas.items():
        assert entry["profile"]["profile_id"] == pid
        assert entry["portfolio"]["portfolio_id"] == "portfolio_" + pid
        assert isinstance(entry["age"], int)
        assert entry["occupation_fr"] and entry["summary_fr"]


def test_personas_respect_contracts():
    for entry in load_personas().values():
        assert check_keys(entry["profile"], InvestorProfile) == []
        assert check_keys(entry["portfolio"], Portfolio) == []
        for rule in entry["profile"]["rules"]:
            assert set(rule) == RULE_KEYS
            assert rule["rule_type"] in RULE_TYPES


def test_personas_are_fictional_and_assumptions():
    for entry in load_personas().values():
        profile = entry["profile"]
        assert profile["is_fictional"] is True
        assert entry["portfolio"]["is_fictional"] is True
        assert entry["portfolio"]["base_currency"] == "CAD"
        # Six règles financières ; Mateo (exigence ESG forte) a en plus R7, l'exclusion ESG ;
        # Amira a en plus R8, le plafond par groupe corrélé (P2, US-18).
        expected = {"robert": 6, "amira": 7, "mateo": 7}[profile["profile_id"]]
        assert len(profile["rules"]) == expected
        assert all(r["is_assumption"] is True for r in profile["rules"])
        assert all(r["origin"] == "persona" for r in profile["rules"])


def test_persona_traits_match_brief():
    p = {k: v["profile"] for k, v in load_personas().items()}
    assert (p["amira"]["risk_tolerance"], p["amira"]["crypto_allowed"]) == ("high", True)
    assert p["amira"]["horizon_years_min"] >= 15
    assert (p["mateo"]["risk_tolerance"], p["mateo"]["esg_preference"]) == ("moderate", "strong")
    assert (p["mateo"]["horizon_years_min"], p["mateo"]["horizon_years_max"]) == (8, 12)
    assert (p["robert"]["risk_tolerance"], p["robert"]["crypto_allowed"]) == ("low_moderate", False)
    assert (p["robert"]["horizon_years_min"], p["robert"]["horizon_years_max"]) == (3, 5)


def test_default_level_follows_experience():
    for entry in load_personas().values():
        profile = entry["profile"]
        expected = "novice" if profile["experience"] == "beginner" else "pro"
        assert profile["default_level"] == expected


def test_robert_and_amira_rules_match_b0_fixtures():
    personas = load_personas()
    for pid in ("robert", "amira"):
        fixture = json.loads((FIXTURES / f"profile_{pid}.json").read_text(encoding="utf-8"))
        # Les six règles de la fixture B0 restent identiques ; Amira en a une de plus (R8, P2).
        assert personas[pid]["profile"]["rules"][:len(fixture["rules"])] == fixture["rules"]
    assert len(personas["robert"]["profile"]["rules"]) == 6
    extra = personas["amira"]["profile"]["rules"][6]
    assert extra["rule_type"] == "max_correlated_group_weight" and extra["is_assumption"] is True


def test_load_personas_returns_independent_copies():
    first = load_personas()
    first["robert"]["profile"]["rules"][0]["warn_threshold"] = 0.99
    assert load_personas()["robert"]["profile"]["rules"][0]["warn_threshold"] == 0.2


def test_crypto_rules_follow_persona():
    personas = load_personas()
    for pid in ("robert", "mateo"):
        r5 = rule_by_id(personas[pid]["profile"], "R5")
        assert r5["rule_type"] == "excluded_asset_class"
        assert r5["params"] == {"asset_class": "crypto"}
        assert r5["limit_threshold"] == 0.0 and r5["warn_threshold"] is None
    r5 = rule_by_id(personas["amira"]["profile"], "R5")
    assert r5["rule_type"] == "max_asset_class_weight"
    assert r5["params"] == {"asset_class": "crypto"}


# ---------- portefeuilles ----------

def test_portfolio_weights_sum_to_one():
    for entry in load_personas().values():
        total = sum(p["weight"] for p in entry["portfolio"]["positions"])
        assert total == pytest.approx(1.0, abs=1e-9)
        assert all(p["weight"] > 0 for p in entry["portfolio"]["positions"])


def test_portfolio_tickers_exist_in_universe_without_duplicates():
    with (ROOT / "data" / "raw" / "assets_universe.csv").open(encoding="utf-8") as handle:
        universe = {row["ticker"]: row["asset_class"] for row in csv.DictReader(handle)}
    for entry in load_personas().values():
        tickers = [p["ticker"] for p in entry["portfolio"]["positions"]]
        assert len(tickers) == len(set(tickers))
        assert set(tickers) <= set(universe)


def test_robert_portfolio_matches_b0_fixture():
    fixture = json.loads((FIXTURES / "portfolio_robert.json").read_text(encoding="utf-8"))
    assert load_personas()["robert"]["portfolio"] == fixture


def test_starting_portfolios_respect_simple_persona_rules():
    """Les portefeuilles de départ ne doivent pas être en tension avant toute idée."""
    with (ROOT / "data" / "raw" / "assets_universe.csv").open(encoding="utf-8") as handle:
        universe = {row["ticker"]: row["asset_class"] for row in csv.DictReader(handle)}
    for pid, entry in load_personas().items():
        profile, positions = entry["profile"], entry["portfolio"]["positions"]
        top = max(p["weight"] for p in positions)
        assert top <= rule_by_id(profile, "R1")["warn_threshold"], pid
        crypto = sum(p["weight"] for p in positions if universe[p["ticker"]] == "crypto")
        if profile["crypto_allowed"]:
            assert crypto <= rule_by_id(profile, "R5")["warn_threshold"], pid
        else:
            assert crypto == 0, pid
        # Les obligations sont une borne basse de la part défensive (définition exacte : flux A).
        bonds = sum(p["weight"] for p in positions if universe[p["ticker"]] == "etf_bond")
        assert bonds >= rule_by_id(profile, "R4")["warn_threshold"] - 1e-9, pid


# ---------- seuils ----------

def test_persona_thresholds_are_ordered():
    for entry in load_personas().values():
        for rule in entry["profile"]["rules"]:
            warn, limit = rule["warn_threshold"], rule["limit_threshold"]
            if warn is None or limit is None:
                continue
            if rule["direction"] == "max":
                assert warn <= limit, rule["rule_id"]
            else:
                assert warn >= limit, rule["rule_id"]
            assert 0.0 <= min(warn, limit) and max(warn, limit) <= 1.0


@pytest.mark.parametrize("risk", profiles.RISK_TOLERANCES)
@pytest.mark.parametrize("crypto_allowed", [True, False])
def test_built_thresholds_are_ordered_and_labelled_as_assumptions(risk, crypto_allowed):
    profile = build_profile_from_answers(valid_answers(risk_tolerance=risk, crypto_allowed=crypto_allowed))
    assert [r["rule_id"] for r in profile["rules"]] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    for rule in profile["rules"]:
        assert set(rule) == RULE_KEYS
        assert rule["is_assumption"] is True
        assert rule["origin"] == "checkbox"
        warn, limit = rule["warn_threshold"], rule["limit_threshold"]
        if warn is None or limit is None:
            continue
        if rule["direction"] == "max":
            assert warn <= limit
        else:
            assert warn >= limit


def test_thresholds_get_stricter_when_tolerance_decreases():
    built = {r: build_profile_from_answers(valid_answers(risk_tolerance=r, max_single_asset_weight=None))
             for r in profiles.RISK_TOLERANCES}
    for rule_id in ("R2", "R3"):
        warns = [rule_by_id(built[r], rule_id)["warn_threshold"] for r in profiles.RISK_TOLERANCES]
        assert warns == sorted(warns), rule_id
    defensive = [rule_by_id(built[r], "R4")["warn_threshold"] for r in profiles.RISK_TOLERANCES]
    assert defensive == sorted(defensive, reverse=True)


def test_single_asset_cap_sets_thresholds():
    rule = rule_by_id(build_profile_from_answers(valid_answers(max_single_asset_weight=0.15)), "R1")
    assert rule["warn_threshold"] == 0.15
    assert rule["limit_threshold"] == pytest.approx(0.20)
    rule = rule_by_id(build_profile_from_answers(valid_answers(max_single_asset_weight=0.98)), "R1")
    assert rule["limit_threshold"] == 1.0


def test_default_single_asset_cap_used_when_missing():
    answers = valid_answers()
    del answers["max_single_asset_weight"]
    profile = build_profile_from_answers(answers)
    assert rule_by_id(profile, "R1")["warn_threshold"] == profiles.DEFAULT_SINGLE_ASSET_CAP["moderate"]
    assert "default_single_cap_used" in codes(check_answers(answers), "info")


def test_crypto_rule_depends_on_crypto_allowed():
    excluded = rule_by_id(build_profile_from_answers(valid_answers(crypto_allowed=False)), "R5")
    assert excluded["rule_type"] == "excluded_asset_class"
    assert excluded["unit"] == "bool" and excluded["limit_threshold"] == 0.0
    capped = rule_by_id(build_profile_from_answers(valid_answers(crypto_allowed=True)), "R5")
    assert capped["rule_type"] == "max_asset_class_weight"
    assert capped["params"] == {"asset_class": "crypto"}
    assert capped["unit"] == "pct"


def test_mateo_answers_reproduce_mateo_rules():
    mateo = load_personas()["mateo"]["profile"]
    built = build_profile_from_answers(valid_answers(
        esg_preference="strong", max_single_asset_weight=0.25))
    persona_rules = [dict(r, origin="checkbox") for r in mateo["rules"]]
    assert built["rules"] == persona_rules


# ---------- construction du profil ----------

def test_build_profile_respects_contract():
    profile = build_profile_from_answers(valid_answers())
    assert check_keys(profile, InvestorProfile) == []
    assert profile["profile_id"] == "custom"
    assert profile["is_fictional"] is True
    assert profile["capital_cad"] == 50000.0 and isinstance(profile["capital_cad"], float)
    assert profile["objective"] == "Croissance modérée"


def test_default_level_from_answers():
    assert build_profile_from_answers(valid_answers(experience="beginner"))["default_level"] == "novice"
    assert build_profile_from_answers(valid_answers(experience="intermediate"))["default_level"] == "pro"
    assert build_profile_from_answers(valid_answers(experience="advanced"))["default_level"] == "pro"


def test_build_does_not_mutate_answers():
    answers = valid_answers()
    snapshot = dict(answers)
    build_profile_from_answers(answers)
    assert answers == snapshot


# ---------- champs manquants et valeurs invalides ----------

@pytest.mark.parametrize("field", profiles.REQUIRED_ANSWERS)
def test_missing_required_field_is_rejected(field):
    answers = valid_answers()
    del answers[field]
    with pytest.raises(ProfileValidationError) as error:
        build_profile_from_answers(answers)
    assert any(i["code"] == "missing_field" and i["fields"] == [field] for i in error.value.issues)


def test_none_value_counts_as_missing():
    assert "missing_field" in codes(check_answers(valid_answers(risk_tolerance=None)), "error")


@pytest.mark.parametrize("overrides", [
    {"risk_tolerance": "extreme"},
    {"experience": "expert"},
    {"esg_preference": "max"},
    {"crypto_allowed": "oui"},
    {"capital_cad": 0},
    {"capital_cad": -10},
    {"capital_cad": "100000"},
    {"horizon_years_min": -1},
    {"horizon_years_min": 2.5},
    {"max_single_asset_weight": 0},
    {"max_single_asset_weight": 1.5},
    {"objective": "   "},
])
def test_invalid_values_are_rejected(overrides):
    with pytest.raises(ProfileValidationError):
        build_profile_from_answers(valid_answers(**overrides))


def test_inverted_horizon_is_rejected():
    answers = valid_answers(horizon_years_min=10, horizon_years_max=5)
    assert "horizon_inverted" in codes(check_answers(answers), "error")
    with pytest.raises(ProfileValidationError):
        build_profile_from_answers(answers)


def test_unknown_field_is_rejected_not_ignored():
    """Aucun texte libre ni champ inconnu : pas d'ignorance silencieuse."""
    answers = valid_answers(other_constraint="pas de pétrole")
    assert "unknown_field" in codes(check_answers(answers), "error")
    with pytest.raises(ProfileValidationError):
        build_profile_from_answers(answers)


def test_non_dict_answers_are_rejected():
    assert codes(check_answers(None)) == {"answers_not_dict"}  # type: ignore[arg-type]
    with pytest.raises(ProfileValidationError):
        build_profile_from_answers([])  # type: ignore[arg-type]


def test_error_messages_are_in_french():
    issues = check_answers(valid_answers(capital_cad=0))
    assert "capital" in issues[0]["message_fr"].lower()


# ---------- contradictions ----------

def test_valid_answers_have_no_warning():
    assert codes(check_answers(valid_answers()), "warning") == set()


def test_low_tolerance_with_crypto_and_high_cap_is_flagged():
    """Exemple de la user story US-02."""
    answers = valid_answers(risk_tolerance="low", crypto_allowed=True, max_single_asset_weight=0.4)
    found = codes(check_answers(answers), "warning")
    assert {"crypto_vs_low_risk", "single_cap_vs_risk"} <= found
    # Une contradiction ne bloque pas la construction du profil.
    assert build_profile_from_answers(answers)["profile_id"] == "custom"


def test_low_moderate_with_crypto_is_flagged():
    assert "crypto_vs_low_risk" in codes(check_answers(valid_answers(
        risk_tolerance="low_moderate", crypto_allowed=True)), "warning")


def test_cap_contradiction_boundary():
    default = profiles.DEFAULT_SINGLE_ASSET_CAP["moderate"]
    at_margin = default + profiles.CAP_CONTRADICTION_MARGIN
    assert "single_cap_vs_risk" not in codes(check_answers(
        valid_answers(max_single_asset_weight=at_margin)), "warning")
    assert "single_cap_vs_risk" in codes(check_answers(
        valid_answers(max_single_asset_weight=at_margin + 0.01)), "warning")


def test_high_risk_with_short_horizon_is_flagged():
    assert "short_horizon_vs_high_risk" in codes(check_answers(valid_answers(
        risk_tolerance="high", horizon_years_min=1, horizon_years_max=4)), "warning")
    assert "short_horizon_vs_high_risk" not in codes(check_answers(valid_answers(
        risk_tolerance="high", horizon_years_min=1, horizon_years_max=5)), "warning")


def test_high_risk_beginner_is_flagged():
    assert "beginner_vs_high_risk" in codes(check_answers(valid_answers(
        risk_tolerance="high", experience="beginner", max_single_asset_weight=0.35)), "warning")


def test_esg_preference_is_never_silently_dropped():
    assert "esg_not_evaluated" in codes(check_answers(valid_answers(esg_preference="moderate")), "info")
    assert "esg_evidence_unavailable" in codes(check_answers(valid_answers(esg_preference="strong")), "info")
    quiet = codes(check_answers(valid_answers()))
    assert "esg_not_evaluated" not in quiet and "esg_evidence_unavailable" not in quiet


def esg_rules(profile):
    return [r for r in profile["rules"] if r["rule_type"] == "esg_exclusion"]


def test_mateo_has_an_esg_exclusion_rule_that_follows_the_contract():
    mateo = load_personas()["mateo"]["profile"]
    assert mateo["esg_preference"] == "strong"
    (rule,) = esg_rules(mateo)
    assert rule["rule_id"] == "R7" and set(rule) == RULE_KEYS
    assert (rule["params"], rule["direction"], rule["unit"]) == ({}, "max", "bool")
    assert (rule["warn_threshold"], rule["limit_threshold"]) == (None, 0.0)
    assert rule["is_assumption"] is True and rule["origin"] == "persona"
    assert [r["rule_id"] for r in mateo["rules"]] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]


def test_personas_without_strong_esg_have_no_esg_rule():
    personas = load_personas()
    assert esg_rules(personas["robert"]["profile"]) == [] and esg_rules(personas["amira"]["profile"]) == []


def test_custom_profile_gets_an_esg_rule_only_for_strong_preference():
    strong = build_profile_from_answers(valid_answers(esg_preference="strong"))
    (rule,) = esg_rules(strong)
    assert rule["rule_id"] == "R7" and rule["origin"] == "checkbox" and set(rule) == RULE_KEYS
    assert rule["limit_threshold"] == 0.0 and rule["warn_threshold"] is None and rule["is_assumption"] is True
    for preference in ("none", "moderate"):
        profile = build_profile_from_answers(valid_answers(esg_preference=preference))
        assert esg_rules(profile) == [] and len(profile["rules"]) == 6


def test_esg_rule_never_carries_a_score_or_evidence_reference():
    for profile in (load_personas()["mateo"]["profile"],
                    build_profile_from_answers(valid_answers(esg_preference="strong"))):
        (rule,) = esg_rules(profile)
        assert rule["params"] == {} and rule["warn_threshold"] is None


# ---------- R6 : actions individuelles ----------

def test_r6_label_says_individual_stocks_and_matches_its_parameters():
    profiles = [e["profile"] for e in load_personas().values()]
    profiles.append(build_profile_from_answers(valid_answers()))
    for profile in profiles:
        r6 = rule_by_id(profile, "R6")
        assert r6["rule_type"] == "max_asset_class_weight" and r6["params"] == {"asset_class": "equity"}
        assert r6["label_fr"] == "Concentration en actions individuelles"
        assert "par catégorie" not in r6["label_fr"]


def test_r6_thresholds_were_not_changed():
    thresholds = {k: (rule_by_id(e["profile"], "R6")["warn_threshold"], rule_by_id(e["profile"], "R6")["limit_threshold"])
                  for k, e in load_personas().items()}
    assert thresholds == {"amira": (0.7, 0.85), "mateo": (0.7, 0.85), "robert": (0.65, 0.8)}


def test_issues_have_expected_shape():
    issues = check_answers(valid_answers(risk_tolerance="low", crypto_allowed=True, esg_preference="moderate"))
    for issue in issues:
        assert set(issue) == {"code", "severity", "fields", "message_fr"}
        assert issue["severity"] in {"error", "warning", "info"}
        assert issue["fields"] and issue["message_fr"]
