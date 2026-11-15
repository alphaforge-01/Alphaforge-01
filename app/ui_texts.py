"""Textes de l'interface AlphaForge, en français.

Tout texte destiné à l'utilisateur vit ici. Le code reste en anglais.
Ponctuation ASCII seulement (règle 1 de CLAUDE.md) : pas de guillemets
typographiques, pas de tiret cadratin, pas d'emoji. Principe : une phrase
courte à l'écran, le détail dans une info-bulle ou un encadré repliable.
"""

PAGE_TITLE = "AlphaForge"
BRAND = "AlphaForge"
BRAND_TAGLINE = "copilote de cohérence"

DISCLAIMER = (
    "Simulation éducative, pas un conseil financier personnalisé. "
    "Profils, portefeuilles et montants fictifs."
)
FIXTURE_BANNER = "Données d'essai : chiffres inventés, ils ne décrivent aucun marché."
NOT_AVAILABLE = "non disponible"

# --- Navigation ----------------------------------------------------------------
NAV_JOURNEY = "Parcours"
NAV_CHECKS = "Vérifier"
PAGE_NAMES = {
    "home": "Accueil",
    "simulation": "Simulation",
    "custom": "Créer un profil fictif",
    "guardrail": "Test du garde-fou",
    "sources": "Sources et méthode",
}
PAGE_INTROS = {
    "home": "Testez une idée de placement contre un profil d'investisseur fictif, avec chaque chiffre vérifiable.",
    "simulation": "Décrivez une idée ou réglez-la à la main : l'agent vérifie sa cohérence avec le profil, il ne recommande rien.",
    "custom": "Répondez par cases et curseurs : aucune donnée personnelle n'est demandée.",
    "guardrail": "Requêtes prédéfinies : le garde-fou doit laisser passer les unes et refuser les autres.",
    "sources": "D'où viennent les données et ce que les chiffres ne disent pas.",
}
NEXT_STEP = "Étape suivante : {page}"
GO_TO = "Aller à : {page}"
NEED_PROFILE = "Choisissez d'abord un profil."
PROFILE_NOT_IN_MODE = "Ce profil n'existe pas dans ce mode de données. Choisissez-en un autre."

# --- Accueil ----------------------------------------------------------------------
HOME_PROFILES_TITLE = "Choisir un profil du datathon"
HOME_CUSTOM_LINK = "Ou créer un profil fictif"
HOME_LEVEL_TITLE = "Niveau d'explication de l'agent"
HOME_LEVEL_DESCRIPTIONS = {
    "novice": "Novice : phrases simples, une image pour chaque notion, sans jargon.",
    "pro": "Pro : vocabulaire précis, mesures et méthode, plus concis.",
}
HOME_PREVIEW_TITLE = "Exemple de réponse en mode {level}"
HOME_LEVEL_HOVER_HINT = "Survolez Novice ou Pro pour voir comment l'agent s'exprime, puis réglez le curseur."
HOME_PREVIEW_SOURCE = (
    "Passage (Résumé) rédigé par l'agent explicateur pour {persona} et l'idée \"25 % dans TSLA\", "
    "modèle {model}, chiffres à la date de la trace. Texte réel, tiré de {source}."
)

