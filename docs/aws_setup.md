# Mise en place AWS (flux C, tâches C1 et C2)

Ce document décrit comment vérifier l'accès au compte de l'atelier, choisir un modèle Bedrock et créer le garde-fou d'AlphaForge. Il ne contient aucun identifiant de compte, aucun ARN complet et aucun secret. Le compte Workshop Studio est temporaire : tout ce qui compte (code, configuration, prompts, traces utiles) vit dans le dépôt, jamais seulement sur AWS.

AlphaForge reste une simulation éducative : aucune transaction, aucune connexion à un courtier, aucun conseil personnalisé. Aucun agent ne reçoit d'outil de passage d'ordres.

## 1. Variables d'environnement

Noms seulement (voir `.env.example`). Les valeurs vivent dans le terminal dédié ou dans un `.env` ignoré par Git, jamais dans le dépôt.

| Variable | Rôle | Fournie par |
| --- | --- | --- |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Identifiants temporaires (les trois ensemble) | Page Workshop Studio, chacun les siens |
| `AWS_REGION` | Toujours `us-east-1` | Terminal dédié |
| `ALPHAFORGE_MODE` | `bedrock` ou `offline` | Équipe |
| `ALPHAFORGE_ANALYST_MODEL_ID` | Modèle ou profil d'inférence de l'agent analyste | Choisi après `check_aws_access.py` |
| `ALPHAFORGE_EXPLAINER_MODEL_ID` | Modèle de l'agent explicateur (même modèle au départ) | Idem |
| `ALPHAFORGE_GUARDRAIL_ID`, `ALPHAFORGE_GUARDRAIL_VERSION` | Garde-fou à appliquer | Sortie de `setup_guardrail.py --apply` |
| `ALPHAFORGE_TRACE_BUCKET` | Compartiment S3 privé des traces | Créé plus tard (tâche C7) |

Aucun identifiant de modèle ni de garde-fou n'est codé en dur : le code lit ces variables.

## 2. Vérifier le compte avant toute opération

Dans le terminal dédié, après avoir collé les trois valeurs temporaires et `AWS_REGION=us-east-1` :

```bash
aws sts get-caller-identity
aws configure list
```

Vérifier que le compte est bien celui de l'atelier (sans le recopier nulle part) et que la région est `us-east-1`. Ne pas utiliser `aws login` pour ce compte, et ne jamais créer de clé IAM permanente. En cas de `ExpiredToken`, `ExpiredTokenException` ou `InvalidClientTokenId`, récupérer un nouvel ensemble des trois valeurs.

## 3. Ordre d'exécution des scripts

Tous les scripts se lancent depuis la racine du projet, dans le même terminal que la CLI.

1. **Vérification en lecture seule (C1)** : `python scripts/check_aws_access.py`
   - affiche si le compte répond et si la région est conforme, avec numéro de compte et ARN masqués ;
   - liste les modèles `ACTIVE` texte vers texte et les profils d'inférence (préfixes `us.`, `global.`) ;
   - ne crée ni ne modifie rien. Codes de sortie : 0 succès, 1 erreur AWS ou d'identifiants, 2 configuration.
2. **Essai Converse avec outil (C1)** : `python scripts/check_aws_access.py --skip-listing --try-converse <identifiant>` (ou sans valeur pour lire `ALPHAFORGE_ANALYST_MODEL_ID`).
   - un seul appel, avec un outil factice `get_fictional_metric` ; le script affiche le nom de l'outil demandé par le modèle ;
   - `--tool-choice any` vérifie la prise en charge du choix d'outil forcé.
   - Reporter ensuite l'identifiant retenu dans `ALPHAFORGE_ANALYST_MODEL_ID` et `ALPHAFORGE_EXPLAINER_MODEL_ID`.
3. **Garde-fou, simulation (C2)** : `python scripts/setup_guardrail.py` affiche la configuration, sans aucun appel AWS.
4. **Garde-fou, création ou mise à jour (C2)** : `python scripts/setup_guardrail.py --apply`
   - seule commande du dépôt qui modifie le compte ; à lancer par la personne responsable du flux C uniquement ;
   - idempotente : si `alphaforge-guardrail` existe, il est mis à jour au lieu d'être recréé ; une nouvelle version numérotée est publiée à chaque fois ;
   - copier les deux lignes affichées (`ALPHAFORGE_GUARDRAIL_ID=...`, `ALPHAFORGE_GUARDRAIL_VERSION=...`) dans son environnement local.
5. **Garde-fou, essai des requêtes (C2)** : `python scripts/setup_guardrail.py --test`
   - envoie chaque requête de `tests/fixtures/guardrail_prompts.json` à `ApplyGuardrail` (source `INPUT`) et affiche un tableau attendu/obtenu ;
   - code de sortie 3 si une requête n'a pas le résultat attendu. Consomme du quota partagé : ne pas boucler.

Options du garde-fou : `--grounding-threshold` et `--relevance-threshold` (défaut 0,5, borne 0,99), `--grounding-action NONE|BLOCK` (défaut `NONE`, mode détection).

Les tests automatisés (`pytest tests`) n'appellent jamais AWS : ils utilisent des clients simulés.

## 4. Configuration du garde-fou

