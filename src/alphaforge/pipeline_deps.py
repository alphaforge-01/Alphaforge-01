"""Dependances du pipeline : outils du flux A et mecanismes du flux B.

Le flux C ne reimplemente rien de ce qui appartient aux flux A et B. Ce module
decrit les fonctions attendues (signatures gelees du plan de sprint, section 3)
et les charge quand elles existent. Tant qu'elles n'existent pas, le pipeline
utilise les bouchons de ``fixture_collaborators`` et marque ses resultats
``is_fixture`` pour que l'interface affiche le bandeau "donnees d'essai".
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PipelineDeps:
    """Ensemble des fonctions externes dont le pipeline a besoin."""

    # flux A : outils deterministes (agent_tools.py) et registre de preuves (evidence.py)
    analyze_portfolio: Callable[..., Any]
    get_asset_facts: Callable[..., Any]
    simulate_portfolio_change: Callable[..., Any]
    make_registry: Callable[[], Any]          # fabrique un objet avec .register(tool_result)
    # flux B : gouvernance et explication en code
    evaluate: Callable[..., Any]
    build_brief: Callable[..., Any]
    render_template: Callable[..., Any]
    validate: Callable[..., Any]
    render_markdown: Callable[..., Any]
    is_fixture: bool = False
    supports_variants: bool = True
    # rend les limites {limit_id, text_novice, text_pro} pour une liste d'identifiants (None = fichier de reference du flux B)
    limits_for: Callable[[list[str]], list[dict]] | None = None


_REQUIRED = {
    "agent_tools": ("analyze_portfolio", "get_asset_facts", "simulate_portfolio_change"),
    "evidence": ("EvidenceRegistry",),
    "governance": ("evaluate",),
    "explanation_brief": ("build_brief",),
    "explanation_fallback": ("render_template",),
    "explanation_validator": ("validate",),
    "explanation_rendering": ("render_markdown",),
}


def load_real_deps() -> PipelineDeps | None:
    """Charge les vrais modules des flux A et B, ou rend None s'il en manque un."""
    loaded: dict[str, Any] = {}
    for module_name, attributes in _REQUIRED.items():
        try:
            module = importlib.import_module(f"alphaforge.{module_name}")
        except ModuleNotFoundError as error:
            # Seul un module absent est un cas normal. Une erreur d'import DANS un module existant
            # est un vrai bogue : elle remonte au lieu de basculer en silence sur les bouchons.
            if error.name != f"alphaforge.{module_name}":
                raise
            return None
        for attribute in attributes:
            if not hasattr(module, attribute):
                return None
            loaded[attribute] = getattr(module, attribute)
    return PipelineDeps(
        analyze_portfolio=loaded["analyze_portfolio"],
        get_asset_facts=loaded["get_asset_facts"],
        simulate_portfolio_change=loaded["simulate_portfolio_change"],
        make_registry=loaded["EvidenceRegistry"],
        evaluate=loaded["evaluate"],
        build_brief=loaded["build_brief"],
        render_template=loaded["render_template"],
        validate=loaded["validate"],
        render_markdown=loaded["render_markdown"],
        is_fixture=False,
    )


def resolve_deps() -> PipelineDeps:
    """Vrais modules si disponibles, sinon bouchons de fixtures (is_fixture=True)."""
    real = load_real_deps()
    if real is not None:
        return real
    from .fixture_collaborators import fixture_deps

    return fixture_deps()
