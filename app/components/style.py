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
[data-testid="stMainBlockContainer"] { padding-top: 5.2rem !important; padding-bottom: 1.5rem !important; max-width: 1320px; }
[data-testid="stMain"] { padding-bottom: 0 !important; }
[data-testid="stBottomBlockContainer"]:empty, [data-testid="stBottom"]:empty { display: none; }

/* Barre de navigation du haut : marque à gauche, liens texte à droite, soulignement discret. */
/* Barre collante : elle reste en haut au défilement. L'en-tête natif de Streamlit est masqué
   (plus de barre latérale à ouvrir), la barre prend sa place, fond légèrement translucide. */
[data-testid="stHeader"] { display: none; }
/* Position fixe (le collage "sticky" ne tient pas dans la mise en page de Streamlit) : la barre
   couvre toute la largeur, son contenu reste aligné sur la colonne de 1320 px ; le contenu
   de la page commence sous elle (padding-top du conteneur principal). */
.st-key-af-topnav { position: fixed !important; top: 0; left: 0; right: 0; width: 100% !important;
  z-index: 999990; box-sizing: border-box; gap: .5rem;
  padding: .8rem max(1.5rem, calc((100vw - 1320px) / 2 + 1rem)) .8rem;
  border-bottom: 1px solid #e6ebf1; background: rgba(255, 255, 255, .88);
  -webkit-backdrop-filter: saturate(180%) blur(12px); backdrop-filter: saturate(180%) blur(12px); }
.st-key-af-topnav .af-brand { font-size: 1.3rem; }
.st-key-af-topnav [data-testid="stPageLink"] a { padding: .4rem .95rem; border-radius: 999px;
  transition: background .15s ease; }
