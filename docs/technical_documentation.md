# Documentation technique : AlphaForge AI

Équipe AlphaForge 01 (Naoufal, Samer, Godwin, Ibrahima), datathon PolyFinances AlphaForge AI 2026.

> Simulation éducative uniquement : profils, portefeuilles et montants fictifs, aucune transaction réelle, aucune connexion à un courtier, aucun conseil personnalisé. Les résultats décrivent le passé sur une période explicite et ne prévoient rien.

Ce document répond aux quatre attentes de l'énoncé (p. 15) : méthodes, modèles et technologies avec leur justification (section 2) ; sources, actifs, traitements et hypothèses (section 3) ; mécanisme d'explicabilité avec un exemple relié aux données et à la trace (section 4) ; validations, mise à l'épreuve, limites et améliorations (sections 5 et 6). L'installation et la reproduction sont dans le [README](../README.md).

## 1. Problème et réponse

**Question servie :** « Mon portefeuille fictif correspond-il à mon profil, et que change mon idée de placement ? »

L'outil est un **copilote de cohérence, pas un conseiller**. Il ne propose pas de portefeuille et ne prédit aucun rendement. Il prend un profil fictif et une idée (« porter TSLA à 25 % du portefeuille »), simule l'avant/après sur données historiques, vérifie l'idée contre les règles du profil et explique le verdict, chiffre par chiffre, avec ses sources.

Les trois personas de l'énoncé testent trois comportements, couverts par le même mécanisme (une tension entre une demande et un profil) :

| Persona | Ce que l'énoncé teste | Ce que montre l'outil |
| --- | --- | --- |
| Robert (risque faible à modéré, 3 à 5 ans) | Contester une demande incohérente avec le profil | 25 % de TSLA : **conflit** sur la concentration par actif, contrefactuel « conforme à 20 % ou moins », variante simulée à 17 % conforme ; tout cryptoactif est exclu de son profil : **conflit** dès 10 % de BTC-USD |
| Amira (risque élevé, 15 ans et plus) | « Risque élevé » ne veut pas dire « tout est permis » | 25 % de TSLA : **tension** sur la perte maximale historique ; 40 % de BTC-USD : **conflit** (plafond des cryptoactifs), avec un groupe de titres corrélés en tension |
| Mateo (modéré, forte préférence ESG) | Intégrer autre chose que le rendement et le risque | Deux verdicts séparés : le **verdict financier** (conforme pour TSLA 25 %, NVDA 15 % et XOM 15 %, conflit pour les cryptoactifs, exclus de son profil) et le **verdict ESG**, qui reste « information manquante » faute de preuve ESG, jamais « conforme ». Les preuves ESG sont un travail futur (section 6.3) |

## 2. Architecture, méthodes et technologies

### 2.1 Chaîne d'exécution

```
Interface Streamlit (app/), 5 pages
        |   message de la conversation : request_parsing (règles, sans modèle) -> idée, idée à confirmer,
        |   réponse du code (accueil, positions du portefeuille, définition du glossaire), question ou refus
        |   [en cours : interprète sur Bedrock pour les formulations libres ; agent pour les questions de profil]
        v
analysis_pipeline.run_analysis(profil, portefeuille, idée, as_of, mode)
  1. Analyse     agent analyste (Bedrock, outils)  ou séquence fixe (hors ligne)
        |          analyze_portfolio, simulate_portfolio_change, get_asset_facts
        |          + appels décidés par le code : simulation de contrôle, variantes, faits de l'actif seul
  2. Gouvernance code : statut et marge par règle, contrefactuel, verdicts financier et ESG séparés
  3. Dossier     code : registre de preuves numérotées, facteurs classés, contexte du profil, limites, glossaire
        |
analysis_pipeline.explain(résultat, niveau)
  4. Explication agent explicateur (Bedrock, sans outil, dossier seul, prompt explainer_v5)  ou gabarit ;
                 la phrase du contrefactuel est toujours écrite par le code
  5. Validation  code : rejette chiffre hors registre, renvoi inconnu, recommandation, prévision, lien, HTML
  6. Garde-fou   Bedrock Guardrails : sujets refusés, ancrage contre une source en phrases  ->  trace (S3 privé)
```

**Principe directeur : un agent agit, le code juge, un agent explique.** Aucun modèle ne calcule un chiffre ni ne décide d'un verdict. Chaque étape est visible dans la trace, avec son acteur (agent, code, garde-fou) ; chaque appel d'outil porte `caller` (`agent` ou `code`), affiché dans la colonne « Décidé par » de l'interface.

### 2.2 Composants et justification

