"""Tests de la source d'ancrage en phrases (src/alphaforge/grounding_source.py).

Dossier d'explication fictif, construit à la main : aucun appel réseau, aucune donnée réelle.
Les conventions vérifiées sont celles de la gouvernance : une valeur égale à un seuil ne
le franchit pas, la marge est la distance au seuil suivant, négative au-delà de la limite.
"""
from copy import deepcopy
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alphaforge.bedrock_client import GROUNDING_SOURCE_MAX_CHARS  # noqa: E402
from alphaforge.explanation_rendering import format_percent, format_points  # noqa: E402
from alphaforge.grounding_source import build_grounding_source  # noqa: E402
from alphaforge.reference_texts import disclaimers  # noqa: E402


def _evidence(evidence_id, label, value, display, **extra):
    entry = {
        "evidence_id": evidence_id, "evidence_key": f"m{evidence_id}:portfolio_after", "tool_name": "analyze_portfolio",
        "metric": "volatility_ann", "subject": "portfolio_after", "label_fr": label, "value": value, "unit": "pct",
        "display_value": display, "qualifier": None, "period_start": "2021-11-12", "period_end": "2026-11-12",
        "as_of": "2026-11-12", "currency": "CAD", "source_ids": ["prices_daily.csv"],
        "transformation": "Calcul fictif pour les tests.", "n_observations": 1000, "limit_ids": ["LM1"],
    }
    entry.update(extra)
    return entry


def _rule(rule_id, rule_type, label, direction="max", warn=0.2, limit=0.22, unit="pct", assumption=True):
    return {"rule_id": rule_id, "rule_type": rule_type, "params": {}, "direction": direction,
            "warn_threshold": warn, "limit_threshold": limit, "unit": unit, "label_fr": label,
            "origin": "persona", "is_assumption": assumption}


def _check(check_id, rule, status, value, margin, evidence_ids, counterfactual=None, missing_reason=None):
    return {"check_id": check_id, "rule_id": rule["rule_id"], "rule_type": rule["rule_type"],
            "label_fr": rule["label_fr"], "status": status, "value": value,
            "warn_threshold": rule["warn_threshold"], "limit_threshold": rule["limit_threshold"],
            "margin": margin, "unit": rule["unit"], "evidence_ids": evidence_ids,
            "counterfactual": counterfactual, "missing_reason": missing_reason}


def _brief(rules, checks, evidence=(), ranked=(), variants=(), idea=None, level="novice"):
    return {
        "brief_id": "brief-test", "run_id": "run-test", "level": level, "profile_rules": list(rules),
        "idea": idea or {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata",
                         "funding_ticker": None},
        "ranked_factors": list(ranked), "checks": list(checks), "variants": list(variants),
        "evidence": list(evidence),
        "limits": [{"limit_id": "LM1", "text": "Les résultats décrivent le passé, pas l'avenir."}],
        "glossary": [{"term_id": "T1", "term": "Volatilité", "definition": "Ampleur des variations",
                      "analogy": "Une route de montagne"}],
        "max_chars_per_slot": 400,
    }


def make_brief():
    rules = [
        _rule("R1", "max_single_asset_weight", "Concentration par actif"),
        _rule("R2", "max_portfolio_volatility", "Volatilité annuelle", warn=0.16, limit=0.25),
        _rule("R3", "min_defensive_share", "Part défensive minimale", direction="min", warn=0.4, limit=0.3),
        _rule("R4", "excluded_asset_class", "Cryptoactifs exclus", warn=None, limit=0.0, unit="bool"),
        _rule("R5", "esg_exclusion", "Exclusion ESG", warn=None, limit=None, unit="bool"),
    ]
    evidence = [
        _evidence("E1", "Poids du plus gros actif (portefeuille après l'ajout)", 0.25, "25 %"),
        _evidence("E2", "Volatilité annualisée (portefeuille après l'ajout)", 0.176, "17,6 %"),
        _evidence("E3", "Part défensive (portefeuille après l'ajout)", 0.4875, "48,75 %"),
        _evidence("E4", "Perte maximale historique (variante)", 0.1991, "19,91 %", subject="variant:V1"),
        _evidence("E5", "Durée de récupération", None, None),
    ]
    checks = [
        _check("G2", rules[1], "tension", 0.176, 0.074, ["E2"],
               counterfactual={"parameter": "target_weight", "compliant_at_or_below": 0.21, "display_value": "21 %"}),
        _check("G1", rules[0], "conflict", 0.25, -0.03, ["E1"],
               counterfactual={"parameter": "target_weight", "compliant_at_or_below": None, "display_value": ""}),
        _check("G3", rules[2], "compliant", 0.4875, 0.0875, ["E3"]),
        _check("G4", rules[3], "compliant", 0.0, 0.0, []),
        _check("G5", rules[4], "missing_info", None, None, [], missing_reason="Aucune preuve ESG disponible."),
    ]
    ranked = [{"rank": 1, "check_id": "G1", "status": "conflict", "evidence_ids": ["E1"]},
              {"rank": 2, "check_id": "G2", "status": "tension", "evidence_ids": ["E2"]}]
    variants = [{"variant_id": "V1", "reason_code": "reduce_weight", "overall_status": "compliant",
                 "evidence_ids": ["E4"]}]
    return _brief(rules, checks, evidence, ranked, variants)


