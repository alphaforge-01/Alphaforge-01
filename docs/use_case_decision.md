# Choix du cas d'usage

Statut : **proposition à valider par l'équipe**. Rien n'est choisi tant que l'équipe n'a pas tranché (voir CLAUDE.md, section "Exigences du projet et décisions"). Les notes ci-dessous sont un jugement, pas une mesure.

## Recommandation : banc d'essai d'une idée de placement (cas A)

**Question utile :** "J'ai une idée de placement : que change-t-elle à mon portefeuille fictif, et est-elle cohérente avec mon profil ?"

**Parcours utilisateur :**

1. L'utilisateur choisit un profil :
   - l'un des trois personas préremplis (Amira, Mateo, Robert) ;
   - ou un profil fictif construit avec le constructeur de profil (voir plus bas).
2. Il voit le portefeuille fictif de départ associé au profil.
3. Il écrit une idée en langage libre, par exemple "mettre 25 % dans TSLA".
4. Il reçoit :
   - une comparaison avant/après (risque, concentration, perte maximale historique) ;
   - les tensions avec son profil ;
   - une ou deux variantes simulées qui réduisent ces tensions ;
   - une explication dont chaque chiffre renvoie à une preuve.

**Couverture des personas :**

| Profil | Demande type | Ce que le système montre |
| --- | --- | --- |
| Robert | "25 % dans TSLA" | Concentration, perte maximale et durée de récupération face à un horizon de 3 à 5 ans. Il nomme la tension et n'acquiesce pas. |
| Mateo | "ajouter XOM ou CNQ" | Contrôle ESG en plus des contrôles financiers, avec une preuve datée et sourcée, ou "information manquante". |
| Amira | "40 % crypto, le reste en NVDA" | Risque élevé accepté, mais les plafonds de concentration et de diversification signalent le conflit avec sa propre préférence. |
| Profil construit | n'importe quelle idée | Mêmes contrôles, appliqués aux règles dérivées du questionnaire. |

**Pourquoi ce cas :**

- Les trois tests des personas sont le même mécanisme : une tension entre une demande et un profil. Un seul parcours les couvre tous.
- Le système évalue une idée de l'utilisateur au lieu de prescrire un actif. C'est plus défendable face aux contraintes "pas de conseil personnalisé" et "pas d'association automatique entre un profil et un actif".
- La démo est forte : la même demande, soumise à deux profils, donne deux verdicts différents.

## Constructeur de profil

L'énoncé permet des profils autres que les personas :

- p. 8 : "considérer les personas et, au besoin, d'autres objectifs, préférences ou contraintes explicites" ;
- p. 14 : "les équipes restent libres de définir leurs propres scénarios fictifs" ;
- p. 11 : "Profils et scénarios" figure parmi les familles de données exploitables.

**Fonctionnement :**

- Un court questionnaire : horizon, objectif, tolérance au risque, expérience, préférences (ESG, crypto, technologies), contraintes (exclusions, besoin de liquidité), capital fictif.
- Il produit un profil au même format que les personas, avec les mêmes règles et seuils (plafond par titre, par secteur, part de crypto, part défensive).
- La traduction des réponses en seuils est faite par du code déterministe. Elle est affichée comme une hypothèse de l'équipe.
- Les trois personas sont des profils préremplis du même format, modifiables.

**Conditions :**

- Le profil est **fictif**. Aucune donnée personnelle réelle n'est demandée ni conservée (règle n°7). L'interface le rappelle.
- L'avertissement "simulation, à but éducatif, pas un conseil personnalisé" reste visible (règle n°8).
- Les trois personas restent les scénarios de démo principaux : l'énoncé dit ce que chacun teste.

## Candidats écartés

| Cas | Note pondérée (sur 5) | Faisabilité (sur 5) | Raison |
| --- | --- | --- | --- |
| **A. Banc d'essai d'une idée de placement** | **4,55** | 4 | Retenu |
| C. Comparateur ESG par recherche documentaire (RAG) | 4,05 | 2 | Bon pour AWS, mais lourd en données et faible pour Amira et Robert |
| D. Explorateur de périodes historiques | 3,50 | 4 | Peu agentique. Il devient un outil de l'agent dans A |
| B. Allocation fictive selon le profil | 3,45 | 4 | Attendu, ne teste pas Robert, frôle le conseil personnalisé |

Détail des notes de A, B, C et D :

| Critère (poids) | A | B | C | D |
| --- | --- | --- | --- | --- |
| Qualité, pertinence, innovation (20) | 5 | 3 | 4 | 3 |
| Agentique et explicabilité (20) | 5 | 3 | 4 | 3 |
| Analyse de données (20) | 4 | 4 | 4 | 5 |
| UX/UI (10) | 4 | 4 | 3 | 4 |
| AWS (15) | 4 | 4 | 5 | 3 |
| Présentation, valeur d'affaires (15) | 5 | 3 | 4 | 3 |

## Architecture proposée

