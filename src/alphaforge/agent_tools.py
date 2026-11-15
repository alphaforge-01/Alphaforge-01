"""Outils déterministes de l'agent analyste (flux A, tâche A5).

Trois outils, appelés par le pipeline du flux C (`pipeline_deps.PipelineDeps`) :

- `analyze_portfolio(portfolio, as_of=None, capital_cad=None)` : radiographie
  du portefeuille fictif de départ (sujet `portfolio_before`) ;
- `simulate_portfolio_change(portfolio, idea, as_of=None, capital_cad=None)` :
  portefeuille après l'idée ; `data = {"before", "after"}`, preuves du sujet
  `portfolio_after` seulement (les preuves "avant" viennent d'`analyze_portfolio`,
  pour qu'un couple métrique et sujet désigne une seule preuve) ;
- `get_asset_facts(ticker, as_of=None)` : faits historiques d'un actif.

Chaque outil rend un `ToolResult`. Statuts : `ok` ; `error` pour une entrée
invalide (message en français) ; `missing_info` si les données manquent. Hors
`ok`, `data` est vide et il n'y a aucune preuve : jamais de données partielles.

Les outils décrivent le passé sur une période explicite. Ils ne prédisent rien,
ne recommandent rien et ne passent aucun ordre : tout est simulé.
"""

from __future__ import annotations

import copy
import math
import re
import uuid
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd

from alphaforge import calendar_alignment
from alphaforge.calendar_alignment import MissingPriceError, NoDataError, daily_cad_returns, returns_base_date
from alphaforge.contracts import EvidenceEntry, InvestmentIdea, Portfolio, PortfolioSnapshot, ToolResult
from alphaforge.data_loading import load_universe
from alphaforge.evidence import (
    ALL_LIMITS,
    NOT_RECOVERED,
    NOT_RECOVERED_FR,
    PRICE_SOURCES,
    UNIVERSE_SOURCES,
    format_cad,
    format_days,
    format_signed_points,
    make_entry,
    percent_display,
)
from alphaforge.fx_conversion import BASE_CURRENCY, MissingFxRateError
from alphaforge.metrics import InsufficientDataError, ReturnMetrics, compute_return_metrics
from alphaforge.portfolio import (
    PortfolioError,
    UnknownTickerError,
    apply_idea,
    build_snapshot_with_metrics,
    portfolio_weights,
)

TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,12}$")
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FUNDING_SOURCES = ("pro_rata", "from_ticker")
MAX_ERROR_LENGTH = 200
SNAPSHOT_CACHE_SIZE = 1024
MISSING_DATA_ERRORS = (InsufficientDataError, MissingPriceError, MissingFxRateError, NoDataError)

ASSET_FACT_LIMITS = ["LM1", "LM2", "LM3", "LM5"]
WEIGHT_LIMITS = ["LM4"]
CORRELATION_LIMITS = ["LM1", "LM2", "LM3", "LM4"]
COMPOSITION_LIMITS = ["LM1", "LM4"]
CURRENCY_LIMITS = ["LM3", "LM4"]
DELTA_METRICS = ("volatility_ann", "max_drawdown", "top_asset_weight", "defensive_share")


class ToolInputError(ValueError):
    """Paramètre d'outil invalide (message en français, sans recopier la saisie)."""


# --- Entrées -------------------------------------------------------------------

def _clean_ticker(raw: Any) -> str:
    if not isinstance(raw, str):
        raise ToolInputError("Le symbole de l'actif doit être une chaîne de caractères")
    ticker = raw.strip().upper()
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ToolInputError("Symbole d'actif mal formé")
    return ticker


