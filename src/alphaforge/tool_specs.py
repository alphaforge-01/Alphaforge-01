"""Schemas des outils de l'analyste et dispatcheur borne (``ToolBox``).

L'analyste (agent Bedrock) ne voit que quatre outils : trois outils
deterministes du flux A et ``submit_analysis`` qui cloture son travail. Il ne
passe jamais le portefeuille ni la date de reference : ``ToolBox`` les fixe.
Aucun outil de passage d'ordres n'existe, ni ici ni ailleurs.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from .bedrock_client import redact_text
from .contracts import AnalystSubmission, EvidenceEntry, InvestmentIdea, Portfolio, ToolResult
from .pipeline_deps import PipelineDeps

MAX_TOOL_CALLS = 12
MAX_VARIANTS = 2
MAX_HIGHLIGHTS = 2
REASON_CODES = ("reduce_weight", "change_funding_source", "spread_across_existing")
UNSUPPORTED_CODES = ("return_prediction", "personalized_advice", "order_execution", "other")
FUNDING_SOURCES = ("pro_rata", "from_ticker")
_TICKER = re.compile(r"^[A-Z0-9.\-]{1,12}$")
DATA_TOOL_NAMES = ("analyze_portfolio", "get_asset_facts", "simulate_portfolio_change")

_IDEA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "Symbole de l'actif, par exemple TSLA."},
        "target_weight": {"type": "number", "description": "Poids cible entre 0 et 1 (0.25 pour 25 %)."},
        "funding_source": {"type": "string", "enum": list(FUNDING_SOURCES)},
        "funding_ticker": {"type": ["string", "null"], "description": "Requis si funding_source vaut from_ticker."},
    },
    "required": ["ticker", "target_weight", "funding_source"],
}

TOOL_SPECS: list[dict[str, Any]] = [
    {"toolSpec": {
        "name": "analyze_portfolio",
        "description": "Radiographie du portefeuille fictif actuel : volatilite, perte maximale, concentration, expositions.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }},
    {"toolSpec": {
        "name": "get_asset_facts",
        "description": "Faits historiques d'un actif sur une periode explicite : rendement, volatilite, perte maximale, recuperation.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        }},
    }},
    {"toolSpec": {
        "name": "simulate_portfolio_change",
        "description": "Simulation avant/apres d'une idee de placement sur le portefeuille fictif. Simulation, jamais une recommandation.",
        "inputSchema": {"json": copy.deepcopy(_IDEA_SCHEMA)},
    }},
    {"toolSpec": {
        "name": "submit_analysis",
        "description": (
            "Cloture l'analyse. Aucune prose, aucun chiffre, aucun verdict : seulement l'idee comprise, "
            "au plus deux variantes (motif en code ferme), au plus deux preuves a mettre en avant, "
            "et les demandes non prises en charge."
        ),
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "understood_idea": copy.deepcopy(_IDEA_SCHEMA),
                "variants": {
                    "type": "array", "maxItems": MAX_VARIANTS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "reason_code": {"type": "string", "enum": list(REASON_CODES)},
                            "idea": copy.deepcopy(_IDEA_SCHEMA),
                        },
                        "required": ["reason_code", "idea"],
                    },
                },
                "highlight_evidence_ids": {"type": "array", "maxItems": MAX_HIGHLIGHTS, "items": {"type": "string"}},
                "unsupported_requests": {"type": "array", "items": {"type": "string", "enum": list(UNSUPPORTED_CODES)}},
            },
            "required": ["understood_idea"],
        }},
    }},
]


def tool_config() -> dict[str, Any]:
    """Configuration d'outils au format Converse (copie, pour eviter toute mutation partagee)."""
    return {"tools": copy.deepcopy(TOOL_SPECS)}


class ToolBudgetExceeded(Exception):
    """Le nombre maximal d'appels d'outils est atteint."""


class AgentFailure(Exception):
    """Un agent Bedrock n'a pas produit de sortie exploitable : le pipeline utilise le repli code."""


class AnalystFailure(AgentFailure):
    """L'analyste n'a pas produit de soumission exploitable : le pipeline bascule sur la sequence scriptee."""


class ExplainerFailure(AgentFailure):
    """L'explicateur n'a pas produit de JSON exploitable : le pipeline utilise le gabarit."""


@dataclass
class AnalystOutcome:
    """Resultat d'une analyse (agent ou sequence scriptee), avant gouvernance."""

    submission: AnalystSubmission
    actor: str                      # "agent" ou "code"
    model_id: str | None = None
    turns: int = 0
    stop_reason: str = "submitted"