.st-key-af-topnav [data-testid="stPageLink"] a span { color: #1a2332; font-size: 1.02rem; font-weight: 500; }
.st-key-af-topnav [data-testid="stPageLink"] a:hover { background: #eef2f7; }
.st-key-af-topnav [data-testid="stPageLink"] a[aria-current="page"],
.st-key-af-topnav [data-testid="stPageLink"] a[class*="active" i] { background: #e3edf9; }
.st-key-af-topnav [data-testid="stPageLink"] a[aria-current="page"] span,
.st-key-af-topnav [data-testid="stPageLink"] a[class*="active" i] span { color: #14325c; font-weight: 650; }
.af-nav-here { display: inline-block; padding: .4rem .95rem; border-radius: 999px; background: #e3edf9;
  color: #14325c; font-size: 1.02rem; font-weight: 650; cursor: default; white-space: nowrap; }
/* Créer un profil fictif : action à contour, séparée des pages du parcours par un filet. */
.st-key-af-nav-action { margin-left: .5rem; padding-left: 1rem; border-left: 1px solid #e1e7ee; }
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a { border: 1.5px solid #1d4e89;
  padding: .32rem .95rem .32rem .75rem; }
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a span { color: #1d4e89; font-weight: 600; }
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a:hover { background: #1d4e89; }
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a:hover span { color: #ffffff; }
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a[aria-current="page"],
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a[class*="active" i] { background: #1d4e89; }
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a[aria-current="page"] span,
.st-key-af-topnav .st-key-af-nav-action [data-testid="stPageLink"] a[class*="active" i] span { color: #ffffff; }
/* Créer un profil fictif : une colonne étroite et centrée, étapes séparées par des filets,
   récapitulatif en carte à la fin. */
.st-key-custom-wrap { max-width: 720px; width: 100%; margin: 1.2rem auto 0; }
.st-key-custom-wrap h2 { text-align: center; }
.st-key-custom-wrap .af-intro { text-align: center; margin-bottom: 1rem; }
[class*="st-key-custom-step-"] { padding: 1.4rem 0 1.5rem; border-top: 1px solid #e6ebf1; gap: 1rem; }
/* Contenu de chaque étape centré : titres, libellés, boutons et interrupteurs ; les curseurs, champs
   et la grille d'objectif gardent toute la largeur. */
[class*="st-key-custom-step-"] { align-items: center; text-align: center; }
[class*="st-key-custom-step-"] .af-form-step { justify-content: center; }
[class*="st-key-custom-step-"] [data-testid="stWidgetLabel"] { justify-content: center; width: 100%; }
[class*="st-key-custom-step-"] [data-testid="stWidgetLabel"] > div { margin-left: auto; margin-right: auto; }
[class*="st-key-custom-step-"] > div:has([data-testid="stSlider"]),
[class*="st-key-custom-step-"] > div:has([data-testid="stHorizontalBlock"]),
[class*="st-key-custom-step-"] > [data-testid="stHorizontalBlock"],
[class*="st-key-custom-step-"] > .st-key-custom_objective { align-self: stretch; width: 100%; }
[class*="st-key-custom-step-"] [data-testid="stHorizontalBlock"] { text-align: left; }
.af-form-step { display: flex; align-items: center; gap: .6rem; font-size: 1.05rem; font-weight: 650;
  color: #14243a; }
.af-form-step .af-step-n { width: 1.5rem; height: 1.5rem; font-size: .8rem; }
.st-key-custom-preview { margin-top: .6rem; padding: 1.4rem 1.5rem; border-radius: .9rem;
  background: #ffffff; border: 1px solid #dbe2ea; border-top: 4px solid #0f6b78; gap: .9rem;
  box-shadow: 0 10px 28px rgba(20, 50, 92, .08); }
/* Tolérance au risque : couleur du curseur selon le niveau (rond, partie remplie, libellé). */
/* e13xtgje3 (rond) et e13xtgje5 (barre remplie) : classes du curseur de Streamlit 1.67, à revoir si la version change. */
.st-key-custom-risk-low [role="slider"], .st-key-custom-risk-low [data-testid="stSlider"] [class*="e13xtgje3"] { background-color: #2e8b57 !important; box-shadow: 0 0 0 4px #2e8b5733 !important; }
.st-key-custom-risk-low [data-testid="stSliderThumbValue"] { color: #2e8b57 !important; font-weight: 650; }
.st-key-custom-risk-low [data-testid="stSlider"] [class*="e13xtgje5"] { background: linear-gradient(to right, #2e8b57 0%, #2e8b57 0%, #e3e9f1 0%, #e3e9f1 100%) !important; }
.st-key-custom-risk-low_moderate [role="slider"], .st-key-custom-risk-low_moderate [data-testid="stSlider"] [class*="e13xtgje3"] { background-color: #7a9a1e !important; box-shadow: 0 0 0 4px #7a9a1e33 !important; }
.st-key-custom-risk-low_moderate [data-testid="stSliderThumbValue"] { color: #7a9a1e !important; font-weight: 650; }
.st-key-custom-risk-low_moderate [data-testid="stSlider"] [class*="e13xtgje5"] { background: linear-gradient(to right, #7a9a1e 0%, #7a9a1e 33.33%, #e3e9f1 33.33%, #e3e9f1 100%) !important; }
.st-key-custom-risk-moderate [role="slider"], .st-key-custom-risk-moderate [data-testid="stSlider"] [class*="e13xtgje3"] { background-color: #c98500 !important; box-shadow: 0 0 0 4px #c9850033 !important; }
.st-key-custom-risk-moderate [data-testid="stSliderThumbValue"] { color: #c98500 !important; font-weight: 650; }
.st-key-custom-risk-moderate [data-testid="stSlider"] [class*="e13xtgje5"] { background: linear-gradient(to right, #c98500 0%, #c98500 66.67%, #e3e9f1 66.67%, #e3e9f1 100%) !important; }
.st-key-custom-risk-high [role="slider"], .st-key-custom-risk-high [data-testid="stSlider"] [class*="e13xtgje3"] { background-color: #c8442f !important; box-shadow: 0 0 0 4px #c8442f33 !important; }
.st-key-custom-risk-high [data-testid="stSliderThumbValue"] { color: #c8442f !important; font-weight: 650; }
.st-key-custom-risk-high [data-testid="stSlider"] [class*="e13xtgje5"] { background: linear-gradient(to right, #c8442f 0%, #c8442f 100%, #e3e9f1 100%, #e3e9f1 100%) !important; }
/* Objectif : quatre choix en grille 2 x 2 de même largeur, boutons séparés et arrondis. */
.st-key-custom_objective div:has(> button) { display: grid !important; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .55rem; width: 100%; }
.st-key-custom_objective div:has(> button) > button { width: 100%; margin: 0 !important; border-radius: .7rem !important;
  padding: .7rem .9rem; justify-content: flex-start; text-align: left; border: 1px solid #dbe2ea !important; }
.st-key-custom_objective div:has(> button) > button[kind*="Active"] { border-color: #1d4e89 !important;
  box-shadow: inset 0 0 0 1px #1d4e89; }
@media (max-width: 640px) { .st-key-custom_objective div:has(> button) { grid-template-columns: 1fr; } }
/* Règles produites : bouton en pastille, centré ; une fois ouvert, le tableau reprend toute la largeur. */
.st-key-custom-preview [data-testid="stElementContainer"]:has([data-testid="stExpander"]),
.st-key-custom-preview [data-testid="stExpander"] { width: fit-content !important; align-self: center; margin: 0 auto; }
.st-key-custom-preview [data-testid="stElementContainer"]:has(details[open]),
.st-key-custom-preview [data-testid="stExpander"]:has(details[open]) { width: 100% !important; }
.st-key-custom-preview [data-testid="stExpander"] details { border: none; background: transparent; }
.st-key-custom-preview [data-testid="stExpander"] summary { display: flex; justify-content: center; gap: .45rem;
  width: fit-content; margin: 0 auto; padding: .45rem 1.1rem; border-radius: 999px; font-size: .9rem;
  font-weight: 600; color: #1d4e89; background: #f1f6fc; border: 1px solid #c9d8ea; cursor: pointer;
  transition: background .15s ease, border-color .15s ease; }
.st-key-custom-preview [data-testid="stExpander"] summary:hover { background: #e3edf9; border-color: #1d4e89; }
.st-key-custom-preview [data-testid="stExpander"] summary:focus-visible { outline: 2px solid #1d4e89; outline-offset: 2px; }
.st-key-custom-preview [data-testid="stExpander"] summary span { flex: 0 0 auto; }
.st-key-custom-preview [data-testid="stCaptionContainer"] { text-align: center; }
/* Récapitulatif du profil construit : en-tête centré, grille 3 x 2 des réponses. */
.af-recap-kicker { text-align: center; font-size: .7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: var(--af-accent); margin-bottom: .9rem; }
.af-recap-head { display: flex; flex-direction: column; align-items: center; gap: .35rem; margin-bottom: 1.2rem; }
.af-recap-head .af-pc-avatar { background: var(--af-accent); }
.af-recap-head .af-pc-name { justify-content: center; }
.af-recap-sub { color: #4f5a68; font-size: .95rem; }
.af-recap-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .55rem; margin: 0; }
.af-recap-grid > div { padding: .65rem .8rem; border-radius: .65rem; background: #f6f8fb; text-align: center; }
.af-recap-grid dt { font-size: .7rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  color: #6b7684; margin-bottom: .15rem; }
.af-recap-grid dd { margin: 0; font-size: .98rem; font-weight: 650; color: #1a2332; }
@media (max-width: 640px) { .af-recap-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.af-recap-note { display: flex; gap: .5rem; align-items: flex-start; justify-content: center; text-align: left;
  font-size: .85rem; color: #4f5a68; line-height: 1.45; margin: .35rem auto 0; max-width: 34rem; }
.af-recap-note span { flex: 0 0 auto; width: 1.1rem; height: 1.1rem; border-radius: 50%; margin-top: .1rem;
  display: inline-flex; align-items: center; justify-content: center; font-size: .7rem; font-weight: 700;
  font-style: italic; font-family: Georgia, serif; color: #0f6b78; border: 1px solid #0f6b78; }
/* Simulation : colonne centrée, bande du profil, contexte en onglets, conversation en bulles. */
.st-key-sim-wrap { max-width: 880px; width: 100%; margin: .8rem auto 0; }
.st-key-sim-head { padding: .4rem 0 .2rem; }
.af-sim-head { display: flex; align-items: center; gap: 1rem; }
.af-sim-head .af-pc-avatar { width: 3.4rem; height: 3.4rem; font-size: 1.5rem; background: var(--af-accent); }
.af-sim-head h1 { font-size: 1.75rem; line-height: 1.2; font-weight: 750; color: #14243a; margin: 0; padding: 0; }
.af-sim-sub { color: #5b6675; font-size: .98rem; margin: .15rem 0 .45rem; }
.af-sim-head .af-pc-facts { display: flex; flex-wrap: wrap; gap: .4rem; }
.st-key-sim-context { padding: .4rem 1.2rem 1rem; border-radius: 1rem; background: #ffffff;
  border: 1px solid #e3e9f1; box-shadow: 0 6px 20px rgba(20, 50, 92, .05); }
.st-key-sim-context .st-key-portfolio-chart { border: none !important; padding: 0 !important; box-shadow: none; }
.st-key-sim-context [data-baseweb="tab-list"] { gap: .4rem; }
.st-key-sim-context [data-baseweb="tab"] p { font-size: .95rem; font-weight: 600; }
.af-sim-section { margin: 1.6rem 0 .2rem; font-size: .72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: #6b7684; display: flex; align-items: center; gap: .8rem; }
.af-sim-section::after { content: ""; flex: 1; height: 1px; background: #e6ebf1; }
.st-key-sim-wrap [data-testid="stChatMessage"] { background: #ffffff; border: 1px solid #e6ebf1;
  border-radius: 1rem; padding: .9rem 1.1rem; box-shadow: 0 2px 8px rgba(20, 50, 92, .04); }
[class*="st-key-chat-user-"] { align-items: flex-end; scroll-margin-top: 6rem; }  /* sous la barre fixe */
[class*="st-key-chat-user-"] [data-testid="stChatMessage"] { flex-direction: row-reverse; width: fit-content;
  max-width: 80%; margin-left: auto; background: #e8f0fb; border-color: #d3e1f3; border-radius: 1rem 1rem .3rem 1rem;
  padding: .6rem 1rem; box-shadow: none; }
[class*="st-key-chat-user-"] [data-testid="stChatMessage"] p { color: #14325c; }
[data-testid="stBottomBlockContainer"] { max-width: 880px; padding-top: .8rem; padding-bottom: 1.2rem; }
[data-testid="stBottom"] > div { background: linear-gradient(180deg, rgba(255,255,255,0), #ffffff 35%); }
[data-testid="stChatInput"] { border-radius: 1.4rem !important; border: 1px solid #d3dce8 !important;
  box-shadow: 0 8px 24px rgba(20, 50, 92, .08); background: #ffffff; }
[data-testid="stChatInput"]:focus-within { border-color: #1d4e89 !important; }
.af-progress { border: none; background: transparent; padding: .2rem 0; margin: .4rem 0 1rem; }
/* Explication complète : carte structurée, intertitres, résumé mis en avant, raisons en blocs doux. */
.st-key-af-expl-card { padding: 1.3rem 1.5rem 1.2rem; border-radius: 1rem; background: #ffffff;
  border: 1px solid #e3e9f1; gap: .7rem; }
.af-expl-h { margin: 1rem 0 .1rem; font-size: .72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: #1d4e89; display: flex; align-items: center; gap: .6rem; }
.af-expl-h::after { content: ""; flex: 1; height: 1px; background: #e6ebf1; }
.st-key-af-expl-card > div:first-child .af-expl-h { margin-top: 0; }
.st-key-af-expl-summary { padding: .9rem 1.1rem; border-radius: .8rem; background: #f3f7fc;
  border-left: 4px solid #1d4e89; }
.st-key-af-expl-summary p { font-size: 1.04rem; line-height: 1.6; color: #14243a; margin: 0; }
[class*="st-key-af-expl-factor-"] { padding: .8rem 1rem; border-radius: .8rem; background: #f7f9fb;
  border: 1px solid #edf1f5; gap: .4rem; }
[class*="st-key-af-expl-factor-"] p { line-height: 1.55; }
.st-key-af-expl-warnings { padding: .7rem 1rem; border-radius: .8rem; background: #fffaf1;
  border: 1px solid #f1dcb4; gap: .2rem; }
.st-key-af-expl-warnings p, .st-key-af-expl-warnings li { font-size: .88rem; color: #6b4a12; }
.st-key-af-expl-limits li, .st-key-af-expl-limits p { font-size: .88rem; color: #4f5a68; line-height: 1.5; }
.st-key-af-expl-card [data-testid="stExpander"] details { border-radius: .7rem; border-color: #e6ebf1; }
/* Contexte actif dans la barre du haut : une pastille grise groupée, séparateurs fins,
   distincte des liens (pas de survol) et du bouton d'action. */
.st-key-af-nav-context { margin-left: 1rem; width: auto !important; }
.st-key-af-nav-context .af-header { margin: 0; justify-content: flex-start; }
.st-key-af-nav-context .af-chips { gap: 0; flex-wrap: nowrap; padding: .15rem .25rem; border-radius: 999px;
  background: #f5f7fa; border: 1px solid #e3e8ef; }
.st-key-af-nav-context .af-chip { background: none; border: none; border-radius: 0; font-size: .76rem;
  color: #6b7684; padding: .12rem .65rem; max-width: 15rem; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.st-key-af-nav-context .af-chip + .af-chip { border-left: 1px solid #e1e7ee; }
.st-key-af-nav-context .af-chip b { color: #1a2332; font-weight: 600; }
@media (max-width: 1100px) { .st-key-af-nav-context { display: none; } }
/* Écran large : la pastille est centrée dans la barre (la barre fixe sert de repère). En dessous,
   elle reste à côté de la marque pour ne pas chevaucher les liens. */
@media (min-width: 1380px) { .st-key-af-nav-context { position: absolute !important; left: 50%;
  top: 50%; transform: translate(-50%, -50%); margin: 0; } }
/* Barre d'outils des graphiques (tableau, téléchargement, plein écran) : en bas à droite du
   graphique, pour ne plus couvrir le sélecteur Barres / Composition. La vue tableau reste
   accessible (compense le contraste faible de certaines couleurs). */
.st-key-portfolio-chart [data-testid="stElementToolbar"] { top: auto !important; bottom: -.4rem !important;
  right: 0 !important; }
/* Icône de paramètres seule : le libellé reste pour les lecteurs d'écran et l'info-bulle. */
.st-key-af-settings button p { position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0); white-space: nowrap; }
.st-key-af-settings button { margin-left: .4rem; }
h1, h2, h3 { letter-spacing: -0.01em; }

.af-header { display: flex; justify-content: flex-end; align-items: center; margin-top: .5rem;
  flex-wrap: wrap; gap: .5rem; }
.af-brand { font-weight: 700; font-size: 1.1rem; color: #14325c; }
.af-brand span { font-weight: 400; font-size: .9rem; color: #5b6675; margin-left: .45rem; }
.af-chips { display: flex; flex-wrap: wrap; gap: .35rem; }
.af-chip { font-size: .78rem; padding: .12rem .6rem; border-radius: 999px;
  background: #eef2f7; border: 1px solid #dbe2ea; color: #1a2332; }
.af-chip b { font-weight: 600; }
/* Avertissement : une puce centrée, même taille, point d'accent et fond translucide. */
.af-disclaimer { display: flex; justify-content: center; width: 100%; margin: .4rem 0 .2rem; }
.af-disclaimer span { display: inline-flex; align-items: center; gap: .45rem; font-size: .75rem;
  padding: .14rem .75rem .14rem .6rem; border-radius: 999px; letter-spacing: .02em; color: #7a4a0c; font-weight: 600;
  background: linear-gradient(180deg, #fffaf1, #fdf1dc); border: 1px solid #efd3a3;
  box-shadow: 0 1px 2px rgba(122, 74, 12, .08); cursor: help; }
.af-disclaimer span::before { content: ""; width: .42rem; height: .42rem; border-radius: 50%;
  background: #d08a1c; box-shadow: 0 0 0 3px rgba(208, 138, 28, .16); }
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

/* Accueil : titre-promesse sur une ligne, trois étapes discrètes. */
.af-hero { margin: 1.2rem 0 1.4rem; }
.af-hero h1 { font-size: 2.7rem; line-height: 1.15; font-weight: 750; color: #14243a; margin: 0 0 .8rem;
  padding: 0; letter-spacing: -0.02em; }
.af-hero p { font-size: 1.2rem; color: #5b6675; margin: 0; line-height: 1.5; }
.af-steps { list-style: none; display: flex; flex-wrap: wrap; gap: .4rem 1.6rem;
  margin: 0 0 1.4rem !important; padding: 0 !important; }
.af-step { display: flex; gap: .45rem; align-items: center; margin: 0 !important; padding: 0 !important;
  font-size: .95rem; color: #4f5a68; }
.af-step-n { flex: 0 0 auto; width: 1.2rem; height: 1.2rem; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: .72rem; font-weight: 700;
  background: #e8f0fb; color: #1d4e89; }

/* Cartes des personas : le conteneur à clé est la carte (bouton compris), même hauteur. */
[data-testid="stHorizontalBlock"]:has([class*="st-key-persona-"]) { align-items: stretch; }
[data-testid="stColumn"]:has([class*="st-key-persona-"]) > [data-testid="stVerticalBlock"] { height: 100%; }
[data-testid="stColumn"]:has([class*="st-key-persona-"]) [data-testid="stLayoutWrapper"] {
  flex: 1 1 auto; display: flex; flex-direction: column; }
[class*="st-key-persona-"] { gap: .8rem; flex: 1 1 auto; box-sizing: border-box; padding: 1.7rem 1.8rem 1.7rem;
  border-radius: .9rem; background: #ffffff; border: 1px solid #dbe2ea; border-top: 4px solid #5b6675;
  box-shadow: 0 2px 8px rgba(20, 50, 92, .06); transition: box-shadow .18s ease, transform .18s ease; }
.st-key-persona-robert { border-top-color: #1d4e89 !important; }
.st-key-persona-amira { border-top-color: #6a3fb0 !important; }
.st-key-persona-mateo { border-top-color: #2a6f46 !important; }
[class*="st-key-persona-"]:hover { box-shadow: 0 10px 24px rgba(20, 50, 92, .12); transform: translateY(-2px); }
[class*="st-key-persona-"] [data-testid="stElementContainer"]:has(.af-pc) { flex: 0 0 auto; height: auto !important; }
.af-pc { position: relative; display: flex; flex-direction: column; gap: 1.1rem; padding-bottom: 1.4rem; }
/* Objectif du profil : bloc flottant au-dessus de la carte, fondu et léger glissement au survol. */
.af-pc-more { position: absolute; left: -.4rem; right: -.4rem; bottom: calc(100% + 2.3rem); z-index: 20;
  padding: .85rem 1.05rem; border-radius: .8rem; background: rgba(255, 255, 255, .97);
  border: 1px solid #dbe2ea; border-left: 4px solid var(--af-accent);
  box-shadow: 0 14px 34px rgba(20, 50, 92, .16); color: #1a2332; font-size: .92rem; line-height: 1.5;
  opacity: 0; visibility: hidden; transform: translateY(6px); pointer-events: none;
  transition: opacity .22s ease, transform .22s ease, visibility 0s linear .22s; }
.af-pc-more span { display: block; font-size: .68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--af-accent); margin-bottom: .2rem; }
.af-pc-more::after { content: ""; position: absolute; left: 1.6rem; top: 100%; width: .7rem; height: .7rem;
  background: inherit; border-right: 1px solid #dbe2ea; border-bottom: 1px solid #dbe2ea;
  transform: translateY(-50%) rotate(45deg); }
/* La carte survolée passe au premier plan : son bloc flottant couvre le bandeau d'aisance. */
[class*="st-key-persona-"] { position: relative; z-index: 1; }
[class*="st-key-persona-"]:hover, [class*="st-key-persona-"]:focus-within { z-index: 100; }
[class*="st-key-persona-"]:hover .af-pc-more, [class*="st-key-persona-"]:focus-within .af-pc-more {
  opacity: 1; visibility: visible; transform: translateY(0); transition-delay: .12s, .12s, 0s; }
.af-pc-head { display: flex; align-items: center; gap: .7rem; }
.af-pc-avatar { flex: 0 0 auto; width: 2.8rem; height: 2.8rem; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 1.1rem; font-weight: 700; color: #ffffff;
  background: var(--af-accent); }
.af-pc-name { font-size: 1.3rem; font-weight: 700; color: #1a2332; display: flex; align-items: center;
  gap: .45rem; flex-wrap: wrap; }
.af-pc-badge, .af-pc-selected { font-size: .68rem; font-weight: 600; padding: .05rem .45rem; border-radius: 999px; }
.af-pc-badge { background: #eef2f7; color: #4f5a68; border: 1px solid #dbe2ea; }
.af-pc-selected { background: var(--af-accent); color: #ffffff; }
.af-pc-sub { color: #4f5a68; font-size: .84rem; }
.af-pc-tests { color: #1a2332; line-height: 1.55; font-size: 1.02rem; min-height: 4.65em; }
.af-pc-tests span { display: block; font-size: .68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--af-accent); margin-bottom: .15rem; }
.af-pc-facts { display: flex; flex-wrap: wrap; gap: .4rem; }
.af-pc-tag { font-size: .78rem; padding: .1rem .55rem; border-radius: 999px; background: #f3f6fa;
  border: 1px solid #e1e7ee; color: #4f5a68; }
.af-pc-tag b { color: #1a2332; font-weight: 600; }
@media (prefers-reduced-motion: reduce) { [class*="st-key-persona-"] { transition: none; } [class*="st-key-persona-"]:hover { transform: none; } .af-pc-more { transition: none; transform: none; } }

[class*="st-key-home-foot"] { margin-top: .6rem; }
/* Question d'aisance : bandeau léger entre les étapes et les cartes. */
.st-key-home-level-row { position: relative; z-index: 0; margin: 0 0 1.6rem; padding: .9rem 1.2rem; border-radius: .9rem;
  background: #f5f8fc; border: 1px solid #e3e9f1; }
.st-key-home-level-row [data-testid="stWidgetLabel"] p { font-size: 1.05rem; font-weight: 650; color: #14243a; }
.st-key-home-level-row [data-testid="stCaptionContainer"] { padding-bottom: .45rem; }
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
