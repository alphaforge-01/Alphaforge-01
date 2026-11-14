# Choix du cas d'usage

Statut : **proposition à valider par l'équipe**. Rien n'est choisi tant que l'équipe n'a pas tranché (voir CLAUDE.md, section "Exigences du projet et décisions"). Les notes ci-dessous sont un jugement, pas une mesure.

Cette version fusionne la proposition initiale (cas A) avec les idées de Samer et d'Ibrahima. Le tableau "Ce qui change" résume les arbitrages.

## Recommandation : un copilote de cohérence, pas un conseiller

Positionnement proposé par Ibrahima : le système ne dit pas quoi acheter. Il vérifie si un portefeuille fictif et une envie de placement sont cohérents avec le profil de l'investisseur, et il montre ses preuves.

**Question utile :** "Mon portefeuille fictif correspond-il à mon profil, et que change mon idée de placement ?"

**Parcours utilisateur (une seule porte d'entrée pour le MVP) :**

1. **Profil.** Choisir Amira, Mateo ou Robert, ou construire un profil fictif avec des cases à cocher.
2. **Radiographie.** Voir le portefeuille fictif de départ et son état : volatilité, perte maximale historique, concentration, exposition USD/CAD, statut par règle du profil.
3. **Idée.** Soumettre une idée avec des sélecteurs (actif, poids, source des fonds) ou en texte libre, par exemple "mettre 25 % dans TSLA".
4. **Résultat.**
   - comparaison avant/après ;
   - tensions avec le profil, statut par règle ;
   - contrefactuel : ce qui ferait changer le statut (par exemple "conforme sous 8 %") ;
   - une ou deux variantes simulées qui réduisent les tensions ;
   - explication au niveau choisi (novice, intermédiaire, pro).
5. **Vérification.** Cliquer sur un chiffre pour voir le calcul, la source, la période, la devise et les limites.

**Couverture des personas :**

| Profil | Demande type | Ce que le système montre |
| --- | --- | --- |
| Robert | "25 % dans TSLA" | Concentration, perte maximale et durée de récupération face à un horizon de 3 à 5 ans. Il nomme la tension, n'acquiesce pas, donne le contrefactuel. |
| Mateo | "ajouter XOM ou CNQ" | Contrôle ESG en plus des contrôles financiers, avec une preuve datée et sourcée, ou "information manquante". |
| Amira | "40 % crypto, le reste en NVDA" | Risque élevé accepté, mais fausse diversification : NVDA, QQQ et la crypto bougent ensemble. Conflit avec sa propre préférence de diversification. |
| Profil construit | n'importe quelle idée | Mêmes contrôles, appliqués aux règles issues des cases cochées. |

**Pourquoi ce cas :**

- Les trois tests des personas sont le même mécanisme : une tension entre une demande et un profil.
- Le système évalue une idée de l'utilisateur au lieu de prescrire un actif. C'est défendable face à "pas de conseil personnalisé" et "pas d'association automatique entre un profil et un actif".
- Deux scènes de démo fortes : même demande et deux profils donnent deux verdicts ; même résultat et trois niveaux d'explication donnent trois textes avec les mêmes chiffres.

## Ce qui change par rapport à la version précédente

| Sujet | Décision proposée | Origine |
| --- | --- | --- |
| Saisie | Cases et sélecteurs par défaut, texte libre optionnel | Samer |
| Positionnement | "Copilote de cohérence, pas un conseiller" | Ibrahima |
| Radiographie du portefeuille | Ajoutée comme étape 2 | Ibrahima |
| Contrefactuel | Ajouté, calculé par la gouvernance | Ibrahima |
| Niveaux d'explication | Ajoutés (3 niveaux, mêmes chiffres) | Ibrahima |
| Fausse diversification | Ajoutée, version par corrélations | Ibrahima |
| Fidélité aux données | Validateur de chiffres et repli sans modèle ajoutés | Samer |
| Nouvelles libres | Écartées du MVP, remplacées par les annonces planifiées | Ibrahima (les deux idées) |
| Rejeu | Extension, mais `as_of` posé dès le socle | Ibrahima |
| Agents | Un agent analyste, pas quatre | arbitrage |
| Lambda | Extension, pas MVP | arbitrage |

## Profil : cases à cocher d'abord, texte libre ensuite

Combinaison des idées de Samer (cases) et d'Ibrahima (règle proposée puis confirmée).

| Étape | Mécanisme | Qui décide |
| --- | --- | --- |
| 1. Choix rapide | Trois personas préremplis, modifiables | Utilisateur |
| 2. Cases et curseurs | Objectif, horizon, tolérance au risque, expérience, ESG, crypto, plafond par titre, capital fictif | Code déterministe : réponses vers règles et seuils |
| 3. "Autre contrainte" (optionnel) | Texte libre, par exemple "pas de pétrole" | L'agent propose une règle du catalogue, l'utilisateur confirme ou refuse |
| 4. Contrôle du profil | Contradictions et champs manquants signalés | Code déterministe |

Règles du jeu :

- **Catalogue fermé de règles** : plafond par titre, par secteur, par classe d'actifs, exclusion de secteur, exclusion d'actif, part minimale défensive, exclusion ESG. L'agent ne peut proposer qu'une règle de ce catalogue.
- Une contrainte hors catalogue s'affiche "non prise en charge". Elle n'est jamais ignorée en silence.
- Aucune règle issue du texte libre n'est active sans confirmation de l'utilisateur. La confirmation apparaît dans la trace.
- Les seuils sont des **hypothèses de l'équipe**, affichées comme telles et réglables (test de sensibilité).
- L'idée de placement suit le même principe : sélecteurs d'abord, texte libre possible, idées suggérées en un clic pour la démo.
- Le profil est **fictif**. Aucune donnée personnelle réelle n'est demandée ni conservée (règle n°7). L'interface le rappelle.

## Niveaux d'explication (idée d'Ibrahima)

| Niveau | Forme | Identique partout |
| --- | --- | --- |
| Novice | Mots simples, montants en dollars, une analogie sans chiffre | Chiffres, statuts, limites |
| Intermédiaire | Termes financiers définis au premier usage | Chiffres, statuts, limites |
| Pro | Termes techniques, méthode et paramètres (fenêtre, annualisation, alignement) | Chiffres, statuts, limites |

- Le niveau est prérempli selon l'expérience déclarée et modifiable à tout moment.
- Le niveau est un paramètre de rédaction. Il ne relance aucun calcul et ne change aucun statut.
- Les montants en dollars sont calculés par les outils (capital fictif fois pourcentage), pas par le modèle.
- Le niveau pro détaille la méthode, jamais le raisonnement interne du modèle.
- Les textes sont mis en cache par niveau pour que la bascule soit instantanée en démo.

## Fidélité aux données : ce qui est garanti et ce qui ne l'est pas

Demande de Samer : l'agent ne doit jamais inventer. Aucun système ne peut promettre "zéro hallucination". On promet des garanties précises, obtenues par construction.

| Mécanisme | Ce qu'il garantit | Ce qu'il ne garantit pas |
| --- | --- | --- |
| Calculs par outils déterministes testés | Aucun chiffre financier ne vient du modèle | L'absence d'erreur dans les données sources |
| Registre de preuves | Chaque chiffre affiché a une source, une période, une devise et une transformation | Que la source elle-même soit exacte |
| Rédaction par références | Le modèle écrit des renvois (`[E12]`), l'interface insère la valeur du registre | La justesse des phrases qualitatives autour |
| Validateur de chiffres | Un texte contenant un chiffre hors registre ou une référence inconnue est rejeté | Rien sur les phrases sans chiffre |
| Gouvernance déterministe | Le statut par règle ne dépend jamais du modèle | Que les seuils soient "les bons" (ce sont des hypothèses) |
| Refus si donnée manquante | Un outil sans donnée renvoie "information manquante", jamais une valeur par défaut | Sans objet |
| Repli sans modèle | Après un rejet et un nouvel essai, une explication à gabarit fixe est affichée | La qualité de style du repli |
| Garde-fou Bedrock | Sujets refusés (conseil personnalisé, exécution d'ordres, prédiction), contrôle d'ancrage sur le texte final | **L'exactitude factuelle** : c'est un filtre probabiliste à seuil |

Risque résiduel assumé : une formulation qualitative trompeuse ("faible", "rassurant"). Mesures : consignes de rédaction strictes, qualificatifs liés à des seuils affichés, contrôle d'ancrage, relecture d'un jeu de scénarios fixes avant la démo.

## Annonces planifiées plutôt que nouvelles libres

Ibrahima propose deux variantes de la deuxième porte d'entrée. Recommandation : garder les annonces planifiées, écarter les nouvelles libres du MVP.

| Critère | Nouvelle libre collée | Annonce planifiée |
| --- | --- | --- |
| Licence | Texte de presse souvent protégé | Publications officielles publiques (conditions à vérifier et consigner) |
| Datation | Incertaine, heure de publication floue | Date et heure officielles |
| Anticipation | Élevée (on connaît la suite) | Maîtrisable avec un calendrier |
| Canal d'exposition | Déduit par le modèle, invérifiable | Fixé par le type d'annonce (taux, inflation) |
| Comparables | "Épisodes semblables" subjectifs | Même type d'annonce, nombre d'observations affiché |

**Ce que cela demande en données :**

- Notre série du taux directeur (V39079) change **le lendemain** de l'annonce. Exemple : la hausse annoncée le mercredi 2 mars 2022 (date à confirmer sur le site de la Banque du Canada) y apparaît le jeudi 3 mars. Les décisions de maintien n'y laissent aucune trace.
- Il faut donc un fichier `data/external/scheduled_announcements.csv` : type d'annonce, date et heure d'annonce, période de référence, décision (hausse, baisse, maintien), valeur, URL, date d'extraction.
- Étape 1 : décisions de taux de la Banque du Canada (8 par an, environ 40 sur la fenêtre, dont 20 changements visibles dans nos données). Saisie manuelle depuis le calendrier officiel, faisable en une heure.
- Étape 2, si le temps le permet : publications de l'inflation. Il faut les **dates de publication** (Statistique Canada, BLS), pas seulement le mois de référence. Les valeurs FRED sont révisées : pour rester fidèle, il faudrait les premières publications (ALFRED) ou afficher la limite.

**Ce que l'outil calcule :** le rendement du portefeuille fictif le jour de l'annonce et sur les 5 jours ouvrables suivants, pour toutes les annonces passées du même type, avec la médiane, l'étendue et le nombre d'observations.

**Limites affichées :** peu d'observations, d'autres événements le même jour, aucune causalité affirmée, description du passé et non prévision.

## Rejeu à une date passée : discipline requise

Le rejeu (idée d'Ibrahima) est une extension. Sa discipline est posée dès le socle : toutes les fonctions de chargement et tous les outils acceptent un paramètre `as_of`, et aucune donnée postérieure n'est lue.

| Piège avec nos données | Règle |
| --- | --- |
| Macro mensuelle datée au mois de référence | Colonne `available_from` : date de publication réelle, sinon délai prudent documenté |
| Valeurs FRED révisées | Limite affichée, ou premières publications si on les ajoute |
| `adj_close` rétro-ajusté depuis 2026 | En rejeu, n'utiliser que des rendements, jamais de niveaux de prix. Les montants viennent du capital fictif |
| Biais du survivant | L'univers a été choisi en 2026. Le rejeu ne montre pas "ce qu'on aurait vu à l'époque" : limite affichée en permanence |
| Preuves ESG et annonces | Filtrées par date de publication antérieure à `as_of` |
| Secteurs et libellés | Ce sont ceux d'aujourd'hui : limite affichée |
| Le modèle de langage connaît la suite | Les outils sont à l'aveugle, pas le modèle. En rejeu, explication à gabarit fixe ou très contrainte, et limite dite à l'écran |

Test obligatoire : pour une date donnée, le résultat d'un outil ne change pas si on supprime toutes les données postérieures.

## Les 12 cas d'Ibrahima : où ils vont

| Cas | Place |
| --- | --- |
| 1. Radiographie | MVP |
| 2. Ajout d'un titre en vogue | MVP (cas A) |
| 3. Fausse diversification | MVP, par corrélations et secteurs. Chevauchement réel des FNB reporté |
| 4. Contraintes ESG | MVP, version minimale |
| 5. Changement de profil | MVP (curseurs) |
| 6. Impact d'une nouvelle | Remplacé par les annonces planifiées (extension 1) |
| 7. Scénarios "et si ça dure ?" | Extension 3 |
| 8. "Comment en profiter ?" | Pas une fonction. Requête refusée dans les tests du garde-fou |
| 9. Rejeu | Extension 2 |
| 10. Définir le profil | MVP (cases, puis texte libre confirmé) |
| 11. Niveau d'explication | MVP |
| 12. Vérifier un chiffre | MVP (registre de preuves) |

## Candidats écartés

| Cas | Note pondérée (sur 5) | Faisabilité (sur 5) | Raison |
| --- | --- | --- | --- |
| **A. Banc d'essai d'une idée, devenu copilote de cohérence** | **4,55** | 4 | Retenu |
| C. Comparateur ESG par recherche documentaire (RAG) | 4,05 | 2 | Bon pour AWS, mais lourd en données et faible pour Amira et Robert |
| D. Explorateur de périodes historiques | 3,50 | 4 | Peu agentique. Il devient un outil de l'agent dans A |
| B. Allocation fictive selon le profil | 3,45 | 4 | Attendu, ne teste pas Robert, frôle le conseil personnalisé |

| Critère (poids) | A | B | C | D |
| --- | --- | --- | --- | --- |
| Qualité, pertinence, innovation (20) | 5 | 3 | 4 | 3 |
| Agentique et explicabilité (20) | 5 | 3 | 4 | 3 |
| Analyse de données (20) | 4 | 4 | 4 | 5 |
| UX/UI (10) | 4 | 4 | 3 | 4 |
| AWS (15) | 4 | 4 | 5 | 3 |
| Présentation, valeur d'affaires (15) | 5 | 3 | 4 | 3 |

## Architecture proposée

### Un agent, pas quatre

L'énoncé préfère explicitement une conception simple, ciblée et vérifiable à un grand nombre d'agents. Il décrit l'explicabilité et la gouvernance comme "agent ou mécanisme". Recommandation : **un agent analyste**, et des mécanismes déterministes pour le reste.

| Rôle | Nature | Pourquoi |
| --- | --- | --- |
| Analyste | Agent sur Bedrock, tours et appels bornés | Seul rôle qui demande du jugement : comprendre la demande, choisir les outils, proposer des variantes, rédiger |
| Profil | Code, plus un appel à l'agent pour le texte libre | La traduction en règles doit être reproductible |
| Gouvernance | Code déterministe testé | Un verdict ne doit pas varier d'un appel à l'autre |
| Explication | Registre de preuves, validateur, niveau de rédaction | La fidélité s'obtient par construction, pas par un deuxième modèle |

Raisons : chaque agent ajoute des appels (quotas partagés), de la latence en démo, des points de panne et une trace plus difficile à lire. Les quatre rôles restent **visibles dans l'interface** comme étapes de la trace. Les rôles exacts des quatre agents d'Ibrahima sont à confirmer avec lui.

### Composants

| Composant | Rôle |
| --- | --- |
| Agent analyste | Structure l'idée (actif, poids, source des fonds), pose une question si elle est incomplète, choisit les outils, propose les variantes et les repasse dans les mêmes outils, rédige par références au registre |
| Gouvernance | Statut par règle : conforme, tension, conflit, information manquante. Donne aussi la marge avant changement de statut (contrefactuel). **Le modèle ne décide jamais du verdict** |
| Registre de preuves | Une entrée numérotée par résultat d'outil : source, période, devise, transformation, valeur |
| Validateur d'explication | Rejette tout chiffre hors registre et toute référence inconnue. Un nouvel essai, puis repli à gabarit fixe |
| Garde-fou Bedrock | Sujets refusés et contrôle d'ancrage. Interventions visibles dans la trace |

### Outils de l'agent

Tous déterministes, tous avec `as_of`, aucun outil de passage d'ordres.

| Outil | Rend | Phase |
| --- | --- | --- |
| `get_profile` | Profil fictif et ses règles | MVP |
| `propose_profile_rule` | Règle du catalogue proposée à partir d'un texte libre, à confirmer | MVP |
| `analyze_portfolio` | Radiographie : volatilité, perte maximale, concentration, exposition USD/CAD | MVP |
| `get_asset_facts` | Rendement et volatilité annualisés sur une période explicite, perte maximale, durée de récupération | MVP |
| `simulate_portfolio_change` | Avant/après en CAD : poids, volatilité, concentration par titre, secteur, classe d'actifs | MVP |
| `get_diversification` | Corrélations, groupes d'actifs qui bougent ensemble, exposition réelle par secteur | MVP |
| `get_historical_episode` | Comportement pendant un épisode daté (par exemple 2022), en pourcentage et en dollars fictifs | MVP |
| `get_esg_evidence` | Preuves datées, ou "aucune preuve disponible" | MVP |
| `check_governance` | Statut et marge par règle | MVP |
| `get_announcement_reactions` | Réaction du portefeuille aux annonces passées d'un même type | Extension 1 |

### Trace visible

Idée comprise, règles confirmées, outils appelés (nom, paramètres, numéro de preuve), gouvernance appliquée, références validées, garde-fou passé ou intervenu. Le raisonnement interne du modèle n'est pas exposé.

### Hypothèses affichées comme telles

- seuils par profil, réglables par curseurs ;
- portefeuilles de départ, fictifs et modifiables ;
- devise de base : CAD ;
- alignement sur les jours ouvrables communs, crypto ramenée à ce calendrier, taux de change reporté en avant ;
- limites : biais du survivant, fenêtre de 5 ans, un seul épisode de baisse marquée (2022), volatilité comme indicateur parmi d'autres.

### Données à ajouter

| Fichier | Contenu | Phase |
| --- | --- | --- |
| `data/external/investor_profiles.json` | Les trois personas au format profil, portefeuilles fictifs | MVP |
| `data/external/esg_evidence.csv` | Une ligne par affirmation : URL, date de publication, date d'extraction. Commencer par les titres des scénarios de démo | MVP |
| `data/external/scheduled_announcements.csv` | Calendrier des annonces (voir plus haut) | Extension 1 |

Chaque fichier a son entrée dans `data/external/sources.md`. Conditions de redistribution à vérifier avant tout commit. L'absence de preuve s'affiche "information manquante", jamais "conforme".

## Pile AWS minimale (option, à valider)

| Service | Rôle concret | Phase |
| --- | --- | --- |
| Bedrock, API Converse avec appels d'outils | L'agent analyste | MVP |
| Garde-fou Bedrock | Sujets refusés, contrôle d'ancrage, testé avec des requêtes permises et refusées | MVP |
| S3 privé | Traces d'exécution consultables (une par analyse) | MVP |
| Hébergement de l'interface sur AWS | Démo accessible par URL | Extension 4 |
| Lambda pour les outils | Outils appelables hors de l'application | Extension 4 |

**Lambda maintenant ou plus tard ?** Recommandation : plus tard.

- Pour quelques mégaoctets de CSV, des outils dans le processus sont plus rapides, testables hors ligne et sans emballage de dépendances (pandas).
- Lambda ajoute IAM, déploiement et démarrages à froid, sans rien changer pour l'utilisateur.
- On garde la porte ouverte : chaque outil est une fonction pure avec un schéma JSON en entrée et en sortie. Un déploiement Lambda devient un simple enrobage.
- Si l'équipe juge que le critère AWS (15 %) demande plus, Lambda est la première chose à ajouter, à durée bornée (une demi-journée).

## Emplacement du code

- `src/alphaforge/` :
  - données : `data_loading.py` (avec `as_of`), `calendar_alignment.py`, `fx_conversion.py` ;
  - calculs : `metrics.py`, `portfolio.py`, `diversification.py` ;
  - profils : `profiles.py` (cases vers règles, catalogue de règles) ;
  - contrôle et preuves : `governance.py`, `evidence.py`, `explanation.py` (validateur, niveaux, repli) ;
  - agent : `agent_tools.py`, `agent.py`, `prompts/` ;
  - extension : `scheduled_events.py`.
- `app/` : interface. Nouveau dossier racine, à valider (il modifie la règle n°5).
- `scripts/` : `build_processed.py`, `setup_guardrail.py`, `run_scenarios.py`.
- `tests/` : un `test_<module>.py` par module.
- `docs/` : documentation technique, one pager, script de démo.

## Périmètre

### MVP

| Bloc | Critères servis |
| --- | --- |
| Socle de calcul testé (alignement, devises, métriques, `as_of`) | Analyse de données |
| Radiographie et avant/après pour les trois personas | Qualité, analyse de données |
| Gouvernance avec statuts et contrefactuel | Agentique et explicabilité |
| Agent Bedrock, registre, validateur, repli, trace | Agentique et explicabilité, AWS |
| Garde-fou et traces S3 | AWS |
| Profil par cases, idée par sélecteurs, panneau "Sources et méthode", avertissement | UX/UI |
| Trois niveaux d'explication | UX/UI, explicabilité |
| ESG minimal pour Mateo | Qualité |

### Extensions, dans l'ordre

1. Annonces planifiées : décisions de taux de la Banque du Canada.
2. Rejeu à une date passée, puis révélation de la suite.
3. Scénarios "choc temporaire ou régime prolongé" en dollars fictifs.
4. Hébergement sur AWS, puis outils sur Lambda.
5. Publications de l'inflation, chevauchement réel des FNB.

### Scènes de démo (vidéo de 5 minutes)

| Scène | Contenu | Phase |
| --- | --- | --- |
| 1 | Robert veut 25 % de TSLA : tension nommée, contrefactuel, variante | MVP |
| 2 | Même demande pour Amira : autre verdict, même mécanisme | MVP |
| 3 | Bascule novice, intermédiaire, pro : le texte change, les chiffres restent | MVP |
| 4 | Clic sur un chiffre : calcul, source, date, limites. Puis une requête refusée par le garde-fou | MVP |
| 5 | Mateo et une annonce de la Banque du Canada | Extension 1 |

## Feuille de route

1. **Décisions.** Répondre aux questions ouvertes, vérifier le compte AWS et les modèles actifs, obtenir l'accord d'un mentor pour les données.
2. **Socle de calcul.** Chargement avec `as_of`, alignement, devises, métriques, simulation avant/après, tests.
3. **Profils et gouvernance.** Trois personas, catalogue de règles, statuts, marges, tests.
4. **Première démo de bout en bout.** Robert et TSLA : agent, registre, validateur, repli, page avec avertissement.
5. **Interface.** Cases du profil, sélecteurs de l'idée, radiographie, deux profils côte à côte, panneau de preuves, niveaux d'explication.
6. **AWS.** Garde-fou testé et visible dans la trace, traces sur S3.
7. **ESG minimal et fausse diversification.** Scénarios de Mateo et d'Amira.
8. **Gel du MVP et enregistrement d'une première vidéo.** Avant toute extension.
9. **Extensions**, dans l'ordre ci-dessus, selon le temps restant.
10. **Livrables.** README, documentation technique, one pager, vidéo finale.

## Risques

- **Dérive du périmètre :** 12 cas d'usage, c'est trop. Geler le MVP avant les extensions.
- **Compte AWS temporaire :** enregistrer la vidéo pendant qu'il est actif.
- **Quotas partagés :** modèle peu coûteux, tours bornés, nouvelles tentatives espacées, cache des textes par niveau.
- **Perception "pas assez agentique" avec un seul agent :** montrer dans la trace le choix des outils, la question de précision et les variantes repassées dans les outils.
- **Promesse "zéro hallucination" :** ne pas la faire. Présenter le tableau des garanties.
- **Seuils arbitraires :** les présenter comme des hypothèses réglables.
- **Table ESG contestable :** rester factuel et daté.
- **Montants en dollars lus comme une prévision :** toujours écrire "perte historique observée sur telle période, appliquée au capital fictif".
- **Analogies du niveau novice :** sans chiffre, sinon rejetées par le validateur.
- **Contrôle d'ancrage du garde-fou :** compatibilité avec les appels d'outils à vérifier dans le compte. Sinon l'appliquer au texte final seulement.

## Questions ouvertes

1. Date limite et consignes de dépôt ?
2. Taille de l'équipe et répartition (socle de calcul, agent et AWS, interface, données ESG et annonces, livrables) ?
3. Date de fin du compte Workshop Studio, et modèles Bedrock actifs ?
4. Streamlit pour l'interface ? Interface en français ?
5. Hébergement sur AWS exigé, ou Bedrock, garde-fou et S3 suffisent-ils ? Sinon, Lambda remonte-t-il dans le MVP ?
6. Un mentor autorise-t-il le téléversement des CSV dans le compte ?
7. Qui monte la table ESG, et pour quels titres en premier ?
8. Accepte-t-on le dossier racine `app/` et les seuils comme hypothèses réglables ?
9. Ibrahima : quels étaient les rôles des quatre agents ? L'arbitrage "un agent et des mécanismes" convient-il ?
10. Samer et Ibrahima : la combinaison "cases d'abord, texte libre confirmé ensuite" convient-elle ?
11. Trois niveaux d'explication dès le MVP, ou deux (novice et pro) pour commencer ?
12. Annonces planifiées : qui saisit le calendrier de la Banque du Canada, et ses conditions d'utilisation permettent-elles de le versionner ?
13. Accepte-t-on d'écarter les nouvelles libres et le cas "comment en profiter ?" ?
