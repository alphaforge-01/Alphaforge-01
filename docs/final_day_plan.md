# Plan d'attaque de la dernière journée

Datathon PolyFinances 2026, dimanche 15 novembre. Qui fait quoi, à quelle heure, et qui est responsable quand une tâche demande deux ou trois personnes. Établi à partir de la revue complète du dépôt contre l'énoncé officiel.

Simulation éducative : aucune transaction réelle, aucun conseil personnalisé.

## Horloge (heure de Montréal)

| Heure | Jalon |
| --- | --- |
| 9 h 30 | Point d'équipe, 15 min |
| 9 h 50 | Contrats annoncés (noms de champs) |
| 12 h 15 | Fusion 1 |
| 14 h 30 | Fusion 2 |
| 15 h | Réponse du mentor |
| 16 h | Fin du travail sur place |
| **16 h 30** | **Fusion 3 : dernier changement de comportement** |
| **18 h 30** | **Gel du code** |
| 19 h 30 à 21 h 30 | Tournage de la vidéo |
| **23 h 59** | **Code sur main (remise visée à 23 h)** |
| **Lundi 13 h 59** | **Fermeture des comptes AWS** |
| **Lundi 14 h** | **Vidéo, one pager, documentation technique** |

**Règle de la journée.** Tout changement qui modifie les sorties (prompt, dossier, libellés de preuves, gouvernance) est fusionné à 16 h 30 au plus tard, pour que les traces de démonstration soient régénérées ensuite. Après 18 h 30 : seulement des corrections de bogue qui bloquent la démo (`fix/`) et des documents (`docs/`). Lundi matin : aucun code.

## Décisions à prendre à 9 h 30

| # | Décision | Recommandation | Tranche |
| --- | --- | --- | --- |
| D1 | Mise à l'épreuve des hypothèses (P1-6) | Script allégé `scripts/run_sensitivity.py`, sans toucher au pipeline ni à l'interface, si la fenêtre est déjà un paramètre des outils (vérification en 10 min). Sinon, tableau dans la doc technique. | Naoufal |
| D2 | ESG de Mateo (P1-9) | Verdicts financier et ESG séparés (1 h). "Information manquante" assumée devient un argument d'honnêteté. Les preuves WBA vont dans les travaux futurs. | Samer |
| D3 | Version du garde-fou, 4 ou 5 | Comparer les deux, garder celle qui passe tous les refus attendus, tout remesurer avec elle. | Godwin, avant 10 h |
| D4 | Vidéo : langue, outil, poste | Français. Capture scène par scène sur le poste de Godwin, seul en mode Bedrock, sans partage d'identifiants. Ibrahima dirige. Voix lundi matin. QuickTime ou OBS, essai de 2 min avant midi. | Ibrahima |
| D5 | Dernière fusion de comportement | 16 h 30. | Samer |
| D6 | Périmètre des P2 | P2-11 abandonné. P2-10 réduit à l'étiquette `caller` et au renvoi des statuts. P2-12 réduit au seuil minimal de rendements. P2-13 conservé. | Équipe |
| D7 | Questions au mentor | Avant 15 h : redistribution des prix Yahoo dans le dépôt privé ouvert au jury, données dérivées dans S3. | Naoufal pose, Godwin note |

## Ce que fait chacun

Capacité avant le gel : environ 8 h par personne. Branches créées depuis `main` à jour, PR fusionnées en squash dans l'ordre B, A, C, D.

### Naoufal (flux A) : données, outils, README, doc technique

| Créneau | Tâche | Livrable | Terminé quand |
| --- | --- | --- | --- |
| 9 h 30 à 10 h 15 | P1-8, libellés français | `agent_tools.py` l. 270 à 277, branche `fix/evidence-labels-fr` | Plus de "equity" ni de "Consumer Discretionary" dans les libellés, PR à 10 h 15 |
| 10 h 15 à 12 h | P1-6, sensibilité | `scripts/run_sensitivity.py`, `outputs/reports/sensitivity.md` (Robert + TSLA 25 % : 5 ans, 3 ans, devise locale), branche `feat/sensitivity-report` | Tableau reproductible en une commande. Repli à 11 h 30 : tableau manuel dans la doc |
| 13 h à 14 h | P2-12, seuil de rendements, mentor | `metrics.py` l. 42 avec test, branche `fix/volatility-min-observations` ; questions D7 | Pas de volatilité annualisée sous le seuil ; réponse du mentor dans le canal |
| 14 h à 16 h | P0-3, README | Mode `offline`, tableau des verdicts aligné sur les boutons (TSLA25, NVDA15, BTC10, BTC40, XOM15), section sensibilité, branche `docs/readme-final` | Tout est juste, sauf le nombre de tests |
| 16 h à 18 h 30 | P0-3, doc technique | PR 42, ligne 56, mise à l'épreuve, limites, WBA en travaux futurs, `explainer_v5` | Plus aucun "en cours", scores insérés ou marqués à remplir |
| Soir | Vérification finale | Reproduction depuis un clone propre selon le README, nombre de tests final | Clone, installation, tests et application en `offline` sans erreur |
| Lundi matin | Doc technique | Relecture et export PDF | Déposée avant 13 h |

