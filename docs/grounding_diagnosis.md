# Diagnostic de l'ancrage de l'agent explicateur

Statut : diagnostic hors ligne fait le 14 novembre 2026, mesuré sur le compte AWS de l'atelier le 15 novembre 2026 vers 3 h UTC (section "Mesure sur le compte"). Branche : `fix/explainer-grounding`.

## En bref

1. **La cause du score bas est confirmée : c'est la source JSON.** Avec le même contenu écrit en phrases, le texte réel de l'explicateur passe de 0,15 à 0,42 à une plage de 0,73 à 0,92 (seuil du garde-fou : 0,5). Sur la scène 2 simulée avec la configuration réelle, le texte novice d'Amira passe de 0,27, qui le ferait remplacer par le gabarit, à 0,82.
2. **Mais le contrôle d'ancrage ne repère pas un verdict faux.** Un texte qui déclare toutes les règles conformes obtient presque le même score que le texte juste, avec les deux sources. Le score mesure surtout la proximité de vocabulaire et de sujet, pas la justesse des statuts.
3. **Conséquence :** passer à la source en phrases évite de remplacer à tort le texte du modèle par le gabarit, mais le score ne doit pas être présenté comme une preuve d'exactitude ni servir à bloquer. La fidélité reste garantie par le code : renvois, validateur, statuts calculés par la gouvernance.

## Constat

- Le contrôle d'ancrage de Bedrock Guardrails donne des scores autour de 0,4 pour le texte de l'explicateur (de 0,16 à 0,47 avant le remplacement des renvois, voir `docs/aws_setup.md`). Le seuil du garde-fou est 0,5 et le plancher du pipeline 0,3 : le texte est souvent signalé `grounding_weak`, parfois remplacé par le gabarit.
- La langue seule n'explique pas ces scores : la documentation AWS classe le français "optimisé et pris en charge" pour l'ancrage contextuel, au niveau Classic comme au niveau Standard ([langues prises en charge](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-supported-languages.html)).

## Cause principale : la forme de la source

L'étape 6 du pipeline (`analysis_pipeline.explain`) envoie comme source `json.dumps(brief)` : le dossier d'explication en JSON. Les faits y sont, mais sous une forme qu'un modèle d'implication textuelle relie mal à des phrases françaises :

- **Statuts en codes anglais.** Le texte dit "en conflit", "conforme" ; la source ne contient que `conflict`, `compliant`. Le verdict, qui est l'affirmation principale du texte, n'est jamais écrit dans la source.
- **Seuils en clés anglaises et nombres bruts.** Le texte dit "dépasse le seuil d'attention du profil" ; la source dit `"warn_threshold": 0.2` et `"value": 0.17596769539961174`.
- **Bruit.** Environ 14 000 à 18 000 caractères, dont la moitié de structure JSON (clés, identifiants, codes de métrique).

Mesure hors ligne, sans réseau. Le texte contrôlé est celui du **gabarit du code**, fidèle au dossier par construction : s'il est mal relié à la source, la cause est la source, pas le modèle. Indicateur : part des mots de 5 lettres ou plus du texte que l'on retrouve tels quels dans la source (indicateur grossier, pas le score du garde-fou).

| Cas (idée : 25 % de TSLA) | Source JSON | Source en phrases | Statuts absents de la source JSON |
| --- | --- | --- | --- |
| Robert, novice | 26/54 mots, 14 381 car. | 44/54 mots, 7 825 car. | conflit, conforme |
| Robert, pro | 26/59 | 39/59 | conflit, conforme |
| Amira, novice | 22/43 | 35/43 | conforme |
| Amira, pro | 22/51 | 32/51 | conforme |
| Mateo, novice | 24/46 | 33/46 | conflit, tension |
| Mateo, pro | 23/51 | 29/51 | conflit, tension, conforme |

La source en phrases (`src/alphaforge/grounding_source.py`) réécrit le même dossier en français, de façon déterministe, sans fait ajouté : idée, verdict d'ensemble, pour chaque règle son statut, sa mesure, ses seuils, sa marge et son contrefactuel, puis les variantes, les preuves (valeur, période, devise, calcul), les limites et le glossaire. Elle fait à peu près deux fois moins de caractères, et tous les statuts cités par le texte s'y retrouvent.

## Causes secondaires

- **Phrases de liaison et de méthode.** Le gabarit et le modèle écrivent des phrases vraies mais absentes du dossier : "Points à regarder", "Respecter une règle n'implique pas de respecter les autres", "Les limites ci-dessous s'appliquent à tous les chiffres". Le niveau Classic de l'ancrage pénalise toute information absente de la source.
- **Paraphrases du glossaire.** "amplitude des variations" pour une définition qui dit "ampleur des variations".
- **Négations.** "Aucune règle n'est en tension ni en conflit" cite des statuts absents du dossier.

## Mesure sur le compte

Conditions : compte de l'atelier (rôle `WSParticipantRole`), `us-east-1`, garde-fou `alphaforge-guardrail` version 5 (ancrage et pertinence au seuil 0,5, mode détection), requête fixe du pipeline. Idée : 25 % de TSLA au prorata. Le témoin est le même texte avec toutes les règles déclarées conformes. Coût total : 40 appels `ApplyGuardrail` et 6 appels Converse.

**Texte du gabarit (fidèle par construction)**

