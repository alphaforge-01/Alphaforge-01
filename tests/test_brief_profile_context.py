"""Tests P1-7 : contexte du profil dans le dossier d'explication. Profils fictifs, aucun appel AWS."""
import copy
import json
import re
import sys
from pathlib import Path
from typing import get_args, get_type_hints

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alphaforge import explanation_brief  # noqa: E402
from alphaforge.contracts import (  # noqa: E402
    ExplanationBrief, ExplanationResult, InvestorProfile, ProfileContext, check_keys,
)
from alphaforge.explanation_brief import (  # noqa: E402
    ESG_PREFERENCE_FR, EXPERIENCE_FR, MAX_OBJECTIVE_CHARS, RISK_TOLERANCE_FR, build_brief,
    build_profile_context,
)
from alphaforge.explanation_fallback import render_template  # noqa: E402
from alphaforge.explanation_rendering import render_markdown  # noqa: E402
from alphaforge.explanation_validator import has_unsafe_markup, validate  # noqa: E402
from alphaforge.profiles import build_profile_from_answers, load_personas  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
CONTEXT_KEYS = set(ProfileContext.__annotations__)
PROFILE_KEYS = ("objective", "horizon_years_min", "horizon_years_max", "risk_tolerance", "experience",
                "esg_preference", "crypto_allowed")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def result_for(persona_id):
    """Résultat de la fixture de Robert, avec le profil réel du persona (gouvernance alignée)."""
    result = load("analysis_result_robert_tsla.json")
    result["profile"] = load_personas()[persona_id]["profile"]
    result["governance_after"]["profile_id"] = persona_id
    return result


def profile(**overrides):
    base = copy.deepcopy(load_personas()["robert"]["profile"])
    base.update(overrides)
    return base


# ---------- contenu : seulement ce que le profil contient ----------

EXPECTED = {
    "robert": {"objective": "Préserver le capital avant la retraite", "horizon_years_min": 3, "horizon_years_max": 5,
               "risk_tolerance": "low_moderate", "risk_tolerance_fr": "faible à modérée",
               "experience": "advanced", "experience_fr": "avancé", "esg_preference": "none",
               "esg_preference_fr": "aucune", "crypto_allowed": False},
    "amira": {"objective": "Croissance à long terme avec diversification", "horizon_years_min": 15,
              "horizon_years_max": 30, "risk_tolerance": "high", "risk_tolerance_fr": "élevée",
              "experience": "intermediate", "experience_fr": "intermédiaire", "esg_preference": "none",
              "esg_preference_fr": "aucune", "crypto_allowed": True},
    "mateo": {"objective": "Croissance équilibrée avec critères ESG", "horizon_years_min": 8, "horizon_years_max": 12,
              "risk_tolerance": "moderate", "risk_tolerance_fr": "modérée", "experience": "intermediate",
              "experience_fr": "intermédiaire", "esg_preference": "strong", "esg_preference_fr": "forte",
              "crypto_allowed": False},
}


@pytest.mark.parametrize("persona_id", sorted(EXPECTED))
@pytest.mark.parametrize("level", ["novice", "pro"])
def test_context_of_each_persona_is_copied_from_the_profile(persona_id, level):
    brief = build_brief(result_for(persona_id), level)
    assert brief["profile_context"] == EXPECTED[persona_id]


@pytest.mark.parametrize("persona_id", sorted(EXPECTED))
def test_every_context_value_comes_from_the_profile(persona_id):
    source = load_personas()[persona_id]["profile"]
    context = build_brief(result_for(persona_id), "pro")["profile_context"]
    for key in PROFILE_KEYS:
        assert context[key] == source[key], key
    assert set(context) <= CONTEXT_KEYS


@pytest.mark.parametrize("persona_id", sorted(EXPECTED))
def test_no_identity_capital_threshold_or_rule_in_the_context(persona_id):
    source = load_personas()[persona_id]["profile"]
    dump = json.dumps(build_brief(result_for(persona_id), "novice")["profile_context"], ensure_ascii=False)
    for forbidden in (source["display_name"], "capital_cad", "100000", "warn_threshold", "limit_threshold",
                      "rule_id", "profile_id", "default_level", "is_fictional"):
        assert forbidden not in dump, forbidden


