"""Registre de preuves : chaque chiffre affiché ou cité remonte à une entrée datée et sourcée.

Une preuve (`contracts.EvidenceEntry`) décrit un chiffre calculé par un outil :
sa valeur, son affichage en français, sa période, sa devise, ses sources, la
transformation appliquée et les limites qui s'y rattachent (catalogue
`reference/limits.json`, identifiants LM1 à LM5).

Clé stable : `evidence_key = "<metric>:<subject>"`. Le `metric` ne contient
jamais de deux-points (le sujet peut en contenir, par exemple `variant:V1`).
Les champs dictionnaires de la radiographie donnent des métriques composées
`<champ>.<clé>`, par exemple `weight_by_asset_class.crypto`.

`EvidenceRegistry` numérote les preuves d'une analyse (E1, E2, ...). Il modifie
les entrées sur place et rend le même objet : le pipeline (flux C) lit et
réétiquette ces mêmes dictionnaires. Il ne fusionne jamais deux preuves de même
clé.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from alphaforge.contracts import EvidenceEntry, ToolResult
from alphaforge.explanation_rendering import format_percent, format_points
from alphaforge.reference_texts import load_limits

ALLOWED_UNITS = ("pct", "cad", "days", "ratio", "count", "text")
# Identifiants du catalogue des limites du flux B (reference/limits.json)
KNOWN_LIMIT_IDS = tuple(item["limit_id"] for item in load_limits())
ALL_LIMITS = list(KNOWN_LIMIT_IDS)

# Sources (noms de fichiers de data/raw/, voir sources_metadata.csv)
PRICE_SOURCES = ("prices_daily.csv", "fx_usdcad_daily.csv")
UNIVERSE_SOURCES = ("assets_universe.csv",)

NOT_RECOVERED = "not_recovered"
NOT_RECOVERED_FR = "non récupérée sur la période"

# Catalogue des métriques produites par le flux A (source de vérité de docs/evidence_keys.md).
# Pour les métriques composées, la clé est le préfixe (avant le point).
EVIDENCE_METRICS: dict[str, dict[str, str]] = {
    "volatility_ann": {"unit": "pct", "label_fr": "Volatilité annualisée",
                       "transformation": "Écart-type des rendements quotidiens en CAD (n - 1), multiplié par la racine de 252."},
    "max_drawdown": {"unit": "pct", "label_fr": "Perte maximale historique",
                     "transformation": "Plus forte baisse entre un sommet et le creux suivant, sur les rendements quotidiens en CAD."},
    "max_drawdown_cad": {"unit": "cad", "label_fr": "Perte maximale historique appliquée au capital fictif",
                         "transformation": "Perte historique observée sur la période, appliquée au capital fictif. Ce n'est pas une prévision."},
    "max_drawdown_start": {"unit": "text", "label_fr": "Date du sommet avant la perte maximale",
                           "transformation": "Dernier sommet de la valeur avant le creux de la perte maximale."},
    "max_drawdown_end": {"unit": "text", "label_fr": "Date du creux de la perte maximale",
                         "transformation": "Date où la baisse depuis le sommet est la plus forte."},
    "recovery_days": {"unit": "days", "label_fr": "Durée de récupération après le creux",
                      "transformation": "Jours civils entre le creux et le retour au niveau du sommet."},
    "underwater_days": {"unit": "days", "label_fr": "Durée passée sous le sommet",
                        "transformation": "Jours civils entre le sommet et le retour à son niveau, ou la fin de la période si ce niveau n'est pas retrouvé."},
    "total_return": {"unit": "pct", "label_fr": "Rendement cumulé sur la période",
                     "transformation": "Produit des (1 + rendement quotidien en CAD) moins 1."},
    "return_ann": {"unit": "pct", "label_fr": "Rendement annualisé",
                   "transformation": "Rendement composé ramené à un an de 252 jours de bourse, seulement si la période dure au moins un an."},
    "top_asset_weight": {"unit": "pct", "label_fr": "Poids du plus gros actif",
                         "transformation": "Poids le plus élevé du portefeuille fictif."},
    "defensive_share": {"unit": "pct", "label_fr": "Part défensive",
                        "transformation": "Poids des FNB d'obligations et des FNB de matières premières (l'or dans cet univers). Hypothèse de l'équipe."},
    "largest_correlated_group_weight": {
        "unit": "pct", "label_fr": "Poids du plus grand groupe corrélé",
        "transformation": ("Somme des poids du plus grand groupe de titres dont la corrélation des rendements "
                           "quotidiens en CAD est d'au moins 0,80 (liaison simple), sur toute la période. "
                           "Seuil et méthode : hypothèses de l'équipe. La corrélation décrit le passé.")},
    "weight_by_asset_class": {"unit": "pct", "label_fr": "Poids de la classe d'actifs",
                              "transformation": "Somme des poids des positions de cette classe (univers des organisateurs)."},
    "weight_by_sector": {"unit": "pct", "label_fr": "Poids du secteur",
                         "transformation": "Somme des poids des positions de ce secteur (univers des organisateurs)."},
    "currency_exposure": {"unit": "pct", "label_fr": "Exposition à la devise",
                          "transformation": "Somme des poids des positions cotées dans cette devise (devise de cotation)."},
    "weights": {"unit": "pct", "label_fr": "Poids de la position",
                "transformation": "Poids de la position dans le portefeuille fictif."},
    "volatility_ann_delta": {"unit": "pct", "label_fr": "Écart de volatilité (après moins avant)",
                             "transformation": "Volatilité après l'idée moins volatilité avant, en points de pourcentage."},
    "max_drawdown_delta": {"unit": "pct", "label_fr": "Écart de perte maximale (après moins avant)",
                           "transformation": "Perte maximale après l'idée moins perte maximale avant, en points de pourcentage."},
    "top_asset_weight_delta": {"unit": "pct", "label_fr": "Écart du poids du plus gros actif (après moins avant)",
                               "transformation": "Poids du plus gros actif après moins avant, en points de pourcentage."},
    "defensive_share_delta": {"unit": "pct", "label_fr": "Écart de part défensive (après moins avant)",
                              "transformation": "Part défensive après moins avant, en points de pourcentage."},
}


class EvidenceError(ValueError):
    """Preuve mal formée (unité, limite ou métrique inconnue)."""


def evidence_key(metric: str, subject: str) -> str:
    """Clé stable d'une preuve : "<metric>:<subject>"."""
    if ":" in metric:
        raise EvidenceError(f"Une métrique ne contient pas de deux-points : {metric}")
    return f"{metric}:{subject}"


