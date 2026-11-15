"""Tests B3 : rendu Markdown. Chiffres inventés, aucun appel AWS."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import (  # noqa: E402
    REFERENCE_PATTERN, format_percent, format_points, render_markdown,
)
from alphaforge.governance import evaluate  # noqa: E402
from alphaforge.reference_texts import disclaimers, mandatory_limits  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_brief(level="novice"):
    brief = copy.deepcopy(load("explanation_brief_robert_novice.json"))
    brief["level"] = level
    return brief


def rendered(level="novice"):
    brief = make_brief(level)
    return render_markdown(render_template(brief), brief)


def output_with(**slots):
    base = {"brief_id": "x", "level": "novice", "summary": "", "factors": [], "counterfactual": "",
            "variants": "", "limits_context": "", "origin": "template", "model_id": None,
            "prompt_version": None, "attempt": 0}
    base.update(slots)
    return base


# ---------- formats ----------

@pytest.mark.parametrize("value,expected", [
    (0.25, "25 %"), (0.4125, "41,25 %"), (0.0, "0 %"), (1.0, "100 %"), (0.0125, "1,25 %"),
    (-0.000001, "0 %"), (-0.0001, "-0,01 %"), (0.2, "20 %"), (0.123456, "12,35 %"),
])
def test_format_percent(value, expected):
    assert format_percent(value) == expected


@pytest.mark.parametrize("value,expected", [(-0.03, "-3 pts"), (0.0125, "1,25 pts"), (0.0, "0 pts")])
def test_format_points(value, expected):
    assert format_points(value) == expected


# ---------- remplacement des renvois ----------

@pytest.mark.parametrize("level", ["novice", "pro"])
def test_no_reference_left_after_rendering(level):
    text = rendered(level)
    assert not REFERENCE_PATTERN.search(text)
    assert "référence inconnue" not in text


def test_evidence_reference_becomes_registry_display_value():
    brief = make_brief()
    text = render_markdown(output_with(summary="Le poids atteint [E1], la part défensive [E4]."), brief)
    assert "Le poids atteint 25 %, la part défensive 41,25 %." in text


def test_check_reference_becomes_label_and_governance_status():
    brief = make_brief()
    text = render_markdown(output_with(summary="[G1] puis [G2] puis [G4]"), brief)
    assert "**Concentration par actif** (en conflit)" in text
    assert "**Volatilité annuelle** (en tension)" in text
    assert "**Part défensive minimale** (conforme)" in text


def test_term_reference_becomes_glossary_term_and_listed():
    text = render_markdown(output_with(summary="Voir [T1]."), make_brief("novice"))
    assert "Voir **Volatilité**." in text
    assert "## Glossaire" in text and "Des hauts et des bas" in text


def test_unknown_references_are_flagged_not_guessed():
    text = render_markdown(output_with(summary="[E99] [G99] [T99]"), make_brief())
    assert text.count("référence inconnue") == 3
    assert "[référence inconnue : E99]" in text


def test_missing_value_evidence_renders_missing_info():
    brief = make_brief()
    brief["evidence"][0]["value"] = None
    brief["evidence"][0]["display_value"] = ""
    text = render_markdown(output_with(summary="Valeur [E1]."), brief)
    assert "Valeur information manquante." in text


def test_missing_info_check_in_details_with_reason():
    brief = make_brief("pro")
    brief["checks"][1].update(status="missing_info", value=None, margin=None,
                              missing_reason="Valeur indisponible dans l'instantané : volatility_ann.")
    text = render_markdown(render_template(brief), brief)
    row = next(line for line in text.splitlines() if line.startswith("| G2"))
    assert "information manquante" in row
    assert "Valeur indisponible dans l'instantané : volatility_ann." in text
    assert "(information manquante)" in text


# ---------- éléments factuels ajoutés par le code ----------

def test_disclaimer_idea_and_limits_are_always_shown():
    for level in ("novice", "pro"):
        text = rendered(level)
        for item in disclaimers(level):
            assert item["text"] in text
        assert "Idée simulée : « TSLA », poids cible 25 %" in text
        assert "**L1** : Données d’essai inventées" in text
        assert "pas des normes" in text


def test_idea_funding_from_ticker():
    brief = make_brief()
    brief["idea"].update(funding_source="from_ticker", funding_ticker="SPY")
    assert "financé par « SPY »" in render_markdown(render_template(brief), brief)


def test_counterfactual_value_comes_from_governance_check():
    text = rendered("novice")
    assert "Concentration par actif : le plus grand poids testé conforme à cette règle est 22 %." in text


def test_counterfactual_none_means_no_compliant_weight():
    brief = make_brief()
    brief["checks"][0]["counterfactual"] = {"parameter": "target_weight",
                                            "compliant_at_or_below": None, "display_value": "aucun"}
    assert "aucun poids testé n'est conforme à cette règle" in render_markdown(render_template(brief), brief)


def test_details_table_matches_checks():
    brief = make_brief("pro")
    text = render_markdown(render_template(brief), brief)
    for check in brief["checks"]:
        row = next(line for line in text.splitlines() if line.startswith(f"| {check['check_id']} "))
        assert {"conflict": "en conflit", "tension": "en tension", "compliant": "conforme"}[check["status"]] in row
        assert check["rule_id"] in row
    g1 = next(line for line in text.splitlines() if line.startswith("| G1 "))
    assert "25 %" in g1 and "20 %" in g1 and "22 %" in g1 and "-3 pts" in g1


def test_evidence_section_has_source_period_currency_transformation():
    text = rendered("novice")
    section = text.split("## Preuves citées")[1]
    for expected in ("**E1**", "période 2021-11-12 au 2026-11-12", "devise CAD", "prices_daily.csv",
                     "transformation"):
        assert expected in section
    assert "**E5**" not in section   # preuve jamais citée


def test_pro_evidence_has_method_details_novice_does_not():
    novice = rendered("novice").split("## Preuves citées")[1]
    pro = rendered("pro").split("## Preuves citées")[1]
    assert "1000 observations" in pro and "analyze_portfolio" in pro and "limites L1" in pro
    assert "1000 observations" not in novice and "analyze_portfolio" not in novice


# ---------- niveaux ----------

def test_numbers_identical_across_levels_but_text_differs():
    novice, pro = rendered("novice"), rendered("pro")
    assert novice != pro
    for number in ("25 %", "21 %", "29 %", "41,25 %", "22 %"):
        assert number in novice and number in pro, number
    for status in ("en conflit", "en tension"):
        assert status in novice and status in pro
    assert "Niveau pro" not in novice and "niveau pro" in pro and "niveau novice" in novice


def test_pro_has_technical_columns_novice_has_simple_columns():
    assert "Seuil d'avertissement" in rendered("pro") and "Marge" in rendered("pro")
    assert "Seuil d'avertissement" not in rendered("novice")
    assert "max_single_asset_weight" in rendered("pro")
    assert "max_single_asset_weight" not in rendered("novice")


# ---------- fixtures existantes et gouvernance ----------

@pytest.mark.parametrize("name", ["explainer_output_robert_novice.json", "explainer_output_robert_pro.json"])
def test_b0_explainer_fixtures_render(name):
    brief = make_brief()
    text = render_markdown(load(name), brief)
    assert "référence inconnue" not in text and not REFERENCE_PATTERN.search(text)
    assert "25 %" in text


def test_invalid_fixture_renders_without_crashing():
    text = render_markdown(load("explainer_output_invalid.json"), make_brief())
    assert "99 %" in text   # le rendu ne corrige pas : c'est le rôle du validateur (B6)


def test_rendered_statuses_match_governance_evaluate():
    data = load("analysis_result_robert_tsla.json")
    result = evaluate(data["profile"], data["snapshot_after"], evidence=data["evidence"])
    brief = make_brief("pro")
    brief["checks"] = result["checks"]
    brief["ranked_factors"] = [{"rank": i, "check_id": c["check_id"], "status": c["status"],
                                "evidence_ids": c["evidence_ids"]}
                               for i, c in enumerate(result["checks"], start=1)]
    brief["profile_rules"] = data["profile"]["rules"]
    text = render_markdown(render_template(brief), brief)
    labels = {"conflict": "en conflit", "tension": "en tension", "compliant": "conforme",
              "missing_info": "information manquante"}
    for check in result["checks"]:
        row = next(line for line in text.splitlines() if line.startswith(f"| {check['check_id']} "))
        assert labels[check["status"]] in row


# ---------- robustesse ----------

def test_missing_slots_are_skipped():
    text = render_markdown(output_with(), make_brief())
    assert "## Résumé" not in text and "## Ce qui pèse" not in text
    assert all(item["text"] in text for item in disclaimers("novice"))


def test_deterministic_no_mutation_and_ascii_punctuation():
    brief = make_brief("pro")
    output = render_template(brief)
    before = copy.deepcopy((brief, output))
    first = render_markdown(output, brief)
    assert first == render_markdown(output, brief)
    assert (brief, output) == before
    assert "\u2014" not in first
    assert first.endswith("\n") and not first.endswith("\n\n")


def test_pipe_in_text_does_not_break_table():
    brief = make_brief()
    brief["checks"][0]["label_fr"] = "Règle | piégée"
    text = render_markdown(render_template(brief), brief)
    row = next(line for line in text.splitlines() if line.startswith("| Règle / piégée"))
    assert row.count("|") == 5


def test_numbers_in_rendering_come_from_registry_checks_or_idea():
    """Tout nombre du rendu vient du registre, des contrôles, de l'idée ou des textes fixes."""
    text = rendered("novice")
    numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:,\d+)?", text))
    allowed = {"25", "21", "29", "41,25", "22", "20", "35", "30", "2021", "11", "12", "2026", "1", "2"}  # "1" et "2" : numérotation des facteurs
    assert numbers <= allowed, numbers - allowed