# --- Simulation et conversation -------------------------------------------------------
SIM_SHOW_XRAY = "Afficher la radiographie du portefeuille"
SIM_MANUAL = "Réglages manuels"
CHAT_PLACEHOLDER = "Ex. : Et si je mettais 25 % dans TSLA ?"
CHAT_WELCOME = (
    "Décrivez une idée à simuler sur ce portefeuille fictif : un actif, un poids visé, "
    "et si vous voulez le titre vendu pour la financer."
)
CHAT_EXAMPLES = (
    "Et si je mettais 25 % dans TSLA ?",
    "Ajoute 10 % de BTC en vendant XIU.TO",
    "Et si j'ajoutais du Tesla ?",
)
CHAT_MANUAL_CHANGE = "Paramètres modifiés : {idea}"
CHAT_CHOICE = "Choix : {choice}"
CHAT_MODE_CHANGED = "Source des données : {mode}."
CHAT_UNDERSTOOD = "Idée simulée : {idea}."
CHAT_PREVIOUS = "Idée précédente : {idea}."
CHAT_COMPACT = "{idea} ({name})"
CHAT_GUARD_STATUS = {
    "none": "Garde-fou Bedrock : demande permise.",
    "not_run": "Garde-fou Bedrock : contrôle non exécuté (mode hors ligne ou garde-fou non configuré).",
}
CHAT_REFUSED = "Je ne peux pas répondre à cette demande. Sujet refusé : {topics}."
CHAT_REFUSED_BY = {
    "guardrail": "Refus du garde-fou Amazon Bedrock.",
    "local": (
        "Refus du contrôle local du code (règles fixes, actives même hors ligne). "
        "Rappel : l'outil ne passe aucun ordre et ne prédit aucun rendement."
    ),
}
CHAT_REFUSED_HELP = (
    "Je peux seulement simuler une idée sur ce portefeuille fictif et décrire le passé, "
    "par exemple : \"Et si je mettais 10 % dans NVDA ?\""
)
CHAT_CLARIFY = {
    "not_an_idea": "Je simule une idée précise : un actif de l'univers et un poids visé, par exemple \"15 % dans NVDA\".",
    "unknown_asset": "Je ne reconnais pas l'actif ({unknown}) dans l'univers étudié. Lequel voulez-vous simuler ?",
    "several_assets": "Vous citez plusieurs actifs ({tickers}). Je simule une idée à la fois : lequel ?",
    "missing_weight": "Quel poids visé pour {tickers} ? Choisissez une valeur ou précisez-la.",
    "several_weights": "Vous citez plusieurs poids. Lequel voulez-vous simuler ?",
    "weight_out_of_range": "Le poids visé doit être un nombre entier de 1 % à 100 %.",
    "missing_target": "Vous citez le titre vendu ({funding}), mais quel actif voulez-vous ajouter ?",
    "several_funding": "Un seul titre peut financer l'idée. Lequel ?",
    "funding_same_as_asset": "Le titre vendu ne peut pas être l'actif ajouté.",
    "funding_not_held": "{funding} n'est pas détenu dans ce portefeuille : il ne peut pas financer l'idée.",
}
CHAT_CLARIFY_MANUAL = "Vous pouvez aussi passer par les réglages manuels."
CHAT_KEY_POINTS = "Points clés (cliquez sur un chiffre pour sa preuve)"
CHAT_SHOW_DETAILS = "Voir le détail : faits, hypothèses, simulation, sources, trace"
CHAT_TAB_DETAILS = "Faits, hypothèses, simulation"
CHAT_TAB_TEXT = "Explication complète"
CHAT_TAB_SOURCES = "Sources et limites"
CHAT_TAB_TRACE = "Trace"
CHAT_SOURCES = "Sources citées"
CHAT_LIMITS = "Limites et incertitudes"

# --- En-tête et barre latérale ---------------------------------------------------
HEADER_MODE = "Mode"
HEADER_PROFILE = "Profil"
HEADER_IDEA = "Idée"
HEADER_NONE = "aucun"
HEADER_NO_IDEA = "aucune"

SIDEBAR_MODE_LABEL = "Source des données"
SIDEBAR_MODE_HELP = (
    "Hors ligne : données réelles, sans agent. Amazon Bedrock : agents et garde-fou "
    "(lancés seulement sur demande, quotas partagés). Données d'essai : chiffres inventés."
)
SIDEBAR_ACTIVE_PROFILE = "Profil actif"
SIDEBAR_NO_PROFILE = "Aucun profil choisi."
SIDEBAR_LEVEL = "Niveau"
SIDEBAR_BEDROCK = "État de Bedrock"
SIDEBAR_BEDROCK_MODELS = "Modèles"
SIDEBAR_BEDROCK_GUARDRAIL = "Garde-fou"
SIDEBAR_BEDROCK_TRACES = "Traces S3"
SIDEBAR_BEDROCK_FALLBACK = "Configuration incomplète : repli hors ligne, signalé dans la trace."
YES = "oui"
NO = "non"

MODE_LABELS = {
    "offline": "Hors ligne",
    "bedrock": "Amazon Bedrock",
    "fixture": "Données d'essai",
}

