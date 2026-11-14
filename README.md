# AlphaForge 01

Projet de l'équipe pour le datathon PolyFinances AlphaForge AI 2026. Matériel de simulation uniquement, aucun conseil en placement.

## Structure

```
data/
  raw/          Données de départ fournies par les organisateurs (ne pas modifier à la main)
  external/     Données ajoutées par l'équipe (source, date et traitement documentés)
  processed/    Données nettoyées ou alignées, générées par le code (non versionnées)
app/            Interface Streamlit (flux D), texte en français
src/alphaforge/ Code réutilisable (chargement, alignement, stratégies, métriques)
scripts/        Scripts exécutables en ligne de commande
notebooks/      Exploration et analyses
outputs/
  figures/      Graphiques générés
  reports/      Tableaux et rapports générés
docs/           Documentation du projet et méthodologie
tests/          Tests
```

La documentation du jeu de données de départ est dans [data/raw/README.md](data/raw/README.md).

## Installation

```bash
python -m venv .venv
.venv/Scripts/pip install pandas yfinance      # .venv/bin/... sous macOS/Linux
```

Toutes les commandes se lancent depuis la racine du projet.

## Lancer l'interface

```bash
.venv/bin/pip install -r requirements.txt      # .venv/Scripts/pip sous Windows
.venv/bin/streamlit run app/streamlit_app.py
```

La configuration `.streamlit/config.toml` limite l'écoute à 127.0.0.1 et masque les traces Python.

Variable optionnelle `ALPHAFORGE_MODE` : `fixture` (données d'essai, par défaut), `offline` ou `bedrock`.
