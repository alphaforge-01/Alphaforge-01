"""Évaluation de la compréhension des messages de la page Simulation.

Pourquoi : savoir, chiffres à l'appui, ce que le système comprend et ce qu'il rate, au lieu
d'une impression. Le jeu de phrases (`tests/fixtures/dialogue_phrases.json`) porte pour
chaque phrase le **comportement idéal** attendu : jamais deviner un actif ou un poids,
refuser ce qui est interdit. Une phrase réussit si chaque champ attendu (statut, intention,
terme, actif, poids, raison) est égal au résultat ; les champs non attendus sont ignorés.

Le module évalue n'importe quel « compreneur » : par défaut les règles déterministes
(`request_parsing.parse_request`), et plus tard l'interprète sur Bedrock, avec la même
signature. Aucun appel réseau ici. Les phrases sont inventées ; le portefeuille est fictif.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from alphaforge import request_parsing

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHRASES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "dialogue_phrases.json"
EXPECTED_FIELDS = ("status", "answer_kind", "term_id", "ticker", "target_weight", "reason")

# understand(text, universe, held_tickers, previous_idea) -> dict au format de ParsedRequest
Understand = Callable[[str, Sequence[Mapping[str, Any]], Sequence[str], Optional[Mapping[str, Any]]], Mapping[str, Any]]


def load_phrases(path: Optional[Path] = None) -> Dict[str, Any]:
    """Jeu de phrases étiquetées. Lève ValueError si un identifiant est en double."""
    data = json.loads((path or PHRASES_PATH).read_text(encoding="utf-8"))
    ids = [phrase["id"] for phrase in data["phrases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Identifiants de phrases en double dans le jeu de dialogue")
    return data


def rules_understand(text: str, universe: Sequence[Mapping[str, Any]], held_tickers: Sequence[str],
                     previous_idea: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Compreneur de référence : les règles déterministes du lot 1."""
    return dataclasses.asdict(request_parsing.parse_request(
        text, universe, held_tickers=held_tickers, previous_idea=previous_idea))


def observed_fields(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Champs comparables d'un résultat : le ticker et le poids viennent de l'idée, sinon des champs lus."""
    idea = result.get("idea") or {}
    tickers = result.get("tickers") or ()
    return {
        "status": result.get("status"),
        "answer_kind": result.get("answer_kind"),
        "term_id": result.get("term_id"),
        "ticker": idea.get("ticker") or (tickers[0] if len(tickers) == 1 else None),
        "target_weight": idea.get("target_weight") if idea else result.get("target_weight"),
        "reason": result.get("reason"),
    }


def compare(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> List[str]:
    """Champs attendus qui diffèrent (liste vide : la phrase est réussie)."""
    differences = []
    for field in EXPECTED_FIELDS:
        if field not in expected:
            continue
        wanted, got = expected[field], observed.get(field)
        if field == "target_weight" and wanted is not None and got is not None:
            if abs(float(wanted) - float(got)) > 1e-9:
                differences.append(field)
        elif wanted != got:
            differences.append(field)
    return differences


def evaluate(understand: Understand, universe: Sequence[Mapping[str, Any]], held_tickers: Sequence[str],
             phrases: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Évalue un compreneur sur tout le jeu ; rend le détail par phrase et par catégorie."""
    data = phrases or load_phrases()
    default_previous = data.get("previous_idea_default")
    rows = []
    for phrase in data["phrases"]:
        previous = default_previous if phrase.get("previous_idea") == "default" else None
        result = understand(phrase["text"], universe, held_tickers, previous)
        observed = observed_fields(result)
        differences = compare(phrase["expected"], observed)
        rows.append({"id": phrase["id"], "category": phrase["category"], "text": phrase["text"],
                     "expected": phrase["expected"], "observed": observed, "ok": not differences,
                     "differences": differences})
    by_category: Dict[str, Dict[str, int]] = {}
    for row in rows:
        stats = by_category.setdefault(row["category"], {"ok": 0, "total": 0})
        stats["total"] += 1
        stats["ok"] += int(row["ok"])
    return {"total": len(rows), "ok": sum(row["ok"] for row in rows),
            "by_category": by_category, "rows": rows}
