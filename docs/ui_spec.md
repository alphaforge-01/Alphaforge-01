# Spec du flux D : interface Streamlit

Statut : interface complète branchée sur le pipeline, revue statique et scènes jouées en offline. Propriétaire : Ibrahima (flux D).

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
| US-06 | Règles en conflit, puis en tension, puis manquantes, puis conformes. Pour chacune : libellé, valeur, seuils, statut. Statut global en tête, suivi des pastilles "Financier" et "ESG" quand le profil a une règle ESG (verdicts séparés du flux B, P1-9 ; rien pour Robert et Amira). Mêmes pastilles dans les réponses compactes et les variantes | `governance_after.checks`, `overall_status`, `split_verdicts` | D4a |
| US-07 | "Conforme à X % ou moins", ou "aucun poids testé n'est conforme". Marge pour les règles conformes | `RuleCheck.counterfactual`, `RuleCheck.margin` | D4a |
| US-08 | Au plus deux variantes dans un encadré "Simulation" : motif, idée, statut global, statuts par règle. Mention "simulation, pas une recommandation" | `variants` | D4b |
| US-09 | Changer de profil remet la simulation à zéro : fil vidé, idée oubliée, sélecteurs par défaut (choix de l'équipe, remplace la reprise de l'idée). Une idée dont la source des fonds n'est pas détenue par le profil est financée au prorata, avec un message | état de session | D4b |
| US-10 | Curseur Novice / Pro (curseur dans la barre latérale ; sur l'accueil, deux boutons centrés Novice et Pro, dont l'info-bulle montre un passage réel). Seconde bascule instantanée. Badge "Rédigé par l'agent explicateur" et résumé de l'agent sous les points clés ; un texte standard (gabarit) n'est montré que dans l'onglet "Explication complète", avec la raison du repli en mode Bedrock. Avant : le gabarit est utilisé | `explain(result, level)`, `output.origin`, `rendered_markdown` | D5 |
| US-11 | Bouton "Vérifier" sur chaque chiffre : libellé, valeur, outil, sources, période, devise, transformation, nombre d'observations, limites. Sous l'explication, la liste des preuves citées, chacune vérifiable | `EvidenceEntry`, `validation.checked_references`, `limits`, `data/raw/sources_metadata.csv` | D5 |
| US-12 | Avertissement dans le bandeau du haut, toujours visible sur chaque page (une seule fois, pour ne pas le diluer). Limites au texte fixe du niveau. Faits, hypothèses et simulations dans des zones distinctes | `limits[].text_novice`, `limits[].text_pro` | D1, D5 |
| US-13 | Six étapes, chacune étiquetée "agent", "code" ou "garde-fou". Étape 1 : outils appelés, paramètres, numéros de preuve. Bouton "Ce que l'explicateur a vu". Jamais de raisonnement interne | `AnalysisResult.trace` (1 à 3), `ExplanationResult.trace` (4 à 6), dossier d'explication | D6 |
| US-14 | Page de test du garde-fou : requêtes prédéfinies, permises et refusées, présentées en conversation. Sujet refusé affiché. Score d'ancrage à l'étape 6 | `check_request(text)`, `GuardrailResult` | D7 |
| US-15 | Mode affiché en permanence. Une erreur de chargement ou de Bedrock affiche un message, la page ne plante pas | `mode`, exceptions de `data_source` | D1, D4a |
| US-19 (P2) | Deux colonnes, même idée, deux profils | deux `AnalysisResult` | D10 (P2) |

## 2. Règles d'affichage

