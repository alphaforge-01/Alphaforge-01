# Documentation technique : AlphaForge AI

Équipe AlphaForge 01 (Naoufal, Samer, Godwin, Ibrahima), datathon PolyFinances AlphaForge AI 2026.

> Simulation éducative uniquement : profils, portefeuilles et montants fictifs, aucune transaction réelle, aucune connexion à un courtier, aucun conseil personnalisé. Les résultats décrivent le passé sur une période explicite et ne prévoient rien.

Ce document répond aux quatre attentes de l'énoncé (p. 15) : méthodes, modèles et technologies avec leur justification (section 2) ; sources, actifs, traitements et hypothèses (section 3) ; mécanisme d'explicabilité avec un exemple relié aux données et à la trace (section 4) ; validations, limites et améliorations (sections 5 et 6). L'installation et la reproduction sont dans le [README](../README.md).

## 1. Problème et réponse

**Question servie :** « Mon portefeuille fictif correspond-il à mon profil, et que change mon idée de placement ? »

L'outil est un **copilote de cohérence, pas un conseiller**. Il ne propose pas de portefeuille et ne prédit aucun rendement. Il prend un profil fictif et une idée (« porter TSLA à 25 % du portefeuille »), simule l'avant/après sur données historiques, vérifie l'idée contre les règles du profil et explique le verdict, chiffre par chiffre, avec ses sources.

Les trois personas de l'énoncé testent trois comportements, couverts par le même mécanisme (une tension entre une demande et un profil) :

| Persona | Ce que l'énoncé teste | Ce que montre l'outil |
| --- | --- | --- |
| Robert (risque faible à modéré, 3 à 5 ans) | Contester une demande incohérente avec le profil | 25 % de TSLA : **conflit** sur la concentration, contrefactuel « conforme à 20 % ou moins », variante simulée à 17 % conforme |
| Amira (risque élevé, 15 ans et plus) | « Risque élevé » ne veut pas dire « tout est permis » | 25 % de TSLA, 20 % de BTC-USD ou 20 % de NVDA : **tension** sur la perte maximale historique |
| Mateo (modéré, forte préférence ESG) | Intégrer autre chose que le rendement et le risque | Cryptoactifs exclus : **conflit** dès 20 % de BTC-USD. Limite assumée : aucune donnée ESG n'est encore intégrée (section 6) |

## 2. Architecture, méthodes et technologies

### 2.1 Chaîne d'exécution

```
Interface Streamlit (app/)
        |
analysis_pipeline.run_analysis(profil, portefeuille, idée, as_of, mode)
        |
  1. Analyse     agent analyste (Bedrock, outils)  ou séquence fixe (hors ligne)
        |          analyze_portfolio, simulate_portfolio_change, get_asset_facts
  2. Gouvernance code : statut et marge par règle, contrefactuel
  3. Dossier     code : registre de preuves numérotées, facteurs classés, limites, glossaire
        |
analysis_pipeline.explain(résultat, niveau)
  4. Explication agent explicateur (Bedrock, sans outil, dossier seul)  ou gabarit
  5. Validation  code : rejette chiffre hors registre, renvoi inconnu, recommandation, prévision
  6. Garde-fou   Bedrock Guardrails : sujets refusés, ancrage contextuel  ->  trace (S3 privé)
```

**Principe directeur : un agent agit, le code juge, un agent explique.** Aucun modèle ne calcule un chiffre ni ne décide d'un verdict. Chaque étape est visible dans la trace, avec son acteur (agent, code, garde-fou).

### 2.2 Composants et justification

