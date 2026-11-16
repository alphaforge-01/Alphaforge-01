# Mises à jour attendues du one pager et de la documentation technique

Suivi tenu le dimanche 15 novembre 2026, établi en comparant `docs/one_pager.md` et `docs/technical_documentation.md` à l'état de `main` (commit 5ac08bc, 2760 tests verts). Cocher chaque ligne dans la PR qui la traite. Simulation éducative : rien ici n'est un conseil.

Responsables d'après le plan : one pager, Samer (issue 74, relecture croisée de Naoufal) ; documentation technique, Naoufal ; scores, traces et description AWS, Godwin.

## A. À trancher avant d'écrire (décisions de l'équipe)

- [ ] **Messages signalés envoyés à l'agent (PR 93).** En mode `bedrock`, un message que le garde-fou d'entrée signale, ou que les règles locales refusent, est maintenant transmis à l'agent avec outils avec un signalement : l'agent choisit les outils de « la reformulation permise la plus proche » (un ordre avec actif et poids devient une idée à confirmer, un ordre sans poids les faits de l'actif, un conseil la description du profil). La sortie reste contrôlée par le validateur et le garde-fou de sortie, et le signalement est affiché. Avant cette PR, un message refusé n'atteignait jamais un modèle (c'est ce que l'audit de sécurité des PR 88 et 92 avait vérifié). La règle 8 demande que le garde-fou fasse respecter le refus : décider si on garde ce comportement, puis **le décrire tel quel** dans la documentation technique (sections 2.1, 5.1 et 6.2). Aucun audit de sécurité n'est mentionné dans la PR 93.
- [ ] **Application hébergée et AWS.** `docs/deployment.md` dit : mode hors ligne, aucune clé AWS dans les secrets de l'hébergeur, conformément à CLAUDE.md. Si l'équipe modifie cette règle pour la remise, mettre à jour ce document, la doc technique (2.3) et le one pager.
- [ ] **Accès au dépôt.** Dépôt privé : accès donné aux organisateurs par invitation (lecture). À écrire dans le message de remise, pas dans la doc.

## B. One pager (`docs/one_pager.md`, Samer)

Contraintes : une page en PDF, six rubriques exigées par l'énoncé (problème, approche agentique, originalité, sources de données, explicabilité, bénéfices pour l'utilisateur).

