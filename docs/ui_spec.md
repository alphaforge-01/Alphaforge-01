# Spec du flux D : interface Streamlit

Statut : brouillon à valider. Propriétaire : Ibrahima (flux D). Branche : `feat/streamlit-ui`.

Sources : `docs/sprint_plan.md` (sections 1, 3, 4 et 5), `docs/user_stories.md`, `src/alphaforge/contracts.py`, `src/alphaforge/profiles.py` (flux B, en cours).

Échéance : l'application doit être sur `main` **dimanche 15 novembre avant 23 h 59**. Lundi ne sert qu'à la vidéo et aux documents, jamais au code (`docs/sprint_plan.md`, section 1).

## 1. Exigences

L'interface ne calcule rien. Elle lit des objets du contrat (`AnalysisResult`, `ExplanationResult`, `GuardrailResult`) et les affiche.

| US | Ce que l'interface affiche | Données lues | Tâche |
| --- | --- | --- | --- |
| US-01 | Trois cartes : nom, âge, métier, résumé, risque, horizon, objectif. Un clic charge le profil et son portefeuille. Badge "profil fictif". Niveau prérempli | `load_personas()` : `profile`, `portfolio`, `age`, `occupation_fr`, `summary_fr`. `profile.default_level` | D2a |
| US-02 | Formulaire par cases et curseurs. Erreurs bloquantes, contradictions signalées, points d'information. Seuils étiquetés "hypothèse de l'équipe". Aucun champ de texte : l'objectif est une liste fermée | `check_answers`, `build_profile_from_answers`, `ProfileValidationError.issues` | D2b |
| US-03 | Radiographie : volatilité, perte maximale et ses dates, durée de récupération, plus gros poids, part défensive, exposition USD/CAD, poids par secteur et par classe. Période de calcul. Statut par règle | `snapshot_before`, `governance_before`, `evidence` | D3 |
| US-04 | Sélecteurs : actif (univers), poids visé (0 à 100 %, pas de 1 point), source des fonds (au prorata ou depuis un titre détenu). Idées en un clic, dont "25 % dans TSLA". Message clair si l'idée est invalide | Univers (fonction à demander à A), `portfolio_before.positions` | D4a, D4b |
| US-05 | Avant et après côte à côte, sens de l'écart. Montants en dollars formulés comme "perte historique observée sur telle période, appliquée au capital fictif" | `snapshot_before`, `snapshot_after`, `evidence` | D4a |
| US-06 | Règles en conflit, puis en tension, puis manquantes, puis conformes. Pour chacune : libellé, valeur, seuils, statut. Statut global en tête | `governance_after.checks`, `overall_status` | D4a |
| US-07 | "Conforme à X % ou moins", ou "aucun poids testé n'est conforme". Marge pour les règles conformes | `RuleCheck.counterfactual`, `RuleCheck.margin` | D4a |
| US-08 | Au plus deux variantes dans un encadré "Simulation" : motif, idée, statut global, statuts par règle. Mention "simulation, pas une recommandation" | `variants` | D4b |
| US-09 | Changer de profil garde l'idée. Si la source des fonds est un titre que le nouveau profil ne détient pas, elle repasse à "au prorata" avec un message | état de session | D4b |
| US-10 | Bascule novice/pro. Seconde bascule instantanée. Badge "texte de repli" si le gabarit est utilisé | `explain(result, level)`, `output.origin`, `rendered_markdown` | D5 |
| US-11 | Bouton "Vérifier" sur chaque chiffre : libellé, valeur, outil, sources, période, devise, transformation, nombre d'observations, limites. Sous l'explication, la liste des preuves citées, chacune vérifiable | `EvidenceEntry`, `validation.checked_references`, `limits`, `data/raw/sources_metadata.csv` | D5 |
| US-12 | Avertissement en haut de chaque onglet. Limites au texte fixe du niveau. Faits, hypothèses et simulations dans des zones distinctes | `limits[].text_novice`, `limits[].text_pro` | D1, D5 |
| US-13 | Six étapes, chacune étiquetée "agent", "code" ou "garde-fou". Étape 1 : outils appelés, paramètres, numéros de preuve. Bouton "Ce que l'explicateur a vu". Jamais de raisonnement interne | `AnalysisResult.trace` (1 à 3), `ExplanationResult.trace` (4 à 6), dossier d'explication | D6 |
| US-14 | Onglet de test du garde-fou : requêtes prédéfinies, permises et refusées, présentées en conversation. Sujet refusé affiché. Score d'ancrage à l'étape 6 | `check_request(text)`, `GuardrailResult` | D7 |
| US-15 | Mode affiché en permanence. Une erreur de chargement ou de Bedrock affiche un message, la page ne plante pas | `mode`, exceptions de `data_source` | D1, D4a |
| US-19 (P2) | Deux colonnes, même idée, deux profils | deux `AnalysisResult` | D10 (P2) |

