"""Tests de `render_sections` (PR-4) : l'explication découpée en sections, sans rien ajouter.

Chiffres des fixtures, aucun appel AWS. Deux garanties :
1. `render_markdown` rend exactement le même texte qu'avant l'ajout de `render_sections`
   (empreintes des rendus de référence, calculées avant le changement) ;
2. chaque section structurée reprend ce que le Markdown contient, sans texte ni chiffre de plus.
"""
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import (  # noqa: E402
    RenderedSections, render_markdown, render_sections,
)
from alphaforge.reference_texts import disclaimers, mandatory_limits, threshold_assumption  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

# SHA-256 de render_markdown sur les fixtures de Robert, calculé AVANT l'ajout de render_sections.
# Un changement volontaire du rendu Markdown doit mettre ces empreintes à jour.
MARKDOWN_SNAPSHOTS = {
    "novice": "e4451de6a0c31d243775526ea2efbc46189153187e7614891cb35558eedd91fe",
    "pro": "26c62881a03a8790f777d2ff1bd0b630a71f7bb7621370ac5d1f285c58d59929",
}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def case(level):
    output = load(f"explainer_output_robert_{level}.json")
    brief = load("explanation_brief_robert_novice.json")
    brief["level"] = output["level"]
    return output, brief


def citing_term(output):
    """Même sortie avec un renvoi au glossaire en fin de résumé (la fixture n'en cite aucun)."""
    return {**output, "summary": output["summary"].rstrip() + " Voir [T1]."}


def with_context(brief, **overrides):
    brief = copy.deepcopy(brief)
    context = {"objective": "Préserver le capital", "horizon_years_min": 3, "horizon_years_max": 5,
               "risk_tolerance": "low_moderate", "risk_tolerance_fr": "faible à modérée",
               "esg_preference": "none", "esg_preference_fr": "aucune", "crypto_allowed": False}
    context.update(overrides)
    brief["profile_context"] = context
    return brief


# --- render_markdown inchangé -----------------------------------------------------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_render_markdown_is_unchanged(level):
    output, brief = case(level)
    digest = hashlib.sha256(render_markdown(output, brief).encode()).hexdigest()
    assert digest == MARKDOWN_SNAPSHOTS[level]


def test_render_sections_does_not_mutate_inputs():
    output, brief = case("novice")
    output, brief = copy.deepcopy(output), with_context(brief)
    snapshot = copy.deepcopy((output, brief))
    render_sections(output, brief)
    assert (output, brief) == snapshot


def test_render_sections_leaves_markdown_unchanged_when_called_before():
    output, brief = case("pro")
    render_sections(output, brief)
    digest = hashlib.sha256(render_markdown(output, brief).encode()).hexdigest()
    assert digest == MARKDOWN_SNAPSHOTS["pro"]


# --- Les sections reprennent le Markdown -----------------------------------------------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_every_section_text_appears_in_markdown(level):
    output, brief = case(level)
    brief = with_context(brief)
    sections = render_sections(output, brief)
    markdown = render_markdown(output, brief)
    assert isinstance(sections, RenderedSections) and sections.level == level
    for text in (sections.summary, sections.counterfactual, sections.variants, sections.limits_context,
                 sections.idea_line, *[f.text for f in sections.factors],
                 *[f"- {i.label} : {i.text}" for i in sections.counterfactual_items],
                 *[t for _, t in sections.disclaimers], *[t for _, t in sections.limits]):
        assert text and text in markdown


def test_evidence_and_glossary_match_markdown_sections():
    output, brief = case("novice")
    output = citing_term(output)
    sections = render_sections(output, brief)
    markdown = render_markdown(output, brief)
    cited = re.findall(r"^- \*\*(E\d+)\*\* :", markdown, flags=re.M)
    assert [item.evidence_id for item in sections.evidence] == cited
    terms = re.findall(r"^- \*\*([^*]+)\*\* : .*$", markdown.split("## Glossaire")[1], flags=re.M)
    assert [g.term for g in sections.glossary] == terms