def _clean_as_of(raw: Any) -> str | None:
    """Date AAAA-MM-JJ (ou date, Timestamp), au plus la dernière date des données."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if not ISO_DATE_PATTERN.fullmatch(raw.strip()):
            raise ToolInputError("Date de référence `as_of` attendue au format AAAA-MM-JJ")
        raw = raw.strip()
    elif not isinstance(raw, (date, pd.Timestamp)):
        raise ToolInputError("Date de référence `as_of` attendue au format AAAA-MM-JJ")
    try:
        stamp = pd.Timestamp(raw)
    except (TypeError, ValueError, AttributeError):
        raise ToolInputError("Date de référence `as_of` illisible") from None
    if pd.isna(stamp):
        raise ToolInputError("Date de référence `as_of` illisible")
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    stamp = stamp.normalize()
    if stamp > _last_data_date():
        raise ToolInputError("Date de référence `as_of` postérieure aux données disponibles")
    return stamp.date().isoformat()


def _last_data_date() -> pd.Timestamp:
    return calendar_alignment.aligned_cad_prices().index[-1]


def _clean_target(raw: Any) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
        raise ToolInputError("Le poids visé doit être un nombre fini")
    if not 0.0 <= float(raw) <= 1.0:
        raise ToolInputError("Le poids visé doit être compris entre 0 % et 100 %")
    return float(raw)


def _clean_funding_source(raw: Any) -> str:
    if raw not in FUNDING_SOURCES:
        raise ToolInputError("Source des fonds attendue : pro_rata ou from_ticker")
    return raw


def _clean_capital(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
        raise ToolInputError("Le capital fictif doit être un nombre")
    if raw < 0:
        raise ToolInputError("Le capital fictif doit être positif ou nul")
    return float(raw)


def _clean_portfolio_id(portfolio: dict) -> str | None:
    raw = portfolio.get("portfolio_id")
    if isinstance(raw, str) and re.fullmatch(r"[A-Za-z0-9_:\-]{1,64}", raw):
        return raw
    return None


def _known_tickers() -> set[str]:
    return set(load_universe()["ticker"])


# --- Résultats -----------------------------------------------------------------

def _new_call_id(tool_name: str) -> str:
    return f"{tool_name}-{uuid.uuid4().hex[:8]}"


def _result(tool_name: str, params: dict, data: dict, evidence: list[EvidenceEntry]) -> ToolResult:
    return ToolResult(tool_name=tool_name, call_id=_new_call_id(tool_name), params=params,
                      status="ok", error_message=None, data=data, evidence=evidence)


def _failure(tool_name: str, params: dict, status: str, message: str) -> ToolResult:
    return ToolResult(tool_name=tool_name, call_id=_new_call_id(tool_name), params=params,
                      status=status, error_message=message[:MAX_ERROR_LENGTH], data={}, evidence=[])


def _guarded(tool_name: str, params: dict, compute) -> ToolResult:
    """Exécute `compute` et convertit les erreurs connues en statut ; les autres remontent."""
    try:
        return compute()
    except ToolInputError as error:
        return _failure(tool_name, params, "error", str(error))
    except UnknownTickerError:
        return _failure(tool_name, params, "missing_info", "Actif absent de l'univers de données")
    except PortfolioError as error:
        return _failure(tool_name, params, "error", str(error))
    except MISSING_DATA_ERRORS as error:
        return _failure(tool_name, params, "missing_info", f"Données insuffisantes : {error}")


# --- Cache des radiographies ---------------------------------------------------

@lru_cache(maxsize=SNAPSHOT_CACHE_SIZE)
def _cached_snapshot(weights_key: tuple[tuple[str, float], ...], as_of: str | None):
    portfolio = {"portfolio_id": "cache", "positions": [{"ticker": t, "weight": w} for t, w in weights_key]}
    return build_snapshot_with_metrics(portfolio, "cache", as_of)


def _snapshot(portfolio: Portfolio, subject: str, as_of: str | None) -> tuple[PortfolioSnapshot, ReturnMetrics]:
    weights = portfolio_weights(portfolio)
    key = tuple(sorted((str(t), round(float(w), 10)) for t, w in weights.items()))
    snapshot, metrics = _cached_snapshot(key, as_of)
    snapshot = copy.deepcopy(snapshot)
    snapshot["subject"] = subject
    return snapshot, metrics


@lru_cache(maxsize=SNAPSHOT_CACHE_SIZE)
def _cached_asset_metrics(ticker: str, as_of: str | None) -> ReturnMetrics:
    returns = daily_cad_returns(as_of=as_of, tickers=[ticker])[ticker]
    return compute_return_metrics(returns, returns_base_date(as_of))


def clear_caches() -> None:
    """Vide les caches des outils et des données (si data/raw/ change)."""
    _cached_snapshot.cache_clear()
    _cached_asset_metrics.cache_clear()
    calendar_alignment.clear_caches()


# --- Preuves ---------------------------------------------------------------------

def _series_entries(tool: str, subject: str, metrics: ReturnMetrics, as_of: str,
                    limits: list[str], capital_cad: float | None) -> list[EvidenceEntry]:
    """Preuves calculées sur une série de rendements (période explicite, devise CAD)."""
    common = dict(tool_name=tool, subject=subject, as_of=as_of, limit_ids=limits,
                  period_start=metrics.period_start, period_end=metrics.period_end,
                  n_observations=metrics.n_observations, currency=BASE_CURRENCY,
                  source_ids=PRICE_SOURCES)
    entries = [
        make_entry(metric="volatility_ann", value=metrics.volatility_ann,
                   display_value=percent_display(metrics.volatility_ann), **common),
        make_entry(metric="max_drawdown", value=metrics.max_drawdown,
                   display_value=percent_display(metrics.max_drawdown), **common),
    ]
    if capital_cad is not None:
        amount = round(metrics.max_drawdown * capital_cad, 2)
        entries.append(make_entry(metric="max_drawdown_cad", value=amount,
                                  display_value=format_cad(amount), **common))
    entries += [
        make_entry(metric="max_drawdown_start", value=metrics.max_drawdown_start,
                   display_value=metrics.max_drawdown_start, **common),
        make_entry(metric="max_drawdown_end", value=metrics.max_drawdown_end,
                   display_value=metrics.max_drawdown_end, **common),
    ]
    if metrics.recovery_days is None:
        entries.append(make_entry(metric="recovery_days", value=NOT_RECOVERED, unit="text",
                                  display_value=NOT_RECOVERED_FR, **common))
    else:
        entries.append(make_entry(metric="recovery_days", value=metrics.recovery_days,
                                  display_value=format_days(metrics.recovery_days), **common))
    entries += [
        make_entry(metric="underwater_days", value=metrics.underwater_days,
                   display_value=format_days(metrics.underwater_days), **common),
        make_entry(metric="total_return", value=metrics.total_return,
                   display_value=percent_display(metrics.total_return), **common),
    ]
    if metrics.return_ann is not None:
        entries.append(make_entry(metric="return_ann", value=metrics.return_ann,
                                  display_value=percent_display(metrics.return_ann), **common))
    return entries


def _composition_entries(tool: str, snapshot: PortfolioSnapshot, as_of: str) -> list[EvidenceEntry]:
    """Preuves de composition (poids, classes, secteurs, devises) : sans période."""
    subject = snapshot["subject"]

    def entry(metric: str, value: float, limits: list[str], sources, label: str | None = None):
        return make_entry(tool_name=tool, metric=metric, subject=subject, value=value,
                          display_value=percent_display(value), as_of=as_of, limit_ids=limits,
                          source_ids=sources, label_fr=label)

    entries = [
        entry("top_asset_weight", snapshot["top_asset_weight"], WEIGHT_LIMITS, (),
              f"Poids du plus gros actif ({snapshot['top_asset']})"),
        entry("defensive_share", snapshot["defensive_share"], COMPOSITION_LIMITS, UNIVERSE_SOURCES),
    ]
    entries += [entry(f"weight_by_asset_class.{name}", value, COMPOSITION_LIMITS, UNIVERSE_SOURCES,
                      f"Poids de la classe d'actifs {name}")
                for name, value in snapshot["weight_by_asset_class"].items()]
    entries += [entry(f"weight_by_sector.{name}", value, COMPOSITION_LIMITS, UNIVERSE_SOURCES,
                      f"Poids du secteur {name}")
                for name, value in snapshot["weight_by_sector"].items()]
    entries += [entry(f"currency_exposure.{name}", value, CURRENCY_LIMITS, UNIVERSE_SOURCES,
                      f"Exposition au {name}")
                for name, value in snapshot["currency_exposure"].items()]
    entries += [entry(f"weights.{ticker}", value, WEIGHT_LIMITS, (), f"Poids de {ticker}")
                for ticker, value in snapshot["weights"].items()]
    return entries


def _delta_entries(tool: str, before: PortfolioSnapshot, after: PortfolioSnapshot, as_of: str,
                   after_metrics: ReturnMetrics) -> list[EvidenceEntry]:
    """Écarts après moins avant, en points de pourcentage (sujet `portfolio_after`)."""
    entries = []
    for metric in DELTA_METRICS:
        delta = round(float(after[metric]) - float(before[metric]), 10)
        common = dict(tool_name=tool, metric=f"{metric}_delta", subject=after["subject"], value=delta,
                      display_value=format_signed_points(delta), as_of=as_of)
        if metric in ("volatility_ann", "max_drawdown"):
            entries.append(make_entry(**common, limit_ids=ALL_LIMITS, source_ids=PRICE_SOURCES,
                                      period_start=after_metrics.period_start, period_end=after_metrics.period_end,
                                      n_observations=after_metrics.n_observations, currency=BASE_CURRENCY))
        elif metric == "defensive_share":
            entries.append(make_entry(**common, limit_ids=COMPOSITION_LIMITS, source_ids=UNIVERSE_SOURCES))
        else:
            entries.append(make_entry(**common, limit_ids=WEIGHT_LIMITS))
    return entries


def _correlation_entries(tool: str, snapshot: PortfolioSnapshot, metrics: ReturnMetrics,
                         as_of: str) -> list[EvidenceEntry]:
    """Preuve du plus grand groupe corrélé, absente quand la mesure est indisponible (information manquante)."""
    value = snapshot.get("largest_correlated_group_weight")
    if value is None:
        return []
    members = snapshot.get("correlated_group_members") or []
    label = (f"Poids du plus grand groupe corrélé ({', '.join(members)})" if members
             else "Poids du plus grand groupe corrélé (aucun groupe)")
    return [make_entry(tool_name=tool, metric="largest_correlated_group_weight", subject=snapshot["subject"],
                       value=value, display_value=percent_display(value), as_of=as_of,
                       limit_ids=CORRELATION_LIMITS, period_start=metrics.period_start,
                       period_end=metrics.period_end, n_observations=metrics.n_observations,
                       currency=BASE_CURRENCY, source_ids=PRICE_SOURCES, label_fr=label)]


def _portfolio_evidence(tool: str, snapshot: PortfolioSnapshot, metrics: ReturnMetrics,
                        as_of: str, capital_cad: float | None) -> list[EvidenceEntry]:
    return (_series_entries(tool, snapshot["subject"], metrics, as_of, ALL_LIMITS, capital_cad)
            + _composition_entries(tool, snapshot, as_of)
            + _correlation_entries(tool, snapshot, metrics, as_of))


# --- Outils ----------------------------------------------------------------------

def analyze_portfolio(portfolio: Portfolio, as_of: Any = None, capital_cad: Any = None) -> ToolResult:
    """Radiographie du portefeuille fictif de départ (sujet `portfolio_before`)."""
    tool = "analyze_portfolio"
    # Les paramètres renvoyés ne contiennent que des valeurs nettoyées (jamais la saisie brute)
    params: dict[str, Any] = {"portfolio_id": None, "as_of": None, "capital_cad": None}

    def compute() -> ToolResult:
        if not isinstance(portfolio, dict):
            raise ToolInputError("Portefeuille invalide")
        params["portfolio_id"] = _clean_portfolio_id(portfolio)
        params["as_of"] = day = _clean_as_of(as_of)
        params["capital_cad"] = capital = _clean_capital(capital_cad)
        snapshot, metrics = _snapshot(portfolio, "portfolio_before", day)
        evidence = _portfolio_evidence(tool, snapshot, metrics, day or metrics.period_end, capital)
        return _result(tool, params, snapshot, evidence)

    return _guarded(tool, params, compute)


def simulate_portfolio_change(portfolio: Portfolio, idea: InvestmentIdea, as_of: Any = None,
                              capital_cad: Any = None) -> ToolResult:
    """Portefeuille après l'idée : `data = {"before", "after"}`, preuves du sujet `portfolio_after`."""
    tool = "simulate_portfolio_change"
    params: dict[str, Any] = {"ticker": None, "target_weight": None, "funding_source": None,
                              "funding_ticker": None, "portfolio_id": None, "as_of": None, "capital_cad": None}

    def compute() -> ToolResult:
        if not isinstance(portfolio, dict) or not isinstance(idea, dict):
            raise ToolInputError("Portefeuille ou idée invalide")
        params["portfolio_id"] = _clean_portfolio_id(portfolio)
        params["ticker"] = ticker = _clean_ticker(idea.get("ticker"))
        params["target_weight"] = target = _clean_target(idea.get("target_weight"))
        params["funding_source"] = funding = _clean_funding_source(idea.get("funding_source"))
        funding_ticker = None
        if funding == "from_ticker":
            funding_ticker = _clean_ticker(idea.get("funding_ticker"))
        params["funding_ticker"] = funding_ticker
        if ticker not in _known_tickers():
            return _failure(tool, params, "missing_info", "Actif absent de l'univers de données")
        params["as_of"] = day = _clean_as_of(as_of)
        params["capital_cad"] = capital = _clean_capital(capital_cad)
        clean_idea = InvestmentIdea(ticker=ticker, target_weight=target, funding_source=funding,
                                    funding_ticker=funding_ticker)
        before, _ = _snapshot(portfolio, "portfolio_before", day)
        after, after_metrics = _snapshot(apply_idea(portfolio, clean_idea), "portfolio_after", day)
        effective = day or after_metrics.period_end
        evidence = _portfolio_evidence(tool, after, after_metrics, effective, capital)
        evidence += _delta_entries(tool, before, after, effective, after_metrics)
        return _result(tool, params, {"before": before, "after": after}, evidence)

    return _guarded(tool, params, compute)


