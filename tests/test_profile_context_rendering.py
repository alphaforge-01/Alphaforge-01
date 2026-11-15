"""Tests P1-7 : section "Contexte déclaré du profil fictif" du rendu Markdown. Profils fictifs, aucun appel AWS."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge.contracts import ExplanationBrief, check_keys  # noqa: E402
from alphaforge.explanation_brief import build_brief  # noqa: E402
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import (  # noqa: E402
    PROFILE_CONTEXT_NOTICE, PROFILE_CONTEXT_TITLE, render_markdown,
)
from alphaforge.explanation_validator import validate  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SECTION = re.compile(re.escape(PROFILE_CONTEXT_TITLE) + r"\n(.*?)(?=\n## |\Z)", re.DOTALL)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def brief_for(persona_id, level="novice"):
    result = load("analysis_result_robert_tsla.json")
    result["profile"] = load_personas()[persona_id]["profile"]
    result["governance_after"]["profile_id"] = persona_id
    return build_brief(result, level)


def rendered(brief):
    return render_markdown(render_template(brief), brief)


def section_of(markdown):
    match = SECTION.search(markdown)
    return match.group(1) if match else None


def items_of(markdown):
    return [line for line in (section_of(markdown) or "").splitlines() if line.startswith("- ")]


# ---------- contexte complet ----------

FULL = {
    "robert": ["- Objectif : Préserver le capital avant la retraite.", "- Horizon d'investissement : de 3 à 5 ans.",
               "- Tolérance au risque : faible à modérée", "- Préférence ESG : aucune", "- Cryptoactifs : non permis."],
    "amira": ["- Objectif : Croissance à long terme avec diversification.",
              "- Horizon d'investissement : de 15 à 30 ans.", "- Tolérance au risque : élevée",
              "- Préférence ESG : aucune", "- Cryptoactifs : permis."],
    "mateo": ["- Objectif : Croissance équilibrée avec critères ESG.", "- Horizon d'investissement : de 8 à 12 ans.",
              "- Tolérance au risque : modérée", "- Préférence ESG : forte", "- Cryptoactifs : non permis."],
}


@pytest.mark.parametrize("persona_id", sorted(FULL))
@pytest.mark.parametrize("level", ["novice", "pro"])
def test_full_context_is_shown_with_the_profile_values(persona_id, level):
    items = items_of(rendered(brief_for(persona_id, level)))
    assert len(items) == 5
    for item, expected in zip(items, FULL[persona_id]):
        assert item.startswith(expected), (item, expected)


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_section_is_presented_as_declared_context_not_as_a_conclusion(level):
    markdown = rendered(brief_for("robert", level))
    assert PROFILE_CONTEXT_TITLE in markdown and "fictif" in PROFILE_CONTEXT_TITLE and "déclaré" in PROFILE_CONTEXT_TITLE
    notice = PROFILE_CONTEXT_NOTICE[level]
    assert notice in markdown
    assert "ni conclusion de l'analyse" in notice or "n'est ni une conclusion de l'analyse" in notice
    assert "recommandation" in notice
    assert not re.search(r"\d", notice)


def test_section_sits_between_the_idea_and_the_summary():
    markdown = rendered(brief_for("amira"))
    positions = [markdown.index(text) for text in ("Idée simulée", PROFILE_CONTEXT_TITLE, "## Résumé")]
    assert positions == sorted(positions)
    assert markdown.count(PROFILE_CONTEXT_TITLE) == 1


def test_levels_differ_only_in_wording_not_in_facts():
    novice = items_of(rendered(brief_for("robert", "novice")))
    pro = items_of(rendered(brief_for("robert", "pro")))
    assert novice != pro
    assert [re.sub(r" \(`[a-z_]+`\)", "", item) for item in pro] == novice
    assert not any("`" in item for item in novice) and any("`low_moderate`" in item for item in pro)
    assert PROFILE_CONTEXT_NOTICE["novice"] != PROFILE_CONTEXT_NOTICE["pro"]


def test_every_number_in_the_section_comes_from_the_profile():
    for persona_id in FULL:
        profile = load_personas()[persona_id]["profile"]
        numbers = re.findall(r"\d+", section_of(rendered(brief_for(persona_id))))
        assert numbers == [str(profile["horizon_years_min"]), str(profile["horizon_years_max"])]


def test_experience_identity_capital_and_rules_are_not_displayed():
    profile = load_personas()["robert"]["profile"]
    text = section_of(rendered(brief_for("robert")))
    for forbidden in ("Expérience", "avancé", profile["display_name"], "100000", "100 000", "Concentration",
                      "seuil", "R1"):
        assert forbidden not in text, forbidden


# ---------- contexte partiel ----------

def with_context(persona_id, **changes):
    brief = brief_for(persona_id)
    context = brief["profile_context"]
    for key, value in changes.items():
        if value is None:
            context.pop(key, None)
        else:
            context[key] = value
    return brief


@pytest.mark.parametrize("keys,label", [
    (("objective",), "Objectif"),
    (("horizon_years_min", "horizon_years_max"), "Horizon d'investissement"),
    (("risk_tolerance_fr",), "Tolérance au risque"),
    (("esg_preference_fr",), "Préférence ESG"),
    (("crypto_allowed",), "Cryptoactifs"),
])
def test_missing_key_hides_only_its_line(keys, label):
    brief = with_context("robert", **{key: None for key in keys})
    items = items_of(rendered(brief))
    assert len(items) == 4 and not any(item.startswith(f"- {label}") for item in items)
    assert section_of(rendered(brief)) is not None


def test_only_the_horizon_is_shown_when_it_is_the_only_key():
    brief = brief_for("mateo")
    brief["profile_context"] = {"horizon_years_min": 8, "horizon_years_max": 12}
    assert items_of(rendered(brief)) == ["- Horizon d'investissement : de 8 à 12 ans."]


def test_label_without_its_value_key_is_still_shown_and_value_without_label_is_not():
    brief = brief_for("robert")
    brief["profile_context"] = {"risk_tolerance_fr": "faible", "esg_preference": "strong"}   # pas de esg_preference_fr
    items = items_of(rendered(brief))
    assert items == ["- Tolérance au risque : faible."]            # jamais la valeur anglaise brute


@pytest.mark.parametrize("low,high,expected", [(5, 5, "5 ans"), (1, 1, "1 an"), (0, 0, "0 an"), (0, 1, "de 0 à 1 an"),
                                               (10, 30, "de 10 à 30 ans")])
def test_horizon_wording(low, high, expected):
    brief = brief_for("robert")
    brief["profile_context"] = {"horizon_years_min": low, "horizon_years_max": high}
    assert items_of(rendered(brief)) == [f"- Horizon d'investissement : {expected}."]


@pytest.mark.parametrize("low,high", [(5, 3), (-1, 5), (3.0, 5), (True, 5), ("3", "5"), (None, 5), (3, None)])
def test_invalid_horizon_is_not_displayed(low, high):
    brief = brief_for("robert")
    brief["profile_context"]["horizon_years_min"], brief["profile_context"]["horizon_years_max"] = low, high
    assert not any(i.startswith("- Horizon") for i in items_of(rendered(brief)))


@pytest.mark.parametrize("bad", [None, "", "   ", 12, ["x"], "https://exemple.test", "voir [x](y)", "<b>gras</b>",
                                 "<script>x</script>", "ht\u200btp://x.y", "ligne\nsuivante", "nul\x00"])
def test_unsafe_or_invalid_objective_is_not_displayed(bad):
    brief = brief_for("robert")
    brief["profile_context"]["objective"] = bad
    markdown = rendered(brief)
    assert not any(i.startswith("- Objectif") for i in items_of(markdown))
    assert "<script" not in markdown and "https://" not in markdown and "](" not in markdown


@pytest.mark.parametrize("key", ["crypto_allowed"])
@pytest.mark.parametrize("bad", ["oui", 1, 0, None])
def test_crypto_must_be_a_boolean_to_be_displayed(key, bad):
    brief = brief_for("robert")
    brief["profile_context"][key] = bad
    assert not any(i.startswith("- Cryptoactifs") for i in items_of(rendered(brief)))


def test_objective_with_final_period_is_not_doubled():
    brief = brief_for("robert")
    brief["profile_context"]["objective"] = "Préserver le capital."
    assert "- Objectif : Préserver le capital." in rendered(brief) and "capital.." not in rendered(brief)


def test_unknown_keys_and_empty_context_give_no_section():
    brief = brief_for("robert")
    brief["profile_context"] = {"experience": "advanced", "experience_fr": "avancé", "inconnu": "x"}
    assert PROFILE_CONTEXT_TITLE not in rendered(brief)
    brief["profile_context"] = {}
    assert PROFILE_CONTEXT_TITLE not in rendered(brief)


@pytest.mark.parametrize("value", ["texte", 3, ["x"], None])
def test_non_dictionary_context_gives_no_section_and_no_error(value):
    brief = brief_for("robert")
    brief["profile_context"] = value
    assert PROFILE_CONTEXT_TITLE not in rendered(brief)


# ---------- contexte absent : anciennes explications ----------

def test_old_brief_without_context_renders_exactly_as_before():
    brief = load("explanation_brief_robert_novice.json")
    assert "profile_context" not in brief and check_keys(brief, ExplanationBrief) == []
    markdown = rendered(brief)
    assert PROFILE_CONTEXT_TITLE not in markdown and "Contexte déclaré" not in markdown
    assert "## Résumé" in markdown and "Idée simulée" in markdown


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_removing_the_context_removes_only_the_section(level):
    brief = brief_for("amira", level)
    without = copy.deepcopy(brief)
    del without["profile_context"]
    with_markdown, without_markdown = rendered(brief), rendered(without)
    assert PROFILE_CONTEXT_TITLE in with_markdown and PROFILE_CONTEXT_TITLE not in without_markdown
    stripped = re.sub(re.escape(PROFILE_CONTEXT_TITLE) + r"\n.*?(?=## )", "", with_markdown, flags=re.DOTALL)
    assert stripped == without_markdown


def test_old_model_output_fixtures_still_render_without_section():
    brief = load("explanation_brief_robert_novice.json")
    for name in ("explainer_output_robert_novice.json", "explainer_output_robert_pro.json"):
        markdown = render_markdown(load(name), brief)
        assert PROFILE_CONTEXT_TITLE not in markdown and "## Résumé" in markdown


# ---------- cohérence avec le contrat, le validateur et le gabarit ----------

@pytest.mark.parametrize("persona_id", sorted(FULL))
@pytest.mark.parametrize("level", ["novice", "pro"])
def test_rendering_does_not_change_the_brief_the_output_or_the_validation(persona_id, level):
    brief = brief_for(persona_id, level)
    snapshot = copy.deepcopy(brief)
    output = render_template(brief)
    output_snapshot = copy.deepcopy(output)
    first = render_markdown(output, brief)
    assert brief == snapshot and output == output_snapshot
    assert render_markdown(output, brief) == first                 # déterministe
    assert validate(output, brief)["is_valid"] is True
    assert check_keys(brief, ExplanationBrief) == []


@pytest.mark.parametrize("level", ["novice", "pro"])
def test_the_section_text_is_written_by_the_code_not_by_the_model(level):
    brief = brief_for("robert", level)
    output = render_template(brief)
    output["summary"] = "Un résumé de modèle sans lien avec le profil [G1]."
    markdown = render_markdown(output, brief)
    assert items_of(markdown)[0].startswith("- Objectif : Préserver le capital avant la retraite")
    assert "Préserver le capital avant la retraite" not in json.dumps(output, ensure_ascii=False)


def test_no_forbidden_punctuation_or_unresolved_reference_in_the_section():
    for persona_id in FULL:
        text = PROFILE_CONTEXT_TITLE + "\n" + section_of(rendered(brief_for(persona_id, "pro")))
        assert "\u2014" not in text and "\u2013" not in text and not re.search(r"\[[EGT]\d+\]", text)


def test_real_offline_pipeline_shows_the_context_of_each_persona():
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    idea = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    for persona_id, persona in load_personas().items():
        result = run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline", config=BedrockConfig())
        explanation = explain(result, "novice", mode="offline", config=BedrockConfig())
        assert result["is_fixture"] is False and explanation["validation"]["is_valid"] is True
        assert items_of(explanation["rendered_markdown"])[0].startswith(FULL[persona_id][0])


def test_fixture_pipeline_without_context_has_no_section():
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.fixture_collaborators import fixture_deps
    deps = fixture_deps()
    result = run_analysis(load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json"),
                          deps=deps, config=BedrockConfig())
    explanation = explain(result, "novice", deps=deps, config=BedrockConfig())
    assert PROFILE_CONTEXT_TITLE not in explanation["rendered_markdown"]
