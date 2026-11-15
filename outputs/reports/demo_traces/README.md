# Traces de démonstration du mode Bedrock

Six traces réelles, produites le 15 novembre 2026 par `scripts/try_bedrock_run.py --run --save-local` sur le compte de l'atelier. Elles montrent la chaîne complète en mode `bedrock` pour l'idée fictive "porter TSLA à 25 % du portefeuille, financement au prorata", avec Robert et Amira.

Tout est fictif : profils, portefeuilles, capitaux. Aucune recommandation. Ce sont des simulations éducatives.

## Contenu

| Fichier | Ce qu'il contient |
| --- | --- |
| `robert_analysis.json`, `amira_analysis.json` | Analyse : outils appelés par l'agent, gouvernance, registre de preuves, variantes, trace des étapes 1 à 3 |
| `robert_explanation_novice.json`, `robert_explanation_pro.json` | Explication de Robert aux deux niveaux : texte du modèle, validation, contrôle du garde-fou, trace des étapes 4 à 6 |
| `amira_explanation_novice.json`, `amira_explanation_pro.json` | Idem pour Amira |

## Ce que ces essais ont mesuré

| Explication | Texte affiché | Ancrage | Pertinence | Tentatives |
| --- | --- | --- | --- | --- |
| Robert, novice | modèle | 0,34 | 1,0 | 1 |
| Robert, pro | modèle | 0,43 | 1,0 | 1 |
| Amira, novice | modèle | 0,42 | 1,0 | 1 |
| Amira, pro | modèle | 0,40 | 1,0 | 1 |

Les quatre textes viennent du modèle, ont passé le validateur au premier essai et n'ont eu besoin d'aucune réparation. Le score d'ancrage mesure si chaque affirmation du texte se retrouve dans le dossier de preuves. Il se situe autour de 0,4, sous le seuil de 0,5 : il est signalé dans la trace (`grounding_weak`) et n'écarte pas le texte, comme le prévoit le plan de sprint. Un texte sous 0,3 serait remplacé par le gabarit.

## Configuration utilisée

- Agent analyste : `us.anthropic.claude-haiku-5-5`.
- Agent explicateur : `us.anthropic.claude-sonnet-5-5`, prompt `explainer_v4`.
- Garde-fou Bedrock : version 4, sujets refusés au niveau Standard, ancrage contextuel en détection.
- Les traces ont aussi été écrites dans un compartiment S3 privé.

## Comment lire une trace

Chaque explication a trois étapes : 4 (explication, acteur "agent"), 5 (validation par le code) et 6 (garde-fou). Dans `trace`, le champ `details` indique ce qui s'est passé : tentative, réparations éventuelles (`repaired_slots`), score d'ancrage, nombre de caractères contrôlés. La section `analysis.evidence` du fichier d'analyse est le registre complet de preuves, avec leur source, leur période et leur devise.

## Reproduire

Avec un terminal qui a les identifiants et les variables du projet (voir `docs/aws_setup.md`) :

```
.venv/bin/python scripts/try_bedrock_run.py --run --save-local
```

Les traces locales vont dans `outputs/reports/traces/`, ignoré par Git. Rien d'autre que ces six fichiers n'est versionné.
