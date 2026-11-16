"""Outils de l'agent conversationnel et assemblage du dossier de reponse.

L'agent (voir `conversation_router.py`) choisit les outils ; ce module les execute avec du code
deterministe et rassemble leurs resultats dans un `ConversationBrief`. La reponse est ensuite redigee
par la chaine existante (`analysis_pipeline.answer_question` : agent, validateur, garde-fou, repli).

Les donnees viennent de fournisseurs injectes par l'interface (`ConversationProviders`) : le module ne
connait ni Streamlit ni le mode de donnees. Chaque outil renvoie au modele un resume court et citable
(identifiants E#, G#, T#), jamais un calcul a refaire. Aucun outil de passage d'ordres n'existe ;
`propose_idea` ne lance aucune simulation : elle produit une confirmation a cliquer.

Les appels sont enregistres (`calls`) pour reconstruire le meme dossier a un autre niveau sans
rappeler le modele (`replay`).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

MAX_TOOL_CALLS = 6
MAX_LISTED_ASSETS = 12
LEVELS = ("novice", "pro")
TRACE_PARAMS = ("ticker", "sector", "weight_pct")
_TICKER = re.compile(r"^[A-Z0-9.\-]{1,12}$")

# Secteurs de l'univers, regroupes sous des noms simples que le modele peut choisir.
SECTOR_GROUPS: dict[str, tuple[str, ...]] = {
    "technologie": ("Information Technology", "Communication Services", "Broad market (U.S. growth/tech-heavy)"),
    "finance": ("Financials",),
    "energie": ("Energy",),
    "sante": ("Health Care",),
    "consommation": ("Consumer Discretionary", "Consumer Staples"),
    "industrie": ("Industrials",),
    "services_publics": ("Utilities",),
    "obligations": ("Bonds (U.S. long Treasury)", "Bonds (U.S. aggregate)", "Bonds (Canada aggregate)",
                    "Bonds (Canada ultra short-term)"),
    "marche_large": ("Broad market (U.S.)", "Broad market (Canada)", "Broad market (U.S. growth/tech-heavy)"),
    "or": ("Gold",),
    "crypto": ("Crypto asset",),
}

TOOL_SPECS: list[dict[str, Any]] = [
    {"toolSpec": {
        "name": "lookup_glossary",
        "description": ("Definition d'un terme financier du glossaire du projet, au niveau de l'utilisateur. "
                        "Seule source de definitions : un terme absent n'a pas de definition."),
        "inputSchema": {"json": {"type": "object", "properties": {
            "term": {"type": "string", "description": "Le terme, en francais (ex. volatilite, correlation)."}},
            "required": ["term"]}}}},
    {"toolSpec": {
        "name": "get_profile_facts",
        "description": "Objectif, horizon, tolerance au risque et preferences declares du profil fictif.",
        "inputSchema": {"json": {"type": "object", "properties": {}}}}},
    {"toolSpec": {
        "name": "analyze_portfolio",
        "description": ("Radiographie du portefeuille fictif de depart : composition, part defensive, "
                        "volatilite et perte maximale historiques, controles du profil."),
        "inputSchema": {"json": {"type": "object", "properties": {}}}}},
    {"toolSpec": {
        "name": "get_asset_facts",
        "description": "Faits historiques d'un actif de l'univers (periode explicite, aucune prevision).",
        "inputSchema": {"json": {"type": "object", "properties": {
            "ticker": {"type": "string", "description": "Symbole d'un actif de l'univers, ex. NVDA ou XIU.TO."}},
            "required": ["ticker"]}}}},
    {"toolSpec": {
        "name": "list_assets",
        "description": ("Actifs de l'univers d'un secteur, tels qu'ils figurent dans les donnees. "
                        "Liste factuelle : ne pas en choisir un pour l'utilisateur."),
        "inputSchema": {"json": {"type": "object", "properties": {
            "sector": {"type": "string", "enum": list(SECTOR_GROUPS)}},
            "required": ["sector"]}}}},
    {"toolSpec": {
        "name": "get_current_analysis",
        "description": ("Resultat de la derniere idee simulee : controles du profil (conforme, en tension, "
                        "en conflit) et leurs preuves. Pour les questions 'pourquoi' et 'que faudrait-il changer'."),
        "inputSchema": {"json": {"type": "object", "properties": {}}}}},
    {"toolSpec": {
        "name": "propose_idea",
        "description": ("Reprend une idee que l'UTILISATEUR a exprimee (actif ET poids cites dans son message) "
                        "pour qu'il la confirme d'un clic. Ne lance aucune simulation. Jamais un actif ou un poids "
                        "choisi par toi."),
        "inputSchema": {"json": {"type": "object", "properties": {
            "ticker": {"type": "string"},
            "weight_pct": {"type": "integer", "minimum": 1, "maximum": 100,
                           "description": "Poids vise cite par l'utilisateur, en pourcentage entier."}},
            "required": ["ticker", "weight_pct"]}}}},
    {"toolSpec": {
        "name": "finish",
        "description": "Termine la collecte : la reponse sera redigee a partir des outils appeles.",
        "inputSchema": {"json": {"type": "object", "properties": {}}}}},
]
DATA_TOOLS = tuple(spec["toolSpec"]["name"] for spec in TOOL_SPECS if spec["toolSpec"]["name"] != "finish")
# Type de reponse retenu quand plusieurs outils sont appeles : le plus specifique d'abord.
KIND_PRIORITY = (("get_current_analysis", "explanation"), ("analyze_portfolio", "xray"),
                 ("get_asset_facts", "xray"), ("list_assets", "xray"), ("lookup_glossary", "concept"),
                 ("get_profile_facts", "profile"))


def tool_config() -> dict[str, Any]:
    return {"tools": copy.deepcopy(TOOL_SPECS)}


class ToolBudgetExceeded(RuntimeError):
    """Plus d'appels d'outils que `MAX_TOOL_CALLS`."""


@dataclass
class ConversationProviders:
    """Donnees fournies par l'interface. Chaque fonction peut lever une exception : l'outil rend une erreur."""
    profile: Mapping[str, Any]
    profile_context: Callable[[], Optional[Mapping[str, Any]]]
    profile_facts: Callable[[], Mapping[str, Any]]          # ToolResult de agent_tools.get_profile_facts
    xray: Callable[[], Mapping[str, Any]]                   # {"evidence": {id: entry}, "governance": {...}}
    asset_facts: Callable[[str], Mapping[str, Any]]         # {"evidence": {id: entry}, "data": {...}}
    universe: Callable[[], Sequence[Mapping[str, Any]]]
    glossary: Callable[[], Sequence[Mapping[str, Any]]]
    analysis_brief: Callable[[str], Optional[Mapping[str, Any]]]   # dossier d'explication au niveau, ou None


def _normalize(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")


@dataclass
class ConversationToolBox:
    """Execute les outils et accumule un dossier unique, renumerote (E#, G#) sans collision."""
    providers: ConversationProviders
    level: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    glossary: list[dict[str, Any]] = field(default_factory=list)
    limits: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)
    idea: Optional[dict[str, Any]] = None
    proposal: Optional[dict[str, Any]] = None
    _keys: dict[str, str] = field(default_factory=dict)

    # -- enregistrement des preuves -------------------------------------------------
    def _add_evidence(self, entries: Sequence[Mapping[str, Any]]) -> dict[str, str]:
        """Ajoute des preuves et rend la table ancien identifiant -> nouvel identifiant."""
        mapping: dict[str, str] = {}
        for entry in entries:
            old = str(entry.get("evidence_id") or "")
            key = str(entry.get("evidence_key") or old)
            if key in self._keys:
                mapping[old] = self._keys[key]
                continue
            new_id = f"E{len(self.evidence) + 1}"
            item = copy.deepcopy(dict(entry))
            item["evidence_id"] = new_id
            self.evidence.append(item)
            self._keys[key] = new_id
            mapping[old] = new_id
        return mapping

    def _add_checks(self, checks: Sequence[Mapping[str, Any]], mapping: Mapping[str, str]) -> list[str]:
        added = []
        for check in checks:
            item = copy.deepcopy(dict(check))
            item["check_id"] = f"G{len(self.checks) + 1}"
            item["evidence_ids"] = [mapping[eid] for eid in check.get("evidence_ids") or [] if eid in mapping]
            self.checks.append(item)
            added.append(item["check_id"])
        return added

    @staticmethod
    def _summary(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [{"id": e["evidence_id"], "label": e.get("label_fr", "")} for e in entries]

    # -- outils ---------------------------------------------------------------------
    def call(self, name: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if name not in DATA_TOOLS:
            return {"status": "error", "error_message": f"Outil inconnu : {name}."}
        if len(self.calls) >= MAX_TOOL_CALLS:
            raise ToolBudgetExceeded(name)
        clean = {k: v for k, v in dict(params or {}).items() if isinstance(v, (str, int, float))}
        call = {"name": name, "params": clean}
        self.calls.append(call)
        before = len(self.evidence)
        try:
            result = getattr(self, f"_tool_{name}")(clean)
        except Exception as error:  # un outil defaillant ne fait jamais planter la conversation
            result = {"status": "error", "error_message": f"Outil indisponible ({type(error).__name__})."}
        call["status"] = str(result.get("status"))
        call["evidence_ids"] = [e["evidence_id"] for e in self.evidence[before:]]
        return result

    def trace_calls(self) -> list[dict[str, Any]]:
        """Appels pour la trace : parametres fermes seulement (le terme cherche peut venir de la question)."""
        return [{"tool_name": c["name"], "caller": "agent", "status": c.get("status"),
                 "params": {k: v for k, v in c["params"].items() if k in TRACE_PARAMS},
                 "evidence_ids": c.get("evidence_ids", [])} for c in self.calls]

    def _tool_lookup_glossary(self, params: Mapping[str, Any]) -> dict[str, Any]:
        wanted = _normalize(str(params.get("term", "")))[:60].strip()
        catalog = list(self.providers.glossary())
        known = [term["term"] for term in catalog]
        # Memes mots-cles que les regles de la conversation ("variations" -> volatilite), puis le nom du terme.
        from .request_parsing import find_term, normalize
        matched_id = find_term(normalize(wanted)) if wanted else None
        for term in catalog:
            names = [term["term"]] + list(term.get("synonyms") or [])
            if wanted and (term["term_id"] == matched_id
                           or any(_normalize(n) in wanted or wanted in _normalize(n) for n in names)):
                text = term.get(self.level) or {}
                if term["term_id"] not in {g["term_id"] for g in self.glossary}:
                    self.glossary.append({"term_id": term["term_id"], "term": term["term"],
                                          "definition": text.get("definition", ""),
                                          "analogy": text.get("analogy", "")})
                self.focus.append(term["term_id"])
                return {"status": "ok", "term_id": term["term_id"], "term": term["term"],
                        "definition": text.get("definition", ""), "analogy": text.get("analogy", "")}
        missing = f"definition:{wanted}" if wanted else "definition"
        if missing not in self.missing:
            self.missing.append(missing)
        return {"status": "not_found", "message": "Terme absent du glossaire du projet.", "known_terms": known}

    def _tool_get_profile_facts(self, params: Mapping[str, Any]) -> dict[str, Any]:
        result = self.providers.profile_facts()
        if result.get("status") != "ok":
            return {"status": "error", "error_message": str(result.get("error_message") or result.get("status"))}
        mapping = self._add_evidence([{**e, "evidence_id": f"P{i}"} for i, e in
                                      enumerate(result.get("evidence") or [], start=1)])
        for item in (result.get("data") or {}).get("missing") or []:
            if item not in self.missing:
                self.missing.append(str(item))
        added = [e for e in self.evidence if e["evidence_id"] in set(mapping.values())]
        return {"status": "ok", "evidence": self._summary(added),
                "missing": list((result.get("data") or {}).get("missing") or [])}

    def _tool_analyze_portfolio(self, params: Mapping[str, Any]) -> dict[str, Any]:
        xray = self.providers.xray()
        mapping = self._add_evidence(list(xray["evidence"].values()))
        check_ids = self._add_checks(list((xray.get("governance") or {}).get("checks") or []), mapping)
        added = [e for e in self.evidence if e["evidence_id"] in set(mapping.values())]
        checks = [c for c in self.checks if c["check_id"] in check_ids]
        return {"status": "ok", "evidence": self._summary(added),
                "checks": [{"id": c["check_id"], "label": c.get("label_fr", ""), "status": c.get("status")}
                           for c in checks]}

    def _known_ticker(self, raw: Any) -> Optional[str]:
        ticker = str(raw or "").strip().upper()
        if not _TICKER.match(ticker):
            return None
        return ticker if ticker in {a["ticker"] for a in self.providers.universe()} else None

    def _tool_get_asset_facts(self, params: Mapping[str, Any]) -> dict[str, Any]:
        ticker = self._known_ticker(params.get("ticker"))
        if ticker is None:
            return {"status": "error", "error_message": "Actif hors de l'univers du projet."}
        facts = self.providers.asset_facts(ticker)
        mapping = self._add_evidence(list(facts["evidence"].values()))
        added = [e for e in self.evidence if e["evidence_id"] in set(mapping.values())]
        return {"status": "ok", "ticker": ticker, "evidence": self._summary(added)}

    def _tool_list_assets(self, params: Mapping[str, Any]) -> dict[str, Any]:
        sector = str(params.get("sector", ""))
        if sector not in SECTOR_GROUPS:
            return {"status": "error", "error_message": "Secteur inconnu.", "sectors": list(SECTOR_GROUPS)}
        names = SECTOR_GROUPS[sector]
        assets = [a for a in self.providers.universe() if a.get("sector") in names][:MAX_LISTED_ASSETS]
        if not assets:
            return {"status": "ok", "assets": [], "message": "Aucun actif de ce secteur dans l'univers."}
        listing = ", ".join(f"{a['ticker']} ({a.get('name') or a['ticker']})" for a in assets)
        mapping = self._add_evidence([{
            "evidence_id": "L1", "evidence_key": f"sector_assets:{sector}", "tool_name": "list_assets",
            "metric": "sector_assets", "subject": sector, "label_fr": f"Actifs de l'univers ({sector})",
            "value": listing, "unit": "text", "display_value": listing, "qualifier": None,
            "period_start": None, "period_end": None, "as_of": "", "currency": None,
        }])
        return {"status": "ok", "evidence": [{"id": mapping["L1"], "label": f"Actifs de l'univers ({sector})"}],
                "assets": [a["ticker"] for a in assets]}

    def _tool_get_current_analysis(self, params: Mapping[str, Any]) -> dict[str, Any]:
        brief = self.providers.analysis_brief(self.level)
        if not brief:
            if "analyse_en_cours" not in self.missing:
                self.missing.append("analyse_en_cours")
            return {"status": "not_found", "message": "Aucune idee n'a encore ete simulee."}
        mapping = self._add_evidence(list(brief.get("evidence") or []))
        check_ids = self._add_checks(list(brief.get("checks") or []), mapping)
        self.idea = copy.deepcopy(brief.get("idea"))
        self.limits.extend(copy.deepcopy(list(brief.get("limits") or [])))
        known = {g["term_id"] for g in self.glossary}
        self.glossary.extend(copy.deepcopy(g) for g in brief.get("glossary") or [] if g.get("term_id") not in known)
        checks = [c for c in self.checks if c["check_id"] in check_ids]
        self.focus.extend(c["check_id"] for c in checks if c.get("status") != "compliant")
        return {"status": "ok", "idea": self.idea,
                "checks": [{"id": c["check_id"], "label": c.get("label_fr", ""), "status": c.get("status"),
                            "evidence": c["evidence_ids"]} for c in checks]}

    def _tool_propose_idea(self, params: Mapping[str, Any]) -> dict[str, Any]:
        ticker = self._known_ticker(params.get("ticker"))
        try:
            weight = int(params.get("weight_pct"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            weight = 0
        if ticker is None or not 1 <= weight <= 100:
            return {"status": "error", "error_message": "Actif de l'univers et poids entier de 1 a 100 requis."}
        self.proposal = {"ticker": ticker, "target_weight": weight / 100, "funding_source": "pro_rata",
                         "funding_ticker": None}
        return {"status": "ok", "message": "Idee affichee pour confirmation par l'utilisateur."}

    # -- dossier ----------------------------------------------------------------------
    def answer_kind(self) -> str:
        called = {c["name"] for c in self.calls}
        for tool, kind in KIND_PRIORITY:
            if tool in called and (tool != "get_current_analysis" or self.idea is not None):
                return kind
        return "profile"

    def brief(self, question: str) -> dict[str, Any]:
        content = {
            "level": self.level,
            "answer_kind": self.answer_kind(),
            "focus": list(dict.fromkeys(self.focus)),
            "question": question,
            "profile_context": self.providers.profile_context(),
            "evidence": self.evidence,
            "checks": self.checks,
            "idea": self.idea,
            "glossary": self.glossary,
            "limits": self.limits,
            "cards": [],
            "missing": self.missing,
        }
        digest = hashlib.sha256(json.dumps({**content, "question": ""}, sort_keys=True, default=str,
                                           ensure_ascii=False).encode()).hexdigest()[:12]
        return {"brief_id": f"conversation-{digest}", **content}


def replay(providers: ConversationProviders, level: str, calls: Sequence[Mapping[str, Any]],
           question: str) -> dict[str, Any]:
    """Reconstruit le dossier d'une reponse a un autre niveau en rejouant ses outils, sans le modele."""
    box = ConversationToolBox(providers, level)
    for call in calls[:MAX_TOOL_CALLS]:
        if call.get("name") != "propose_idea":
            box.call(str(call.get("name")), dict(call.get("params") or {}))  # statut recalcule
    return box.brief(question)
