"""Test strict de `as_of` : supprimer physiquement les données postérieures ne change rien.

Les tests existants comparent `f(as_of=X)` à `f(full).loc[:X]` sur les MEMES
fichiers complets. Ici, pour plusieurs dates de coupure, on fabrique une copie de
data/raw/ dont les fichiers de prix, de change et de macro sont tronqués aux
lignes datées au plus de la coupure, puis on compare :

- fichiers tronqués, `as_of=None` ;
- fichiers complets, `as_of=coupure`.

Les deux doivent donner le même résultat (rendements CAD, métriques des
portefeuilles des personas, sorties et preuves des outils de l'agent). Cela
prouve qu'aucune donnée postérieure à `as_of` n'est lue nulle part : ni au
chargement, ni dans l'intersection des calendriers, ni dans le report du taux de
change (jours fériés canadiens), ni dans les caches.

Les coupures couvrent un mercredi (2022-06-15), un samedi (2023-07-01, la
dernière ligne est alors le vendredi précédent) et le lundi 2023-10-02, jour sans
taux de change publié (taux reporté du vendredi).

Limite connue : les `adj_close` du fichier sont rétro-ajustés à partir du
téléchargement de 2026, donc une copie tronquée porte encore, dans ses NIVEAUX,
les ajustements de dividendes ultérieurs. Seuls des rapports (rendements, pertes
maximales) sont utilisés, et ils n'en sont pas affectés. Ce test ne peut donc pas
détecter un biais d'anticipation fondé sur les niveaux de prix ; il est exclu par
conception (le docstring de calendar_alignment interdit d'utiliser les niveaux).
"""

import math
import shutil

import pandas as pd
import pytest

from alphaforge import agent_tools, data_loading
from alphaforge import calendar_alignment as calendar
from alphaforge.portfolio import build_snapshot_with_metrics
from alphaforge.profiles import load_personas

CUTOFFS = ["2022-06-15", "2023-07-01", "2023-10-02"]
EXPECTED_LAST_ROW = {"2022-06-15": "2022-06-15", "2023-07-01": "2023-06-30", "2023-10-02": "2023-10-02"}
IDEA = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
TRUNCATED_FILES = ("prices_daily.csv", "fx_usdcad_daily.csv", "macro_rates.csv")
COPIED_FILES = ("assets_universe.csv", "sources_metadata.csv")
FLOAT_TOLERANCE = 1e-10
PERSONAS = load_personas()


def _clear_all_caches():
    agent_tools.clear_caches()  # vide aussi les caches de l'alignement et du chargement
    data_loading.clear_caches()


def _truncate_raw(cutoff: str, target):
    """Copie de data/raw/ avec les fichiers datés tronqués à `date <= cutoff`."""
    target.mkdir(parents=True)
    for name in COPIED_FILES:
        shutil.copy(data_loading.RAW_DIR / name, target / name)
    for name in TRUNCATED_FILES:
        source = data_loading.RAW_DIR / name
        if not source.exists():
            continue
        frame = pd.read_csv(source, dtype=str, keep_default_na=False)  # texte inchangé
        keep = pd.to_datetime(frame["date"]) <= pd.Timestamp(cutoff)
        frame.loc[keep].to_csv(target / name, index=False, lineterminator="\n")


def _evidence_view(result):
    """Preuves sans `evidence_id` ni `as_of` (leur sémantique diffère entre les deux cas)."""
    return [{k: v for k, v in entry.items() if k not in ("evidence_id", "as_of")}
            for entry in result["evidence"]]


def _tools_outputs(as_of):
    robert = PERSONAS["robert"]["portfolio"]
    return {
        "analyze": agent_tools.analyze_portfolio(robert, as_of=as_of),
        "simulate": agent_tools.simulate_portfolio_change(robert, IDEA, as_of=as_of),
        "facts": agent_tools.get_asset_facts("TSLA", as_of=as_of),
    }


def _compute(as_of):
    """Tout ce que l'on compare, calculé avec les fichiers actuellement pointés."""
    returns = calendar.daily_cad_returns(as_of=as_of)
    snapshots = {}
    for persona_id, persona in PERSONAS.items():
        snapshot, metrics = build_snapshot_with_metrics(persona["portfolio"], persona_id, as_of)
        snapshots[persona_id] = (snapshot, metrics.to_dict())
    return {
        "returns": returns,
        "base_date": calendar.returns_base_date(as_of=as_of),
        "snapshots": snapshots,
        "tools": _tools_outputs(as_of),
    }


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory):
    """Pour chaque coupure : résultats « complet + as_of » et « tronqué + as_of None »."""
    patcher = pytest.MonkeyPatch()
    outcomes = {}
    try:
        _clear_all_caches()
        full = {cutoff: _compute(cutoff) for cutoff in CUTOFFS}
        for cutoff in CUTOFFS:
            raw_dir = tmp_path_factory.mktemp("raw") / "raw"
            _truncate_raw(cutoff, raw_dir)
            patcher.setattr(data_loading, "RAW_DIR", raw_dir)
            patcher.setattr(data_loading, "UNIVERSE_FILE", raw_dir / "assets_universe.csv")
            patcher.setattr(data_loading, "PRICES_FILE", raw_dir / "prices_daily.csv")
            patcher.setattr(data_loading, "FX_FILE", raw_dir / "fx_usdcad_daily.csv")
            patcher.setattr(data_loading, "SOURCES_FILE", raw_dir / "sources_metadata.csv")
            _clear_all_caches()
            truncated = _compute(None)
            outcomes[cutoff] = {"full": full[cutoff], "truncated": truncated}
            patcher.undo()
            _clear_all_caches()
    finally:
        patcher.undo()
        _clear_all_caches()
    return outcomes


