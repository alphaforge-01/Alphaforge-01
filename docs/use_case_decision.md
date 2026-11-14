# Choix du cas d'usage

Statut : **proposition à valider par l'équipe**. Rien n'est choisi tant que l'équipe n'a pas tranché (voir CLAUDE.md, section "Exigences du projet et décisions"). Les notes ci-dessous sont un jugement, pas une mesure.

Cette version fusionne la proposition initiale (cas A) avec les idées de Samer et d'Ibrahima, dont l'agent explicateur séparé et les scénarios hypothétiques fournis par l'équipe, tous deux proposés par Ibrahima. Le tableau "Ce qui change" résume les arbitrages.

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
| Nouvelles | Recadrées en scénarios hypothétiques écrits et étiquetés par l'équipe : ni recherche en ligne, ni vérification, le système reste dans l'hypothèse. Extension 1 | Ibrahima (recadrage), arbitrage (conditions) |
| Canaux d'exposition | Liste fermée. La table canal vers actifs est une hypothèse de l'équipe, lue par le code, jamais déduite par un modèle | Ibrahima, arbitrage |
| Épisodes comparables | Règle déterministe sur un facteur observable de nos données. Pas de choc appliqué comme multiplicateur | arbitrage |
| Annonces planifiées | Conservées comme complément (événements officiels datés), reculées en extension 3 | Ibrahima |
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
| 3. "Autre contrainte" (optionnel) | Texte libre, par exemple "pas de pétrole" | L'agent analyste propose une règle du catalogue, l'utilisateur confirme ou refuse |
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
| Novice | Mots simples, montants en dollars, une analogie sans chiffre tirée du glossaire | Chiffres, statuts, limites, ordre des sections |
| Intermédiaire | Termes financiers, définitions tirées du glossaire au premier usage | Chiffres, statuts, limites, ordre des sections |
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
| Scénario par identifiant | Les outils de scénario prennent un `scenario_id`. Les canaux viennent de la table de l'équipe ou d'une confirmation de l'utilisateur, jamais du modèle | Que les étiquettes de l'équipe soient "les bonnes" (ce sont des hypothèses) |
| Fait, observation, hypothèse séparés | Exposition (fait), épisodes passés (observation) et scénario (hypothèse) ont chacun leur type de preuve et leur encadré | Que le lecteur ne lise pas l'observation comme une prévision |

Risques résiduels assumés :

- **Formulation qualitative trompeuse** ("rassurant", "solide"). Mesures : qualificatifs par seuil, glossaire fermé, liste de termes interdits, contrôle d'ancrage, relecture d'un jeu de scénarios fixes avant la démo.
- **Emphase à l'intérieur d'un emplacement.** L'ordre global est fixé, pas le poids des mots dans une phrase. Mesure : relecture du jeu fixe.
- **Connaissances du modèle hors données** (par exemple une remarque sur une entreprise). Mesures : consigne stricte, contrôle d'ancrage, relecture.
- **Motif d'une variante.** L'explicateur ne sait pas pourquoi l'analyste l'a proposée. Mesure : motif transmis sous forme de code fermé (`reduce_weight`, `change_funding_source`, `spread_across_existing`), jamais deviné.
- **Sujet du scénario connu du modèle.** L'explicateur peut ajouter une conséquence "connue" (par exemple l'effet des taux sur l'immobilier). Mesures : il ne reçoit qu'un libellé de canal généré par le code, emplacement à phrase encadrée, contrôle d'ancrage, relecture du jeu fixe.

## Scénarios hypothétiques et annonces planifiées

Ibrahima propose de recadrer le cas "impact d'une nouvelle" : l'équipe fournit elle-même la nouvelle. Vraie ou fausse, peu importe : c'est une hypothèse, et le système reste dans ce cadre pour décrire ce qu'elle toucherait dans le portefeuille fictif. Aucune recherche en ligne, aucune vérification des faits.

Recommandation : **l'adopter sous conditions, en extension 1**. Les annonces planifiées restent un complément (extension 3).

### Ce que le recadrage règle