# ---------- libellé du contrefactuel (conformité non nécessairement monotone) ----------

def non_monotone_brief(level, bound):
    brief = make_brief(level)
    brief["checks"][0]["counterfactual"] = {
        "parameter": "target_weight", "compliant_at_or_below": bound,
        "display_value": "aucun poids conforme" if bound is None else format_percent(bound)}
    return brief


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_counterfactual_line_states_largest_tested_compliant_weight(level):
    brief = non_monotone_brief(level, 0.24)    # 0.24 conforme alors que des poids plus bas ne le sont pas
    text = render_markdown(render_template(brief), brief)
    assert "Concentration par actif : le plus grand poids testé conforme à cette règle est 24 %." in text
    assert "% ou moins" not in text and "% et moins" not in text and "sous 24" not in text


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_counterfactual_section_says_it_concerns_one_rule_only(level):
    brief = make_brief(level)
    section = render_markdown(render_template(brief), brief).split("## Ce qui ferait changer le verdict")[1]
    section = section.split("## ")[0]
    assert "règle seule" in section
    assert ("n'implique pas de respecter les autres" in section) or ("pas à l'ensemble du portefeuille" in section)


def test_counterfactual_no_solution_line_is_scoped_to_the_rule():
    brief = non_monotone_brief("novice", None)
    text = render_markdown(render_template(brief), brief)
    assert "Concentration par actif : aucun poids testé n'est conforme à cette règle." in text


