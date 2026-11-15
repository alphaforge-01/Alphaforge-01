"""Tests du plus grand groupe corrélé (US-18) : corrélations calculées à la main, puis cas réels."""
from __future__ import annotations

import pandas as pd
import pytest

from alphaforge import diversification as div
from alphaforge.diversification import MIN_OBSERVATIONS, correlated_group, largest_correlated_group

# A = [1,-1,1,-1], B = 2A (corrélation 1 avec A), C = [1,1,-1,-1] (corrélation 0 avec A),
# D = A + C (corrélation 1/racine(2), soit 0,707, avec A et avec C).
PATTERN = {"A": [1, -1, 1, -1], "B": [2, -2, 2, -2], "C": [1, 1, -1, -1], "D": [2, 0, 0, -2]}


def returns(repeat: int = MIN_OBSERVATIONS // 4 + 1, **overrides) -> pd.DataFrame:
    data = {name: values * repeat for name, values in {**PATTERN, **overrides}.items()}
    return pd.DataFrame(data, dtype=float)


EQUAL = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}


def test_seuil_08_donne_le_groupe_a_et_b():
    weight, members = largest_correlated_group(returns(), EQUAL, threshold=0.8)
    assert members == ["A", "B"]
    assert weight == pytest.approx(0.5)


def test_seuil_07_chaine_tous_les_titres_en_un_groupe():
    # 0,707 >= 0,7 : D relie A et C ; la liaison simple met les quatre titres ensemble.
    weight, members = largest_correlated_group(returns(), EQUAL, threshold=0.7)
    assert members == ["A", "B", "C", "D"]
    assert weight == pytest.approx(1.0)


def test_aucun_groupe_donne_zero():
    assert largest_correlated_group(returns(), {"A": 0.5, "C": 0.5}, threshold=0.8) == (0.0, [])


def test_un_seul_titre_donne_zero_sans_charger_de_donnees():
    assert largest_correlated_group(returns(), {"A": 1.0}) == (0.0, [])
    assert correlated_group({"A": 1.0}) == (0.0, [])


def test_titres_sans_poids_ignores():
    weight, members = largest_correlated_group(returns(), {"A": 0.5, "B": 0.5, "C": 0.0, "D": 0.0}, 0.8)
    assert members == ["A", "B"] and weight == pytest.approx(1.0)


def test_serie_plate_nest_jamais_un_lien():
    flat = returns(A=[0, 0, 0, 0], B=[0, 0, 0, 0])
    assert largest_correlated_group(flat, {"A": 0.5, "B": 0.5}, 0.8) == (0.0, [])


def test_trop_peu_dobservations_donne_none():
    short = returns(repeat=1)
    assert len(short) < MIN_OBSERVATIONS
    assert largest_correlated_group(short, EQUAL, 0.8) == (None, [])


def test_egalite_de_poids_choisit_la_liste_triee_la_plus_petite():
    # Deux paires de même poids : A-B (B = 2A) et C-E (E = 3C), A et C décorrélés.
    data = returns(E=[3 * v for v in PATTERN["C"]])[["A", "B", "C", "E"]]
    weight, members = largest_correlated_group(data, {"A": 0.25, "B": 0.25, "C": 0.25, "E": 0.25}, 0.8)
    assert members == ["A", "B"] and weight == pytest.approx(0.5)


def test_types_natifs():
    weight, members = largest_correlated_group(returns(), EQUAL, 0.8)
    assert type(weight) is float and all(type(member) is str for member in members)


# --- Cas réels (données du jeu de départ, aucun appel AWS) ---

def test_amira_avant_lidee_le_groupe_est_qqq_spy():
    from alphaforge.profiles import load_personas
    from alphaforge.portfolio import build_snapshot

    snapshot = build_snapshot(load_personas()["amira"]["portfolio"], "portfolio_before")
    assert snapshot["correlated_group_members"] == ["QQQ", "SPY"]
    assert snapshot["largest_correlated_group_weight"] == pytest.approx(0.30, abs=0.02)


def test_quarante_pour_cent_btc_forme_le_groupe_crypto_et_met_la_regle_en_tension():
    from alphaforge.agent_tools import simulate_portfolio_change
    from alphaforge.governance import evaluate
    from alphaforge.profiles import load_personas

    amira = load_personas()["amira"]
    idea = {"ticker": "BTC-USD", "target_weight": 0.40, "funding_source": "pro_rata", "funding_ticker": None}
    outcome = simulate_portfolio_change(amira["portfolio"], idea, capital_cad=amira["profile"]["capital_cad"])
    assert outcome["status"] == "ok"
    after = outcome["data"]["after"]
    assert set(after["correlated_group_members"]) == {"BTC-USD", "ETH-USD"}
    assert after["largest_correlated_group_weight"] > 0.35
    check = next(c for c in evaluate(amira["profile"], after)["checks"]
                 if c["rule_type"] == "max_correlated_group_weight")
    assert check["status"] in ("tension", "conflict")
    entry = next(e for e in outcome["evidence"] if e["metric"] == "largest_correlated_group_weight")
    assert entry["period_start"] and entry["n_observations"] >= MIN_OBSERVATIONS and entry["currency"] == "CAD"


def test_robert_et_mateo_nont_pas_la_regle_mais_ont_la_mesure():
    from alphaforge.portfolio import build_snapshot
    from alphaforge.profiles import load_personas

    for persona in ("robert", "mateo"):
        entry = load_personas()[persona]
        assert all(r["rule_type"] != "max_correlated_group_weight" for r in entry["profile"]["rules"])
        assert build_snapshot(entry["portfolio"], "portfolio_before")["largest_correlated_group_weight"] is not None