def test_context_is_identical_at_both_levels_and_independent_of_the_result():
    result = result_for("amira")
    novice, pro = build_brief(result, "novice"), build_brief(result, "pro")
    assert novice["profile_context"] == pro["profile_context"]
    novice["profile_context"]["objective"] = "modifié"
    assert result["profile"]["objective"] == "Croissance à long terme avec diversification"
    assert build_brief(result, "novice")["profile_context"]["objective"] != "modifié"


def test_building_does_not_mutate_the_result_and_is_json_serializable():
    result = result_for("mateo")
    snapshot = copy.deepcopy(result)
    brief = build_brief(result, "novice")
    assert result == snapshot
    assert json.loads(json.dumps(brief, ensure_ascii=False))["profile_context"] == brief["profile_context"]


def test_custom_profile_context_follows_the_answers():
    answers = {"objective": "Croissance équilibrée", "horizon_years_min": 8, "horizon_years_max": 12,
               "risk_tolerance": "moderate", "experience": "beginner", "esg_preference": "moderate",
               "crypto_allowed": True, "capital_cad": 50000}
    custom = build_profile_from_answers(answers)
    result = load("analysis_result_robert_tsla.json")
    result["profile"] = custom
    result["governance_after"]["profile_id"] = "custom"
    context = build_brief(result, "novice")["profile_context"]
    assert context["objective"] == "Croissance équilibrée" and context["experience_fr"] == "débutant"
    assert context["esg_preference_fr"] == "modérée" and context["crypto_allowed"] is True
    assert (context["horizon_years_min"], context["horizon_years_max"]) == (8, 12)
    assert "50000" not in json.dumps(context)


# ---------- libellés : une traduction fixe, complète, sans interprétation ----------

@pytest.mark.parametrize("field,labels", [("risk_tolerance", RISK_TOLERANCE_FR), ("experience", EXPERIENCE_FR),
                                           ("esg_preference", ESG_PREFERENCE_FR)])
def test_labels_cover_every_value_of_the_contract(field, labels):
    allowed = set(get_args(get_type_hints(InvestorProfile)[field]))
    assert set(labels) == allowed
    assert len(set(labels.values())) == len(labels)
    for text in labels.values():
        assert not re.search(r"\d", text) and text == text.strip()


def test_labels_do_not_add_judgement_words():
    words = " ".join([*RISK_TOLERANCE_FR.values(), *EXPERIENCE_FR.values(), *ESG_PREFERENCE_FR.values()])
    for forbidden in ("prudent", "agressif", "sécuritaire", "recommand", "court terme", "long terme"):
        assert forbidden not in words


# ---------- valeur absente ou invalide : la clé est omise, rien n'est inventé ----------

@pytest.mark.parametrize("key", PROFILE_KEYS)
def test_missing_profile_field_omits_only_its_keys(key):
    partial = profile()
    del partial[key]
    context = build_profile_context(partial)
    expected_missing = {key, f"{key}_fr"}
    if key in ("horizon_years_min", "horizon_years_max"):
        expected_missing = {"horizon_years_min", "horizon_years_max"}
    assert expected_missing.isdisjoint(context)
    assert set(context) == set(build_profile_context(profile())) - expected_missing


@pytest.mark.parametrize("bad", [None, "", "   ", 12, ["x"], "a" * (MAX_OBJECTIVE_CHARS + 1), "ligne 1\nligne 2",
                                 "tab\tulation", "https://exemple.test", "voir [x](y)", "<b>gras</b>",
                                 "<script>x</script>", "ht\u200btp://x.y", "texte\x00nul"])
def test_unsafe_or_invalid_objective_is_omitted(bad):
    context = build_profile_context(profile(objective=bad))
    assert "objective" not in context and "risk_tolerance" in context


def test_objective_length_boundary_and_whitespace():
    assert build_profile_context(profile(objective="a" * MAX_OBJECTIVE_CHARS))["objective"] == "a" * MAX_OBJECTIVE_CHARS
    assert build_profile_context(profile(objective="  Préserver le capital  "))["objective"] == "Préserver le capital"
    assert build_profile_context(profile(objective="Croissance < 10 ans"))["objective"] == "Croissance < 10 ans"


