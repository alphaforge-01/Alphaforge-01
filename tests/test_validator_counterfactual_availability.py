"""Tests P0-5 : le validateur rejette un contrefactuel déclaré indisponible alors qu'il est calculé.

Données fictives ou traces de démonstration versionnées, aucun appel AWS.
"""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge.contracts import ValidationResult, check_keys  # noqa: E402
from alphaforge.explanation_brief import build_brief  # noqa: E402
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_validator import validate  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
TRACES = ROOT / "outputs" / "reports" / "demo_traces"
CODES = {"unknown_reference", "number_outside_registry", "forbidden_term", "missing_rule_citation",
         "slot_missing", "too_long"}

# Texte fautif de la trace robert_explanation_pro.json (renvois restaurés à la place des libellés).
TRACE_FAULTY = ("Avec un poids cible de TSLA plus bas, propre à chaque règle, les contrôles [G1], [G2] et [G3] "
                "seraient respectés ; ces poids ne sont pas disponibles parmi les preuves.")

UNAVAILABLE_TEXTS = [
    TRACE_FAULTY,
    "Ces poids ne sont pas disponibles.",
    "Les poids ne sont pas disponibles parmi les preuves.",
    "Le poids cible n'est pas disponible.",
    "Le poids n’est pas disponible.",                     # apostrophe typographique
    "LE POIDS N'EST PAS DISPONIBLE.",
    "Les poids sont indisponibles.",
    "Le poids conforme est indisponible.",
    "Poids non calculés pour ces règles.",
    "Le poids n'est pas calculé.",
    "Les poids ne sont pas encore calculés.",
    "Le poids n'a pas été calculé.",
    "Le poids n'a pas pu être déterminé.",
    "Les poids ne peuvent pas être calculés.",
    "Il est impossible de calculer le poids conforme.",
    "Le poids conforme est impossible à déterminer.",
    "On ne peut pas calculer le poids conforme.",
    "Nous ne pouvons pas déterminer ce poids.",
    "Le contrefactuel n'est pas disponible.",
    "Le contrefactuel est indisponible.",
    "Le contrefactuel n'a pas été calculé.",
    "Le contrefactuel est non calculé.",
    "Aucun contrefactuel n'est disponible.",
    "Pas de contrefactuel pour cette règle.",
    "La règle est sans contrefactuel.",
    "Le dossier ne donne pas le poids.",
    "Le dossier n'indique pas de poids cible.",
    "Le dossier ne fournit pas ces poids.",
    "Les poids ne figurent pas parmi les preuves.",
    "Ces poids n'apparaissent pas dans le dossier.",
    "Ces poids sont absents du dossier.",
    "Les poids sont manquants.",
    "Les poids sont inconnus.",
    "Aucune information sur le poids.",
    "Aucune valeur pour le poids conforme.",
    "Un poids plus bas rendrait les règles conformes. Ces poids ne sont pas disponibles.",
    "Pour [G1], le poids n'est pas disponible.",
]

ACCEPTED_TEXTS = [
    "Un poids cible plus bas, détaillé juste en dessous, rendrait conformes les règles [G1], [G2] et [G3].",
    "Avec un poids de TSLA plus bas, la règle [G1] serait respectée.",
    "Le dossier indique un poids cible plus bas.",
    "Aucun poids testé n'est conforme à cette règle.",
    "Aucun poids cible testé ne rend [G1] conforme.",
    "Aucun poids conforme n'a été trouvé pour [G1].",
    "Un poids plus bas rendrait [G1] conforme, mais [G2] reste en tension.",
    "Le poids de TSLA atteint la limite de la règle [G1].",
    "Le plus grand poids testé conforme est donné ci-dessous.",
    "Seule la marge au seuil est disponible pour [G3].",
    "Les poids détaillés ci-dessous sont disponibles pour chaque règle.",
    "La règle [G1] n'est pas conforme au poids actuel.",
    "Le dossier ne donne pas d'autre information sur la règle [G1].",
    "Ces résultats ne sont pas des mesures de risque complètes.",
    "Une information manquante empêche tout verdict sur [G3].",
]


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def robert_brief(level="pro", **checks_changes):
    """Dossier de Robert (G1 conflit 20 %, G2 tension 21 %, G3 tension 17 %), contrefactuels calculés."""
    result = load("analysis_result_robert_tsla.json")
    result["profile"] = load_personas()["robert"]["profile"]
    cf = lambda display, bound: {"parameter": "target_weight", "compliant_at_or_below": bound,  # noqa: E731
                                 "display_value": display}
    for check in result["governance_after"]["checks"]:
        check["counterfactual"] = {"G1": cf("20 %", 0.20), "G2": cf("21 %", 0.21), "G3": cf("17 %", 0.17)}.get(
            check["check_id"])
    brief = build_brief(result, level)
    brief["max_chars_per_slot"] = 1000
    for check in brief["checks"]:
        if check["check_id"] in checks_changes:
            check["counterfactual"] = checks_changes[check["check_id"]]
    return brief


