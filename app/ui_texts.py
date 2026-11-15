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
NOT_AVAILABLE = "non disponible"

TAB_ANALYSIS = "Analyse"
TAB_GUARDRAIL = "Test du garde-fou"
TAB_SOURCES = "Sources et méthode"

SECTION_PROFILE = "1. Profil"
SECTION_XRAY = "2. Radiographie du portefeuille"
SECTION_IDEA = "3. Idée de placement"
SECTION_RESULT = "4. Résultat"
SECTION_EXPLANATION = "5. Explication"
SECTION_TRACE = "6. Trace des étapes"

# --- Barre latérale ---------------------------------------------------------
SIDEBAR_TITLE = "Session"
SIDEBAR_MODE_LABEL = "Source des données"
SIDEBAR_ACTIVE_PROFILE = "Profil actif"
SIDEBAR_NO_PROFILE = "Aucun profil choisi."
SIDEBAR_LEVEL = "Niveau d'explication"
SIDEBAR_BEDROCK = "Configuration Bedrock"
SIDEBAR_BEDROCK_MODELS = "Modèles configurés"
SIDEBAR_BEDROCK_GUARDRAIL = "Garde-fou configuré"
SIDEBAR_BEDROCK_TRACES = "Compartiment des traces configuré"
SIDEBAR_BEDROCK_FALLBACK = (
    "Configuration incomplète : le pipeline revient au mode hors ligne et la trace l'indique."
)
YES = "oui"
NO = "non"

MODE_LABELS = {
    "offline": "Hors ligne (données réelles, sans Bedrock)",
    "bedrock": "Amazon Bedrock (agents)",
    "fixture": "Données d'essai (fixtures)",
}

# --- Statuts ----------------------------------------------------------------
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
STATUS_ORDER = ("conflict", "tension", "missing_info", "compliant")

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

ASSET_CLASS_LABELS = {
    "equity": "Actions",
    "etf_equity": "FNB d'actions",
    "etf_bond": "FNB d'obligations",
    "etf_commodity": "FNB de matières premières",
    "crypto": "Cryptoactifs",
}
# Libellés des secteurs du jeu de données (en anglais dans assets_universe.csv).
SECTOR_LABELS = {
    "Financials": "Finance",
    "Energy": "Énergie",
    "Industrials": "Industrie",
    "Utilities": "Services publics",
    "Consumer Staples": "Consommation de base",
    "Consumer Discretionary": "Consommation discrétionnaire",
    "Information Technology": "Technologies de l'information",
    "Communication Services": "Services de communication",
    "Health Care": "Santé",
    "Broad market (Canada)": "Marché large (Canada)",
    "Broad market (U.S.)": "Marché large (États-Unis)",
    "Broad market (U.S. growth/tech-heavy)": "Marché large (États-Unis, croissance et technologie)",
    "Broad market (U.S., ESG-screened)": "Marché large (États-Unis, filtre ESG)",
    "Bonds (Canada aggregate)": "Obligations (Canada, ensemble du marché)",
    "Bonds (Canada ultra short-term)": "Obligations (Canada, très court terme)",
    "Bonds (U.S. aggregate)": "Obligations (États-Unis, ensemble du marché)",
    "Bonds (U.S. long Treasury)": "Obligations (Trésor américain, long terme)",
    "Gold": "Or",
    "Crypto asset": "Cryptoactif",
}

# --- Profil -----------------------------------------------------------------
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
CUSTOM_DRAFT_CHANGED = (
    "Le formulaire a changé depuis la dernière activation : cliquez sur "
    "\"Mettre à jour le profil construit\" pour appliquer ces réponses."
)
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
PROFILE_NOT_IN_MODE = (
    "Le profil choisi n'existe pas dans ce mode de données. Choisissez un autre profil."
)

# --- Preuves (clic sur un chiffre, US-11) -------------------------------------
PROOF_HELP = "Cliquer pour voir d'où vient ce chiffre."
PROOF_ID = "Preuve"
PROOF_KEY = "Clé de la preuve"
PROOF_VALUE = "Valeur"
PROOF_TOOL = "Calculé par l'outil"
PROOF_SOURCES = "Sources"
PROOF_PERIOD = "Période"
PROOF_PERIOD_VALUE = "du {start} au {end}"
PROOF_DATA_AS_OF = "Données arrêtées au"
PROOF_CURRENCY = "Devise"
PROOF_TRANSFORMATION = "Calcul"
PROOF_OBSERVATIONS = "Observations"
PROOF_QUALIFIER = "Qualificatif (par seuil, calculé par le code)"
PROOF_LIMITS = "Limites rattachées"
PROOF_NONE = "aucune"
QUALIFIER_LABELS = {"low": "faible", "moderate": "modéré", "high": "élevé"}