| Composant | Nature | Rôle | Pourquoi ce choix |
| --- | --- | --- | --- |
| Conversation par règles (`request_parsing.py`) | Code déterministe testé, sans modèle | Traduit un message en idée (titre, poids visé, source des fonds) ; un poids écrit sans « % » (« 0,25 », « un quart ») ou une relance (« et à 10 % ? », sur la dernière idée analysée) devient une **idée à confirmer en un clic** ; répond par le code à une salutation, à « quels sont mes actifs ? » (positions du portefeuille fictif) et à « c'est quoi la volatilité ? » (définition du glossaire, au niveau choisi) ; demande ambiguë : une question ; demande interdite (ordre, conseil personnalisé, prédiction) : refus, même hors ligne et derrière une salutation | L'outil ne devine jamais l'idée ni le poids ; ce contrôle local complète le garde-fou sans le remplacer. Mesuré sur 60 phrases (section 5.1) |
| Outils de l'agent (`agent_tools.py`) | Code déterministe testé | Radiographie, simulation avant/après, faits d'un actif, **faits déclarés du profil** (`get_profile_facts` : objectif, horizon, tolérance, expérience, ESG, cryptoactifs, capital, recopiés en preuves citables de sujet `profile`, la capacité de perte signalée manquante et jamais déduite) ; chaque résultat porte ses preuves ; libellés en français (`asset_labels.py`) | L'énoncé et l'atelier demandent des calculs vérifiés : un modèle de langage peut confondre des notions financières. Les faits du profil deviennent citables par renvoi comme un chiffre |
| Agent analyste (`analyst_agent.py`) | Modèle sur Bedrock, API Converse avec appels d'outils, au plus 6 tours et 12 appels | Choisit les outils, comprend l'idée, propose au plus 2 variantes, met en avant au plus quatre preuves ; termine par un résultat structuré, sans prose | Seul rôle qui demande du jugement ; borné pour les quotas partagés et la lisibilité de la trace |
| Gouvernance (`governance.py`, `counterfactual.py`) | Code déterministe testé | Statut par règle (conforme, tension, conflit, information manquante), marge, contrefactuel par balayage du poids au point près ; verdict global, financier et ESG | Un verdict ne doit pas varier d'un appel à l'autre ; il doit être testable. Séparer l'ESG évite qu'une préférence non vérifiable masque le verdict financier |
| Registre de preuves (`evidence.py`) | Code | Numérote chaque chiffre (E1, E2...) avec valeur, affichage, période, devise, sources, transformation, limites | Base de l'explicabilité : tout chiffre affiché remonte à une preuve |
| Dossier et gabarit (`explanation_brief.py`, `explanation_fallback.py`) | Code | Seule entrée de l'explicateur : facteurs classés, faits de l'actif seul, contexte déclaré du profil (objectif, horizon, tolérance, ESG, cryptoactifs), glossaire et limites ; explication de repli sans modèle | L'explicateur ne voit ni le texte de l'utilisateur ni les données brutes : il ne peut parler que de ce qui a été calculé ou déclaré |
| Agent explicateur (`explainer_agent.py`, `prompts/explainer_v5.md`) | Modèle sur Bedrock, un appel sans outil, un nouvel essai au plus | Rédige en novice ou en pro, uniquement par renvois (`[E3]`, `[G1]`, `[T2]`) ; cite les faits de l'actif seul quand une règle est en tension ou en conflit ; s'appuie sur le contexte du profil. La phrase du contrefactuel est remplacée par celle du code | Séparer l'explication de l'analyse : changer de niveau ne relance que l'explicateur, les chiffres ne peuvent pas bouger |
| Validateur (`explanation_validator.py`) | Code | Rejette tout chiffre hors registre (y compris en lettres), renvoi inconnu, terme de recommandation ou de prévision, règle non citée, contrefactuel dit « indisponible », lien, image ou balise HTML, texte trop long | Fidélité garantie par construction, pas par un second modèle |
| Garde-fou (`scripts/setup_guardrail.py`, `bedrock_client.py`, `grounding_source.py`) | Amazon Bedrock Guardrails | Sujets refusés : conseil personnalisé, exécution d'ordres, prédiction de rendement. Ancrage contextuel en mode détection, appliqué aux **seules phrases écrites par le modèle** (valeurs à la place des renvois), contre une **source rédigée en phrases françaises** à partir du seul dossier. **Aucun texte de modèle n'est affiché sans garde-fou qui l'a vérifié** : garde-fou absent, en erreur, intervenu (sujet refusé) ou sans score, et c'est le gabarit du code qui s'affiche, avec la raison dans la trace. Un ancrage faible est un **signal, pas un blocage** : entre 0,3 et 0,5, le texte reste affiché avec l'avertissement « ancrage faible » ; sous 0,3, avec l'avertissement « ancrage très faible » (`grounding_very_weak` dans la trace) et sans mise en cache | Règle de simulation de l'énoncé ; indicateur de proximité du texte avec le dossier (ce qu'il mesure vraiment : section 5.3) |
| Traces (`trace_store.py`, `scripts/setup_trace_bucket.py`) | Amazon S3 privé | Une trace JSON par appel, sans secret ni texte libre du modèle (paramètres réduits aux clés validées), écrite seulement si les quatre options Block Public Access sont actives et si le compartiment appartient au compte attendu ; compartiment créé par script idempotent (chiffrement, TLS obligatoire) | Preuve consultable de l'intégration AWS réelle |
| Interface (`app/`) | Streamlit, en français, 5 pages | Accueil, simulation (saisie en une phrase ou par réglages), création d'un profil fictif par cases, test du garde-fou, sources et méthode ; niveau novice ou pro par un interrupteur ; verdict global, avec les verdicts financier et ESG pour un profil qui a une règle ESG ; avant/après, explication, fiches de preuve, trace | Tout en Python, lancement local, adaptée à la bascule de niveau |

### 2.3 Services AWS

| Service | Usage | Justification |
| --- | --- | --- |
| Amazon Bedrock Runtime, API Converse | Agents analyste et explicateur | API unifiée avec appels d'outils ; identifiant de modèle configurable par variable d'environnement, vérifié dans le compte (`scripts/check_aws_access.py`) |
| Amazon Bedrock Guardrails | Sujets refusés (niveau de classification Standard) et ancrage contextuel | Faire respecter la simulation et mesurer la proximité du texte avec le dossier ; complète les contrôles du code ; mesuré dans le compte (section 5) |
| Amazon S3 (privé) | Traces d'exécution | Trace consultable de chaque analyse |
| AWS STS | Vérification du compte | Contrôle des identifiants temporaires avant toute opération |

Choix assumés : pas de Lambda, d'hébergement, de Glue ni d'Athena. Les données font quelques mégaoctets : `pandas` en local suffit, et l'application tourne en local (décision d'équipe). En mode `bedrock`, toute erreur d'agent ou de configuration bascule sur le repli hors ligne, signalé dans la trace. Une politique IAM de référence, au moindre privilège, est donnée dans [docs/aws_setup.md](aws_setup.md) pour un hébergement futur.