| Objection à la nouvelle libre collée | Réponse du scénario fourni par l'équipe | Reste à surveiller |
| --- | --- | --- |
| Licence du texte de presse | Texte original de l'équipe, jamais copié ni paraphrasé d'un article | Discipline de rédaction, entrée dans `sources.md` |
| Datation et anticipation | Le scénario n'est pas un fait daté : c'est une hypothèse posée à la date `as_of` | L'équipe écrit ses scénarios en connaissant le passé : limite affichée |
| Canal d'exposition déduit par le modèle | Canaux étiquetés par l'équipe dans une liste fermée | Les étiquettes sont des hypothèses, affichées comme telles |
| Comparables subjectifs | Règle déterministe sur un facteur observable, nombre d'observations affiché | Peu d'observations, une seule fenêtre de 5 ans |

### Règles de rédaction d'un scénario

- Écrit par l'équipe, en français, deux phrases au plus, ton neutre.
- Porte sur un canal macro, une devise, un secteur ou une classe d'actifs. **Jamais sur une entreprise réelle ni sur une personne réelle** : pas de fausse nouvelle sur un émetteur, et aucun comparable calculable pour un événement propre à une entreprise.
- Aucune date réelle, aucun chiffre de marché inventé présenté comme un fait.
- Champs : `scenario_id`, `title`, `summary`, `channels` (canal, direction, intensité), `persistence` (`shock` ou `regime`), `author`, `written_on`, `fictional: true`.
- Un scénario dont un canal est hors liste, ou dont la direction ou l'intensité manque, est refusé au chargement (test).

### Canaux : liste fermée, table de l'équipe