1. **Chiffre calculé** (métrique, poids, montant, écart avant/après) : toujours le `display_value` d'une entrée du registre, trouvée par `evidence_key` (`<metric>:<subject>`). Le chiffre est lui-même le bouton qui ouvre sa preuve. Sans entrée : "non disponible". L'interface ne calcule jamais rien.
2. **Paramètre** (seuil d'une règle, poids choisi par l'utilisateur, capital fictif, dates) : mis en forme par `app/formatting.py`, au format français ("25 %", "100 000 $", "12 nov. 2021"). Seule valeur calculée sans texte prêt dans le contrat : la marge d'une règle, calculée par la gouvernance (flux B) et mise en forme en points avec la fonction de l'explication (`format_points`), pour un format identique partout. Les métadonnées de la trace (durées des étapes, scores d'ancrage et de pertinence du garde-fou) sont affichées telles que le pipeline les rend : ce ne sont pas des chiffres financiers.
3. **Statuts** : couleur et texte, jamais la couleur seule. Conforme (vert), Tension (orange), Conflit (rouge), Information manquante (gris). Aucun emoji.
4. **Textes** : tous dans `app/ui_texts.py`, en français. Le code reste en anglais.
5. **Zones** : faits (cartes de métriques), hypothèses (encadré "Hypothèses de l'équipe"), simulations (encadré "Simulation").
6. **Données d'essai** : si `is_fixture` est vrai, un bandeau "Données d'essai : chiffres inventés" est affiché en haut.

## 3. Conception

### Fichiers (tous dans `app/`)

| Fichier | Rôle |
| --- | --- |
| `streamlit_app.py` | Point d'entrée : thème et CSS, navigation (`st.navigation`), barre latérale (mode, niveau Novice / Pro, profil actif, avertissement), en-tête compact (mode, profil, idée, avertissement), bandeau de données d'essai, exécution de la page choisie |
| `navigation.py` | Déclaration des pages, liens entre pages, message "il manque ..." avec lien, bouton "Étape suivante" |
| `session.py` | État de session, rappels (profil, idée, conversation, mode, niveau), chargement avec mémoire des échecs (`cached_load`), protection des sections (`guarded`), contexte du profil actif |
| `data_source.py` | Point de contact avec `src/` et les fixtures. Fonctions : `get_personas`, `check_profile_answers`, `build_custom_persona`, `get_universe`, `get_sources`, `get_reference_limits`, `get_threshold_notice`, `get_guardrail_prompts`, `get_bedrock_status`, `get_xray`, `get_analysis`, `get_explanation`, `get_asset_facts`, `rule_metric`, `check_request`, `parse_request`, `get_level_preview` |
| `ui_texts.py` | Tous les textes : libellés courts, messages, statuts, zones, questions de clarification, avertissement, idées de démonstration |
| `formatting.py` | Mise en forme des paramètres et des marges (règle 2), extraction de la section "Résumé" d'une explication rendue. Aucun calcul |
| `views/home_page.py` | Accueil : cartes des personas (un clic choisit le profil et ouvre la simulation), lien vers le profil construit, deux boutons centrés Novice et Pro, avec une info-bulle au survol de chacun (description du niveau et passage réel) |
| `views/simulation_page.py` | Radiographie repliable, réglages manuels, conversation avec l'agent et champ de saisie |
| `views/custom_profile_page.py` | Formulaire du profil construit, inchangé |
| `views/guardrail_page.py`, `views/sources_page.py` | Test du garde-fou, sources et méthode |
| `components/style.py` | Seul module qui injecte du CSS : en-tête, pastilles de statut, verdict, étiquettes de zones, cartes alignées |
| `components/banners.py` | En-tête, avertissement, bandeau de données d'essai, titre de page |
| `components/conversation.py` | Fil : demandes, réglages manuels, refus, questions de clarification, réponse courte puis détail |
| `components/profile_panel.py` | Cartes des personas, formulaire de profil construit (réponses gardées entre les pages) |
| `components/evidence.py` | Recherche d'une preuve par clé, chiffre cliquable, carte de métrique, contenu de la preuve |
| `components/rules.py` | Statut par règle : mesure, seuils, marge, contrefactuel ; points clés d'une réponse |
| `components/xray.py` | Radiographie : zone faits (cartes), zone hypothèses (règles), composition et méthode repliées |
| `components/idea_panel.py` | Idées en un clic et sélecteurs, validés par "Simuler" |
| `components/result_panel.py` | Verdict (statut global, règles en conflit ou en tension, contrefactuel), détail en onglets : avant/après (simulation), règles (hypothèses), faits sur l'actif, variantes |
| `components/explanation_panel.py` | Badge d'origine (agent ou gabarit), texte complet, preuves citées |
| `components/trace_panel.py` | Trace à six étapes, dossier transmis |
| `components/guardrail_panel.py` | Test du garde-fou |
| `components/sources_panel.py` | Sources et méthode |

Côté `src/alphaforge/`, `request_parsing.py` traduit une demande en langage naturel en idée, par des règles déterministes testées (`tests/test_request_parsing.py`) : aucun appel à un modèle.

`streamlit_app.py` ajoute `src/` au chemin d'import à partir de `Path(__file__).resolve().parents[1]`, comme `tests/test_contracts.py`.

Lancement, depuis la racine du projet : `streamlit run app/streamlit_app.py`.

### Modes de données

| Mode | Source | Usage |
| --- | --- | --- |
| `offline` (défaut) | Données réelles : `run_analysis(..., mode="offline")` et `explain(..., mode="offline")` | Démo sans réseau, filet de la démo |
| `bedrock` | Mêmes fonctions, `mode="bedrock"`. Configuration lue dans l'environnement ; si elle est incomplète, le pipeline revient au hors ligne et l'interface l'affiche | Démo complète |
| `fixture` | `tests/fixtures/analysis_result_<profil>_tsla.json`. Seule l'idée "25 % dans TSLA" est disponible | Secours si les données réelles manquent |

La valeur initiale du mode vient de `ALPHAFORGE_MODE` (`offline` si absente ou inconnue). Le mode se change dans la barre latérale, où il reste affiché. En mode `bedrock`, la barre latérale indique si les modèles, le garde-fou et le compartiment des traces sont configurés (oui ou non, aucun identifiant).

En mode `fixture`, les profils et les portefeuilles viennent aussi des fixtures d'analyse, pour rester cohérents avec les chiffres affichés. En modes `offline` et `bedrock`, ils viennent de `load_personas()`.

La radiographie avant toute idée (`get_xray`) n'utilise que du code déterministe : l'outil `analyze_portfolio` du flux A, passé par la `ToolBox` du flux C pour enregistrer les preuves, puis `evaluate` du flux B. Aucun agent n'est appelé, le résultat est le même en `offline` et en `bedrock`. De même, les faits sur l'actif de l'idée (`get_asset_facts`, outil du flux A) ne dépendent pas du profil : ils montrent que la même idée donne les mêmes chiffres de l'actif pour tous les profils (US-09).

L'analyse d'une idée est gardée en cache par profil : refaire pour un profil une idée déjà analysée est instantané. Changer de profil remet la simulation à zéro (fil, idée, sélecteurs) : rien d'un profil précédent ne reste affiché. En mode `bedrock`, aucun agent n'est lancé sans demande explicite (quotas partagés) : un message dans le chat, "Simuler" ou une idée en un clic demandent à la fois l'analyse et l'explication ; un changement de mode affiche "Analyser cette idée pour ce profil" ; un changement de niveau, ou l'ouverture de la page après ce changement, affiche "Rédiger l'explication (niveau X)" tant que l'explication de ce niveau n'est ni en cache ni en échec. Ces demandes sont remises à faux au changement de profil ou de mode, et après usage. Un curseur ne lance jamais rien. En `offline`, l'explication par gabarit est produite sans clic.

Le mode choisi dans la barre latérale est transmis au pipeline par la configuration (`BedrockConfig` avec `mode` surchargé) : choisir Bedrock fonctionne même si l'application a été lancée sans `ALPHAFORGE_MODE=bedrock`.

### Mise en page

- Navigation multipage (`st.navigation`, Streamlit 1.67) dans la barre latérale. "Parcours" : Accueil, Simulation, Créer un profil fictif. "Vérifier" : Test du garde-fou, Sources et méthode. Icônes Material, aucun emoji.
- En-tête compact sur chaque page : marque, mode, profil et idée actifs, avertissement court toujours visible ; bandeau de données d'essai dessous si `is_fixture` ou mode `fixture`.
- Barre latérale, rendue avant la page pour rester utilisable si une section échoue : navigation, mode, niveau Novice / Pro, résumé du profil actif, avertissement.
- Accueil : une phrase d'accroche, deux boutons centrés Novice et Pro (le niveau choisi est mis en avant) avec une info-bulle au survol de chacun (description et passage réel) (au-dessus des cartes : le niveau réglé n'est plus écrasé par le choix du profil), cartes des trois personas, de même hauteur (un clic choisit le profil et ouvre la simulation), lien vers le profil construit. L'aperçu est la section "Résumé" de textes réels de l'agent explicateur (`outputs/reports/demo_traces/<persona>_explanation_<niveau>.json`, Robert si le profil actif n'a pas de trace), avec sa source.
- Simulation : radiographie derrière un interrupteur, réglages manuels dans un encadré repliable, puis le fil de conversation et le champ de saisie.
- Demande écrite : garde-fou Bedrock (`check_request`), puis contrôle local des sujets interdits (actif même hors ligne), puis traduction déterministe (`parse_request`). Refus : sujet affiché et origine du refus. Demande ambiguë ou incomplète (actif hors univers, deux actifs, pas de poids, poids non entier ou hors de 1 % à 100 %, titre vendu sans actif cible, titre de financement non détenu) : une question, jamais une supposition ; s'il ne manque que le poids, quatre poids proposés en un clic ; un poids décimal propose son arrondi ; avec deux actifs, un bouton par actif qui garde la source des fonds. Sinon, l'idée passe par `get_analysis` puis `get_explanation`, comme en mode manuel.
- Réglage manuel : un curseur ne lance rien ; "Simuler" ou une idée en un clic s'inscrit dans le fil ("Paramètres modifiés : ...") et met à jour la même idée que le chat.
- Réponse : idée simulée et état du garde-fou, verdict (pastille, phrase, règles en conflit ou en tension avec leur contrefactuel), trois points clés avec chiffres cliquables, badge d'origine et section "Résumé" de l'explication, avertissement. "Voir le détail" ouvre quatre onglets : faits, hypothèses et simulation (zones distinctes) ; explication complète et preuves citées ; sources et limites ; trace et "Ce que l'explicateur a vu". Seule la réponse la plus récente est détaillée, les précédentes restent compactes.
- Chaque section est protégée : une erreur affiche un message à sa place, l'exception est écrite dans la console du serveur, le reste de la page continue.

### État de session

| Clé | Contenu |
| --- | --- |
| `mode` | "offline", "bedrock" ou "fixture" |
| `profile_id` | "robert", "amira", "mateo" ou "custom" |
| `custom_persona` | persona (profil et portefeuille) construit, ou absent ; retiré au changement de mode |
| `chat_history` | fil de la conversation : demandes, réglages manuels, notes (mode), refus, questions, réponses. Chaque réponse garde sa clé d'analyse complète (mode, profil, portefeuille, idée) et le nom de son profil : une réponse ancienne montre toujours son propre verdict |
| `idea` | dernière `InvestmentIdea` soumise, oubliée au changement de profil. Si sa source des fonds n'est pas détenue par le profil, l'idée est financée au prorata, avec un message |
| `level` | "novice" ou "pro", prérempli par le profil et repris de lui après un changement de mode |
| `xray_cache`, `analysis_cache`, `explanation_cache` | résultats par `(mode, profil, portefeuille)`, `(mode, profil, portefeuille, idée)` et `(mode, run_id, niveau)` |
| `xray_failures`, `analysis_failures`, `explanation_failures` | échecs mémorisés aux mêmes clés, avec un bouton "Réessayer" pour les erreurs (quotas Bedrock partagés) |
| `analysis_request`, `explanation_request`, `level_chosen`, `level_reset`, `asset_cache`, `asset_failures`, `guardrail_pending` | demandes explicites d'analyse et d'explication en mode bedrock (quotas partagés), niveau réglé par l'utilisateur (le choix d'un profil ne l'écrase plus), reprise du niveau au changement de mode, faits sur l'actif mémorisés, requête du garde-fou en attente |
| `guardrail_history` | requêtes testées dans l'onglet du garde-fou et leurs verdicts |

Les personas sont relus à chaque exécution (fichiers JSON locaux, coût négligeable).

## 4. Demandes aux autres flux

État au samedi soir, après la fusion des flux A, B et C.

| Flux | Demande | État |
| --- | --- | --- |
| B (Samer) | Niveau par défaut des personas | Réglé : `investor_profiles.json` met les trois personas en "pro", conforme à US-01 |
| B | Verdict d'Amira avec "25 % dans TSLA" | Réglé : tension sur ses vraies règles (Robert : conflit, Mateo : information manquante sur la règle ESG tant qu'aucune preuve ESG n'existe) |
| B | Clé `margin_display` dans `RuleCheck` | Non fournie : la marge brute de la gouvernance est mise en forme avec `format_points` (règle d'affichage 2) |
| B | Liste fermée des objectifs pour le formulaire | Non fournie : liste du flux D dans `ui_texts.py`, à confirmer |
| B, C | Clé `brief` dans `ExplanationResult` | Réglé (PR 25) : affichée par "Ce que l'explicateur a vu" |
| A (Naoufal) | Une `evidence_key` par chiffre affiché | Réglé : radiographie, comparaison, écarts (`*_delta`), poids par position, classe et secteur, variantes |
| A | `load_universe()` | Réglé (`data_loading.py`) |
| A | Écart avant/après | Réglé : preuves `<metric>_delta:portfolio_after` |
| C (Godwin) | `run_analysis(mode="offline")` | Réglé : branché, données réelles |
| C, B | Radiographie avant toute idée | Réglé côté interface : `get_xray` compose `analyze_portfolio`, la `ToolBox` et `evaluate`, sans agent |
| C | Message précis quand l'idée est impossible | Le pipeline garde un message général : `get_analysis` redemande la raison exacte à l'outil de simulation (par exemple "NVDA ne pèse que 15 %") |

## 5. Tâches

### Sprint 1 : samedi soir, jusqu'à J2 (23 h 30)

- [x] D1. Squelette : environnement Python 3.11, `streamlit_app.py`, onglets, avertissement, bandeau de données d'essai, mode affiché, `data_source.py` en mode `fixture`, `ui_texts.py`, `formatting.py` (US-12, US-15)
- [x] D2a. Cartes des personas, badge "profil fictif", niveau prérempli (US-01). En mode `fixture` : Robert et Amira. En modes `offline` et `bedrock` : les trois personas avec âge et métier, par `load_personas` (fusionné dans la PR 8)
- [x] D2b. Formulaire de profil construit (US-02), avancé du sprint 2. Contrôle relancé à chaque changement : erreurs, contradictions et points d'information de `check_answers` affichés tout de suite. Règles et seuils produits par `build_profile_from_answers`, chacun étiqueté "Hypothèse de l'équipe". Deux choix du flux D, à confirmer : la liste fermée des objectifs (`OBJECTIVE_OPTIONS` dans `ui_texts.py`, en attendant celle du flux B) et le portefeuille de départ, choisi parmi ceux des personas
- [x] D3. Radiographie : huit cartes de métriques par le registre, période et dates de la perte maximale, statut par règle, composition (positions, classes, secteurs), chaque chiffre cliquable (US-03)
- [x] D4a. Idées en un clic dont "25 % dans TSLA", avant/après avec l'écart du registre, règles triées par gravité, seuils, marges, contrefactuel (US-05, US-06, US-07)
- [x] J2. `offline` branché sur les vrais outils, la vraie gouvernance et le gabarit

Terminé quand : la scène 1 se joue en mode `fixture` sans erreur, l'avertissement est visible dans chaque onglet, aucun chiffre calculé ne vient d'ailleurs que du registre.

### Sprint 2 : dimanche (S3 et S4), jusqu'au gel (J5, 18 h 30)

- [x] D4b. Sélecteurs complets (actif de l'univers, poids de 1 à 100 %, source des fonds avec le poids actuel du titre), variantes dans un encadré "Simulation", changement de profil qui remet la simulation à zéro (US-04, US-08, US-09)
- [x] D5. Explication : bascule novice/pro qui ne relance que l'explicateur, cache par niveau, origine du texte (agent ou gabarit), preuves citées cliquables, limites dans le texte fixe du flux B (US-10, US-11, US-12)
- [x] D6. Trace à six étapes : acteur, statut, durée, modèle, outils appelés avec paramètres et preuves, raisons de repli, scores du garde-fou, trace S3, "Ce que l'explicateur a vu" (US-13)
- [x] D7. Test du garde-fou : requêtes prédéfinies du flux C, permises et refusées, verdict en conversation avec le résultat attendu (US-14)
- [x] D8. Sources et méthode : provenance des données, limites fixes, hypothèse des seuils, univers des actifs (US-11)
- [x] US-18 (P2). Groupe corrélé : carte en radiographie et dans la comparaison, période, jours communs et méthode lus dans la preuve, règle R7 d'Amira, idée "40 % dans BTC-USD".
- [ ] D10 (P2). Deux profils côte à côte (US-19) : abandonné sur décision de l'équipe

Terminé quand : les scènes 1 à 5 se jouent en mode `offline` et en mode `bedrock`, et l'application est sur `main` avant dimanche 23 h 59.

### Sprint 3 : dimanche soir et lundi matin (aucun code)

Après le gel, seulement des corrections de bogues dans des branches `fix/...`, et jamais après dimanche 23 h 59.

- [ ] D9a. Script de démo et liste de contrôle manuelle dans `docs/demo_script.md` (dimanche 19 h 30)
- [ ] D9b. Script final, `docs/video_plan.md`, enregistrement dimanche soir, montage, captures dans `outputs/figures/`. Vidéo déposée lundi avant 14 h

## 6. Vérification

- Pas de tests d'interface versionnés (décision du plan). Avant chaque PR : lancement réel, puis la liste de contrôle de `docs/demo_script.md`.
- Contrôle rapide hors navigateur avec `streamlit.testing.v1.AppTest` (non versionné) : chaque page s'exécute sans exception pour chaque persona, avec une demande permise, une demande refusée, une demande ambiguë et un réglage manuel. Limite connue : après un `st.switch_page` dans le script, AppTest réexécute la page d'origine ; un navigateur reste sur la nouvelle page.
- Recherche dans le diff : aucun tiret cadratin, aucun emoji, aucun secret.

## 7. Questions ouvertes

1. Onglets ou page unique pour la vidéo ? Réglé : navigation multipage, conversation sur la page Simulation.
2. Avertissement du bandeau : texte court du flux D. Les avertissements complets du flux B (`fixed_texts.json`) apparaissent en tête de chaque explication.
3. Mode `bedrock` : vérifié seulement sans configuration (repli affiché). L'essai avec de vrais identifiants reste à faire sur le poste de démo.

## 8. Règles d'affichage ajoutées après la revue

- Le numéro de preuve (E1, E2...) n'est montré que pour le registre du résultat. La radiographie et les faits d'actif ont chacun leur registre, donc leurs preuves affichent la clé (`<métrique>:<sujet>`).
- Les signes `$` du texte d'explication sont échappés : sans cela Streamlit lit deux montants comme une formule.
- Étape 6 de la trace : une intervention du garde-fou, un ancrage sous le seuil ou un remplacement par le gabarit s'affichent "intervention", jamais "réussi".

## 9. Allègement après l'audit UI/UX du 15 novembre

- Réponse courte : carte de verdict (pastille, phrase, statut avant l'idée, pastilles Financier / ESG), puis trois points clés avec le chiffre en grand et, pour une règle en cause, le contrefactuel. Plus de puces en double dans la carte.
- "Idée simulée" n'est rappelée que pour une demande écrite ; une idée identique à celle déjà simulée n'est pas renvoyée (bouton, préréglage ou "Simuler").
- Tableau avant/après : libellés neutres, sans le suffixe de périmètre (il reste dans les preuves).
- Marge nulle d'une règle conforme : "À la limite de la tension, sans la franchir."
- Garde-fou : quatre exemples visibles par colonne, les autres dans un encadré repliable.
- Accueil : sans choix explicite, aucun niveau n'est mis en avant ; le profil choisi fixe alors le sien.
