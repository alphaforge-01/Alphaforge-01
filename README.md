# AlphaForge AI : un copilote de cohérence, pas un conseiller

Projet de l'équipe AlphaForge 01 pour le datathon PolyFinances AlphaForge AI 2026 (Banque Nationale et AWS).

> **Simulation éducative uniquement.** Profils, portefeuilles et montants sont fictifs. Aucune transaction réelle, aucune connexion à un courtier, aucun conseil financier personnalisé. Les résultats décrivent le passé sur une période explicite et ne prévoient rien.

## Ce que fait l'outil

Question servie : **« Mon portefeuille fictif correspond-il à mon profil, et que change mon idée de placement ? »**

1. L'utilisateur choisit un profil fictif (Amira, Mateo, Robert, ou un profil construit par cases).
2. Il voit la **radiographie** du portefeuille fictif : volatilité, perte maximale historique, concentration, exposition aux devises, part défensive.
3. Il soumet une **idée** (par exemple « porter TSLA à 25 % du portefeuille »).
4. Le système simule l'avant/après, applique les **règles du profil** (conforme, tension, conflit, information manquante), donne le **contrefactuel** (« conforme à X % ou moins ») et des **variantes** simulées.
5. Un **agent explicateur** rédige l'explication en niveau novice ou pro ; chaque chiffre renvoie à une **preuve** (source, période, devise, transformation, limites) que l'on peut ouvrir.

Même demande, profils différents, verdicts différents : avec 25 % de TSLA, Robert ressort en **conflit** (concentration), Amira en **tension** (perte maximale).

## Démarrage rapide

Prérequis : Python 3.11 ou plus récent, Git. Toutes les commandes se lancent depuis la racine du projet.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS / Linux

.venv/Scripts/python -m pytest -q                  # tests, sans aucun appel AWS
.venv/Scripts/streamlit run app/streamlit_app.py   # interface locale
```

L'interface s'ouvre sur `http://127.0.0.1:8501`. La configuration `.streamlit/config.toml` limite l'écoute à 127.0.0.1 et masque les traces Python.

## Modes d'exécution

La variable `ALPHAFORGE_MODE` choisit le mode de départ de l'interface (modifiable ensuite dans l'interface) :

