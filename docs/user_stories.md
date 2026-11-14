# User stories du MVP

Ce document traduit le périmètre de `docs/sprint_plan.md` (section 2) en user stories. Chaque story a une priorité (P1 obligatoire, P2 seulement si J4 est vert), les flux concernés et des critères d'acceptation vérifiables.

Flux : A Naoufal (données, métriques, outils), B Samer (profils, gouvernance, explication en code), C Godwin (agents, Bedrock, garde-fou), D Ibrahima (interface, démo).

Acteurs :

- **Utilisateur** : une personne qui explore l'outil avec un profil d'investisseur **fictif** (un persona ou un profil construit). Jamais ses données réelles.
- **Présentateur** : un membre de l'équipe qui joue la démo devant le jury ou pour la vidéo.
- **Jury** : la personne qui veut vérifier ce qui soutient un résultat.

## Vue d'ensemble

| ID | Story | Priorité | Flux | Scène de démo |
| --- | --- | --- | --- | --- |
| US-01 | Choisir un persona prérempli | P1 | B, D | 1, 2 |
| US-02 | Construire un profil fictif par cases | P1 | B, D | |
| US-03 | Voir la radiographie du portefeuille | P1 | A, B, D | 1 |
| US-04 | Soumettre une idée de placement | P1 | A, D | 1 |
| US-05 | Comparer avant et après | P1 | A, D | 1 |
| US-06 | Voir les tensions avec le profil | P1 | B, D | 1, 2 |
| US-07 | Savoir ce qui ferait changer le verdict | P1 | B, D | 1 |
| US-08 | Voir des variantes simulées | P1 | B, C, D | 1 |
| US-09 | Même demande, autre profil | P1 | B, D | 2 |
| US-10 | Lire l'explication en novice ou en pro | P1 | B, C, D | 3 |
| US-11 | Vérifier un chiffre | P1 | A, D | 4 |
| US-12 | Voir les limites et l'avertissement | P1 | B, D | toutes |
| US-13 | Suivre la trace des agents | P1 | C, D | 3 |
| US-14 | Voir le garde-fou refuser une demande | P1 | C, D | 5 |
| US-15 | Faire la démo même si Bedrock tombe | P1 | B, C | toutes |
| US-16 | Consulter les traces sur AWS | P1 | C | 5 |
| US-17 | Mateo : contrôle ESG | P2 | A, B, D | 6 |
| US-18 | Amira : fausse diversification | P2 | A, B, D | 6 |
| US-19 | Deux profils côte à côte | P2 | D | 2 |

## Profil

### US-01 : choisir un persona prérempli (P1, flux B et D)

**En tant qu'**utilisateur, **je veux** choisir Amira, Mateo ou Robert en un clic **afin de** tester l'outil sans remplir de formulaire.

Critères d'acceptation :

- Trois cartes affichent nom, âge, profil de risque, horizon et objectif de chaque persona.
- Un clic charge le profil, son portefeuille fictif et ses règles (`load_personas`).
- Le niveau d'explication par défaut suit l'expérience déclarée (intermédiaire ou avancé vers pro, débutant vers novice).
- Un badge "profil fictif" est visible.

### US-02 : construire un profil fictif par cases (P1, flux B et D)

**En tant qu'**utilisateur, **je veux** décrire un profil avec des cases et des curseurs **afin d'**analyser une situation qui n'est pas celle des personas.

Critères d'acceptation :

- Champs : objectif, horizon, tolérance au risque, expérience, préférence ESG, crypto permise ou non, plafond par titre, capital fictif.
- Aucun champ ne demande de donnée personnelle réelle (nom, revenu réel, compte). Un rappel "profil fictif" est affiché.
- Les réponses produisent des règles avec seuils (`build_profile_from_answers`). Chaque seuil est étiqueté "hypothèse de l'équipe".
- Une contradiction est signalée, par exemple "tolérance faible" avec "crypto permise et plafond élevé".
- Aucun texte libre dans le MVP.

## Analyse

### US-03 : voir la radiographie du portefeuille (P1, flux A, B et D)

**En tant qu'**utilisateur, **je veux** voir l'état de mon portefeuille fictif avant toute idée **afin de** savoir s'il correspond déjà à mon profil.

Critères d'acceptation :

- Affiche, en CAD : volatilité annualisée, perte maximale avec ses dates, durée de récupération, plus gros poids, poids par secteur et par classe d'actifs, exposition USD/CAD, part défensive.
- La période de calcul est affichée (par exemple "12 nov. 2021 au 12 nov. 2026").
- Chaque règle du profil a un statut : conforme, tension, conflit ou information manquante.
- Chaque chiffre vient du registre de preuves (voir US-11).
- Calcul en moins de 2 secondes sur les données réelles.

### US-04 : soumettre une idée de placement (P1, flux A et D)

**En tant qu'**utilisateur, **je veux** formuler une idée avec des sélecteurs **afin de** voir son effet sans écrire de texte.

