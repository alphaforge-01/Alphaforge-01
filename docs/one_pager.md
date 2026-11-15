# AlphaForge AI : un copilote de cohérence, pas un conseiller

Datathon PolyFinances 2026. Simulation éducative : tout est fictif, aucune transaction, aucun conseil personnalisé.

## Problème
Une idée tentante (25 % dans TSLA) peut ne pas respecter le profil de celui qui la formule. Un verdict sans preuve est inutilisable : chaque chiffre doit être vérifiable.

## Solution
Question servie : "Mon portefeuille fictif correspond-il à mon profil, et que change mon idée ?" Le système ne dit pas quoi acheter. Il compare le portefeuille avant et après l'idée, applique les règles du profil, donne pour chaque règle en tension ou en conflit le plus grand poids testé qui la respecte, propose des variantes et explique le résultat aux niveaux novice et pro, avec les mêmes chiffres.

## Architecture agentique
Un agent agit, le code juge, un agent explique.
- **Analyste** (Bedrock, 6 tours et 12 appels au plus) : choisit les outils et propose au plus deux variantes, sans rédiger.
- **Code déterministe** : calculs, gouvernance, registre de preuves, dossier d'explication, validateur.
- **Explicateur** (Bedrock, un appel, sans outil) : ne voit que le dossier et écrit des renvois ([E3], [G1], [T2]) remplacés par les valeurs du registre. Texte rejeté ou Bedrock en échec : un gabarit sans modèle prend le relais, et la trace l'indique.
- **Garde-fou Bedrock** : sujets refusés et ancrage du texte rendu, en mode détection.

## Données
31 actifs, prix quotidiens Yahoo Finance (2021-11-12 au 2026-11-12), taux USD/CAD de la Banque du Canada, séries FRED. Prix convertis en CAD, calendrier commun, rendements sur `adj_close`. Personas et seuils : fictifs, hypothèses de l'équipe.

## Gouvernance et explicabilité
- 6 règles financières par profil, plus une règle ESG pour une exigence ESG forte (Mateo). 4 statuts : conforme, tension, conflit, information manquante. Une donnée absente donne "information manquante", jamais "conforme".
- Aucune preuve ESG n'existe : la règle ESG reste en "information manquante". Un verdict financier conforme n'est donc pas une vérification ESG.
- Le validateur rejette un chiffre hors registre (même en lettres), un renvoi inconnu, une recommandation ou prévision, une règle non citée.
- Quatre avertissements et cinq limites obligatoires, au texte fixe par niveau. Chaque preuve porte source, période, devise et limites.

## État du prototype
**Opérationnel, données réelles, sans AWS (mode `offline`)** : outils de simulation, registre de preuves, gouvernance, contrefactuel, variantes, dossier, gabarit novice et pro, validateur. Les 12 scénarios fixes (3 personas, 4 demandes) s'exécutent sans échec : avec 25 % de TSLA, Robert est en conflit (concentration), Amira en tension (perte maximale) et Mateo en "information manquante" (ESG).

**Présent, testé avec un client simulé, non vérifié sur AWS** : agents Bedrock, garde-fou, cache des explications, traces S3. Aucun essai réel de bout en bout n'est documenté.

**Interface Streamlit** (mode `fixture` : chiffres inventés) : choix et construction du profil, avertissements. Radiographie, résultat, explication et trace sont "à venir" ; les résultats se lisent par `scripts/run_scenarios.py`.

## Limites
- Aucune donnée ESG. Biais du survivant, cinq ans d'historique avec une seule baisse marquée, volatilité comme indicateur parmi d'autres, données publiques non certifiées. Le passé décrit, rien n'est prévu.
- Hors périmètre : texte libre, rejeu historique, transactions réelles.
