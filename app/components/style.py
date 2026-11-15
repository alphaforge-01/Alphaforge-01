"""Styles de l'interface, centralisés ici (seul module qui injecte du CSS).

Les couleurs de base viennent de .streamlit/config.toml. Ce module ajoute
seulement : l'en-tête compact, les pastilles de statut (toujours couleur et
texte), le verdict, les étiquettes des trois zones (faits, hypothèses,
simulation), des cartes de métriques de hauteur égale et les bulles des
niveaux Novice / Pro de l'accueil. Les blocs Streamlit
sont ciblés par la classe `st-key-<clé>` que Streamlit pose sur un conteneur
qui a une clé.
"""
from __future__ import annotations

import re
from html import escape

import streamlit as st

import ui_texts as texts

# Préfixes de clés de conteneurs reconnus par le CSS ci-dessous.
CARD_KEY = "card-"
ZONE_KEY = "zone-"
NEXT_KEY = "next-step"

_CSS = """
<style>
[data-testid="stMainBlockContainer"] { padding-top: 2.2rem; max-width: 1180px; }
h1, h2, h3 { letter-spacing: -0.01em; }

.af-header { display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: .5rem; }
.af-brand { font-weight: 700; font-size: 1.1rem; color: #14325c; }
.af-brand span { font-weight: 400; font-size: .9rem; color: #5b6675; margin-left: .45rem; }
.af-chips { display: flex; flex-wrap: wrap; gap: .35rem; }
.af-chip { font-size: .78rem; padding: .12rem .6rem; border-radius: 999px;
  background: #eef2f7; border: 1px solid #dbe2ea; color: #1a2332; }
.af-chip b { font-weight: 600; }
.af-disclaimer { margin: .45rem 0 .15rem; padding: .35rem .75rem; border-radius: .45rem;
  font-size: .82rem; background: #fff8e6; border: 1px solid #f0dfa8; color: #5c4700; }
.af-fixture { margin: .25rem 0; padding: .35rem .75rem; border-radius: .45rem;
  font-size: .82rem; background: #fdecea; border: 1px solid #f3c2bd; color: #8a1c12;
  font-weight: 600; }

.af-intro { color: #4a5563; margin: -.4rem 0 .6rem; }

.af-pill { display: inline-block; padding: .1rem .6rem; border-radius: 999px;
  font-size: .8rem; font-weight: 600; border: 1px solid transparent; }
.af-pill--compliant { background: #e7f5ec; color: #1d6b37; border-color: #bfe3cb; }
.af-pill--tension { background: #fff1e0; color: #8f4700; border-color: #f5cf9f; }
.af-pill--conflict { background: #fdeaea; color: #a3191b; border-color: #f2bcbc; }
.af-pill--missing_info { background: #eef0f3; color: #45505e; border-color: #d5dae1; }

.af-verdict { border: 1px solid #dbe2ea; border-left: 6px solid #8a94a3;
  border-radius: .6rem; padding: .8rem 1rem; margin: .4rem 0 .8rem; background: #fbfcfd; }
.af-verdict--compliant { border-left-color: #2e8b57; }
.af-verdict--tension { border-left-color: #e08a1e; }
.af-verdict--conflict { border-left-color: #c62828; }
.af-verdict-head { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap;
  font-size: 1.05rem; font-weight: 650; }
.af-verdict-sub { color: #5b6675; font-size: .85rem; margin-top: .2rem; }
.af-verdict ul { margin: .5rem 0 0 1.1rem; padding: 0; }
.af-verdict li { margin: .15rem 0; font-size: .92rem; }
.af-verdict-note { color: #5b6675; font-size: .78rem; margin-top: .45rem; }

.af-zone { display: inline-block; font-size: .7rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; padding: .05rem .5rem; border-radius: .3rem; margin-bottom: .2rem; }
.af-zone--facts { background: #e8f0fb; color: #1d4e89; }
.af-zone--assumptions { background: #fdf3dc; color: #7a5300; }
.af-zone--simulation { background: #f1eafb; color: #5b2f99; }
[class*="st-key-zone-facts"] { border-left: 4px solid #1d4e89 !important; }
[class*="st-key-zone-assumptions"] { border-left: 4px solid #c99a2e !important; }
[class*="st-key-zone-simulation"] { border-left: 4px solid #7b4fc0 !important; }

[class*="st-key-card-"] { min-height: 7.4rem; }
[class*="st-key-card-"] [data-testid="stPopover"] button p { font-size: 1.35rem; font-weight: 650; }

[class*="st-key-next-step"] a { background: #1d4e89; border-radius: .5rem; padding: .35rem .9rem; }
[class*="st-key-next-step"] a p, [class*="st-key-next-step"] a span { color: #ffffff !important; }

.af-levels { display: flex; justify-content: space-between; margin: .2rem 0 -.2rem; }
.af-level { position: relative; display: inline-block; cursor: help; outline: none;
  font-size: .85rem; font-weight: 600; padding: .15rem .7rem; border-radius: 999px;
  background: #eef2f7; border: 1px solid #dbe2ea; color: #1a2332; }
.af-level--active { background: #1d4e89; border-color: #1d4e89; color: #ffffff; }
.af-bubble { visibility: hidden; opacity: 0; transition: opacity .15s ease-in-out;
  position: absolute; z-index: 1000; top: calc(100% + .6rem); left: 0;
  width: min(28rem, 85vw); padding: .7rem .85rem; border-radius: .6rem;
  background: #ffffff; border: 1px solid #c9d3df; box-shadow: 0 6px 18px rgba(20, 50, 92, .18);
  color: #1a2332; font-size: .85rem; font-weight: 400; line-height: 1.45; text-align: left; }
.af-bubble::before { content: ""; position: absolute; top: -.45rem; left: 1.2rem;
  border-width: 0 .45rem .45rem; border-style: solid;
  border-color: transparent transparent #c9d3df; }
.af-level--end .af-bubble { left: auto; right: 0; }
.af-level--end .af-bubble::before { left: auto; right: 1.2rem; }
.af-level:hover .af-bubble, .af-level:focus .af-bubble { visibility: visible; opacity: 1; }
.af-bubble-title { font-weight: 650; margin-bottom: .2rem; }
.af-bubble-desc { color: #5b6675; margin-bottom: .45rem; }
.af-bubble-source { color: #5b6675; font-size: .75rem; margin-top: .45rem; }
/* Curseur de l'accueil : les étiquettes à bulle nomment déjà les niveaux, on masque ceux du curseur. */
[class*="st-key-home_level"] [data-testid="stSliderThumbValue"],
[class*="st-key-home_level"] [data-testid="stSliderTickBar"] { display: none; }

[data-testid="stSidebar"] .af-side-disclaimer { font-size: .78rem; color: #5c4700;
  background: #fff8e6; border: 1px solid #f0dfa8; border-radius: .45rem; padding: .4rem .6rem; }
</style>
"""


