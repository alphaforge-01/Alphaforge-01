"""Tests de la source du contrôle d'ancrage. Fixtures inventées, aucun appel AWS."""
import json
import re

import pytest

from alphaforge import analysis_pipeline, bedrock_client
from alphaforge.explanation_rendering import format_percent, format_points
from alphaforge.grounding_facts import (
    SCOPE_SUFFIXES, check_sentence, fact_sentence, grounding_source_text, idea_sentence,
    subject_phrase, variant_sentence,
)
from alphaforge.profiles import load_personas


# ---------- unitaires ----------

@pytest.mark.parametrize("subject, expected", [
    ("portfolio_before", "du portefeuille avant l'ajout"),
    ("portfolio_after", "du portefeuille après l'ajout"),
    ("variant:V1", "de la variante simulée V1"),
    ("explored:abc", "de la simulation explorée par l'analyste (abc)"),
    ("TSLA", "de l'actif TSLA"),
])
def test_subject_phrase(subject, expected):
    assert subject_phrase(subject) == expected, f"Sujet mal décrit : {subject}"


def make_entry(**kw):
    entry = {"label_fr": "Volatilité annualisée", "metric": "volatility_ann", "subject": "TSLA",
             "unit": "pct", "display_value": "52,3 %", "period_start": "2021-01-04",
             "period_end": "2025-12-31", "currency": "CAD"}
    entry.update(kw)
    return entry


def test_fact_sentence_serie_avec_periode():
    text = fact_sentence(make_entry())
    assert text.startswith("Volatilité annualisée de l'actif TSLA")
    assert "52,3 %" in text
    assert "(période du 2021-01-04 au 2025-12-31, devise CAD)" in text
    assert text.endswith(".")


def test_fact_sentence_sans_devise():
    text = fact_sentence(make_entry(currency=None))
    assert "(période du 2021-01-04 au 2025-12-31)" in text


def test_fact_sentence_delta_et_valeur_absente():
    text = fact_sentence(make_entry(metric="volatility_delta", subject="portfolio_after"))
    assert "entre le portefeuille avant l'ajout et le portefeuille après l'ajout" in text
    assert "du portefeuille après l'ajout :" not in text
    for empty in (None, ""):
        assert "information manquante" in fact_sentence(make_entry(display_value=empty))


@pytest.mark.parametrize("suffix", SCOPE_SUFFIXES)
def test_fact_sentence_suffixe_de_perimetre_non_double(suffix):
    text = fact_sentence(make_entry(label_fr="Volatilité annualisée" + suffix, subject="portfolio_after"))
    assert text.startswith("Volatilité annualisée du portefeuille après l'ajout")
    assert suffix.strip() not in text


@pytest.mark.parametrize("unit", ["pct", "cad", "days"])
def test_fact_sentence_periode_pour_unites_de_serie(unit):
    assert "période du" in fact_sentence(make_entry(unit=unit))


def test_fact_sentence_composition_sans_periode():
    text = fact_sentence(make_entry(unit="pct", period_start=None, period_end=None))
    assert "période" not in text
    assert text.endswith(".")


def test_fact_sentence_pas_de_periode_pour_unite_hors_serie():
    assert "période" not in fact_sentence(make_entry(unit="count"))


def make_check(**kw):
    check = {"rule_id": "R1", "label_fr": "Volatilité maximale", "status": "tension", "unit": "pct",
             "value": 0.2, "warn_threshold": 0.15, "limit_threshold": 0.25, "margin": -0.03,
             "counterfactual": None, "missing_reason": None}
    check.update(kw)
    return check


@pytest.mark.parametrize("status, fr", [
    ("compliant", "conforme"), ("tension", "en tension"),
    ("conflict", "en conflit"), ("missing_info", "information manquante")])
def test_check_sentence_statuts(status, fr):
    assert f": {fr}" in check_sentence(make_check(status=status))


def test_check_sentence_formats():
    text = check_sentence(make_check())
    assert f"valeur observée {format_percent(0.2)}" in text
    assert f"seuil d'attention {format_percent(0.15)}" in text
    assert f"limite du profil {format_percent(0.25)}" in text
    assert f"marge {format_points(-0.03)}" in text
    assert text.endswith(".")


