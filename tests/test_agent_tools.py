"""Tests des outils de l'agent analyste (alphaforge.agent_tools), sur les personas fictifs et les donnees reelles."""
import copy
import time

import pytest

from alphaforge import agent_tools as tools
from alphaforge.contracts import EvidenceEntry, PortfolioSnapshot, ToolResult, check_keys
from alphaforge.data_loading import load_sources_metadata
from alphaforge.explanation_rendering import format_percent
from alphaforge.profiles import load_personas
from alphaforge.reference_texts import load_limits

PERSONAS = load_personas()
ROBERT = PERSONAS["robert"]["portfolio"]
AMIRA = PERSONAS["amira"]["portfolio"]
IDEA = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
EARLY = "2022-06-30"
SNAPSHOT_PCT_FIELDS = ("volatility_ann", "max_drawdown", "top_asset_weight", "defensive_share")


@pytest.fixture(scope="module")
def analyzed():
    return tools.analyze_portfolio(ROBERT)


@pytest.fixture(scope="module")
def simulated():
    return tools.simulate_portfolio_change(ROBERT, IDEA)


def by_metric(result):
    return {e["metric"]: e for e in result["evidence"]}


# --- Contrats ---

def test_contrats_analyze(analyzed):
    assert check_keys(analyzed, ToolResult) == []
    assert all(check_keys(e, EvidenceEntry) == [] for e in analyzed["evidence"])
    assert check_keys(analyzed["data"], PortfolioSnapshot) == []


def test_contrats_simulate(simulated):
    assert check_keys(simulated, ToolResult) == []
    assert all(check_keys(e, EvidenceEntry) == [] for e in simulated["evidence"])
    assert check_keys(simulated["data"]["before"], PortfolioSnapshot) == []
    assert check_keys(simulated["data"]["after"], PortfolioSnapshot) == []


@pytest.mark.parametrize("persona", ["amira", "mateo", "robert"])
def test_deux_premieres_preuves(persona):
    portfolio = PERSONAS[persona]["portfolio"]
    for result in (tools.analyze_portfolio(portfolio), tools.simulate_portfolio_change(portfolio, IDEA)):
        assert [e["metric"] for e in result["evidence"][:2]] == ["volatility_ann", "max_drawdown"]


# --- Valeurs ---

def check_values(result, snapshot):
    entries = by_metric(result)
    for field in SNAPSHOT_PCT_FIELDS:
        assert entries[field]["value"] == snapshot[field], f"{field} doit egaler le champ de la radiographie"
    for field in ("weight_by_asset_class", "weight_by_sector", "currency_exposure", "weights"):
        assert snapshot[field], f"{field} ne doit pas etre vide"
        for key, value in snapshot[field].items():
            assert entries[f"{field}.{key}"]["value"] == value
    for entry in result["evidence"]:
        if entry["unit"] == "pct" and isinstance(entry["value"], float):
            assert entry["display_value"] == format_percent(entry["value"]) or entry["metric"].endswith("_delta")


def test_valeurs_analyze(analyzed):
    check_values(analyzed, analyzed["data"])
    assert {e["subject"] for e in analyzed["evidence"]} == {"portfolio_before"}


def test_valeurs_simulate(simulated):
    check_values(simulated, simulated["data"]["after"])
    assert {e["subject"] for e in simulated["evidence"]} == {"portfolio_after"}, \
        "Aucune preuve portfolio_before dans simulate"


def test_simulate_deltas(simulated):
    before, after = simulated["data"]["before"], simulated["data"]["after"]
    entries = by_metric(simulated)
    for field in SNAPSHOT_PCT_FIELDS:
        expected = after[field] - before[field]
        assert entries[f"{field}_delta"]["value"] == pytest.approx(expected, abs=1e-9), field
    assert set(simulated["data"]) == {"before", "after"}
    assert simulated["data"]["before"]["subject"] == "portfolio_before"
    assert simulated["data"]["after"]["subject"] == "portfolio_after"


@pytest.mark.parametrize("fixture_name", ["analyzed", "simulated"])
def test_metrique_sujet_unique(request, fixture_name):
    result = request.getfixturevalue(fixture_name)
    pairs = [(e["metric"], e["subject"]) for e in result["evidence"]]
    assert len(pairs) == len(set(pairs)), "Un couple (metrique, sujet) doit designer une seule preuve"


# --- Limites et sources ---

def test_limites_et_sources_existent(analyzed, simulated):
    limits = {item["limit_id"] for item in load_limits()}
    sources = set(load_sources_metadata()["file"])
    facts = tools.get_asset_facts("TSLA")
    for result in (analyzed, simulated, facts):
        for entry in result["evidence"]:
            assert set(entry["limit_ids"]) <= limits, entry["evidence_key"]
            assert set(entry["source_ids"]) <= sources, entry["evidence_key"]