## 2. Règles d'affichage

1. **Chiffre calculé** (métrique, poids après simulation, montant) : toujours le `display_value` d'une entrée du registre, trouvée par `evidence_key` (`<metric>:<subject>`). Sans entrée : "non disponible". Jamais une valeur brute mise en forme par l'interface.
2. **Paramètre** (seuil d'une règle, poids choisi par l'utilisateur, capital fictif) : mis en forme par `app/formatting.py`, au format français ("25 %", "100 000 $"). Ce ne sont pas des résultats de calcul.
3. **Statuts** : couleur et texte, jamais la couleur seule. Conforme (vert), Tension (orange), Conflit (rouge), Information manquante (gris). Aucun emoji.
4. **Textes** : tous dans `app/ui_texts.py`, en français. Le code reste en anglais.
5. **Zones** : faits (cartes de métriques), hypothèses (encadré "Hypothèses de l'équipe"), simulations (encadré "Simulation").
6. **Données d'essai** : si `is_fixture` est vrai, un bandeau "Données d'essai : chiffres inventés" est affiché en haut.

## 3. Conception

### Fichiers (tous dans `app/`)

| Fichier | Rôle |
| --- | --- |
| `streamlit_app.py` | Point d'entrée : configuration de la page, onglets, initialisation de l'état de session |
| `data_source.py` | Seul point de contact avec `src/` et les fixtures. Fonctions : `get_personas`, `get_universe`, `get_analysis`, `get_explanation`, `check_request` |
| `ui_texts.py` | Libellés, messages, statuts, motifs de variantes, avertissement |
| `formatting.py` | Mise en forme des paramètres seulement (règle 2) |
| `components/banners.py` | Avertissement, bandeau de données d'essai, mode |
| `components/profile_panel.py` | Cartes des personas, formulaire de profil construit |
| `components/evidence.py` | Recherche d'une preuve par clé, carte de métrique avec bouton "Vérifier" |
| `components/xray.py` | Radiographie |
| `components/idea_panel.py` | Sélecteurs et idées en un clic |
| `components/result_panel.py` | Avant/après, règles, contrefactuel, variantes |
| `components/explanation_panel.py` | Bascule de niveau, texte rendu, preuves citées, limites |
| `components/trace_panel.py` | Trace à six étapes, dossier transmis |
| `components/guardrail_panel.py` | Test du garde-fou |
| `components/sources_panel.py` | Sources et méthode |

`streamlit_app.py` ajoute `src/` au chemin d'import à partir de `Path(__file__).resolve().parents[1]`, comme `tests/test_contracts.py`.

Lancement, depuis la racine du projet : `streamlit run app/streamlit_app.py`.

### Modes de données

| Mode | Source | Usage |
| --- | --- | --- |
| `fixture` | `tests/fixtures/analysis_result_<profil>_tsla.json` et `explainer_output_*.json` | Jusqu'à J2. Seule l'idée "25 % dans TSLA" est disponible |
| `offline` | `run_analysis(..., mode="offline")` et `explain(..., mode="offline")` | Dès que C3 est fusionné. Filet de la démo |
| `bedrock` | mêmes fonctions, `mode="bedrock"` | Dès J4 |

La valeur initiale du mode vient de `ALPHAFORGE_MODE` (`fixture` si absente ou inconnue). Le mode se change dans la barre latérale, où il reste affiché.

En mode `fixture`, les profils et les portefeuilles viennent aussi des fixtures d'analyse, pour rester cohérents avec les chiffres affichés. En modes `offline` et `bedrock`, ils viennent de `load_personas()`.

### Mise en page

- Onglets : "Analyse", "Test du garde-fou", "Sources et méthode".
- Onglet "Analyse", dans l'ordre de la démo : Profil, Radiographie, Idée, Résultat, Explication, Trace (section repliable).
- Barre latérale : avertissement, profil actif, mode.

### État de session

| Clé | Contenu |
| --- | --- |
| `profile_id` | "robert", "amira", "mateo" ou "custom" |
| `custom_profile` | `InvestorProfile` construit, ou absent |
| `idea` | `InvestmentIdea` en cours, conservée au changement de profil |
| `analysis` | dictionnaire `(profile_id, idée) -> AnalysisResult` |
| `explanations` | dictionnaire `(run_id, level) -> ExplanationResult` |
| `level` | "novice" ou "pro" |

Les personas et l'univers sont mis en cache avec `st.cache_data`.

## 4. Demandes aux autres flux

À faire avant le gel des contrats (samedi 20 h 30), car ce sont des ajouts au contrat ou des décisions qui le touchent.