### Samer (flux B) : gouvernance, explication, one pager, intégrateur

| Créneau | Tâche | Livrable | Terminé quand |
| --- | --- | --- | --- |
| 9 h 30 à 10 h 45 | P1-7, contexte du profil | Champ facultatif `profile_context` (horizon, objectif, préférences) dans `explanation_brief.py`, et `contracts.py` si besoin, branche `feat/brief-profile-context` | Nom et forme du champ postés à 9 h 50, PR à 10 h 45 |
| 10 h 45 à 11 h 30 | P0-5, filet du contrefactuel | Rejet de "pas disponible" dans l'emplacement contrefactuel quand un contrefactuel existe, `explanation_validator.py`, branche `fix/validator-counterfactual-availability` | Le texte fautif de la trace est rejeté, 0 fausse alerte sur le gabarit |
| 11 h 30 à 12 h | Fusion 1 | Relecture et fusion, ordre B, A, C, D | `main` vert à 12 h 15 |
| 13 h à 14 h | P1-9, verdicts séparés | Statuts financier et ESG distincts, en champs facultatifs, dans `governance.py`, branche `feat/governance-split-esg-status` | Mateo + XOM : financier conforme (6 règles), ESG "information manquante" ; champ annoncé à Ibrahima à 13 h 15 |
| 14 h à 15 h | P0-4, one pager | Originalité, bénéfices concrets ; retrait de FRED, de 0,34 et de "affichage non relu", branche `docs/one-pager-final` | Les 6 éléments de l'énoncé présents, PDF d'essai sur une page |
| 15 h à 16 h | Vérification, P0-3 | Versionner `scripts/final_checks.sh` (Godwin fournit le fichier) ; une ligne dans `sprint_plan.md` (explainer_v5) et dans `use_case_decision.md` | Script vert sur `main` |
| 16 h à 18 h 30 | Fusions 2 et 3 | Fusion de 16 h 30 (dernier comportement), relectures, fusion du gel | `main` vert et gelé à 18 h 30 |
| Soir | Remise | Fusion des documents et des traces, `final_checks.sh`, confirmation avec Naoufal | `main` final poussé à 23 h |
| Lundi matin | P0-4, one pager | Version finale en PDF | Une page, déposée |

### Godwin (flux C) : agents, Bedrock, garde-fou, seul sur AWS

