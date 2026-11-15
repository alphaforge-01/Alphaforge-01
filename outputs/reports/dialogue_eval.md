# Compréhension des messages : mesure sur 60 phrases

> Simulation éducative : phrases inventées, portefeuille fictif de Robert. Aucun appel AWS.

Compreneur mesuré : **règles déterministes (lot 1)**. Chaque phrase porte le comportement idéal attendu (jamais deviner un actif ou un poids, refuser ce qui est interdit), défini dans `tests/fixtures/dialogue_phrases.json`. Une phrase réussit si chaque champ attendu (statut, intention, terme, actif, poids, raison) correspond.

**Résultat : 45 phrases sur 60.**

| Catégorie | Réussies | Ce qui est testé |
| --- | --- | --- |
| idee_explicite (sécurité) | 5/5 | Idée avec un actif et un poids en pourcentage : analyse directe. |
| idee_libre | 6/10 | Idée formulée librement : confirmation ou question, jamais une supposition. |
| relance | 3/4 | Relance après une analyse (dernière idée : 25 % dans NVDA, au prorata). |
| portefeuille_profil | 2/9 | Questions sur le portefeuille fictif ou le profil (atelier : ce que le portefeuille montre, ce qui manque). |
| concept_glossaire | 7/7 | Concepts présents dans le glossaire du projet (T1 à T11). |
| concept_hors_glossaire | 4/6 | Concepts de l'atelier absents du glossaire : réponse honnête, sans inventer. |
| refus (sécurité) | 8/8 | Sujets interdits : ordre, conseil personnalisé, prédiction de rendement. |
| conversation | 5/6 | Salutations, aide et hors périmètre. |
| piege (sécurité) | 5/5 | Demandes ambiguës, invalides ou qui tentent de détourner les consignes. |

## Phrases ratées

| Id | Phrase | Attendu | Compris |
| --- | --- | --- | --- |
| D08 | Et si j'investissais la moitié dans l'or ? | status confirm, ticker GLD, target_weight 0.5 | status answer, answer_kind out_of_scope, reason not_an_idea |
| D09 | Mon portefeuille semble très canadien. Est-ce qu'augmenter mon exposition au S&P 500 améliorerait ma diversification ? | status clarify, ticker SPY | status answer, answer_kind portfolio |
| D13 | Mets un peu plus de tech | status clarify | status answer, answer_kind out_of_scope, reason not_an_idea |
| D14 | Je veux le titre dont tout le monde parle | status clarify | status answer, answer_kind out_of_scope, reason not_an_idea |
| D19 | Et si je finançais avec SPY ? | status confirm, ticker NVDA, target_weight 0.25 | status clarify, ticker SPY, reason missing_weight |
| D22 | Quel est mon horizon de placement ? | status answer, answer_kind profile | status answer, answer_kind out_of_scope, reason not_an_idea |
| D23 | Quelle perte puis-je absorber ? | status answer, answer_kind profile | status answer, answer_kind out_of_scope, reason not_an_idea |
| D24 | Quel est mon objectif ? | status answer, answer_kind profile | status answer, answer_kind out_of_scope, reason not_an_idea |
| D25 | Mon portefeuille est-il bien diversifié ? | status answer, answer_kind xray | status answer, answer_kind portfolio |
| D26 | Quelle est mon exposition au dollar américain ? | status answer, answer_kind xray | status answer, answer_kind out_of_scope, reason not_an_idea |
| D27 | Quelle est ma part défensive ? | status answer, answer_kind xray | status answer, answer_kind out_of_scope, reason not_an_idea |
| D28 | Pourquoi mon idée est-elle en conflit avec mon profil ? | status answer, answer_kind explanation | status answer, answer_kind out_of_scope, reason not_an_idea |
| D37 | C'est quoi un CPG ? | status answer, answer_kind definition | status clarify, reason unknown_asset |
| D41 | Quelle différence entre tolérance et capacité au risque ? | status answer, answer_kind definition | status answer, answer_kind out_of_scope, reason not_an_idea |
| D53 | Merci ! | status answer, answer_kind greeting | status answer, answer_kind out_of_scope, reason not_an_idea |

## Lecture

- Les catégories de sécurité (refus, idées explicites, pièges) doivent rester à 100 % : un test le vérifie à chaque modification.
- Les autres phrases ratées donnent la liste de ce qu'un interprète (compréhension par un modèle) ou un agent conversationnel devra couvrir, sans jamais deviner.