@pytest.mark.parametrize("low,high", [(5, 3), (-1, 5), (3.0, 5), (3, 5.5), (True, 5), ("3", "5"), (None, 5), (3, None)])
def test_invalid_horizon_is_omitted_entirely(low, high):
    context = build_profile_context(profile(horizon_years_min=low, horizon_years_max=high))
    assert "horizon_years_min" not in context and "horizon_years_max" not in context


def test_valid_horizon_edge_cases():
    context = build_profile_context(profile(horizon_years_min=0, horizon_years_max=0))
    assert (context["horizon_years_min"], context["horizon_years_max"]) == (0, 0)


@pytest.mark.parametrize("field", ["risk_tolerance", "experience", "esg_preference"])
@pytest.mark.parametrize("bad", ["extreme", "", None, 3, "LOW"])
def test_unknown_enum_value_is_omitted_with_its_label(field, bad):
    context = build_profile_context(profile(**{field: bad}))
    assert field not in context and f"{field}_fr" not in context


@pytest.mark.parametrize("bad", [None, "oui", 1, 0])
def test_crypto_allowed_must_be_a_boolean(bad):
    assert "crypto_allowed" not in build_profile_context(profile(crypto_allowed=bad))


@pytest.mark.parametrize("value", [None, [], "texte", 3, {}])
def test_unusable_profile_gives_no_context(value):
    assert build_profile_context(value) is None


def test_brief_without_any_usable_profile_field_has_no_context_key():
    result = load("analysis_result_robert_tsla.json")
    result["profile"] = {"profile_id": "robert", "rules": result["profile"]["rules"]}
    brief = build_brief(result, "novice")
    assert "profile_context" not in brief
    assert check_keys(brief, ExplanationBrief) == []


# ---------- contrat et compatibilité ----------

def test_contract_declares_the_field_as_optional():
    assert "profile_context" in ExplanationBrief.__annotations__
    assert check_keys({k: None for k in ExplanationBrief.__annotations__ if k != "profile_context"},
                      ExplanationBrief) == []
    assert "objective" in ProfileContext.__annotations__ and ProfileContext.__required_keys__ == frozenset()


@pytest.mark.parametrize("persona_id", sorted(EXPECTED))
def test_brief_with_context_respects_the_contract(persona_id):
    brief = build_brief(result_for(persona_id), "pro")
    assert check_keys(brief, ExplanationBrief) == []
    assert set(brief) == set(ExplanationBrief.__annotations__)


def test_old_fixture_without_context_still_works_everywhere():
    brief = load("explanation_brief_robert_novice.json")
    assert "profile_context" not in brief and check_keys(brief, ExplanationBrief) == []
    output = render_template(brief)
    assert validate(output, brief)["is_valid"] is True
    assert "## Résumé" in render_markdown(output, brief)


@pytest.mark.parametrize("persona_id", sorted(EXPECTED))
@pytest.mark.parametrize("level", ["novice", "pro"])
def test_template_validator_and_rendering_are_unchanged_by_the_context(persona_id, level):
    with_context = build_brief(result_for(persona_id), level)
    without = copy.deepcopy(with_context)
    del without["profile_context"]
    out_with, out_without = render_template(with_context), render_template(without)
    assert {k: v for k, v in out_with.items() if k != "brief_id"} == {k: v for k, v in out_without.items()
                                                                         if k != "brief_id"}
    assert validate(out_with, with_context)["is_valid"] is True
    # Seul le rendu ajoute la section du contexte du profil ; le reste du texte est identique.
    section = re.compile(r"## Contexte déclaré du profil fictif\n.*?(?=## )", re.DOTALL)
    rendered = render_markdown(out_with, with_context)
    assert section.search(rendered) and section.sub("", rendered) == render_markdown(out_without, without)


