# AlphaForge AI : un copilote de cohérence, pas un conseiller

Projet de l'équipe AlphaForge 01 pour le datathon PolyFinances AlphaForge AI 2026 (Banque Nationale et AWS).

> **Simulation éducative uniquement.** Profils, portefeuilles et montants sont fictifs. Aucune transaction réelle, aucune connexion à un courtier, aucun conseil financier personnalisé. Les résultats décrivent le passé sur une période explicite et ne prévoient rien.

## Ce que fait l'outil

Question servie : **« Mon portefeuille fictif correspond-il à mon profil, et que change mon idée de placement ? »**

1. L'utilisateur choisit un profil fictif (Amira, Mateo, Robert, ou un profil construit par cases et curseurs, sans aucune donnée personnelle).
2. Il voit la **radiographie** du portefeuille fictif : volatilité, perte maximale historique, concentration, exposition aux devises, part défensive.
3. Il soumet une **idée**, en une phrase (« porter TSLA à 25 % ») ou par les boutons et réglages. La phrase est traduite par des règles déterministes, sans modèle de langage : une demande ambiguë reçoit une question, une demande interdite (ordre, conseil personnalisé, prédiction) est refusée.
4. Le système simule l'avant/après, applique les **règles du profil** (conforme, tension, conflit, information manquante), donne le **contrefactuel** (« conforme à X % ou moins ») et des **variantes** simulées.
5. Un **agent explicateur** rédige l'explication en niveau novice ou pro ; chaque chiffre renvoie à une **preuve** (source, période, devise, transformation, limites) que l'on peut ouvrir.

Même demande, profils différents, verdicts différents : avec 25 % de TSLA, Robert ressort en **conflit** (concentration par actif), Amira en **tension** (perte maximale historique).

L'interface compte cinq pages : Accueil, Simulation, Créer un profil fictif, Test du garde-fou, Sources et méthode.

## Démarrage rapide

Prérequis : Python 3.11 ou plus récent, Git. Toutes les commandes se lancent depuis la racine du projet.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS / Linux

.venv/Scripts/python -m pytest -q                  # tests, sans aucun appel AWS
.venv/Scripts/streamlit run app/streamlit_app.py   # interface locale, mode hors ligne par défaut
```

L'interface s'ouvre sur `http://127.0.0.1:8501`. La configuration `.streamlit/config.toml` limite l'écoute à 127.0.0.1 et masque les traces Python. Sans aucune configuration, elle démarre en mode `offline` : données réelles, aucun appel AWS.

## Modes d'exécution

La variable `ALPHAFORGE_MODE` choisit le mode de départ de l'interface (modifiable ensuite dans l'interface) :

| Mode | Données | Agents | AWS | Usage |
| --- | --- | --- | --- | --- |
| `offline` (défaut) | Données réelles de `data/raw/` | Séquence d'outils fixe, explication par gabarit | Non | Démo sans réseau, repli de secours |
| `bedrock` | Données réelles | Agent analyste et agent explicateur sur Amazon Bedrock, garde-fou Bedrock | Oui | Démo complète |
| `fixture` | Fichiers de `tests/fixtures/`, chiffres inventés, bandeau « données d'essai » | Aucun | Non | Développement de l'interface |

En mode `bedrock`, toute erreur d'agent ou de configuration bascule sur le repli hors ligne, et la trace l'indique : l'application ne plante pas.

## Configuration AWS (mode `bedrock`)

Le compte AWS est un compte temporaire Workshop Studio partagé par l'équipe, région `us-east-1`. **Aucun identifiant ne doit entrer dans le dépôt** : les valeurs vivent dans un terminal dédié ou dans un `.env` ignoré par Git. Les noms des variables sont dans `.env.example` :

