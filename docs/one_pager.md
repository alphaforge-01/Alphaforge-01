# AlphaForge AI : un copilote de cohérence, pas un conseiller

Datathon PolyFinances 2026. Simulation éducative : tout est fictif, aucune transaction, aucun conseil personnalisé.

## Problème et solution
Une idée tentante (25 % dans TSLA) peut contredire le profil de celui qui la formule, et un verdict sans preuve est inutilisable. Le système ne dit pas quoi acheter : il compare le portefeuille avant et après l'idée, applique les règles du profil, donne le plus grand poids testé qui respecte chaque règle en tension ou en conflit, propose des variantes et explique le résultat aux niveaux novice et pro, avec les mêmes chiffres.

## Architecture : un agent agit, le code juge, un agent explique
- **Analyste** (Bedrock, tours et appels bornés) : choisit les outils, propose au plus deux variantes.
- **Code déterministe** : calculs, gouvernance, preuves, dossier, validateur.
- **Explicateur** (Bedrock, sans outil) : écrit des renvois ([E3], [G1]) remplacés par les valeurs du registre. Texte rejeté ou Bedrock en échec : un gabarit sans modèle prend le relais.
- **Garde-fou Bedrock** : sujets refusés et ancrage du texte, en mode détection.

## Données
31 actifs, prix Yahoo Finance (2021-11-12 au 2026-11-12), taux USD/CAD de la Banque du Canada, FRED. Prix en CAD. Profils, portefeuilles et seuils : fictifs, hypothèses de l'équipe.

## Gouvernance et explicabilité
- Statuts : conforme, tension, conflit, information manquante. Aucune preuve ESG n'existe : la règle ESG de Mateo reste en "information manquante", donc un verdict conforme n'est pas une vérification ESG.
- Le validateur rejette un chiffre hors registre, un renvoi inconnu, une recommandation ou prévision, une règle non citée, un lien, une image ou une balise HTML.
- Avertissements et limites fixes par niveau ; chaque preuve porte source, période et devise.

## État du prototype
- **Vérifié en local, sans AWS** : outils, gouvernance, dossier, validateur, tests automatisés, 12 scénarios fixes sans échec (25 % de TSLA : Robert en conflit, Amira en tension, Mateo en "information manquante").
- **Vérifié dans le compte AWS**, d'après `docs/technical_documentation.md` et `outputs/reports/demo_traces/` : agents, garde-fou, traces S3.
- **Implémenté, sans test automatisé** : interface Streamlit (affichage non relu).

## Limites
- Aucune donnée ESG. Biais du survivant, cinq ans d'historique, données publiques non certifiées.
- Ancrage faible des explications du modèle (0,34 pour Robert) malgré des chiffres validés ; le mode Bedrock dépend du compte temporaire.
- Hors périmètre : texte libre, rejeu historique, transactions réelles.