| Composant | Nature | Rôle | Pourquoi ce choix |
| --- | --- | --- | --- |
| Outils de l'agent (`agent_tools.py`) | Code déterministe testé | Radiographie, simulation avant/après, faits d'un actif ; chaque résultat porte ses preuves | L'énoncé et l'atelier demandent des calculs vérifiés : un modèle de langage peut confondre des notions financières |
| Agent analyste (`analyst_agent.py`) | Modèle sur Bedrock, API Converse avec appels d'outils, au plus 6 tours et 12 appels | Choisit les outils, comprend l'idée, propose au plus 2 variantes ; termine par un résultat structuré, sans prose | Seul rôle qui demande du jugement ; borné pour les quotas partagés et la lisibilité de la trace |
| Gouvernance (`governance.py`, `counterfactual.py`) | Code déterministe testé | Statut par règle (conforme, tension, conflit, information manquante), marge, contrefactuel par balayage du poids au point près | Un verdict ne doit pas varier d'un appel à l'autre ; il doit être testable |
| Registre de preuves (`evidence.py`) | Code | Numérote chaque chiffre (E1, E2...) avec valeur, affichage, période, devise, sources, transformation, limites | Base de l'explicabilité : tout chiffre affiché remonte à une preuve |
| Dossier et gabarit (`explanation_brief.py`, `explanation_fallback.py`) | Code | Seule entrée de l'explicateur ; ordre des facteurs, glossaire et limites fixés par le code ; explication de repli sans modèle | L'explicateur ne voit ni le texte de l'utilisateur ni les données brutes : il ne peut parler que de ce qui a été calculé |
| Agent explicateur (`explainer_agent.py`) | Modèle sur Bedrock, un appel sans outil, un nouvel essai au plus | Rédige en novice ou en pro, uniquement par renvois (`[E3]`, `[G1]`, `[T2]`) | Séparer l'explication de l'analyse : changer de niveau ne relance que l'explicateur, les chiffres ne peuvent pas bouger |
| Validateur (`explanation_validator.py`) | Code | Rejette tout chiffre hors registre (y compris en lettres), renvoi inconnu, terme de recommandation ou de prévision, règle non citée, texte trop long | Fidélité garantie par construction, pas par un second modèle |
| Garde-fou (`scripts/setup_guardrail.py`, `bedrock_client.py`) | Amazon Bedrock Guardrails | Sujets refusés : conseil personnalisé, exécution d'ordres, prédiction de rendement ; ancrage du texte contre le dossier (mode détection). **Aucun texte de modèle n'est affiché sans garde-fou qui l'a vérifié** : garde-fou absent, en erreur, intervenu ou ancrage sous le seuil, et c'est le gabarit du code qui s'affiche, avec la raison dans la trace | Règle de simulation de l'énoncé ; mesure de la fidélité du texte au dossier |
| Traces (`trace_store.py`, `scripts/setup_trace_bucket.py`) | Amazon S3 privé | Une trace JSON par appel, sans secret ni texte libre du modèle (paramètres réduits aux clés validées), écrite seulement si les quatre options Block Public Access sont actives ; compartiment créé par script idempotent (chiffrement, TLS obligatoire) | Preuve consultable de l'intégration AWS réelle |
| Interface (`app/`) | Streamlit, en français | Profil par cases, radiographie, idée par sélecteurs, avant/après, explication novice et pro, trace | Tout en Python, lancement local, adaptée à la bascule de niveau |

### 2.3 Services AWS

| Service | Usage | Justification |
| --- | --- | --- |
| Amazon Bedrock Runtime, API Converse | Agents analyste et explicateur | API unifiée avec appels d'outils ; identifiant de modèle configurable par variable d'environnement, vérifié dans le compte (`scripts/check_aws_access.py`) |
| Amazon Bedrock Guardrails | Sujets refusés et ancrage contextuel | Faire respecter la simulation et mesurer la fidélité ; complète les contrôles du code |
| Amazon S3 (privé) | Traces d'exécution | Trace consultable de chaque analyse |
| AWS STS | Vérification du compte | Contrôle des identifiants temporaires avant toute opération |

Choix assumés : pas de Lambda, d'hébergement, de Glue ni d'Athena. Les données font quelques mégaoctets : `pandas` en local suffit, et l'application tourne en local (décision d'équipe). En mode `bedrock`, toute erreur d'agent ou de configuration bascule sur le repli hors ligne, signalé dans la trace.

### 2.4 Méthodes de calcul