# --- Radiographie (US-03) ----------------------------------------------------
XRAY_INTRO = "État du portefeuille fictif avant toute idée. Cliquez sur un chiffre pour le vérifier."
XRAY_PERIOD = "Période de calcul : du {start} au {end}, rendements quotidiens en {currency}."
XRAY_DRAWDOWN_DATES = "Perte maximale : du sommet du {start} au creux du {end}."
XRAY_TOP_ASSET = "Plus gros poids : {ticker}"
XRAY_RULES = "Statut par règle du profil"
XRAY_POSITIONS = "Poids par position"
XRAY_CLASSES = "Poids par classe d'actifs"
XRAY_SECTORS = "Poids par secteur"
XRAY_HYPOTHESIS = (
    "Hypothèses de l'équipe : portefeuille fictif, poids fixes rééquilibrés chaque jour, "
    "seuils réglables. Ce sont des descriptions du passé, pas des prévisions."
)
XRAY_SPINNER = "Calcul de la radiographie..."

# Mesures affichées dans les cartes et dans la comparaison, dans cet ordre
# (clés de preuve du flux A).
XRAY_METRICS = (
    "volatility_ann",
    "max_drawdown",
    "max_drawdown_cad",
    "recovery_days",
    "top_asset_weight",
    "defensive_share",
    "currency_exposure.CAD",
    "currency_exposure.USD",
    "largest_correlated_group_weight",
)
XRAY_CORRELATION = (
    "Groupe corrélé : période du {start} au {end}, {count} jours communs, en {currency}. "
    "Description du passé, pas une prévision."
)
# Sujet d'une preuve, pour distinguer avant, après et variantes.
SUBJECT_LABELS = {
    "portfolio_before": "avant",
    "portfolio_after": "après",
}
SUBJECT_VARIANT = "variante {variant_id}"

# --- Règles et gouvernance (US-06, US-07) -------------------------------------
RULE_MEASURE = "Mesure"
RULE_THRESHOLDS = "Seuils (hypothèses de l'équipe) : tension {warn}, conflit {limit}."
RULE_MARGIN_TO_TENSION = "Marge avant la tension : {margin}."
RULE_MARGIN_TO_CONFLICT = "Marge avant le conflit : {margin}."
RULE_BEYOND_LIMIT = "Au-delà de la limite de {margin}."
RULE_COUNTERFACTUAL = (
    "Simulation : conforme à cette règle avec un poids de {value} ou moins pour l'idée "
    "(hypothèse de l'équipe, pas une recommandation)."
)
RULE_NO_COUNTERFACTUAL = "Aucun poids testé pour l'idée n'est conforme à cette règle."
RULE_MISSING = "Information manquante : {reason}"
RULE_NO_POSITION = "aucune position"

# --- Idée (US-04) -------------------------------------------------------------
IDEA_INTRO = (
    "Choisissez une idée à simuler. L'outil ne recommande aucun actif : "
    "il vérifie la cohérence de votre idée avec le profil."
)
IDEA_SUGGESTIONS = "Idées en un clic"
IDEA_ASSET = "Actif"
IDEA_WEIGHT = "Poids visé dans le portefeuille (%)"
IDEA_FUNDING = "Source des fonds"
IDEA_FUNDING_LABELS = {
    "pro_rata": "Au prorata des positions existantes",
    "from_ticker": "Depuis un titre détenu",
}
IDEA_FUNDING_TICKER = "Titre vendu pour financer l'idée"
IDEA_NO_FUNDING_CANDIDATE = "Aucun autre titre détenu ne peut financer cette idée."
IDEA_FUNDING_WEIGHT = "Poids actuel de {ticker} dans le portefeuille : {weight}."
IDEA_SUBMIT = "Analyser cette idée"
IDEA_CURRENT = "Idée analysée : {weight} dans {ticker}, financée {funding}."
IDEA_FUNDING_SHORT = {
    "pro_rata": "au prorata des positions existantes",
    "from_ticker": "depuis {ticker}",
}
IDEA_NONE_YET = "Aucune idée analysée pour l'instant."
IDEA_FUNDING_RESET = (
    "{ticker} n'est pas détenu dans ce portefeuille : l'idée est financée au prorata."
)
# Idées de démonstration, les mêmes pour tous les profils (aucune association profil-actif).
IDEA_PRESETS = (
    {"label": "25 % dans TSLA", "ticker": "TSLA", "target_weight": 0.25},
    {"label": "15 % dans NVDA", "ticker": "NVDA", "target_weight": 0.15},
    {"label": "10 % dans BTC-USD", "ticker": "BTC-USD", "target_weight": 0.10},
    {"label": "40 % dans BTC-USD", "ticker": "BTC-USD", "target_weight": 0.40},
    {"label": "15 % dans XOM", "ticker": "XOM", "target_weight": 0.15},
)