| Mode | Données | Agents | AWS | Usage |
| --- | --- | --- | --- | --- |
| `fixture` (défaut de l'interface) | Fichiers de `tests/fixtures/`, chiffres inventés, bandeau « données d'essai » | Aucun | Non | Développement de l'interface |
| `offline` | Données réelles de `data/raw/` | Séquence d'outils fixe, explication par gabarit | Non | Démo sans réseau, repli de secours |
| `bedrock` | Données réelles | Agent analyste et agent explicateur sur Amazon Bedrock, garde-fou Bedrock | Oui | Démo complète |

En mode `bedrock`, toute erreur d'agent ou de configuration bascule sur le repli hors ligne, et la trace l'indique : l'application ne plante pas.

## Configuration AWS (mode `bedrock`)

Le compte AWS est un compte temporaire Workshop Studio partagé par l'équipe, région `us-east-1`. **Aucun identifiant ne doit entrer dans le dépôt** : les valeurs vivent dans un terminal dédié ou dans un `.env` ignoré par Git. Les noms des variables sont dans `.env.example` :

| Variable | Rôle |
| --- | --- |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Identifiants temporaires de Workshop Studio (les trois ensemble) |
| `AWS_REGION` | `us-east-1` |
| `ALPHAFORGE_MODE` | `fixture`, `offline` ou `bedrock` |
| `ALPHAFORGE_ANALYST_MODEL_ID`, `ALPHAFORGE_EXPLAINER_MODEL_ID` | Modèle ou profil d'inférence Bedrock vérifié dans le compte |
| `ALPHAFORGE_GUARDRAIL_ID`, `ALPHAFORGE_GUARDRAIL_VERSION` | Garde-fou créé par `scripts/setup_guardrail.py --apply` |
| `ALPHAFORGE_TRACE_BUCKET` | Compartiment S3 privé des traces (facultatif) |

Ordre des opérations (détail dans [docs/aws_setup.md](docs/aws_setup.md)) :

```bash
aws sts get-caller-identity                                  # vérifier le compte et la région
.venv/Scripts/python scripts/check_aws_access.py             # modèles ACTIVE, lecture seule
.venv/Scripts/python scripts/check_aws_access.py --skip-listing --try-converse <modele>
.venv/Scripts/python scripts/setup_guardrail.py              # simulation, aucun appel AWS
.venv/Scripts/python scripts/setup_guardrail.py --apply      # création du garde-fou (responsable du flux C)
.venv/Scripts/python scripts/setup_guardrail.py --test       # requêtes permises et refusées
.venv/Scripts/python scripts/setup_trace_bucket.py --check   # compartiment S3 privé des traces (--apply pour le créer)
.venv/Scripts/python scripts/try_bedrock_run.py              # plan et configuration, sans appel
.venv/Scripts/python scripts/try_bedrock_run.py --run --personas robert   # essai réel de bout en bout
```

En mode `bedrock`, un texte rédigé par le modèle n'est affiché que si le garde-fou l'a vérifié ; sinon l'interface affiche l'explication du gabarit construite par le code, et la trace dit pourquoi.

## Reproduire les résultats

```bash
.venv/Scripts/python -m pytest -q -W error                   # plus de 1 000 tests, sans AWS
.venv/Scripts/python scripts/run_scenarios.py                # 3 personas x 4 demandes fictives, hors ligne
.venv/Scripts/python scripts/run_scenarios.py --mode bedrock --persona robert   # agents réels (quotas partagés)
```

`run_scenarios.py` écrit un rapport dans `outputs/reports/scenarios/` (ignoré par Git) : verdicts, contrefactuels, variantes, textes d'explication et taux de rejet du validateur.

Résultat hors ligne de référence (verdict après la demande, données jusqu'au 12 novembre 2026) :

| Profil | TSLA 25 % | BTC-USD 20 % | NVDA 20 % | XOM 10 % |
| --- | --- | --- | --- | --- |
| Robert | conflit | conflit | tension | conforme |
| Amira | tension | tension | tension | conforme |
| Mateo | information manquante | conflit | information manquante | information manquante |

Mateo est en « information manquante » dès son portefeuille de départ : sa règle d'exclusion ESG (R7) exige des preuves ESG, qui ne sont pas encore intégrées. Le système refuse donc de le déclarer conforme plutôt que de passer l'ESG sous silence. Avec 20 % de BTC-USD, le conflit sur les cryptoactifs exclus l'emporte.

Les données de départ ne sont **pas** retéléchargées : `scripts/build_dataset.py` reconstruirait `data/raw/` depuis Yahoo Finance, la Banque du Canada et la FRED, mais `adj_close` est rétro-ajusté à chaque téléchargement et les résultats changeraient. Ne le relancer que volontairement.

## Données et sources

| Source | Contenu | Fichier | Conditions |
| --- | --- | --- | --- |
| Yahoo Finance (via `yfinance`) | Prix quotidiens, clôture ajustée, dividendes et fractionnements, 31 actifs | `data/raw/prices_daily.csv`, `corporate_actions.csv` | Conditions Yahoo, données non certifiées |
| Banque du Canada (API Valet) | Taux USD/CAD quotidien, taux et IPC canadiens | `data/raw/fx_usdcad_daily.csv`, `macro_rates.csv` | Conditions de la Banque du Canada |
| FRED (Federal Reserve Bank of St. Louis) | Taux, IPC et chômage américains | `data/raw/macro_rates.csv` | Conditions de la FRED, valeurs révisées |
| Équipe (fictif) | Personas, portefeuilles et seuils des règles | `data/external/investor_profiles.json` | Contenu original, hypothèses de l'équipe |

Période : du 12 novembre 2021 au 12 novembre 2026 (extraction du 13 novembre 2026). Provenance et limites détaillées : [data/raw/README.md](data/raw/README.md), [data/raw/sources_metadata.csv](data/raw/sources_metadata.csv), [docs/data_review.md](docs/data_review.md), [data/external/sources.md](data/external/sources.md).

**Traitements et hypothèses** (affichés comme tels dans l'outil) :

- rendements calculés sur `adj_close` (dividendes et fractionnements inclus), convertis en CAD au taux USD/CAD de la Banque du Canada du **même jour** (dernier taux connu les jours fériés, au plus 4 jours) ;
- calendrier commun : seulement les jours où la TSX et les marchés américains sont tous deux ouverts (1 228 jours, aucun prix inventé) ; crypto ramenée à ce calendrier ;
- portefeuilles à **poids fixes rééquilibrés chaque jour** ; **part défensive = obligations + or** ;
- volatilité et rendement annualisés sur 252 jours ; perte maximale en fraction positive avec ses dates ; pas de rendement annualisé sous un an de données ;
- paramètre `as_of` : aucune donnée postérieure à la date d'analyse n'est lue (vérifié par `tests/test_as_of_invariance.py` sur des copies tronquées des données).

## Architecture

```
Interface Streamlit (app/)
        |
        v
analysis_pipeline.run_analysis / explain
        |
  1. Agent analyste (Bedrock, outils, tours bornés)  ou séquence fixe hors ligne
        |   analyze_portfolio, simulate_portfolio_change, get_asset_facts
        v
  2. Gouvernance (code) : statut et marge par règle, contrefactuel
  3. Registre de preuves et dossier d'explication (code)
  4. Agent explicateur (Bedrock, sans outil, dossier seul)  ou gabarit
  5. Validateur (code) : aucun chiffre hors registre, aucune recommandation ni prévision
  6. Garde-fou Bedrock : sujets refusés, ancrage contextuel  ->  trace (S3 privé facultatif)
```

Les calculs sont faits par du **code déterministe testé** ; aucun modèle ne calcule un chiffre ni ne décide d'un verdict. Le modèle explicateur n'écrit que des renvois (`[E3]`), remplacés par la valeur du registre.

| Flux | Responsable | Modules |
| --- | --- | --- |
| A : données, métriques, outils | Naoufal | `data_loading.py`, `calendar_alignment.py`, `fx_conversion.py`, `metrics.py`, `portfolio.py`, `agent_tools.py`, `evidence.py`, `scripts/run_scenarios.py` |
| B : profils, gouvernance, explication en code | Samer | `contracts.py`, `profiles.py`, `governance.py`, `counterfactual.py`, `explanation_*.py`, `reference_texts.py`, `reference/` |
| C : agents, Bedrock, garde-fou | Godwin | `analysis_pipeline.py`, `analyst_agent.py`, `explainer_agent.py`, `bedrock_client.py`, `tool_specs.py`, `trace_store.py`, `prompts/`, scripts AWS |
| D : interface, démo | Ibrahima | `app/` |

## Structure du dépôt

```
data/
  raw/            Données de départ des organisateurs (lecture seule)
  external/       Données ajoutées par l'équipe (source, date, traitement documentés)
  processed/      Données générées par le code (non versionnées)
app/              Interface Streamlit (flux D), textes en français
src/alphaforge/   Package Python : données, métriques, portefeuille, outils, gouvernance, explication, agents
prompts/          Prompts versionnés des agents
scripts/          Scripts en ligne de commande (scénarios, vérification AWS, garde-fou, reconstruction des données)
notebooks/        Exploration (les vérifications manuelles personnelles sont ignorées par Git)
outputs/          Figures et rapports générés
docs/             Documentation : cas d'usage, plan, user stories, clés de preuves, AWS, interface, one pager
tests/            Tests automatisés (aucun appel AWS)
```

## Documentation

- [docs/technical_documentation.md](docs/technical_documentation.md) : **documentation technique** (méthodes, données, explicabilité avec un exemple relié à la trace, validations, limites).
- [docs/use_case_decision.md](docs/use_case_decision.md) : cas d'usage retenu et architecture.
- [docs/user_stories.md](docs/user_stories.md) : user stories du MVP et critères d'acceptation.
- [docs/evidence_keys.md](docs/evidence_keys.md) : preuves produites (clés, unités, sources, limites).
- [docs/aws_setup.md](docs/aws_setup.md) : mise en place AWS, garde-fou, permissions.
- [docs/ui_spec.md](docs/ui_spec.md) : spécification de l'interface.
- [docs/data_review.md](docs/data_review.md) : revue des données et sources complémentaires.
- [docs/one_pager.md](docs/one_pager.md) : résumé d'une page.
- [docs/sprint_plan.md](docs/sprint_plan.md) : organisation du travail.

## Limites

- **Biais du survivant** : l'univers de 31 actifs a été choisi en 2026 parmi des noms importants aujourd'hui.
- **Historique court** : cinq ans, un seul épisode de baisse marquée (2022). La volatilité est un indicateur de risque parmi d'autres.
- **Seuils des règles** : hypothèses de l'équipe, pas des normes réglementaires.
- **ESG** : aucune donnée ESG n'est intégrée. Pour un profil à forte préférence ESG (Mateo), la règle d'exclusion ESG rend « information manquante » au lieu d'un faux « conforme ». Pour les autres profils, un verdict « conforme » ne dit rien de l'ESG.
- **Groupe corrélé (Amira)** : seuil de corrélation de 0,80 choisi après examen des données, mesure très sensible à la fenêtre de dates (détail dans `docs/technical_documentation.md`).
- **Concentration en actions individuelles (R6)** : la règle compte les actions détenues directement, pas les FNB d'actions.
- **Données publiques gratuites**, non certifiées ; valeurs FRED révisées.
- Le garde-fou Bedrock complète les contrôles du code mais ne prouve pas l'exactitude factuelle.