# --- Statuts et zones ------------------------------------------------------------
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

# Trois zones visuellement distinctes (US-12) : faits, hypothèses, simulations.
ZONE_LABELS = {
    "facts": "Faits historiques",
    "assumptions": "Hypothèses de l'équipe",
    "simulation": "Simulation",
}
ZONE_HELP = {
    "facts": "Mesures calculées sur des données passées. Elles décrivent, elles ne prédisent pas.",
    "assumptions": "Seuils réglables choisis par l'équipe : ni une norme, ni un conseil.",
    "simulation": "Portefeuille fictif modifié par l'idée. Effet historique, pas une prévision.",
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

# --- Profil ---------------------------------------------------------------------
FICTIONAL_BADGE = "Fictif"
PERSONA_AGE = "{age} ans"
PERSONA_RISK = "Risque"
PERSONA_HORIZON = "Horizon"
PERSONA_OBJECTIVE = "Objectif"
PERSONA_EXPERIENCE = "Expérience"
PERSONA_CAPITAL = "Capital fictif"
CHOOSE_PROFILE = "Choisir"
SELECTED_PROFILE = "Profil choisi"

CUSTOM_REMINDER = "Aucune donnée personnelle : ni nom, ni revenu, ni compte."
CUSTOM_OBJECTIVE = "Objectif"
CUSTOM_HORIZON = "Horizon (années)"
CUSTOM_RISK = "Tolérance au risque"
CUSTOM_EXPERIENCE = "Expérience"
CUSTOM_ESG = "Préférence ESG"
CUSTOM_CRYPTO = "Cryptoactifs permis"
CUSTOM_OWN_CAP = "Fixer mon plafond par titre"
CUSTOM_OWN_CAP_HELP = "Sinon, le plafond supposé par l'équipe pour ce niveau de risque s'applique."
CUSTOM_CAP = "Plafond par titre (%)"
CUSTOM_CAPITAL = "Capital fictif (CAD)"
CUSTOM_CAPITAL_HELP = "Montant inventé, sert seulement à exprimer les pertes historiques en dollars."
CUSTOM_PORTFOLIO = "Portefeuille de départ"
CUSTOM_RULES_TITLE = "Règles produites"
CUSTOM_USE = "Utiliser ce profil"
CUSTOM_UPDATE = "Mettre à jour le profil"
CUSTOM_ACTIVE = "Profil construit actif."
CUSTOM_DRAFT_CHANGED = "Réponses modifiées : cliquez sur \"Mettre à jour le profil\" pour les appliquer."
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
PROOF_QUALIFIER = "Qualificatif (seuil fixé par le code)"
PROOF_LIMITS = "Limites rattachées"
PROOF_NONE = "aucune"
QUALIFIER_LABELS = {"low": "faible", "moderate": "modéré", "high": "élevé"}

# --- Radiographie (US-03) ----------------------------------------------------
XRAY_PERIOD = "Du {start} au {end}, rendements quotidiens en {currency}."
XRAY_DRAWDOWN_DATES = "Sommet le {start}, creux le {end}"
XRAY_TOP_ASSET = "{ticker}"
XRAY_RULES = "Règles du profil"
XRAY_POSITIONS = "Positions"
XRAY_CLASSES = "Classes d'actifs"
XRAY_SECTORS = "Secteurs"
XRAY_COMPOSITION = "Composition détaillée"
XRAY_METHOD = "Méthode et hypothèses"
XRAY_HYPOTHESIS = (
    "Portefeuille fictif, poids fixes rééquilibrés chaque jour, seuils réglables. "
    "Ce sont des descriptions du passé, pas des prévisions."
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
XRAY_CORRELATION = "Groupe corrélé : du {start} au {end}, {count} jours communs, en {currency}."
# Sujet d'une preuve, pour distinguer avant, après et variantes.
SUBJECT_LABELS = {
    "portfolio_before": "avant",
    "portfolio_after": "après",
}
SUBJECT_VARIANT = "variante {variant_id}"

# --- Règles et gouvernance (US-06, US-07) -------------------------------------
RULE_THRESHOLDS = "Tension {warn}, conflit {limit}."
RULE_THRESHOLDS_HELP = "Seuils : hypothèses de l'équipe, réglables, pas une norme."
RULE_MARGIN_TO_TENSION = "Marge avant la tension : {margin}."
RULE_MARGIN_TO_CONFLICT = "Marge avant le conflit : {margin}."
RULE_BEYOND_LIMIT = "Dépasse la limite de {margin}."
RULE_COUNTERFACTUAL = "Conforme avec un poids de {value} ou moins pour l'idée (simulation)."
RULE_NO_COUNTERFACTUAL = "Aucun poids testé pour l'idée n'est conforme."
RULE_MISSING = "Information manquante : {reason}"
RULE_NO_POSITION = "aucune position"

# --- Idée (US-04) -------------------------------------------------------------
IDEA_SUGGESTIONS = "Idées en un clic"
IDEA_ASSET = "Actif"
IDEA_WEIGHT = "Poids visé (%)"
IDEA_FUNDING = "Financement"
IDEA_FUNDING_LABELS = {
    "pro_rata": "Au prorata",
    "from_ticker": "Depuis un titre détenu",
}
IDEA_FUNDING_TICKER = "Titre vendu"
IDEA_NO_FUNDING_CANDIDATE = "Aucun autre titre détenu ne peut financer cette idée."
IDEA_FUNDING_WEIGHT = "Poids actuel de {ticker} : {weight}."
IDEA_SUBMIT = "Simuler"
IDEA_CURRENT = "{weight} dans {ticker}, financée {funding}"
IDEA_FUNDING_SHORT = {
    "pro_rata": "au prorata",
    "from_ticker": "depuis {ticker}",
}
IDEA_FUNDING_RESET = "{ticker} n'est pas détenu ici : l'idée est financée au prorata."
# Idées de démonstration, les mêmes pour tous les profils (aucune association profil-actif).
IDEA_PRESETS = (
    {"label": "25 % dans TSLA", "ticker": "TSLA", "target_weight": 0.25},
    {"label": "15 % dans NVDA", "ticker": "NVDA", "target_weight": 0.15},
    {"label": "10 % dans BTC-USD", "ticker": "BTC-USD", "target_weight": 0.10},
    {"label": "40 % dans BTC-USD", "ticker": "BTC-USD", "target_weight": 0.40},
    {"label": "15 % dans XOM", "ticker": "XOM", "target_weight": 0.15},
)

# --- Résultat (US-05 à US-08) ---------------------------------------------------
RESULT_SPINNER = "Analyse de l'idée..."
RESULT_BEDROCK_PENDING = "Mode Amazon Bedrock : les agents ne sont lancés que sur demande (quotas partagés)."
RESULT_BEDROCK_RUN = "Analyser cette idée pour ce profil"
RESULT_MODE_FALLBACK = "Bedrock non utilisé ({reason}) : mêmes outils et même gouvernance, en séquence scriptée."

# Verdict en tête du résultat : le désaccord avec le profil est dit tout de suite.
VERDICT_TITLE = "Après l'idée : {status}"
VERDICT_BEFORE = "Avant l'idée : {status}"
VERDICT_HEADLINES = {
    "conflict": "Cette idée va à l'encontre du profil.",
    "tension": "Cette idée met le profil sous tension.",
    "missing_info": "Il manque une information pour conclure.",
    "compliant": "Cette idée respecte les règles du profil.",
}
VERDICT_RULE = "{label} : {status}."
VERDICT_FOOTNOTE = "Règles et seuils : hypothèses de l'équipe. Détail sous \"Voir le détail\"."

TAB_COMPARE = "Avant / après"
TAB_RULES = "Règles du profil"
TAB_FACTS = "Faits sur {ticker}"
TAB_VARIANTS = "Variantes"

COLUMN_MEASURE = "Mesure"
COLUMN_BEFORE = "Avant"
COLUMN_AFTER = "Après"
COLUMN_DELTA = "Écart"
RESULT_AMOUNT_NOTE = "Montants : pertes historiques observées sur la période, appliquées au capital fictif."
RESULT_COMPOSITION = "Composition après l'idée"
# Libellés génériques des mesures qui ont des membres propres à chaque colonne ou qui peuvent manquer.
METRIC_LABELS = {"largest_correlated_group_weight": "Poids du plus grand groupe corrélé"}
COMPARE_METRICS = XRAY_METRICS

ASSET_FACTS_NOTE = "Mêmes chiffres pour tous les profils : seules les règles changent."
ASSET_FACTS_METRICS = ("volatility_ann", "max_drawdown", "recovery_days")
ASSET_FACTS_SPINNER = "Lecture des faits sur l'actif..."

VARIANTS_NOTICE = "Pas une recommandation : chaque variante repasse par les mêmes outils et la même gouvernance."
VARIANTS_NONE = "Aucune variante simulée pour cette idée."
VARIANT_HEADER = "{variant_id} : {reason}"
VARIANT_RULES = "Règles pour cette variante"
REASON_LABELS = {
    "reduce_weight": "réduire le poids",
    "change_funding_source": "changer la source des fonds",
    "spread_across_existing": "répartir sur les positions existantes",
}

# --- Explication (US-10) -------------------------------------------------------
EXPLANATION_LEVEL = "Niveau d'explication"
EXPLANATION_LEVEL_HELP = "Seul le texte change : chiffres et statuts restent identiques."
EXPLANATION_SPINNER = "Rédaction de l'explication..."
EXPLANATION_RUN = "Rédiger l'explication (niveau {level})"
EXPLANATION_ORIGIN = {
    "llm": "Rédigé par l'agent explicateur",
    "template": "Texte de repli (gabarit)",
}
EXPLANATION_ORIGIN_HELP = {
    "llm": "Agent Bedrock, contrôlé par le validateur et le garde-fou.",
    "template": "Gabarit écrit par l'équipe, sans modèle. Mêmes chiffres.",
}
EXPLANATION_EVIDENCE = "Preuves citées"
EXPLANATION_FALLBACK = "Agent explicateur non utilisé ({reason}) : texte du gabarit, mêmes chiffres."

# --- Trace (US-13) -------------------------------------------------------------
TRACE_INTRO = "Étapes réelles, construites par le code. Le raisonnement interne des modèles n'est jamais affiché."
TRACE_STEP = "{step}. {name}"
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
COLUMN_CALLER = "Décidé par"
COLUMN_PARAMS = "Paramètres"
COLUMN_STATUS = "Statut"
COLUMN_EVIDENCE = "Preuves produites"
TRACE_NO_PARAMS = "aucun"
TRACE_BEFORE_AFTER = "Statut global : {before} avant, {after} après."
TRACE_BRIEF = "Dossier {brief_id}. Facteurs classés par le code : {factors}. Limites : {limits}."
TRACE_EXPLANATION = "Niveau {level}, texte : {origin}, essai {attempt}, cache : {cache}."
TRACE_ORIGINS = {"llm": "agent explicateur", "template": "gabarit"}
TRACE_VALIDATION_OK = "Texte accepté : {count} renvois vérifiés."
TRACE_VALIDATION_KO = "Texte rejeté ({codes}), remplacé par le gabarit."
TRACE_GUARDRAIL = "Action : {action}. Ancrage : {grounding}. Pertinence : {relevance}."
TRACE_GUARDRAIL_ACTIONS = {
    "none": "aucune intervention",
    "intervened": "intervention",
    "not_run": "contrôle non exécuté",
}
TRACE_STATUS_INTERVENTION = "intervention"
TRACE_STATUS_FLAGGED = "signalé"
TRACE_GUARDRAIL_SCORE_NOTE = (
    "Le score d'ancrage mesure la proximité du texte avec le dossier, pas l'exactitude des statuts : "
    "celle-ci vient du code (renvois vérifiés, validateur, statuts calculés par la gouvernance)."
)
TRACE_GUARDRAIL_DENIED = "Sujet refusé : {topics}."
TRACE_GUARDRAIL_BELOW_THRESHOLD = (
    "Ancrage sous le seuil du garde-fou : signalé, sans écarter le texte (mode détection)."
)
TRACE_GUARDRAIL_ERROR = "Le contrôle d'ancrage a échoué ({error})."
TRACE_GUARDRAIL_REPLACED = "Texte du modèle remplacé par le gabarit."
TRACE_SAVED = "Trace enregistrée sur S3 : {location}."
TRACE_NOT_SAVED = "Trace non enregistrée sur S3 ({reason})."
TRACE_EXPLAINER_SAW = "Ce que l'explicateur a vu"
TRACE_EXPLAINER_SAW_HELP = "Le dossier transmis à l'explicateur, tel quel : sa seule entrée."
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
    "ancrage_insuffisant": "ancrage trop faible, sous le plancher du pipeline",
    "mode_offline": "mode hors ligne",
    "non_execute": "non exécuté",
    "bucket_non_configure": "compartiment non configuré",
}

# --- Garde-fou (US-14) -----------------------------------------------------------
GUARDRAIL_DETAILS = "Ce que le garde-fou refuse"
GUARDRAIL_DETAILS_TEXT = (
    "Le garde-fou Amazon Bedrock refuse le conseil personnalisé, les ordres de transaction "
    "et les prédictions de rendement. Aucun texte libre : seules ces requêtes sont testables."
)
GUARDRAIL_OFFLINE = "Le garde-fou n'est appelé qu'en mode Amazon Bedrock. Ici, chaque test affiche \"contrôle non exécuté\"."
GUARDRAIL_ALLOWED = "Doivent passer"
GUARDRAIL_DENIED = "Doivent être refusées"
GUARDRAIL_TEST = "Tester"
GUARDRAIL_SPINNER = "Interrogation du garde-fou..."
GUARDRAIL_HISTORY = "Résultats"
GUARDRAIL_CLEAR = "Effacer"
GUARDRAIL_RESULT_DENIED = "Refusée. Sujet : {topics}."
GUARDRAIL_RESULT_ALLOWED = "Permise."
GUARDRAIL_RESULT_NOT_RUN = "Contrôle non exécuté : passez en mode Amazon Bedrock avec un garde-fou configuré."
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
SOURCES_NOTE = "Repris de data/raw/sources_metadata.csv (textes des organisateurs, en anglais)."
METHOD_TITLE = "Limites"
METHOD_INTRO = "Textes fixes de l'équipe, valables pour tous les chiffres."
UNIVERSE_TITLE = "Univers des actifs"
UNIVERSE_COLUMNS = {
    "ticker": "Symbole",
    "name": "Nom",
    "asset_class": "Classe d'actifs",
    "currency": "Devise",
    "sector": "Secteur",
}

# --- Messages ------------------------------------------------------------------
MSG_PROFILES_NOT_READY = "Profils indisponibles dans ce mode. Essayez le mode Données d'essai."
MSG_PROFILE_BUILDER_NOT_READY = "Construction de profil indisponible (module profiles absent)."
MSG_PIPELINE_NOT_READY = "Pipeline d'analyse indisponible. Essayez le mode Données d'essai."
MSG_UNIVERSE_NOT_READY = "Univers des actifs indisponible (module data_loading absent)."
MSG_REFERENCE_NOT_READY = "Textes fixes indisponibles (module reference_texts absent)."
MSG_GUARDRAIL_PROMPTS_MISSING = "Requêtes prédéfinies du garde-fou introuvables."
MSG_FIXTURE_NO_ASSET_FACTS = "Faits sur l'actif indisponibles en mode Données d'essai."
MSG_ASSET_FACTS_FAILED = "Faits sur {ticker} indisponibles : {reason}"
MSG_XRAY_FAILED = "Radiographie impossible : {reason}"
MSG_ANALYSIS_REFUSED = "Idée non analysable : {reason}"
MSG_EXPLANATION_REFUSED = "Explication impossible : {reason}"
MSG_FIXTURE_PROFILE_MISSING = "Aucune donnée d'essai pour ce profil (seuls les profils avec fixture sont disponibles)."
MSG_FIXTURE_IDEA_ONLY = "En mode Données d'essai, seule l'idée \"25 % dans TSLA\", au prorata, est disponible."
MSG_PREVIEW_MISSING = "Aperçu des niveaux indisponible (traces de démonstration absentes)."
RETRY = "Réessayer"
MSG_UNEXPECTED_ERROR = "Une erreur est survenue ({error_type}). La page reste utilisable : réessayez ou changez de mode."