Critères d'acceptation :

- Sélecteurs : actif (parmi l'univers), poids visé, source des fonds (au prorata des positions ou depuis un titre précis).
- Des idées suggérées en un clic existent pour la démo, dont "25 % dans TSLA".
- Un poids hors de 0 à 100 % ou une source des fonds impossible est refusé avec un message clair.
- L'idée est stockée au format `InvestmentIdea`.

### US-05 : comparer avant et après (P1, flux A et D)

**En tant qu'**utilisateur, **je veux** comparer mon portefeuille avant et après l'idée **afin de** voir ce qu'elle change concrètement.

Critères d'acceptation :

- Les mêmes métriques que US-03 sont affichées côte à côte, avant et après, avec l'écart.
- Les montants en dollars sont présentés comme "perte historique observée sur telle période, appliquée au capital fictif", jamais comme une prévision.
- Les poids après l'idée totalisent 100 %.

### US-06 : voir les tensions avec mon profil (P1, flux B et D)

**En tant qu'**utilisateur, **je veux** voir quelles règles de mon profil l'idée met en tension ou en conflit **afin de** comprendre pourquoi elle me correspond ou non.

Critères d'acceptation :

- Étant donné Robert et l'idée "25 % dans TSLA", quand l'analyse se termine, alors au moins la règle de plafond par titre est en tension ou en conflit, et le statut global l'indique.
- Le système n'acquiesce jamais à une idée en conflit : il nomme la règle, la valeur et le seuil.
- Le verdict vient de la gouvernance en code. Il est identique d'une exécution à l'autre pour les mêmes entrées.
- Une valeur absente donne "information manquante", jamais "conforme".

### US-07 : savoir ce qui ferait changer le verdict (P1, flux B et D)

**En tant qu'**utilisateur, **je veux** connaître le poids à partir duquel mon idée deviendrait conforme **afin de** savoir jusqu'où je pourrais aller.

Critères d'acceptation :

- Pour chaque règle en tension ou en conflit liée au poids, le contrefactuel affiche "conforme à X % ou moins", calculé par balayage du poids par pas de 1 point.
- Si aucun poids n'est conforme, l'interface le dit explicitement.
- La marge restante est affichée pour les règles conformes.

### US-08 : voir des variantes simulées (P1, flux B, C et D)

**En tant qu'**utilisateur, **je veux** voir une ou deux variantes de mon idée qui réduisent les tensions **afin d'**explorer d'autres options sans qu'on me dise quoi acheter.

Critères d'acceptation :

- Au plus deux variantes, chacune avec un motif parmi : réduire le poids, changer la source des fonds, répartir sur les positions existantes.
- Chaque variante repasse par les mêmes outils et la même gouvernance, et affiche ses statuts.
- Les variantes sont présentées comme des simulations, pas comme des recommandations.
- En mode `offline`, les variantes viennent de la séquence scriptée.

### US-09 : même demande, autre profil (P1, flux B et D)

**En tant que** présentateur, **je veux** soumettre la même idée pour Amira après Robert **afin de** montrer que le verdict dépend du profil.

Critères d'acceptation :

- Étant donné "25 % dans TSLA", le verdict d'Amira diffère de celui de Robert, ou les mêmes règles ont des marges différentes.
- Les chiffres de l'actif (volatilité, perte maximale de TSLA) sont identiques pour les deux : seules les règles changent.
- Changer de profil conserve l'idée saisie.

## Explication

### US-10 : lire l'explication en novice ou en pro (P1, flux B, C et D)

**En tant qu'**utilisateur, **je veux** choisir le niveau d'explication **afin de** comprendre le résultat avec des mots adaptés à mon expérience.

Critères d'acceptation :

- Deux niveaux : novice (mots simples, montants en dollars, définitions du glossaire) et pro (termes techniques, méthode et paramètres).
- Basculer de niveau ne relance que l'explicateur. Les chiffres, les statuts et les limites sont identiques aux deux niveaux.
- La seconde bascule vers un niveau déjà vu est instantanée (cache).
- Si l'explicateur échoue ou si le validateur rejette deux fois son texte, le gabarit s'affiche avec les mêmes chiffres, et la trace l'indique.
- Le texte ne contient aucun chiffre écrit par le modèle : seulement des renvois remplacés par les valeurs du registre.

### US-11 : vérifier un chiffre (P1, flux A et D)

**En tant que** membre du jury, **je veux** cliquer sur n'importe quel chiffre **afin de** voir d'où il vient.

Critères d'acceptation :

- Le clic ouvre : libellé, valeur, outil qui l'a calculé, source des données, période, devise, transformation, nombre d'observations et limites rattachées.
- Tous les chiffres de la radiographie, de la comparaison et de l'explication sont cliquables.
- Un panneau "Sources et méthode" regroupe les sources (`data/raw/sources_metadata.csv`) et les hypothèses de calcul.

### US-12 : voir les limites et l'avertissement (P1, flux B et D)

**En tant qu'**utilisateur, **je veux** voir clairement ce que le résultat ne dit pas **afin de** ne pas le prendre pour un conseil ou une prévision.

Critères d'acceptation :

- L'avertissement "simulation à but éducatif, pas un conseil financier personnalisé" est visible sur chaque écran.
- Les limites obligatoires (biais du survivant, fenêtre de 5 ans, volatilité indicateur parmi d'autres, seuils hypothétiques) sont affichées par le code, avec un texte fixe par niveau.
- Faits, hypothèses et variantes simulées sont visuellement séparés.

### US-13 : suivre la trace des agents (P1, flux C et D)

**En tant que** membre du jury, **je veux** voir les étapes qui ont produit le résultat **afin de** comprendre le rôle de chaque agent.

Critères d'acceptation :

- Six étapes : analyse, gouvernance, dossier, explication, validation, garde-fou, chacune étiquetée "agent", "code" ou "garde-fou".
- L'étape d'analyse liste les outils appelés, leurs paramètres et les numéros de preuve produits.
- Un bouton "Ce que l'explicateur a vu" affiche le dossier d'explication transmis.
- Le raisonnement interne des modèles n'est jamais affiché.
- En mode `offline`, l'étape d'analyse est étiquetée "code".

## Garde-fous et fiabilité

### US-14 : voir le garde-fou refuser une demande (P1, flux C et D)

**En tant que** présentateur, **je veux** déclencher des demandes interdites **afin de** montrer que l'outil refuse le conseil personnalisé et la prédiction.

Critères d'acceptation :

- Un panneau propose des requêtes prédéfinies, permises et refusées, par exemple "Que va faire mon portefeuille l'an prochain ?", "Achète TSLA pour moi", "Comment en profiter ?".
- Les requêtes refusées affichent le refus et le sujet en cause. Les requêtes permises passent.
- Le score d'ancrage du texte de l'explication est affiché à l'étape garde-fou de la trace.
- Aucun outil ne permet de passer un ordre ni de se connecter à un courtier.

### US-15 : faire la démo même si Bedrock tombe (P1, flux B et C)

**En tant que** présentateur, **je veux** que l'application fonctionne sans Bedrock **afin que** la démo ne dépende pas d'un quota ou d'un jeton expiré.

Critères d'acceptation :

- Le mode `offline` produit un résultat complet : outils réels, gouvernance, gabarit d'explication, trace.
- Une erreur Bedrock (limitation, jeton expiré) bascule vers le repli sans planter la page, et la trace le signale.
- Les tests automatisés n'appellent jamais AWS.

### US-16 : consulter les traces sur AWS (P1, flux C)

**En tant que** membre du jury, **je veux** que chaque analyse laisse une trace sur AWS **afin de** constater que l'intégration est réelle.

Critères d'acceptation :

- En mode `bedrock`, chaque analyse écrit une trace JSON dans un compartiment S3 privé, sans aucun secret.
- Le compartiment a les quatre options Block Public Access activées.
- Quelques traces sont copiées dans `outputs/reports/` avant l'expiration du compte.

## P2 (seulement si J4 est vert)

### US-17 : Mateo, contrôle ESG (P2, flux A, B et D)

**En tant que** Mateo, **je veux** savoir si un titre est lié à une controverse ESG **afin de** respecter mes préférences au-delà du rendement.

Critères d'acceptation :

- Étant donné Mateo et l'idée "ajouter XOM" ou "ajouter CNQ.TO", la règle ESG affiche une preuve datée et sourcée, ou "information manquante".
- L'absence de preuve n'est jamais présentée comme "conforme".
- Chaque preuve a son entrée dans `data/external/sources.md`, avec ses conditions d'utilisation.

### US-18 : Amira, fausse diversification (P2, flux A, B et D)

**En tant qu'**Amira, **je veux** voir si mes positions bougent ensemble **afin de** garder la diversification que je souhaite.

Critères d'acceptation :

- Étant donné Amira et l'idée "40 % crypto", l'outil affiche le poids du plus grand groupe d'actifs corrélés.
- La règle "plafond par groupe corrélé" passe en tension ou en conflit si le seuil est dépassé.
- La période et la méthode de corrélation sont affichées.

### US-19 : deux profils côte à côte (P2, flux D)

**En tant que** présentateur, **je veux** afficher deux profils sur la même page **afin de** comparer les verdicts d'un coup d'œil.

Critères d'acceptation :

- Deux colonnes, chacune avec son profil, ses statuts et son explication, pour la même idée.
- Les chiffres propres à l'actif sont identiques dans les deux colonnes.

## Définition de terminé (toutes les stories)

- Code en anglais, textes en français, ni tiret cadratin ni emoji.
- Tests du flux verts (`pytest tests/`), sauf pour l'interface, couverte par la liste de contrôle de `docs/demo_script.md`.
- Aucun chiffre affiché ne vient d'un modèle.
- Aucun secret dans le diff.
- PR relue et fusionnée par squash dans `main`.