# --- Résultat (US-05 à US-08) ---------------------------------------------------
RESULT_SPINNER = "Analyse de l'idée en cours..."
RESULT_OVERALL = (
    "Statut global après l'idée, par rapport aux règles du profil "
    "(hypothèses de l'équipe) : {status}"
)
RESULT_COMPOSITION = "Composition après l'idée : positions, classes d'actifs, secteurs"
RESULT_BEDROCK_PENDING = (
    "En mode Amazon Bedrock, l'analyse fait appel aux agents : elle n'est lancée qu'à votre demande "
    "(quotas partagés)."
)
RESULT_BEDROCK_RUN = "Analyser cette idée pour ce profil"
ASSET_FACTS_TITLE = "Faits historiques sur {ticker}"
ASSET_FACTS_NOTE = (
    "Ces chiffres décrivent l'actif seul, sur la période observée : ils sont les mêmes pour "
    "tous les profils. Seules les règles du profil changent."
)
ASSET_FACTS_METRICS = ("volatility_ann", "max_drawdown", "recovery_days")
ASSET_FACTS_SPINNER = "Lecture des faits sur l'actif..."
RESULT_OVERALL_BEFORE = "Avant l'idée : {status}"
ZONE_SIMULATION = "Simulation sur un portefeuille fictif"
ZONE_SIMULATION_NOTE = (
    "La colonne Après est une simulation : elle décrit l'effet historique de l'idée, "
    "pas ce qui arrivera."
)
ZONE_FACTS = "Faits historiques sur l'actif"
ZONE_ASSUMPTIONS = "Hypothèses de l'équipe"
ZONE_ASSUMPTIONS_NOTE = (
    "Les seuils des règles sont des hypothèses de l'équipe, pas des normes ni un conseil."
)
RESULT_COMPARE = "Avant et après l'idée"
COLUMN_MEASURE = "Mesure"
COLUMN_BEFORE = "Avant"
COLUMN_AFTER = "Après"
COLUMN_DELTA = "Écart"
RESULT_AMOUNT_NOTE = (
    "Les montants en dollars sont des pertes historiques observées sur la période, "
    "appliquées au capital fictif. Ce ne sont pas des prévisions."
)
RESULT_RULES = "Règles du profil après l'idée"
RESULT_MODE_FALLBACK = (
    "Bedrock n'a pas été utilisé pour cette analyse ({reason}) : la séquence d'outils "
    "scriptée a pris le relais, avec les mêmes outils et la même gouvernance."
)
# Mesures comparées avant et après, dans cet ordre.
COMPARE_METRICS = XRAY_METRICS
VARIANTS_TITLE = "Variantes simulées"
VARIANTS_NOTICE = (
    "Simulation, pas une recommandation : chaque variante repasse par les mêmes outils "
    "et la même gouvernance que votre idée."
)
VARIANTS_NONE = "Aucune variante simulée pour cette idée."
VARIANT_HEADER = "{variant_id} : {reason}"
VARIANT_IDEA = "Variante simulée : {weight} dans {ticker}, financée {funding}."
REASON_LABELS = {
    "reduce_weight": "réduire le poids",
    "change_funding_source": "changer la source des fonds",
    "spread_across_existing": "répartir sur les positions existantes",
}

# --- Explication (US-10) -------------------------------------------------------
EXPLANATION_LEVEL = "Niveau d'explication"
EXPLANATION_LEVEL_HELP = (
    "Changer de niveau ne relance que l'explicateur : les chiffres et les statuts restent identiques."
)
EXPLANATION_SPINNER = "Rédaction de l'explication..."
EXPLANATION_ORIGIN = {
    "llm": "Texte rédigé par l'agent explicateur (Bedrock), contrôlé par le validateur et le garde-fou.",
    "template": "Texte du gabarit écrit par l'équipe (sans modèle). Les chiffres sont les mêmes.",
}
EXPLANATION_EVIDENCE = "Preuves citées dans l'explication"
EXPLANATION_FALLBACK = (
    "L'agent explicateur n'a pas été utilisé ({reason}) : le texte affiché est celui du gabarit, "
    "avec les mêmes chiffres."
)

