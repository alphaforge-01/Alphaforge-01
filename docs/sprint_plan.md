# Plan de sprint (14 au 16 novembre 2026)

Statut : proposition à valider par l'équipe. Ce plan applique les décisions de `docs/use_case_decision.md` (section "Décisions de l'équipe") et les règles de `CLAUDE.md`. Les choix marqués "par défaut" peuvent être renversés par l'équipe.

## 1. Cadre et horloge

- H0 = samedi 14 novembre, 14 h 30 (Montréal).
- Échéances officielles (site PolyFinances, reprises dans `AWS_WORKSHOP.md`, hors du dépôt) :

| Quand | Quoi |
| --- | --- |
| Dimanche 15 novembre, 16 h | Fin du travail sur place |
| **Dimanche 15 novembre, 23 h 59** | **Dépôt GitHub et application** |
| Lundi 16 novembre, 13 h 59 | Fermeture des comptes AWS et destruction des données |
| Lundi 16 novembre, 14 h | Dépôt de la vidéo, du one pager et de la documentation technique |

- Conséquences : le code et l'application doivent être sur `main` **dimanche avant 23 h 59**. Le bloc S6 de lundi ne sert plus qu'à la vidéo et aux documents, jamais au code. Le compte à rebours de Workshop Studio ne correspond pas exactement à l'heure de fermeture annoncée : enregistrer la démo dimanche soir.
- Capacité : 4 personnes, environ 16 h de développement chacune avant le gel, plus une soirée pour la vidéo et les livrables.

| Bloc | Horaire | Heures depuis H0 |
| --- | --- | --- |
| S1 | Samedi 14 h 30 à 18 h 30 | H0 à H+4 |
| S2 | Samedi 19 h 30 à 23 h 30 | H+5 à H+9 |
| Nuit | Sommeil | H+9 à H+18,5 |
| S3 | Dimanche 9 h à 13 h | H+18,5 à H+22,5 |
| S4 | Dimanche 14 h à 18 h 30 | H+23,5 à H+28 |
| S5 | Dimanche 19 h 30 à 22 h 30 | H+29 à H+32 (vidéo, livrables) |
| S6 | Lundi 7 h 30 à 13 h | H+41 à H+46,5 (vidéo, one pager, documentation technique ; aucun code) |

## 2. Périmètre

Question servie : "Mon portefeuille fictif correspond-il à mon profil, et que change mon idée de placement ?"

| Priorité | Contenu | Critères servis |
| --- | --- | --- |
| P1 (obligatoire) | Chargement avec `as_of`, alignement des calendriers, conversion en CAD, volatilité, perte maximale, durée de récupération, concentration, exposition USD/CAD | Analyse de données |
| P1 | Radiographie du portefeuille fictif et simulation avant/après d'une idée (actif, poids, source des fonds) | Qualité, analyse de données |
| P1 | Trois personas, profil par cases, 6 règles, gouvernance en code (4 statuts, marge, contrefactuel "conforme sous X %") | Agentique et explicabilité |
| P1 | Registre de preuves, dossier d'explication, gabarit de repli novice et pro, validateur | Explicabilité |
| P1 | Agent analyste (Converse, outils, tours bornés) et agent explicateur (un appel, dossier seul) | Agentique, AWS |
| P1 | Garde-fou Bedrock (sujets refusés, ancrage en mode détection), traces sur S3 privé | AWS |
| P1 | Interface locale : profil, radiographie, idée, résultat, bascule novice/pro, clic sur un chiffre, trace à six étapes, panneau de test du garde-fou, avertissement | UX/UI |
| P2 (si P1 est vert à H+24) | Fausse diversification par corrélations (scène Amira "40 % crypto") | Qualité |
| P2 | ESG minimal pour Mateo : 3 à 5 preuves datées pour XOM et CNQ.TO, sinon "information manquante". Budget : 1 h 30, pas plus | Qualité |
| P2 | Deux profils côte à côte dans la même page | UX/UI |