| Volet | Réglage | Raison |
| --- | --- | --- |
| Sujet refusé `personalized_advice` | Blocage en entrée et en sortie | Règle 8 : pas de conseil personnalisé |
| Sujet refusé `order_execution` | Blocage en entrée et en sortie | Règle 8 : aucun ordre, aucun courtier |
| Sujet refusé `return_prediction` | Blocage en entrée et en sortie | Contrainte du cas : pas de prédiction de rendement |
| Ancrage `GROUNDING` et `RELEVANCE` | Mode détection (`action = NONE`), seuils réglables | Scores affichés à l'étape 6 de la trace, calibrage avant blocage |
| Messages de blocage | En français | Règle 4 |

Les sujets sont volontairement étroits : chaque définition précise que l'analyse historique d'une idée de placement fictive n'est pas visée. Le cas de démo ("Que se passe-t-il pour Robert si on ajoute 25 % de TSLA ?") doit passer.

Le volet d'ancrage s'évalue avec `ApplyGuardrail` sur le texte rendu de l'explication : source = dossier d'explication, requête = question fixe, contenu = texte. Le garde-fou complète les contrôles du code (validateur, gouvernance) ; il ne prouve pas l'exactitude factuelle. Ses interventions et scores sont convertis en `GuardrailResult` (`summarize_assessment` dans `scripts/setup_guardrail.py`, à reprendre dans `bedrock_client.py` à la tâche C4).

## 5. Inventaire des ressources prévues

Préfixe `alphaforge-`. Seule la personne du flux C crée ou modifie des ressources dans le compte partagé.

| Ressource | Nom | Rôle | Création | État |
| --- | --- | --- | --- | --- |
| Garde-fou Bedrock | `alphaforge-guardrail` | Sujets refusés et ancrage contextuel | `scripts/setup_guardrail.py --apply` | Script prêt, non exécuté |
| Compartiment S3 privé | `alphaforge-traces-<suffixe>` (préfixe `alphaforge-`) | Une trace JSON sans secret par analyse | À écrire (tâche C7), quatre options Block Public Access activées | À faire |
| Rôle d'exécution | Rôle de l'atelier pour le développement local ; rôle dédié seulement si hébergement | Inférence Bedrock, `ApplyGuardrail`, écriture S3 sur le seul compartiment des traces | À décider avec l'équipe | À faire |

Permissions minimales visées pour un éventuel rôle d'application (moindre privilège, pas de `AmazonBedrockFullAccess`) : `bedrock:InvokeModel` (utilisé par Converse) sur les modèles et profils choisis, `bedrock:ApplyGuardrail` sur `alphaforge-guardrail`, `s3:PutObject` et `s3:GetObject` sur le préfixe des traces. Les actions de création de garde-fou (`bedrock:CreateGuardrail`, `UpdateGuardrail`, `CreateGuardrailVersion`, `ListGuardrails`, `GetGuardrail`) restent réservées au rôle de console du flux C.

## 6. Services AWS utilisés et pourquoi

| Service | Usage | Justification |
| --- | --- | --- |
| AWS STS | `get-caller-identity` | Vérifier le compte et les identifiants temporaires avant toute opération |
| Amazon Bedrock (contrôle) | Liste des modèles et profils, gestion du garde-fou | Choisir un modèle `ACTIVE` vérifié dans le compte, créer le garde-fou par script reproductible |
| Amazon Bedrock Runtime, API Converse | Agents analyste et explicateur | API unifiée avec appels d'outils, identifiant de modèle configurable |
| Amazon Bedrock Guardrails | Sujets refusés, ancrage contextuel | Faire respecter la règle 8 et mesurer la fidélité de l'explication au dossier |
| Amazon S3 (plus tard) | Traces d'exécution privées | Preuve consultable de l'intégration réelle (US-16) |

## 7. Points à vérifier dans le compte

- Modèles en cycle de vie `ACTIVE` et profils d'inférence disponibles (`us.`, `global.`) : l'API ne dit pas si un modèle accepte Converse ou les outils, d'où l'essai `--try-converse`.
- Prise en charge du choix d'outil forcé (`--tool-choice any`) par le modèle retenu.
- Niveau d'ancrage : Classic (par défaut, français pris en charge, ancrage strict) ou Standard (meilleure tolérance à la reformulation, mais exige l'inférence interrégionale du garde-fou ; disponibilité non vérifiée). Le script utilise le niveau par défaut.
- Comportement en français : faux refus sur les requêtes permises (`A01` à `A10`) et refus manqués (`D01` à `D09`) au test `--test`. Ajuster les définitions et exemples, puis relancer `--apply` (nouvelle version).
- Limites d'`ApplyGuardrail` pour l'ancrage : 100 000 caractères pour la source, 1 000 pour la requête, 5 000 pour le texte.

## 8. Clés API Bedrock à courte durée (option à confirmer)

Bedrock propose des clés API à courte durée. Ce n'est pas la méthode prévue : les identifiants temporaires de Workshop Studio suffisent. Si l'équipe envisage cette option, la confirmer d'abord avec un mentor. Une telle clé est un secret au même titre que les identifiants AWS : terminal dédié ou `.env` ignoré seulement, jamais dans le dépôt, un prompt, une capture ou la vidéo.

## 9. Ce qui ne doit jamais entrer dans le dépôt

- Identifiants AWS (clé d'accès, clé secrète, jeton de session), clés API, contenu de `.env`.
- Numéro de compte, ARN complets (ils contiennent le numéro de compte), URL Kiro contenant un jeton.
- Captures ou journaux non masqués. Les scripts masquent déjà le compte et les ARN dans leurs sorties.

Avant chaque commit, relire le diff indexé pour y chercher ces motifs. Si un secret a été exposé, cesser de l'utiliser et prévenir un mentor ou un organisateur ; le supprimer dans un commit ultérieur ne suffit pas.