def with_counterfactual(brief, text):
    output = copy.deepcopy(render_template(brief))
    output["counterfactual"] = text
    return output


def availability_rejections(result):
    return [r for r in result["rejections"] if r["slot"] == "counterfactual" and r["code"] == "forbidden_term"]


def no_counterfactual(brief):
    for check in brief["checks"]:
        check["counterfactual"] = None
    return brief


# ---------- le dossier : un contrefactuel disponible ----------

def test_brief_carries_computed_counterfactuals_on_flagged_checks():
    brief = robert_brief()
    computed = {c["check_id"]: c["counterfactual"]["display_value"] for c in brief["checks"] if c["counterfactual"]}
    assert computed == {"G1": "20 %", "G2": "21 %", "G3": "17 %"}
    assert all(set(c["counterfactual"]) == {"parameter", "compliant_at_or_below", "display_value"}
               for c in brief["checks"] if c["counterfactual"])


# ---------- rejet quand le contrefactuel est calculé ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("text", UNAVAILABLE_TEXTS)
def test_unavailable_wording_is_rejected_when_a_counterfactual_is_computed(text, level):
    brief = robert_brief(level)
    result = validate(with_counterfactual(brief, text), brief)
    found = availability_rejections(result)
    assert found, text
    assert result["is_valid"] is False and all(r["code"] == "forbidden_term" and r["excerpt"] for r in found)


@pytest.mark.parametrize("text", UNAVAILABLE_TEXTS)
def test_unavailable_wording_is_also_rejected_in_strict_mode(text):
    brief = robert_brief()
    assert availability_rejections(validate(with_counterfactual(brief, text), brief, allow_registry_numbers=False))


def test_rejection_uses_existing_contract_codes_and_shape():
    brief = robert_brief()
    result = validate(with_counterfactual(brief, TRACE_FAULTY), brief)
    assert check_keys(result, ValidationResult) == [] and set(result) == {"is_valid", "rejections", "checked_references"}
    assert {r["code"] for r in result["rejections"]} <= CODES
    assert all(set(r) == {"code", "slot", "excerpt"} for r in result["rejections"])
    (rejection,) = availability_rejections(result)
    assert "pas disponibles" in rejection["excerpt"] and len(rejection["excerpt"]) <= 80


@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("text", ACCEPTED_TEXTS)
def test_legitimate_counterfactual_wording_is_never_flagged(text, level):
    brief = robert_brief(level)
    assert availability_rejections(validate(with_counterfactual(brief, text), brief)) == [], text


# ---------- deux sens de None, et aucun poids conforme ----------

def test_no_rejection_when_the_counterfactual_is_none_because_simulation_is_unavailable():
    brief = no_counterfactual(robert_brief())
    for text in UNAVAILABLE_TEXTS:
        assert availability_rejections(validate(with_counterfactual(brief, text), brief)) == [], text


def test_no_compliant_weight_is_a_computed_result_so_unavailable_wording_is_rejected():
    none_bound = {"parameter": "target_weight", "compliant_at_or_below": None, "display_value": "aucun poids conforme"}
    brief = no_counterfactual(robert_brief())
    brief["checks"][0]["counterfactual"] = none_bound
    assert availability_rejections(validate(with_counterfactual(brief, "Ces poids ne sont pas calculés."), brief))
    for text in ("Aucun poids testé n'est conforme à cette règle.", "Aucun poids cible testé ne rend [G1] conforme.",
                 "Aucun poids conforme n'a été trouvé pour [G1]."):
        assert availability_rejections(validate(with_counterfactual(brief, text), brief)) == [], text