### 2.4 Méthodes de calcul

| Mesure | Méthode |
| --- | --- |
| Rendement quotidien | Rendement simple de `adj_close` (dividendes et fractionnements inclus), converti en CAD |
| Rendement cumulé | Produit des (1 + r) moins 1 |
| Rendement annualisé | (1 + cumulé) ^ (252 / n) - 1, **non affiché sous 252 rendements** (annualiser une période courte serait trompeur) |
| Volatilité annualisée | Écart-type quotidien (n - 1) x racine de 252, pour tous les actifs, crypto comprise ; **refusée sous 60 rendements** (environ trois mois de bourse) : l'outil rend alors « information manquante » au lieu d'un chiffre trompeur |
| Perte maximale | Plus forte baisse entre un sommet et le creux suivant, fraction positive, avec dates du sommet et du creux |
| Récupération | Jours civils du creux au retour au niveau du sommet ; jours passés sous le sommet ; « non récupérée » si le niveau n'est pas retrouvé |
| Portefeuille | Poids fixes rééquilibrés chaque jour : rendement quotidien = somme pondérée des rendements en CAD |
| Idée | Poids visé total ; financement au prorata des autres positions ou par un seul titre |
| Contrefactuel | Balayage du poids visé par pas d'un point ; plus grand poids conforme pour chaque règle |
| Groupe corrélé | Corrélation de Pearson des rendements quotidiens en CAD, seuil de 0,80, liaison simple, au moins 60 jours communs ; poids du plus grand groupe (section 6.2) |
| Montant en dollars | Perte historique observée sur la période, appliquée au capital fictif, jamais présentée comme une prévision |

## 3. Données, actifs, traitements et hypothèses

### 3.1 Sources

| Source | Contenu | Période | Conditions |
| --- | --- | --- | --- |
| Yahoo Finance (via `yfinance`, jeu des organisateurs) | Prix quotidiens, clôture ajustée, dividendes, fractionnements | 12 nov. 2021 au 12 nov. 2026, extraction du 13 nov. 2026 | Conditions Yahoo, données non certifiées ; fichiers gardés dans le dépôt privé ouvert au jury (décision dans le README) |
| Banque du Canada (API Valet) | Taux USD/CAD quotidien | Idem | Conditions de la Banque du Canada |
| Équipe (fictif) | 3 personas, portefeuilles fictifs, seuils des règles | Sans objet | Contenu original, hypothèses de l'équipe ([data/external/sources.md](../data/external/sources.md)) |

Les séries macroéconomiques du jeu (taux, inflation, chômage) ne sont pas utilisées par le prototype. Aucune donnée ESG, actualité ou donnée fondamentale n'est intégrée. Détail : `data/raw/sources_metadata.csv`, [docs/data_review.md](data_review.md).

### 3.2 Actifs

L'univers des organisateurs : 31 actifs, 10 actions canadiennes, 10 actions américaines, 9 FNB (actions, obligations, or, un FNB filtré ESG), Bitcoin et Ether. Les demandes prêtes de l'interface portent sur TSLA (25 %), NVDA (15 %), BTC-USD (10 % et 40 %) et XOM (15 %) ; les portefeuilles fictifs combinent actions, FNB d'actions, FNB obligataires, or et, pour Amira, cryptoactifs.

### 3.3 Traitements

- **Devise de référence CAD** : prix américains convertis au taux USD/CAD **du même jour** (publié vers 16 h 30, après la clôture américaine) ; les jours sans publication, dernier taux connu, au plus 4 jours ; jamais un taux postérieur.
- **Calendrier commun** : seulement les jours où toutes les actions et tous les FNB, de la TSX et des États-Unis, ont un prix (1 228 jours ; 27 jours TSX seuls et 27 jours américains seuls écartés). Aucun prix inventé ; le mouvement d'un jour écarté s'ajoute au jour commun suivant.
- **Crypto** : journée UTC de même date ramenée au calendrier boursier ; les mouvements du week-end s'ajoutent au jour ouvrable suivant.
- **Date d'analyse `as_of`** : aucune donnée postérieure n'est lue, à aucune étape. La date la plus ancienne utilisable laisse au moins 60 rendements (14 février 2022).
- **Libellés** : classes d'actifs, secteurs et devises de l'univers affichés en français ; les clés de preuve gardent les codes d'origine.

### 3.4 Hypothèses affichées comme telles

