"""Textes de l'interface v2 (cartes, verdicts, graphiques).

Ces libellés sont séparés de `ui_texts.py` pour ne pas toucher au fichier que d'autres
membres de l'équipe modifient. Le français est celui du reste de l'interface. Aucun
chiffre ne figure ici : les valeurs viennent toujours du registre de preuves.
"""
from __future__ import annotations

from typing import Dict, Tuple

# --- Mesures de tête : (métrique du registre, libellé court) --------------------
HEADLINE_METRICS: Tuple[Tuple[str, str], ...] = (
    ("volatility_ann", "Volatilité annualisée"),
    ("max_drawdown", "Perte maximale historique"),
    ("top_asset_weight", "Poids du plus gros actif"),
    ("defensive_share", "Part défensive"),
)
METRIC_HELP: Dict[str, str] = {
    "volatility_ann": "Amplitude des variations de valeur sur l'historique, ramenée à une année.",
    "max_drawdown": "Plus forte baisse observée entre un sommet et le creux suivant, sur l'historique.",
    "top_asset_weight": "Part du portefeuille placée dans le titre le plus important.",
    "defensive_share": "Part du portefeuille classée défensive dans les données du projet.",
}

# --- Pastilles du contexte du profil ---------------------------------------------
PROFILE_CHIP_LABELS: Tuple[Tuple[str, str], ...] = (
    ("risk_tolerance_fr", "Tolérance au risque"),
    ("experience_fr", "Expérience"),
    ("esg_preference_fr", "Préférence ESG"),
)
CHIP_HORIZON = "Horizon"
CHIP_CAPITAL = "Capital fictif"
CHIP_CRYPTO = "Cryptoactifs"
CRYPTO_ALLOWED = "autorisés"
CRYPTO_EXCLUDED = "exclus"

# --- Cartes de mesures -------------------------------------------------------------
NOT_AVAILABLE = "Non disponible"
CARD_BEFORE_LINE = "Avant : {value}"
CARD_AFTER_LINE = "Après : {value}"
CARD_DELTA_HELP = "Écart entre le portefeuille après l'idée et le portefeuille avant."
CARD_DELTA_UNAVAILABLE = "Écart : non disponible"
CARDS_CAPTION = "Mesures calculées sur l'historique des données du projet. Elles ne sont pas des prévisions."

# --- Verdicts --------------------------------------------------------------------
VERDICT_OVERALL = "Verdict global"
VERDICT_FINANCIAL = "Verdict financier"
VERDICT_ESG = "Verdict ESG"
VERDICT_OVERALL_HELP = "Le plus sévère des statuts de toutes les règles du profil."
VERDICT_FINANCIAL_HELP = "Règles de risque et de concentration du profil."
VERDICT_ESG_HELP = "Règles d'exclusion liées aux préférences ESG du profil."
VERDICT_ESG_NONE = "Aucune règle ESG pour ce profil."
VERDICT_UNAVAILABLE = "Non disponible"

# --- États visuels : icône Material et phrase d'aide par statut ---------------------
STATUS_ICONS: Dict[str, str] = {
    "compliant": ":material/check_circle:",
    "tension": ":material/warning:",
    "conflict": ":material/error:",
    "missing_info": ":material/help:",
}
STATUS_HELP: Dict[str, str] = {
    "compliant": "Respecte les règles du profil.",
    "tension": "Dépasse le seuil d'avertissement du profil, sans atteindre la limite.",
    "conflict": "Dépasse la limite du profil.",
    "missing_info": "Il manque des données pour évaluer cette règle.",
}

# --- Graphiques --------------------------------------------------------------------
SERIES_BEFORE = "Avant l'idée"
SERIES_AFTER = "Après l'idée"
SERIES_LEGEND_TITLE = "Portefeuille"
TOOLTIP_TICKER = "Titre"
TOOLTIP_NAME = "Nom"
TOOLTIP_VALUE = "Valeur"
TOOLTIP_SERIES = "Portefeuille"

