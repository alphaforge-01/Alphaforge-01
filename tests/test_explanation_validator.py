"""Tests B6 : validateur d'explication. Chiffres inventés, aucun appel AWS ni modèle."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge import explanation_validator  # noqa: E402
from alphaforge.contracts import ExplainerOutput, ValidationResult, check_keys  # noqa: E402
from alphaforge.explanation_brief import build_brief  # noqa: E402
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_validator import validate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
CODES = {"unknown_reference", "number_outside_registry", "forbidden_term", "missing_rule_citation",
         "slot_missing", "too_long"}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def brief():
    return load("explanation_brief_robert_novice.json")


def good_output():
    """Sortie valide pour le dossier de la fixture : cite G1, G2 et G3, aucun chiffre en clair."""
    return {
        "brief_id": "fixture-brief-robert-novice", "level": "novice",
        "summary": "Le poids atteint [E1], voir [G1]. La volatilité [E2] relève de [G2] et la perte [E3] de [G3].",
        "factors": [{"check_id": "G1", "text": "La concentration dépasse la règle [G1] selon [E1]."},
                    {"check_id": "G2", "text": "La volatilité [E2] mérite attention [G2]."}],
        "counterfactual": "Le plus grand poids testé conforme pour [G1] est donné par le code.",
        "variants": "Aucune variante simulée n'est disponible.",
        "limits_context": "Les données d'essai ne représentent pas les marchés réels.",
        "origin": "llm", "model_id": "modèle-d-essai", "prompt_version": "v1", "attempt": 1,
    }


def codes(result):
    return {r["code"] for r in result["rejections"]}


def with_text(slot, text):
    output = good_output()
    output[slot] = text
    return output


def rejected(output, code, slot=None, **kwargs):
    result = validate(output, brief(), **kwargs)
    matches = [r for r in result["rejections"] if r["code"] == code and (slot is None or r["slot"] == slot)]
    assert matches, (code, slot, result["rejections"])
    assert result["is_valid"] is False
    return matches


# ---------- contrat et cas valides ----------

def test_good_output_is_valid_and_result_respects_contract():
    result = validate(good_output(), brief())
    assert result["is_valid"] is True and result["rejections"] == []
    assert check_keys(result, ValidationResult) == []
    assert set(result) == {"is_valid", "rejections", "checked_references"}
    assert result["checked_references"] == ["E1", "G1", "E2", "G2", "E3", "G3"]


@pytest.mark.parametrize("name", ["explainer_output_robert_novice.json", "explainer_output_robert_pro.json"])
def test_valid_fixtures_are_accepted(name):
    result = validate(load(name), brief())
    assert result["is_valid"] is True, result["rejections"]
    assert set(result["checked_references"]) <= {"E1", "E2", "E3", "G1", "G2", "G3"}


def test_invalid_fixture_is_rejected_with_expected_codes():
    result = validate(load("explainer_output_invalid.json"), brief())
    assert result["is_valid"] is False
    found = codes(result)
    assert {"number_outside_registry", "forbidden_term", "missing_rule_citation"} <= found
    assert found <= CODES
    summary = [r for r in result["rejections"] if r["slot"] == "summary"]
    assert any("99" in r["excerpt"] for r in summary if r["code"] == "number_outside_registry")
    assert any("gagnera" in r["excerpt"] for r in summary if r["code"] == "forbidden_term")


def test_rejection_shape_and_codes_are_from_the_contract():
    result = validate(load("explainer_output_invalid.json"), brief())
    for rejection in result["rejections"]:
        assert set(rejection) == {"code", "slot", "excerpt"} and rejection["code"] in CODES
        assert all(isinstance(v, str) for v in rejection.values())
    keys = [(r["code"], r["slot"], r["excerpt"]) for r in result["rejections"]]
    assert len(keys) == len(set(keys))                    # pas de doublon


def test_validate_does_not_mutate_inputs_and_is_deterministic():
    output, dossier = load("explainer_output_invalid.json"), brief()
    snapshot = copy.deepcopy((output, dossier))
    assert validate(output, dossier) == validate(output, dossier)
    assert (output, dossier) == snapshot


# ---------- unknown_reference ----------

@pytest.mark.parametrize("text,excerpt", [
    ("Voir [E99].", "[E99]"),
    ("Voir [G99].", "[G99]"),
    ("Voir [T99].", "[T99]"),
    ("Voir [E6].", "[E6]"),               # absent du dossier (qui contient E1 à E5)
    ("Voir [L1].", "[L1]"),               # type de renvoi non permis
    ("Voir [X1].", "[X1]"),
    ("Voir [e1].", "[e1]"),               # casse incorrecte : le rendu ne le remplacerait pas
    ("Voir [E1, E2].", "[E1, E2]"),       # multi-renvoi non pris en charge
    ("Voir [E 1].", "[E 1]"),
    ("Voir [E1 ].", "[E1 ]"),
])
def test_unknown_or_malformed_references_are_rejected(text, excerpt):
    found = rejected(with_text("summary", good_output()["summary"] + " " + text), "unknown_reference", "summary")
    assert any(r["excerpt"] == excerpt for r in found)


def test_bare_identifier_without_brackets_is_rejected():
    found = rejected(with_text("counterfactual", "Voir le contrôle G1 pour la suite."), "unknown_reference")
    assert any("G1" in r["excerpt"] for r in found)


def test_unknown_reference_in_every_slot_and_factor():
    for slot in ("counterfactual", "variants", "limits_context"):
        rejected(with_text(slot, "Voir [E77]."), "unknown_reference", slot)
    output = good_output()
    output["factors"][1]["text"] = "La volatilité [E77] mérite attention [G2]."
    rejected(output, "unknown_reference", "factors[1]")


def test_factor_with_unknown_check_id_is_rejected():
    output = good_output()
    output["factors"][1]["check_id"] = "G42"
    rejected(output, "unknown_reference", "factors[1]")


def test_known_references_are_listed_as_checked():
    brief_t = brief()
    brief_t["glossary"] = [{"term_id": "T1", "term": "Volatilité", "definition": "d", "analogy": "a"}]
    output = with_text("limits_context", "Voir [T1] et [E4].")
    result = validate(output, brief_t)
    assert "T1" in result["checked_references"] and "E4" in result["checked_references"]
    assert len(result["checked_references"]) == len(set(result["checked_references"]))


# ---------- number_outside_registry ----------

@pytest.mark.parametrize("text", [
    "Le portefeuille gagne 99 % ici.",
    "La part est de 0,5 environ.",
    "Soit 41,26 % de défensif.",           # proche d'une valeur du registre (41,25), mais différent
    "Environ 1 000 000 de dollars.",
    "Sur 3 ans.",
    "En 2031 peut-être.",
    "Valeur 12.5 constatée.",
])
def test_digits_outside_registry_are_rejected(text):
    rejected(with_text("summary", good_output()["summary"] + " " + text), "number_outside_registry", "summary")


@pytest.mark.parametrize("text", [
    "Il y a trois points à voir.", "Un quart du portefeuille.", "Le double de la part.",
    "La moitié des actifs.", "Vingt-cinq pour cent.", "Quatre-vingts titres.", "Un tiers environ.",
    "Une dizaine de lignes.", "Zéro risque.", "Le triple.", "Mille raisons.", "Dix actifs.",
    "Cent pour cent investi.", "Un demi du capital.", "Une centaine de jours.",
])
def test_numbers_written_in_words_are_rejected(text):
    rejected(with_text("variants", text), "number_outside_registry", "variants")


@pytest.mark.parametrize("text", [
    "Une idée simulée pour un placement unique.", "La première variante et la deuxième variante.",
    "Un seul actif domine, une même catégorie aussi.", "Le contrôle du seuil d'attention.",
    "Ce vendredi, la perte reste historique.",         # "vendredi" ne contient pas "vendre" comme mot
])
def test_articles_ordinals_and_ordinary_words_are_not_numbers(text):
    result = validate(with_text("variants", text), brief())
    assert result["is_valid"] is True, result["rejections"]


def test_registry_numbers_are_accepted_by_default_and_rejected_in_strict_mode():
    output = with_text("variants", "Le poids est 25 % et la part défensive 41,25 %.")
    assert validate(output, brief())["is_valid"] is True
    rejected(output, "number_outside_registry", "variants", allow_registry_numbers=False)


@pytest.mark.parametrize("text", [
    "Le poids est 25 %.", "Le poids est 25%.", "Le poids est 0,25.", "Le poids est 0.25.",
    "La part défensive est de 41,25 %.", "La part vaut 41.25.", "Sur 1000 observations.",
    "Sur 1 000 observations.", "Période du 2021-11-12 au 2026-11-12.", "Volatilité à 21 %.",
])
def test_formats_of_registry_numbers_are_recognized(text):
    assert validate(with_text("variants", text), brief())["is_valid"] is True


def test_date_not_in_registry_is_rejected():
    rejected(with_text("variants", "Période du 2020-01-01."), "number_outside_registry", "variants")


def test_number_inside_valid_reference_is_not_a_number():
    result = validate(with_text("variants", "Voir [E3] puis [G2]."), brief())
    assert "number_outside_registry" not in codes(result)


def test_number_check_covers_factors_and_every_slot():
    for slot in ("summary", "counterfactual", "variants", "limits_context"):
        rejected(with_text(slot, "Environ 77 sur la période."), "number_outside_registry", slot)
    output = good_output()
    output["factors"][0]["text"] = "La concentration dépasse [G1] de 7 points."
    rejected(output, "number_outside_registry", "factors[0]")


# ---------- forbidden_term ----------

@pytest.mark.parametrize("text", [
    "Je recommande de réduire ce poids.", "Nous vous conseillons la prudence.", "Vous devriez attendre.",
    "Achetez maintenant.", "Il faut vendre ce titre.", "Mieux vaut éviter cet actif.",
    "Il vaut mieux diminuer.", "Réduisez ce poids.", "Profitez de l'occasion.", "C'est garanti.",
    "Placement sans risque.", "Ce portefeuille gagnera beaucoup.", "Le titre va monter.",
    "Une prévision favorable.", "Le modèle prédit une hausse.", "Le titre perdra de la valeur.",
    "Le rendement futur est bon.", "C'est un portefeuille rassurant.", "Une allocation solide.",
    "Un résultat excellent.", "Nous suggérons de garder.", "À coup sûr rentable.",
    "Les rendements attendus sont bons.", "Il faudrait diversifier.", "Vendez avant la baisse.",
])
def test_forbidden_terms_are_rejected(text):
    rejected(with_text("limits_context", text), "forbidden_term", "limits_context")


def test_forbidden_terms_ignore_case_accents_and_curly_apostrophe():
    for text in ("RECOMMANDÉ par l’équipe.", "Prevision possible.", "GARANTIE totale."):
        rejected(with_text("variants", text), "forbidden_term", "variants")


def test_forbidden_terms_checked_in_factors():
    output = good_output()
    output["factors"][0]["text"] = "Il faut réduire [G1]."
    rejected(output, "forbidden_term", "factors[0]")


def test_forbidden_term_inside_reference_free_longer_word_is_not_flagged():
    for text in ("Le vendredi suit le jeudi.", "Un rendement observé dans le passé.", "Une idée simulée."):
        assert "forbidden_term" not in codes(validate(with_text("variants", text), brief()))


# ---------- missing_rule_citation ----------

@pytest.mark.parametrize("status", ["tension", "conflict", "missing_info"])
def test_uncited_non_compliant_check_is_rejected(status):
    dossier = brief()
    dossier["checks"][3]["status"] = status        # G4, jamais cité dans la sortie
    result = validate(good_output(), dossier)
    found = [r for r in result["rejections"] if r["code"] == "missing_rule_citation"]
    assert found and "G4" in found[0]["excerpt"] and status in found[0]["excerpt"]


def test_compliant_check_needs_no_citation():
    assert "missing_rule_citation" not in codes(validate(good_output(), brief()))   # G4 est conforme


def test_citation_anywhere_in_output_counts():
    dossier = brief()
    dossier["checks"][3]["status"] = "tension"
    for slot in ("counterfactual", "variants", "limits_context"):
        output = with_text(slot, "Voir [G4].")
        assert "missing_rule_citation" not in codes(validate(output, dossier)), slot


def test_citation_of_unknown_check_does_not_count_for_the_missing_one():
    dossier = brief()
    dossier["checks"][3]["status"] = "conflict"
    output = with_text("variants", "Voir [G44].")
    assert {"unknown_reference", "missing_rule_citation"} <= codes(validate(output, dossier))


def test_all_uncited_checks_are_reported():
    output = good_output()
    output["summary"] = "Un résumé sans renvoi."
    output["factors"] = [{"check_id": "G1", "text": "Texte sans renvoi."}, {"check_id": "G2", "text": "Idem."}]
    output["counterfactual"] = "Aucun renvoi."
    result = validate(output, brief())
    missing = [r["excerpt"] for r in result["rejections"] if r["code"] == "missing_rule_citation"]
    assert [m.split("]")[0] for m in missing] == ["[G1", "[G2", "[G3"]


# ---------- slot_missing ----------

@pytest.mark.parametrize("slot", ["summary", "counterfactual", "variants", "limits_context"])
@pytest.mark.parametrize("bad", [None, "", "   ", 12, ["texte"]])
def test_empty_text_slot_is_rejected(slot, bad):
    rejected(with_text(slot, bad), "slot_missing", slot)


@pytest.mark.parametrize("key", sorted(ExplainerOutput.__annotations__))
def test_missing_contract_key_is_rejected(key):
    output = good_output()
    del output[key]
    rejected(output, "slot_missing", key)


def test_missing_factors_are_rejected():
    output = good_output()
    output["factors"] = output["factors"][:1]
    found = rejected(output, "slot_missing", "factors")
    assert any("G2" in r["excerpt"] for r in found)
    output["factors"] = []
    assert len(rejected(output, "slot_missing", "factors")) == 2
    output["factors"] = "pas une liste"
    rejected(output, "slot_missing", "factors")


def test_factor_text_missing_or_without_check_id():
    output = good_output()
    output["factors"][0]["text"] = ""
    rejected(output, "slot_missing", "factors[0]")
    output = good_output()
    output["factors"][1] = {"text": "Texte sans identifiant [G2]."}
    rejected(output, "slot_missing", "factors[1]")
    output = good_output()
    output["factors"][1] = "texte brut"
    rejected(output, "slot_missing", "factors[1]")


def test_factor_order_must_follow_ranked_factors():
    output = good_output()
    output["factors"].reverse()
    found = rejected(output, "slot_missing", "factors")
    assert "G1, G2" in found[0]["excerpt"]


def test_non_dictionary_output_is_rejected_without_raising():
    for bad in (None, "texte", [], 3):
        result = validate(bad, brief())
        assert result["is_valid"] is False and codes(result) == {"slot_missing"}


def test_empty_object_reports_every_missing_field():
    result = validate({}, brief())
    assert {r["slot"] for r in result["rejections"]} >= set(ExplainerOutput.__annotations__)
    assert codes(result) <= {"slot_missing", "missing_rule_citation"}


# ---------- too_long ----------

def test_text_longer_than_max_is_rejected_per_slot():
    for slot in ("summary", "counterfactual", "variants", "limits_context"):
        too_long = "Mot " * 101                       # 404 caractères
        rejected(with_text(slot, too_long), "too_long", slot)
    output = good_output()
    output["factors"][0]["text"] = "La concentration [G1] [E1] " + "x" * 400
    rejected(output, "too_long", "factors[0]")


def test_length_boundary_is_inclusive():
    dossier = brief()
    dossier["max_chars_per_slot"] = 60
    exact = "a" * 60
    def too_long_slots(output):
        return {r["slot"] for r in validate(output, dossier)["rejections"] if r["code"] == "too_long"}

    assert "variants" not in too_long_slots(with_text("variants", exact))
    assert "variants" in too_long_slots(with_text("variants", exact + "a"))


def test_max_chars_comes_from_the_brief_with_default():
    dossier = brief()
    dossier["max_chars_per_slot"] = 30
    assert "too_long" in codes(validate(good_output(), dossier))
    del dossier["max_chars_per_slot"]
    assert "too_long" not in codes(validate(good_output(), dossier))
    assert "too_long" in codes(validate(with_text("variants", "a" * 401), dossier))


# ---------- compatibilité avec B3 et B4 ----------

def robert_result():
    return load("analysis_result_robert_tsla.json")


def variant_result():
    result = robert_result()
    result["evidence"]["E6"] = dict(result["evidence"]["E1"], evidence_id="E6", subject="variant:V1",
                                    evidence_key="top_asset_weight:variant:V1")
    check = copy.deepcopy(result["governance_after"]["checks"][0])
    check.update(status="compliant", evidence_ids=["E6"], counterfactual=None, margin=0.1)
    idea = dict(result["idea"], target_weight=0.1)
    result["variants"] = [{"variant_id": "V1", "reason_code": "reduce_weight", "idea": idea,
                           "snapshot": result["snapshot_after"],
                           "governance": {"profile_id": "robert", "subject": "variant:V1",
                                          "overall_status": "tension", "checks": [check]}}]
    return result


@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("make", [robert_result, lambda: load("analysis_result_amira_tsla.json"), variant_result])
def test_fallback_template_always_passes_the_validator(level, make):
    dossier = build_brief(make(), level)
    output = render_template(dossier)
    result = validate(output, dossier)
    assert result["is_valid"] is True, result["rejections"]
    assert validate(output, dossier, allow_registry_numbers=False)["is_valid"] is True   # aucun chiffre en clair


@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("status", ["conflict", "tension", "missing_info", "compliant"])
def test_fallback_passes_for_each_status(level, status):
    result = robert_result()
    for check in result["governance_after"]["checks"]:
        check["status"] = status
        if status == "missing_info":
            check.update(value=None, margin=None, missing_reason="Valeur indisponible.")
    dossier = build_brief(result, level)
    outcome = validate(render_template(dossier), dossier)
    assert outcome["is_valid"] is True, outcome["rejections"]


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_fallback_passes_with_counterfactual_and_small_slot_limit(level):
    result = robert_result()
    result["governance_after"]["checks"][0]["counterfactual"] = {
        "parameter": "target_weight", "compliant_at_or_below": 0.2, "display_value": "20 %"}
    dossier = build_brief(result, level)
    dossier["max_chars_per_slot"] = 240
    outcome = validate(render_template(dossier), dossier)
    assert outcome["is_valid"] is True, outcome["rejections"]


def test_tampering_with_a_template_output_is_caught():
    dossier = build_brief(robert_result(), "novice")
    output = render_template(dossier)
    tampered = copy.deepcopy(output)
    tampered["summary"] += " Le rendement sera de 12 % l'an prochain."
    assert {"number_outside_registry", "forbidden_term"} <= codes(validate(tampered, dossier))
    tampered = copy.deepcopy(output)
    tampered["factors"][0]["text"] = tampered["factors"][0]["text"].replace("[E1]", "[E9]")
    assert "unknown_reference" in codes(validate(tampered, dossier))
    tampered = copy.deepcopy(output)
    tampered["summary"] = "Résumé sans aucun renvoi."
    tampered["factors"] = [{"check_id": f["check_id"], "text": "Sans renvoi."} for f in tampered["factors"]]
    tampered["counterfactual"] = "Sans renvoi."
    assert "missing_rule_citation" in codes(validate(tampered, dossier))


def test_module_has_no_network_or_model_dependency():
    source = Path(explanation_validator.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(boto3|botocore|requests|urllib|anthropic)", source, re.M)
    assert "\u2014" not in source
