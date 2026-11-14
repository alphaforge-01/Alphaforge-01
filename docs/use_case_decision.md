# Choix du cas d'usage

Statut : **proposition à valider par l'équipe**. Rien n'est choisi tant que l'équipe n'a pas tranché (voir CLAUDE.md, section "Exigences du projet et décisions"). Les notes ci-dessous sont un jugement, pas une mesure.

Cette version fusionne la proposition initiale (cas A) avec les idées de Samer et d'Ibrahima, dont l'agent explicateur séparé proposé par Ibrahima. Le tableau "Ce qui change" résume les arbitrages.

## Recommandation : un copilote de cohérence, pas un conseiller

Positionnement proposé par Ibrahima : le système ne dit pas quoi acheter. Il vérifie si un portefeuille fictif et une envie de placement sont cohérents avec le profil de l'investisseur, et il montre ses preuves.

**Question utile :** "Mon portefeuille fictif correspond-il à mon profil, et que change mon idée de placement ?"

**Parcours utilisateur (une seule porte d'entrée pour le MVP) :**

1. **Profil.** Choisir Amira, Mateo ou Robert, ou construire un profil fictif avec des cases à cocher.
2. **Radiographie.** Voir le portefeuille fictif de départ et son état : volatilité, perte maximale historique, concentration, exposition USD/CAD, statut par règle du profil.
3. **Idée.** Soumettre une idée avec des sélecteurs (actif, poids, source des fonds), par exemple "mettre 25 % dans TSLA". Le texte libre vient après le MVP.
4. **Résultat.**
   - comparaison avant/après ;
   - tensions avec le profil, statut par règle ;
   - contrefactuel : ce qui ferait changer le statut (par exemple "conforme sous 8 %") ;
   - une ou deux variantes simulées qui réduisent les tensions ;
   - explication au niveau choisi (novice ou pro).
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
- Deux scènes de démo fortes : même demande et deux profils donnent deux verdicts ; même résultat et deux niveaux d'explication donnent deux textes avec les mêmes chiffres.

## Ce qui change par rapport à la version précédente

| Sujet | Décision proposée | Origine |
| --- | --- | --- |
| Saisie | Cases et sélecteurs uniquement pour le MVP (décision d'équipe). Texte libre confirmé après le MVP | Samer, Ibrahima |
| Positionnement | "Copilote de cohérence, pas un conseiller" | Ibrahima |
| Radiographie du portefeuille | Ajoutée comme étape 2 | Ibrahima |
| Contrefactuel | Ajouté, calculé par la gouvernance | Ibrahima |
| Niveaux d'explication | Ajoutés : novice et pro (décision d'équipe), mêmes chiffres | Ibrahima |
| Fausse diversification | Ajoutée, version par corrélations | Ibrahima |
| Fidélité aux données | Validateur de chiffres et repli sans modèle ajoutés | Samer |
| Nouvelles libres | Écartées du MVP, remplacées par les annonces planifiées. Le recadrage en scénarios hypothétiques fournis par l'équipe a été étudié, puis écarté pour le moment par l'équipe | Ibrahima (les deux idées), décision d'équipe |
| Rejeu | Extension, mais `as_of` posé dès le socle | Ibrahima |
| Agents | Deux agents aux pouvoirs séparés : un analyste (outils) et un explicateur (dossier seul). La gouvernance reste en code | Ibrahima (agent explicateur), arbitrage (conditions) |
| Rédaction | L'analyste ne rédige plus : il soumet un résultat structuré. L'explicateur rédige dans des emplacements fixes | Ibrahima, arbitrage |
| Limites et avertissement | Choisis et affichés par le code, jamais laissés au modèle | arbitrage |
| Lambda | Extension, pas MVP | arbitrage |

## Profil : cases à cocher d'abord, texte libre ensuite

Combinaison des idées de Samer (cases) et d'Ibrahima (règle proposée puis confirmée).

| Étape | Mécanisme | Qui décide |
| --- | --- | --- |
| 1. Choix rapide | Trois personas préremplis, modifiables | Utilisateur |
| 2. Cases et curseurs | Objectif, horizon, tolérance au risque, expérience, ESG, crypto, plafond par titre, capital fictif | Code déterministe : réponses vers règles et seuils |
| 3. "Autre contrainte" (après le MVP) | Texte libre, par exemple "pas de pétrole" | L'agent analyste propose une règle du catalogue, l'utilisateur confirme ou refuse |
| 4. Contrôle du profil | Contradictions et champs manquants signalés | Code déterministe |

Règles du jeu :

- **Catalogue fermé de règles** : plafond par titre, par secteur, par classe d'actifs, exclusion de secteur, exclusion d'actif, part minimale défensive, exclusion ESG. L'agent ne peut proposer qu'une règle de ce catalogue.
- Une contrainte hors catalogue s'affiche "non prise en charge". Elle n'est jamais ignorée en silence.
- Aucune règle issue du texte libre n'est active sans confirmation de l'utilisateur. La confirmation apparaît dans la trace.
- Les seuils sont des **hypothèses de l'équipe**, affichées comme telles et réglables (test de sensibilité).
- L'idée de placement suit le même principe : sélecteurs pour le MVP, idées suggérées en un clic pour la démo, texte libre après le MVP.
- Le profil est **fictif**. Aucune donnée personnelle réelle n'est demandée ni conservée (règle n°7). L'interface le rappelle.

## Niveaux d'explication (idée d'Ibrahima)

| Niveau | Forme | Identique partout |
| --- | --- | --- |
| Novice | Mots simples, montants en dollars, une analogie sans chiffre tirée du glossaire | Chiffres, statuts, limites, ordre des sections |
| Pro | Termes techniques, méthode et paramètres (fenêtre, annualisation, alignement) lus dans le registre | Chiffres, statuts, limites, ordre des sections |

- Le niveau est prérempli selon l'expérience déclarée et modifiable à tout moment.
- Changer de niveau relance **seulement l'agent explicateur** sur le même dossier d'explication figé. L'analyse, les outils et la gouvernance ne sont pas relancés : aucun chiffre et aucun statut ne peut bouger.
- Les montants en dollars sont calculés par les outils (capital fictif fois pourcentage), pas par le modèle.
- Les définitions et les analogies viennent d'un glossaire fermé écrit par l'équipe et fourni dans le dossier. L'explicateur choisit, il n'invente pas. Cela garde le texte vérifiable par le contrôle d'ancrage.
- Le niveau pro détaille la méthode, jamais le raisonnement interne du modèle.
- Les textes sont générés à la demande : le niveau affiché d'abord, les autres au clic ou en arrière-plan. Ils sont mis en cache (clé : dossier, niveau, modèle, version du prompt) pour une bascule instantanée en démo.
- Les limites obligatoires et l'avertissement ont un texte fixe par niveau, écrit par l'équipe et affiché par le code.

## Fidélité aux données : ce qui est garanti et ce qui ne l'est pas

Demande de Samer : l'agent ne doit jamais inventer. Aucun système ne peut promettre "zéro hallucination". On promet des garanties précises, obtenues par construction.

| Mécanisme | Ce qu'il garantit | Ce qu'il ne garantit pas |
| --- | --- | --- |
| Calculs par outils déterministes testés | Aucun chiffre financier ne vient d'un modèle | L'absence d'erreur dans les données sources |
| Registre de preuves | Chaque chiffre affiché a une source, une période, une devise et une transformation | Que la source elle-même soit exacte |
| Explicateur isolé (idée d'Ibrahima) | Le rédacteur ne voit que le dossier d'explication : ni texte libre de l'utilisateur, ni historique, ni données brutes, ni outil | Que le modèle n'utilise pas ses connaissances générales : l'isolation du contexte n'isole pas le modèle |
| Rédaction par références | Le modèle écrit des renvois (`[E12]`, `[G3]`), l'interface insère la valeur ou le statut du registre | La justesse des phrases qualitatives autour |
| Emplacements fixes | L'ordre des sections et des facteurs est fixé par le code (gravité du statut, puis marge) | La qualité du style dans chaque emplacement |
| Validateur d'explication | Rejet de tout chiffre hors registre (y compris en lettres : "un quart", "le double"), de toute référence inconnue, de tout terme de recommandation ou de prédiction, et de tout texte qui ne cite pas chaque règle en tension, en conflit ou en information manquante | Rien sur le sens des phrases sans chiffre |
| Limites et avertissement par le code | Les limites obligatoires (catalogue fermé, rattachées aux outils appelés) et l'avertissement sont toujours affichés, avec un texte fixe | Que l'utilisateur les lise |
| Qualificatifs par seuil | "Élevé", "modéré", "faible" sont calculés par le code à partir de seuils affichés | Que les seuils soient "les bons" (ce sont des hypothèses) |
| Gouvernance déterministe | Le statut par règle ne dépend d'aucun modèle. L'explicateur ne peut ni le changer ni ajouter de recommandation | Que les seuils soient "les bons" |
| Refus si donnée manquante | Un outil sans donnée renvoie "information manquante", jamais une valeur par défaut | Sans objet |
| Repli sans modèle | Après un rejet et un nouvel essai, une explication à gabarit fixe est affichée, avec les mêmes chiffres | La qualité de style du repli |
| Garde-fou Bedrock | Sujets refusés (conseil personnalisé, exécution d'ordres, prédiction). Contrôle d'ancrage du texte final contre le dossier d'explication | **L'exactitude factuelle** : c'est un filtre probabiliste à seuil |

Risques résiduels assumés :

- **Formulation qualitative trompeuse** ("rassurant", "solide"). Mesures : qualificatifs par seuil, glossaire fermé, liste de termes interdits, contrôle d'ancrage, relecture d'un jeu de scénarios fixes avant la démo.
- **Emphase à l'intérieur d'un emplacement.** L'ordre global est fixé, pas le poids des mots dans une phrase. Mesure : relecture du jeu fixe.
- **Connaissances du modèle hors données** (par exemple une remarque sur une entreprise). Mesures : consigne stricte, contrôle d'ancrage, relecture.
- **Motif d'une variante.** L'explicateur ne sait pas pourquoi l'analyste l'a proposée. Mesure : motif transmis sous forme de code fermé (`reduce_weight`, `change_funding_source`, `spread_across_existing`), jamais deviné.

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
| Les modèles de langage connaissent la suite | Les outils sont à l'aveugle, pas les modèles. L'isolation de l'explicateur n'y change rien. En rejeu, explication à gabarit fixe, et limite dite à l'écran |

Test obligatoire : pour une date donnée, le résultat d'un outil ne change pas si on supprime toutes les données postérieures.

## Les 12 cas d'Ibrahima : où ils vont

| Cas | Place |
| --- | --- |
| 1. Radiographie | MVP |
| 2. Ajout d'un titre en vogue | MVP (cas A) |
| 3. Fausse diversification | MVP, par corrélations et secteurs. Chevauchement réel des FNB reporté |
| 4. Contraintes ESG | MVP, version minimale |
| 5. Changement de profil | MVP (curseurs) |
| 6. Impact d'une nouvelle | Remplacé par les annonces planifiées (extension 1). Recadrage en scénarios hypothétiques écarté pour le moment par l'équipe |
| 7. Scénarios "et si ça dure ?" | Extension 3 |
| 8. "Comment en profiter ?" | Pas une fonction. Requête refusée dans les tests du garde-fou |
| 9. Rejeu | Extension 2 |
| 10. Définir le profil | MVP par cases. Texte libre confirmé après le MVP |
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

### Deux agents, un juge en code

L'énoncé préfère explicitement une conception simple, ciblée et vérifiable à un grand nombre d'agents. Il décrit l'explicabilité et la gouvernance comme "agent ou mécanisme". Ibrahima propose de séparer l'explication de l'analyse dans un second agent. Recommandation : **l'adopter sous conditions**. Un agent agit, le code juge, un agent explique.

| Rôle | Nature | Pourquoi |
| --- | --- | --- |
| Analyste | Agent sur Bedrock avec outils, tours et appels bornés | Seul rôle qui demande du jugement : comprendre la demande, choisir les outils, proposer des variantes. Il ne rédige pas |
| Profil | Code, plus un appel à l'analyste pour le texte libre | La traduction en règles doit être reproductible |
| Gouvernance | Code déterministe testé | Un verdict ne doit pas varier d'un appel à l'autre |
| Registre et dossier d'explication | Code | Les preuves, l'ordre des facteurs et les limites obligatoires ne dépendent d'aucun modèle |
| Explicateur (idée d'Ibrahima) | Agent sur Bedrock, un appel borné, sans outil, dossier seul | Rédiger au niveau choisi sans pouvoir sortir de ce qui a été calculé |
| Validateur et repli | Code | La fidélité se contrôle par construction, pas par un modèle |

Chaîne d'exécution :

1. **Analyste** (agent, outils) : structure l'idée, appelle les outils, propose des variantes, termine par `submit_analysis`.
2. **Gouvernance** (code) : statut et marge par règle.
3. **Registre et dossier** (code) : preuves numérotées, facteurs classés, limites obligatoires, glossaire du niveau.
4. **Explicateur** (agent, dossier seul) : rédige dans des emplacements fixes, par renvois.
5. **Validateur** (code) : un nouvel essai en cas de rejet, puis repli à gabarit fixe.
6. **Garde-fou Bedrock** : sujets refusés et contrôle d'ancrage sur le texte rendu.

Conditions de l'adoption :

- **L'analyste ne rédige aucun texte destiné à l'utilisateur**, sauf une question de précision quand l'idée est incomplète. Son résultat est structuré : idée comprise, variantes (paramètres et motif en code fermé), au plus deux preuves à mettre en avant, demandes non prises en charge. Ni prose, ni chiffre, ni verdict.
- **La trace vient du code**, pas d'une déclaration du modèle : appels d'outils, paramètres, numéros de preuve, erreurs.
- **L'explicateur ne voit que le dossier d'explication** : niveau, règles du profil fictif, idée normalisée, preuves (source, période, devise, transformation, valeur, qualificatif), statuts et marges, variantes, facteurs classés, limites, glossaire. Le texte libre de l'utilisateur n'y entre jamais.
- **L'explicateur ne juge pas** : il ne peut ni changer un statut, ni ajouter une recommandation, ni choisir les limites.
- **Le repli à gabarit est construit en premier.** Il sert de filet, de référence de comparaison et de mode hors ligne.

Ce que l'isolation apporte : pas de contamination par le contexte, pas d'injection par le texte libre, un contrôle d'ancrage applicable (source = dossier), un explicateur testable seul, des chiffres immobiles à la bascule de niveau.

Ce qu'elle n'apporte pas : les chiffres étaient déjà protégés par les renvois et le validateur. Les formulations qualitatives restent un risque résiduel (voir "Fidélité aux données").

Coût : environ un appel de modèle de plus par analyse, puis un appel et un contrôle de garde-fou par niveau affiché. Le dernier tour de l'analyste devient court. Les niveaux sont générés à la demande et mis en cache.

Formulation honnête à tenir devant le jury : l'explicateur est un appel borné et contraint, sans outil. On ne multiplie pas les agents au-delà de ces deux rôles.

### Composants

| Composant | Rôle |
| --- | --- |
| Agent analyste | Structure l'idée (actif, poids, source des fonds), pose une question si elle est incomplète, choisit les outils, propose les variantes et les repasse dans les mêmes outils, soumet un résultat structuré. Ne rédige pas l'explication |
| Gouvernance | Statut par règle : conforme, tension, conflit, information manquante. Donne aussi la marge avant changement de statut (contrefactuel). **Aucun modèle ne décide du verdict** |
| Registre de preuves | Une entrée numérotée par résultat d'outil : source, période, devise, transformation, valeur, qualificatif par seuil, limites rattachées |
| Dossier d'explication | Construit par le code à partir du résultat de l'analyste, de la gouvernance et du registre. Fixe l'ordre des facteurs, les limites obligatoires et le glossaire du niveau. C'est la seule entrée de l'explicateur, et la source du contrôle d'ancrage |
| Agent explicateur (idée d'Ibrahima) | Un appel par niveau, sans outil ni historique. Rédige dans des emplacements fixes (résumé, facteurs, contrefactuel, variantes, contexte des limites), par renvois au dossier |
| Validateur d'explication | Rejette tout chiffre hors registre, toute référence inconnue, tout terme de recommandation ou de prédiction, toute règle non conforme non citée. Un nouvel essai, puis repli à gabarit fixe |
| Limites et avertissement | Texte fixe par niveau, affiché par le code sous l'explication. Jamais généré |
| Garde-fou Bedrock | Sujets refusés sur la demande de l'utilisateur et sur le texte final. Contrôle d'ancrage du texte rendu contre le dossier. Interventions et scores visibles dans la trace |

### Outils de l'agent analyste

Tous déterministes, tous avec `as_of`, aucun outil de passage d'ordres. L'agent explicateur n'a aucun outil.

| Outil | Rend | Phase |
| --- | --- | --- |
| `get_profile` | Profil fictif et ses règles | MVP |
| `propose_profile_rule` | Règle du catalogue proposée à partir d'un texte libre, à confirmer | Après le MVP |
| `analyze_portfolio` | Radiographie : volatilité, perte maximale, concentration, exposition USD/CAD | MVP |
| `get_asset_facts` | Rendement et volatilité annualisés sur une période explicite, perte maximale, durée de récupération | MVP |
| `simulate_portfolio_change` | Avant/après en CAD : poids, volatilité, concentration par titre, secteur, classe d'actifs | MVP |
| `get_diversification` | Corrélations, groupes d'actifs qui bougent ensemble, exposition réelle par secteur | MVP |
| `get_historical_episode` | Comportement pendant un épisode daté (par exemple 2022), en pourcentage et en dollars fictifs | MVP |
| `get_esg_evidence` | Preuves datées, ou "aucune preuve disponible" | MVP |
| `check_governance` | Statut et marge par règle | MVP |
| `submit_analysis` | Clôt l'analyse : idée comprise, variantes avec motif en code fermé, preuves à mettre en avant, demandes non prises en charge | MVP |
| `get_announcement_reactions` | Réaction du portefeuille aux annonces passées d'un même type | Extension 1 |

### Trace visible

Six étapes, chacune avec une étiquette "agent" ou "code" :

| Étape | Acteur | Ce qui est affiché |
| --- | --- | --- |
| 1. Analyse | Agent analyste (Bedrock) | Idée comprise, règles confirmées, outils appelés (nom, paramètres, numéro de preuve), variantes proposées, modèle, nombre de tours |
| 2. Gouvernance | Code | Statut, seuil et marge par règle |
| 3. Dossier | Code | Preuves retenues, ordre des facteurs, limites obligatoires. Bouton "Ce que l'explicateur a vu" |
| 4. Explication | Agent explicateur (Bedrock) | Niveau, modèle, essai 1 ou 2, texte lu dans le cache ou généré |
| 5. Validation | Code | Références vérifiées, motifs de rejet, repli utilisé ou non |
| 6. Garde-fou | Bedrock Guardrails | Sujets refusés, scores d'ancrage et de pertinence, action prise |

Les deux agents sont visuellement distincts et la frontière est lisible : l'analyste a des outils et pas de plume, l'explicateur a une plume et pas d'outil. Le raisonnement interne des modèles n'est pas exposé. La trace complète (sans secret) est enregistrée sur S3.

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
| Bedrock, API Converse | Agent analyste (avec appels d'outils) et agent explicateur (un appel sans outil). Identifiants de modèle configurables séparément | MVP |
| Garde-fou Bedrock | Sujets refusés sur l'entrée et sur le texte final. Contrôle d'ancrage par `ApplyGuardrail` : source = dossier d'explication, requête fixe, contenu = texte rendu. Testé avec des requêtes permises et refusées | MVP |
| S3 privé | Traces d'exécution consultables (une par analyse) | MVP |
| Hébergement de l'interface sur AWS | Démo accessible par URL | Extension 4 |
| Lambda pour les outils | Outils appelables hors de l'application | Extension 4 |

**Contrôle d'ancrage, points vérifiés dans la documentation AWS (2026-11-14) et à confirmer dans le compte :**

- Cas pris en charge : résumé, paraphrase, questions-réponses. L'explicateur (dossier vers texte) entre dans ce cadre, pas la boucle d'outils de l'analyste.
- Niveau Classic (par défaut) : français pris en charge, ancrage strict. Toute information absente de la source baisse le score, d'où le glossaire fourni dans le dossier.
- Niveau Standard : tolère mieux la reformulation, mais exige l'inférence interrégionale du garde-fou. Disponibilité dans le compte de l'atelier non vérifiée.
- Limites : 100 000 caractères pour la source, 1 000 pour la requête, 5 000 pour la réponse. L'explication est donc plafonnée en longueur.
- Démarrer en mode détection (scores affichés, sans blocage), calibrer les seuils sur le jeu de scénarios fixes, puis décider du blocage.

**Modèles :** commencer avec le même modèle peu coûteux pour les deux agents. L'analyste exige des appels d'outils fiables, l'explicateur un bon français et le respect d'un format. Ne séparer les modèles que si le jeu de scénarios fixes le justifie. Modèles actifs et prise en charge du choix d'outil forcé à vérifier dans le compte.

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
  - contrôle et preuves : `governance.py`, `evidence.py` (registre, catalogue de limites) ;
  - explication : `explanation_brief.py` (dossier, facteurs classés, glossaire), `explanation_validator.py`, `explanation_fallback.py` (gabarits par niveau) ;
  - agents : `agent_tools.py`, `analyst_agent.py`, `explainer_agent.py`, `analysis_pipeline.py` (enchaînement des six étapes, cache par niveau), `bedrock_client.py` (Converse, garde-fou, nouvelles tentatives), `prompts/` (un prompt par agent, versionné) ;
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
| Agent analyste Bedrock, registre, dossier d'explication, trace à six étapes | Agentique et explicabilité, AWS |
| Agent explicateur (idée d'Ibrahima), validateur, repli à gabarit | Agentique et explicabilité, AWS |
| Garde-fou et traces S3 | AWS |
| Profil par cases, idée par sélecteurs, panneau "Sources et méthode", avertissement | UX/UI |
| Deux niveaux d'explication (novice et pro), générés par l'explicateur seul | UX/UI, explicabilité |
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
| 3 | Bascule novice, pro : seul l'explicateur est relancé, le texte change, les chiffres restent. La trace montre "ce que l'explicateur a vu" | MVP |
| 4 | Clic sur un chiffre : calcul, source, date, limites. Puis une requête refusée par le garde-fou, et le score d'ancrage du texte | MVP |
| 5 | Mateo et une annonce de la Banque du Canada | Extension 1 |

## Feuille de route

1. **Décisions.** Répondre aux questions ouvertes, vérifier le compte AWS et les modèles actifs, obtenir l'accord d'un mentor pour les données.
2. **Socle de calcul.** Chargement avec `as_of`, alignement, devises, métriques, simulation avant/après, tests.
3. **Profils et gouvernance.** Trois personas, catalogue de règles, statuts, marges, tests.
4. **Première démo de bout en bout.** Robert et TSLA, dans cet ordre : dossier d'explication et repli à gabarit (la page fonctionne sans modèle), validateur et ses tests, agent analyste avec `submit_analysis`, puis agent explicateur avec un nouvel essai et le cache. Page avec avertissement.
5. **Interface.** Cases du profil, sélecteurs de l'idée, radiographie, deux profils côte à côte, panneau de preuves, niveaux d'explication.
6. **AWS.** Garde-fou testé (requêtes permises et refusées), contrôle d'ancrage en mode détection puis seuils calibrés sur le jeu de scénarios fixes, interventions et scores visibles dans la trace, traces sur S3.
7. **ESG minimal et fausse diversification.** Scénarios de Mateo et d'Amira.
8. **Gel du MVP et enregistrement d'une première vidéo.** Avant toute extension. Si l'explicateur ne passe pas le jeu de scénarios fixes à cette date, livrer le repli à gabarit pour deux niveaux et garder l'explicateur pour le troisième.
9. **Extensions**, dans l'ordre ci-dessus, selon le temps restant.
10. **Livrables.** README, documentation technique, one pager, vidéo finale.

## Risques

- **Dérive du périmètre :** 12 cas d'usage, c'est trop. Geler le MVP avant les extensions.
- **Compte AWS temporaire :** enregistrer la vidéo pendant qu'il est actif.
- **Quotas partagés :** modèle peu coûteux, tours bornés, nouvelles tentatives espacées, niveaux générés à la demande, cache des textes par niveau. Pire cas par analyse : deux niveaux avec un nouvel essai chacun, soit quatre appels explicateur et quatre contrôles de garde-fou.
- **Second agent perçu comme décoratif :** montrer ce qu'il change (dossier fermé, bascule de niveau sans recalcul, contrôle d'ancrage) et le présenter honnêtement comme un appel borné sans outil.
- **Perception "pas assez agentique" :** montrer dans la trace le choix des outils, la question de précision, les variantes repassées dans les outils et la séparation "agir, juger, expliquer".
- **Explicateur trop contraint, texte plat :** acceptable. La fidélité prime sur le style, et le repli donne le plancher.
- **Taux de rejet élevé du validateur :** chaque rejet coûte un appel. Le mesurer sur le jeu de scénarios fixes et corriger le prompt avant la démo. Le repli garantit un affichage.
- **Contrôle d'ancrage trop strict :** au niveau Classic, une analogie ou une définition hors dossier baisse le score. Glossaire fourni dans le dossier, mode détection d'abord, seuils calibrés.
- **Perte d'information utile :** ce qui n'est pas dans le dossier n'existe pas pour l'explicateur. C'est voulu. Si une nuance manque, on l'ajoute au registre par un outil, pas au prompt.
- **Deux prompts à maintenir :** versionnés dans `prompts/`, version incluse dans la clé de cache et dans la trace.
- **Promesse "zéro hallucination" :** ne pas la faire. Présenter le tableau des garanties.
- **Seuils arbitraires :** les présenter comme des hypothèses réglables.
- **Table ESG contestable :** rester factuel et daté. Les libellés des preuves ESG entrent dans le dossier : ils sont rédigés par l'équipe, pas copiés d'une source.
- **Montants en dollars lus comme une prévision :** toujours écrire "perte historique observée sur telle période, appliquée au capital fictif". Formule portée par le gabarit du registre, pas par le modèle.
- **Analogies du niveau novice :** tirées du glossaire, sans chiffre, sinon rejetées par le validateur.
- **Rejeu :** l'explicateur connaît la suite, comme tout modèle. En rejeu, repli à gabarit fixe.

## Décisions de l'équipe (14 novembre 2026)

| Sujet | Décision |
| --- | --- |
| Équipe | 4 personnes |
| Temps disponible | Le compte Workshop Studio expire environ 1 jour et 20 heures après le 14 novembre en début d'après-midi, soit vers le 16 novembre en matinée. Vidéo à enregistrer avant |
| Hébergement | Local : l'interface tourne sur un poste de l'équipe et appelle Bedrock. Pas d'hébergement sur AWS ni de Lambda |
| Données sur AWS | Le mentor autorise le téléversement des CSV dans le compte |
| Agents | Deux agents : analyste et explicateur, aux conditions décrites plus haut |
| Saisie | Cases et sélecteurs uniquement pour le MVP (idée de Samer) |
| Niveaux d'explication | Deux : novice et pro |
| Nouvelles libres et scénarios hypothétiques | Écartés pour le moment |

Modèles Bedrock et options du garde-fou : suivre la section AWS de CLAUDE.md et vérifier directement dans le compte.

## Questions ouvertes

1. Date limite et heure exacte de remise ? (Non trouvée dans l'énoncé ni dans la présentation : l'énoncé renvoie aux consignes logistiques.)
2. Répartition des blocs entre les 4 personnes (socle de calcul, agents et AWS, interface, données ESG et livrables) ?
3. Streamlit pour l'interface ? Interface en français ?
4. Qui monte la table ESG, et pour quels titres en premier ?
5. Accepte-t-on le dossier racine `app/` et les seuils comme hypothèses réglables ?
6. Qui rédige le glossaire et les textes fixes des limites pour les niveaux novice et pro ?
7. Annonces planifiées : à abandonner faute de temps ?
8. Accepte-t-on d'écarter le cas "comment en profiter ?" ?