| Flux | Demande | Pourquoi |
| --- | --- | --- |
| B (Samer) | Trancher le niveau par défaut des personas : les fixtures disent "novice" pour Robert et Amira, `build_profile_from_answers` et US-01 disent "pro" sauf débutant | US-01 |
| B | Revoir Amira avec "25 % dans TSLA" : la fixture la donne "conforme" avec une seule règle | Scène 2 |
| B | Clé facultative `margin_display` dans `RuleCheck` | US-07, règle d'affichage 1 |
| B | Liste fermée des objectifs pour le formulaire | US-02 sans texte libre |
| B, C | Clé facultative `brief` (dossier transmis) dans `ExplanationResult` | US-13, "Ce que l'explicateur a vu" |
| A (Naoufal) | Liste des `evidence_key` produites, une par chiffre affiché en radiographie et en comparaison | Règle d'affichage 1 |
| A | `load_universe()` : ticker, nom, classe, devise, secteur | US-04 |
| A | Écart avant/après : entrées de preuve dédiées, ou l'interface affiche seulement le sens | US-05 |
| C (Godwin) | `run_analysis(mode="offline")` fusionné pour J2 (23 h 30), sinon l'interface reste en mode `fixture` | J2 |
| C, B | Radiographie avant toute idée : aucune fonction gelée ne la fournit, car `run_analysis` exige une idée. Proposition : `run_xray(profile, portfolio, as_of=None) -> AnalysisResult` partiel (`snapshot_before`, `governance_before`, `evidence`, `limits`, trace), dans `analysis_pipeline.py`. Sinon, la radiographie ne s'affiche qu'après l'idée | US-03, parcours étape 2 |
| B | La fixture d'Amira reprend le portefeuille de Robert (`label_fr` : "Portefeuille fictif de Robert") | Scène 2 |

## 5. Tâches

### Sprint 1 : samedi soir, jusqu'à J2 (23 h 30)

- [x] D1. Squelette : environnement Python 3.11, `streamlit_app.py`, onglets, avertissement, bandeau de données d'essai, mode affiché, `data_source.py` en mode `fixture`, `ui_texts.py`, `formatting.py` (US-12, US-15)
- [x] D2a. Cartes des personas (Robert et Amira depuis les fixtures), badge "profil fictif", niveau prérempli (US-01). Reste : Mateo, l'âge, le métier et le résumé arrivent avec `load_personas` (flux B)
- [ ] D3. Radiographie : cartes de métriques par le registre, période, poids par secteur et par classe, statut par règle (US-03)
- [ ] D4a. Idée "25 % dans TSLA" en un clic, avant/après, règles triées par gravité, contrefactuel, marges (US-05, US-06, US-07)
- [ ] J2. Brancher `offline` si C3 est fusionné. PR `feat(ui): ...` relue et fusionnée

Terminé quand : la scène 1 se joue en mode `fixture` sans erreur, l'avertissement est visible dans chaque onglet, aucun chiffre calculé ne vient d'ailleurs que du registre.

### Sprint 2 : dimanche (S3 et S4), jusqu'au gel (J5, 18 h 30)

- [ ] D2b. Formulaire de profil construit (US-02)
- [ ] D4b. Sélecteurs complets, variantes, changement de profil qui garde l'idée (US-04, US-08, US-09)
- [ ] D5. Explication : bascule, cache, preuves citées, limites, bouton "Vérifier" partout (US-10, US-11, US-12)
- [ ] D6. Trace à six étapes, dossier transmis (US-13)
- [ ] D7. Test du garde-fou (US-14)
- [ ] D8. Sources et méthode, finitions (US-11)
- [ ] D10 (P2). Deux profils côte à côte (US-19), seulement si J4 est vert

Terminé quand : les scènes 1 à 5 se jouent en mode `offline` et en mode `bedrock`, et l'application est sur `main` avant dimanche 23 h 59.

### Sprint 3 : dimanche soir et lundi matin (aucun code)

Après le gel, seulement des corrections de bogues dans des branches `fix/...`, et jamais après dimanche 23 h 59.

- [ ] D9a. Script de démo et liste de contrôle manuelle dans `docs/demo_script.md` (dimanche 19 h 30)
- [ ] D9b. Script final, `docs/video_plan.md`, enregistrement dimanche soir, montage, captures dans `outputs/figures/`. Vidéo déposée lundi avant 14 h

## 6. Vérification

- Pas de tests d'interface versionnés (décision du plan). Avant chaque PR : lancement réel, puis la liste de contrôle de `docs/demo_script.md`.
- Contrôle rapide hors navigateur avec `streamlit.testing.v1.AppTest` (non versionné) : la page s'exécute sans exception pour chaque persona.
- Recherche dans le diff : aucun tiret cadratin, aucun emoji, aucun secret.

## 7. Questions ouvertes

1. Onglets ou page unique pour la vidéo ? Par défaut : onglets.
2. Libellé exact de l'avertissement : à reprendre des textes fixes de B (`fixed_texts.json`) dès qu'ils existent.
3. Écart avant/après : chiffre (preuve dédiée de A) ou sens seulement ?