def test_check_sentence_unite_bool_exclusion():
    text = check_sentence(make_check(unit="bool", rule_id="R9", status="conflict", value=0.2,
                                     warn_threshold=None, limit_threshold=0.0, margin=-0.2))
    assert "marge -20 pts" in text
    assert "valeur observée 20 %" in text
    assert "seuil d'attention" not in text, "Un seuil None doit être ignoré"


def test_check_sentence_contrefactuel_et_raison_manquante():
    cf = {"display_value": "12 %", "compliant_at_or_below": 0.12}
    text = check_sentence(make_check(counterfactual=cf, missing_reason="Donnée absente."), idea_ticker="TSLA")
    assert "le plus grand poids testé pour TSLA conforme à cette règle seule est 12 %" in text
    assert "les autres règles ne sont pas garanties" in text
    assert "Donnée absente" in text and "Donnée absente.." not in text
    assert "pour TSLA" not in check_sentence(make_check(counterfactual=cf))


def test_check_sentence_contrefactuel_aucun_poids_conforme():
    cf = {"display_value": None, "compliant_at_or_below": None}
    text = check_sentence(make_check(status="conflict", counterfactual=cf), idea_ticker="TSLA")
    assert "aucun poids testé pour TSLA n'est conforme à cette règle" in text
    assert "le plus grand poids" not in text


def test_check_sentence_contrefactuel_ignore_si_conforme():
    cf = {"display_value": "12 %", "compliant_at_or_below": 0.12}
    assert "poids testé" not in check_sentence(make_check(status="compliant", counterfactual=cf), "TSLA")


@pytest.mark.parametrize("direction, expected", [
    ("max", "plafond : la valeur doit rester sous les seuils"),
    ("min", "plancher : la valeur doit rester au-dessus des seuils"),
])
def test_check_sentence_direction(direction, expected):
    assert expected in check_sentence(make_check(), direction=direction)
    assert "plafond" not in check_sentence(make_check()) and "plancher" not in check_sentence(make_check())


def test_idea_sentence():
    pro_rata = idea_sentence({"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata"})
    assert "porter TSLA à 25 % du portefeuille" in pro_rata and "au prorata" in pro_rata
    from_t = idea_sentence({"ticker": "BTC-USD", "target_weight": 0.1, "funding_source": "from_ticker",
                            "funding_ticker": "XIU.TO"})
    assert "vente de XIU.TO" in from_t


def test_idea_sentence_champs_manquants():
    assert idea_sentence({}) == "Idée simulée (demande fictive)."
    assert idea_sentence({"ticker": "TSLA"}) == "Idée simulée (demande fictive) sur TSLA."
    no_ticker = idea_sentence({"target_weight": 0.2, "funding_source": "pro_rata"})
    assert "porter" not in no_ticker and "au prorata" in no_ticker
    no_weight = idea_sentence({"ticker": "TSLA", "funding_source": "from_ticker", "funding_ticker": None})
    assert "vente" not in no_weight and "%" not in no_weight


def test_variant_sentence():
    text = variant_sentence({"variant_id": "V1", "reason_code": "reduce_weight", "overall_status": "tension"})
    assert text == ("Variante simulée V1 (première variante) : elle réduit la part de l'idée "
                    "(réduction du poids cible) ; verdict d'ensemble tension.")
    second = variant_sentence({"variant_id": "V2", "reason_code": "inconnu", "overall_status": "conflict"}, 1)
    assert "(deuxième variante)" in second and "elle" not in second and "conflit" in second
    assert "(autre variante)" in variant_sentence({"variant_id": "V9"}, 7)


def make_brief(statuses=("compliant", "tension")):
    return {
        "idea": {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None},
        "checks": [make_check(rule_id=f"R{i}", status=s) for i, s in enumerate(statuses, 1)],
        "evidence": [make_entry(evidence_id="E12")],
        "variants": [{"variant_id": "V1", "reason_code": "reduce_weight", "overall_status": "compliant"}],
        "glossary": [{"term": "Volatilité", "definition": "Ampleur des variations.", "analogy": "Des vagues."}],
        "limits": [{"text": "Le passé ne prédit pas l'avenir."}],
        "profile_rules": [{"rule_id": "R1", "direction": "max"}],
    }


