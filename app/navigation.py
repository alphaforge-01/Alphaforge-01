"""Pages de l'application et liens entre elles (st.navigation).

Parcours de la démo : accueil (niveau, profil), simulation (conversation et
réglages manuels), puis deux pages de vérification. Le formulaire de profil
construit a sa propre page. Chaque page est un fichier de
`app/views/`. Icônes Material seulement, aucun emoji.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import streamlit as st

import ui_texts as texts
from components.banners import render_page_heading
from components.style import NEXT_KEY


@dataclass(frozen=True)
class PageSpec:
    key: str
    path: str        # relatif au point d'entrée app/streamlit_app.py
    icon: str
    url_path: str


JOURNEY: Tuple[PageSpec, ...] = (
    PageSpec("home", "views/home_page.py", ":material/home:", "accueil"),
    PageSpec("simulation", "views/simulation_page.py", ":material/forum:", "simulation"),
    PageSpec("custom", "views/custom_profile_page.py", ":material/tune:", "profil-fictif"),
)
CHECKS: Tuple[PageSpec, ...] = (
    PageSpec("guardrail", "views/guardrail_page.py", ":material/shield:", "garde-fou"),
    PageSpec("sources", "views/sources_page.py", ":material/menu_book:", "sources"),
)
ALL_PAGES: Dict[str, PageSpec] = {spec.key: spec for spec in JOURNEY + CHECKS}
# Bouton "Étape suivante" : le fil de la démo.
_NEXT = {"home": "simulation", "custom": "simulation", "simulation": "guardrail", "guardrail": "sources"}


def _page(spec: PageSpec, default: bool = False):
    return st.Page(spec.path, title=texts.PAGE_NAMES[spec.key], icon=spec.icon,
                   url_path=spec.url_path, default=default)


def build():
    """Navigation de la barre latérale. Les pages sont recréées à chaque exécution."""
    return st.navigation({
        texts.NAV_JOURNEY: [_page(spec, default=index == 0) for index, spec in enumerate(JOURNEY)],
        texts.NAV_CHECKS: [_page(spec) for spec in CHECKS],
    })


def heading(key: str) -> None:
    """Titre de la page et une seule phrase d'introduction."""
    render_page_heading(texts.PAGE_NAMES[key], texts.PAGE_INTROS[key])


def link(key: str, label: Optional[str] = None) -> None:
    spec = ALL_PAGES[key]
    st.page_link(spec.path, label=label or texts.GO_TO.format(page=texts.PAGE_NAMES[key]),
                 icon=":material/arrow_forward:")


def missing(message: str, key: str) -> None:
    """Message court quand une page a besoin d'un élément absent, avec le lien vers la page qui le fournit."""
    st.info(message)
    link(key)


def next_step(current: str) -> None:
    """Bouton "Étape suivante" en bas de page, pour garder le fil de la démo."""
    following = _NEXT.get(current)
    if following is None:
        return
    st.divider()
    with st.container(key=NEXT_KEY, horizontal=True, horizontal_alignment="right"):
        link(following, texts.NEXT_STEP.format(page=texts.PAGE_NAMES[following]))