def normalize_idea(raw: Any) -> tuple[InvestmentIdea | None, str | None]:
    """Valide et normalise une idee brute. Rend (idee, None) ou (None, message en francais)."""
    if not isinstance(raw, dict):
        return None, "L'idee doit etre un objet avec ticker, target_weight et funding_source."
    ticker = raw.get("ticker")
    weight = raw.get("target_weight")
    source = raw.get("funding_source")
    funding_ticker = raw.get("funding_ticker")
    if not isinstance(ticker, str) or not _TICKER.match(ticker.strip().upper()):
        return None, "ticker manquant ou invalide (lettres, chiffres, point ou tiret, 12 caracteres au plus)."
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 < float(weight) <= 1:
        return None, "target_weight doit etre un nombre entre 0 (exclu) et 1 (inclus)."
    if source not in FUNDING_SOURCES:
        return None, "funding_source doit valoir pro_rata ou from_ticker."
    if source == "from_ticker":
        if not isinstance(funding_ticker, str) or not _TICKER.match(funding_ticker.strip().upper()):
            return None, "funding_ticker est requis et valide quand funding_source vaut from_ticker."
    else:
        funding_ticker = None
    return InvestmentIdea(
        ticker=ticker.strip().upper(),
        target_weight=float(weight),
        funding_source=source,
        funding_ticker=funding_ticker.strip().upper() if isinstance(funding_ticker, str) else None,
    ), None


class ToolBox:
    """Execute les outils deterministes pour un run, avec trace et budget d'appels.

    Chaque resultat valide est passe au registre de preuves (qui attribue les
    ``evidence_id``). La liste ``calls`` alimente l'etape 1 de la trace : elle
    est construite par le code a partir des appels reels, jamais par le modele.
    """

    def __init__(
        self,
        deps: PipelineDeps,
        portfolio: Portfolio,
        *,
        as_of: str | None,
        capital_cad: float | None,
        max_calls: int = MAX_TOOL_CALLS,
    ) -> None:
        self._deps = deps
        self._portfolio = portfolio
        self._as_of = as_of
        self._capital_cad = capital_cad
        self._registry = deps.make_registry()
        self.max_calls = max_calls
        self.calls: list[dict[str, Any]] = []
        self.results: list[ToolResult] = []

    @property
    def calls_used(self) -> int:
        return len(self.calls)

    def evidence(self) -> dict[str, EvidenceEntry]:
        """Toutes les preuves enregistrees pendant ce run, indexees par evidence_id."""
        entries: dict[str, EvidenceEntry] = {}
        for result in self.results:
            for entry in result.get("evidence", []) or []:
                entries[entry["evidence_id"]] = entry
        return entries

    def call(self, tool_name: str, params: dict[str, Any] | None = None) -> ToolResult:
        """Execute un outil de donnees. Toute erreur devient un ToolResult de statut ``error``."""
        if self.calls_used >= self.max_calls:
            raise ToolBudgetExceeded(f"Budget de {self.max_calls} appels d'outils atteint.")
        params = dict(params or {})
        index = self.calls_used + 1
        result = self._execute(tool_name, params, index)
        evidence_ids = [entry["evidence_id"] for entry in result.get("evidence", []) or []]
        self.calls.append({
            "tool_name": tool_name,
            "params": params,
            "status": result["status"],
            "evidence_ids": evidence_ids,
        })
        self.results.append(result)
        return result

    def _execute(self, tool_name: str, params: dict[str, Any], index: int) -> ToolResult:
        if tool_name not in DATA_TOOL_NAMES:
            return self._error(tool_name, params, index, f"Outil inconnu : {tool_name}.")
        try:
            if tool_name == "analyze_portfolio":
                raw = self._deps.analyze_portfolio(
                    self._portfolio, as_of=self._as_of, capital_cad=self._capital_cad)
            elif tool_name == "get_asset_facts":
                ticker = params.get("ticker")
                if not isinstance(ticker, str) or not ticker.strip():
                    return self._error(tool_name, params, index, "ticker manquant ou invalide.")
                raw = self._deps.get_asset_facts(ticker.strip().upper(), as_of=self._as_of)
            else:
                idea, problem = normalize_idea(params)
                if idea is None:
                    return self._error(tool_name, params, index, problem or "Idee invalide.")
                raw = self._deps.simulate_portfolio_change(
                    self._portfolio, idea, as_of=self._as_of, capital_cad=self._capital_cad)
            result = copy.deepcopy(raw)
            result.setdefault("call_id", f"call-{index}")
            if result.get("status") == "ok":
                result = self._registry.register(result)
            return result
        except Exception as error:  # un outil defaillant ne doit jamais faire planter la boucle
            return self._error(tool_name, params, index, f"Echec de l'outil ({type(error).__name__}).")

    @staticmethod
    def _error(tool_name: str, params: dict[str, Any], index: int, message: str) -> ToolResult:
        return ToolResult(
            tool_name=tool_name, call_id=f"call-{index}", params=params, status="error",
            error_message=redact_text(message), data={}, evidence=[],
        )