def test_counterfactual_none_gives_no_weight_line():
    brief = make_brief("pro")
    brief["checks"][0]["counterfactual"] = None
    text = render_markdown(render_template(brief), brief)
    assert "le plus grand poids testé conforme" not in text and "seule la marge" in text


def test_each_rule_gets_its_own_counterfactual_line_with_its_own_value():
    brief = make_brief("pro")
    brief["checks"][1]["counterfactual"] = {"parameter": "target_weight", "compliant_at_or_below": 0.12,
                                            "display_value": "12 %"}
    text = render_markdown(render_template(brief), brief)
    assert "Concentration par actif : le plus grand poids testé conforme à cette règle est 22 %." in text
    assert "Volatilité annuelle : le plus grand poids testé conforme à cette règle est 12 %." in text


# ---------- statut déjà dit à côté d'un renvoi [G..] : pas de répétition ----------

STATUS_TEXT = {"conflict": "en conflit", "tension": "en tension", "compliant": "conforme",
               "missing_info": "information manquante"}
STATUS_COUNT = re.compile(r"\bconflits?\b|\btensions?\b|\bconformes?\b|information manquante|manque d'information")
G1_LABEL = "Concentration par actif"


def brief_with_status(status, level="novice"):
    """Dossier de la fixture dont le contrôle G1 prend le statut donné."""
    brief = make_brief(level)
    check = brief["checks"][0]
    check["status"] = status
    if status == "missing_info":
        check.update(value=None, margin=None, missing_reason="Valeur indisponible.")
    return brief


def summary_line(text, brief):
    """Résumé rendu, sur une seule ligne, pour un texte de modèle donné."""
    markdown = render_markdown(output_with(level=brief["level"], summary=text), brief)
    return markdown.split("## Résumé\n\n")[1].split("\n")[0]


SENTENCES = {
    "conflict": ["La règle [G1] est en conflit avec le profil.", "Un conflit apparaît sur [G1]."],
    "tension": ["La règle [G1] est en tension.", "Il y a une tension sur [G1]."],
    "compliant": ["La règle [G1] reste conforme.", "[G1] : conforme au profil."],
    "missing_info": ["[G1] : information manquante.", "Pour [G1], le contrôle manque d'information.",
                     "Pour [G1], l'information manquante empêche tout verdict."],
}
NEUTRAL = ["Contrôle : [G1].", "Voir [G1] pour le détail.", "Points à regarder : [G1]."]


@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("status", sorted(SENTENCES))
def test_status_already_in_the_sentence_is_not_repeated(status, level):
    for sentence in SENTENCES[status]:
        line = summary_line(sentence, brief_with_status(status, level))
        assert f"**{G1_LABEL}**" in line, sentence                 # le nom de la règle est conservé
        assert f"({STATUS_TEXT[status]})" not in line, sentence    # pas de statut entre parenthèses
        assert len(STATUS_COUNT.findall(line.lower())) == 1, (sentence, line)