def test_grounding_source_text_ordre_et_forme():
    lines = grounding_source_text(make_brief()).split("\n")
    assert lines[0].startswith("Faits établis")
    kinds = [
        next(i for i, line in enumerate(lines) if line.startswith(p))
        for p in ("Idée simulée", "Verdict d'ensemble", "Contrôle", "Volatilité annualisée",
                  "Variante simulée", "Définitions du glossaire :", "Volatilité :",
                  "Limites et hypothèses (les seuils des règles sont des hypothèses de l'équipe) :",
                  "Le passé")]
    assert kinds == sorted(kinds), f"Ordre des lignes incorrect : {kinds}"
    text = "\n".join(lines)
    assert "{" not in text and "}" not in text, "Aucune accolade JSON attendue"
    assert "E12" not in text
    assert "plafond : la valeur doit rester sous les seuils" in lines[3], "Direction issue de profile_rules"


def test_sections_absentes_sans_glossaire_ni_limites():
    brief = make_brief()
    brief["glossary"], brief["limits"] = [], []
    text = grounding_source_text(brief)
    assert "Définitions du glossaire" not in text and "Limites et hypothèses" not in text


@pytest.mark.parametrize("statuses, worst", [
    (("compliant", "missing_info"), "information manquante"),
    (("missing_info", "tension", "compliant"), "tension"),
    (("tension", "conflict", "compliant"), "conflit"),
    (("compliant",), "conforme"),
    ((), "information manquante"),
])
def test_pire_statut(statuses, worst):
    text = grounding_source_text(make_brief(statuses))
    assert f"de l'idée simulée sur TSLA : {worst}." in text
    assert "Verdict d'ensemble (pire statut des règles évaluées)" in text


def test_brief_vide_ne_plante_pas():
    assert grounding_source_text({}).startswith("Faits établis")


# ---------- intégration (données réelles, hors ligne) ----------

IDEAS = [("TSLA", 0.25), ("BTC-USD", 0.20)]
NUMBER = re.compile(r"(?<![A-Za-z0-9])-?\d+(?:,\d+)?(?:\s?(?:%|pts|jours?|\$))?")
REF_ID = re.compile(r"\[?\b[EGT]\d+\b\]?")


@pytest.fixture(scope="module")
def runs():
    personas = load_personas()
    out = {}
    for pid in ("robert", "amira", "mateo"):
        for ticker, weight in IDEAS:
            idea = {"ticker": ticker, "target_weight": weight, "funding_source": "pro_rata",
                    "funding_ticker": None}
            persona = personas[pid]
            out[(pid, ticker)] = analysis_pipeline.run_analysis(
                persona["profile"], persona["portfolio"], idea, mode="offline")
    return out


@pytest.mark.parametrize("pid", ["robert", "amira", "mateo"])
@pytest.mark.parametrize("ticker", ["TSLA", "BTC-USD"])
@pytest.mark.parametrize("level", ["novice", "pro"])
def test_integration_ancrage(runs, pid, ticker, level):
    result = runs[(pid, ticker)]
    explanation = analysis_pipeline.explain(result, level, mode="offline")
    brief = explanation["brief"]
    source = grounding_source_text(brief)
    # Ce que le garde-fou vérifie : les phrases du modèle, renvois remplacés par les valeurs du dossier
    body = REF_ID.sub("", analysis_pipeline._model_text(explanation["output"], brief))

    manquants = [m.group(0).strip() for m in NUMBER.finditer(body)
                 if m.group(0).strip() not in source]
    assert manquants == [], f"Nombres du texte absents de la source ({pid}, {ticker}, {level}) : {manquants}"

    assert len(source) < bedrock_client.GROUNDING_SOURCE_MAX_CHARS
    assert len(source) < len(json.dumps(brief, ensure_ascii=False)) / 2, "La source doit être bien plus courte que le JSON"
    for entry in brief["evidence"]:
        assert entry["display_value"] in source, f"Preuve absente : {entry['evidence_key']}"
    assert source == grounding_source_text(brief), "La source doit être déterministe"