| Composant | Nature | Rôle |
| --- | --- | --- |
| Agent analyste | Modèle de langage sur Bedrock, tours et appels bornés | Structure l'idée (actif, poids, source des fonds), pose une question si elle est incomplète, choisit les outils, propose les variantes et les repasse dans les mêmes outils, rédige l'explication. |
| Gouvernance | Code déterministe testé | Applique les règles du profil et de la simulation. Rend un statut par règle : conforme, tension, conflit ou information manquante. **Le modèle de langage ne décide jamais du verdict.** |
| Registre de preuves | Code déterministe | Chaque appel d'outil enregistre une entrée numérotée : source, période, devise, transformation, valeur. L'interface affiche les chiffres du registre, pas ceux du texte du modèle. Toute citation absente du registre est rejetée. |
| Garde-fou Bedrock | Service géré | Sujets refusés (conseil personnalisé, exécution d'ordres) et vérification que les réponses restent fidèles aux données. Ses interventions apparaissent dans la trace. |

**Outils de l'agent** (tous déterministes, aucun outil de passage d'ordres) :

- `get_profile` : profil fictif et ses règles ;
- `get_asset_facts` : rendement et volatilité annualisés sur une période explicite, perte maximale, durée de récupération ;
- `simulate_portfolio_change` : poids, volatilité, concentration par titre, secteur et classe d'actifs, avant et après, en CAD ;
- `get_correlations` : corrélations entre actifs ;
- `get_historical_episode` : comportement pendant un épisode daté (par exemple 2022), descriptif seulement ;
- `get_esg_evidence` : preuves datées, ou "aucune preuve disponible" ;
- `check_governance` : statut par règle.

**Étapes visibles dans la trace :** idée comprise, calculs effectués, gouvernance appliquée, citations validées, garde-fou passé. Le raisonnement interne du modèle n'est pas exposé.

**Hypothèses affichées comme telles :**

- les seuils par profil, réglables par curseurs, ce qui donne le test de sensibilité ("le verdict change si le plafond passe de X à Y") ;
- les portefeuilles de départ, fictifs et modifiables ;
- la devise de base, le CAD ;
- l'alignement des calendriers sur les jours ouvrables communs, avec la crypto ramenée à ce calendrier et le taux de change reporté en avant ;
- les limites : biais du survivant, fenêtre de 5 ans, volatilité comme indicateur parmi d'autres.

**Données à ajouter :**

- `data/external/investor_profiles.json` : les trois personas au format profil ;
- `data/external/esg_evidence.csv` : une ligne par affirmation, avec URL, date de publication et date d'extraction, pour les 20 actions du jeu de départ. Les conditions de redistribution sont à vérifier avant tout commit. L'absence de preuve s'affiche "information manquante", jamais "conforme".

**Pile AWS minimale** (option, à valider) :

- Bedrock, API Converse avec appels d'outils ;
- garde-fou Bedrock, testé avec des requêtes permises et refusées ;
- S3 privé pour les traces d'exécution ;
- interface Streamlit, locale d'abord, hébergée sur AWS ensuite si le temps le permet.

## Emplacement du code

- `src/alphaforge/` :
  - données : `data_loading.py`, `calendar_alignment.py`, `fx_conversion.py` ;
  - calculs : `metrics.py`, `portfolio.py` ;
  - profils : `profiles.py` (constructeur et règles dérivées) ;
  - contrôle et preuves : `governance.py`, `evidence.py` ;
  - agent : `agent_tools.py`, `agent.py`, `prompts/`.
- `app/` : interface. Nouveau dossier racine, à valider (il modifie la règle n°5).
- `scripts/` : `build_processed.py`, `setup_guardrail.py`, `run_scenarios.py`.
- `tests/` : un `test_<module>.py` par module.
- `docs/` : documentation technique, one pager, script de démo.

## Feuille de route

1. **Décisions.** Répondre aux questions ouvertes, vérifier le compte AWS et les modèles disponibles, obtenir l'accord d'un mentor pour les données.
2. **Socle de calcul.** Chargement, alignement des calendriers, conversion de devises, métriques, simulation avant/après, avec tests.
3. **Première démo de bout en bout.** Robert demande TSLA : agent, gouvernance, registre de preuves, page avec avertissement.
4. **Profils.** Les trois personas, le constructeur de profil, la table ESG, les variantes, les curseurs, deux profils côte à côte.
5. **AWS.** Garde-fou visible dans la trace, traces sur S3, hébergement optionnel.
6. **Livrables.** README, documentation technique, one pager, vidéo.

## Risques

- **Compte AWS temporaire :** enregistrer la vidéo pendant qu'il est actif.
- **Quotas partagés :** modèle peu coûteux et nouvelles tentatives espacées en cas de limitation.
- **Perception "pas assez agentique" :** les variantes et les questions de précision doivent être visibles dans la démo.
- **Seuils arbitraires :** les présenter comme des hypothèses réglables.
- **Table ESG contestable :** rester factuel et daté.

## Questions ouvertes

1. Date limite et consignes de dépôt ?
2. Taille et compétences de l'équipe ?
3. Date de fin du compte Workshop Studio, et modèles Bedrock disponibles ?
4. Streamlit pour l'interface ? Interface en français ?
5. Hébergement sur AWS exigé, ou Bedrock, garde-fou et S3 suffisent-ils ?
6. Un mentor autorise-t-il le téléversement des CSV dans le compte ?
7. Qui monte la table ESG ?
8. Accepte-t-on le dossier racine `app/` et les seuils comme hypothèses réglables ?