Hors périmètre : texte libre (profil et idée), `propose_profile_rule`, annonces planifiées, rejeu à une date passée (seul le paramètre `as_of` reste), scénarios hypothétiques, nouvelles, "comment en profiter ?" comme fonction (c'est seulement une requête refusée), outil `get_historical_episode`, chevauchement des FNB, Lambda, hébergement AWS, base de connaissances, troisième niveau d'explication.

Scènes de démo, par ordre de priorité :

| No | Scène | Dépend de |
| --- | --- | --- |
| 1 | Robert, 25 % de TSLA : tension nommée, contrefactuel, variante | P1 |
| 2 | Même demande pour Amira : autre verdict, même mécanisme | P1 |
| 3 | Bascule novice/pro : texte différent, chiffres identiques, "ce que l'explicateur a vu" | P1 |
| 4 | Clic sur un chiffre : calcul, source, période, devise, limites | P1 |
| 5 | Requête refusée par le garde-fou, score d'ancrage du texte | P1 |
| 6 | Mateo et XOM (ESG) ou Amira et la fausse diversification | P2 |

## 3. Contrats (heure 0 à 1 h 30)

Un seul module : `src/alphaforge/contracts.py`. Des `TypedDict` et des `Literal`, donc de simples dictionnaires sérialisables en JSON. Aucune conversion n'est nécessaire avec les fixtures, les résultats d'outils Bedrock et l'état de session de Streamlit. Le module contient aussi `check_keys(obj, contract)` qui vérifie les clés obligatoires.

Règles de modification :

- Propriétaire : flux B. Version v0 fusionnée à H+1,5, gel à H+6 (v1).
- Avant le gel : changement demandé dans le canal de l'équipe, fait par B dans une petite PR `chore/contracts-update`, annoncé à tous.
- Après le gel : ajouts de clés facultatives seulement. Aucun renommage, aucune suppression.
- Les valeurs d'énumération sont en anglais. Les libellés français vivent dans les champs `label_fr` et dans l'interface.
- Les pourcentages sont stockés en fraction (0.25), le champ `display_value` porte le format français ("25 %").

```python
Level = Literal["novice", "pro"]
RuleStatus = Literal["compliant", "tension", "conflict", "missing_info"]
RuleType = Literal[
    "max_single_asset_weight", "max_asset_class_weight", "max_portfolio_volatility",
    "max_portfolio_drawdown", "min_defensive_share", "excluded_asset_class",
    "max_correlated_group_weight", "esg_exclusion",   # les deux derniers : P2
]
ReasonCode = Literal["reduce_weight", "change_funding_source", "spread_across_existing"]

class Rule(TypedDict):
    rule_id: str            # "R1"
    rule_type: RuleType
    params: dict            # ex. {"asset_class": "crypto"}
    direction: Literal["max", "min"]
    warn_threshold: float | None    # au-delà : tension
    limit_threshold: float | None   # au-delà : conflit
    unit: Literal["pct", "ratio", "bool"]
    label_fr: str
    origin: Literal["persona", "checkbox"]
    is_assumption: bool     # toujours True : seuil = hypothèse de l'équipe

class InvestorProfile(TypedDict):
    profile_id: str         # "robert", "amira", "mateo", "custom"
    display_name: str
    is_fictional: bool      # toujours True
    objective: str
    horizon_years_min: int
    horizon_years_max: int
    risk_tolerance: Literal["low", "low_moderate", "moderate", "high"]
    experience: Literal["beginner", "intermediate", "advanced"]
    esg_preference: Literal["none", "moderate", "strong"]
    crypto_allowed: bool
    capital_cad: float
    default_level: Level
    rules: list[Rule]

class Position(TypedDict):
    ticker: str
    weight: float           # somme des poids = 1.0

class Portfolio(TypedDict):
    portfolio_id: str
    label_fr: str
    is_fictional: bool
    base_currency: Literal["CAD"]
    positions: list[Position]

class InvestmentIdea(TypedDict):
    ticker: str
    target_weight: float
    funding_source: Literal["pro_rata", "from_ticker"]
    funding_ticker: str | None

class EvidenceEntry(TypedDict):
    evidence_id: str        # "E1", attribué par le registre
    evidence_key: str       # stable : "<metric>:<subject>"
    tool_name: str
    metric: str             # "volatility_ann", "max_drawdown", "recovery_days", ...
    subject: str            # ticker, "portfolio_before", "portfolio_after", "variant:V1"
    label_fr: str
    value: float | str | None
    unit: Literal["pct", "cad", "days", "ratio", "count", "text"]
    display_value: str
    qualifier: Literal["low", "moderate", "high"] | None   # réservé : toujours None, aucun seuil global de risque ; les jugements viennent de la gouvernance, par profil
    period_start: str | None    # ISO
    period_end: str | None
    as_of: str
    currency: Literal["CAD", "USD"] | None
    source_ids: list[str]       # identifiants de data/raw/sources_metadata.csv ou sources.md
    transformation: str         # phrase courte en français
    n_observations: int | None
    limit_ids: list[str]        # "L1", ...

class ToolResult(TypedDict):
    tool_name: str
    call_id: str
    params: dict
    status: Literal["ok", "missing_info", "error"]
    error_message: str | None
    data: dict                  # forme propre à l'outil, voir plus bas
    evidence: list[EvidenceEntry]

class PortfolioSnapshot(TypedDict):   # data de analyze_portfolio
    subject: str
    weights: dict[str, float]
    volatility_ann: float
    max_drawdown: float
    max_drawdown_start: str
    max_drawdown_end: str
    recovery_days: int | None   # None = pas encore récupéré dans la fenêtre
    top_asset: str
    top_asset_weight: float
    weight_by_sector: dict[str, float]
    weight_by_asset_class: dict[str, float]
    currency_exposure: dict[str, float]   # {"CAD": .., "USD": ..}
    defensive_share: float
    largest_correlated_group_weight: float | None   # P2 : diversification.py ; None = trop peu d'observations
    correlated_group_members: NotRequired[list[str]]   # titres du plus gros groupe corrélé (vide : aucun groupe)

class Counterfactual(TypedDict):
    parameter: Literal["target_weight"]
    compliant_at_or_below: float | None   # None = aucun poids conforme
    display_value: str

class RuleCheck(TypedDict):
    check_id: str               # "G1"
    rule_id: str
    rule_type: RuleType
    label_fr: str
    status: RuleStatus
    value: float | None
    warn_threshold: float | None
    limit_threshold: float | None
    margin: float | None        # distance au prochain seuil
    unit: str
    evidence_ids: list[str]
    counterfactual: Counterfactual | None
    missing_reason: str | None

class GovernanceResult(TypedDict):
    profile_id: str
    subject: str                # "portfolio_before", "portfolio_after", "variant:V1"
    overall_status: RuleStatus  # le pire statut
    checks: list[RuleCheck]

class AnalystSubmission(TypedDict):     # paramètres de submit_analysis
    understood_idea: InvestmentIdea
    variants: list[dict]        # au plus 2 : {"reason_code": ReasonCode, "idea": InvestmentIdea}
    highlight_evidence_ids: list[str]   # au plus 2
    unsupported_requests: list[str]

class Variant(TypedDict):
    variant_id: str             # "V1"
    reason_code: ReasonCode
    idea: InvestmentIdea
    snapshot: PortfolioSnapshot
    governance: GovernanceResult

class TraceStep(TypedDict):
    step: int                   # 1 à 6
    name: Literal["analysis", "governance", "brief", "explanation", "validation", "guardrail"]
    actor: Literal["agent", "code", "guardrail"]
    status: Literal["ok", "fallback", "skipped", "error"]
    model_id: str | None
    duration_ms: int
    details: dict               # ex. tool_calls: [{tool_name, params, status, evidence_ids}], turns

class AnalysisResult(TypedDict):
    run_id: str
    created_at: str
    as_of: str
    mode: Literal["bedrock", "offline"]
    is_fixture: bool            # True : chiffres inventés, bandeau "données d'essai"
    profile: InvestorProfile
    portfolio_before: Portfolio
    idea: InvestmentIdea
    snapshot_before: PortfolioSnapshot
    snapshot_after: PortfolioSnapshot
    governance_before: GovernanceResult
    governance_after: GovernanceResult
    variants: list[Variant]
    evidence: dict[str, EvidenceEntry]
    limits: list[dict]          # {limit_id, text_novice, text_pro}
    submission: AnalystSubmission
    trace: list[TraceStep]      # étapes 1 à 3

class ExplanationBrief(TypedDict):      # seule entrée de l'explicateur
    brief_id: str               # empreinte du contenu, sert de clé de cache
    run_id: str
    level: Level
    profile_rules: list[Rule]
    idea: InvestmentIdea
    ranked_factors: list[dict]  # {rank, check_id, status, evidence_ids}, ordre fixé par le code
    checks: list[RuleCheck]
    variants: list[dict]        # {variant_id, reason_code, overall_status, evidence_ids}
    evidence: list[EvidenceEntry]
    limits: list[dict]          # {limit_id, text} pour le niveau
    glossary: list[dict]        # {term_id "T1", term, definition, analogy}
    max_chars_per_slot: int

class ExplainerOutput(TypedDict):
    brief_id: str
    level: Level
    summary: str                # texte avec renvois [E3] [G1] [T2], aucun chiffre en clair
    factors: list[dict]         # {check_id, text}, même ordre que ranked_factors
    counterfactual: str
    variants: str
    limits_context: str
    origin: Literal["llm", "template"]
    model_id: str | None
    prompt_version: str | None
    attempt: int

class ValidationResult(TypedDict):
    is_valid: bool
    rejections: list[dict]      # {code, slot, excerpt}
    checked_references: list[str]
# codes : unknown_reference, number_outside_registry, forbidden_term,
#         missing_rule_citation, slot_missing, too_long

class GuardrailResult(TypedDict):
    check: Literal["request_topic", "output_grounding"]
    action: Literal["none", "intervened", "not_run"]
    denied_topics: list[str]
    grounding_score: float | None
    relevance_score: float | None
    mode: Literal["detect", "block"]

class ExplanationResult(TypedDict):
    output: ExplainerOutput
    validation: ValidationResult
    guardrail: GuardrailResult
    rendered_markdown: str      # renvois remplacés par les valeurs du registre
    trace: list[TraceStep]      # étapes 4 à 6
```

Signatures qui servent de coutures entre les flux (gelées avec les contrats) :

| Fonction | Module (propriétaire) | Appelée par |
| --- | --- | --- |
| `analyze_portfolio(portfolio, as_of=None, capital_cad=None) -> ToolResult` | `agent_tools.py` (A) | C, B |
| `get_asset_facts(ticker, as_of=None) -> ToolResult` | `agent_tools.py` (A) | C |
| `simulate_portfolio_change(portfolio, idea, as_of=None, capital_cad=None) -> ToolResult` | `agent_tools.py` (A) | C, B |
| `EvidenceRegistry.register(tool_result) -> ToolResult` (attribue les `evidence_id`) | `evidence.py` (A) | C |
| `load_personas() -> dict`, `build_profile_from_answers(answers) -> InvestorProfile` | `profiles.py` (B) | D, C |
| `evaluate(profile, snapshot, simulate_fn=None, idea=None) -> GovernanceResult` | `governance.py` (B) | C |
| `build_brief(result, level) -> ExplanationBrief` | `explanation_brief.py` (B) | C |
| `render_template(brief) -> ExplainerOutput` | `explanation_fallback.py` (B) | C |
| `validate(output, brief) -> ValidationResult` | `explanation_validator.py` (B) | C |
| `render_markdown(output, brief) -> str` | `explanation_rendering.py` (B) | C, D |
| `run_analysis(profile, portfolio, idea, as_of=None, mode="offline") -> AnalysisResult` | `analysis_pipeline.py` (C) | D |
| `explain(result, level, mode="offline") -> ExplanationResult` | `analysis_pipeline.py` (C) | D |
| `check_request(text) -> GuardrailResult` | `analysis_pipeline.py` (C) | D |

Mode `offline` : l'analyste est remplacé par une séquence d'outils scriptée (étiquetée "code" dans la trace) et l'explication vient du gabarit. Ce mode sert de bouchon pour D, de filet pour la démo et de référence de comparaison.

Fixtures dans `tests/fixtures/` (créées par B à l'heure 0, chiffres inventés, `is_fixture: true`) :

| Fichier | Sert à |
| --- | --- |
| `profile_robert.json`, `profile_amira.json`, `portfolio_robert.json`, `idea_tsla_25.json` | Tous |
| `tool_results_robert_tsla.json` (liste de `ToolResult`) | B (gouvernance), C (outils bouchons) |
| `analysis_result_robert_tsla.json`, `analysis_result_amira_tsla.json` | D (interface), B (dossier) |
| `explanation_brief_robert_novice.json` | C (explicateur) |
| `explainer_output_robert_novice.json`, `explainer_output_robert_pro.json`, `explainer_output_invalid.json` | D (rendu), B (validateur) |

Chacun peut ajouter ses propres fixtures (nouveau fichier), jamais modifier celles des autres.

## 4. Flux de travail

Attribution (décision d'équipe) :

| Flux | Responsable |
| --- | --- |
| A : données, métriques, outils | Naoufal |
| B : contrats, profils, gouvernance, explication en code, intégration des PR | Samer |
| C : agents, Bedrock, garde-fou | Godwin |
| D : interface, script de démo, vidéo | Ibrahima |

Les user stories du MVP, avec leurs critères d'acceptation et leur flux, sont dans `docs/user_stories.md`.

Règles communes :

- Un fichier a un seul propriétaire. Fichiers partagés : `contracts.py` et `requirements.txt` (B), `README.md` et `data/external/sources.md` (A). Pour y changer quelque chose, on demande au propriétaire.
- Une branche par sujet, créée depuis `main` à jour. Les PR sont fusionnées par squash. Après chaque fusion, repartir d'une nouvelle branche depuis `main` (ne pas continuer sur la branche fusionnée).
- Chaque flux fusionne au moins une fois par jalon. Les tests de son dossier doivent passer (`pytest tests/`).
- Code en anglais, textes pour humains en français, ni tiret cadratin ni emoji (règles 1 et 4).
- Sous-agents (règle 9) : ils servent la personne qui utilise Claude Code. Les autres lui transmettent leurs demandes de revue aux jalons.

### Flux A : données, métriques, outils

| Élément | Détail |
| --- | --- |
| Branches | `feat/data-metrics`, puis `feat/analysis-tools`, `feat/diversification` (P2), `data/esg-evidence` (P2), `docs/readme-technical-doc` |
| Fichiers | `src/alphaforge/data_loading.py`, `calendar_alignment.py`, `fx_conversion.py`, `metrics.py`, `portfolio.py`, `diversification.py`, `agent_tools.py`, `evidence.py`, `scripts/run_scenarios.py`, `data/external/esg_evidence.csv`, tests correspondants, `README.md`, `docs/technical_documentation.md` |
| Consomme | `data/raw/*.csv`, contrats, fixtures de profil et de portefeuille |
| Livre | Trois outils qui rendent des `ToolResult` avec preuves, le registre de preuves |

| No | Tâche | Durée | Bloc |
| --- | --- | --- | --- |
| A1 | `data_loading.py` : prix, univers, taux de change, filtre `as_of` | 1 h | S1 |
| A2 | Alignement (jours où tous les actifs hors crypto ont un prix, crypto ramenée à ce calendrier, taux de change reporté en avant), matrice de rendements en CAD à partir de `adj_close`, mise en cache | 2 h | S1 |
| A3 | `metrics.py` : rendement et volatilité annualisés (252 jours), perte maximale datée, durée de récupération. Tests sur des séries calculées à la main | 2 h | S1, S2 |
| A4 | `portfolio.py` : instantané (poids fixes rééquilibrés chaque jour, hypothèse affichée), concentration, exposition aux devises, part défensive, application d'une idée (`pro_rata`, `from_ticker`) | 2 h 30 | S2 |
| A5 | `agent_tools.py` et `evidence.py` : trois outils, preuves avec source, période, devise, transformation, qualificatif par seuil | 3 h | S2, S3 |
| A6 | Test `as_of` : le résultat ne change pas si on supprime les données postérieures | 30 min | S3 |
| A7 | `scripts/run_scenarios.py` : jeu de scénarios fixes (3 personas, 4 idées), tableau des statuts et taux de rejet du validateur | 1 h | S3 |
| A8 (P2) | `diversification.py` : corrélations, poids du plus grand groupe corrélé | 1 h 30 | S4 |
| A9 (P2) | Table ESG minimale, entrée dans `sources.md`, conditions d'utilisation vérifiées | 1 h 30 | S4 |
| A10 | README (dépendances, sources, configuration, reproduction) et documentation technique | 3 h | S5, S6 |

- Terminé quand : les trois outils tournent sur les données réelles pour les trois personas en moins de 2 secondes, les valeurs de Robert et TSLA sont vérifiées à la main dans un carnet, les tests passent.
- Tests : `test_metrics.py`, `test_calendar_alignment.py`, `test_fx_conversion.py`, `test_portfolio.py`, `test_agent_tools.py` (conformité aux contrats), `test_data_loading.py` (`as_of`).
- Sous-agents : `test-writer` (A3, A4, A6), `explorer` (recherche dans les CSV), `debugger` (écarts d'alignement), `security-auditor` avant la PR de A9.

### Flux B : contrats, profils, gouvernance, explication en code

| Élément | Détail |
| --- | --- |
| Branches | `chore/sprint-bootstrap`, puis `feat/profiles-governance`, `feat/explanation-brief-fallback`, `feat/explanation-validator`, `docs/one-pager` |
| Fichiers | `src/alphaforge/contracts.py`, `profiles.py`, `governance.py`, `explanation_brief.py`, `explanation_fallback.py`, `explanation_rendering.py`, `explanation_validator.py`, `src/alphaforge/reference/glossary.json`, `limits.json`, `fixed_texts.json`, `data/external/investor_profiles.json`, `tests/fixtures/` (fichiers initiaux), `requirements.txt`, `.env.example`, tests correspondants, `docs/one_pager.md` |
| Consomme | Fixture `tool_results_robert_tsla.json`, puis les outils de A |
| Livre | Verdict par règle avec marge et contrefactuel, dossier d'explication, gabarit novice et pro, validateur, textes fixes |

| No | Tâche | Durée | Bloc |
| --- | --- | --- | --- |
| B0 | Amorçage : contrats v0, fixtures, `requirements.txt`, `.env.example` (noms de variables seulement), dossiers `app/` et `src/alphaforge/reference/`, `prompts/` | 1 h 30 | S1 |
| B1 | `investor_profiles.json` (3 personas, portefeuilles fictifs, seuils en hypothèses) et `profiles.py` (cases vers règles, contrôle des contradictions) | 2 h | S1 |
| B2 | `governance.py` : statut et marge par règle, pire statut global, "information manquante" si la valeur est absente | 2 h | S2 |
| B3 | `explanation_fallback.py` et `explanation_rendering.py` : gabarits novice et pro, remplacement des renvois par les valeurs du registre. Construit avant le reste de l'explication | 2 h | S2 |
| B4 | `explanation_brief.py` : facteurs classés (gravité, puis marge), glossaire du niveau, limites obligatoires | 1 h 30 | S3 |
| B5 | Contrefactuel : balayage du poids par pas de 1 point avec `simulate_fn`, plus grand poids conforme | 1 h | S3 |
| B6 | `explanation_validator.py` : aucun chiffre hors renvoi (y compris en lettres), renvoi inconnu, termes interdits, règle en tension non citée, longueur | 2 h | S3, S4 |
| B7 | Glossaire, limites et avertissement par niveau (textes fixes) | 1 h | S4 |
| B8 | Intégration des PR, revue avant fusion, puis one pager | 2 h | S4, S5 |

- Terminé quand : `evaluate` rend le verdict attendu pour les trois personas, le gabarit affiche une explication complète sans modèle, le validateur rejette `explainer_output_invalid.json` et accepte les deux sorties valides.
- Tests : `test_profiles.py`, `test_governance.py` (cas limites des seuils, valeur manquante), `test_explanation_brief.py`, `test_explanation_fallback.py`, `test_explanation_validator.py` (un test par code de rejet), `test_contracts.py` (fixtures conformes).
- Sous-agents : `test-writer` (B2, B6), `code-reviewer` avant chaque fusion de fonctionnalité, `security-auditor` avant les fusions qui touchent AWS ou les données.

### Flux C : agents, Bedrock, garde-fou

| Élément | Détail |
| --- | --- |
| Branches | `feat/bedrock-setup`, puis `feat/analysis-pipeline`, `feat/analyst-agent`, `feat/explainer-agent` |
| Fichiers | `src/alphaforge/bedrock_client.py`, `tool_specs.py`, `analyst_agent.py`, `explainer_agent.py`, `analysis_pipeline.py`, `trace_store.py`, `prompts/analyst_v1.md`, `prompts/explainer_v1.md`, `scripts/setup_guardrail.py`, `scripts/check_aws_access.py`, `tests/fixtures/guardrail_prompts.json`, tests correspondants, `docs/aws_setup.md` |
| Consomme | Fixtures (outils bouchons qui relisent `tool_results_robert_tsla.json`), gabarit de B, puis les vrais outils |
| Livre | `run_analysis`, `explain`, `check_request`, garde-fou créé et testé, traces sur S3 |

| No | Tâche | Durée | Bloc |
| --- | --- | --- | --- |
| C1 | Vérification du compte (voir section 7), liste des modèles `ACTIVE`, essai Converse avec un outil, `docs/aws_setup.md` | 1 h 30 | S1 |
| C2 | `scripts/setup_guardrail.py` (idempotent) : sujets refusés (conseil personnalisé, exécution d'ordres, prédiction de rendement), ancrage en mode détection. Jeu de requêtes permises et refusées | 2 h | S1 |
| C3 | `analysis_pipeline.py` en mode `offline` avec outils bouchons : séquence scriptée, gouvernance, dossier, gabarit, trace | 1 h 30 | S2 |
| C4 | `bedrock_client.py` : Converse, parcours de tous les blocs `text`, délai exponentiel sur `ThrottlingException`, `ApplyGuardrail` | 2 h | S2 |
| C5 | `tool_specs.py` et `analyst_agent.py` : boucle d'outils bornée (6 tours, 12 appels), `submit_analysis`, trace construite par le code, repli sur la séquence scriptée | 3 h | S3 |
| C6 | `explainer_agent.py` : un appel sans outil, sortie JSON par emplacement, un nouvel essai après rejet, puis gabarit. Cache (dossier, niveau, modèle, version du prompt) | 2 h 30 | S3, S4 |
| C7 | Contrôle d'ancrage du texte rendu (source = dossier), `trace_store.py` vers S3 privé | 1 h 30 | S4 |
| C8 | Branchement des vrais outils, réglage des prompts sur le jeu de scénarios fixes | 2 h | S4 |

- Terminé quand : `run_analysis(mode="bedrock")` aboutit pour Robert et Amira, la trace montre les outils choisis, l'explicateur passe le validateur sur les scénarios de démo, une requête est refusée et une autre permise par le garde-fou, une trace est lisible sur S3.
- Tests : `test_analysis_pipeline.py` (mode `offline`, sans réseau), `test_analyst_agent.py` et `test_explainer_agent.py` (client Bedrock simulé), `test_bedrock_client.py` (blocs multiples, nouvelle tentative). Les tests n'appellent jamais AWS. Les essais réels passent par `scripts/`.
- Sous-agents : `aws-integration` (C1, C2, C4, C7), `debugger` (boucle d'outils), `security-auditor` avant chaque poussée, `test-writer` (clients simulés).

### Flux D : interface, script de démo, vidéo

| Élément | Détail |
| --- | --- |
| Branches | `feat/streamlit-ui`, puis `feat/ui-explanation-trace`, `docs/demo-script` |
| Fichiers | `app/streamlit_app.py`, `app/components/*.py`, `app/ui_texts.py`, `docs/demo_script.md`, `docs/video_plan.md`, `outputs/figures/` (captures) |
| Consomme | Fixtures `analysis_result_*.json` et `explainer_output_*.json`, puis `run_analysis` et `explain` |
| Livre | Interface locale, script de démo, vidéo |

| No | Tâche | Durée | Bloc |
| --- | --- | --- | --- |
| D1 | Squelette de page, bandeau d'avertissement, bandeau "données d'essai" si `is_fixture`, lecture d'une fixture | 1 h 30 | S1 |
| D2 | Panneau profil : choix du persona, cases et curseurs, rappel "profil fictif" | 2 h | S1 |
| D3 | Radiographie : cartes de métriques, poids, statut par règle (couleur et libellé) | 1 h 30 | S2 |
| D4 | Idée (sélecteurs, idées en un clic) et résultat : avant/après, tensions, contrefactuel, variantes | 3 h | S2, S3 |
| D5 | Explication : bascule novice/pro avec cache en session, un bouton par preuve ouvrant calcul, source, période, devise, limites | 2 h 30 | S3 |
| D6 | Trace à six étapes, étiquettes "agent" et "code", bouton "Ce que l'explicateur a vu" | 1 h 30 | S4 |
| D7 | Panneau de test du garde-fou : requêtes prédéfinies permises et refusées | 1 h | S4 |
| D8 | Panneau "Sources et méthode", finitions | 1 h 30 | S4 |
| D9 | Script de démo (brouillon en S3, final au gel), enregistrement et montage | 4 h | S3, S5, S6 |

- Terminé quand : les scènes 1 à 5 se jouent sans erreur en mode `offline` et en mode `bedrock`, aucun chiffre affiché ne vient d'ailleurs que du registre, l'avertissement est visible sur chaque écran.
- Tests : pas de tests d'interface automatisés. Liste de contrôle manuelle dans `docs/demo_script.md`. La logique reste dans `src/`.
- Sous-agents : `frontend-dev` (D3 à D8), `code-reviewer` avant fusion.

## 5. Intégration

Ordre de fusion à chaque jalon : B, A, C, D. B (ou la personne désignée) relit et fusionne. Une PR en retard ne bloque pas les autres : les suivantes restent sur les fixtures.

| Jalon | Quand | Critère | Repli si en retard |
| --- | --- | --- | --- |
| J0 | H+1,5 (samedi 16 h) | `chore/sprint-bootstrap` fusionnée, identité AWS et modèles vérifiés | Si AWS est inaccessible : avertir un mentor, C avance avec le client simulé |
| J1 | H+6 (samedi 20 h 30) | Contrats gelés, garde-fou créé, un test vert par flux | Garde-fou reporté à S3 au plus tard |
| J2 | H+9 (samedi 23 h 30) | Bout en bout avec bouchons : l'interface affiche Robert et TSLA via `run_analysis(mode="offline")` | D lit directement la fixture, branchement à S3 |
| J3 | H+20 (dimanche 10 h 30) | Données réelles en mode `offline` : vrais outils, gouvernance, gabarit. Chiffres de Robert et d'Amira relus | Sans contrefactuel : afficher seulement la marge |
| J4 | H+24 (dimanche 14 h 30) | Bedrock de bout en bout : analyste, explicateur, validateur, scores du garde-fou, trace S3 | Analyste instable : séquence scriptée et explicateur seul sur Bedrock. Explicateur instable : gabarit et analyste seul sur Bedrock. Les deux instables : mode `offline`, le garde-fou reste la partie AWS démontrée |
| J5 | H+28 (dimanche 18 h 30) | Gel des fonctionnalités. Jeu de scénarios fixes exécuté, textes mis en cache, P2 fusionné ou abandonné | Tout P2 non fusionné est abandonné |
| J6 | H+29 à H+32 (dimanche soir) | Vidéo enregistrée, captures de la console AWS (garde-fou, S3), copie de quelques traces dans `outputs/reports/` | Reprise en S6 |
| Remise du code | Dimanche avant 23 h 59 | `main` contient l'application finale, README à jour (dépôt GitHub officiel) | Livrer l'état du dernier jalon atteint |
| J7 | H+41 à H+46,5 (lundi, avant 13 h) | Reprise éventuelle de la vidéo, one pager et documentation technique finaux (remise à 14 h). Aucun changement de code | Sans objet |

Après J5 : corrections de bogues seulement, chacune dans une branche `fix/...`.

## 6. Dépendances et environnement

`requirements.txt` créé par B à l'heure 0. Fourchettes de départ, à remplacer par les versions exactes installées (`pip freeze`) avant J0 :

```
pandas>=2.2,<3
numpy>=1.26,<3
boto3>=1.35
streamlit>=1.40,<2
pytest>=8
# seulement pour scripts/build_dataset.py (ne pas relancer) :
yfinance
```

- Même version mineure de Python pour tous (3.11 ou plus), à confirmer à l'heure 0.
- Variables d'environnement (noms dans `.env.example`, valeurs jamais versionnées) : `AWS_REGION`, `ALPHAFORGE_MODE`, `ALPHAFORGE_ANALYST_MODEL_ID`, `ALPHAFORGE_EXPLAINER_MODEL_ID`, `ALPHAFORGE_GUARDRAIL_ID`, `ALPHAFORGE_GUARDRAIL_VERSION`, `ALPHAFORGE_TRACE_BUCKET`.
- Interface : Streamlit et textes en français, par défaut. Raisons : tout en Python (pas de chaîne JavaScript), état de session adapté à la bascule de niveau, lancement local avec la chaîne d'identifiants de boto3, option présentée par l'atelier. Le français suit la règle 4 du projet.
- Le dossier racine `app/` est nouveau : A l'ajoute à la section "Structure" du `README.md` (règle 5).

## 7. AWS

| Quand | Qui | Action |
| --- | --- | --- |
| H0 à H+1 | C | `aws sts get-caller-identity` et `aws configure list` : vérifier le compte et `us-east-1` |
| H0 à H+1,5 | C | Lister les modèles `ACTIVE` et les profils d'inférence, choisir un modèle peu coûteux qui prend en charge les appels d'outils avec Converse, faire un essai réel. Aucun identifiant de modèle n'est codé en dur |
| H+1,5 à H+4 | C | Créer le garde-fou par script, tester requêtes permises et refusées, vérifier le contrôle d'ancrage en français |
| S2 | C | Créer le compartiment S3 privé des traces (les quatre options Block Public Access activées) |
| J4 | C, D | D vérifie Bedrock depuis le poste de démo avec ses propres identifiants temporaires |
| J6 | C | Captures de la console, copie des traces utiles dans le dépôt. Le compte est jetable : rien ne doit exister seulement sur AWS |

- Ressources partagées : C est la seule personne qui crée ou modifie des ressources. Préfixe `alphaforge-`. Inventaire dans `docs/aws_setup.md` (nom, rôle, script de création), sans identifiant de compte ni secret.
- Identifiants : uniquement les trois valeurs temporaires de Workshop Studio, collées dans un terminal dédié. Chacun récupère les siennes sur la page de l'atelier. Jamais dans le dépôt, le clavardage, un prompt, une capture ou la vidéo. Pas de `aws login`, pas de clé IAM permanente.
- Quotas partagés : tours et appels bornés, cache des explications, pas de boucle de tests contre Bedrock. Les tests automatisés utilisent un client simulé.
- Garde-fou sur l'analyste : commencer par `ApplyGuardrail` sur les requêtes et sur le texte rendu. N'attacher le garde-fou aux appels Converse de l'analyste que si les essais ne montrent pas de faux refus sur les résultats d'outils.
- Les interventions et les scores du garde-fou sont affichés à l'étape 6 de la trace.

## 8. Explicabilité, simulation et données

- Aucun chiffre ne vient d'un modèle : les outils calculent, le registre numérote, l'explicateur écrit des renvois, le code insère les valeurs.
- Chaque preuve porte source, période, devise, transformation, nombre d'observations et limites. C'est ce que montre le clic sur un chiffre.
- Le verdict vient du code. L'explicateur ne peut ni le changer ni recommander.
- La trace est construite par le code à partir des appels réels. Le raisonnement interne des modèles n'est pas affiché.
- Avertissement (simulation, éducatif, pas de conseil personnalisé) et limites : textes fixes affichés par le code. Faits, hypothèses (seuils, portefeuilles fictifs, rééquilibrage) et variantes simulées sont séparés à l'écran.
- Aucun outil de passage d'ordres, aucune connexion à un courtier. Profils, portefeuilles et montants sont fictifs et étiquetés.
- Rendements historiques décrits sur une période explicite, jamais projetés. Formule imposée : "perte historique observée sur telle période, appliquée au capital fictif".
- Données : `adj_close` pour les rendements, conversion en CAD, alignement documenté, biais du survivant affiché en limite. Toute source ajoutée (ESG) a son entrée dans `data/external/sources.md` avec ses conditions d'utilisation.

## 9. Risques propres au sprint

| Risque | Mesure |
| --- | --- |
| Contrats instables après H+6 | Gel strict, ajouts facultatifs seulement, un seul propriétaire |
| Intégration tardive | Mode `offline` de bout en bout dès J2, fusion à chaque jalon |
| Appels d'outils peu fiables avec le modèle choisi | Essai réel à l'heure 1, séquence scriptée en repli, schémas d'outils courts |
| Taux de rejet élevé du validateur | Mesure sur le jeu fixe à J4, correction du prompt, gabarit en repli |
| Ancrage trop strict en français | Mode détection, scores affichés sans blocage, glossaire dans le dossier |
| Expiration ou limitation du compte avant la vidéo | Vidéo dimanche soir, captures et traces copiées, démo possible en mode `offline` |
| Jetons temporaires expirés en pleine démo | Renouveler juste avant l'enregistrement, textes en cache |
| Flux B surchargé | A reprend B5 ou B7 dès que A5 est terminé |
| Chiffres inventés des fixtures dans la vidéo | Bandeau "données d'essai", contrôle dans la liste de la démo |
| Conflits de fusion | Un propriétaire par fichier, squash, nouvelle branche après chaque fusion |
| Dérive vers P2 | P2 seulement si J4 est vert, abandon automatique à J5 |
| Secret poussé par fatigue | `security-auditor` et lecture du diff avant chaque poussée, `.env` ignoré par Git |
| Indisponibilité d'une personne lundi matin | Tout l'essentiel est terminé dimanche soir, S6 n'est qu'une réserve |

## 10. Questions ouvertes

1. Réglée : code et application dimanche 23 h 59, vidéo et documents lundi 14 h (voir section 1).
2. Réglée : A Naoufal, B Samer, C Godwin, D Ibrahima (voir section 4).
3. Streamlit et interface en français : confirmés ? Langue de la vidéo ?
4. Panneau de test du garde-fou : requêtes prédéfinies seulement (par défaut), ou un champ de texte limité à ce panneau ?
5. Dossier racine `app/` accepté ?
6. Seuils des trois personas : qui les valide avant J3 ?
7. Tout le monde est-il disponible lundi matin pour la réserve ?