| Variable | Rôle |
| --- | --- |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Identifiants temporaires de Workshop Studio (les trois ensemble, jamais dans le dépôt) |
| `AWS_REGION` | `us-east-1` |
| `ALPHAFORGE_MODE` | `offline`, `bedrock` ou `fixture` |
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
bash scripts/run_app_bedrock.sh                              # interface en mode bedrock (macOS, Linux, CloudShell)
```

`run_app_bedrock.sh` charge le `.env`, vérifie les réglages et la connexion AWS sans afficher aucune valeur, puis lance l'interface sur 127.0.0.1. Sous Windows, définir `ALPHAFORGE_MODE=bedrock` dans le terminal et lancer Streamlit comme dans le démarrage rapide.

En mode `bedrock`, un texte rédigé par le modèle n'est affiché que si le garde-fou l'a vérifié. Le contrôle d'ancrage compare les phrases du modèle à une source rédigée en phrases françaises à partir du seul dossier d'explication (`grounding_source.py`). Sous le plancher de 0,3, ou si le garde-fou intervient ou échoue, l'interface affiche l'explication du gabarit construite par le code, et la trace dit pourquoi. Mesures et méthode : [docs/grounding_diagnosis.md](docs/grounding_diagnosis.md).

## Reproduire les résultats

```bash
.venv/Scripts/python -m pytest -q -W error                   # plus de 2 200 tests, sans AWS
.venv/Scripts/python scripts/run_scenarios.py                # 3 personas x les 5 boutons de l'interface, hors ligne
.venv/Scripts/python scripts/run_sensitivity.py              # mise à l'épreuve des hypothèses, hors ligne
.venv/Scripts/python scripts/run_scenarios.py --mode bedrock --persona robert   # agents réels (quotas partagés)
```

Pour tout revérifier comme le jury, à partir de GitHub seulement : `.venv/Scripts/python scripts/check_clean_clone.py`. Le script clone `main` dans un dossier vide, installe `requirements.txt` dans un environnement neuf, lance les tests, les scénarios, la sensibilité (rapport identique octet pour octet au rapport versionné) et l'interface sans navigateur, et contrôle l'absence de secrets, de tirets cadratins et de fichiers interdits à la racine.

`run_scenarios.py` écrit un rapport dans `outputs/reports/scenarios/` (ignoré par Git) : verdicts global, financier et ESG, contrefactuels, variantes, textes d'explication et taux de rejet du validateur.

Résultat hors ligne de référence : verdict affiché après la demande, financement au prorata, données jusqu'au 12 novembre 2026.

| Profil | TSLA 25 % | NVDA 15 % | BTC-USD 10 % | BTC-USD 40 % | XOM 15 % |
| --- | --- | --- | --- | --- | --- |
| Robert | conflit | conforme | conflit | conflit | conforme |
| Amira | tension | conforme (sans effet) | conforme (sans effet) | conflit | conforme |
| Mateo | information manquante | information manquante | conflit | conflit | information manquante |

- **Robert** : TSLA 25 % dépasse sa limite de concentration par actif (25 % pour 22 %) ; tout cryptoactif est exclu de son profil.
- **Amira** : TSLA 25 % met sa perte maximale historique en tension ; à 40 %, le cryptoactif dépasse sa limite. « Sans effet » : son portefeuille fictif détient déjà 15 % de NVDA et 10 % de BTC-USD.
- **Mateo** : sa règle d'exclusion ESG (R7) exige des preuves ESG, qui ne sont pas intégrées. Le système la laisse en « information manquante » plutôt que de la déclarer conforme. Son **verdict financier**, calculé à part, est conforme pour TSLA 25 %, NVDA 15 % et XOM 15 %, et en conflit pour les deux demandes en cryptoactif, exclu de son profil.

### Mise à l'épreuve des hypothèses

`scripts/run_sensitivity.py` refait la gouvernance en changeant **un seul choix à la fois** : fenêtre de 3 ans ou 1 an, devise locale au lieu du CAD, données arrêtées en 2024 ou 2025, rendements hebdomadaires, seuils 20 % plus stricts ou plus souples, et cinq blocs annuels disjoints. Rapport versionné : [outputs/reports/sensitivity.md](outputs/reports/sensitivity.md).

- Le conflit de Robert avec TSLA 25 % tient dans les 6 variantes de données ; il ne devient « tension » qu'avec des seuils 20 % plus souples.
- **Les seuils sont l'hypothèse la plus sensible** : 7 cas sur 15 changent de verdict financier avec des seuils plus stricts, 2 avec des seuils plus souples.
- Les fenêtres de 3 ans et 1 an et les rendements hebdomadaires ne changent aucun verdict financier ; la devise locale en change 4.

Les données de départ ne sont **pas** retéléchargées : `scripts/build_dataset.py` reconstruirait `data/raw/` depuis Yahoo Finance, la Banque du Canada et la FRED, mais `adj_close` est rétro-ajusté à chaque téléchargement et les résultats changeraient. Ne le relancer que volontairement.

## Données et sources

| Source | Contenu | Fichier | Conditions |
| --- | --- | --- | --- |
| Yahoo Finance (via `yfinance`) | Prix quotidiens, clôture ajustée, dividendes et fractionnements, 31 actifs | `data/raw/prices_daily.csv`, `corporate_actions.csv` | Conditions Yahoo, données non certifiées |
| Banque du Canada (API Valet) | Taux USD/CAD quotidien, taux et IPC canadiens | `data/raw/fx_usdcad_daily.csv`, `macro_rates.csv` | Conditions de la Banque du Canada |
| FRED (Federal Reserve Bank of St. Louis) | Taux, IPC et chômage américains | `data/raw/macro_rates.csv` | Conditions de la FRED, valeurs révisées |
| Équipe (fictif) | Personas, portefeuilles et seuils des règles | `data/external/investor_profiles.json` | Contenu original, hypothèses de l'équipe |

Période : du 12 novembre 2021 au 12 novembre 2026 (extraction du 13 novembre 2026). Provenance et limites détaillées : [data/raw/README.md](data/raw/README.md), [data/raw/sources_metadata.csv](data/raw/sources_metadata.csv), [docs/data_review.md](docs/data_review.md), [data/external/sources.md](data/external/sources.md).

**Données Yahoo Finance dans le dépôt.** Les fichiers de `data/raw/` sont le jeu de départ fourni par les organisateurs du datathon. Ils restent dans le dépôt, qui est **privé** et dont l'accès est donné au jury : retirer ces fichiers empêcherait de reproduire les résultats, puisqu'un nouveau téléchargement change les prix ajustés. Si le dépôt devenait public, il faudrait d'abord retirer les prix Yahoo (`prices_daily.csv`, `corporate_actions.csv`) et ne garder que `scripts/build_dataset.py`, sauf accord écrit des organisateurs.

**Traitements et hypothèses** (affichés comme tels dans l'outil) :

- rendements calculés sur `adj_close` (dividendes et fractionnements inclus), convertis en CAD au taux USD/CAD de la Banque du Canada du **même jour** (dernier taux connu les jours fériés, au plus 4 jours) ;
- calendrier commun : seulement les jours où la TSX et les marchés américains sont tous deux ouverts (1 228 jours, aucun prix inventé) ; crypto ramenée à ce calendrier ;
- portefeuilles à **poids fixes rééquilibrés chaque jour** ; **part défensive = obligations + or** ;
- volatilité et rendement annualisés sur 252 jours ; perte maximale en fraction positive avec ses dates ; **aucune volatilité annualisée sous 60 rendements** (l'outil rend alors « information manquante ») et aucun rendement annualisé sous un an de données ;
- libellés des classes d'actifs, secteurs et devises traduits en français (`asset_labels.py`), clés de preuve inchangées ;
- paramètre `as_of` : aucune donnée postérieure à la date d'analyse n'est lue (vérifié par `tests/test_as_of_invariance.py` sur des copies tronquées des données).

## Architecture

```
Interface Streamlit (app/), 5 pages
        |
        v