# --- Periode ---

def test_return_ann_omis_sous_252_rendements():
    result = tools.analyze_portfolio(ROBERT, as_of=EARLY)
    assert result["status"] == "ok"
    assert "return_ann" not in by_metric(result)
    n = by_metric(result)["volatility_ann"]["n_observations"]
    assert n < 252
    assert "return_ann" in by_metric(tools.analyze_portfolio(ROBERT)), "Present sur toute la fenetre"


def test_recuperation_non_recuperee():
    result = tools.get_asset_facts("TLT")
    assert result["status"] == "ok"
    entry = by_metric(result)["recovery_days"]
    if result["data"]["recovery_days"] is not None:
        pytest.skip("TLT s'est recupere : donnees modifiees")
    assert entry["value"] == "not_recovered"
    assert entry["unit"] == "text"


def test_recuperation_recuperee():
    entry = by_metric(tools.get_asset_facts("TSLA"))["recovery_days"]
    assert entry["unit"] == "days"
    assert isinstance(entry["value"], int)


def test_max_drawdown_cad_seulement_avec_capital():
    assert "max_drawdown_cad" not in by_metric(tools.analyze_portfolio(ROBERT))
    result = tools.analyze_portfolio(ROBERT, capital_cad=100000)
    entry = by_metric(result)["max_drawdown_cad"]
    assert entry["value"] == round(result["data"]["max_drawdown"] * 100000, 2)
    assert entry["unit"] == "cad"
    assert "max_drawdown_cad" not in by_metric(tools.simulate_portfolio_change(ROBERT, IDEA))
    assert "max_drawdown_cad" in by_metric(tools.simulate_portfolio_change(ROBERT, IDEA, capital_cad=100000))


def test_as_of_pas_de_periode_apres_la_date():
    result = tools.analyze_portfolio(ROBERT, as_of=EARLY)
    for entry in result["evidence"]:
        assert entry["as_of"] == EARLY
        if entry["period_end"] is not None:
            assert entry["period_end"] <= EARLY, "Aucune donnee posterieure a as_of"
    facts = tools.get_asset_facts("TSLA", as_of=EARLY)
    assert all(e["period_end"] <= EARLY for e in facts["evidence"])


def test_as_of_par_defaut_egale_fin_de_periode(analyzed):
    first = analyzed["evidence"][0]
    assert first["as_of"] == first["period_end"]


# --- Erreurs ---

@pytest.mark.parametrize("call,status", [
    (lambda: tools.simulate_portfolio_change(ROBERT, {**IDEA, "ticker": "bad ticker!"}), "error"),
    (lambda: tools.simulate_portfolio_change(ROBERT, {**IDEA, "ticker": "ZZZZ"}), "missing_info"),
    (lambda: tools.simulate_portfolio_change(ROBERT, {**IDEA, "target_weight": True}), "error"),
    (lambda: tools.simulate_portfolio_change(ROBERT, {**IDEA, "target_weight": "0.25"}), "error"),
    (lambda: tools.analyze_portfolio(ROBERT, as_of="pas une date"), "error"),
    (lambda: tools.analyze_portfolio(ROBERT, capital_cad=-5), "error"),
    (lambda: tools.analyze_portfolio(ROBERT, capital_cad=True), "error"),
    (lambda: tools.analyze_portfolio(ROBERT, as_of="2020-01-01"), "missing_info"),
    (lambda: tools.get_asset_facts("a b"), "error"),
    (lambda: tools.get_asset_facts(None), "error"),
    (lambda: tools.get_asset_facts("ZZZZ"), "missing_info"),
])
def test_statuts_d_erreur(call, status):
    result = call()
    assert result["status"] == status
    assert result["data"] == {}, "Jamais de donnees partielles"
    assert result["evidence"] == []
    assert result["error_message"]
    assert check_keys(result, ToolResult) == []


def test_message_d_erreur_ne_recopie_pas_la_saisie():
    secret = "<script>X9Q7_unique</script>"
    for result in (
        tools.get_asset_facts(secret),
        tools.analyze_portfolio(ROBERT, as_of=secret),
    ):
        assert result["status"] == "error"
        assert "X9Q7_unique" not in result["error_message"]
    assert len(tools.get_asset_facts("x" * 500)["error_message"]) <= tools.MAX_ERROR_LENGTH


def test_message_d_erreur_poids_vise_ne_recopie_pas_la_saisie():
    result = tools.simulate_portfolio_change(ROBERT, {**IDEA, "target_weight": "<script>X9Q7_unique</script>"})
    assert result["status"] == "error"
    assert "X9Q7_unique" not in result["error_message"]