| Cas | JSON, texte juste | JSON, témoin faux | Phrases, texte juste | Phrases, témoin faux |
| --- | --- | --- | --- | --- |
| Robert, novice | 0,52 | 0,63 | 0,85 | 0,82 |
| Robert, pro | 0,61 | 0,47 | 0,63 | 0,28 |
| Amira, novice | 0,46 | 0,47 | 0,79 | 0,79 |
| Amira, pro | 0,54 | 0,54 | 0,46 | 0,47 |
| Mateo, novice | 0,56 | 0,61 | 0,92 | 0,92 |
| Mateo, pro | 0,58 | 0,58 | 0,88 | 0,88 |
| Moyenne | 0,55 | | 0,76 | |

Chez Mateo, le témoin change peu le sens (ses statuts sont "conforme" et "information manquante", les mots remplacés sont dans une négation) : ses lignes ne testent pas le témoin.

**Texte réel d'un explicateur** (modèle `us.anthropic.claude-haiku-5-5`, choisi avant de connaître la configuration réelle ; prompt `explainer_v4`, sorties acceptées par le validateur)

| Cas | JSON, texte juste | JSON, témoin faux | Phrases, texte juste | Phrases, témoin faux |
| --- | --- | --- | --- | --- |
| Robert, novice | 0,42 | 0,52 | 0,83 | 0,80 |
| Robert, pro | 0,15 | 0,18 | 0,73 | 0,74 |

**Simulation de la scène 2 avec la configuration réelle** (Amira, 25 % de TSLA ; explicateur `us.anthropic.claude-sonnet-5-5`, celui des traces de `outputs/reports/demo_traces/`, prompt `explainer_v4`, plafond de 2 500 jetons ; réponses complètes en environ 1 100 jetons, acceptées par le validateur)

| Niveau | Source JSON (pipeline actuel) | Source en phrases | Témoin faux, JSON | Témoin faux, phrases |
| --- | --- | --- | --- | --- |
| Novice | 0,27 | 0,82 | 0,27 | 0,82 |
| Pro | 0,33 | 0,92 | 0,33 | 0,91 |

Avec le pipeline actuel, le texte novice (0,27, sous le plancher de 0,3) serait remplacé par le gabarit, et le texte pro (0,33) affiché avec la mention d'ancrage faible. Les traces réelles d'Amira enregistrées par l'équipe donnent 0,42 et 0,40 : le score varie d'un texte à l'autre, mais reste sous le seuil avec la source JSON. Avec la source en phrases, les deux textes dépassent nettement le seuil. Le témoin faux obtient exactement les mêmes scores.

Lecture :

- Avec la source JSON, le texte du modèle reste sous le seuil, et à 0,15 il passe sous le plancher de 0,3 du pipeline : le texte serait remplacé par le gabarit alors qu'il est fidèle. Ces valeurs concordent avec celles déjà relevées par le flux C (0,16 à 0,47).
- Avec la source en phrases, le gabarit gagne en moyenne 0,2 point de score, et le texte du modèle dépasse le seuil dans les deux cas.
- Le témoin faux n'est nettement pénalisé que dans un cas sur six utiles (Robert, pro, gabarit, source en phrases : 0,28 contre 0,63). Avec la source JSON, il obtient même parfois un score plus haut que le texte juste.

**Autre constat, seulement avec Haiku : réponses tronquées.** Les traces de l'équipe montrent que l'explicateur configuré est `us.anthropic.claude-sonnet-5-5` (Haiku sert à l'analyste). Avec Haiku comme explicateur, la réponse contient un bloc de raisonnement d'environ 5 500 caractères avant le JSON : au plafond de 2 500 jetons, les deux premiers appels se sont arrêtés sur `max_tokens`, JSON incomplet ; à 8 000 jetons, ils ont abouti avec environ 2 100 jetons. Avec Sonnet, la réponse tient en environ 1 100 jetons : pas de troncature.

Pour refaire la mesure avec des identifiants locaux, dans le terminal dédié, après `aws sts get-caller-identity` :

```bash
python scripts/diagnose_grounding.py --apply                                  # au plus 24 appels ApplyGuardrail
python scripts/diagnose_grounding.py --apply --explainer --personas robert    # vrai texte du modèle, 2 cas
```

Le script mesure chaque texte contre les deux sources, plus le témoin négatif. Avec `--explainer`, il utilise le plafond de jetons du pipeline et peut donc rencontrer la troncature décrite ci-dessus.

## Correctifs proposés (flux C, à valider par Godwin)

1. **Source du contrôle.** À l'étape 6 de `explain`, remplacer `json.dumps(brief, ensure_ascii=False)` par `build_grounding_source(brief)`. L'explicateur continue de recevoir le dossier JSON ; seule la source du contrôle change, et elle ne contient que le contenu du dossier.
2. **Rôle du score.** Garder le mode détection. Le plancher de 0,3 peut rester comme filet contre un texte hors sujet, mais le score ne doit ni bloquer ni être présenté comme une vérification des statuts : le témoin montre qu'il ne la fait pas.
3. **Plafond de jetons de l'explicateur.** Inutile avec Sonnet. À relever (par exemple 4 000) seulement si l'explicateur passe à Haiku.

## Limites de ce diagnostic

- Petit échantillon : six cas pour le gabarit, deux pour le modèle, un seul essai chacun. Le classifieur du garde-fou n'est pas parfaitement stable d'un essai à l'autre (voir `docs/technical_documentation.md`).
- L'indicateur lexical hors ligne n'est qu'un indice ; seuls les scores du compte comptent.
- Le témoin ne teste que l'inversion des statuts, pas un chiffre attribué à la mauvaise règle.