# --- Trace (US-13) -------------------------------------------------------------
TRACE_INTRO = (
    "Étapes réelles de l'exécution, construites par le code. Le raisonnement interne "
    "des modèles n'est jamais affiché."
)
TRACE_STEP = "Étape {step} : {name}"
TRACE_STEP_NAMES = {
    "analysis": "Analyse",
    "governance": "Gouvernance",
    "brief": "Dossier d'explication",
    "explanation": "Explication",
    "validation": "Validation",
    "guardrail": "Garde-fou",
}
TRACE_ACTORS = {
    "agent": "agent (Bedrock)",
    "code": "code",
    "guardrail": "garde-fou (Bedrock)",
}
TRACE_STATUSES = {
    "ok": "réussi",
    "fallback": "repli",
    "skipped": "non exécuté",
    "error": "erreur",
}
TRACE_DURATION_VALUE = "{ms} ms"
TRACE_MODEL = "Modèle"
TRACE_TURNS = "Tours de l'agent"
TRACE_REASON = "Raison du repli"
TRACE_TOOL_CALLS = "Outils appelés"
COLUMN_TOOL = "Outil"
COLUMN_PARAMS = "Paramètres"
COLUMN_STATUS = "Statut"
COLUMN_EVIDENCE = "Preuves produites"
TRACE_NO_PARAMS = "aucun"
TRACE_BEFORE_AFTER = "Statut global : {before} avant, {after} après."
TRACE_BRIEF = "Dossier {brief_id}, facteurs classés par le code : {factors}. Limites : {limits}."
TRACE_EXPLANATION = "Niveau {level}, texte : {origin}, essai {attempt}, lu dans le cache : {cache}."
TRACE_ORIGINS = {"llm": "agent explicateur", "template": "gabarit"}
TRACE_VALIDATION_OK = "Texte accepté : {count} renvois vérifiés."
TRACE_VALIDATION_KO = "Texte rejeté ({codes}), remplacé par le gabarit."
TRACE_GUARDRAIL = "Action : {action}. Score d'ancrage : {grounding}. Score de pertinence : {relevance}."
TRACE_GUARDRAIL_ACTIONS = {
    "none": "aucune intervention",
    "intervened": "intervention",
    "not_run": "contrôle non exécuté",
}
TRACE_STATUS_INTERVENTION = "intervention"
TRACE_GUARDRAIL_DENIED = "Sujet refusé : {topics}."
TRACE_GUARDRAIL_BELOW_THRESHOLD = "Ancrage sous le seuil : le texte du modèle n'est pas montré."
TRACE_GUARDRAIL_ERROR = "Le contrôle d'ancrage a échoué ({error})."
TRACE_GUARDRAIL_REPLACED = "Le texte du modèle a été remplacé par le gabarit."
TRACE_SAVED = "Trace enregistrée sur S3 : {location}."
TRACE_NOT_SAVED = "Trace non enregistrée sur S3 ({reason})."
TRACE_EXPLAINER_SAW = "Ce que l'explicateur a vu"
TRACE_EXPLAINER_SAW_HELP = (
    "Le dossier d'explication transmis à l'explicateur, tel quel : c'est sa seule entrée."
)
TRACE_GUARDRAIL_NOT_RUN = "Contrôle d'ancrage non exécuté : {reason}."
TOOL_LABELS = {
    "analyze_portfolio": "analyze_portfolio (radiographie)",
    "simulate_portfolio_change": "simulate_portfolio_change (simulation avant/après)",
    "get_asset_facts": "get_asset_facts (faits sur un actif)",
    "outil_inconnu": "outil inconnu (demande rejetée)",
}
REASON_CODES_FR = {
    "configuration_incomplete": "configuration Bedrock incomplète",
    "analyste_indisponible": "agent analyste indisponible",
    "explicateur_indisponible": "agent explicateur indisponible",
    "garde_fou_non_configure": "garde-fou non configuré",
    "rejet_du_validateur": "texte rejeté par le validateur",
    "garde_fou_indisponible": "garde-fou indisponible",
    "garde_fou_sortie": "texte refusé par le garde-fou",
    "mode_offline": "mode hors ligne",
    "non_execute": "non exécuté",
    "bucket_non_configure": "compartiment non configuré",
}

