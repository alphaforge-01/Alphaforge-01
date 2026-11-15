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
| `ALPHAFORGE_TRACE_BUCKET` | Compartiment S3 privé des traces | Nom affiché par `setup_trace_bucket.py --apply` ou `--check` |

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

6. **Compartiment des traces, simulation (C7)** : `python scripts/setup_trace_bucket.py` affiche le plan, sans créer aucun client AWS.
7. **Compartiment des traces, création ou correction (C7)** : `python scripts/setup_trace_bucket.py --apply`
   - nom `alphaforge-traces-<suffixe>` : le suffixe vient de `--suffix` ou, par défaut, des 8 premiers caractères hexadécimaux du SHA-256 du numéro de compte renvoyé par STS ; le numéro lui-même n'est jamais affiché ni stocké ;
   - crée le compartiment en `us-east-1` s'il n'existe pas, puis applique seulement les réglages qui manquent (voir section 5) ; ne supprime rien, ne remplace aucun énoncé de politique ni aucune étiquette existante ;
   - si le nom existe déjà dans un autre compte, le script s'arrête sans rien modifier (code 4) : choisir un autre `--suffix` ;
   - copier la ligne affichée `ALPHAFORGE_TRACE_BUCKET=...` dans le terminal dédié ou un `.env` ignoré par Git, jamais dans le dépôt.
8. **Compartiment des traces, vérification (C7)** : `python scripts/setup_trace_bucket.py --check`
   - lecture seule : affiche l'état de chaque réglage ; code 3 si le compartiment est absent ou si un réglage manque.
9. **Essai réel de bout en bout (C8)** : `python scripts/try_bedrock_run.py` (simulation par défaut), puis `python scripts/try_bedrock_run.py --run`
   - sans `--run`, n'appelle rien : affiche la configuration lue (identifiants de modèle, présence du garde-fou et du compartiment, jamais de secret) et vérifie que `ALPHAFORGE_ANALYST_MODEL_ID`, `ALPHAFORGE_EXPLAINER_MODEL_ID`, `ALPHAFORGE_GUARDRAIL_ID` et `ALPHAFORGE_GUARDRAIL_VERSION` sont définies (code 2 sinon) ;
   - avec `--run` : pour chaque persona de `--personas` (défaut `robert,amira`, au plus 3), analyse de l'idée fictive TSLA 25 % financée au prorata avec les vrais outils, puis explications `novice` et `pro`. Budget borné : au plus 3 x (1 analyse + 2 explications), le script refuse au-delà ;
   - résumé par persona : mode demandé et effectif, statut et acteur de chaque étape, raison de repli, outils appelés, validation, scores du garde-fou, trace S3 enregistrée ou non. Jamais le texte des prompts ni de secret ;
   - `--save-local` copie les traces dans `outputs/reports/traces/` (US-16, avant l'expiration du compte) ; `--check-requests` passe les requêtes de `tests/fixtures/guardrail_prompts.json` à `check_request` et affiche un tableau attendu/obtenu (code 3 en cas d'écart) ;
   - code 1 si une étape est en `error`, si l'analyse n'est pas en mode effectif `bedrock` ou si une explication a basculé hors Bedrock pour une autre raison qu'un contrôle du code (validateur, garde-fou). Consomme du quota partagé : ne pas boucler.

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