@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("status", sorted(SENTENCES))
def test_status_is_kept_when_the_text_does_not_say_it(status, level):
    for sentence in NEUTRAL:
        line = summary_line(sentence, brief_with_status(status, level))
        assert f"**{G1_LABEL}** ({STATUS_TEXT[status]})" in line, (status, sentence)


@pytest.mark.parametrize("status,wrong_word", [
    ("compliant", "tension"), ("tension", "conflit"), ("conflict", "tension"), ("missing_info", "conflit"),
])
def test_another_status_word_never_removes_the_real_status(status, wrong_word):
    line = summary_line(f"La règle [G1] est en {wrong_word}.", brief_with_status(status))
    assert f"({STATUS_TEXT[status]})" in line


def test_negated_conformity_does_not_count_as_compliant():
    brief = brief_with_status("compliant")
    for sentence in ("Contrôles non conformes : [G1].", "La règle [G1] n'est pas conforme."):
        assert "(conforme)" in summary_line(sentence, brief), sentence


def test_each_reference_is_judged_on_its_own_neighbourhood():
    brief = make_brief()                      # G1 en conflit, G2 en tension, G3 en tension
    assert summary_line("[G1] et [G2] sont en tension.", brief) == (
        f"**{G1_LABEL}** (en conflit) et **Volatilité annuelle** sont en tension.")
    assert summary_line("[G2] est en tension, [G1] aussi.", brief) == (
        f"**Volatilité annuelle** est en tension, **{G1_LABEL}** (en conflit) aussi.")


def test_status_said_in_another_sentence_does_not_count():
    line = summary_line("Le verdict est un conflit. Voir [G1].", make_brief())
    assert f"**{G1_LABEL}** (en conflit)" in line


def test_accents_and_case_are_ignored_when_looking_for_the_status():
    assert "(information manquante)" not in summary_line("Pour [G1], INFORMATION MANQUANTE.",
                                                         brief_with_status("missing_info"))
    assert "(conforme)" not in summary_line("[G1] est CONFORME.", brief_with_status("compliant"))


def test_other_references_are_untouched():
    line = summary_line("[G99] en conflit, preuve [E1] et terme [T1].", make_brief())
    assert "[référence inconnue : G99]" in line and "25 %" in line and "**Volatilité**" in line


def test_governance_verdict_stays_in_the_details_table_whatever_the_text():
    for status in sorted(SENTENCES):
        brief = brief_with_status(status)
        text = render_markdown(output_with(summary=SENTENCES[status][0]), brief)
        row = next(line for line in text.splitlines() if line.startswith(f"| {G1_LABEL}"))
        assert STATUS_TEXT[status] in row


def test_substitution_does_not_change_the_checks_or_the_registry():
    brief = brief_with_status("conflict")
    before = copy.deepcopy(brief)
    summary_line(SENTENCES["conflict"][0], brief)
    assert brief == before


@pytest.mark.parametrize("level", ["novice", "pro"])
@pytest.mark.parametrize("status", sorted(SENTENCES))
def test_template_text_shows_each_status_exactly_once_per_reference(status, level):
    """Le gabarit ne dit pas le statut à côté du renvoi : le rendu l'ajoute une seule fois, sans doublon."""
    brief = brief_with_status(status, level)
    text = render_markdown(render_template(brief), brief)
    assert not re.search(r"\(([^()]+)\)\s*\(\1\)", text)
    assert not re.search(r"(en conflit|en tension)[^.\n]{0,20}\(\1\)", text)
    if status != "compliant":
        assert f"**{G1_LABEL}** ({STATUS_TEXT[status]})" in text


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_model_like_output_is_readable_without_repeated_statuses(level):
    brief = make_brief(level)
    output = output_with(
        level=level,
        summary="La règle [G1] est en conflit avec le profil, et [G2] est en tension.",
        factors=[{"check_id": "G1", "text": "Le poids [E1] met [G1] en conflit."},
                 {"check_id": "G2", "text": "La volatilité [E2] place [G2] en tension."}],
        counterfactual="Pour [G1], le plus grand poids testé conforme est donné ci-dessous.")
    text = render_markdown(output, brief)
    assert "**Concentration par actif** est en conflit" in text and "**Volatilité annuelle** est en tension" in text
    assert "met **Concentration par actif** en conflit" in text and "place **Volatilité annuelle** en tension" in text
    assert "**Concentration par actif** (en conflit)" in text.split("## Ce qui ferait changer le verdict")[1]
    assert not re.search(r"(en conflit|en tension)[^.\n]{0,40}\((en conflit|en tension)\)", text)
    assert not re.search(r"\((en conflit|en tension)\)[^.\n]{0,15}(en conflit|en tension)", text)
    assert not REFERENCE_PATTERN.search(text)
