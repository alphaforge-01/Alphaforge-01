"""Graphiques de l'interface v2 (PR-3) : app/components/charts.py.

Les données tracées sont vérifiées par les fonctions `*_records`, la spécification Altair par
`to_dict()` (qui la valide contre le schéma Vega-Lite), le rendu par `AppTest`. Règle centrale :
une valeur `None` reste inconnue, la barre est omise et la phrase "Non disponible" le dit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import ui_labels as labels  # noqa: E402
import view_models as vm  # noqa: E402
from components import charts  # noqa: E402

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


@pytest.fixture(scope="module")
def view():
    from alphaforge.analysis_pipeline import run_analysis
    from alphaforge.bedrock_client import BedrockConfig
    from alphaforge.profiles import load_personas

    persona = load_personas()["robert"]
    idea = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
    result = run_analysis(persona["profile"], persona["portfolio"], idea, mode="offline",
                          config=BedrockConfig())
    return vm.build_result_view(result, {"TSLA": "Tesla"})


def _dataset(chart):
    """Premier jeu de données de la spécification : celui que le graphique trace réellement."""
    datasets = chart.to_dict()["datasets"]
    return next(iter(datasets.values()))


def _row(ticker="AAA", before=0.2, after=0.3):
    return vm.WeightRow(ticker, ticker, before, f"{before:.0%}" if before is not None else None,
                        after, f"{after:.0%}" if after is not None else None)


def _bar(**overrides):
    base = dict(check_id="G1", label="Concentration", value=0.25, value_display="25 %", warn=0.2,
                limit=0.22, warn_display="20 %", limit_display="22 %", direction="max",
                status="conflict", status_label="Conflit")
    base.update(overrides)
    return vm.ThresholdBar(**base)


def _variant(row_id="V1", volatility=0.13, drawdown=0.2, status="compliant", weight="17 %",
             reason="réduire le poids"):
    return vm.VariantRow(
        row_id=row_id, reason_code=None if row_id == "initial" else "reduce_weight",
        reason_label=None if row_id == "initial" else reason, target_weight_display=weight,
        status=status, status_label={"compliant": "Conforme", "conflict": "Conflit"}.get(status, status),
        volatility=volatility, volatility_display=None if volatility is None else f"{volatility:.0%}",
        max_drawdown=drawdown, max_drawdown_display=None if drawdown is None else f"{drawdown:.0%}")


# --- 1. Composition ------------------------------------------------------------

def test_weight_records_match_view_rows(view):
    records, missing_before, missing_after = charts.weight_records(view.weight_rows)
    by_key = {(r["ticker"], r["series"]): r for r in records}
    for row in view.weight_rows:
        if row.after is not None:
            assert by_key[(row.ticker, labels.SERIES_AFTER)]["value"] == row.after
            assert by_key[(row.ticker, labels.SERIES_AFTER)]["display"] == row.after_display
        if row.before is not None:
            assert by_key[(row.ticker, labels.SERIES_BEFORE)]["value"] == row.before
    assert "TSLA" in missing_before and missing_after == []


def test_weight_missing_value_is_omitted_never_zero():
    records, missing_before, missing_after = charts.weight_records([_row("AAA", None, 0.3)])
    assert [r["series"] for r in records] == [labels.SERIES_AFTER]
    assert all(r["value"] != 0 for r in records)
    assert missing_before == ["AAA"] and missing_after == []


def test_weight_row_without_any_value_has_no_record():
    records, before, after = charts.weight_records([_row("AAA", None, None)])
    assert records == [] and before == ["AAA"] and after == ["AAA"]
    assert charts.weight_chart([_row("AAA", None, None)]) is None


def test_weight_real_zero_is_kept():
    records, _, _ = charts.weight_records([vm.WeightRow("AAA", "AAA", 0.0, "0 %", 0.5, "50 %")])
    assert {"value": 0.0} .items() <= next(r for r in records if r["series"] == labels.SERIES_BEFORE).items()


def test_weight_chart_spec_is_valid_and_traces_the_records(view):
    chart = charts.weight_chart(view.weight_rows)
    records, _, _ = charts.weight_records(view.weight_rows)
    assert len(_dataset(chart)) == len(records)
    assert chart.to_dict()["layer"]


def test_weight_chart_empty():
    assert charts.weight_chart([]) is None


# --- 2. Seuils -----------------------------------------------------------------

def test_threshold_records_follow_bars(view):
    measures, marks = charts.threshold_records(view.threshold_bars)
    assert [m["value"] for m in measures] == [b.value for b in view.threshold_bars]
    limits = [m["value"] for m in marks if m["mark"] == labels.THRESHOLD_LIMIT]
    assert limits == [b.limit for b in view.threshold_bars]
    warns = [m for m in marks if m["mark"] == labels.THRESHOLD_WARN]
    assert len(warns) == sum(b.warn is not None for b in view.threshold_bars)


def test_threshold_without_warn_threshold_has_only_limit_mark():
    _, marks = charts.threshold_records([_bar(warn=None, warn_display=None)])
    assert [m["mark"] for m in marks] == [labels.THRESHOLD_LIMIT]


def test_threshold_direction_text_for_novices():
    measures, _ = charts.threshold_records([_bar(direction="min")])
    assert measures[0]["direction"] == labels.THRESHOLD_DIRECTION["min"]


def test_threshold_chart_spec_is_valid(view):
    chart = charts.threshold_chart(view.threshold_bars)
    spec = chart.to_dict()
    assert len(spec["layer"]) == 3
    assert spec["resolve"]["scale"]["color"] == "independent"


def test_threshold_chart_domain_covers_every_value():
    bars = [_bar(value=0.9, limit=0.3, warn=0.2)]
    domain = charts.threshold_chart(bars).to_dict()["layer"][0]["encoding"]["x"]["scale"]["domain"]
    assert domain[0] == 0 and domain[1] >= 0.9


def test_threshold_chart_empty():
    assert charts.threshold_chart([]) is None


def test_percent_ticks_cover_maximum():
    ticks = charts._percent_ticks(0.31)
    assert ticks[0] == 0 and ticks[-1] >= 0.31 and ticks == sorted(ticks)
    assert charts._percent_ticks(0.9)[1] == 0.1


# --- 3. Variantes --------------------------------------------------------------

def test_variant_row_labels(view):
    labels_ = [charts.variant_row_label(r) for r in view.variant_rows]
    assert labels_[0].startswith("Idée initiale (25 %)")
    assert labels_[0].endswith("Conflit")
    assert labels_[1] == "V1 : réduire le poids (17 %), Conforme"
    assert len(set(labels_)) == len(labels_)


def test_variant_label_without_weight_or_reason():
    row = vm.VariantRow("V9", None, None, "", "compliant", "Conforme", None, None, None, None)
    assert charts.variant_row_label(row) == "V9, Conforme"


def test_variant_records_follow_view(view):
    records, missing = charts.variant_records(view.variant_rows)
    assert {r["value"] for r in records} == (
        {r.volatility for r in view.variant_rows if r.volatility is not None}
        | {r.max_drawdown for r in view.variant_rows if r.max_drawdown is not None})
    assert missing[labels.VARIANT_VOLATILITY] == [] and missing[labels.VARIANT_DRAWDOWN] == []


def test_variant_missing_measure_is_omitted_never_zero():
    rows = [_variant("initial", 0.17, 0.26, "conflict", "25 %"), _variant("V1", None, 0.2)]
    records, missing = charts.variant_records(rows)
    assert missing[labels.VARIANT_VOLATILITY] == ["V1"]
    assert not [r for r in records if r["row"].startswith("V1") and r["measure"] == labels.VARIANT_VOLATILITY]
    assert all(r["value"] > 0 for r in records)


def test_variant_chart_spec_is_valid(view):
    chart = charts.variant_chart(view.variant_rows)
    assert chart.to_dict()["layer"]
    assert len(_dataset(chart)) == len(charts.variant_records(view.variant_rows)[0])


def test_variant_chart_none_without_any_measure():
    rows = [_variant("initial", None, None), _variant("V1", None, None)]
    assert charts.variant_chart(rows) is None


# --- Rendu Streamlit -----------------------------------------------------------

SCRIPT = """
import sys
sys.path.insert(0, {app!r})
import view_models as vm
from components import charts
charts.render_weight_comparison({weights})
charts.render_threshold_chart({bars})
charts.render_variant_comparison({variants})
"""


def _run(weights, bars, variants):
    script = SCRIPT.format(app=str(APP_DIR), weights=weights, bars=bars, variants=variants)
    return AppTest.from_string(script, default_timeout=60).run()


W = "[vm.WeightRow('AAA','Alpha',None,None,0.3,'30 %'), vm.WeightRow('BBB','Beta',0.2,'20 %',0.2,'20 %')]"
B = ("[vm.ThresholdBar('G1','Concentration',0.25,'25 %',0.2,0.22,'20 %','22 %','max','conflict','Conflit')]")
V = ("[vm.VariantRow('initial',None,None,'25 %','conflict','Conflit',0.17,'17 %',None,None),"
     "vm.VariantRow('V1','reduce_weight','réduire le poids','17 %','compliant','Conforme',0.13,'13 %',0.2,'20 %')]")


def test_render_all_charts_with_missing_values():
    at = _run(W, B, V)
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.get("vega_lite_chart")) == 3
    captions = [c.value for c in at.caption]
    assert labels.WEIGHTS_MISSING.format(side=labels.WEIGHTS_MISSING_BEFORE, tickers="AAA") in captions
    assert labels.VARIANTS_MISSING.format(measure="perte maximale historique", rows="initial") in captions
    assert labels.THRESHOLDS_CAPTION in captions
    titles = [m.value for m in at.markdown]
    assert f"**{labels.WEIGHTS_TITLE}**" in titles
    assert f"**{labels.THRESHOLDS_TITLE}**" in titles
    assert f"**{labels.VARIANTS_TITLE}**" in titles


def test_render_empty_inputs_say_not_available_without_exception():
    at = _run("[]", "[]", "[]")
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.get("vega_lite_chart")) == 0
    captions = [c.value for c in at.caption]
    assert labels.WEIGHTS_EMPTY in captions
    assert labels.THRESHOLDS_EMPTY in captions
    assert labels.VARIANTS_EMPTY in captions


def test_render_single_row_variants_say_none_proposed():
    at = _run("[]", "[]", "[vm.VariantRow('initial',None,None,'25 %','conflict','Conflit',0.17,'17 %',0.2,'20 %')]")
    assert labels.VARIANTS_NONE_PROPOSED in [c.value for c in at.caption]


def test_charts_module_is_not_wired_to_state_or_data():
    source = (APP_DIR / "components" / "charts.py").read_text(encoding="utf-8")
    for forbidden in ("session", "data_source", "boto3", "requests", "random", "numpy"):
        assert forbidden not in source