| Mesure | Méthode |
| --- | --- |
| Rendement quotidien | Rendement simple de `adj_close` (dividendes et fractionnements inclus), converti en CAD |
| Rendement cumulé | Produit des (1 + r) moins 1 |
| Rendement annualisé | (1 + cumulé) ^ (252 / n) - 1, **non affiché sous 252 rendements** (annualiser une période courte serait trompeur) |
| Volatilité annualisée | Écart-type quotidien (n - 1) x racine de 252, pour tous les actifs, crypto comprise |
| Perte maximale | Plus forte baisse entre un sommet et le creux suivant, fraction positive, avec dates du sommet et du creux |
| Récupération | Jours civils du creux au retour au niveau du sommet ; jours passés sous le sommet ; « non récupérée » si le niveau n'est pas retrouvé |
| Portefeuille | Poids fixes rééquilibrés chaque jour : rendement quotidien = somme pondérée des rendements en CAD |
| Idée | Poids visé total ; financement au prorata des autres positions ou par un seul titre |
| Contrefactuel | Balayage du poids visé par pas d'un point ; plus grand poids conforme pour chaque règle |
| Montant en dollars | Perte historique observée sur la période, appliquée au capital fictif, jamais présentée comme une prévision |

## 3. Données, actifs, traitements et hypothèses

### 3.1 Sources

| Source | Contenu | Période | Conditions |
| --- | --- | --- | --- |
| Yahoo Finance (via `yfinance`, jeu des organisateurs) | Prix quotidiens, clôture ajustée, dividendes, fractionnements | 12 nov. 2021 au 12 nov. 2026, extraction du 13 nov. 2026 | Conditions Yahoo, données non certifiées |
| Banque du Canada (API Valet) | Taux USD/CAD quotidien | Idem | Conditions de la Banque du Canada |
| Équipe (fictif) | 3 personas, portefeuilles fictifs, seuils des règles | Sans objet | Contenu original, hypothèses de l'équipe |

Les séries macroéconomiques du jeu (taux, inflation, chômage) ne sont pas utilisées par le prototype. Aucune donnée ESG, actualité ou donnée fondamentale n'est intégrée. Détail : `data/raw/sources_metadata.csv`, [docs/data_review.md](data_review.md).

### 3.2 Actifs

L'univers des organisateurs : 31 actifs, 10 actions canadiennes, 10 actions américaines, 9 FNB (actions, obligations, or, un FNB filtré ESG), Bitcoin et Ether. Les idées de démonstration portent sur TSLA, BTC-USD, NVDA et XOM ; les portefeuilles fictifs combinent actions, FNB d'actions, FNB obligataires et or.

### 3.3 Traitements

- **Devise de référence CAD** : prix américains convertis au taux USD/CAD **du même jour** (publié vers 16 h 30, après la clôture américaine) ; les jours sans publication, dernier taux connu, au plus 4 jours ; jamais un taux postérieur.
- **Calendrier commun** : seulement les jours où toutes les actions et tous les FNB, de la TSX et des États-Unis, ont un prix (1 228 jours ; 27 jours TSX seuls et 27 jours américains seuls écartés). Aucun prix inventé ; le mouvement d'un jour écarté s'ajoute au jour commun suivant.
- **Crypto** : journée UTC de même date ramenée au calendrier boursier ; les mouvements du week-end s'ajoutent au jour ouvrable suivant.
- **Date d'analyse `as_of`** : aucune donnée postérieure n'est lue, à aucune étape.

### 3.4 Hypothèses affichées comme telles

