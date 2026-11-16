"""Pages de l'application et liens entre elles (st.navigation).

Parcours de la démo : accueil (niveau, profil), simulation (conversation et
réglages manuels), puis deux pages de vérification. Le formulaire de profil
construit a sa propre page. Chaque page est un fichier de
`app/views/`. Icônes Material seulement, aucun emoji.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Dict, Optional, Tuple

import streamlit as st

import ui_texts as texts
from components.banners import render_page_heading
from components.style import NEXT_KEY, html


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
# Pages ouvertes par le choix d'un profil : dans la barre du haut, simple repère quand on y est,
# lien seulement une fois un profil choisi (pour y revenir), absentes sinon.
INDICATOR_ONLY = frozenset({"simulation"})
# Action à part dans la barre (bouton à contour), distincte des pages du parcours.
NAV_ACTION = "custom"
# Bouton "Étape suivante" : le fil du parcours. Les pages de vérification sont hors du parcours.
_NEXT = {"home": "simulation", "custom": "simulation"}


def _page(spec: PageSpec, default: bool = False):
    return st.Page(spec.path, title=texts.PAGE_NAMES[spec.key], icon=spec.icon,
                   url_path=spec.url_path, default=default)


def build():
    """Toutes les pages, sans le menu automatique de Streamlit (recréées à chaque exécution).

    Le visiteur ne voit que le parcours (`render_top_nav`). Les pages de vérification restent
    enregistrées : le garde-fou est lié depuis le menu de paramètres (`render_check_links`),
    sources et méthode n'a pas de lien (adresse /sources, pour la démo et le jury).
    """
    pages = [_page(spec, default=index == 0) for index, spec in enumerate(JOURNEY)]
    pages += [_page(spec) for spec in CHECKS]
    return st.navigation(pages, position="hidden")


def current_key(page) -> Optional[str]:
    """Clé de la page en cours, retrouvée par son titre."""
    return next((key for key, name in texts.PAGE_NAMES.items() if name == page.title), None)


def render_top_nav(current: Optional[str] = None, has_profile: bool = False):
    """Barre horizontale en haut de chaque page : marque, parcours, puis une icône de paramètres.

    La simulation s'ouvre en choisissant un profil : dans la barre, c'est un repère non
    cliquable quand on y est, un lien quand un profil est déjà choisi, rien sinon. Renvoie le conteneur du menu de
    paramètres : l'appelant y place les réglages (pas de barre latérale).

    Renvoie aussi la place du contexte actif (mode, profil, idée), à droite de la marque :
    l'appelant la remplit une fois les données chargées.
    """
    with st.container(horizontal=True, vertical_alignment="center", key="af-topnav"):
        html(f'<div class="af-brand">{escape(texts.BRAND)}<span>{escape(texts.BRAND_TAGLINE)}</span></div>')
        context_slot = st.container(key="af-nav-context")
        st.space("stretch")
        for spec in JOURNEY:
            if spec.key in INDICATOR_ONLY and spec.key == current:
                html(f'<span class="af-nav-here" aria-current="page">{escape(texts.PAGE_NAMES[spec.key])}</span>')
            elif spec.key == NAV_ACTION:
                with st.container(key="af-nav-action", width="content"):
                    st.page_link(spec.path, label=texts.PAGE_NAMES[spec.key], icon=":material/add:")
            elif spec.key not in INDICATOR_ONLY or has_profile:
                st.page_link(spec.path, label=texts.PAGE_NAMES[spec.key])
        settings = st.popover(texts.SIDEBAR_ADVANCED, icon=":material/settings:", type="tertiary",
                              help=texts.SIDEBAR_ADVANCED, key="af-settings")
    return settings, context_slot


# Liens du menu de paramètres : le garde-fou seulement. Sources et méthode reste une page
# enregistrée (adresse /sources), sans lien : l'explication complète cite déjà sources et limites.
CHECK_LINKS = ("guardrail",)


def render_check_links() -> None:
    """Liens discrets vers les pages de vérification (à placer dans le menu de paramètres)."""
    st.caption(texts.NAV_CHECKS)
    for spec in (ALL_PAGES[key] for key in CHECK_LINKS):
        st.page_link(spec.path, label=texts.PAGE_NAMES[spec.key], icon=spec.icon)


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
