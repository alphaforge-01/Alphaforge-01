"""Portefeuille fictif : radiographie et simulation d'une idée de placement.

Produit le `PortfolioSnapshot` (voir `contracts.py`) que lit la gouvernance.

Hypothèses retenues par l'équipe, à afficher comme telles :

- **Poids fixes, rééquilibrés chaque jour** : le rendement quotidien du
  portefeuille est la moyenne pondérée des rendements quotidiens en CAD.
  C'est une simplification : un portefeuille réel dérive entre deux rééquilibrages.
- **Part défensive** = poids des obligations et de l'or (classes d'actifs
  `etf_bond` et `etf_commodity` de l'univers). Ce choix est une hypothèse : il ne
  garantit pas qu'un actif protège en cas de baisse : dans nos données, TLT a
  connu une perte maximale d'environ 40 % en CAD entre décembre 2021 et
  octobre 2023 (chiffre à recalculer par le code, jamais à citer tel quel).
- Classes d'actifs, secteurs et devises sont ceux de `data/raw/assets_universe.csv`.
  La devise est la devise de cotation (exposition apparente, pas l'exposition
  économique des entreprises sous-jacentes).

Aucune fonction ne passe d'ordre ni ne se connecte à un courtier : tout est simulé.
"""

from __future__ import annotations

import math
from typing import Literal

import pandas as pd

from alphaforge.calendar_alignment import daily_cad_returns, returns_base_date
from alphaforge.contracts import InvestmentIdea, Portfolio, PortfolioSnapshot, Position
from alphaforge.data_loading import AsOf, load_universe
from alphaforge.metrics import ReturnMetrics, compute_return_metrics

DEFENSIVE_ASSET_CLASSES = ("etf_bond", "etf_commodity")
REPORTED_CURRENCIES = ("CAD", "USD")
WEIGHT_TOLERANCE = 1e-6
# Un poids plus petit est considéré comme nul (position retirée)
ZERO_WEIGHT = 1e-12
# Arrondi des poids publiés, pour éviter le bruit du type 0.19999999999999996
WEIGHT_DECIMALS = 10
IDEA_REQUIRED_KEYS = ("ticker", "target_weight", "funding_source")


class PortfolioError(ValueError):
    """Portefeuille ou idée de placement invalide."""