def test_the_two_meanings_of_none_give_opposite_verdicts_on_the_same_sentence():
    sentence = "Pour [G1], le poids n'est pas calculé."
    computed = robert_brief()
    simulation_down = no_counterfactual(robert_brief())
    no_weight = no_counterfactual(robert_brief())
    no_weight["checks"][0]["counterfactual"] = {"parameter": "target_weight", "compliant_at_or_below": None,
                                                "display_value": "aucun poids conforme"}
    assert availability_rejections(validate(with_counterfactual(computed, sentence), computed))
    assert availability_rejections(validate(with_counterfactual(simulation_down, sentence), simulation_down)) == []
    assert availability_rejections(validate(with_counterfactual(no_weight, sentence), no_weight))


@pytest.mark.parametrize("bad", [{}, {"parameter": "target_weight"}, {"compliant_at_or_below": "20 %"},
                                 {"compliant_at_or_below": True}, "20 %", 0.2, []])
def test_malformed_counterfactual_is_not_treated_as_computed(bad):
    brief = no_counterfactual(robert_brief())
    brief["checks"][0]["counterfactual"] = bad
    assert availability_rejections(validate(with_counterfactual(brief, "Le poids n'est pas disponible."), brief)) == []


def test_counterfactual_on_a_compliant_check_is_not_displayed_so_it_does_not_count():
    brief = no_counterfactual(robert_brief())
    brief["checks"][3]["counterfactual"] = {"parameter": "target_weight", "compliant_at_or_below": 0.4,
                                            "display_value": "40 %"}
    assert brief["checks"][3]["status"] == "compliant"
    assert availability_rejections(validate(with_counterfactual(brief, "Le poids n'est pas disponible."), brief)) == []


# ---------- contrôles avec et sans contrefactuel dans le même dossier ----------

def mixed_brief():
    return robert_brief(G2=None, G3=None)       # seul G1 a un contrefactuel calculé


def test_clause_about_checks_without_counterfactual_may_say_the_weight_is_missing():
    brief = mixed_brief()
    for text in ("Pour [G2], le poids n'est pas disponible.", "Pour [G2] et [G3], les poids ne sont pas calculés.",
                 "Un poids plus bas rendrait [G1] conforme ; pour [G2], le poids n'est pas disponible."):
        assert availability_rejections(validate(with_counterfactual(brief, text), brief)) == [], text


def test_clause_about_a_check_with_counterfactual_is_rejected_even_next_to_others():
    brief = mixed_brief()
    for text in ("Pour [G1], le poids n'est pas disponible.", "Pour [G1] et [G2], les poids ne sont pas calculés.",
                 "Pour [G2], seule la marge est connue ; pour [G1], le poids n'est pas disponible."):
        assert availability_rejections(validate(with_counterfactual(brief, text), brief)), text


def test_clause_without_reference_is_rejected_as_soon_as_one_counterfactual_exists():
    brief = mixed_brief()
    assert availability_rejections(validate(with_counterfactual(brief, "Ces poids ne sont pas disponibles."), brief))


def test_unknown_reference_does_not_count_as_a_check_with_counterfactual():
    brief = mixed_brief()
    text = "Pour [G99], le poids n'est pas disponible."
    result = validate(with_counterfactual(brief, text), brief)
    assert availability_rejections(result) == [] and any(r["code"] == "unknown_reference" for r in result["rejections"])


def test_esg_missing_info_sentence_is_not_a_false_alarm():
    """Mateo : un poids plus bas rend la concentration conforme, mais la règle ESG reste sans preuve."""
    brief = robert_brief()
    text = "Un poids plus bas rendrait [G1] conforme, mais [G7] reste en information manquante."
    assert availability_rejections(validate(with_counterfactual(brief, text), brief)) == []


# ---------- seul l'emplacement contrefactuel est concerné ----------

@pytest.mark.parametrize("slot", ["summary", "variants", "limits_context"])
def test_other_slots_are_not_subject_to_this_rule(slot):
    brief = robert_brief()
    output = copy.deepcopy(render_template(brief))
    output[slot] = "Les poids ne sont pas disponibles ailleurs que dans cet emplacement."
    assert availability_rejections(validate(output, brief)) == []


def test_factor_text_is_not_subject_to_this_rule():
    brief = robert_brief()
    output = copy.deepcopy(render_template(brief))
    output["factors"][0]["text"] = "Le poids n'est pas disponible [G1]."
    assert availability_rejections(validate(output, brief)) == []


# ---------- gabarits : aucune fausse alerte ----------