analysis_pipeline.run_analysis / explain
        |
  1. Agent analyste (Bedrock, outils, tours bornés)  ou séquence fixe hors ligne
        |   analyze_portfolio, simulate_portfolio_change, get_asset_facts
        v
  2. Gouvernance (code) : statut et marge par règle, contrefactuel, verdicts financier et ESG séparés
  3. Registre de preuves et dossier d'explication (code)
  4. Agent explicateur (Bedrock, sans outil, dossier seul, prompt explainer_v5)  ou gabarit
  5. Validateur (code) : aucun chiffre hors registre, aucune recommandation ni prévision, aucun lien ni HTML
  6. Garde-fou Bedrock : sujets refusés, ancrage contre la source en phrases  ->  trace (S3 privé facultatif)
```

Les calculs sont faits par du **code déterministe testé** ; aucun modèle ne calcule un chiffre ni ne décide d'un verdict. Le modèle explicateur n'écrit que des renvois (`[E3]`), remplacés par la valeur du registre ; le contrefactuel est écrit par le code.

| Flux | Responsable | Modules |
| --- | --- | --- |
| A : données, métriques, outils | Naoufal | `data_loading.py`, `calendar_alignment.py`, `fx_conversion.py`, `metrics.py`, `portfolio.py`, `agent_tools.py`, `evidence.py`, `asset_labels.py`, `sensitivity.py`, `scripts/run_scenarios.py`, `scripts/run_sensitivity.py` |
| B : profils, gouvernance, explication en code | Samer | `contracts.py`, `profiles.py`, `governance.py`, `counterfactual.py`, `explanation_*.py`, `reference_texts.py`, `reference/` |
| C : agents, Bedrock, garde-fou | Godwin | `analysis_pipeline.py`, `analyst_agent.py`, `explainer_agent.py`, `bedrock_client.py`, `tool_specs.py`, `trace_store.py`, `pipeline_deps.py`, `prompt_loader.py`, `prompts/`, scripts AWS |
| D : interface, démo, diversification | Ibrahima | `app/`, `request_parsing.py`, `diversification.py`, `grounding_source.py`, `scripts/diagnose_grounding.py`, `scripts/run_app_bedrock.sh` |

## Structure du dépôt

```
data/
  raw/            Données de départ des organisateurs (lecture seule)
  external/       Données ajoutées par l'équipe (source, date, traitement documentés)
  processed/      Données générées par le code (non versionnées)
