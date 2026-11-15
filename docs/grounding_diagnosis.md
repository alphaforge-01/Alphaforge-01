# Diagnostic de l'ancrage de l'agent explicateur

Statut : diagnostic du 14 au 15 novembre 2026, mesuré sur le compte AWS de l'atelier. Le correctif 1 (source en phrases) est branché dans le pipeline depuis la branche `fix/explainer-grounding-wording` ; il reste à remesurer sur le compte, car ce branchement a été fait sans identifiants AWS.

## En bref

1. **La cause du score bas est la source JSON.** Avec le même dossier écrit en phrases françaises, le texte réel de l'explicateur passe d'une plage de 0,15 à 0,42 à une plage de 0,70 à 0,91 (seuil du garde-fou : 0,5). Sur la scène 2 (Amira, 25 % de TSLA), le texte novice passe de 0,27, qui le ferait remplacer par le gabarit, à 0,82.
2. **Le contrôle d'ancrage ne repère presque jamais un verdict faux.** Un texte où les règles en conflit ou en tension sont déclarées conformes obtient presque le même score que le texte juste, avec les deux sources. Le score mesure surtout la proximité de vocabulaire et de sujet, pas la justesse des statuts.
3. **Conséquence :** passer à la source en phrases évite de remplacer à tort le texte du modèle par le gabarit, mais le score ne doit ni bloquer ni être présenté comme une preuve d'exactitude. La fidélité reste garantie par le code : renvois, validateur, statuts calculés par la gouvernance.

## Constat de départ

- Les scores relevés par le flux C sur le texte du modèle vont de 0,16 à 0,47 (docstring de `_model_text` dans `analysis_pipeline.py`). Les traces de démonstration (`outputs/reports/demo_traces/`) donnent 0,42 et 0,40 pour Amira. Le seuil du garde-fou est 0,5 et le plancher du pipeline 0,3 : le texte est signalé `grounding_weak`, et remplacé par le gabarit sous 0,3.
- La langue n'explique pas ces scores : la documentation AWS classe le français "optimisé et pris en charge" pour l'ancrage contextuel, au niveau Classic comme au niveau Standard ([langues prises en charge](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-supported-languages.html)).

## Cause principale : la forme de la source

L'étape 6 du pipeline (`analysis_pipeline.explain`) envoie comme source `json.dumps(brief)`, le dossier d'explication en JSON. Les faits y sont, mais sous une forme qu'un modèle d'implication textuelle relie mal à des phrases françaises :

- **Statuts en codes anglais.** Le texte dit "en conflit", "conforme" ; la source ne contient que `conflict`, `compliant`. Le verdict, affirmation principale du texte, n'est jamais écrit dans la source.
- **Seuils en clés anglaises et nombres bruts.** Le texte dit "dépasse le seuil d'attention du profil" ; la source dit `"warn_threshold": 0.2` et `"value": 0.17596769539961174`.
- **Bruit.** De 14 000 à 18 000 caractères, dont la moitié de structure JSON (clés, identifiants, codes de métrique).

Indice hors ligne, sans réseau, sur le texte du **gabarit du code**, fidèle au dossier par construction : part des mots de 5 lettres ou plus du texte retrouvés tels quels dans la source (indicateur grossier, pas le score du garde-fou).

| Cas (25 % de TSLA) | Source JSON | Source en phrases | Statuts absents de la source JSON |
| --- | --- | --- | --- |
| Robert, novice | 26/54 mots, 14 381 car. | 41/54 mots, 8 339 car. | conflit, conforme |
| Robert, pro | 26/59 | 39/59 | conflit, conforme |
| Amira, novice | 22/43 | 32/43 | conforme |
| Amira, pro | 22/51 | 32/51 | conforme |
| Mateo, novice | 24/46 | 32/46 | conflit, tension |
| Mateo, pro | 23/51 | 30/51 | conflit, tension, conforme |