def _block(source, label):
    """Lignes du contrôle `label`, jusqu'au contrôle suivant."""
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"Contrôle {label} :"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("Contrôle ")), len(lines))
    return "\n".join(lines[start:end])


def test_statuses_in_french_without_english_codes():
    source = build_grounding_source(make_brief())
    for words in ("en conflit", "en tension", "conforme", "information manquante"):
        assert words in source
    for code in ("conflict", "compliant", "missing_info", "warn_threshold", "limit_threshold", "evidence_id"):
        assert code not in source


def test_overall_verdict_is_worst_status():
    assert "Verdict d'ensemble des règles du profil : en conflit." in build_grounding_source(make_brief())


def test_registry_display_values_without_raw_numbers():
    source = build_grounding_source(make_brief())
    for display in ("25 %", "17,6 %", "48,75 %", "19,91 %"):
        assert display in source
    assert not re.search(r"\d\.\d{3,}", source)
    assert "Durée de récupération : information non disponible." in source


def test_status_meaning_follows_rule_direction():
    source = build_grounding_source(make_brief())
    assert ("seuil d'attention du profil de 20 % (tension au-delà), "
            "limite fixée pour ce profil de 22 % (conflit au-delà)") in _block(source, "Concentration par actif")
    assert "La mesure dépasse la limite fixée pour ce profil." in _block(source, "Concentration par actif")
    assert ("La mesure dépasse le seuil d'attention du profil, sans dépasser la limite."
            in _block(source, "Volatilité annuelle"))
    block = _block(source, "Part défensive minimale")
    assert "seuil d'attention du profil de 40 % (tension en dessous)" in block
    assert "La mesure ne descend pas sous le seuil d'attention du profil." in block


def test_exclusion_sentence_only_for_excluded_class_rule():
    source = build_grounding_source(make_brief())
    assert ("Toute position dans la catégorie exclue par la règle Cryptoactifs exclus met cette règle en conflit."
            in _block(source, "Cryptoactifs exclus"))
    esg = _block(source, "Exclusion ESG")
    assert "Toute position" not in esg
    assert "La règle Exclusion ESG n'a pas pu être vérifiée (information manquante)." in esg
    assert "Information manquante : Aucune preuve ESG disponible." in esg


def test_margins_and_counterfactuals_from_governance():
    source = build_grounding_source(make_brief())
    assert "La mesure est au-dessus de la limite de 3 pts." in source
    assert "Marge avant la limite : 7,4 pts." in source
    assert "Marge avant le seuil d'attention : 8,75 pts." in source
    assert ("Le plus grand poids testé pour l'idée qui rend la règle Volatilité annuelle conforme, "
            "à elle seule, est 21 %.") in source
    assert "Aucun poids testé pour l'idée ne rend la règle Concentration par actif conforme." in source


def test_value_equal_to_threshold_is_not_crossed():
    max_rule = _rule("R1", "max_single_asset_weight", "Concentration par actif", warn=0.25, limit=0.3)
    at_warn = _check("G1", max_rule, "compliant", 0.25, 0.0, [])
    tension_rule = _rule("R2", "max_portfolio_volatility", "Volatilité annuelle", warn=0.16, limit=0.22)
    at_limit = _check("G2", tension_rule, "tension", 0.22, 0.0, [])
    source = build_grounding_source(_brief([max_rule, tension_rule], [at_warn, at_limit]))
    block = _block(source, "Concentration par actif")
    assert "La mesure ne dépasse pas le seuil d'attention du profil." in block
    assert "Marge avant le seuil d'attention : 0 pts." in block
    assert "reste sous" not in source
    assert "sans dépasser la limite" in _block(source, "Volatilité annuelle")
    assert "sans atteindre" not in source


def test_min_rule_conflict_margin_says_below():
    rule = _rule("R3", "min_defensive_share", "Part défensive minimale", direction="min", warn=0.4, limit=0.3)
    check = _check("G3", rule, "conflict", 0.26, -0.04, [])
    block = _block(build_grounding_source(_brief([rule], [check])), "Part défensive minimale")
    assert "La mesure descend sous la limite fixée pour ce profil." in block
    assert "La mesure est sous la limite de 4 pts." in block
    assert "au-delà de la limite" not in block and "au-dessus" not in block