def inject() -> None:
    """À appeler une fois par exécution, avant tout affichage."""
    st.markdown(_CSS, unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def pill(status: str) -> str:
    """Pastille de statut : couleur et libellé, jamais la couleur seule."""
    label = texts.STATUS_LABELS.get(status, status)
    return f'<span class="af-pill af-pill--{escape(status)}">{escape(label)}</span>'


def _inline_html(text: str) -> str:
    """Texte Markdown court en HTML sûr : échappé, gras conservé, `$` neutralisé, sans ligne vide.

    Une ligne vide couperait le bloc HTML pour le moteur Markdown de Streamlit.
    """
    safe = escape(text).replace("$", "&#36;")
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    return "<br>".join(line for line in safe.splitlines() if line.strip())


def level_bubbles(items: list) -> None:
    """Étiquettes de niveau alignées sur les extrémités du curseur ; une bulle s'ouvre au survol.

    `items` : dicts {label, title, description, example, source, active}, dans l'ordre du curseur.
    Les étiquettes sont focalisables : la bulle s'ouvre aussi au clavier et au toucher.
    """
    parts = []
    for position, item in enumerate(items):
        classes = ["af-level"]
        if item["active"]:
            classes.append("af-level--active")
        if position == len(items) - 1 and position > 0:
            classes.append("af-level--end")
        parts.append(
            f'<span class="{" ".join(classes)}" tabindex="0">{escape(item["label"])}'
            f'<span class="af-bubble" role="tooltip">'
            f'<div class="af-bubble-title">{escape(item["title"])}</div>'
            f'<div class="af-bubble-desc">{escape(item["description"])}</div>'
            f'<div>{_inline_html(item["example"])}</div>'
            f'<div class="af-bubble-source">{escape(item["source"])}</div>'
            f'</span></span>')
    html(f'<div class="af-levels">{"".join(parts)}</div>')


def zone_label(kind: str) -> None:
    """Étiquette d'une zone (faits, hypothèses, simulation), avec son info-bulle."""
    html(f'<span class="af-zone af-zone--{kind}" title="{escape(texts.ZONE_HELP[kind])}">'
         f'{escape(texts.ZONE_LABELS[kind])}</span>')


def zone(kind: str, key: str):
    """Conteneur bordé d'une zone, avec sa couleur et son étiquette. S'utilise avec `with`."""
    container = st.container(border=True, key=f"{ZONE_KEY}{kind}-{key}")
    with container:
        zone_label(kind)
        st.caption(texts.ZONE_HELP[kind])
    return container