La source en phrases (`src/alphaforge/grounding_source.py`) réécrit le même dossier en français, de façon déterministe : avertissements fixes du flux B, idée, verdict d'ensemble, puis pour chaque règle son statut, sa mesure, ses seuils, le sens du statut, sa marge et son contrefactuel, puis les variantes (mesures avec leur libellé), les preuves (valeur, période, devise, calcul), les limites et le glossaire. Elle suit les conventions de la gouvernance : une valeur égale à un seuil ne le franchit pas, la marge est la distance au seuil suivant, et seuls les seuils présents sont cités. Elle fait à peu près 40 % de caractères de moins, et tous les statuts cités par le texte s'y retrouvent.

## Mesure sur le compte

Conditions : compte de l'atelier (rôle `WSParticipantRole`), `us-east-1`, garde-fou `alphaforge-guardrail` version 5 (ancrage et pertinence au seuil 0,5, mode détection), requête fixe du pipeline, idée "25 % de TSLA au prorata". Le témoin est le texte juste où les règles en conflit ou en tension sont déclarées conformes (fonction `falsify` du script). Le poste de développement n'avait pas d'identifiants AWS : les appels ont été faits par le serveur AWS de Kiro, avec exactement les textes et les sources que produit le script. Coût total du diagnostic : 80 appels `ApplyGuardrail` et 6 appels Converse.

Score d'ancrage :

| Texte | JSON, juste | JSON, témoin | Phrases, juste | Phrases, témoin |
| --- | --- | --- | --- | --- |
| Gabarit, Robert novice | 0,52 | 0,65 | 0,79 | 0,79 |
| Gabarit, Robert pro | 0,61 | 0,49 | 0,70 | 0,34 |
| Gabarit, Amira novice | 0,46 | 0,47 | 0,88 | 0,89 |
| Gabarit, Amira pro | 0,54 | 0,54 | 0,49 | 0,40 |
| Gabarit, Mateo novice | 0,58 | 0,63 | 0,89 | 0,88 |
| Gabarit, Mateo pro | 0,61 | 0,58 | 0,89 | 0,89 |
| Explicateur Sonnet, Amira novice | 0,27 | 0,27 | 0,82 | 0,84 |
| Explicateur Sonnet, Amira pro | 0,33 | 0,33 | 0,91 | 0,91 |
| Explicateur Haiku, Robert novice | 0,42 | 0,52 | 0,84 | 0,80 |
| Explicateur Haiku, Robert pro | 0,15 | 0,18 | 0,70 | 0,73 |

- Explicateur Sonnet : `us.anthropic.claude-sonnet-5-5`, le modèle des traces de démonstration, donc la configuration réelle. Explicateur Haiku : `us.anthropic.claude-haiku-5-5`, mesuré avant de connaître cette configuration. Prompt `explainer_v4`, sorties acceptées par le validateur.
- Pour Mateo, le témoin ne change que des statuts cités dans une négation ("aucune règle n'est en tension") : ses lignes testent peu le témoin.

Lecture :

- **Texte du modèle.** Avec la source JSON, il reste sous le seuil dans les quatre cas, et deux fois sous le plancher de 0,3 (0,27 et 0,15) : le pipeline le remplacerait par le gabarit alors qu'il est fidèle. Avec la source en phrases, il dépasse le seuil dans les quatre cas (0,70 à 0,91).
- **Gabarit.** La moyenne passe de 0,55 à 0,77. Un cas régresse : Amira pro, de 0,54 à 0,49, juste sous le seuil et au-dessus du plancher. Le gabarit pro emploie des termes de méthode absents du dossier (par exemple "balayage"), ce qui peut expliquer ce cas.
- **Témoin.** Sur vingt paires, le témoin ne perd plus de 0,1 point que deux fois : gabarit de Robert pro, avec la source en phrases (0,70 puis 0,34) et avec la source JSON (0,61 puis 0,49). Ailleurs, il obtient presque le même score, parfois plus haut.

**Autre constat, seulement avec Haiku comme explicateur : réponses tronquées.** La réponse de Haiku contient un bloc de raisonnement d'environ 5 500 caractères avant le JSON. Au plafond de 2 500 jetons (`INFERENCE_CONFIG` de `explainer_agent.py`), les deux premiers appels se sont arrêtés sur `max_tokens`, JSON incomplet ; à 8 000 jetons, ils ont abouti avec environ 2 100 jetons. Avec Sonnet, la réponse tient en environ 1 100 jetons : pas de troncature.

