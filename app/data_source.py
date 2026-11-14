"""Seul point de contact entre l'interface et le reste du projet.

Trois sources de données (docs/ui_spec.md, section 3) :
- "fixture" : fichiers de tests/fixtures/, chiffres inventés, jusqu'à J2 ;
- "offline" : fonctions de src/alphaforge/ sans appel à Bedrock ;
- "bedrock" : mêmes fonctions, avec les agents sur Amazon Bedrock.

Le reste de l'interface ne sait pas d'où viennent les données. Ce module ne
calcule rien : il lit des fixtures ou appelle les fonctions des autres flux.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import ui_texts as texts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
FIXTURE_IDEA_PATH = FIXTURES_DIR / "idea_tsla_25.json"

MODES = ("fixture", "offline", "bedrock")
DEFAULT_MODE = "fixture"


class DataUnavailable(Exception):
    """Donnée absente dans le mode choisi. Le message, en français, s'affiche tel quel."""


def resolve_mode(raw: Optional[str]) -> str:
    """Valeur initiale du mode, par exemple lue dans ALPHAFORGE_MODE. Inconnue : fixture."""
    return raw if raw in MODES else DEFAULT_MODE


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_results() -> Dict[str, Dict[str, Any]]:
    """profile_id -> AnalysisResult, lu dans tests/fixtures/analysis_result_<id>_tsla.json."""
    results: Dict[str, Dict[str, Any]] = {}
    for path in sorted(FIXTURES_DIR.glob("analysis_result_*_tsla.json")):
        result = _read_json(path)
        results[result["profile"]["profile_id"]] = result
    return results


def _same_idea(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    keys = ("ticker", "target_weight", "funding_source", "funding_ticker")
    return all(left.get(key) == right.get(key) for key in keys)


def get_fixture_idea() -> Dict[str, Any]:
    """Idée de démonstration "25 % dans TSLA" (InvestmentIdea)."""
    return _read_json(FIXTURE_IDEA_PATH)


def get_personas(mode: str) -> Dict[str, Dict[str, Any]]:
    """profile_id -> {profile, portfolio, age, occupation_fr, summary_fr}.

    En mode fixture, tout vient des fixtures d'analyse, pour que le profil affiché
    et l'analyse restent cohérents. L'âge, le métier et le résumé y sont absents.
    """
    if mode == "fixture":
        return {
            profile_id: {
                "profile": result["profile"],
                "portfolio": result["portfolio_before"],
                "age": None,
                "occupation_fr": None,
                "summary_fr": None,
            }
            for profile_id, result in _fixture_results().items()
        }
    try:
        from alphaforge.profiles import load_personas
    except ImportError as exc:
        raise DataUnavailable(texts.MSG_PROFILES_NOT_READY) from exc
    return load_personas()


def check_profile_answers(answers: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Problèmes {code, severity, fields, message_fr} du profil construit (flux B)."""
    try:
        from alphaforge.profiles import check_answers
    except ImportError as exc:
        raise DataUnavailable(texts.MSG_PROFILE_BUILDER_NOT_READY) from exc
    return check_answers(answers)


def build_custom_persona(answers: Dict[str, Any], portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Persona "custom" : profil construit par le flux B et portefeuille fictif choisi.

    Lève ProfileValidationError (flux B) si une réponse est invalide.
    """
    try:
        from alphaforge.profiles import build_profile_from_answers
    except ImportError as exc:
        raise DataUnavailable(texts.MSG_PROFILE_BUILDER_NOT_READY) from exc
    return {
        "profile": build_profile_from_answers(answers),
        "portfolio": copy.deepcopy(portfolio),
        "age": None,
        "occupation_fr": None,
        "summary_fr": None,
    }


def get_analysis(mode: str, profile: Dict[str, Any], portfolio: Dict[str, Any],
                 idea: Dict[str, Any]) -> Dict[str, Any]:
    """AnalysisResult pour un profil, son portefeuille et une idée."""
    if mode == "fixture":
        result = _fixture_results().get(profile["profile_id"])
        if result is None:
            raise DataUnavailable(texts.MSG_FIXTURE_PROFILE_MISSING)
        if not _same_idea(idea, result["idea"]):
            raise DataUnavailable(texts.MSG_FIXTURE_IDEA_ONLY)
        return result
    try:
        from alphaforge.analysis_pipeline import run_analysis
    except ImportError as exc:
        raise DataUnavailable(texts.MSG_PIPELINE_NOT_READY) from exc
    try:
        from alphaforge.analysis_pipeline import AnalysisError
    except ImportError as exc:
        raise DataUnavailable(texts.MSG_PIPELINE_NOT_READY) from exc
    try:
        return run_analysis(profile, portfolio, idea, mode=mode)
    except AnalysisError as exc:
        raise DataUnavailable(texts.MSG_ANALYSIS_REFUSED.format(reason=exc)) from exc
    except ValueError as exc:
        # Bouchons du flux C : seuls Robert et Amira ont une fixture tant que
        # les outils du flux A ne sont pas fusionnés.
        raise DataUnavailable(texts.MSG_PROFILE_NOT_COVERED) from exc