def test_ticker_minuscule_avec_espaces_accepte():
    result = tools.get_asset_facts(" tsla ")
    assert result["status"] == "ok"
    assert result["params"]["ticker"] == "TSLA"
    sim = tools.simulate_portfolio_change(ROBERT, {**IDEA, "ticker": " tsla "})
    assert sim["status"] == "ok"


# --- Isolation et identifiants d'appel ---

def test_resultats_non_partages_entre_appels():
    first = tools.analyze_portfolio(AMIRA)
    reference = copy.deepcopy(first["evidence"][0]["display_value"])
    first["evidence"][0]["display_value"] = "MODIFIE"
    first["data"]["weights"]["NVDA"] = 99
    first["data"]["subject"] = "autre"
    second = tools.analyze_portfolio(AMIRA)
    assert second["evidence"][0]["display_value"] == reference
    assert second["data"]["weights"]["NVDA"] != 99
    assert second["data"]["subject"] == "portfolio_before"


def test_call_id_unique_et_prefixe():
    results = [tools.analyze_portfolio(ROBERT), tools.analyze_portfolio(ROBERT),
               tools.simulate_portfolio_change(ROBERT, IDEA), tools.get_asset_facts("TSLA"),
               tools.get_asset_facts("ZZZZ")]
    ids = [r["call_id"] for r in results]
    assert len(set(ids)) == len(ids)
    for result in results:
        assert result["call_id"].startswith(result["tool_name"] + "-")


# --- Performance ---

def test_deuxieme_simulation_identique_rapide():
    tools.simulate_portfolio_change(ROBERT, IDEA)
    start = time.perf_counter()
    tools.simulate_portfolio_change(ROBERT, IDEA)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"Deuxieme appel trop lent : {elapsed:.3f} s"


# --- Ajouts après relecture de code (as_of strict, params nettoyés, deltas traçables) ---

@pytest.mark.parametrize("bad", ["", "NaT", "now", "today", "2023/01/01", float("nan"), 20230101])
def test_as_of_invalide_donne_une_erreur_sans_lever(bad):
    """Formats de date refusés : statut error, jamais d'exception."""
    result = tools.analyze_portfolio(ROBERT, as_of=bad)
    assert result["status"] == "error"
    assert result["data"] == {} and result["evidence"] == []


def test_as_of_futur_refuse():
    """Une date après la fin des données est refusée (pas de date future dans les preuves)."""
    result = tools.analyze_portfolio(ROBERT, as_of="2035-01-01")
    assert result["status"] == "error"
    assert "postérieure" in result["error_message"]


def test_params_ne_contiennent_que_des_valeurs_nettoyees():
    """Saisies invalides : params sans texte brut ni nombre non fini (sérialisable sans NaN)."""
    import json

    long_text = "x" * 600
    bad = tools.simulate_portfolio_change(
        ROBERT, {**IDEA, "target_weight": float("nan"), "ticker": long_text}, as_of=long_text,
        capital_cad=float("inf"))
    assert bad["status"] == "error"
    json.dumps(bad, allow_nan=False)
    assert long_text not in json.dumps(bad)


def test_source_des_fonds_inconnue_non_recopiee():
    """Une source des fonds inconnue donne un message fixe, sans recopier la saisie."""
    result = tools.simulate_portfolio_change(ROBERT, {**IDEA, "funding_source": "<script>Z1</script>"})
    assert result["status"] == "error"
    assert "<script>" not in json_dump(result)


def json_dump(value):
    import json
    return json.dumps(value, ensure_ascii=False)


def test_funding_ticker_ignore_au_prorata():
    """Au prorata, un funding_ticker fantaisiste est ignoré (et non validé)."""
    result = tools.simulate_portfolio_change(ROBERT, {**IDEA, "funding_ticker": "???"})
    assert result["status"] == "ok"
    assert result["params"]["funding_ticker"] is None


def test_tracabilite_des_ecarts():
    """Écarts de volatilité et de perte : sources de prix et nombre d'observations ; composition sans période."""
    result = tools.simulate_portfolio_change(ROBERT, IDEA)
    deltas = {e["metric"]: e for e in result["evidence"] if e["metric"].endswith("_delta")}
    for metric in ("volatility_ann_delta", "max_drawdown_delta"):
        assert deltas[metric]["source_ids"] and deltas[metric]["n_observations"]
    assert deltas["defensive_share_delta"]["source_ids"] == ["assets_universe.csv"]
    for metric in ("defensive_share_delta", "top_asset_weight_delta"):
        assert deltas[metric]["period_start"] is None and deltas[metric]["currency"] is None


def test_faits_d_actif_sans_date_de_recuperation():
    """`recovery_date` n'a pas de preuve dédiée : il n'est pas exposé dans les données."""
    assert "recovery_date" not in tools.get_asset_facts("SPY")["data"]