## Refaire la mesure

Dans le terminal qui contient les identifiants temporaires, après `aws sts get-caller-identity` :

```bash
python scripts/diagnose_grounding.py                                         # hors ligne, aucun appel
python scripts/diagnose_grounding.py --apply                                  # au plus 24 appels ApplyGuardrail
python scripts/diagnose_grounding.py --apply --explainer --personas amira     # vrai texte du modèle configuré
```

Le script mesure chaque texte (gabarit, explicateur avec `--explainer`) et son témoin contre les deux sources. Avec `--explainer`, il utilise le modèle de `ALPHAFORGE_EXPLAINER_MODEL_ID` et le plafond de jetons du pipeline.

## Correctifs proposés (flux C, à valider par Godwin)

1. **Source du contrôle (fait).** `analysis_pipeline._grounding_source` envoie `build_grounding_source(brief)` et se rabat sur le JSON si la réécriture échoue ; la trace note `source_kind` et `source_chars`. Proposition d'origine : à l'étape 6 de `explain`, remplacer `json.dumps(brief, ensure_ascii=False)` par `build_grounding_source(brief)` (import depuis `.grounding_source`). L'explicateur continue de recevoir le dossier JSON ; seule la source du contrôle change, et elle ne contient que le contenu du dossier et les avertissements fixes.
2. **Rôle du score.** Garder le mode détection. Le plancher de 0,3 peut rester comme filet contre un texte hors sujet, mais le score ne doit ni bloquer ni être présenté comme une vérification des statuts : le témoin montre qu'il ne la fait pas.
3. **Requête du contrôle (fait en partie).** Elle est maintenant la constante `GROUNDING_QUERY` du pipeline, au texte inchangé pour que les mesures restent comparables. Constat d'origine : elle est écrite en dur dans `explain` ; le script en garde une copie, vérifiée par un test (`test_query_matches_pipeline_literal`). Une constante publique dans le pipeline supprimerait cette copie.
4. **Plafond de jetons.** Inutile avec Sonnet. À relever (par exemple 4 000) seulement si l'explicateur passe à Haiku.

## Limites de ce diagnostic

- Petit échantillon : dix textes, un seul essai chacun. Le classifieur du garde-fou n'est pas parfaitement stable d'un essai à l'autre (voir `docs/technical_documentation.md`).
- L'indicateur lexical hors ligne n'est qu'un indice ; seuls les scores du compte comptent.
- Le témoin ne teste que l'inversion des statuts, pas un chiffre attribué à la mauvaise règle.

## Autres défauts de l'explication corrigés avec ce branchement

Relevés en relisant les textes réels des traces de démonstration (`outputs/reports/demo_traces/`) et le texte de repli :

- **Règle nommée deux fois.** Le modèle écrit "la règle de concentration par actif [G1]" et le renvoi était remplacé par le libellé, d'où "la règle de concentration par actif **Concentration par actif**". Le rendu met maintenant en gras les mots déjà écrits ("la règle de **concentration par actif**", "la **volatilité annuelle**") au lieu de répéter le libellé. Un terme du glossaire placé en fin de proposition devient "(voir **Terme**)".
- **Variantes sans libellé.** Le texte de repli donnait "Mesures : 13,43 %, 19,91 %, 17 %, 53,95 % et 17 %". Chaque valeur est maintenant précédée de ce qu'elle mesure.
- **Tableau novice.** Il ne montrait que la limite : une mesure "en tension" sous la limite paraissait contradictoire. Il montre aussi le seuil d'attention.
- **Trace de l'interface.** Un ancrage sous le seuil du garde-fou mais au-dessus du plancher était décrit comme "le texte du modèle n'est pas montré", alors que le pipeline le garde. Le libellé dit maintenant "signalé, sans écarter le texte", et rappelle ce que le score mesure.

Non fait, à tester sur le compte avant de l'activer : dire au modèle, dans le prompt, par quoi chaque renvoi est remplacé, pour qu'il n'écrive plus le nom de la règle à côté de son renvoi.