WEIGHTS_TITLE = "Composition du portefeuille avant et après l'idée"
WEIGHTS_CAPTION = "Poids de chaque titre, en pourcentage du portefeuille fictif."
WEIGHTS_MISSING = "Non disponible dans les données : {side} pour {tickers}."
WEIGHTS_MISSING_BEFORE = "poids avant"
WEIGHTS_MISSING_AFTER = "poids après"
WEIGHTS_EMPTY = "Composition non disponible pour ce résultat."

THRESHOLDS_TITLE = "Mesures comparées aux seuils du profil"
THRESHOLDS_CAPTION = (
    "La barre montre la mesure après l'idée. Les repères montrent le seuil d'avertissement "
    "et la limite du profil. Ces seuils sont des hypothèses de l'équipe pour un profil fictif, "
    "pas des normes."
)
THRESHOLD_WARN = "Seuil d'avertissement"
THRESHOLD_LIMIT = "Limite"
THRESHOLD_LEGEND_TITLE = "Repère"
THRESHOLD_STATUS_LEGEND_TITLE = "Statut de la règle"
THRESHOLD_DIRECTION = {
    "max": "À ne pas dépasser",
    "min": "À ne pas descendre sous",
}
TOOLTIP_RULE = "Règle"
TOOLTIP_ROW = "Ligne"
TOOLTIP_DIRECTION = "Sens"
TOOLTIP_STATUS = "Statut"
THRESHOLDS_EMPTY = "Aucune mesure chiffrée à comparer aux seuils pour ce résultat."

VARIANTS_TITLE = "Idée initiale et variantes proposées"
VARIANTS_CAPTION = (
    "Chaque ligne est un portefeuille simulé. Les statuts viennent des règles du profil. "
    "Ces simulations s'appuient sur l'historique et ne prédisent rien."
)
VARIANTS_INITIAL = "Idée initiale"
VARIANT_ROW_LABEL = "{name} ({weight})"
VARIANT_ROW_WITH_STATUS = "{label}, {status}"
VARIANT_MEASURES_LEGEND_TITLE = "Mesure"
VARIANT_VOLATILITY = "Volatilité annualisée"
VARIANT_DRAWDOWN = "Perte maximale historique"
VARIANTS_MISSING = "Non disponible dans les données : {measure} pour {rows}."
VARIANTS_EMPTY = "Aucune variante à comparer pour ce résultat."
VARIANTS_NONE_PROPOSED = "Aucune variante n'a été proposée pour cette idée."

# --- Carte d'explication (PR-4) ------------------------------------------------------
EXPL_TITLE = "Explication de l'analyse"
EXPL_LEVEL_BADGE = {"novice": "Niveau novice", "pro": "Niveau pro"}
EXPL_LEVEL_HELP = "Seul le texte change entre les niveaux : les chiffres et les statuts restent identiques."
EXPL_SUMMARY_TITLE = "En résumé"
EXPL_PROFILE_TITLE = "Contexte déclaré du profil fictif"
EXPL_FACTORS_TITLE = "Ce qui pèse dans le verdict"
EXPL_COUNTERFACTUAL_TITLE = "Ce qui ferait changer le verdict"
EXPL_VARIANTS_TITLE = "Variantes simulées"
EXPL_CHECKS_TITLE = "Détail des contrôles"
EXPL_EVIDENCE_TITLE = "Preuves citées ({count})"
EXPL_GLOSSARY_TITLE = "Glossaire ({count})"
EXPL_LIMITS_TITLE = "Limites"
EXPL_WARNINGS_TITLE = "Avertissements"
EXPL_GLOSSARY_IMAGE = "Image : {text}."
EXPL_NOT_AVAILABLE = "Explication non disponible pour ce résultat."
EXPL_PLAIN_NOTE = "Présentation simplifiée : le dossier de l'explication n'est pas disponible."
EXPL_CHECK_COLUMNS = {
    "novice": ("Règle", "Statut", "Mesure", "Seuil d'attention", "Limite du profil"),
    "pro": ("Contrôle", "Règle", "Statut", "Valeur", "Seuil d'avertissement", "Limite", "Marge", "Preuves"),
}
EXPL_NO_EVIDENCE = "aucune"