def metric_family(metric: str) -> str:
    """Préfixe du catalogue d'une métrique (`weight_by_sector.Energy` donne `weight_by_sector`)."""
    return metric.split(".", 1)[0]


def format_days(days: int) -> str:
    """Nombre de jours en français : 1 jour, 412 jours."""
    return f"{_group_thousands(int(days))} jour" + ("s" if abs(int(days)) > 1 else "")


def format_cad(amount: float) -> str:
    """Montant en dollars canadiens, sans décimale : 26 040 $."""
    return f"{_group_thousands(int(round(amount)))} $"


def format_signed_points(delta: float) -> str:
    """Écart en points de pourcentage, signé : +1,6 pts, -8,75 pts, 0 pts."""
    text = format_points(delta)
    return text if text.startswith("-") or text == "0 pts" else "+" + text


def _group_thousands(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def make_entry(
    *,
    tool_name: str,
    metric: str,
    subject: str,
    value: Any,
    display_value: str,
    as_of: str,
    limit_ids: Iterable[str],
    label_fr: str | None = None,
    unit: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    n_observations: int | None = None,
    currency: str | None = None,
    source_ids: Iterable[str] = (),
    transformation: str | None = None,
) -> EvidenceEntry:
    """Construit une preuve conforme au contrat, avec `evidence_id` vide (attribué par le registre)."""
    family = metric_family(metric)
    spec = EVIDENCE_METRICS.get(family)
    if spec is None:
        raise EvidenceError(f"Métrique absente du catalogue : {family}")
    unit = unit or spec["unit"]
    if unit not in ALLOWED_UNITS:
        raise EvidenceError(f"Unité inconnue : {unit}")
    limits = list(limit_ids)
    unknown = [limit for limit in limits if limit not in KNOWN_LIMIT_IDS]
    if unknown:
        raise EvidenceError(f"Limites absentes du catalogue : {unknown}")
    if value is None:
        raise EvidenceError("Une preuve ne porte jamais une valeur absente : ne pas la créer")
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceError("Une preuve porte toujours une valeur finie")
    return EvidenceEntry(
        evidence_id="",
        evidence_key=evidence_key(metric, subject),
        tool_name=tool_name,
        metric=metric,
        subject=subject,
        label_fr=label_fr or spec["label_fr"],
        value=value,
        unit=unit,
        display_value=display_value,
        qualifier=None,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        currency=currency,
        source_ids=list(source_ids),
        transformation=transformation or spec["transformation"],
        n_observations=n_observations,
        limit_ids=limits,
    )


def percent_display(value: float) -> str:
    """Affichage d'une fraction en pourcentage, identique à celui de la gouvernance."""
    return format_percent(value)


class EvidenceRegistry:
    """Numérote les preuves d'une analyse : E1, E2, ... (une instance par analyse).

    `register` modifie les entrées sur place et rend le même `ToolResult`.
    Réenregistrer un même résultat (même `call_id`, même rang) redonne les mêmes
    identifiants. Aucune fusion par `evidence_key`.
    """

    def __init__(self) -> None:
        self._entries: dict[str, EvidenceEntry] = {}
        self._ids_by_position: dict[tuple[str, int], str] = {}

    def register(self, tool_result: ToolResult) -> ToolResult:
        if tool_result.get("status") != "ok":
            return tool_result
        call_id = str(tool_result.get("call_id") or "")
        for position, entry in enumerate(tool_result.get("evidence") or []):
            slot = (call_id, position)
            evidence_id = self._ids_by_position.get(slot)
            if evidence_id is None:
                evidence_id = f"E{len(self._entries) + 1}"
                self._ids_by_position[slot] = evidence_id
            entry["evidence_id"] = evidence_id
            self._entries[evidence_id] = entry
        return tool_result

    @property
    def entries(self) -> dict[str, EvidenceEntry]:
        """Dictionnaire identifiant vers preuve (vue en lecture seule : ne pas modifier)."""
        return dict(self._entries)

    def get(self, evidence_id: str) -> EvidenceEntry | None:
        return self._entries.get(evidence_id)

    def find(self, metric: str, subject: str) -> list[EvidenceEntry]:
        """Preuves d'un couple (métrique, sujet), dans l'ordre d'enregistrement."""
        return [e for e in self._entries.values() if e["metric"] == metric and e["subject"] == subject]

    def __len__(self) -> int:
        return len(self._entries)