# --- Garde-fou (US-14) -----------------------------------------------------------
GUARDRAIL_INTRO = (
    "Requêtes prédéfinies, sans texte libre. Le garde-fou Amazon Bedrock refuse le conseil "
    "personnalisé, les ordres de transaction et les prédictions de rendement."
)
GUARDRAIL_OFFLINE = (
    "Le garde-fou n'est appelé qu'en mode Amazon Bedrock, avec un garde-fou configuré. "
    "Dans ce mode, chaque test affiche \"contrôle non exécuté\"."
)
GUARDRAIL_ALLOWED = "Requêtes qui doivent passer"
GUARDRAIL_DENIED = "Requêtes qui doivent être refusées"
GUARDRAIL_TEST = "Tester"
GUARDRAIL_SPINNER = "Interrogation du garde-fou..."
GUARDRAIL_HISTORY = "Résultats des tests"
GUARDRAIL_CLEAR = "Effacer les résultats"
GUARDRAIL_RESULT_DENIED = "Refusée par le garde-fou. Sujet : {topics}."
GUARDRAIL_RESULT_ALLOWED = "Permise par le garde-fou."
GUARDRAIL_RESULT_NOT_RUN = (
    "Contrôle non exécuté : passez en mode Amazon Bedrock avec un garde-fou configuré."
)
GUARDRAIL_EXPECTED = {"allowed": "Attendu : permise.", "denied": "Attendu : refusée."}
GUARDRAIL_UNEXPECTED = "Résultat différent de l'attendu : à signaler à l'équipe du garde-fou."
GUARDRAIL_NO_TOPIC = "non précisé"
# Noms des sujets refusés, tels que créés par scripts/setup_guardrail.py (flux C).
GUARDRAIL_TOPIC_LABELS = {
    "personalized_advice": "conseil personnalisé",
    "order_execution": "passage d'ordres",
    "return_prediction": "prédiction de rendement",
}

# --- Sources et méthode (US-11) ---------------------------------------------------
SOURCES_TITLE = "Sources des données"
SOURCES_COLUMNS = {
    "file": "Fichier",
    "content": "Contenu",
    "source": "Source",
    "source_url": "Adresse",
    "retrieved_on": "Extrait le",
    "coverage": "Couverture",
    "frequency": "Fréquence",
    "processing": "Traitement",
    "limitations": "Limites",
    "terms_of_use": "Conditions d'utilisation",
}
SOURCES_NOTE = "Textes repris de data/raw/sources_metadata.csv, rédigés en anglais par les organisateurs."
METHOD_TITLE = "Méthode et limites"
METHOD_INTRO = (
    "Les limites ci-dessous sont des textes fixes de l'équipe, affichés par le code. "
    "Elles s'appliquent à tous les chiffres."
)
UNIVERSE_TITLE = "Univers des actifs"
UNIVERSE_COLUMNS = {
    "ticker": "Symbole",
    "name": "Nom",
    "asset_class": "Classe d'actifs",
    "currency": "Devise",
    "sector": "Secteur",
}

# --- Messages ------------------------------------------------------------------
MSG_PROFILES_NOT_READY = (
    "Les profils ne sont pas disponibles dans ce mode "
    "(fichier des personas ou module profiles introuvable). Utilisez le mode Données d'essai."
)
MSG_PROFILE_BUILDER_NOT_READY = (
    "La construction de profil n'est pas disponible (module profiles.py du flux B absent)."
)
MSG_PIPELINE_NOT_READY = (
    "Le pipeline d'analyse n'est pas disponible (module du flux C introuvable). "
    "Utilisez le mode Données d'essai."
)
MSG_UNIVERSE_NOT_READY = "L'univers des actifs n'est pas disponible (module data_loading introuvable)."
MSG_REFERENCE_NOT_READY = "Les textes fixes ne sont pas disponibles (module reference_texts introuvable)."
MSG_GUARDRAIL_PROMPTS_MISSING = "Les requêtes prédéfinies du garde-fou sont introuvables."
MSG_FIXTURE_NO_ASSET_FACTS = "Faits sur l'actif non disponibles en mode Données d'essai."
MSG_ASSET_FACTS_FAILED = "Faits sur {ticker} non disponibles : {reason}"
MSG_XRAY_FAILED = "La radiographie n'a pas abouti : {reason}"
MSG_ANALYSIS_REFUSED = "L'idée ne peut pas être analysée : {reason}"
MSG_EXPLANATION_REFUSED = "L'explication ne peut pas être produite : {reason}"
MSG_FIXTURE_PROFILE_MISSING = (
    "Aucune donnée d'essai pour ce profil. En mode Données d'essai, seuls les profils "
    "ayant une fixture d'analyse sont disponibles."
)
MSG_FIXTURE_IDEA_ONLY = (
    "En mode Données d'essai, seule l'idée \"25 % dans TSLA\", financée au prorata, est disponible."
)
RETRY = "Réessayer"
MSG_UNEXPECTED_ERROR = (
    "Une erreur est survenue ({error_type}). "
    "La page reste utilisable : changez de mode ou réessayez."
)
