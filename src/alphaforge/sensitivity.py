"""Mise à l'épreuve des hypothèses : les verdicts changent-ils si l'on change un choix ?

Pourquoi : l'énoncé demande de tester la sensibilité des résultats aux hypothèses, aux
données et aux scénarios. Les verdicts de la gouvernance reposent sur des choix de
l'équipe : période de 5 ans, conversion en CAD, rendements quotidiens, données arrêtées
au 12 novembre 2026, seuils des règles. Ce module refait l'évaluation en changeant
**un seul choix à la fois** et montre quelles règles changent de statut.

Ce que ce module ne fait pas : il ne prédit rien. Chaque variante décrit le passé sur
une autre période ou sous une autre convention ; aucune n'est plus « vraie » que le cas
de base, et les variantes ne sont ni indépendantes ni équiprobables : un décompte de
variantes stables n'est pas une probabilité.

Construction d'une variante :
- la composition du portefeuille (poids, classes, secteurs, devises, part défensive)
  vient de `portfolio.build_snapshot`, inchangée ;
- les champs de risque (volatilité, perte maximale, dates, jours de reprise) et le plus
  grand groupe corrélé sont recalculés sur les rendements de la variante ;
- la gouvernance (`governance.evaluate`) juge l'instantané, sans contrefactuel.

Le pipeline, les outils des agents et l'interface ne sont pas modifiés : le module
réutilise leurs briques (alignement, métriques, diversification, gouvernance).
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from alphaforge.calendar_alignment import aligned_cad_prices, common_trading_calendar, pivot_on_calendar
from alphaforge.data_loading import load_prices, load_universe
from alphaforge.diversification import largest_correlated_group
from alphaforge.governance import evaluate, is_esg_rule_type, split_verdicts, worst_status
from alphaforge.metrics import TRADING_DAYS_PER_YEAR, compute_return_metrics
from alphaforge.portfolio import apply_idea, build_snapshot, portfolio_weights

WEEKS_PER_YEAR = 52
ZERO_WEIGHT = 1e-12

# Règles dont les seuils ne sont pas mis à l'épreuve : exclusions (limite nulle, toute
# position compte) et préférences ESG. Ce sont des choix de l'investisseur, pas des
# niveaux de risque réglables.
NON_SCALABLE_RULE_TYPES = frozenset({"excluded_asset_class", "esg_exclusion"})
# Une perte maximale mesurée sur une période plus courte (fenêtre, bloc, date d'arrêt plus
# ancienne) ou sur des points hebdomadaires ne peut que baisser ou rester égale : son statut
# n'est pas comparable aux seuils fixés pour la période complète.
DRAWDOWN_RULE_TYPES = frozenset({"max_portfolio_drawdown"})
RISK_FIELDS = ("volatility_ann", "max_drawdown", "max_drawdown_start", "max_drawdown_end", "recovery_days")

# Demandes prêtes de l'interface (financement au prorata).
DEFAULT_IDEAS: tuple[dict, ...] = tuple(
    {"ticker": ticker, "target_weight": weight, "funding_source": "pro_rata", "funding_ticker": None}
    for ticker, weight in (("TSLA", 0.25), ("NVDA", 0.15), ("BTC-USD", 0.10), ("BTC-USD", 0.40), ("XOM", 0.15))
)


@dataclass(frozen=True)
class Variant:
    """Un seul choix modifié par rapport au cas de base."""

    variant_id: str
    axis: str                       # base, fenetre, devise, date_arret, frequence, seuils, bloc
    label_fr: str
    hypothesis_fr: str              # ce qui est supposé, dit simplement
    as_of: str | None = None        # None : dernière date des données
    window_years: int | None = None  # None : depuis le début du calendrier commun
    start: str | None = None        # début explicite (blocs annuels)
    currency: str = "CAD"           # CAD ou local
    frequency: str = "daily"        # daily ou weekly
    threshold_scale: float = 1.0    # < 1 : seuils plus stricts ; > 1 : plus souples

    @property
    def drawdown_comparable(self) -> bool:
        return (self.window_years is None and self.start is None and self.as_of is None
                and self.frequency == "daily")


BASE = Variant("base", "base", "Cas de base",
               "Période complète (environ 5 ans), CAD au taux du jour, rendements quotidiens, seuils de l'équipe.")

GRID_VARIANTS: tuple[Variant, ...] = (
    BASE,
    Variant("window_3y", "fenetre", "Fenêtre de 3 ans",
            "Seulement les 3 dernières années : l'épisode de baisse de 2022 sort de la période.", window_years=3),
    Variant("window_1y", "fenetre", "Fenêtre de 1 an",
            "Seulement la dernière année : indicatif, environ 250 rendements.", window_years=1),
    Variant("currency_local", "devise", "Devise locale",
            "Chaque actif dans sa devise de cotation : revient à supposer le change parfaitement couvert, "
            "sans coût. C'est une hypothèse, pas un fait.", currency="local"),
    Variant("as_of_2024", "date_arret", "Données arrêtées au 12 nov. 2024",
            "On se place deux ans plus tôt, sans aucune donnée postérieure (environ 3 ans de recul). "
            "L'univers et les portefeuilles restent ceux choisis en 2026.", as_of="2024-11-12"),
    Variant("as_of_2025", "date_arret", "Données arrêtées au 12 nov. 2025",
            "On se place un an plus tôt, sans aucune donnée postérieure (environ 4 ans de recul).",
            as_of="2025-11-12"),
    Variant("weekly", "frequence", "Rendements hebdomadaires",
            "Un point par semaine (dernier jour commun de la semaine) : atténue les décalages d'heure de "
            "clôture entre marchés et cryptoactifs.", frequency="weekly"),
    Variant("thresholds_strict", "seuils", "Seuils 20 % plus stricts",
            "Plafonds multipliés par 0,8 et planchers divisés par 0,8 ; exclusions et ESG inchangées.",
            threshold_scale=0.8),
    Variant("thresholds_loose", "seuils", "Seuils 20 % plus souples",
            "Plafonds multipliés par 1,2 et planchers divisés par 1,2 ; exclusions et ESG inchangées.",
            threshold_scale=1.2),
)


@dataclass
class VariantOutcome:
    """Verdicts et mesures d'un portefeuille (avant ou après l'idée) pour une variante."""

    variant_id: str
    period_start: str
    period_end: str
    n_observations: int
    volatility_ann: float
    max_drawdown: float
    largest_correlated_group_weight: float | None
    overall: str
    financial: str | None
    esg: str | None
    rules: dict[str, dict] = field(default_factory=dict)  # rule_id -> {status, value, label_fr, comparable}
    # Verdict financier où une règle non comparable garde son statut du cas de base : c'est
    # lui qui sert aux comparaisons (synthèse, grille, blocs).
    financial_comparable: str | None = None


# --- Rendements de variante -----------------------------------------------------------


def _local_prices(as_of: Any, tickers: list[str]) -> pd.DataFrame:
    """Prix en devise de cotation sur le même calendrier commun que les prix en CAD."""
    prices = load_prices(as_of=as_of)
    universe = load_universe()
    reference = universe.loc[universe["asset_class"] != "crypto", "ticker"].tolist()
    calendar = common_trading_calendar(prices, reference)
    return pivot_on_calendar(prices, calendar, tickers)


def _start_of_window(index: pd.DatetimeIndex, variant: Variant) -> pd.Timestamp | None:
    if variant.start is not None:
        target = pd.Timestamp(variant.start)
    elif variant.window_years is not None:
        target = index[-1] - pd.DateOffset(years=variant.window_years)
    else:
        return None
    eligible = index[index <= target]
    if len(eligible) == 0:
        raise ValueError(f"Fenêtre de la variante {variant.variant_id} antérieure au début des données")
    return eligible[-1]  # date de base : dernière date du calendrier au plus tard au début visé


def variant_prices(tickers: Sequence[str], variant: Variant) -> pd.DataFrame:
    """Niveaux de prix de la variante (fenêtre, devise, fréquence), date de base en première ligne."""
    tickers = list(tickers)
    if variant.currency == "CAD":
        prices = aligned_cad_prices(as_of=variant.as_of, tickers=tickers)
    elif variant.currency == "local":
        prices = _local_prices(variant.as_of, tickers)
    else:
        raise ValueError(f"Devise de variante inconnue : {variant.currency}")
    if variant.start is not None:
        end = pd.Timestamp(variant.start) + pd.DateOffset(years=1)
        prices = prices.loc[prices.index <= end]
    start = _start_of_window(prices.index, variant)
    if start is not None:
        prices = prices.loc[start:]
    if variant.frequency == "weekly":
        weeks = prices.index.to_period("W-FRI")
        last_of_week = ~pd.Series(weeks, index=prices.index).duplicated(keep="last")
        weekly = prices.loc[last_of_week.to_numpy()]
        # La date de base reste la première date de la fenêtre, pour ne perdre aucune baisse.
        prices = pd.concat([prices.iloc[[0]], weekly]).loc[lambda frame: ~frame.index.duplicated()]
    elif variant.frequency != "daily":
        raise ValueError(f"Fréquence de variante inconnue : {variant.frequency}")
    if len(prices) < 2:
        raise ValueError(f"Moins de deux dates pour la variante {variant.variant_id}")
    return prices


def periods_per_year(variant: Variant) -> int:
    return WEEKS_PER_YEAR if variant.frequency == "weekly" else TRADING_DAYS_PER_YEAR


# --- Instantané et gouvernance ----------------------------------------------------------


def variant_snapshot(portfolio: Mapping, subject: str, variant: Variant) -> tuple[dict, dict]:
    """Instantané de la variante et description de la période (début, fin, observations)."""
    snapshot = dict(build_snapshot(portfolio, subject, as_of=variant.as_of))
    weights = portfolio_weights(portfolio)
    held = [ticker for ticker in weights.index if weights[ticker] > ZERO_WEIGHT]
    prices = variant_prices(held, variant)
    returns = prices.pct_change().iloc[1:]
    portfolio_returns = returns[held].mul(weights[held], axis=1).sum(axis=1)
    metrics = compute_return_metrics(portfolio_returns, prices.index[0], periods_per_year(variant))
    for name in RISK_FIELDS:
        snapshot[name] = getattr(metrics, name)
    if len(held) >= 2:
        group_weight, members = largest_correlated_group(returns[held], weights[held].to_dict())
    else:
        group_weight, members = 0.0, []
    snapshot["largest_correlated_group_weight"] = group_weight
    snapshot["correlated_group_members"] = members
    period = {"period_start": metrics.period_start, "period_end": metrics.period_end,
              "n_observations": metrics.n_observations}
    return snapshot, period


def scale_thresholds(profile: Mapping, scale: float) -> dict:
    """Copie du profil aux seuils plus stricts (`scale` < 1) ou plus souples (`scale` > 1).

    Plafond (`max`) : seuils multipliés par `scale`. Plancher (`min`) : seuils divisés par
    `scale`, pour que « plus strict » ait le même sens. Seuils en pourcentage bornés à
    [0, 1]. Exclusions et règles ESG inchangées. Le profil d'origine n'est pas modifié.
    """
    if scale <= 0:
        raise ValueError("Le facteur d'échelle des seuils doit être positif")
    scaled = copy.deepcopy(dict(profile))
    for rule in scaled.get("rules", []):
        if rule.get("rule_type") in NON_SCALABLE_RULE_TYPES:
            continue
        factor = scale if rule.get("direction") == "max" else 1.0 / scale
        for key in ("warn_threshold", "limit_threshold"):
            value = rule.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                new_value = value * factor
                if rule.get("unit") == "pct":
                    new_value = min(max(new_value, 0.0), 1.0)
                rule[key] = round(new_value, 10)
    return scaled


def flip_factor(rule: Mapping, value: float | None) -> dict:
    """Facteurs d'échelle des seuils auxquels le statut de la règle change.

    Même convention que `scale_thresholds` : en dessous de 1, seuils plus stricts ; au-dessus
    de 1, plus souples. Pour un plafond, le seuil mis à l'échelle vaut `seuil x facteur` :
    il égale la valeur pour `facteur = valeur / seuil`. Pour un plancher, il vaut
    `seuil / facteur` : il égale la valeur pour `facteur = seuil / valeur`.

    Exemple : plafond d'attention 20 %, valeur 25 % : facteur 1,25 ; avec des seuils plus
    souples d'au moins ce facteur, la valeur ne franchit plus l'attention.
    """
    if value is None or rule.get("rule_type") in NON_SCALABLE_RULE_TYPES:
        return {"warn": None, "limit": None}
    is_floor = rule.get("direction") == "min"

    def factor(threshold):
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold == 0:
            return None
        if is_floor:
            return None if value == 0 else round(float(threshold) / float(value), 4)
        return round(float(value) / float(threshold), 4)

    return {"warn": factor(rule.get("warn_threshold")), "limit": factor(rule.get("limit_threshold"))}


def evaluate_variant(profile: Mapping, portfolio: Mapping, subject: str, variant: Variant) -> VariantOutcome:
    """Gouvernance de la variante sur un portefeuille."""
    snapshot, period = variant_snapshot(portfolio, subject, variant)
    used_profile = scale_thresholds(profile, variant.threshold_scale) if variant.threshold_scale != 1.0 else profile
    governance = evaluate(used_profile, snapshot)
    verdicts = split_verdicts(governance)
    rules = {}
    for check in governance["checks"]:
        comparable = variant.drawdown_comparable or check.get("rule_type") not in DRAWDOWN_RULE_TYPES
        rules[check["rule_id"]] = {"status": check["status"], "value": check.get("value"),
                                   "rule_type": check.get("rule_type"), "label_fr": check.get("label_fr"),
                                   "comparable": comparable}
    return VariantOutcome(variant_id=variant.variant_id, volatility_ann=snapshot["volatility_ann"],
                          max_drawdown=snapshot["max_drawdown"],
                          largest_correlated_group_weight=snapshot["largest_correlated_group_weight"],
                          overall=verdicts["overall"], financial=verdicts["financial"], esg=verdicts["esg"],
                          rules=rules, financial_comparable=verdicts["financial"], **period)


# --- Grille --------------------------------------------------------------------------


def idea_has_no_effect(portfolio: Mapping, idea: Mapping) -> bool:
    """Vrai si le poids visé est déjà le poids actuel : l'idée ne change rien."""
    before = portfolio_weights(portfolio)
    after = portfolio_weights(apply_idea(portfolio, idea, "sensitivity"))
    aligned = pd.concat([before, after], axis=1).fillna(0.0)
    return bool((aligned.iloc[:, 0] - aligned.iloc[:, 1]).abs().max() < 1e-9)


