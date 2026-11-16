# Mises à jour attendues du one pager et de la documentation technique

Suivi tenu le dimanche 15 novembre 2026, établi en comparant `docs/one_pager.md` et `docs/technical_documentation.md` à l'état de `main` (2760 tests verts) ; mis à jour après la réécriture du one pager. Cocher chaque ligne dans la PR qui la traite. Simulation éducative : rien ici n'est un conseil.

Responsables d'après le plan : one pager, Samer (issue 74, relecture croisée de Naoufal) ; documentation technique, Naoufal ; scores, traces et description AWS, Godwin.

## A. À trancher avant d'écrire (décisions de l'équipe)

- [ ] **Messages signalés envoyés à l'agent (PR 93).** En mode `bedrock`, un message que le garde-fou d'entrée signale, ou que les règles locales refusent, est maintenant transmis à l'agent avec outils avec un signalement : l'agent choisit les outils de « la reformulation permise la plus proche » (un ordre avec actif et poids devient une idée à confirmer, un ordre sans poids les faits de l'actif, un conseil la description du profil). La sortie reste contrôlée par le validateur et le garde-fou de sortie, et le signalement est affiché. Avant cette PR, un message refusé n'atteignait jamais un modèle (c'est ce que l'audit de sécurité des PR 88 et 92 avait vérifié). La règle 8 demande que le garde-fou fasse respecter le refus : décider si on garde ce comportement, puis **le décrire tel quel** dans la documentation technique (sections 2.1, 5.1 et 6.2). Aucun audit de sécurité n'est mentionné dans la PR 93.
- [ ] **Pas de déploiement (décision du 15 novembre).** Les correcteurs jugent la remise sur la vidéo de démonstration, avec l'application lancée en local ; la PR de déploiement est retirée (PR 99). Ne rien écrire sur un lien hébergé. La vidéo doit montrer l'application locale en mode `bedrock`.
- [ ] **Accès au dépôt.** Dépôt privé : accès donné aux organisateurs par invitation (lecture), à demander si le message de remise exige un lien GitHub. À écrire dans le message de remise, pas dans la doc.

## B. One pager (`docs/one_pager.md`, Samer)

Réécrit le 15 novembre au soir : originalité, bénéfices, sources, 15 scénarios, 2 760 tests, plus de FRED, mise à jour des limites. Reste :

- [ ] **Deux tirets cadratins** (règle 1) : titre, ligne 1, et ligne « Agent analyste » (ligne 13). `scripts/final_checks.sh` échoue tant qu'ils sont là.
- [ ] Vérifier qu'il **tient sur une page en PDF** avec ses six rubriques (problème, approche agentique, originalité, sources, explicabilité, bénéfices).
- [ ] Remplacer la mention d'un ancrage faible par les **scores de l'essai final** (section D), en précisant que le score mesure la proximité avec le dossier, pas l'exactitude des statuts.
- [ ] Facultatif : chiffrer la mise à l'épreuve (7 verdicts sur 15 changent avec des seuils 20 % plus stricts, `outputs/reports/sensitivity.md`).
- [ ] Chaque chiffre du one pager se retrouve dans la doc technique ou dans `outputs/reports/`.

## C. Documentation technique (`docs/technical_documentation.md`, Naoufal)

Part du flux C faite dans la PR 100 : chaîne de la conversation (2.1), composants (2.2), services AWS, captures et contrôles (2.3), limites de l'agent (6.2), améliorations (6.3). Reste :

- [ ] **4.3 trace réelle** : remplacer les cinq lignes « À REMPLIR » et le marqueur d'Amira en 5.3 par l'essai final (section D).
- [ ] **Marqueur de 6.2** (agent conversationnel) : part de texte du modèle affiché, motifs de repli, ancrage, latence, après l'essai réel.
- [ ] **5.1 validations** : « plus de 2 400 tests » devient « plus de 2 700 » (2760 sur `main`) ; citer `scripts/check_clean_clone.py` (installation depuis un clone propre) ; la ligne Interface dépend du travail d'interface en cours.
- [ ] **Explicateur novice sans jargon** (PR 96, `explainer_v6`) : décrire le changement en 2.2.
- [ ] **2.1 et 2.2** : « 5 pages » et la ligne Interface, à relire une fois l'interface terminée.

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
