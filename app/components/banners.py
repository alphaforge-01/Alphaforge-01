"""En-tête commun à toutes les pages : marque, mode, profil, idée, avertissement, données d'essai."""
from __future__ import annotations

from html import escape
from typing import Optional

import streamlit as st

import ui_texts as texts
from components.style import html


def render_header(mode: str, profile_name: Optional[str], idea_text: Optional[str]) -> None:
    """Ligne compacte : marque à gauche, contexte actif (mode, profil, idée) à droite (US-15)."""
    chips = (
        (texts.HEADER_MODE, texts.MODE_LABELS.get(mode, mode)),
        (texts.HEADER_PROFILE, profile_name or texts.HEADER_NONE),
        (texts.HEADER_IDEA, idea_text or texts.HEADER_NO_IDEA),
    )
    chips_html = "".join(
        f'<span class="af-chip">{escape(label)} : <b>{escape(value)}</b></span>' for label, value in chips)
    html(
        f'<div class="af-header"><div class="af-brand">{escape(texts.BRAND)}'
        f'<span>{escape(texts.BRAND_TAGLINE)}</span></div>'
        f'<div class="af-chips">{chips_html}</div></div>'
    )


def render_disclaimer() -> None:
    """Avertissement court (US-12), rendu seul : il ne dépend d'aucune donnée et ne disparaît jamais."""
    html(f'<div class="af-disclaimer">{escape(texts.DISCLAIMER)}</div>')


def render_fixture_banner() -> None:
    """Bandeau visible dès que les chiffres viennent des fixtures (is_fixture)."""
    html(f'<div class="af-fixture">{escape(texts.FIXTURE_BANNER)}</div>')


def render_page_heading(title: str, intro: str) -> None:
    """Titre de page et une seule phrase d'introduction."""
    st.header(title, anchor=False)
    html(f'<div class="af-intro">{escape(intro)}</div>')