| Canal | Directions | Facteur observable (nos données) | Actifs déclarés exposés | Phase |
| --- | --- | --- | --- | --- |
| `rates_ca` | hausse, baisse | Taux du Canada à 2 ans (`BD.CDN.2YR.DQ.YLD`), variation en points | FNB obligataires (XBB.TO, ZST.TO, AGG, TLT) | Extension 1 |
| `usd_cad` | hausse, baisse | `FXUSDCAD`, variation en % | Tous les actifs cotés en USD (fait mécanique) | Extension 1 |
| `crypto` | hausse, baisse | BTC-USD, variation en % | Classe `crypto` | Extension 1 |
| `tech` | hausse, baisse | QQQ, variation en % | Secteur "Information Technology", plus QQQ | Si le temps le permet |
| `equity_market` | hausse, baisse | SPY ou XIU.TO, variation en % | Actions et FNB d'actions | Si le temps le permet |
| `oil` | hausse, baisse | Aucun dans nos données. Demande une série publique du prix du pétrole (FRED, source EIA), à documenter | Secteur "Energy" | Extension 5 |
| `inflation`, `credit` | | Aucun facteur utilisable (mensuel révisé sans date de publication, pas de série d'écarts de crédit) | | Non pris en charge |

- La table vit dans `data/external/scenario_channels.json`. Chaque canal porte son facteur, ses seuils par intensité et sa règle de sélection des actifs (classe, secteur, devise ou liste de titres), avec une justification d'une ligne.
- La table est une **hypothèse de l'équipe**, affichée comme telle. Elle est contrôlée de deux façons :
  - par des tests : chaque canal sélectionne au moins un actif de l'univers, chaque titre cité existe, chaque facteur existe dans les données ;
  - par la **sensibilité mesurée** : corrélation des rendements mensuels de chaque actif avec le facteur, affichée à côté de la déclaration. Les écarts sont signalés ("déclaré exposé, sensibilité mesurée faible", "non déclaré, sensibilité mesurée élevée") et jamais corrigés en silence.
- Un canal sans facteur s'affiche "non pris en charge". Il n'est jamais remplacé par une estimation.

### Ce que le code calcule

1. **Exposition (un fait).** Part du portefeuille fictif placée dans les actifs exposés à chaque canal du scénario, en % et en dollars fictifs, avec la liste des titres. Aucune hypothèse de marché.
2. **Épisodes comparables (une observation du passé).**
   - Unité : le mois civil, sans chevauchement, sur le calendrier commun.
   - Épisode : un mois où le facteur a bougé dans la direction du scénario d'au moins le seuil de l'intensité choisie (par exemple hausse d'au moins 0,25 point du taux à 2 ans).
   - Mesure : rendement du portefeuille fictif en CAD pendant ces mois, poids actuels tenus constants.
   - Sortie : nombre d'épisodes, médiane, minimum, maximum, nombre de mois négatifs, en % et en dollars fictifs. La liste des mois est consultable. La médiane de tous les mois sert de repère.
   - Moins de 5 épisodes : "information insuffisante", sans chiffre.
   - Même mois pour le facteur et le portefeuille : aucun décalage, donc aucune prétention prédictive.
3. **Persistance `regime` (reprend le cas 7 "et si ça dure ?").** Le canal renvoie à un épisode daté de la table (par exemple le cycle de hausses du taux directeur de mars 2022 à juillet 2023), calculé par `get_historical_episode`.

Ordres de grandeur sur nos 60 mois (exploration ponctuelle, seuils provisoires, à recalculer par le code testé) : 10 mois de hausse d'au moins 0,25 point du taux à 2 ans (dont 8 en 2022 et 2023), 13 mois de hausse du USD/CAD d'au moins 1,5 %, 9 mois de baisse du bitcoin d'au moins 15 %.

**Ce qu'on ne fait pas :** multiplier une sensibilité par une ampleur supposée. L'intensité choisit un seuil dans le passé, elle ne fabrique pas un chiffre futur.

### Lecture par la gouvernance

- La gouvernance compare les épisodes au seuil de perte tolérée du profil (nouvelle règle du catalogue, seuil hypothèse de l'équipe) : "la perte mensuelle a dépassé le seuil du profil k fois sur n".
- Statut propre, "tension sous scénario", affiché dans une colonne séparée. Un scénario ne peut jamais produire un conflit ni modifier un statut de base : il est hypothétique.
- L'exposition au canal reste jugée par les règles de base (plafonds par classe et par secteur).
- En mode scénario, l'analyste ne propose aucune variante "pour se protéger" ou "pour en profiter". Les variantes restent liées à une idée de l'utilisateur.

### Parcours dans la chaîne

| Étape | Ce qui passe | Ce qui ne passe pas |
| --- | --- | --- |
| Interface | L'utilisateur choisit un scénario de la bibliothèque. Titre et résumé affichés tels quels dans un encadré "Scénario hypothétique, non vérifié" | Aucune recherche, aucune vérification |
| Analyste | `scenario_id`. Il appelle `get_scenario_exposure` et `get_scenario_episodes` | Il ne passe jamais un canal de son cru : le code résout l'identifiant |
| Registre | Preuves de type `scenario_exposure` (fait) et `scenario_episodes` (observation), avec facteur, seuil, période, n, limites rattachées | |
| Dossier d'explication | Libellé généré par le code à partir des étiquettes ("hausse marquée des taux canadiens"), preuves, statut sous scénario, limites | Le titre et le résumé du scénario n'y entrent pas |
| Explicateur | Un emplacement fixe "Sous ce scénario hypothétique", rédigé par renvois | Aucune conséquence hors registre, aucun nom d'entreprise hors dossier |
| Validateur | Rejet du futur et du conditionnel de prévision ("va", "devrait", "probable"), des termes "profiter" et "se protéger", de tout chiffre hors registre. Exige la mention du nombre d'épisodes | |
| Garde-fou | Sujets refusés et ancrage contre le dossier | |

Plus tard (extension 6), une nouvelle collée par l'utilisateur suit le motif du texte libre du profil : l'analyste **propose** des canaux de la liste fermée, l'utilisateur confirme, et un canal non confirmé n'est jamais utilisé. Le texte collé passe le garde-fou en entrée, n'est vu que par l'analyste et n'entre jamais dans le dossier.

### Limites affichées (texte fixe)

- scénario hypothétique, non vérifié, écrit par l'équipe ;
- canaux et table d'exposition : hypothèses de l'équipe ;
- description de mois passés, pas une prévision : le passé ne dit pas ce qui se produirait ;
- peu d'observations, concentrées dans un seul cycle (2022 et 2023 pour les hausses de taux) ;
- d'autres événements ont eu lieu les mêmes mois, aucune causalité affirmée ;
- pour `tech` et `crypto`, le facteur est lui-même un actif de l'univers.

### Annonces planifiées : le complément

| | Scénario hypothétique | Annonce planifiée |
| --- | --- | --- |
| Nature | Hypothèse tournée vers "et si" | Événements officiels datés du passé |
| Fenêtre | Le mois | Le jour de l'annonce et les 5 jours ouvrables suivants |
| Donnée à ajouter | Deux fichiers écrits par l'équipe | Calendrier saisi à la main depuis la source officielle |
| Lien | | Deuxième type de preuve pour le canal `rates_ca` |

**Ce que les annonces demandent en données :**

- Notre série du taux directeur (V39079) change **le lendemain** de l'annonce : elle montre 20 changements, le premier le 2022-03-03. Les décisions de maintien n'y laissent aucune trace.
- Il faut donc un fichier `data/external/scheduled_announcements.csv` : type d'annonce, date et heure d'annonce, période de référence, décision (hausse, baisse, maintien), valeur, URL, date d'extraction.
- Étape 1 : décisions de taux de la Banque du Canada (8 par an, environ 40 sur la fenêtre). Saisie manuelle depuis le calendrier officiel.
- Étape 2, si le temps le permet : publications de l'inflation, avec les **dates de publication** et la limite sur les valeurs révisées.

**Ce que l'outil calcule :** le rendement du portefeuille fictif le jour de l'annonce et sur les 5 jours ouvrables suivants, pour toutes les annonces passées du même type, avec la médiane, l'étendue et le nombre d'observations. Mêmes limites : peu d'observations, autres événements le même jour, aucune causalité, description du passé.

## Rejeu à une date passée : discipline requise

Le rejeu (idée d'Ibrahima) est une extension. Sa discipline est posée dès le socle : toutes les fonctions de chargement et tous les outils acceptent un paramètre `as_of`, et aucune donnée postérieure n'est lue.

| Piège avec nos données | Règle |
| --- | --- |
| Macro mensuelle datée au mois de référence | Colonne `available_from` : date de publication réelle, sinon délai prudent documenté |
| Valeurs FRED révisées | Limite affichée, ou premières publications si on les ajoute |
| `adj_close` rétro-ajusté depuis 2026 | En rejeu, n'utiliser que des rendements, jamais de niveaux de prix. Les montants viennent du capital fictif |
| Biais du survivant | L'univers a été choisi en 2026. Le rejeu ne montre pas "ce qu'on aurait vu à l'époque" : limite affichée en permanence |
| Preuves ESG et annonces | Filtrées par date de publication antérieure à `as_of` |
| Scénarios hypothétiques | Épisodes limités aux mois terminés avant `as_of`. Seuils lus dans la table, jamais recalculés sur des données postérieures |
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
| 6. Impact d'une nouvelle | Extension 1, recadrée par Ibrahima : scénario hypothétique fourni par l'équipe, canaux étiquetés. Nouvelle collée par l'utilisateur avec canaux confirmés : extension 6. Annonces planifiées : extension 3 |
| 7. Scénarios "et si ça dure ?" | Fusionné dans l'extension 1 : persistance `regime`, qui renvoie à un épisode daté |
| 8. "Comment en profiter ?" | Pas une fonction. Requête refusée dans les tests du garde-fou, y compris posée après un scénario. Aucune variante proposée en mode scénario |
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
- **Un scénario n'entre dans le dossier que par ses étiquettes.** L'explicateur voit le libellé du canal généré par le code, les preuves et le statut sous scénario. Il ne voit ni le titre, ni le résumé, ni un texte collé.

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
| `propose_profile_rule` | Règle du catalogue proposée à partir d'un texte libre, à confirmer | MVP |
| `analyze_portfolio` | Radiographie : volatilité, perte maximale, concentration, exposition USD/CAD | MVP |
| `get_asset_facts` | Rendement et volatilité annualisés sur une période explicite, perte maximale, durée de récupération | MVP |
| `simulate_portfolio_change` | Avant/après en CAD : poids, volatilité, concentration par titre, secteur, classe d'actifs | MVP |
| `get_diversification` | Corrélations, groupes d'actifs qui bougent ensemble, exposition réelle par secteur | MVP |
| `get_historical_episode` | Comportement pendant un épisode daté (par exemple 2022), en pourcentage et en dollars fictifs | MVP |
| `get_esg_evidence` | Preuves datées, ou "aucune preuve disponible" | MVP |
| `check_governance` | Statut et marge par règle | MVP |
| `submit_analysis` | Clôt l'analyse : idée comprise, variantes avec motif en code fermé, preuves à mettre en avant, demandes non prises en charge | MVP |
| `get_scenario_exposure` | Pour un `scenario_id` : canaux, actifs exposés, part du portefeuille fictif en % et en dollars, écart entre exposition déclarée et sensibilité mesurée | Extension 1 |
| `get_scenario_episodes` | Pour un `scenario_id` : mois passés où le facteur a franchi le seuil, rendement du portefeuille fictif (n, médiane, étendue, mois négatifs), ou "information insuffisante" | Extension 1 |
| `get_announcement_reactions` | Réaction du portefeuille aux annonces passées d'un même type | Extension 3 |
| `propose_scenario_channels` | Canaux de la liste fermée proposés à partir d'un texte collé, à confirmer par l'utilisateur | Extension 6 |

### Trace visible

Six étapes, chacune avec une étiquette "agent" ou "code" :

| Étape | Acteur | Ce qui est affiché |
| --- | --- | --- |
| 1. Analyse | Agent analyste (Bedrock) | Idée comprise, règles confirmées, scénario choisi (identifiant, canaux, origine : équipe ou confirmé par l'utilisateur), outils appelés (nom, paramètres, numéro de preuve), variantes proposées, modèle, nombre de tours |
| 2. Gouvernance | Code | Statut, seuil et marge par règle. Colonne séparée "sous scénario" |
| 3. Dossier | Code | Preuves retenues, ordre des facteurs, limites obligatoires. Bouton "Ce que l'explicateur a vu" |
| 4. Explication | Agent explicateur (Bedrock) | Niveau, modèle, essai 1 ou 2, texte lu dans le cache ou généré |
| 5. Validation | Code | Références vérifiées, motifs de rejet, repli utilisé ou non |
| 6. Garde-fou | Bedrock Guardrails | Sujets refusés, scores d'ancrage et de pertinence, action prise |

Les deux agents sont visuellement distincts et la frontière est lisible : l'analyste a des outils et pas de plume, l'explicateur a une plume et pas d'outil. Le raisonnement interne des modèles n'est pas exposé. La trace complète (sans secret) est enregistrée sur S3.

### Hypothèses affichées comme telles

- seuils par profil, réglables par curseurs ;
- portefeuilles de départ, fictifs et modifiables ;
- scénarios hypothétiques : texte, canaux, direction et intensité choisis par l'équipe ;
- table canal vers actifs et seuils par intensité : hypothèses de l'équipe, avec la sensibilité mesurée en regard ;
- épisodes comparables : mois civils, poids actuels tenus constants ;
- devise de base : CAD ;
- alignement sur les jours ouvrables communs, crypto ramenée à ce calendrier, taux de change reporté en avant ;
- limites : biais du survivant, fenêtre de 5 ans, un seul épisode de baisse marquée (2022), volatilité comme indicateur parmi d'autres.

### Données à ajouter

| Fichier | Contenu | Phase |
| --- | --- | --- |
| `data/external/investor_profiles.json` | Les trois personas au format profil, portefeuilles fictifs | MVP |
| `data/external/esg_evidence.csv` | Une ligne par affirmation : URL, date de publication, date d'extraction. Commencer par les titres des scénarios de démo | MVP |
| `data/external/hypothetical_scenarios.json` | 4 à 6 scénarios fictifs écrits par l'équipe : identifiant, titre, résumé, canaux (direction, intensité), persistance, auteur, date de rédaction | Extension 1 |
| `data/external/scenario_channels.json` | Liste fermée des canaux : facteur observable, seuils par intensité, règle de sélection des actifs, épisode de régime, justification | Extension 1 (structure posée au socle) |
| `data/external/scheduled_announcements.csv` | Calendrier des annonces (voir plus haut) | Extension 3 |
| `data/external/market_drivers.csv` | Prix du pétrole (série publique, conditions à vérifier), produit par un script | Extension 5 |

Entrées de `sources.md` pour les deux fichiers de scénarios : source "rédigé par l'équipe, contenu fictif", pas d'URL, date de rédaction, traitement "aucun", limites "hypothèses non vérifiées, choisies en connaissant l'historique", redistribution permise (contenu original). Aucun texte de presse n'y est copié.

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
  - extensions : `scenarios.py` (bibliothèque, canaux, exposition, épisodes comparables), `scheduled_events.py`.
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
| Trois niveaux d'explication, générés par l'explicateur seul | UX/UI, explicabilité |
| ESG minimal pour Mateo | Qualité |

### Extensions, dans l'ordre

1. Scénarios hypothétiques fournis par l'équipe (recadrage d'Ibrahima) : trois canaux (`rates_ca`, `usd_cad`, `crypto`), 4 à 6 scénarios, exposition et épisodes comparables, persistance `regime`. Durée bornée : une journée.
2. Rejeu à une date passée, puis révélation de la suite.
3. Annonces planifiées : décisions de taux de la Banque du Canada, comme deuxième preuve du canal `rates_ca`.
4. Hébergement sur AWS, puis outils sur Lambda.
5. Canaux `tech`, `equity_market` et `oil`, publications de l'inflation, chevauchement réel des FNB.
6. Nouvelle collée par l'utilisateur, canaux proposés puis confirmés.

### Scènes de démo (vidéo de 5 minutes)

| Scène | Contenu | Phase |
| --- | --- | --- |
| 1 | Robert veut 25 % de TSLA : tension nommée, contrefactuel, variante | MVP |
| 2 | Même demande pour Amira : autre verdict, même mécanisme | MVP |
| 3 | Bascule novice, intermédiaire, pro : seul l'explicateur est relancé, le texte change, les chiffres restent. La trace montre "ce que l'explicateur a vu" | MVP |
| 4 | Clic sur un chiffre : calcul, source, date, limites. Puis une requête refusée par le garde-fou, et le score d'ancrage du texte | MVP |
| 5 | Scénario hypothétique "hausse marquée des taux canadiens" appliqué à Robert puis à Amira. Encadré "hypothétique, non vérifié", exposition (fait), mois comparables avec leur nombre (observation), lecture sous scénario. Puis "comment en profiter ?" : refus du garde-fou | Extension 1 |

Intérêt de la scène 5 : le portefeuille "prudent" de Robert est probablement le plus exposé aux taux, ce qui illustre "la volatilité est un indicateur parmi d'autres". À confirmer une fois les portefeuilles fictifs fixés.

## Feuille de route

1. **Décisions.** Répondre aux questions ouvertes, vérifier le compte AWS et les modèles actifs, obtenir l'accord d'un mentor pour les données.
2. **Socle de calcul.** Chargement avec `as_of`, alignement, devises, métriques, simulation avant/après, rendements mensuels du portefeuille en CAD (réutilisés par les scénarios), tests.
3. **Profils et gouvernance.** Trois personas, catalogue de règles (dont le seuil de perte tolérée), statuts, marges, tests.
4. **Première démo de bout en bout.** Robert et TSLA, dans cet ordre : dossier d'explication et repli à gabarit (la page fonctionne sans modèle), validateur et ses tests, agent analyste avec `submit_analysis`, puis agent explicateur avec un nouvel essai et le cache. Page avec avertissement.
5. **Interface.** Cases du profil, sélecteurs de l'idée, radiographie, deux profils côte à côte, panneau de preuves, niveaux d'explication.
6. **AWS.** Garde-fou testé (requêtes permises et refusées), contrôle d'ancrage en mode détection puis seuils calibrés sur le jeu de scénarios fixes, interventions et scores visibles dans la trace, traces sur S3.
7. **ESG minimal et fausse diversification.** Scénarios de Mateo et d'Amira.
8. **Gel du MVP et enregistrement d'une première vidéo.** Avant toute extension. Si l'explicateur ne passe pas le jeu de scénarios fixes à cette date, livrer le repli à gabarit pour deux niveaux et garder l'explicateur pour le troisième.
9. **Extensions**, dans l'ordre ci-dessus, selon le temps restant. Pour l'extension 1, dans cet ordre : table des canaux et ses tests, exposition, épisodes comparables avec le test `as_of`, lecture par la gouvernance, emplacement et gabarit de repli, deux outils de l'analyste, règles du validateur, tests du garde-fou, encadré de l'interface, puis la scène 5.
10. **Livrables.** README, documentation technique, one pager, vidéo finale.

## Risques

- **Dérive du périmètre :** 12 cas d'usage, c'est trop. Geler le MVP avant les extensions.
- **Compte AWS temporaire :** enregistrer la vidéo pendant qu'il est actif.
- **Quotas partagés :** modèle peu coûteux, tours bornés, nouvelles tentatives espacées, niveaux générés à la demande, cache des textes par niveau. Pire cas par analyse : trois niveaux avec un nouvel essai chacun, soit six appels explicateur et six contrôles de garde-fou.
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
- **Scénario lu comme une prévision :** phrase encadrée par le gabarit ("dans n mois passés où ..."), futur et conditionnel de prévision rejetés par le validateur, repère "tous les mois" affiché, limite fixe. Pas de choc multiplié par une ampleur.
- **Scénario pris pour une vraie nouvelle :** on écrit "scénario hypothétique", jamais "nouvelle" ou "actualité". Encadré distinct des faits, aucune entreprise ni personne réelle, aucune date réelle.
- **Connaissances du modèle sur le sujet :** l'explicateur ne reçoit que le libellé du canal. Relecture du jeu de scénarios fixes.
- **Dérive "comment en profiter ?" ou "comment se protéger ?" :** aucune variante en mode scénario, termes rejetés par le validateur, requête refusée testée au garde-fou.
- **Sujet refusé "prédiction" trop large :** il peut bloquer une demande de scénario légitime. Tester des paires permises et refusées ("que montrent les mois passés de hausse des taux ?" contre "que va faire mon portefeuille ?") et ajuster la définition.
- **Peu d'épisodes, groupés dans un cycle :** n affiché, plancher de 5, liste des mois consultable, résultat au seuil voisin montré comme test de sensibilité.
- **Table des canaux contestable :** présentée comme hypothèse, justification par canal, sensibilité mesurée en regard, écarts signalés.
- **Scénarios choisis en connaissant le passé :** limite affichée. Ne pas choisir les scénarios pour leur effet spectaculaire : couvrir les deux directions.
- **Facteur circulaire :** pour `tech` et `crypto`, le facteur est un actif de l'univers. Limite affichée.
- **Dérive du périmètre par les scénarios :** trois canaux et une journée. Les autres canaux attendent l'extension 5.

## Questions ouvertes

1. Date limite et consignes de dépôt ?
2. Taille de l'équipe et répartition (socle de calcul, agent et AWS, interface, données ESG et annonces, livrables) ?
3. Date de fin du compte Workshop Studio ? Quels modèles Bedrock sont actifs, lesquels acceptent le choix d'outil forcé, et le niveau Standard du garde-fou (inférence interrégionale) est-il disponible ?
4. Streamlit pour l'interface ? Interface en français ?
5. Hébergement sur AWS exigé, ou Bedrock, garde-fou et S3 suffisent-ils ? Sinon, Lambda remonte-t-il dans le MVP ?
6. Un mentor autorise-t-il le téléversement des CSV dans le compte ?
7. Qui monte la table ESG, et pour quels titres en premier ?
8. Accepte-t-on le dossier racine `app/` et les seuils comme hypothèses réglables ?
9. Ibrahima : l'agent explicateur est adopté sous conditions (dossier seul, pas d'outil, pas de verdict, limites affichées par le code, emplacements fixes). Ces conditions te conviennent-elles ? Avec un analyste et un explicateur, reste-t-il un rôle de ta proposition à quatre agents qui ne serait couvert ni par un agent ni par le code ?
10. Samer et Ibrahima : la combinaison "cases d'abord, texte libre confirmé ensuite" convient-elle ?
11. Trois niveaux d'explication dès le MVP, ou deux (novice et pro) pour commencer ? Chaque niveau coûte un appel explicateur, un contrôle de garde-fou, un gabarit de repli et une entrée de glossaire. Qui rédige le glossaire et les textes fixes des limites ?
12. Ibrahima : le recadrage des nouvelles est adopté sous conditions (canaux macro ou sectoriels seulement, aucune entreprise réelle, pas de choc multiplié par une ampleur, l'explicateur ne voit que le libellé du canal). Ces conditions te conviennent-elles ? Qui rédige les 4 à 6 scénarios et la table des canaux ?
13. Scénarios : extension 1 comme proposé, ou tranche minimale (exposition seule) dans le MVP ? Trois canaux pour commencer : `rates_ca`, `usd_cad`, `crypto` ?
14. Accepte-t-on la règle "seuil de perte tolérée" dans le catalogue, avec un statut plafonné à "tension sous scénario" ? Quels seuils par profil ?
15. Seuils d'intensité : valeurs fixes par facteur (par exemple 0,25 et 0,40 point pour le taux à 2 ans), ou quantiles calculés ? Les valeurs fixes sont plus simples à expliquer.
16. Annonces planifiées (extension 3) : qui saisit le calendrier de la Banque du Canada, et ses conditions d'utilisation permettent-elles de le versionner ?
17. Accepte-t-on de reporter la nouvelle collée par l'utilisateur en extension 6 et d'écarter le cas "comment en profiter ?" ?