Le volet d'ancrage s'évalue avec `ApplyGuardrail` sur les seules phrases écrites par le modèle, avec les renvois remplacés par les valeurs que voit l'utilisateur : source = dossier d'explication, requête = question fixe, contenu = ces phrases (limite de 5000 caractères, que le texte rendu complet dépasse). Le score d'ancrage est affiché sans écarter le texte (mode détection du plan de sprint), avec un signal visible dans la section de l'explication et dans la trace : `grounding_weak` sous 0,5, et `grounding_very_weak` sous 0,3 (décision de l'équipe du 15 novembre : le texte de l'agent reste affiché, avec une mention plus forte). Le texte est remplacé par le gabarit seulement si le garde-fou intervient (sujet refusé), est indisponible ou ne renvoie aucun score. Ce choix repose sur le signal : un score très bas avait signalé, à un essai réel, une erreur de sens que le validateur ne voit pas. La source envoyée au garde-fou est le dossier réécrit en phrases françaises (`grounding_source.py`) : avec le dossier JSON, le texte réel de l'explicateur obtenait 0,15 à 0,47 ; avec les phrases, 0,70 à 0,91 (`docs/grounding_diagnosis.md`). Les scores des traces finales figurent dans `outputs/reports/demo_traces/`. Ce score mesure la proximité du texte avec la source, pas la justesse des statuts : un texte qui déclare conforme une règle en conflit obtient presque le même score. Les statuts restent garantis par le code (renvois, validateur, gouvernance). Le garde-fou complète les contrôles du code (validateur, gouvernance) ; il ne prouve pas l'exactitude factuelle. Limite assumée : seul le texte de l'explicateur passe par `ApplyGuardrail`. Les appels Converse de l'analyste n'ont pas de `guardrailConfig`, car sa sortie est structurée (idée, variantes, codes fermés) et sans prose destinée à l'utilisateur : le code la valide, et aucune phrase de l'analyste n'est affichée. Ses interventions et scores sont convertis en `GuardrailResult` dans `bedrock_client.py` et affichés à l'étape 6 de la trace.

## 5. Inventaire des ressources prévues

Préfixe `alphaforge-`. Seule la personne du flux C crée ou modifie des ressources dans le compte partagé.

| Ressource | Nom | Rôle | Création | État |
| --- | --- | --- | --- | --- |
| Garde-fou Bedrock | `alphaforge-guardrail` | Sujets refusés et ancrage contextuel | `scripts/setup_guardrail.py --apply` | Créé et testé ; versions publiées et mesurées en section 7, version retenue communiquée dans le canal de l'équipe |
| Compartiment S3 privé | `alphaforge-traces-<suffixe>` (préfixe `alphaforge-`, suffixe dérivé par SHA-256 du compte ou `--suffix`) | Une trace JSON sans secret par analyse et par explication en mode `bedrock` (US-16) | `scripts/setup_trace_bucket.py --apply`, vérification par `--check` | Créé, réglages vérifiés par `--check`, traces écrites lors des essais réels |
| Rôle d'exécution | Rôle de l'atelier pour le développement local ; rôle dédié seulement si hébergement | Inférence Bedrock, `ApplyGuardrail`, écriture S3 sur le seul compartiment des traces | Aucun rôle dédié : le prototype tourne en local avec le rôle de l'atelier | Politique de référence ci-dessous, non appliquée |

Réglages du compartiment des traces, appliqués par `setup_trace_bucket.py --apply` et contrôlés par `--check` :

| Réglage | Valeur | Raison |
| --- | --- | --- |
| Block Public Access | Les quatre options activées | Aucune exposition publique ; `trace_store.py` refuse d'écrire sinon |
| Chiffrement par défaut | SSE-S3 (`AES256`) ; un chiffrement KMS déjà en place est conservé | Données au repos chiffrées, sans clé KMS à gérer |
| Politique de compartiment | Un seul énoncé `Deny` sur `s3:*` si `aws:SecureTransport` vaut `false`, ajouté aux énoncés existants | Refuser tout accès hors TLS ; aucune autorisation publique ni croisée |
| Propriété des objets | `BucketOwnerEnforced` | ACL désactivées, le compte propriétaire possède tous les objets |
| Étiquette | `Project=alphaforge`, ajoutée aux étiquettes existantes | Repérer la ressource dans le compte partagé |

Toutes les lectures et écritures, celles du script comme celles de `trace_store.py`, passent `ExpectedBucketOwner` (compte des identifiants courants, lu par STS et jamais affiché), ce qui empêche d'agir sur un compartiment homonyme d'un autre compte. Le suffixe dérivé évite d'écrire le numéro de compte dans le nom ; ce n'est pas une protection forte (une recherche exhaustive réduirait le numéro à quelques centaines de candidats), et un numéro de compte n'est pas un identifiant d'authentification. Utiliser `--suffix` pour un nom sans lien avec le compte.