def _as_number(value, label: str) -> float:
    """Nombre fini (int ou float, pas bool ni chaîne), sinon `PortfolioError`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortfolioError(f"{label} doit être un nombre (reçu : {value!r})")
    number = float(value)
    if not math.isfinite(number):
        raise PortfolioError(f"{label} doit être un nombre fini (reçu : {value!r})")
    return number


def portfolio_weights(portfolio: Portfolio) -> pd.Series:
    """Poids du portefeuille, validés : tickers connus, positifs, uniques, somme égale à 1."""
    positions = portfolio.get("positions") or []
    if not positions:
        raise PortfolioError("Le portefeuille ne contient aucune position")
    for position in positions:
        if "ticker" not in position or "weight" not in position:
            raise PortfolioError("Chaque position doit avoir un `ticker` et un `weight`")
    tickers = [position["ticker"] for position in positions]
    if len(set(tickers)) != len(tickers):
        raise PortfolioError("Un même ticker apparaît plusieurs fois dans le portefeuille")
    unknown = sorted(set(tickers) - set(load_universe()["ticker"]))
    if unknown:
        raise PortfolioError(f"Tickers absents de l'univers : {unknown}")
    weights = pd.Series({
        position["ticker"]: _as_number(position["weight"], f"Le poids de {position['ticker']}")
        for position in positions
    })
    if (weights < 0).any():
        raise PortfolioError("Les poids doivent être positifs ou nuls")
    if abs(weights.sum() - 1.0) > WEIGHT_TOLERANCE:
        raise PortfolioError(f"La somme des poids doit valoir 100 % (reçu : {weights.sum():.6f})")
    weights = weights[weights > ZERO_WEIGHT]
    return weights / weights.sum()


def portfolio_daily_returns(portfolio: Portfolio, as_of: AsOf = None) -> pd.Series:
    """Rendements quotidiens en CAD du portefeuille rééquilibré chaque jour."""
    series = _weighted_returns(portfolio_weights(portfolio), as_of)
    series.name = portfolio.get("portfolio_id", "portfolio")
    return series


def _weighted_returns(weights: pd.Series, as_of: AsOf) -> pd.Series:
    returns = daily_cad_returns(as_of=as_of, tickers=weights.index.tolist())
    return returns[weights.index].mul(weights, axis=1).sum(axis=1)


def portfolio_return_metrics(portfolio: Portfolio, as_of: AsOf = None) -> ReturnMetrics:
    """Métriques historiques du portefeuille (période explicite, voir `metrics.py`)."""
    return compute_return_metrics(portfolio_daily_returns(portfolio, as_of), returns_base_date(as_of))


def _weights_by(weights: pd.Series, column: str) -> dict[str, float]:
    attributes = load_universe().set_index("ticker")[column]
    labels = attributes.reindex(weights.index)
    if labels.isna().any():
        raise PortfolioError(f"Attribut `{column}` manquant dans l'univers pour : {labels.index[labels.isna()].tolist()}")
    grouped = weights.groupby(labels).sum()
    if abs(grouped.sum() - 1.0) > WEIGHT_TOLERANCE:
        raise PortfolioError(f"La répartition par `{column}` ne totalise pas 100 %")
    return {str(key): round(float(value), WEIGHT_DECIMALS)
            for key, value in grouped.sort_values(ascending=False).items()}


def build_snapshot_with_metrics(
    portfolio: Portfolio, subject: str, as_of: AsOf = None
) -> tuple[PortfolioSnapshot, ReturnMetrics]:
    """Radiographie (`PortfolioSnapshot`) et métriques complètes, calculées une seule fois.

    Les métriques donnent ce que le contrat de radiographie ne porte pas mais
    que les preuves exigent : période, nombre d'observations, rendement cumulé,
    jours sous le sommet. Avec `as_of=None`, la date effective est `metrics.period_end`.
    """
    weights = portfolio_weights(portfolio)
    metrics = compute_return_metrics(_weighted_returns(weights, as_of), returns_base_date(as_of))
    return _snapshot(weights, metrics, subject), metrics


def build_snapshot(portfolio: Portfolio, subject: str, as_of: AsOf = None) -> PortfolioSnapshot:
    """Radiographie du portefeuille au format `PortfolioSnapshot`.

    `subject` identifie le portefeuille dans les preuves : "portfolio_before",
    "portfolio_after" ou "variant:V1".
    """
    return build_snapshot_with_metrics(portfolio, subject, as_of)[0]


def _snapshot(weights: pd.Series, metrics: ReturnMetrics, subject: str) -> PortfolioSnapshot:
    by_class = _weights_by(weights, "asset_class")
    by_currency = _weights_by(weights, "currency")
    top_weight = round(float(weights.max()), WEIGHT_DECIMALS)
    top_asset = sorted(weights.index[weights >= weights.max() - ZERO_WEIGHT])[0]
    return PortfolioSnapshot(
        subject=subject,
        weights={str(ticker): round(float(weight), WEIGHT_DECIMALS)
                 for ticker, weight in weights.sort_values(ascending=False).items()},
        volatility_ann=metrics.volatility_ann,
        max_drawdown=metrics.max_drawdown,
        max_drawdown_start=metrics.max_drawdown_start,
        max_drawdown_end=metrics.max_drawdown_end,
        recovery_days=metrics.recovery_days,
        top_asset=top_asset,
        top_asset_weight=top_weight,
        weight_by_sector=_weights_by(weights, "sector"),
        weight_by_asset_class=by_class,
        currency_exposure={currency: float(by_currency.get(currency, 0.0)) for currency in REPORTED_CURRENCIES},
        defensive_share=round(float(sum(by_class.get(name, 0.0) for name in DEFENSIVE_ASSET_CLASSES)),
                              WEIGHT_DECIMALS),
        largest_correlated_group_weight=None,  # P2 : diversification par corrélations
    )


def max_feasible_target(portfolio: Portfolio, idea: InvestmentIdea) -> float:
    """Plus grand poids visé que l'idée peut atteindre avec sa source des fonds.

    1 au prorata ; avec `from_ticker`, poids actuel du titre visé plus poids du
    titre qui finance. Utile pour borner un balayage de contrefactuel.
    """
    weights = portfolio_weights(portfolio).to_dict()
    if idea.get("funding_source") == "from_ticker":
        source = idea.get("funding_ticker")
        return round(min(1.0, weights.get(idea["ticker"], 0.0) + weights.get(source, 0.0)), WEIGHT_DECIMALS)
    return 1.0


def apply_idea(
    portfolio: Portfolio,
    idea: InvestmentIdea,
    suffix: str = "after",
    label_fr: str | None = None,
) -> Portfolio:
    """Nouveau portefeuille fictif après l'idée : `idea["ticker"]` porté à `target_weight`.

    Source des fonds :
    - `pro_rata` : les autres positions sont réduites (ou augmentées si le poids
      visé baisse) proportionnellement à leur poids ;
    - `from_ticker` : l'écart est pris sur `funding_ticker` seul (ou lui est
      rendu si le poids visé baisse).

    `suffix` distingue les résultats dans la trace (`portfolio_id` vaut
    "<id>:<suffix>", par exemple "variant:V1"). Le portefeuille d'origine n'est
    pas modifié.
    """
    missing = [key for key in IDEA_REQUIRED_KEYS if key not in idea]
    if missing:
        raise PortfolioError(f"Idée incomplète, champs manquants : {missing}")
    weights = portfolio_weights(portfolio).to_dict()
    ticker = idea["ticker"]
    if ticker not in set(load_universe()["ticker"]):
        raise PortfolioError(f"Ticker absent de l'univers : {ticker}")
    target = _as_number(idea["target_weight"], "Le poids visé")
    if not 0.0 <= target <= 1.0:
        raise PortfolioError("Le poids visé doit être compris entre 0 % et 100 %")

    current = weights.get(ticker, 0.0)
    funding: Literal["pro_rata", "from_ticker"] = idea["funding_source"]
    if funding == "pro_rata":
        others = {t: w for t, w in weights.items() if t != ticker}
        others_total = sum(others.values())
        if others_total <= ZERO_WEIGHT and target < 1.0 - ZERO_WEIGHT:
            raise PortfolioError("Aucune autre position pour financer ou recevoir l'écart au prorata")
        scale = (1.0 - target) / others_total if others_total > ZERO_WEIGHT else 0.0
        new_weights = {t: w * scale for t, w in others.items()}
    elif funding == "from_ticker":
        source = idea.get("funding_ticker")
        if not source:
            raise PortfolioError("`funding_ticker` est obligatoire avec la source `from_ticker`")
        if source == ticker:
            raise PortfolioError("Le titre qui finance doit être différent du titre visé")
        if source not in weights:
            raise PortfolioError(f"Le titre qui finance ne détient aucun poids dans le portefeuille : {source}")
        delta = target - current
        remaining = weights[source] - delta
        if remaining < -WEIGHT_TOLERANCE:
            raise PortfolioError(
                f"{source} ne pèse que {weights[source]:.2%} : impossible de financer {delta:.2%}"
            )
        new_weights = {t: w for t, w in weights.items() if t != ticker}
        new_weights[source] = max(remaining, 0.0)
    else:
        raise PortfolioError(f"Source des fonds inconnue : {funding}")

    new_weights[ticker] = target
    kept = {t: w for t, w in new_weights.items() if w > ZERO_WEIGHT}
    total = sum(kept.values())
    positions = [
        Position(ticker=t, weight=round(w / total, WEIGHT_DECIMALS))
        for t, w in sorted(kept.items(), key=lambda item: (-item[1], item[0]))
    ]
    return Portfolio(
        portfolio_id=f"{portfolio.get('portfolio_id', 'portfolio')}:{suffix}",
        label_fr=label_fr or f"{portfolio.get('label_fr', 'Portefeuille fictif')} après l'idée",
        is_fictional=True,
        base_currency="CAD",
        positions=positions,
    )
