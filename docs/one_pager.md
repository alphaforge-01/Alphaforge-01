# AlphaForge AI : un copilote de cohérence, pas un conseiller

Datathon PolyFinances 2026. Simulation éducative : tout est fictif, aucune transaction, aucun conseil personnalisé.

**État du dépôt au 14 novembre 2026.** Ce texte décrit ce qui tourne, pas la cible.

## Problème
Un investisseur peut être tenté par une idée (par exemple 25 % dans TSLA) sans voir si elle respecte son propre profil. Un verdict sans preuve est inutilisable : chaque chiffre doit être vérifiable.

## Solution
Question servie : "Mon portefeuille fictif correspond-il à mon profil, et que change mon idée ?" Le système ne dit pas quoi acheter. Il compare le portefeuille avant et après l'idée, nomme les tensions avec les règles du profil, indique ce qui ferait changer le verdict et explique le résultat en deux niveaux, novice et pro, avec les mêmes chiffres.

## Architecture agentique (conception de l'équipe)
Un agent agit, le code juge, un agent explique. L'analyste (Bedrock, outils, tours bornés) choisit les outils et propose des variantes sans rédiger. La gouvernance est du code déterministe. L'explicateur (un appel, sans outil) ne voit que le dossier d'explication. Un validateur en code rejette son texte au besoin, puis un gabarit sans modèle prend le relais.

## Données
Jeu des organisateurs : 31 actifs, prix quotidiens Yahoo Finance du 2021-11-12 au 2026-11-12, taux USD/CAD de la Banque du Canada, taux et inflation (Banque du Canada, FRED). Prix convertis en CAD, calendriers alignés, rendements sur `adj_close`. Ni ESG ni nouvelles dans ces données.

## Gouvernance et explicabilité (opérationnelles et testées)
- 6 règles par profil, 4 statuts (conforme, tension, conflit, information manquante), marge au seuil et contrefactuel "conforme sous X %" par balayage du poids. Seuils présentés comme hypothèses de l'équipe.
- Dossier d'explication construit par le code : facteurs classés, preuves, glossaire et limites du niveau.
- Rédaction par renvois ([E3], [G1], [T2]) : les chiffres viennent du registre, jamais du texte du modèle. Le validateur rejette un chiffre hors registre, un renvoi inconnu, un terme de recommandation ou de prévision, et une règle non citée.
- Textes fixes affichés par le code : 4 avertissements et 5 limites obligatoires (biais du survivant, historique de cinq ans et volatilité comme indicateur parmi d'autres, dates et devises, hypothèses de simulation, qualité et disponibilité des données).

## Ce qui fonctionne réellement
- Chargement, alignement des calendriers, conversion en CAD, rendement, volatilité et perte maximale (flux A, avec tests).
- Trois personas, profil par cases, gouvernance, contrefactuel, dossier, gabarit novice et pro, validateur et rendu Markdown (flux B).
- Pipeline `run_analysis` et `explain` en mode hors ligne, client Bedrock, spécifications d'outils, scripts de garde-fou et de vérification AWS (flux C).
- Interface Streamlit : choix et construction du profil, bandeaux d'avertissement et de données d'essai (flux D).
- 723 tests automatisés réussis, sans appel AWS.

## Limites du prototype
- Les outils de simulation du flux A (`agent_tools.py`, `evidence.py`) ne sont pas encore dans le dépôt. Le pipeline utilise donc des bouchons à chiffres inventés, marqués "données d'essai".
- Les agents analyste et explicateur sur Bedrock ne sont pas encore écrits. Aucun appel de modèle réel n'a été validé de bout en bout, et la création effective du garde-fou dans le compte AWS n'est pas vérifiée ici.
- L'interface n'affiche pas encore la radiographie, le résultat, l'explication ni la trace.
- Limites des données : biais du survivant, cinq ans d'historique avec une seule baisse marquée, données publiques non certifiées. Les résultats décrivent le passé et ne prévoient rien.
- Hors périmètre : texte libre, rejeu historique, transactions réelles.