def idea_id(idea: Mapping) -> str:
    return f"{idea['ticker']}_{round(idea['target_weight'] * 100)}"


def comparable_financial(base: VariantOutcome, other: VariantOutcome) -> str | None:
    """Verdict financier de `other`, chaque règle non comparable prenant son statut du cas de base."""
    statuses = []
    for rule_id, info in other.rules.items():
        if is_esg_rule_type(info["rule_type"]):
            continue
        if info["comparable"] or rule_id not in base.rules:
            statuses.append(info["status"])
        else:
            statuses.append(base.rules[rule_id]["status"])
    return worst_status(statuses) if statuses else None


def with_comparable_verdict(base: VariantOutcome, other: VariantOutcome) -> VariantOutcome:
    """Complète `other` : `financial_comparable` calculé par rapport à `base` (modifié en place)."""
    other.financial_comparable = comparable_financial(base, other)
    return other


def changed_rules(base: VariantOutcome, other: VariantOutcome) -> list[str]:
    """Règles dont le statut diffère du cas de base (statuts comparables seulement)."""
    return sorted(rule_id for rule_id, info in other.rules.items()
                  if info["comparable"] and rule_id in base.rules and info["status"] != base.rules[rule_id]["status"])


def annual_blocks(as_of: Any = None, n_blocks: int = 5) -> tuple[Variant, ...]:
    """Blocs annuels disjoints depuis le début du calendrier commun (épisodes observés, pas prévus)."""
    first = aligned_cad_prices(as_of=as_of).index[0]
    blocks = []
    for k in range(n_blocks):
        start = (first + pd.DateOffset(years=k)).date().isoformat()
        end = (first + pd.DateOffset(years=k + 1)).date().isoformat()
        blocks.append(Variant(f"block_{k + 1}", "bloc", f"Du {start} au {end}",
                              "Une seule année observée ; la date de début d'un bloc est la date de base "
                              "(dernier prix du bloc précédent), les rendements ne se recouvrent pas.",
                              as_of=as_of, start=start))
    return tuple(blocks)


