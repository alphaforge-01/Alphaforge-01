"""Styles de l'interface, centralisés ici (seul module qui injecte du CSS).

Les couleurs de base viennent de .streamlit/config.toml. Ce module ajoute
seulement : l'en-tête compact, les pastilles de statut (toujours couleur et
texte), le verdict, les étiquettes des trois zones (faits, hypothèses,
simulation), des cartes de métriques, l'accueil (titre-promesse, étapes) et
les cartes de personas côte à côte, de hauteur égale. Les blocs Streamlit
sont ciblés par la classe `st-key-<clé>` que Streamlit pose sur un conteneur
qui a une clé.
"""
from __future__ import annotations

from html import escape

import streamlit as st

import ui_texts as texts

# Préfixes de clés de conteneurs reconnus par le CSS ci-dessous.
CARD_KEY = "card-"
PERSONA_CARD_KEY = "persona-"
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
.af-disclaimer { display: flex; justify-content: flex-end; margin: .3rem 0 .1rem; }
.af-disclaimer span { font-size: .75rem; padding: .1rem .6rem; border-radius: 999px;
  background: #f3f6fa; border: 1px solid #dde3ea; color: #3d4a5a; cursor: help; }
.af-fixture { margin: .25rem 0; padding: .35rem .75rem; border-radius: .45rem;
  font-size: .82rem; background: #fdecea; border: 1px solid #f3c2bd; color: #8a1c12;
  font-weight: 600; }
.af-progress { display: flex; align-items: center; gap: .35rem; margin: .7rem 0 1rem;
  padding: .6rem .75rem; border: 1px solid #dbe2ea; border-radius: .65rem;
  background: #f8fafc; }
.af-progress-step { display: flex; align-items: center; gap: .3rem; color: #7a8492;
  font-size: .78rem; white-space: nowrap; }
.af-progress-step--done, .af-progress-step--active { color: #1d4e89; font-weight: 650; }
.af-progress-dot { width: .55rem; height: .55rem; border-radius: 50%; background: #c9d3df; }
.af-progress-step--done .af-progress-dot { background: #2e8b57; }
.af-progress-step--active .af-progress-dot { background: #1d4e89; box-shadow: 0 0 0 3px #dce9f8; }
.af-progress-line { flex: 1; height: 1px; min-width: .8rem; background: #dbe2ea; }
.af-chat-answer { border: 1px solid #dbe2ea; border-left: 4px solid #1d4e89;
  border-radius: .6rem; padding: .75rem .9rem; margin: .2rem 0 .65rem; background: #fbfcfe; }
.af-chat-answer--fallback { border-left-color: #c99a2e; }
.af-chat-meta { display: flex; gap: .4rem; align-items: center; margin-bottom: .35rem;
  color: #5b6675; font-size: .76rem; }
.af-chat-badge { border-radius: 999px; padding: .1rem .5rem; font-weight: 650;
  background: #e8f0fb; color: #1d4e89; }
.af-chat-badge--fallback { background: #fdf3dc; color: #7a5300; }
.af-chat-proof { border: 1px solid #e3e8ef; border-radius: .45rem; padding: .35rem .6rem;
  margin: .25rem 0; background: #ffffff; }

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
.af-split { display: flex; flex-wrap: wrap; gap: .8rem; margin-top: .35rem; font-size: .82rem; color: #5b6675; }
.af-split-item { display: inline-flex; align-items: center; gap: .35rem; }
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

/* Accueil : titre-promesse et trois étapes. */
.af-hero { margin: 1.4rem 0 1.1rem; max-width: 46rem; }
.af-hero h1 { font-size: 2.3rem; line-height: 1.15; font-weight: 750; color: #14243a; margin: 0 0 .55rem;
  padding: 0; letter-spacing: -0.02em; }
.af-hero p { font-size: 1.08rem; color: #46505e; margin: 0; line-height: 1.5; }
.af-steps { list-style: none; display: grid; grid-template-columns: repeat(3, 1fr); gap: .8rem;
  margin: 0 0 1.8rem !important; padding: 0 !important; }
.af-step { display: flex; gap: .7rem; align-items: flex-start; padding: .75rem .9rem; border-radius: .7rem;
  background: #f5f7fa; margin: 0 !important; }
.af-step-n { flex: 0 0 auto; width: 1.7rem; height: 1.7rem; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: .85rem; font-weight: 700;
  background: #1d4e89; color: #ffffff; }
.af-step-title { font-weight: 650; color: #1a2332; font-size: .95rem; }
.af-step-text { font-size: .84rem; color: #4f5a68; margin-top: .1rem; line-height: 1.4; }

/* Cartes des personas, côte à côte et de même hauteur : colonnes étirées, la carte prend
   la place libre et le bouton reste aligné en bas. */
[data-testid="stHorizontalBlock"]:has([class*="st-key-persona-"]) { align-items: stretch; }
[data-testid="stColumn"]:has([class*="st-key-persona-"]) > [data-testid="stVerticalBlock"] { height: 100%; }
[data-testid="stColumn"]:has([class*="st-key-persona-"]) [data-testid="stLayoutWrapper"] {
  flex: 1 1 auto; display: flex; flex-direction: column; }
[class*="st-key-persona-"] { gap: .6rem; flex: 1 1 auto; }
[class*="st-key-persona-"] [data-testid="stElementContainer"]:has(.af-pc) { flex: 1 1 auto; }
[class*="st-key-persona-"] [data-testid="stElementContainer"]:has(.af-pc) div:has(.af-pc) { height: 100%; }
.af-pc { box-sizing: border-box; height: 100%; display: flex; flex-direction: column; min-height: 17rem; padding: 1.15rem 1.2rem 1rem;
  border-radius: .9rem; background: #ffffff; border: 1px solid #dbe2ea;
  border-top: 4px solid var(--af-accent); box-shadow: 0 2px 8px rgba(20, 50, 92, .06);
  transition: box-shadow .18s ease, transform .18s ease; }
.af-pc:hover { box-shadow: 0 10px 24px rgba(20, 50, 92, .12); transform: translateY(-2px); }
.af-pc--on { border-color: var(--af-accent); }
.af-pc-head { display: flex; align-items: center; gap: .8rem; }
.af-pc-avatar { flex: 0 0 auto; width: 2.8rem; height: 2.8rem; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 1.3rem; font-weight: 700; color: #ffffff;
  background: var(--af-accent); }
.af-pc-name { font-size: 1.3rem; font-weight: 700; color: #1a2332; display: flex; align-items: center;
  gap: .45rem; flex-wrap: wrap; }
.af-pc-badge, .af-pc-selected { font-size: .7rem; font-weight: 600; padding: .08rem .5rem; border-radius: 999px; }
.af-pc-badge { background: #eef2f7; color: #4f5a68; border: 1px solid #dbe2ea; }
.af-pc-selected { background: var(--af-accent); color: #ffffff; }
.af-pc-sub { color: #4f5a68; font-size: .86rem; margin-top: .05rem; }
.af-pc-tests { margin: .95rem 0 .9rem; color: #1a2332; line-height: 1.45; font-size: .95rem; flex: 1 1 auto; }
.af-pc-tests span { display: block; font-size: .7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--af-accent); margin-bottom: .2rem; }
.af-pc-facts { margin: 0; border-top: 1px solid #e6ebf1; }
.af-pc-fact { display: flex; justify-content: space-between; gap: .8rem; padding: .42rem 0;
  border-bottom: 1px solid #eef2f6; font-size: .87rem; }
.af-pc-fact dt { color: #4f5a68; font-weight: 400; }
.af-pc-fact dd { margin: 0; color: #1a2332; font-weight: 600; text-align: right; }
@media (prefers-reduced-motion: reduce) { .af-pc { transition: none; } .af-pc:hover { transform: none; } }
@media (max-width: 900px) { .af-steps { grid-template-columns: 1fr; } .af-pc { min-height: 0; } }
[class*="st-key-home-foot"] { margin-top: 1.2rem; padding-top: .9rem; border-top: 1px solid #e6ebf1; }
@media (max-width: 640px) {
  .af-progress { overflow-x: auto; }
  .af-progress-line { min-width: .5rem; }
}
[class*="st-key-card-"] [data-testid="stPopover"] button p { font-size: 1.35rem; font-weight: 650; }
/* Points clés de la réponse : le chiffre est l'information principale. */
[class*="st-key-keypoints-"] [data-testid="stPopover"] button p { font-size: 1.2rem; font-weight: 650; }

[class*="st-key-next-step"] a { background: #1d4e89; border-radius: .5rem; padding: .35rem .9rem; }
[class*="st-key-next-step"] a p, [class*="st-key-next-step"] a span { color: #ffffff !important; }


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