- [ ] **Ajouter « Originalité » et « Bénéfices pour l'utilisateur »** (absentes). Propositions détaillées dans l'issue 74.
- [ ] Données : retirer « FRED » (aucune série FRED n'est lue). Ajouter : calendrier commun TSX et États-Unis, conversion au taux du même jour, aucune donnée future.
- [ ] État du prototype : « 12 scénarios » devient « 15 scénarios (3 profils x 5 boutons) sans échec » ; ajouter « plus de 2 700 tests » (2760 sur `main`).
- [ ] Remplacer « interface sans test automatisé (affichage non relu) » : interface rejouée sans navigateur pour les trois profils, dialogues de la conversation testés, verdicts financier et ESG affichés.
- [ ] Remplacer « ancrage faible (0,34 pour Robert) » par la plage mesurée et les scores de l'essai final (voir section D). Dire que le score mesure la proximité avec le dossier, pas l'exactitude des statuts.
- [ ] « Hors périmètre : texte libre » est faux : la conversation comprend des messages libres (règles, puis agent avec outils en mode `bedrock`). Garder hors périmètre : transactions réelles et rejeu historique.
- [ ] Architecture : ajouter l'agent conversationnel et son contrôle (même validateur, même garde-fou). Nommer les services AWS : Amazon Bedrock (API Converse, Guardrails) et Amazon S3 privé pour les traces.
- [ ] Ajouter la mise à l'épreuve des hypothèses : les verdicts tiennent sur les variantes de données ; les seuils sont l'hypothèse dominante (7 verdicts sur 15 changent avec des seuils 20 % plus stricts, d'après `outputs/reports/sensitivity.md`).
- [ ] Ajouter l'adresse de l'application hébergée quand elle existe.
- [ ] Couper pour tenir sur une page : « État du prototype » en deux lignes.

## C. Documentation technique (`docs/technical_documentation.md`, Naoufal)

- [ ] **2.1 chaîne d'exécution** : la conversation est marquée « en cours ». Elle est fusionnée (PR 88, 91, 92, 93) : agent avec outils qui collecte les faits (outils du code, au plus 3 tours et 6 appels), puis réponse rédigée sous contrôle (un appel sans outil, validateur, garde-fou), réponse du code en repli, routage par règles si l'agent est indisponible.
- [ ] **2.2 et 2.3** : ajouter l'agent conversationnel (modèle réglé par `ALPHAFORGE_CONVERSATION_MODEL_ID`, par défaut celui de l'explicateur), le prompt `conversation_v1` et `conversation_router_v1`, les contrats `ConversationBrief` et `ConversationReply`. Services AWS : « Agents analyste et explicateur » devient « trois agents ».
- [ ] **2.3 sécurité AWS** : vérification du propriétaire du compartiment (`ExpectedBucketOwner`), politique IAM de référence et captures de la console (`outputs/figures/README.md`), contrôles `scripts/final_checks.sh`. Rien de cela n'est cité aujourd'hui.
- [ ] **Explicateur novice sans jargon** (PR 96, prompt `explainer_v6`) : décrire le changement.
- [ ] **4.3 trace réelle** : remplacer le bloc « À REMPLIR » par l'essai final (voir section D).
- [ ] **5.1 validations** : nombre de tests, installation neuve sur Python 3.12 et 3.14 (`docs/deployment.md`), `scripts/check_clean_clone.py`, mesure des 60 phrases de la conversation (PR 85).
- [ ] **5.3 ancrage** : décrire la décision du 15 novembre (le texte du modèle reste affiché avec un avertissement « ancrage faible » ou « très faible »), le contrôle limité aux phrases écrites par le modèle (PR 89), la source qui contient maintenant le contexte du profil (PR 61), et la plage mesurée des scores.
- [ ] **6.2 limites** : le score varie d'une génération à l'autre pour un même dossier ; l'agent conversationnel n'est mesuré que par les tests et la mesure des 60 phrases tant que l'essai réel n'est pas fait ; le point A (messages signalés) ; l'application hébergée est hors ligne.
- [ ] **Déploiement** : une courte section ou un renvoi vers `docs/deployment.md` (hébergement, gel, retour arrière).

## D. À fournir par Godwin (dépend du terminal AWS)

- [ ] Essai réel final de l'explication sur `main` (`scripts/try_bedrock_run.py --run --personas amira,robert,mateo --save-local`) : date, scores d'ancrage, origine du texte. Joindre les scores à Naoufal et Samer.
- [ ] Essai réel de l'agent conversationnel et de l'agent avec outils : part de texte du modèle affiché, motifs de repli, ancrage, latence, refus d'une demande d'ordre.
- [ ] Régénérer `outputs/reports/demo_traces/` après la dernière fusion, avec son README.
- [ ] Captures restantes : liste des objets du compartiment et sortie du terminal de l'essai réel (`outputs/figures/`).
- [ ] Vérifier en lecture seule la journalisation des appels de modèle : `aws bedrock get-model-invocation-logging-configuration` (les questions de la conversation partent maintenant vers Bedrock).

## E. Contrôles avant l'export PDF

- [ ] Aucun tiret cadratin, aucun emoji, aucune clé, aucun numéro de compte, aucun nom de compartiment ni identifiant de garde-fou : `bash scripts/final_checks.sh`.
- [ ] Chaque chiffre du one pager se retrouve dans la doc technique ou dans `outputs/reports/`.
- [ ] Le one pager tient sur une page en PDF ; la documentation technique est exportée en PDF avant lundi 14 h.