def _assert_close(left, right, path="racine"):
    """Égalité récursive, avec tolérance sur les nombres à virgule."""
    if isinstance(left, dict):
        assert isinstance(right, dict) and left.keys() == right.keys(), f"clés différentes en {path}"
        for key in left:
            _assert_close(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, (list, tuple)):
        assert len(left) == len(right), f"longueurs différentes en {path}"
        for index, (a, b) in enumerate(zip(left, right)):
            _assert_close(a, b, f"{path}[{index}]")
    elif isinstance(left, float) and isinstance(right, float):
        assert math.isclose(left, right, rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE), (
            f"valeurs différentes en {path} : {left} contre {right}")
    else:
        assert left == right, f"valeurs différentes en {path} : {left!r} contre {right!r}"


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_rendements_et_date_de_base_identiques(scenarios, cutoff):
    full, truncated = scenarios[cutoff]["full"], scenarios[cutoff]["truncated"]
    pd.testing.assert_index_equal(full["returns"].index, truncated["returns"].index)
    assert list(full["returns"].columns) == list(truncated["returns"].columns)
    diff = (full["returns"] - truncated["returns"]).abs().to_numpy().max()
    assert diff <= 1e-12, f"écart maximal de rendement {diff} (coupure {cutoff})"
    assert full["base_date"] == truncated["base_date"]
    assert truncated["returns"].index[-1] == pd.Timestamp(EXPECTED_LAST_ROW[cutoff])


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_metriques_des_personas_identiques(scenarios, cutoff):
    full, truncated = scenarios[cutoff]["full"], scenarios[cutoff]["truncated"]
    assert full["snapshots"].keys() == truncated["snapshots"].keys() == PERSONAS.keys()
    _assert_close(full["snapshots"], truncated["snapshots"])
    for _, metrics in truncated["snapshots"].values():
        assert metrics["period_end"] == EXPECTED_LAST_ROW[cutoff], "la période doit finir au dernier jour de bourse"


@pytest.mark.parametrize("tool", ["analyze", "simulate", "facts"])
@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_outils_identiques(scenarios, cutoff, tool):
    full = scenarios[cutoff]["full"]["tools"][tool]
    truncated = scenarios[cutoff]["truncated"]["tools"][tool]
    assert full["status"] == truncated["status"] == "ok", (full["error_message"], truncated["error_message"])
    _assert_close(full["data"], truncated["data"])
    _assert_close(_evidence_view(full), _evidence_view(truncated))
    assert full["evidence"], "les outils doivent produire des preuves"
    # Fichiers complets : as_of = coupure ; fichiers tronqués : as_of = fin de période
    assert {e["as_of"] for e in full["evidence"]} == {cutoff}
    assert {e["as_of"] for e in truncated["evidence"]} == {EXPECTED_LAST_ROW[cutoff]}
    for a, b in zip(full["evidence"], truncated["evidence"]):
        assert a["period_end"] == b["period_end"]
        if a["period_end"] is not None:  # les preuves de composition n'ont pas de période
            assert pd.Timestamp(a["period_end"]) <= pd.Timestamp(cutoff)


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_aucune_date_posterieure_a_la_coupure(scenarios, cutoff):
    full = scenarios[cutoff]["full"]
    limit = pd.Timestamp(cutoff)
    for result in full["tools"].values():
        for entry in result["evidence"]:
            for field in ("period_start", "period_end", "as_of"):
                if entry[field] is not None:
                    assert pd.Timestamp(entry[field]) <= limit, f"{field} après la coupure : {entry['evidence_key']}"
    snapshots = [s for s, _ in full["snapshots"].values()]
    snapshots += [full["tools"]["analyze"]["data"], *full["tools"]["simulate"]["data"].values()]
    for snapshot in snapshots:
        assert pd.Timestamp(snapshot["max_drawdown_start"]) <= limit
        assert pd.Timestamp(snapshot["max_drawdown_end"]) <= limit
    assert full["returns"].index.max() <= limit


def test_les_chemins_et_les_caches_sont_restaures(scenarios):
    """Après la fixture, le code relit bien les vrais fichiers complets."""
    assert scenarios
    assert str(data_loading.PRICES_FILE).replace("\\", "/").endswith("data/raw/prices_daily.csv")
    assert data_loading.load_prices()["date"].max() > pd.Timestamp("2025-01-01")