def test_check_rows_match_governance_checks():
    output, brief = case("novice")
    sections = render_sections(output, brief)
    assert [r.check_id for r in sections.check_rows] == [c["check_id"] for c in brief["checks"]]
    for row, check in zip(sections.check_rows, brief["checks"]):
        assert row.status == check["status"] and row.label == check["label_fr"]
    assert sections.check_rows[0].status_fr == "en conflit"
    assert sections.check_rows[0].value_text.endswith("%")


# --- Novice et pro ----------------------------------------------------------------

def test_pro_adds_technical_details_novice_does_not():
    (novice_output, novice_brief), (pro_output, pro_brief) = case("novice"), case("pro")
    novice = render_sections(citing_term(novice_output), novice_brief)
    pro = render_sections(citing_term(pro_output), pro_brief)
    assert not any("outil" in d for item in novice.evidence for d in item.details)
    assert any(d.startswith("outil ") for item in pro.evidence for d in item.details)
    assert any(item.analogy for item in novice.glossary)
    assert not any(item.analogy for item in pro.glossary)
    assert novice.disclaimers != pro.disclaimers
    assert novice.threshold_notice == threshold_assumption("novice")
    assert pro.threshold_notice == threshold_assumption("pro")


def test_level_falls_back_to_the_brief_level():
    output, brief = case("novice")
    output = {**output, "level": None}
    brief["level"] = "pro"
    assert render_sections(output, brief).level == "pro"


# --- Gabarit de secours et modèle -------------------------------------------------

def test_origin_distinguishes_template_from_model():
    output, brief = case("novice")
    assert render_sections(output, brief).origin == "template"
    assert render_sections({**output, "origin": "llm", "model_id": "m"}, brief).origin == "llm"


def test_template_fallback_output_gives_full_sections():
    _, brief = case("novice")
    output = render_template(brief)
    sections = render_sections(output, brief)
    assert sections.origin == "template"
    assert sections.summary and sections.factors and sections.check_rows
    assert render_markdown(output, brief)  # le même gabarit reste rendu en Markdown


# --- Avertissements et limites, une fois -----------------------------------------------

def test_fixed_warnings_and_mandatory_limits_come_once():
    output, brief = case("novice")
    sections = render_sections(output, brief)
    assert [t for _, t in sections.disclaimers] == [d["text"] for d in disclaimers("novice")]
    assert len({t for _, t in sections.disclaimers}) == len(sections.disclaimers)
    ids = [limit_id for limit_id, _ in sections.limits]
    assert len(ids) == len(set(ids))
    assert [t for _, t in sections.limits][:5] == [m["text"] for m in mandatory_limits("novice")]
    assert not {t for _, t in sections.disclaimers} & {t for _, t in sections.limits}


def test_mandatory_limits_are_present_even_if_brief_has_none():
    output, brief = case("novice")
    brief["limits"] = []
    assert len(render_sections(output, brief).limits) == len(mandatory_limits("novice"))


# --- Contexte du profil ---------------------------------------------------------------

def test_profile_context_items_come_from_the_brief():
    output, brief = case("novice")
    sections = render_sections(output, with_context(brief))
    items = dict(sections.profile_context.items)
    assert items["Objectif"] == "Préserver le capital"
    assert items["Horizon d'investissement"] == "de 3 à 5 ans"
    assert items["Tolérance au risque"] == "faible à modérée"
    assert items["Cryptoactifs"] == "non permis"
    assert "Expérience" not in items


def test_pro_profile_context_shows_raw_values():
    output, brief = case("pro")
    sections = render_sections(output, with_context(brief))
    assert dict(sections.profile_context.items)["Tolérance au risque"] == "faible à modérée (`low_moderate`)"


def test_profile_context_absent_when_brief_has_none():
    output, brief = case("novice")
    assert render_sections(output, brief).profile_context is None