def run_grid(personas: Mapping[str, Mapping], ideas: Sequence[Mapping] = DEFAULT_IDEAS,
             variants: Sequence[Variant] = GRID_VARIANTS) -> list[dict]:
    """Tous les personas x toutes les idées x toutes les variantes (après l'idée)."""
    rows = []
    for name in sorted(personas):
        profile, portfolio = personas[name]["profile"], personas[name]["portfolio"]
        for idea in ideas:
            after = apply_idea(portfolio, idea, "sensitivity")
            outcomes = {variant.variant_id: evaluate_variant(profile, after, "portfolio_after", variant)
                        for variant in variants}
            base = outcomes[variants[0].variant_id]
            outcomes = {key: with_comparable_verdict(base, value) for key, value in outcomes.items()}
            rows.append({
                "persona": name,
                "idea": idea_id(idea),
                "no_effect": idea_has_no_effect(portfolio, idea),
                "outcomes": {key: asdict(value) for key, value in outcomes.items()},
                "changes": {key: changed_rules(base, value) for key, value in outcomes.items() if key != base.variant_id},
            })
    return rows


def axis_summary(rows: Sequence[Mapping], variants: Sequence[Variant] = GRID_VARIANTS) -> list[dict]:
    """Par variante : cas dont le verdict financier comparable change, et règles qui basculent.

    `rule_changes` est indexé par `persona:rule_id` (identifiants propres à chaque persona).
    """
    summary = []
    for variant in variants[1:]:
        verdict_changes, rule_counts = [], {}
        for row in rows:
            base = row["outcomes"]["base"]
            other = row["outcomes"][variant.variant_id]
            if other["financial_comparable"] != base["financial"]:
                verdict_changes.append({"persona": row["persona"], "idea": row["idea"],
                                        "before": base["financial"], "after": other["financial_comparable"]})
            for rule_id in row["changes"][variant.variant_id]:
                # Les identifiants de règle sont propres à chaque persona (R5 n'est pas la même règle
                # chez Amira et chez Robert) : on compte par persona et règle.
                key = f"{row['persona']}:{rule_id}"
                rule_counts[key] = rule_counts.get(key, 0) + 1
        summary.append({"variant_id": variant.variant_id, "axis": variant.axis, "label_fr": variant.label_fr,
                        "n_cases": len(rows), "financial_verdict_changes": verdict_changes,
                        "rule_changes": dict(sorted(rule_counts.items()))})
    return summary


def stable_rules_by_persona(rows: Sequence[Mapping], variants: Sequence[Variant] = GRID_VARIANTS,
                            axes: Sequence[str] = ("fenetre", "devise", "date_arret", "frequence")) -> dict:
    """Par persona : règles dont le statut ne change avec aucune variante des axes donnés."""
    result = {}
    for row in rows:
        persona = row["persona"]
        rule_ids = set(row["outcomes"]["base"]["rules"])
        moved = {rule_id for v in variants[1:] if v.axis in axes for rule_id in row["changes"][v.variant_id]}
        result[persona] = result.get(persona, rule_ids) & (rule_ids - moved)
    return {persona: sorted(ids) for persona, ids in sorted(result.items())}


def data_end_date() -> str:
    """Dernière date du calendrier commun (date d'arrêt du cas de base)."""
    return aligned_cad_prices().index[-1].date().isoformat()