def test_missing_thresholds_are_not_invented():
    no_warn = _rule("R1", "max_single_asset_weight", "Concentration par actif", warn=None, limit=0.3)
    no_limit = _rule("R2", "max_portfolio_volatility", "Volatilité annuelle", warn=0.16, limit=None)
    checks = [_check("G1", no_warn, "compliant", 0.2, 0.1, []), _check("G2", no_limit, "tension", 0.2, None, [])]
    source = build_grounding_source(_brief([no_warn, no_limit], checks))
    block = _block(source, "Concentration par actif")
    assert "seuil d'attention" not in block
    assert "La mesure ne dépasse pas la limite fixée pour ce profil." in block
    assert "Marge avant la limite : 10 pts." in block
    tension = _block(source, "Volatilité annuelle")
    assert "La mesure dépasse le seuil d'attention du profil." in tension
    assert "limite" not in tension


def test_rule_missing_from_profile_gives_no_direction_sentence():
    rule = _rule("R9", "max_portfolio_volatility", "Volatilité annuelle")
    check = _check("G9", rule, "tension", 0.21, 0.01, [])
    source = build_grounding_source(_brief([], [check]))
    assert "La règle Volatilité annuelle est en tension." in source
    for guessed in ("Seuils", "La mesure", "Marge"):
        assert guessed not in source


def test_idea_sentence_reuses_display_wording():
    funded = {"ticker": "TSLA", "target_weight": 0.1, "funding_source": "from_ticker", "funding_ticker": "SPY"}
    source = build_grounding_source(_brief([], [], idea=funded))
    idea_line = next(line for line in source.splitlines() if line.startswith("Idée simulée"))
    assert idea_line == "Idée simulée : ajouter TSLA avec un poids cible de 10 % du portefeuille, financé par SPY."
    odd = {"ticker": "TSLA", "target_weight": 0.1, "funding_source": "autre", "funding_ticker": None}
    assert "financé selon la source choisie." in build_grounding_source(_brief([], [], idea=odd))


def test_variant_measures_are_labelled():
    source = build_grounding_source(make_brief())
    assert ("Variante simulée qui réduit la part de l'idée : verdict d'ensemble conforme. "
            "Mesures de cette variante : Perte maximale historique (variante) : 19,91 %.") in source


def test_disclaimers_and_assumption_notice_come_from_the_brief_and_fixed_texts():
    source = build_grounding_source(make_brief())
    for item in disclaimers("novice"):
        assert item["text"] in source
    assert "Les seuils des règles sont des hypothèses de l'équipe, pas des normes." in source
    brief = make_brief()
    for rule in brief["profile_rules"]:
        rule["is_assumption"] = False
    plain = build_grounding_source(brief)
    assert "hypothèses de l'équipe" not in plain
    assert "Seuils : seuil d'attention du profil de 20 %" in plain


def test_ranked_factors_come_first():
    source = build_grounding_source(make_brief())
    assert source.index("Contrôle Concentration par actif") < source.index("Contrôle Volatilité annuelle")
    assert source.index("Contrôle Volatilité annuelle") < source.index("Contrôle Part défensive minimale")


def test_no_number_is_added():
    """Chaque chiffre de la source vient du dossier : valeur affichée, seuil, marge ou date."""
    brief = make_brief()
    allowed = {e["display_value"] for e in brief["evidence"] if e["display_value"]}
    allowed |= {c["counterfactual"]["display_value"] for c in brief["checks"] if c["counterfactual"]}
    allowed |= {format_percent(r[k]) for r in brief["profile_rules"] for k in ("warn_threshold", "limit_threshold")
                if r[k] is not None}
    allowed |= {format_points(abs(c["margin"])) for c in brief["checks"] if c["margin"] is not None}
    allowed |= {format_percent(brief["idea"]["target_weight"])}
    source = build_grounding_source(brief)
    found = set(re.findall(r"\d+(?:,\d+)? (?:%|pts)", source))
    assert found <= allowed
    assert set(re.findall(r"\d{4}-\d{2}-\d{2}", source)) <= {"2021-11-12", "2026-11-12"}


def test_deterministic_and_input_untouched():
    brief = make_brief()
    snapshot = deepcopy(brief)
    assert build_grounding_source(brief) == build_grounding_source(brief)
    assert brief == snapshot


def test_real_offline_brief_fits_size_limit():
    from alphaforge.analysis_pipeline import run_analysis
    from alphaforge.pipeline_deps import resolve_deps
    from alphaforge.profiles import load_personas

    deps = resolve_deps()
    personas = load_personas()
    idea = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    for persona_id in ("robert", "mateo"):
        persona = personas[persona_id]
        result = run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline")
        for level in ("novice", "pro"):
            brief = deps.build_brief(result, level)
            source = build_grounding_source(brief)
            assert len(source) < GROUNDING_SOURCE_MAX_CHARS
            for check in brief["checks"]:
                assert f"Contrôle {check['label_fr']}" in source
            assert "reste sous" not in source