def test_profile_context_skips_unsafe_objective():
    output, brief = case("novice")
    sections = render_sections(output, with_context(brief, objective="voir <script>x</script>"))
    assert "Objectif" not in dict(sections.profile_context.items)


# --- Contrefactuels calculés ---------------------------------------------------------

def test_counterfactual_items_come_from_governance():
    output, brief = case("novice")
    sections = render_sections(output, brief)
    (item,) = sections.counterfactual_items
    check = next(c for c in brief["checks"] if c["check_id"] == item.check_id)
    assert item.bound == check["counterfactual"]["compliant_at_or_below"]
    assert item.text.startswith("le plus grand poids testé conforme à cette règle est ")
    assert check["counterfactual"]["display_value"] in item.text


def test_counterfactual_with_no_compliant_weight():
    output, brief = case("novice")
    brief["checks"][0]["counterfactual"] = {"parameter": "target_weight", "compliant_at_or_below": None,
                                            "display_value": ""}
    (item,) = render_sections(output, brief).counterfactual_items
    assert item.bound is None and item.text == "aucun poids testé n'est conforme à cette règle."


def test_counterfactual_ignored_for_compliant_checks():
    output, brief = case("novice")
    brief["checks"][3]["counterfactual"] = {"parameter": "target_weight", "compliant_at_or_below": 0.5,
                                            "display_value": "50 %"}
    ids = [i.check_id for i in render_sections(output, brief).counterfactual_items]
    assert "G4" not in ids


def test_counterfactual_items_empty_without_counterfactual_text():
    output, brief = case("novice")
    output = {**output, "counterfactual": ""}
    assert render_sections(output, brief).counterfactual_items == ()


# --- Données manquantes --------------------------------------------------------------

def test_empty_slots_give_empty_sections_not_errors():
    output, brief = case("novice")
    for slot in ("summary", "counterfactual", "variants", "limits_context"):
        output[slot] = ""
    output["factors"] = []
    brief.update(checks=[], evidence=[], glossary=[], idea=None)
    sections = render_sections(output, brief)
    assert sections.summary == "" and sections.factors == () and sections.variants == ""
    assert sections.check_rows == () and sections.check_notes == () and sections.threshold_notice is None
    assert sections.evidence == () and sections.glossary == () and sections.idea_line is None
    assert sections.limits  # les limites obligatoires restent
    assert sections.disclaimers


def test_unknown_reference_is_flagged_not_guessed():
    output, brief = case("novice")
    output["summary"] = "La mesure vaut [E999]."
    assert "[référence inconnue : E999]" in render_sections(output, brief).summary


def test_missing_evidence_value_is_information_manquante():
    output, brief = case("novice")
    brief["evidence"][0]["value"] = None
    output["summary"] = "Le poids est [E1]."
    sections = render_sections(output, brief)
    assert sections.summary == "Le poids est information manquante."
    assert next(e for e in sections.evidence if e.evidence_id == "E1").value_text == "information manquante"


def test_missing_value_check_row_says_information_manquante():
    output, brief = case("novice")
    brief["checks"][1].update(value=None, status="missing_info", missing_reason="Données insuffisantes.")
    sections = render_sections(output, brief)
    assert sections.check_rows[1].value_text == "information manquante"
    assert sections.check_notes == ((brief["checks"][1]["label_fr"], "Données insuffisantes."),)


def test_factor_status_comes_from_the_brief():
    output, brief = case("novice")
    sections = render_sections(output, brief)
    statuses = {c["check_id"]: c["status"] for c in brief["checks"]}
    for factor in sections.factors:
        if factor.check_id in statuses:
            assert factor.status == statuses[factor.check_id]
    unknown = copy.deepcopy(output)
    unknown["factors"] = [{"check_id": "G99", "text": "Texte."}]
    (factor,) = render_sections(unknown, brief).factors
    assert factor.status is None and factor.label is None
