# AlphaForge AI — Un copilote de cohérence, pas un conseiller

**Datathon PolyFinances 2026 | Équipe AlphaForge 01**

*Simulation financière éducative : profils et portefeuilles fictifs, aucune transaction réelle, aucun conseil personnalisé ni prédiction de rendement.*

### 1. Problème et solution
Une idée de placement peut sembler intéressante tout en contredisant les contraintes d'un investisseur. Un simple verdict ne suffit pas : il faut comprendre **pourquoi**, sur quelles données il repose et ce qui pourrait le modifier.

AlphaForge AI simule une idée sur un portefeuille fictif, compare les mesures avant/après, vérifie les règles du profil et explique les résultats en langage novice ou professionnel, sans jamais dire quoi acheter.

### 2. Approche agentique
- **Agent analyste — Amazon Bedrock :** choisit des outils de calcul, examine le portefeuille et propose jusqu'à deux variantes simulées.
- **Code déterministe :** calcule les mesures, applique les règles, produit les verdicts et construit un registre de preuves vérifiables.
- **Agent explicateur et conversationnel :** explique les conflits, les données du profil et les facteurs pouvant modifier un verdict. Les réponses passent par un validateur et les garde-fous Bedrock ; un texte généré par le code prend le relais si nécessaire.
- **AWS :** Bedrock Converse pour les agents, Guardrails pour les sujets refusés et l'ancrage, S3 privé pour les traces d'analyse.

### 3. Originalité
- **Un copilote de cohérence, pas un conseiller :** pour Robert et TSLA à 25 %, il montre un conflit et un poids testé conforme à la règle de concentration à 20 % ou moins, sans recommandation d'achat.
- **L'IA ne décide ni des chiffres ni des verdicts :** elle utilise des renvois `[E#]`, `[G#]`, `[T#]`, remplacés par le code.
- **L'absence de preuve reste visible :** pour Mateo, un verdict financier conforme peut coexister avec un verdict ESG « information manquante ».
- **Des conclusions mises à l'épreuve :** période, devise, fréquence, date d'analyse et seuils sont modifiés séparément pour mesurer leur influence sur les verdicts.

### 4. Sources de données
**31 actifs** : actions canadiennes et américaines, FNB et cryptoactifs. Prix historiques Yahoo Finance du 12 novembre 2021 au 12 novembre 2026 ; taux USD/CAD de la Banque du Canada. Conversion en CAD au taux connu du même jour, calendrier boursier commun TSX–États-Unis et contrôle `as_of` empêchant l'utilisation de données futures. Profils et seuils entièrement fictifs.

### 5. Explicabilité et validation
Chaque mesure est reliée à une preuve contenant sa source, sa période, sa devise, sa transformation et ses limites. Le validateur rejette les chiffres non justifiés, références inconnues, conseils et prédictions. Le garde-fou complète ce contrôle et signale un ancrage faible sans le confondre avec une preuve d'exactitude.

**Prototype vérifié :** 15 scénarios de référence sans échec ; **2 760 tests réussis** et 1 ignoré. Parcours Streamlit testés automatiquement, services Bedrock, Guardrails et traces S3 vérifiés dans le compte AWS de l'atelier.

### 6. Bénéfices pour l'utilisateur
- Comprendre les tensions et conflits avec des explications novice/pro fondées sur les mêmes chiffres.
- Consulter les preuves et comparer portefeuille initial, simulation et variantes.
- Poser des questions pédagogiques sur le profil, les règles et les résultats, avec réponses contrôlées.
- Explorer différentes hypothèses sans exposer de données financières personnelles.

**Limites :** aucune donnée ESG vérifiable ; historique de cinq ans et données publiques non certifiées ; seuils hypothétiques ; sensibilité des résultats aux hypothèses ; mode Bedrock dépendant du compte AWS temporaire. Les simulations historiques ne prédisent pas les performances futures.