@pytest.mark.parametrize("persona_id", ["robert", "amira", "mateo"])
@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("idea", [("TSLA", 0.25), ("BTC-USD", 0.20), ("NVDA", 0.20), ("XOM", 0.10)])
def test_real_templates_pass_with_real_counterfactuals(persona_id, level, idea):
    from alphaforge.analysis_pipeline import run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    persona = load_personas()[persona_id]
    request = {"ticker": idea[0], "target_weight": idea[1], "funding_source": "pro_rata", "funding_ticker": None}
    result = run_analysis(persona["profile"], persona["portfolio"], request, mode="offline", config=BedrockConfig())
    brief = build_brief(result, level)
    output = render_template(brief)
    outcome = validate(output, brief)
    assert outcome["is_valid"] is True, outcome["rejections"]
    assert availability_rejections(validate(output, brief, allow_registry_numbers=False)) == []


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_template_passes_for_every_mix_of_computed_and_missing_counterfactuals(level):
    for keep in ((), ("G1",), ("G2", "G3"), ("G1", "G2", "G3")):
        brief = no_counterfactual(robert_brief(level))
        full = robert_brief(level)
        for check, source in zip(brief["checks"], full["checks"]):
            if check["check_id"] in keep:
                check["counterfactual"] = source["counterfactual"]
        output = render_template(brief)
        assert validate(output, brief)["is_valid"] is True, keep


def test_old_fixture_brief_and_valid_outputs_are_unaffected():
    brief = load("explanation_brief_robert_novice.json")
    for name in ("explainer_output_robert_novice.json", "explainer_output_robert_pro.json"):
        assert validate(load(name), brief)["is_valid"] is True
    assert validate(load("explainer_output_invalid.json"), brief)["is_valid"] is False


# ---------- traces de démonstration ----------

def trace_case(name, level):
    document = json.loads((TRACES / name).read_text(encoding="utf-8"))
    brief = build_brief(document["analysis"], level)
    brief["max_chars_per_slot"] = 1000
    markdown = document["explanation"]["rendered_markdown"]
    match = re.search(r"## Ce qui ferait changer le verdict\n\n(.*?)(?=\n- |\n## )", markdown, re.DOTALL)
    return brief, match.group(1).replace("**", "").strip()


def test_faulty_text_of_the_robert_pro_trace_is_now_rejected():
    brief, paragraph = trace_case("robert_explanation_pro.json", "pro")
    assert "ne sont pas disponibles parmi les preuves" in paragraph
    assert availability_rejections(validate(with_counterfactual(brief, paragraph), brief))
    assert availability_rejections(validate(with_counterfactual(brief, TRACE_FAULTY), brief))


@pytest.mark.parametrize("name,level", [("robert_explanation_novice.json", "novice"),
                                        ("amira_explanation_novice.json", "novice"),
                                        ("amira_explanation_pro.json", "pro")])
def test_good_model_texts_of_the_other_traces_are_not_flagged(name, level):
    brief, paragraph = trace_case(name, level)
    assert any(c["counterfactual"] for c in brief["checks"])
    assert availability_rejections(validate(with_counterfactual(brief, paragraph), brief)) == []


def test_trace_briefs_have_computed_counterfactuals_matching_the_displayed_weights():
    brief, _ = trace_case("robert_explanation_pro.json", "pro")
    markdown = json.loads((TRACES / "robert_explanation_pro.json").read_text(encoding="utf-8"))[
        "explanation"]["rendered_markdown"]
    for check in brief["checks"]:
        if check["counterfactual"]:
            assert f"{check['label_fr']} : le plus grand poids testé conforme à cette règle est " \
                   f"{check['counterfactual']['display_value']}." in markdown


# ---------- intégration avec le pipeline du flux C (lecture seule) ----------

def test_rejection_is_repairable_by_the_pipeline_without_discarding_the_whole_text():
    from alphaforge.analysis_pipeline import _repair_slots
    brief = robert_brief()
    template = render_template(brief)
    output = with_counterfactual(brief, TRACE_FAULTY)
    rejections = validate(output, brief)["rejections"]
    repaired, slots = _repair_slots(output, template, rejections)
    assert slots == ["counterfactual"] and repaired["counterfactual"] == template["counterfactual"]
    assert repaired["summary"] == output["summary"]
    assert validate(repaired, brief)["is_valid"] is True


def test_validator_stays_free_of_network_and_model_dependencies():
    from alphaforge import explanation_validator
    source = Path(explanation_validator.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(boto3|botocore|requests|urllib|anthropic)", source, re.M)
    assert "\u2014" not in source