def test_brief_id_depends_on_the_context_and_stays_stable():
    result = result_for("robert")
    first = build_brief(result, "novice")["brief_id"]
    assert build_brief(result, "novice")["brief_id"] == first
    changed = copy.deepcopy(result)
    changed["profile"]["objective"] = "Préserver le capital"
    assert build_brief(changed, "novice")["brief_id"] != first
    changed = copy.deepcopy(result)
    changed["profile"]["display_name"] = "Autre nom"
    assert build_brief(changed, "novice")["brief_id"] == first       # le nom n'entre pas dans le dossier


def test_existing_identity_rule_still_holds():
    result = result_for("robert")
    result["profile"]["display_name"] = "NomUnique"
    result["profile"]["capital_cad"] = 987654.0
    dump = json.dumps(build_brief(result, "pro"), ensure_ascii=False)
    assert "NomUnique" not in dump and "987654" not in dump


# ---------- ce que voit l'explicateur et le pipeline du flux C ----------

class _Recorder:
    def __init__(self):
        self.calls = []

    def converse(self, model_id, messages, *, system=None, tool_config=None, inference_config=None, **kwargs):
        self.calls.append(messages)
        slots = {"summary": "La règle [G1] est en conflit selon [E1].",
                 "factors": [{"check_id": "G1", "text": "La règle [G1] est en conflit."}],
                 "counterfactual": "Voir [G1].", "variants": "Aucune variante.", "limits_context": "Données fictives."}
        return {"output": {"message": {"role": "assistant", "content": [{"text": json.dumps(slots)}]}},
                "stopReason": "end_turn"}


def test_explainer_receives_the_context_in_the_brief_json():
    from alphaforge.explainer_agent import explain_with_llm
    brief = build_brief(result_for("mateo"), "novice")
    client = _Recorder()
    explain_with_llm(client, "modele-test", brief, lambda o, b: {"is_valid": True, "rejections": [],
                                                                    "checked_references": []})
    sent = client.calls[0][0]["content"][0]["text"]
    assert json.dumps(brief, ensure_ascii=False) in sent and '"profile_context"' in sent
    assert "Croissance équilibrée avec critères ESG" in sent


def test_prompt_already_documents_the_field():
    from alphaforge.prompt_loader import load_prompt
    prompt = load_prompt("explainer_v5")
    assert "profile_context" in prompt and "sans chiffre" in prompt


def test_real_offline_pipeline_exposes_the_context_in_explain_result():
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    persona = load_personas()["robert"]
    idea = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    result = run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline", config=BedrockConfig())
    explanation = explain(result, "novice", mode="offline", config=BedrockConfig())
    assert check_keys(explanation, ExplanationResult) == []
    assert explanation["brief"]["profile_context"] == EXPECTED["robert"]
    assert explanation["validation"]["is_valid"] is True and result["is_fixture"] is False


def test_fixture_collaborators_brief_stays_valid_without_the_context():
    from alphaforge.analysis_pipeline import explain, run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.fixture_collaborators import fixture_deps
    deps = fixture_deps()
    result = run_analysis(load("profile_robert.json"), load("portfolio_robert.json"), load("idea_tsla_25.json"),
                          deps=deps, config=BedrockConfig())
    explanation = explain(result, "pro", deps=deps, config=BedrockConfig())
    assert check_keys(explanation, ExplanationResult) == []
    assert explanation["validation"]["is_valid"] is True


# ---------- aide partagée avec le validateur ----------

@pytest.mark.parametrize("text", ["https://x.y", "www.x.y", "[a](b)", "![a](b)", "<b>x</b>", "<script", "javascript:x",
                                  "ht\u200btp://x.y", "\uff1cscript\uff1ex"])
def test_has_unsafe_markup_detects_links_images_and_html(text):
    assert has_unsafe_markup(text) is True


@pytest.mark.parametrize("text", ["Préserver le capital", "a < b", "<5 %", "x<y", "[E1] et [G1]", "Croissance à long terme"])
def test_has_unsafe_markup_keeps_plain_text(text):
    assert has_unsafe_markup(text) is False


def test_module_has_no_network_or_model_dependency():
    source = Path(explanation_brief.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(boto3|botocore|requests|urllib|anthropic)", source, re.M)
    assert "\u2014" not in source