| Créneau | Tâche | Livrable | Terminé quand |
| --- | --- | --- | --- |
| 9 h 30 à 10 h | P0-2, compte et D3 | Vérification du compte et de la région, comparaison des versions 4 et 5 du garde-fou, essai Bedrock rapide | Version retenue annoncée dans le canal |
| 10 h à 11 h 45 | P0-5 et P1-7, prompt v5, faits de l'actif | `prompts/explainer_v5.md` ; appel systématique de `get_asset_facts` dans `analysis_pipeline.py` ; contrefactuel écrit par le code | Essai Bedrock sur Robert et Amira : pas de "pas disponible", actif seul cité, ancrage au-dessus du plancher |
| 11 h 45 à 12 h | P0-2, captures | Console AWS (garde-fou, versions, compartiment, Block Public Access) dans `outputs/figures/`, sans numéro de compte ni jeton | 4 à 6 captures enregistrées |
| 12 h 15 | P0-2, traces d'assurance | Une régénération rapide des traces sur `main` après la fusion 1, gardée si le compte coupe | Traces datées |
| 13 h à 14 h | P2-13, durcissement | `maxTokens` relevé, `ExpectedBucketOwner` dans `trace_store.py`, politique IAM de référence dans `aws_setup.md` | Aucune troncature sur 3 essais, tests verts |
| 14 h à 15 h | P2-10, trace honnête | Étiquette `caller` sur chaque appel d'outil, colonne "Décidé par" | La trace n'attribue plus à l'agent un appel du code |
| 15 h à 16 h | P0-3 et P0-1 | `aws_setup.md` mis à jour ; prises vidéo de secours des scènes trace et garde-fou | Plus de "non exécuté" ; 2 fichiers vidéo de secours |
| 16 h 30 à 18 h 30 | P0-2, traces finales | Régénération de `outputs/reports/demo_traces/` (Robert, Amira, Mateo ; novice et pro) sur `main` fusionné, mesure d'ancrage de bout en bout, README des traces | Scores transmis à Naoufal et Ibrahima à 18 h |
| Soir | P0-1, tournage | Enregistrement sur son poste de 19 h 30 à 21 h 30, jetons renouvelés à 19 h 15, audit de sécurité | 8 scènes capturées, fichiers remis à Ibrahima |
| Lundi matin | Réserve | Reprise d'une scène Bedrock avant 12 h seulement, relecture de la vidéo | Sans objet |

### Ibrahima (flux D) : interface, script de démo, vidéo

| Créneau | Tâche | Livrable | Terminé quand |
| --- | --- | --- | --- |
| 9 h 30 à 11 h | P0-1, script de démo | `docs/demo_script.md` (8 scènes minutées, voix, liste de contrôle) et `docs/video_plan.md`, branche `docs/demo-script` ; envoie à Godwin avant 10 h la commande exacte du diagnostic d'ancrage | Posté à 11 h pour relecture à la pause |
| 11 h à 12 h | P1-8, interface, lot 1 | `repaired_slots` affiché, titre "Conflit" nommant la règle, score, plancher 0,3 et `source_kind` dans la trace, branche `fix/ui-review-batch-1` | Visible sur Robert en `offline` |
| 13 h à 15 h | P1-8, interface, lot 2 | Règles au-dessus du tableau, libellé avant et après, "information manquante" en gris, nom de l'expander, ordre des preuves ; si le temps le permet, booléens et "0 pts" | 3 personas sans erreur |
| 15 h à 16 h | P1-9 et P1-7, affichage | Deux pastilles de verdict (financier, ESG), ligne "contexte du profil", branche `feat/ui-split-verdict` | Mateo montre 6 règles conformes et un ESG gris |
| 16 h à 17 h | P0-3, documents | `ui_spec.md`, `grounding_diagnosis.md` (version retenue) | PR ouverte |
| 17 h à 18 h 30 | P0-1, répétition | Répétition complète en `offline` sur `main`, script corrigé avec les boutons réels | Liste de contrôle cochée, 5 min au chronomètre |
| Soir | P0-1, tournage | Direction de l'enregistrement de 19 h 30 à 21 h 30, captures d'interface dans `outputs/figures/` | Toutes les scènes récupérées à 22 h |
| Lundi matin | P0-1, montage | Voix, montage, export de 7 h 30 à 11 h 30, relecture de l'équipe à 11 h 30 | Vidéo de 5 min au plus déposée avant 13 h |

## Tâches partagées : qui est responsable

**R** responsable unique, qui tranche et rend compte. **C** contributeur, avec ce qu'il livre et où. **V** relecteur.