app/              Interface Streamlit (flux D), textes en français
src/alphaforge/   Package Python : données, métriques, portefeuille, outils, gouvernance, explication, agents
prompts/          Prompts versionnés des agents
scripts/          Scripts en ligne de commande (scénarios, sensibilité, vérification AWS, garde-fou, reconstruction des données)
notebooks/        Exploration (les vérifications manuelles personnelles sont ignorées par Git)
outputs/          Figures et rapports générés : traces réelles du mode bedrock, rapport de sensibilité
docs/             Documentation : cas d'usage, plan, user stories, clés de preuves, AWS, interface, ancrage, one pager
tests/            Tests automatisés (aucun appel AWS)
```

## Documentation

- [docs/technical_documentation.md](docs/technical_documentation.md) : **documentation technique** (méthodes, données, explicabilité avec un exemple relié à la trace, validations, limites).
- [outputs/reports/sensitivity.md](outputs/reports/sensitivity.md) : mise à l'épreuve des hypothèses.
- [outputs/reports/demo_traces/README.md](outputs/reports/demo_traces/README.md) : traces réelles du mode `bedrock`.
- [docs/use_case_decision.md](docs/use_case_decision.md) : cas d'usage retenu et architecture.
- [docs/user_stories.md](docs/user_stories.md) : user stories du MVP et critères d'acceptation.
- [docs/evidence_keys.md](docs/evidence_keys.md) : preuves produites (clés, unités, sources, limites).
- [docs/aws_setup.md](docs/aws_setup.md) : mise en place AWS, garde-fou, permissions.
- [docs/grounding_diagnosis.md](docs/grounding_diagnosis.md) : diagnostic et mesures du contrôle d'ancrage.
- [docs/ui_spec.md](docs/ui_spec.md) : spécification de l'interface.
- [docs/data_review.md](docs/data_review.md) : revue des données et sources complémentaires.
- [docs/one_pager.md](docs/one_pager.md) : résumé d'une page.
- [docs/sprint_plan.md](docs/sprint_plan.md) et [docs/final_day_plan.md](docs/final_day_plan.md) : organisation du travail.

## Limites

- **Biais du survivant** : l'univers de 31 actifs a été choisi en 2026 parmi des noms importants aujourd'hui.
- **Historique court** : cinq ans, un seul épisode de baisse marquée (2022). La volatilité est un indicateur de risque parmi d'autres.
- **Seuils des règles** : hypothèses de l'équipe, pas des normes réglementaires ; c'est l'hypothèse à laquelle les verdicts sont le plus sensibles (voir la mise à l'épreuve).
- **ESG** : aucune donnée ESG n'est intégrée. Pour un profil à forte préférence ESG (Mateo), la règle d'exclusion ESG rend « information manquante » au lieu d'un faux « conforme », et le verdict financier est donné à part. Pour les autres profils, un verdict « conforme » ne dit rien de l'ESG.
- **Groupe corrélé (Amira)** : seuil de corrélation de 0,80 choisi après examen des données, mesure très sensible à la fenêtre de dates (détail dans `docs/technical_documentation.md`).
- **Concentration en actions individuelles (R6)** : la règle compte les actions détenues directement, pas les FNB d'actions.
- **Données publiques gratuites**, non certifiées ; valeurs FRED révisées.
- Le garde-fou Bedrock complète les contrôles du code mais ne prouve pas l'exactitude factuelle : son score d'ancrage mesure la cohérence du texte avec le vocabulaire du dossier, pas l'exactitude des statuts, que garantit le code.