- Seuils des règles par profil (hypothèses de l'équipe, pas des normes réglementaires). Exemple, Robert : concentration par actif, alerte à 20 % et limite à 22 % ; volatilité 16 % et 25 % ; perte maximale 20 % et 35 % ; part défensive minimale 40 % et 30 % ; cryptoactifs exclus. Leur effet sur les verdicts est mesuré en section 5.2.
- Part défensive = obligations + or.
- Rééquilibrage quotidien.
- Exposition aux devises = devise de cotation, pas l'exposition économique des entreprises.

## 4. Explicabilité : comment une conclusion remonte aux données

### 4.1 Le mécanisme

1. **Les outils calculent** et produisent des preuves. Chaque preuve porte une clé stable `<métrique>:<sujet>` (par exemple `max_drawdown:portfolio_after`), sa valeur, son affichage français, sa période, son nombre d'observations, sa devise, ses fichiers sources, une phrase de transformation et ses limites (LM1 à LM5). Liste complète : [docs/evidence_keys.md](evidence_keys.md).
2. **Le registre numérote** les preuves d'une analyse (E1, E2...). Le numéro dépend de l'ordre des appels ; la clé, elle, est stable.
3. **La gouvernance** rattache chaque contrôle de règle à la preuve de la métrique lue (`evidence_ids`).
4. **L'explicateur n'écrit aucun chiffre** : il écrit `[E39]`, `[G1]`, `[T3]`. Le code remplace chaque renvoi par la valeur du registre, et écrit lui-même la phrase du contrefactuel.
5. **Le validateur** rejette le texte s'il contient un chiffre absent du registre, un renvoi inconnu, une recommandation ou une prévision, un lien ou du HTML, ou s'il omet une règle en tension ou en conflit. Un texte rejeté deux fois est remplacé par le gabarit, et la trace le dit.
6. **L'interface** affiche chaque chiffre depuis sa preuve ; un clic ouvre la fiche de la preuve.

### 4.2 Exemple : Robert veut porter TSLA à 25 %

Exécution réelle en mode hors ligne (`run_analysis`, données jusqu'au 12 novembre 2026), conclusion suivie de l'écran jusqu'aux fichiers.

**Conclusion affichée** (niveau novice) :

> « Pour la part d'un seul placement dans le portefeuille (voir **Concentration**), la mesure **25 %** franchit la limite fixée pour ce profil. Contrôle : **Concentration par actif** (en conflit). »

**Ce que l'explicateur a réellement écrit** (aucun chiffre) :

> « Pour la part d'un seul placement dans le portefeuille (voir [T3]), la mesure [E39] franchit la limite fixée pour ce profil. Contrôle : [G1]. »

**Remontée de la conclusion :**

| Niveau | Élément | Contenu |
| --- | --- | --- |
| Contrôle | `G1`, règle `R1` Concentration par actif | Statut **conflit** : valeur 0,25 ; alerte 0,20 ; limite 0,22 ; contrefactuel « conforme à 20 % ou moins » ; preuve `E39` |
| Preuve | `E39` = `top_asset_weight:portfolio_after` | Valeur 0,25, affichage « 25 % », libellé « Poids du plus gros actif (TSLA) », outil `simulate_portfolio_change`, limite LM4 (hypothèses de simulation) |
| Trace, étape 1 | Appel `simulate_portfolio_change` | Paramètres `{ticker: TSLA, target_weight: 0.25, funding_source: pro_rata}`, statut `ok`, preuves `E30` à `E65` |
| Calcul | `portfolio.apply_idea` | TSLA porté à 25 %, les six autres positions de Robert réduites au prorata (multipliées par 0,75) |
| Données | `data/external/investor_profiles.json` | Portefeuille fictif de départ de Robert (aucune position TSLA) |

La même analyse rattache les deux autres règles non conformes à des preuves de série, elles-mêmes reliées aux fichiers de prix :

| Contrôle | Statut | Preuve | Affichage | Période et sources |
| --- | --- | --- | --- | --- |
| `G2` Volatilité annuelle | tension (alerte 16 %, limite 25 %) | `E30` `volatility_ann:portfolio_after` | 17,6 % | 12 nov. 2021 au 12 nov. 2026, 1 227 rendements, `prices_daily.csv`, `fx_usdcad_daily.csv` |
| `G3` Perte maximale historique | tension (alerte 20 %, limite 35 %) | `E31` `max_drawdown:portfolio_after` | 26,04 % | Idem, limites LM1 à LM5 |

**Variante simulée** (proposée par l'analyste, recalculée par les mêmes outils) : `V1`, réduction du poids visé à 17 %, verdict **conforme** (trace : second appel `simulate_portfolio_change` avec `target_weight: 0.17`, preuves `E66` à `E101`). Le code appelle ensuite `get_asset_facts` pour TSLA seul (preuves `E102` à `E109`, libellés « (TSLA seul) » : volatilité de 59,39 % et perte maximale de 69,81 % sur la période), pour que l'explication ne confonde pas l'actif et le portefeuille. Dans la trace, ces trois appels portent `caller: code`.

**Contexte du profil.** L'explication rappelle, dans une section à part et recopiés tels quels, l'objectif (« Préserver le capital avant la retraite »), l'horizon (3 à 5 ans), la tolérance au risque (faible à modérée), l'absence de préférence ESG et l'interdiction des cryptoactifs. Ce n'est ni une conclusion de l'analyse ni une recommandation.

**Trace complète de l'explication :** étape 4 explication (gabarit en mode hors ligne, agent en mode `bedrock`), étape 5 validation (valide, 14 renvois vérifiés), étape 6 garde-fou (non exécuté hors ligne ; en mode `bedrock`, action, scores d'ancrage et nature de la source affichés).

### 4.3 Le même exemple en mode `bedrock` : trace réelle

**[À REMPLIR après la régénération des traces finales (Godwin) : date et heure de l'essai, fichiers de `outputs/reports/demo_traces/`, modèles, nombre de tours et d'appels de l'analyste, phrase rendue par l'explicateur avec `explainer_v5`, renvois vérifiés, action du garde-fou, score d'ancrage et `source_kind`.]**

| Étape | Acteur | Ce que montre la trace |
| --- | --- | --- |
| 1. Analyse | Agent analyste (Bedrock) | **[À REMPLIR]** tours et appels d'outils, avec `caller: agent` pour ceux de l'agent et `caller: code` pour ceux du code |
| 2. Gouvernance | Code | Mêmes verdicts et mêmes valeurs qu'en mode hors ligne (R1 en conflit à 25 %, R2 et R3 en tension) ; seuls les numéros de preuve peuvent différer, car le registre numérote dans l'ordre des appels choisi par l'agent |
| 4. Explication | Agent explicateur (prompt `explainer_v5`) | **[À REMPLIR]** phrase rendue ; contrefactuel écrit par le code (`slots_written_by_code`) |
| 5. Validation | Code | **[À REMPLIR]** renvois vérifiés, rejets éventuels |
| 6. Garde-fou | Bedrock Guardrails | **[À REMPLIR]** action, score d'ancrage, pertinence, `source_kind: sentences` |

Premier essai réel, pour comparaison (14 novembre 2026 au soir, prompt `explainer_v4`, source d'ancrage en JSON) : la gouvernance donnait les mêmes verdicts ; l'explicateur avait écrit « Le poids de TSLA atteint 25 % et dépasse la limite de la règle Concentration par actif (en conflit) », validé au premier essai (9 renvois), avec un ancrage de 0,34 seulement, signalé mais conservé. C'est ce score bas sur un texte exact qui a conduit au diagnostic de la section 5.3.

La conclusion affichée au jury est donc rédigée par un vrai modèle, mais chaque chiffre de la phrase reste la valeur d'une preuve du registre, et le verdict reste celui de la gouvernance en code.

## 5. Validations et mise à l'épreuve

### 5.1 Validations

| Vérification | Moyen | Résultat |
| --- | --- | --- |
| Calculs | Tests sur séries calculées à la main (par exemple 100, 120, 90, 130 : perte de 25 %) et contrôle croisé sur données réelles (perte maximale de TSLA identique à partir des prix et des rendements : 69,81 %) | Conformes |
| Minimum de rendements | Tests à 59 et 60 rendements ; avant le correctif, deux rendements donnaient une « volatilité annualisée » de 4,34 % jugée par la règle R2 | Refus sous 60 rendements, statut « information manquante » |
| Absence d'information future | `tests/test_as_of_invariance.py` : le code tourne sur des copies **physiquement tronquées** des données (un mercredi, un samedi, un jour de taux reporté) et doit rendre exactement le même résultat que sur les données complètes avec `as_of` | Aucune fuite trouvée |
| Contrats entre flux | Tests de conformité des formats (`contracts.py`) pour les radiographies, preuves, résultats d'outils, dossiers et sorties | Conformes |
| Fidélité des explications | Tests du validateur, un par code de rejet ; textes adverses (chiffre en clair, nombre en lettres, renvoi inconnu, « vous devriez », lien, image, HTML, contrefactuel « indisponible ») | Rejetés |
| Robustesse des outils | Saisies invalides venant d'un modèle (poids en texte, booléen, date relative, ticker mal formé) : statut `error` ou `missing_info`, jamais de plantage ni de saisie recopiée | Conformes |
| Bout en bout | `scripts/run_scenarios.py` : 3 personas x les 5 demandes prêtes de l'interface, verdicts global, financier et ESG, contrefactuels, variantes, validité des explications | 15 scénarios, aucun échec, explications toutes valides (mode hors ligne) |
| Interface | Parcours joué sans navigateur (`streamlit.testing`) sur l'interface en 5 pages : choix du profil à l'accueil, page Simulation, demande TSLA 25 %, analyse, pour les 3 personas ; analyse de Robert aux niveaux novice et pro ; page du garde-fou ; 7 dialogues de la conversation (salutation, positions, définition, poids sans « % » confirmé par un clic, relance, écart relatif, refus) dans `tests/test_chat_dialogue.py` | Aucune exception ; statut affiché identique au tableau de référence (Conflit, Tension, Information manquante) ; aucune analyse lancée avant le clic de confirmation |
| Compréhension des messages | `scripts/measure_dialogue.py` : 60 phrases inventées et étiquetées par leur comportement **idéal** (jamais deviner, refuser ce qui est interdit), en 9 catégories tirées de l'atelier finance « Comprendre l'investisseur » (profil, instruments, risques, piège du « meilleur placement ») ; rapport : [outputs/reports/dialogue_eval.md](../outputs/reports/dialogue_eval.md) | **Règles : 45 sur 60.** Catégories de sécurité à 100 % (refus 8/8, idées explicites 5/5, pièges 5/5), concepts du glossaire 7/7 ; manques : idées formulées librement 6/10 (« la moitié dans l'or », « un peu plus de tech »), questions de profil et « pourquoi » 2/9. Des tests empêchent toute régression sur les catégories de sécurité |
| Garde-fou, dans le compte AWS de l'atelier | `scripts/setup_guardrail.py --test` : 19 requêtes en français, 10 permises et 9 à refuser, sur le garde-fou réel ; versions 1 à 4 comparées (niveau de classification Classic puis Standard) | **Mesuré.** Niveau Standard : **9 refus attendus sur 9** (dont « Achète TSLA pour moi » et « Comment en profiter ? »), concordance de 16 à 17 sur 19 ; faux refus connus sur des questions historiques classées à tort comme prédictions (A02, A07, parfois A09). Version retenue pour la démo : **[À REMPLIR, décision D3]**. Détail : [docs/aws_setup.md](aws_setup.md) |
| Repli en conditions réelles | Premier `scripts/try_bedrock_run.py --run` : tous les appels au modèle refusés par Bedrock (paramètre `temperature` non accepté, corrigé depuis) | **Vérifié.** Aucun plantage : bascule sur le code pour l'analyse et les explications, repli et raison signalés dans la trace |
| Traces S3 en conditions réelles | Même essai, compartiment privé créé par `scripts/setup_trace_bucket.py` | **Vérifié.** Traces écrites (une par appel de pipeline), copies locales produites, aucun secret |
| Agents rédigeant du vrai texte | `scripts/try_bedrock_run.py --run --save-local` ; traces dans `outputs/reports/demo_traces/` | **Vérifié** au premier essai (14 nov., 4 explications sur 4 rédigées par le modèle, validées au premier essai). Essai final sur `main` : **[À REMPLIR : personas, explications d'origine modèle, repli éventuel, scores d'ancrage]** |
| Revue | Chaque module relu avant fusion (agent de relecture) ; audits de sécurité sur les parties AWS et avant la remise | Corrections appliquées |

La suite automatisée compte plus de 2 400 tests, tous exécutables sans AWS (`.venv/Scripts/python -m pytest -q -W error`).

Résultat de référence de `run_scenarios.py`, verdict affiché après la demande (financement au prorata) :

| Profil | TSLA 25 % | NVDA 15 % | BTC-USD 10 % | BTC-USD 40 % | XOM 15 % |
| --- | --- | --- | --- | --- | --- |
| Robert | conflit | conforme | conflit | conflit | conforme |
| Amira | tension | conforme (sans effet) | conforme (sans effet) | conflit | conforme |
| Mateo | information manquante | information manquante | conflit | conflit | information manquante |

« Sans effet » : le portefeuille fictif d'Amira détient déjà 15 % de NVDA et 10 % de BTC-USD. Le verdict affiché de Mateo est le pire statut de toutes ses règles : sa règle d'exclusion ESG (R7) reste en « information manquante » faute de preuve. Son verdict financier, calculé à part depuis la séparation des verdicts et affiché sous le verdict global (pastilles « Financier » et « ESG », seulement pour un profil qui a une règle ESG), est **conforme** pour TSLA 25 %, NVDA 15 % et XOM 15 %, et en **conflit** pour les deux demandes en cryptoactif, exclu de son profil.

### 5.2 Mise à l'épreuve des hypothèses

`scripts/run_sensitivity.py` (module `sensitivity.py`) refait la gouvernance en changeant **un seul choix à la fois**, sur les 3 personas et les 5 demandes (15 cas par variante), sans toucher au pipeline. Le cas de base redonne exactement les chiffres des outils. Rapport complet et reproductible : [outputs/reports/sensitivity.md](../outputs/reports/sensitivity.md).

| Variante | Hypothèse testée | Cas dont le verdict financier change |
| --- | --- | --- |
| Fenêtre de 3 ans, de 1 an | Période plus courte (l'épisode 2022 sort de la fenêtre) | 0 sur 15 |
| Devise locale | Change parfaitement couvert, sans coût (convention de calcul, pas une stratégie) | 4 sur 15, tous de conforme à tension : neutraliser le change augmente ici le risque mesuré |
| Données arrêtées au 12 nov. 2024, 2025 | Se placer plus tôt, sans aucune donnée postérieure | 2 sur 15 : Amira, dont le groupe corrélé passe en tension dès le portefeuille de départ |
| Rendements hebdomadaires | Atténue les décalages d'heure de clôture entre marchés et cryptoactifs | 0 sur 15 |
| Seuils 20 % plus stricts | Plafonds x 0,8, planchers / 0,8 ; exclusions et ESG inchangées | 7 sur 15 |
| Seuils 20 % plus souples | Plafonds x 1,2, planchers / 1,2 | 2 sur 15 |

Lecture :

- **Les seuils sont l'hypothèse dominante** ; les choix de données (fenêtre, fréquence, date) changent peu les verdicts.
- Le **conflit de Robert avec TSLA 25 %** tient dans les 6 variantes de données. Il vient de R1 (25 % pour une limite de 22 %), qui ne dépend que des poids : il faudrait des seuils au moins 1,25 fois plus souples pour qu'il redevienne conforme (tableau des facteurs de bascule du rapport).
- Les règles sur les poids (R1, R4, R5, R6) et la préférence ESG ne bougent avec aucune variante de données ; seules les règles sur les prix (volatilité, perte maximale, groupe corrélé) en dépendent.
- Cinq **blocs annuels disjoints** montrent les épisodes observés (dont 2022) sans les prévoir : avec TSLA 25 %, la volatilité annualisée d'Amira atteint 38 % sur la première année, contre 24 % à 32 % les années suivantes.

Précautions de lecture, écrites dans le rapport : une perte maximale mesurée sur une période plus courte ne peut que baisser, elle est marquée « non comparable » et garde son statut de base dans le verdict comparé ; les variantes ne sont ni indépendantes ni équiprobables, un décompte n'est pas une probabilité ; un seul choix change à la fois.

### 5.3 Ce que mesure vraiment le contrôle d'ancrage

Diagnostic du flux C, mesuré dans le compte avec la version 5 du garde-fou ([docs/grounding_diagnosis.md](grounding_diagnosis.md)) :

| Texte de l'explicateur, 25 % de TSLA | Source en JSON | Source en phrases |
| --- | --- | --- |
| Amira novice | 0,27 | 0,82 |
| Amira pro | 0,33 | 0,91 |
| Robert novice | 0,42 | 0,84 |
| Robert pro | 0,15 | 0,70 |

- **Cause du score bas : la forme de la source.** Le dossier en JSON écrit les statuts en codes anglais (`conflict`) et les seuils en nombres bruts ; le texte dit « en conflit » et « 22 % ». Le même dossier réécrit en phrases françaises (`grounding_source.py`, branché dans le pipeline) fait passer les textes du modèle au-dessus du seuil de 0,5. La trace indique `source_kind` et `source_chars`.
- **Le score ne prouve pas l'exactitude.** Un texte témoin où les règles en conflit sont déclarées conformes obtient presque le même score que le texte juste. Le score mesure la proximité de vocabulaire avec le dossier ; l'exactitude des statuts et des chiffres est garantie par le code (renvois, validateur, gouvernance). C'est pourquoi l'équipe a décidé qu'un score faible est un **signal affiché, jamais un blocage** : le texte du modèle reste visible avec un avertissement « ancrage faible » (de 0,3 à 0,5) ou « ancrage très faible » (sous 0,3). Seuls une intervention du garde-fou (sujet refusé) ou l'absence de score font revenir au gabarit.
- **Variabilité** : sur les essais réels du 15 novembre, les scores vont de 0,14 à 0,98 d'une génération à l'autre, pour un même dossier.
- **Point de vigilance** : un score très bas avait signalé, à un essai réel, une erreur de sens que le validateur ne voit pas (une mesure rattachée à la mauvaise chose). Sans plancher bloquant, c'est l'avertissement visible qui protège l'utilisateur ; les règles du prompt réduisent ce risque, et les chiffres, statuts et renvois viennent toujours du code.
- **Cas d'Amira** : après le correctif du contrefactuel, un essai réel donnait 0,19 (novice) et 0,12 (pro) pour Amira, alors que Robert passait (0,70 et 0,88). Le contexte du profil a été ajouté à la source depuis ; avec la nouvelle règle, ce texte serait affiché avec l'avertissement « ancrage très faible ». **[À REMPLIR après l'essai final : scores d'Amira.]**

## 6. Limites et améliorations

### 6.1 Limites des données et de la méthode

- **Biais du survivant** : l'univers a été choisi en 2026 parmi des noms importants aujourd'hui (limite LM1, affichée). Se placer en 2024 dans la mise à l'épreuve réutilise cet univers.
- **Historique court** : cinq ans, un seul épisode de baisse marquée (2022) ; la volatilité est un indicateur de risque parmi d'autres (LM2).
- **Niveaux de `adj_close` rétro-ajustés** depuis 2026 : seuls les rapports entre prix sont utilisés, jamais les niveaux, ce qui exclut cette fuite par conception.
- **Rééquilibrage quotidien** : un portefeuille réel dérive entre deux rééquilibrages (LM4).
- **Données publiques gratuites**, non certifiées (LM5).

### 6.2 Limites du prototype

- **ESG non intégré** : aucune preuve ESG n'existe encore. Pour Mateo, la règle d'exclusion ESG (R7) rend donc « information manquante » : le système refuse de conclure plutôt que de déclarer conforme une idée qu'il ne peut pas vérifier, et donne le verdict financier à part. Pour les autres profils, un verdict « conforme » ne dit rien de l'ESG.
- **Seuils** : hypothèses de l'équipe, et l'hypothèse à laquelle les verdicts sont le plus sensibles (section 5.2). Certains seuils de démonstration coïncident avec les valeurs testées (l'égalité au seuil ne déclenche pas d'alerte, par exemple le plafond de 25 % par actif de Mateo).
- **Concentration en actions individuelles (R6)** : la règle compte les actions détenues directement, pas les FNB d'actions ; l'exposition totale aux actions n'est pas plafonnée en tant que telle.
- **Conversation par règles** : lisible et testée, sans modèle, elle ne comprend que les formulations prévues : 45 phrases sur 60 dans la mesure de la section 5.1. Une formulation libre (« un peu plus de tech », « le titre dont tout le monde parle ») reçoit une réponse « hors périmètre » ou une question plutôt qu'une interprétation, et les questions de profil (« quel est mon horizon ? ») ou les « pourquoi » n'ont pas encore de réponse. C'est le choix assumé de la première version : ne jamais deviner. Les deux suites sont en cours (section 6.3).
- **Garde-fou** : il complète les contrôles du code mais ne prouve pas l'exactitude factuelle ; l'ancrage est en mode détection et mesure la proximité de vocabulaire, pas la justesse des statuts (section 5.3). Mesuré dans le compte, il refuse toutes les demandes interdites testées, mais classe parfois une question historique légitime comme une prédiction (faux refus) ; le classifieur n'est pas parfaitement stable d'un essai à l'autre. Le niveau Standard traite les demandes dans une autre région américaine (profil interrégional), acceptable ici puisque les données sont publiques ou fictives.
- **Agents réels** : le mode `bedrock` dépend du compte temporaire de l'atelier, des modèles actifs et des quotas partagés ; sans température, les réponses varient d'un appel à l'autre, ce que le validateur et le gabarit de repli absorbent.
- **Mise à l'épreuve** : un seul choix change à la fois ; les effets combinés ne sont pas testés.

- **Groupe corrélé (R8 d'Amira)** : la mesure est le poids du plus grand groupe de titres dont la corrélation des rendements quotidiens en CAD atteint 0,80 (corrélation de Pearson, liaison simple, toute la période disponible, au moins 60 jours communs). Le seuil de 0,80 et les seuils de la règle (tension à 35 %, conflit à 50 %) sont des hypothèses de l'équipe, **choisies après examen des données** : ce choix n'est donc pas indépendant des résultats. La corrélation décrit le passé, elle ne prédit rien, et la liaison simple peut réunir des titres peu corrélés entre eux par chaînage. Seule Amira a cette règle ; Robert et Mateo voient la mesure en radiographie sans règle associée.

  Test de sensibilité du seuil de corrélation (période du 12 nov. 2021, date de base, au 12 nov. 2026, 1227 rendements communs) :

  | Seuil de corrélation | Amira avant l'idée | Amira avec 40 % dans BTC-USD | Lecture |
  | --- | --- | --- | --- |
  | 0,6 ou 0,7 | 70 % (actions et FNB d'actions, par chaînage) | 46,7 % (même bloc d'actions) | l'idée *réduit* la mesure : le test ne montre plus la crypto |
  | 0,8 (retenu) | 30 % (QQQ et SPY, corrélation 0,95) | 43,3 % (BTC-USD et ETH-USD, corrélation 0,84) | l'idée fait apparaître un groupe crypto et met la règle en tension |

  Au seuil de 0,8, la paire BTC-USD et ETH-USD (0,84) est proche de la coupure : une autre fenêtre de dates pourrait la séparer.

  La mesure dépend aussi fortement de la fenêtre. Avec le même seuil, le portefeuille de départ d'Amira atteint 60 % (conflit, au-delà de 50 %) lorsque la période s'arrête au 30 juin 2022 ou au 29 décembre 2023 (AAPL, MSFT, NVDA, QQQ et SPY), 45 % au 28 juin 2024 (tension), 40 % au 30 juin 2025 et 30 % sur la fenêtre complète. L'histoire « conforme avant l'idée, en tension après » vaut donc pour la fenêtre qui se termine en 2026, en plus du choix du seuil après examen des données. La mise à l'épreuve de la section 5.2 le confirme : avec des données arrêtées en 2024 ou 2025, la règle d'Amira passe en tension dès son portefeuille de départ.

### 6.3 Améliorations envisagées

- **Preuves ESG datées et sourcées.** Source repérée : les évaluations de la World Benchmarking Alliance, sous licence CC BY 4.0, qui couvrent notamment XOM et CNQ.TO. Elles permettraient à la règle d'exclusion ESG de Mateo de rendre un verdict au lieu d'« information manquante », avec la date de publication de chaque évaluation pour éviter toute information future.
- Composition des FNB chez les émetteurs, pour voir les titres qui se cachent derrière un fonds (la diversification par corrélations ne regarde que les positions détenues).
- **Compréhension des formulations libres (en cours, flux D)** : un interprète sur Bedrock classe seulement les messages que les règles ratent, par un outil à champs fermés (intention, actif de l'univers, poids entier) ; le code valide, une idée comprise par le modèle devient toujours une confirmation, et le modèle peut ajouter un refus, jamais en lever un. Mesure prévue avec le même jeu de 60 phrases.
- **Agent qui répond aux questions de profil et aux « pourquoi » (en cours, flux B et C)** : le code construit un dossier de conversation (profil déclaré via `get_profile_facts`, radiographie, dernière analyse, glossaire, limites), un seul appel Bedrock rédige par renvois `[E#]`, un validateur renforcé contrôle la réponse, et le code écrit les sections « données utilisées », « limites » et « ce qui changerait la réponse ». Plan publié dans l'issue #78 ; cible : les questions de profil de 2/9 vers 9/9 sans toucher aux catégories de sécurité.
- Une **capacité de perte déclarée** dans les profils fictifs (aujourd'hui absente et signalée manquante) et, après accord d'un mentor, de courtes **fiches pédagogiques** tirées de l'atelier comme seule source des explications générales.
- Saisie en texte libre du profil, avec règles proposées par l'agent puis confirmées par l'utilisateur (l'idée se saisit déjà en une phrase).
- Mise à l'épreuve combinée (plusieurs choix à la fois) et rejeu de l'interface à une date passée (le paramètre `as_of`, sa vérification et le minimum de rendements existent déjà).
- Annonces planifiées de la Banque du Canada comme deuxième type de preuve sur les taux.
- Hébergement de l'interface sur AWS (politique IAM de référence prête) et histogramme des codes de rejet de l'explicateur pour régler ses prompts.
