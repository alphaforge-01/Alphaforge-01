"""Textes de l'interface AlphaForge, en français.

Tout texte destiné à l'utilisateur vit ici. Le code reste en anglais.
Ponctuation ASCII seulement (règle 1 de CLAUDE.md) : pas de guillemets
typographiques, pas de tiret cadratin, pas d'emoji.
"""

PAGE_TITLE = "AlphaForge"
APP_TITLE = "AlphaForge : copilote de cohérence"
APP_SUBTITLE = (
    "Votre portefeuille fictif correspond-il à votre profil, "
    "et que change votre idée de placement ?"
)

DISCLAIMER = (
    "Simulation à but éducatif, pas un conseil financier personnalisé. "
    "Profils, portefeuilles et montants sont fictifs."
)
FIXTURE_BANNER = (
    "Données d'essai : les chiffres affichés sont inventés et ne décrivent aucun marché."
)

TAB_ANALYSIS = "Analyse"
TAB_GUARDRAIL = "Test du garde-fou"
TAB_SOURCES = "Sources et méthode"

SECTION_PROFILE = "1. Profil"
SECTION_XRAY = "2. Radiographie du portefeuille"
SECTION_IDEA = "3. Idée de placement"
SECTION_RESULT = "4. Résultat"
SECTION_EXPLANATION = "5. Explication"
SECTION_TRACE = "Trace des étapes"

COMING_SOON = "À venir ({task})."

SIDEBAR_TITLE = "Session"
SIDEBAR_MODE_LABEL = "Source des données"
SIDEBAR_ACTIVE_PROFILE = "Profil actif"
SIDEBAR_NO_PROFILE = "Aucun profil choisi."
SIDEBAR_LEVEL = "Niveau d'explication"

MODE_LABELS = {
    "fixture": "Données d'essai",
    "offline": "Hors ligne (sans Bedrock)",
    "bedrock": "Amazon Bedrock",
}

STATUS_LABELS = {
    "compliant": "Conforme",
    "tension": "Tension",
    "conflict": "Conflit",
    "missing_info": "Information manquante",
}
# Couleurs nommées de Streamlit. Le libellé accompagne toujours la couleur.
STATUS_COLORS = {
    "compliant": "green",
    "tension": "orange",
    "conflict": "red",
    "missing_info": "gray",
}

RISK_LABELS = {
    "low": "Faible",
    "low_moderate": "Faible à modérée",
    "moderate": "Modérée",
    "high": "Élevée",
}
EXPERIENCE_LABELS = {
    "beginner": "Débutant",
    "intermediate": "Intermédiaire",
    "advanced": "Avancé",
}
ESG_LABELS = {
    "none": "Aucune",
    "moderate": "Modérée",
    "strong": "Forte",
}
LEVEL_LABELS = {
    "novice": "Novice",
    "pro": "Pro",
}

FICTIONAL_BADGE = "Profil fictif"
PERSONA_AGE = "{age} ans"
PERSONA_RISK = "Tolérance au risque"
PERSONA_HORIZON = "Horizon"
PERSONA_OBJECTIVE = "Objectif"
PERSONA_EXPERIENCE = "Expérience"
PERSONA_CAPITAL = "Capital fictif"
CHOOSE_PROFILE = "Choisir ce profil"
SELECTED_PROFILE = "Profil choisi"
NO_PROFILE_SELECTED = "Choisissez un profil fictif pour commencer."

ANALYSIS_LOADED = "Analyse chargée : {run_id}, données au {as_of}."

MSG_PROFILES_NOT_READY = (
    "Les profils ne sont pas encore disponibles dans ce mode "
    "(module profiles.py du flux B non fusionné). Utilisez le mode Données d'essai."
)
MSG_PIPELINE_NOT_READY = (
    "Le pipeline d'analyse n'est pas encore disponible dans ce mode "
    "(module analysis_pipeline.py du flux C non fusionné). Utilisez le mode Données d'essai."
)
MSG_FIXTURE_PROFILE_MISSING = (
    "Aucune donnée d'essai pour ce profil. En mode Données d'essai, seuls les profils "
    "ayant une fixture d'analyse sont disponibles."
)
MSG_FIXTURE_IDEA_ONLY = (
    "En mode Données d'essai, seule l'idée \"25 % dans TSLA\", financée au prorata, est disponible."
)
MSG_UNEXPECTED_ERROR = (
    "Une erreur est survenue pendant le chargement ({error_type}). "
    "La page reste utilisable : changez de mode ou réessayez."
)
