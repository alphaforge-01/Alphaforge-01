# Captures de la console AWS

Captures prises le 15 novembre 2026 dans la console AWS, région us-east-1, compte temporaire de l'atelier. Elles montrent l'intégration réelle de l'application avec Amazon Bedrock, Bedrock Guardrails et Amazon S3.

Les zones sensibles sont masquées par un rectangle noir : numéro de compte, rôle de connexion, ARN du garde-fou, identifiant du garde-fou, nom du compartiment S3 et identifiant canonique S3. Aucune capture ne contient d'identifiant temporaire ni de clé. Simulation éducative, données fictives.

| Fichier | Ce qu'il montre | Ce qu'il prouve |
| --- | --- | --- |
| `aws_01_guardrail_versions.png` | Le garde-fou `alphaforge-guardrail`, son brouillon et ses cinq versions publiées par `scripts/setup_guardrail.py` le 14 novembre | Le garde-fou est créé par un script reproductible. |
| `aws_02_version4_denied_topics.png` | Version 4 : trois sujets refusés (conseil personnalisé, exécution d'ordres, prédiction de rendement), bloqués en entrée et en sortie, niveau Standard, inférence interrégionale US Guardrail v1 | Règle 8 : pas de conseil personnalisé, pas d'ordre, pas de prédiction de rendement |
| `aws_03_version4_grounding_and_tier.png` | Version 4 : contrôles d'ancrage et de pertinence activés, seuil de 0,5, action en détection sans blocage, niveau Classic | Le texte du modèle est comparé au dossier d'explication. Le score est signalé sans bloquer. |
| `aws_04_order_refusal_test.png` | Test de la version 4 par l'API `ApplyGuardrail` avec la demande fictive "Achète 100 actions de TSLA pour moi" : intervention, message de refus en français | Une demande d'ordre est refusée par le garde-fou |
| `aws_05_inference_profiles.png` | Profils d'inférence système, dont `us.anthropic.claude-haiku-5-5` et `us.anthropic.claude-sonnet-5-5` | Les deux modèles des agents (analyste et explicateur) sont disponibles dans le compte |
| `aws_06_s3_permissions.png` | Compartiment des traces : Block Public Access activé, politique qui refuse tout accès sans TLS, propriété des objets `Bucket owner enforced`, aucun accès public dans la liste de contrôle d'accès | Les traces sont stockées dans un compartiment privé (CLAUDE.md, sécurité par défaut) |
| `aws_07_s3_properties.png` | Compartiment des traces : chiffrement par défaut SSE-S3, étiquette `Project = alphaforge` | Les traces sont chiffrées au repos |

Les versions 4 et 5 du garde-fou ont été publiées à la même minute. La version 4 est celle configurée pour les essais réels du 15 novembre (voir la sortie de `scripts/try_bedrock_run.py` et les traces dans `outputs/reports/`).

À ajouter avant la remise, après la régénération des traces finales : la liste des objets du compartiment des traces, et la sortie du terminal de l'essai réel (`scripts/try_bedrock_run.py --run`).