- Seuils des règles par profil (hypothèses de l'équipe, pas des normes réglementaires). Exemple, Robert : concentration par actif, alerte à 20 % et limite à 22 % ; volatilité 16 % et 25 % ; perte maximale 20 % et 35 % ; part défensive minimale 40 % et 30 % ; cryptoactifs exclus.
- Part défensive = obligations + or.
- Rééquilibrage quotidien.
- Exposition aux devises = devise de cotation, pas l'exposition économique des entreprises.

## 4. Explicabilité : comment une conclusion remonte aux données

### 4.1 Le mécanisme

1. **Les outils calculent** et produisent des preuves. Chaque preuve porte une clé stable `<métrique>:<sujet>` (par exemple `max_drawdown:portfolio_after`), sa valeur, son affichage français, sa période, son nombre d'observations, sa devise, ses fichiers sources, une phrase de transformation et ses limites (LM1 à LM5). Liste complète : [docs/evidence_keys.md](evidence_keys.md).
2. **Le registre numérote** les preuves d'une analyse (E1, E2...).
3. **La gouvernance** rattache chaque contrôle de règle à la preuve de la métrique lue (`evidence_ids`).
4. **L'explicateur n'écrit aucun chiffre** : il écrit `[E38]`, `[G1]`, `[T3]`. Le code remplace chaque renvoi par la valeur du registre.
5. **Le validateur** rejette le texte s'il contient un chiffre absent du registre, un renvoi inconnu, une recommandation ou une prévision, ou s'il omet une règle en tension ou en conflit. Un texte rejeté deux fois est remplacé par le gabarit, et la trace le dit.
6. **L'interface** affiche chaque chiffre depuis sa preuve ; un clic ouvre la fiche de la preuve.

### 4.2 Exemple : Robert veut porter TSLA à 25 %

Exécution réelle en mode hors ligne (`run_analysis`, données jusqu'au 12 novembre 2026), conclusion suivie de l'écran jusqu'aux fichiers.

**Conclusion affichée** (niveau novice) :

> « Pour la part d'un seul placement dans le portefeuille (voir **Concentration**), la mesure **25 %** franchit la limite fixée pour ce profil. Contrôle : **Concentration par actif** (en conflit). »

**Ce que l'explicateur a réellement écrit** (aucun chiffre) :

> « Pour la part d'un seul placement dans le portefeuille (voir [T3]), la mesure [E38] franchit la limite fixée pour ce profil. Contrôle : [G1]. »

**Remontée de la conclusion :**

| Niveau | Élément | Contenu |
| --- | --- | --- |
| Contrôle | `G1`, règle `R1` Concentration par actif | Statut **conflit** : valeur 0,25 ; alerte 0,20 ; limite 0,22 ; contrefactuel « conforme à 20 % ou moins » ; preuve `E38` |
| Preuve | `E38` = `top_asset_weight:portfolio_after` | Valeur 0,25, affichage « 25 % », libellé « Poids du plus gros actif (TSLA) », outil `simulate_portfolio_change`, limite LM4 (hypothèses de simulation) |
| Trace, étape 1 | Appel `simulate_portfolio_change` | Paramètres `{ticker: TSLA, target_weight: 0.25, funding_source: pro_rata}`, statut `ok`, preuves `E29` à `E63` |
| Calcul | `portfolio.apply_idea` | TSLA porté à 25 %, les six autres positions de Robert réduites au prorata (multipliées par 0,75) |
| Données | `data/external/investor_profiles.json` | Portefeuille fictif de départ de Robert (aucune position TSLA) |

La même analyse rattache les deux autres règles non conformes à des preuves de série, elles-mêmes reliées aux fichiers de prix :

| Contrôle | Statut | Preuve | Affichage | Période et sources |
| --- | --- | --- | --- | --- |
| `G2` Volatilité annuelle | tension (alerte 16 %, limite 25 %) | `E29` `volatility_ann:portfolio_after` | 17,6 % | 12 nov. 2021 au 12 nov. 2026, 1 227 rendements, `prices_daily.csv`, `fx_usdcad_daily.csv` |
| `G3` Perte maximale historique | tension (alerte 20 %, limite 35 %) | `E30` `max_drawdown:portfolio_after` | 26,04 % | Idem, limites LM1 à LM5 |

**Variante simulée** (proposée par l'analyste, recalculée par les mêmes outils) : `V1`, réduction du poids visé à 17 %, verdict **conforme** (trace : second appel `simulate_portfolio_change` avec `target_weight: 0.17`, preuves `E64` à `E98`).

**Trace complète de l'explication :** étape 4 explication (gabarit en mode hors ligne, agent en mode `bedrock`), étape 5 validation (valide, 13 renvois vérifiés), étape 6 garde-fou (non exécuté hors ligne ; en mode `bedrock`, action et scores d'ancrage affichés).

## 5. Validations

| Vérification | Moyen | Résultat |
| --- | --- | --- |
| Calculs | Tests sur séries calculées à la main (par exemple 100, 120, 90, 130 : perte de 25 %) et contrôle croisé sur données réelles (perte maximale de TSLA identique à partir des prix et des rendements : 69,81 %) | Conformes |
| Absence d'information future | `tests/test_as_of_invariance.py` : le code tourne sur des copies **physiquement tronquées** des données (un mercredi, un samedi, un jour de taux reporté) et doit rendre exactement le même résultat que sur les données complètes avec `as_of` | Aucune fuite trouvée |
| Contrats entre flux | Tests de conformité des formats (`contracts.py`) pour les radiographies, preuves, résultats d'outils, dossiers et sorties | Conformes |
| Fidélité des explications | Tests du validateur, un par code de rejet ; textes adverses (chiffre en clair, nombre en lettres, renvoi inconnu, « vous devriez ») | Rejetés |
| Robustesse des outils | Saisies invalides venant d'un modèle (poids en texte, booléen, date relative, ticker mal formé) : statut `error` ou `missing_info`, jamais de plantage ni de saisie recopiée | Conformes |
| Bout en bout | `scripts/run_scenarios.py` : 3 personas x 4 demandes fictives, verdicts, contrefactuels, variantes, validité des explications | 12 scénarios, aucun échec, explications toutes valides (mode hors ligne) |
| Garde-fou | `scripts/setup_guardrail.py --test` : 19 requêtes en français, 10 permises et 9 refusées | À exécuter dans le compte (section 6) |
| Mode `bedrock` réel | `scripts/try_bedrock_run.py --run` : analyse et explications novice et pro avec les vrais outils et les vrais agents, budget borné à 3 personas ; affiche mode effectif, étapes, replis, validation et scores du garde-fou | À exécuter dans le compte (section 6) |
| Revue | Chaque module relu avant fusion ; audits de sécurité sur les parties AWS | Corrections appliquées |

La suite automatisée compte plus de 1 000 tests, tous exécutables sans AWS (`.venv/Scripts/python -m pytest -q -W error`).

Résultat de référence de `run_scenarios.py` (verdict après la demande) :

| Profil | TSLA 25 % | BTC-USD 20 % | NVDA 20 % | XOM 10 % |
| --- | --- | --- | --- | --- |
| Robert | conflit | conflit | tension | conforme |
| Amira | tension | tension | tension | conforme |
| Mateo | conforme | conflit | conforme | conforme |

## 6. Limites et améliorations

### 6.1 Limites des données et de la méthode

- **Biais du survivant** : l'univers a été choisi en 2026 parmi des noms importants aujourd'hui (limite LM1, affichée).
- **Historique court** : cinq ans, un seul épisode de baisse marquée (2022) ; la volatilité est un indicateur de risque parmi d'autres (LM2).
- **Niveaux de `adj_close` rétro-ajustés** depuis 2026 : seuls les rapports entre prix sont utilisés, jamais les niveaux, ce qui exclut cette fuite par conception.
- **Rééquilibrage quotidien** : un portefeuille réel dérive entre deux rééquilibrages (LM4).
- **Données publiques gratuites**, non certifiées (LM5).

### 6.2 Limites du prototype

- **ESG non intégré** : un verdict « conforme » ne dit rien des préférences ESG de Mateo. Avec 25 % de TSLA ou 10 % de XOM, Mateo ressort conforme ; une règle d'exclusion ESG rendrait « information manquante » tant que les preuves ESG n'existent pas.
- **Seuils** : certains seuils de démonstration coïncident avec les valeurs testées (l'égalité au seuil ne déclenche pas d'alerte) ; la règle de concentration par catégorie ne compte que les actions individuelles, pas les FNB d'actions.
- **Garde-fou** : il complète les contrôles du code mais ne prouve pas l'exactitude factuelle ; l'ancrage est en mode détection.
- **Agents réels** : les essais de bout en bout de cette documentation sont en mode hors ligne ; le mode `bedrock` dépend du compte temporaire de l'atelier, des modèles actifs et des quotas partagés.

### 6.3 Améliorations envisagées

- Preuves ESG datées et sourcées (par exemple World Benchmarking Alliance, sous licence CC BY 4.0) et règle d'exclusion ESG pour Mateo.
- Diversification par corrélations (« fausse diversification » d'Amira) et composition des FNB chez les émetteurs.
- Saisie en texte libre du profil et de l'idée, avec règles proposées par l'agent puis confirmées par l'utilisateur.
- Rejeu à une date passée (le paramètre `as_of` et sa vérification existent déjà).
- Annonces planifiées de la Banque du Canada comme deuxième type de preuve sur les taux.
- Hébergement de l'interface sur AWS et histogramme des codes de rejet de l'explicateur pour régler ses prompts.