def get_asset_facts(ticker: Any, as_of: Any = None) -> ToolResult:
    """Faits historiques d'un actif, en CAD, sur une période explicite. Aucune prévision."""
    tool = "get_asset_facts"
    params: dict[str, Any] = {"ticker": None, "as_of": None}

    def compute() -> ToolResult:
        params["ticker"] = clean = _clean_ticker(ticker)
        universe = load_universe().set_index("ticker")
        if clean not in universe.index:
            return _failure(tool, params, "missing_info", "Actif absent de l'univers de données")
        params["as_of"] = day = _clean_as_of(as_of)
        metrics = _cached_asset_metrics(clean, day)
        row = universe.loc[clean]
        facts = metrics.to_dict()
        facts.pop("recovery_date", None)  # aucune preuve dédiée : ne pas l'exposer
        data = {
            "ticker": clean,
            "name": str(row["name"]),
            "asset_class": str(row["asset_class"]),
            "sector": str(row["sector"]),
            "market": str(row["market"]),
            "listing_currency": str(row["currency"]),
            "base_currency": BASE_CURRENCY,
            **facts,
        }
        evidence = _series_entries(tool, clean, metrics, day or metrics.period_end, ASSET_FACT_LIMITS, None)
        for entry in evidence:
            entry["transformation"] += " Rendements convertis en CAD, effet de change inclus."
        return _result(tool, params, data, evidence)

    return _guarded(tool, params, compute)
