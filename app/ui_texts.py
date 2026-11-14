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

CUSTOM_EXPANDER = "Construire un profil fictif (cases et curseurs)"
CUSTOM_REMINDER = (
    "Profil fictif : aucune donnée personnelle n'est demandée ni conservée "
    "(ni nom, ni revenu, ni compte)."
)
CUSTOM_OBJECTIVE = "Objectif"
CUSTOM_HORIZON = "Horizon de placement (années)"
CUSTOM_RISK = "Tolérance au risque"
CUSTOM_EXPERIENCE = "Expérience"
CUSTOM_ESG = "Préférence ESG"
CUSTOM_CRYPTO = "Cryptoactifs permis"
CUSTOM_OWN_CAP = "Fixer mon propre plafond par titre"
CUSTOM_OWN_CAP_HELP = "Sans plafond choisi, l'hypothèse de l'équipe pour la tolérance au risque s'applique."
CUSTOM_CAP = "Plafond par titre (%)"
CUSTOM_CAPITAL = "Capital fictif (CAD)"
CUSTOM_CAPITAL_HELP = "Montant inventé, utilisé seulement pour exprimer les résultats en dollars."
CUSTOM_PORTFOLIO = "Portefeuille fictif de départ"
CUSTOM_RULES_TITLE = "Règles produites par vos réponses"
CUSTOM_RULES_NOTICE = (
    "Chaque seuil est une hypothèse de l'équipe, réglable, et non une norme ni un conseil."
)
CUSTOM_USE = "Utiliser ce profil fictif"
CUSTOM_UPDATE = "Mettre à jour le profil construit"
CUSTOM_ACTIVE = "Profil construit actif."
CUSTOM_DISPLAY_NAME = "Profil construit"

# Liste fermée : pas de texte libre dans le MVP (US-02). À remplacer par la
# liste du flux B si elle est fournie.
OBJECTIVE_OPTIONS = (
    "Préserver le capital",
    "Préserver le capital avec un peu de croissance",
    "Croissance équilibrée",
    "Croissance à long terme",
)

RULE_COLUMN = "Règle"
RULE_TENSION = "Tension"
RULE_CONFLICT = "Conflit"
RULE_THRESHOLD_STATUS = "Statut du seuil"
RULE_ASSUMPTION = "Hypothèse de l'équipe"
RULE_ABOVE = "au-delà de {value}"
RULE_BELOW = "en dessous de {value}"
RULE_EXCLUDED = "toute position"
RULE_NONE = "aucun"

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
MSG_PROFILE_BUILDER_NOT_READY = (
    "La construction de profil n'est pas disponible (module profiles.py du flux B absent)."
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