| Tâche | R | C : livre quoi, où | V | Si quelqu'un est en retard |
| --- | --- | --- | --- | --- |
| P0-1 Vidéo | Ibrahima | Godwin : poste en mode Bedrock, prises, captures de console. Tous : relecture du script, 10 min à la pause | Samer | Scènes Bedrock en panne : prises de secours de 15 h 45 ; le reste en `offline` avec le bandeau |
| P0-2 Traces et captures AWS | Godwin | Ibrahima : commande et paramètres de `scripts/diagnose_grounding.py`, postés à 10 h | Naoufal (chiffres) | Compte coupé : les traces d'assurance de 12 h 15 sont livrées, l'écart est écrit dans le README des traces |
| P0-3 Documents périmés | Un par document | README et doc technique : Naoufal. `aws_setup.md` : Godwin. One pager, `sprint_plan.md`, `use_case_decision.md` : Samer. `ui_spec.md`, `grounding_diagnosis.md` : Ibrahima | Croisée A et B, C et D | Les documents ne sont pas gelés à 18 h 30. Le README passe en premier (23 h 59), le reste peut attendre lundi 11 h |
| P0-5 Contrefactuel "pas disponible" | Godwin | Godwin : prompt v5 et contrefactuel écrit par le code. Samer : rejet dans `explanation_validator.py` | Samer relit le prompt, Godwin le validateur | Le correctif de Godwin suffit ; le rejet n'est qu'un filet |
| P1-7 Robert : pourquoi l'idée heurte son profil | Samer | Samer : `profile_context` dans `explanation_brief.py`. Godwin : appel de `get_asset_facts` et règle de prompt. Ibrahima : ligne d'affichage | Naoufal | Sans Samer à 11 h : P1-7 glisse à 14 h 30. Sans Ibrahima : pas d'affichage, le texte suffit |
| P1-8 Interface et libellés | Ibrahima | Naoufal : libellés français dans `agent_tools.py` | Godwin | Naoufal en retard : table de traduction provisoire dans `ui_texts.py`. Les cosmétiques sautent d'abord |
| P1-9 ESG de Mateo | Samer | Samer : statuts distincts dans `governance.py`. Ibrahima : deux pastilles | Naoufal | Non fusionné à 16 h : abandon, scène Mateo réduite à 20 s |
| P2-11 Contrôle du sens des statuts | Godwin | Samer : avis sur le validateur | Sans objet | Abandonné (D6) ; décrit comme limite et travail futur dans la doc technique |
| Vérification finale | Samer | Samer : `final_checks.sh`. Naoufal : clone propre et README. Godwin : audit de sécurité et traces. Ibrahima : application sur 3 personas | Naoufal | À 23 h, on livre le dernier `main` vert, sans exception |

## Règles de coupe

- Fusion en squash dans l'ordre B, A, C, D à chaque jalon, nouvelle branche après chaque fusion.
- PR de comportement non fusionnée à 16 h 30 : abandonnée, sauf décision de Samer.
- PR de code non verte ou non relue à 18 h 30 : fermée sans discussion.
- Jamais sacrifiés : P0-1 à P0-5.

Ordre des sacrifices si le temps manque :

1. P2-11, contrôle des statuts
2. P2-10 au-delà de l'étiquette
3. `alignment_summary` (P2-12)
4. Cosmétiques de P1-8 ("0 pts", booléens, ordre des preuves)
5. Script de sensibilité, remplacé par le tableau manuel
6. Affichage de P1-7
7. P1-9, verdicts séparés
8. `ExpectedBucketOwner` et politique IAM
9. P1-7 en entier

## Avancement du flux C (mis à jour)

| Élément | État |
| --- | --- |
| P0-5, P1-7 côté pipeline, P2-10 réduit | PR 51 ouverte. Robert validé sur Bedrock. Amira à reconfirmer après le correctif du contrefactuel |
| P2-13, durcissement S3 et maxTokens | PR 52 ouverte, audit de sécurité conforme |
| P0-3, `aws_setup.md` | PR 53 ouverte |
| P0-2, traces finales et captures | À faire après la fusion de 16 h 30 |

## Risques

- **Chaîne des traces sur une seule personne.** La fusion de 16 h 30, les traces et les scores dans les documents reposent sur Godwin. Parade : traces d'assurance de 12 h 15 et prises de secours de 15 h 45.
- **Prompt modifié le dernier jour.** Le v5 peut faire remonter les rejets du validateur. Mesurer avant la fusion 1 ; repli sur v4.
- **Samer surchargé.** Trois tâches de code plus l'intégration. Si P1-9 glisse, il saute.
- **Jetons expirés ou compte fermé plus tôt.** Le compte à rebours de Workshop Studio peut différer de l'heure annoncée.
- **Réponse défavorable du mentor sur Yahoo.** Il faudrait retirer `data/raw/prices_daily.csv` et s'appuyer sur `scripts/build_dataset.py`. À savoir avant 15 h.

## Irréversible après lundi 13 h 59

- Les captures de la console AWS.
- Les scènes vidéo en mode Bedrock.
- Les traces S3 et les mesures d'ancrage.
- La configuration du garde-fou et le texte de la politique IAM.

Tout cela doit être dans le dépôt ou sur les postes dimanche soir. Le code est figé dès dimanche 23 h 59.
