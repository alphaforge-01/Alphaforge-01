# Diagnostic de l'ancrage de l'agent explicateur

Statut : diagnostic hors ligne fait le 14 novembre 2026. Mesure sur le compte AWS à faire avec `scripts/diagnose_grounding.py --apply`. Branche : `fix/explainer-grounding`.

## Constat

- Le contrôle d'ancrage de Bedrock Guardrails donne des scores autour de 0,4 pour le texte de l'explicateur (de 0,16 à 0,47 avant le remplacement des renvois, voir `docs/aws_setup.md`). Le seuil du garde-fou est 0,5 et le plancher du pipeline 0,3 : le texte est souvent signalé `grounding_weak`, parfois remplacé par le gabarit.
- La langue seule n'explique pas ces scores : la documentation AWS classe le français "optimisé et pris en charge" pour l'ancrage contextuel, au niveau Classic comme au niveau Standard ([langues prises en charge](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-supported-languages.html)).

## Cause principale probable : la forme de la source

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

## Mesure à faire sur le compte

Dans le terminal qui contient les identifiants temporaires, après `aws sts get-caller-identity` :

```bash
python scripts/diagnose_grounding.py --apply                                  # au plus 24 appels ApplyGuardrail
python scripts/diagnose_grounding.py --apply --explainer --personas robert    # vrai texte du modèle, 2 cas
```

Le script mesure chaque texte contre les deux sources, plus un témoin négatif : le texte du gabarit où toutes les règles sont déclarées conformes.

Hypothèses à confirmer :

1. Le gabarit obtient un score nettement plus haut avec la source en phrases qu'avec la source JSON, et le texte de l'explicateur suit la même tendance.
2. Avec la source en phrases, le témoin négatif reste nettement sous le texte juste. Sinon, la source rend le contrôle indulgent et le correctif ne doit pas être appliqué.

## Correctif proposé (flux C, à valider par Godwin)

À l'étape 6 de `explain`, remplacer la source `json.dumps(brief, ensure_ascii=False)` par `build_grounding_source(brief)`. L'explicateur continue de recevoir le dossier JSON ; seule la source du contrôle change, et elle ne contient que le contenu du dossier. Recalibrer ensuite le seuil du garde-fou et le plancher de 0,3 sur les scores mesurés.

## Limites de ce diagnostic

- L'indicateur lexical ne remplace pas le score du garde-fou, qui juge le sens et non les mots.
- Le texte mesuré hors ligne est celui du gabarit ; le texte du modèle peut paraphraser davantage.
- Une source plus lisible peut aussi rendre le contrôle plus indulgent : c'est le rôle du témoin négatif. Il ne teste que l'inversion des statuts, pas un chiffre attribué à la mauvaise règle.