Permissions du rôle de console du flux C pour ce script : `sts:GetCallerIdentity`, `s3:CreateBucket`, `s3:ListBucket` (utilisé par `HeadBucket`), `s3:GetBucketPublicAccessBlock`, `s3:PutBucketPublicAccessBlock`, `s3:GetEncryptionConfiguration`, `s3:PutEncryptionConfiguration`, `s3:GetBucketPolicy`, `s3:PutBucketPolicy`, `s3:GetBucketOwnershipControls`, `s3:PutBucketOwnershipControls`, `s3:GetBucketTagging`, `s3:PutBucketTagging`, limitées à `arn:aws:s3:::alphaforge-traces-*`. Aucune action `Delete*` n'est nécessaire.

Permissions minimales d'un rôle d'application (moindre privilège, pas de `AmazonBedrockFullAccess`) : `bedrock:InvokeModel` (utilisé par Converse) sur les modèles et profils choisis, `bedrock:ApplyGuardrail` sur `alphaforge-guardrail`, `s3:PutObject` sur le préfixe des traces et `s3:GetBucketPublicAccessBlock` sur le compartiment (le code vérifie les quatre options Block Public Access avant toute écriture et refuse d'écrire sinon). `sts:GetCallerIdentity` ne demande aucune permission. Aucune lecture S3 n'est nécessaire au code. Les actions de création de garde-fou (`bedrock:CreateGuardrail`, `UpdateGuardrail`, `CreateGuardrailVersion`, `ListGuardrails`, `GetGuardrail`) restent réservées au rôle de console du flux C.

Texte de référence pour un hébergement futur. Il n'est appliqué à aucun rôle : le prototype tourne en local avec le rôle de l'atelier. `<compte>`, `<id-garde-fou>` et `<suffixe>` sont à remplacer hors du dépôt. Les profils d'inférence `us.` acheminent l'appel vers plusieurs régions américaines, d'où la région `*` sur les modèles de fondation et sur le profil interrégional du garde-fou (niveau Standard). À valider avec le simulateur de politiques IAM avant usage.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InferenceAgents",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": [
        "arn:aws:bedrock:us-east-1:<compte>:inference-profile/us.anthropic.claude-*",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
      ]
    },
    {
      "Sid": "GardeFou",
      "Effect": "Allow",
      "Action": "bedrock:ApplyGuardrail",
      "Resource": [
        "arn:aws:bedrock:us-east-1:<compte>:guardrail/<id-garde-fou>",
        "arn:aws:bedrock:*:<compte>:guardrail-profile/us.guardrail.v1:0"
      ]
    },
    {
      "Sid": "VerificationCompartiment",
      "Effect": "Allow",
      "Action": "s3:GetBucketPublicAccessBlock",
      "Resource": "arn:aws:s3:::alphaforge-traces-<suffixe>"
    },
    {
      "Sid": "EcritureTraces",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::alphaforge-traces-<suffixe>/traces/*"
    }
  ]
}
```

## 6. Services AWS utilisés et pourquoi

| Service | Usage | Justification |
| --- | --- | --- |
| AWS STS | `get-caller-identity` | Vérifier le compte et les identifiants temporaires avant toute opération |
| Amazon Bedrock (contrôle) | Liste des modèles et profils, gestion du garde-fou | Choisir un modèle `ACTIVE` vérifié dans le compte, créer le garde-fou par script reproductible |
| Amazon Bedrock Runtime, API Converse | Agents analyste et explicateur | API unifiée avec appels d'outils, identifiant de modèle configurable |
| Amazon Bedrock Guardrails | Sujets refusés, ancrage contextuel | Faire respecter la règle 8 et mesurer la fidélité de l'explication au dossier |
| Amazon S3 | Compartiment privé `alphaforge-traces-<suffixe>` (traces d'exécution JSON) | Preuve consultable de l'intégration réelle (US-16), créée et vérifiée par script reproductible |

## 7. Points à vérifier dans le compte

- Modèles en cycle de vie `ACTIVE` et profils d'inférence disponibles (`us.`, `global.`) : l'API ne dit pas si un modèle accepte Converse ou les outils, d'où l'essai `--try-converse`.
- Prise en charge du choix d'outil forcé (`--tool-choice any`) par le modèle retenu.
- Niveau de classification des sujets refusés : **Standard** (défaut du script, `--tier classic` pour l'autre). Il exige le profil interrégional `us.guardrail.v1:0` : les demandes sont alors traitées dans une autre région américaine, ce qui reste acceptable pour des données publiques ou fictives. Disponible dans le compte de l'atelier. Le niveau d'ancrage contextuel reste Classic. Le panneau de test en texte libre envoie la saisie hors de `us-east-1` : n'y saisir rien de réel.
- Mesure sur le compte (19 requêtes de `tests/fixtures/guardrail_prompts.json`), avec le niveau Classic puis Standard :

  | Version | Niveau | Concordance | Remarque |
  | --- | --- | --- | --- |
  | 1 | Classic | 14/19 | définitions avec une clause "non visé", mal classées |
  | 2 | Classic | 15/19 | définitions à l'affirmatif, "Achète TSLA pour moi" et "Comment en profiter ?" encore manquées |
  | 3 | Standard | 17/19 | tous les refus attendus, 2 faux refus sur des questions historiques |
  | 4 | Standard | 16/19 à 17/19 | définition de la prédiction recentrée sur l'avenir, résultat variable d'un essai à l'autre |

  Restent des faux refus sur des questions historiques (A02, A07, parfois A09), classées à tort comme prédiction. Le classifieur n'est pas parfaitement stable d'un essai à l'autre. Les refus attendus (D01 à D09) sont tous obtenus avec le niveau Standard. Ces faux refus touchent le panneau de test en texte libre, pas l'analyse, qui passe par le formulaire structuré.
- Changer le garde-fou : `--apply` met à jour le garde-fou existant et publie une nouvelle version numérotée. Les versions publiées ne changent plus : revenir en arrière consiste à pointer `ALPHAFORGE_GUARDRAIL_VERSION` vers une version précédente. L'identifiant et la version se communiquent dans le canal de l'équipe, pas dans le dépôt.
- Comportement en français : faux refus sur les requêtes permises (`A01` à `A10`) et refus manqués (`D01` à `D09`) au test `--test`. Ajuster les définitions et exemples, puis relancer `--apply` (nouvelle version).
- Limites d'`ApplyGuardrail` pour l'ancrage : 100 000 caractères pour la source, 1 000 pour la requête, 5 000 pour le texte.

## 8. Clés API Bedrock à courte durée (option à confirmer)

Bedrock propose des clés API à courte durée. Ce n'est pas la méthode prévue : les identifiants temporaires de Workshop Studio suffisent. Si l'équipe envisage cette option, la confirmer d'abord avec un mentor. Une telle clé est un secret au même titre que les identifiants AWS : terminal dédié ou `.env` ignoré seulement, jamais dans le dépôt, un prompt, une capture ou la vidéo.

## 9. Ce qui ne doit jamais entrer dans le dépôt

- Identifiants AWS (clé d'accès, clé secrète, jeton de session), clés API, contenu de `.env`.
- Numéro de compte, ARN complets (ils contiennent le numéro de compte), URL Kiro contenant un jeton.
- Captures ou journaux non masqués. Les scripts masquent déjà le compte et les ARN dans leurs sorties.

Avant chaque commit, relire le diff indexé pour y chercher ces motifs. Si un secret a été exposé, cesser de l'utiliser et prévenir un mentor ou un organisateur ; le supprimer dans un commit ultérieur ne suffit pas.
