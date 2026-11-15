# Mise à l'épreuve des hypothèses

> **Avertissement.** Simulation éducative sur des profils, portefeuilles et capitaux fictifs. Ce rapport décrit le passé sous plusieurs conventions ; il ne prédit aucun rendement et n'est pas un conseil financier personnalisé. Les seuils des règles sont des hypothèses de l'équipe.

## Ce qui est testé

Les verdicts de la gouvernance reposent sur des choix de l'équipe. Ce rapport refait l'évaluation en changeant **un seul choix à la fois** et montre quelles règles changent de statut, pour les 3 personas fictifs et les 5 demandes prêtes de l'interface (financement au prorata), soit 15 cas par variante. Les verdicts portent sur le portefeuille après l'idée.

Reproduire : `.venv/Scripts/python scripts/run_sensitivity.py` (aucun appel AWS, sortie identique à chaque exécution).

## Faits

- Données : `data/raw/prices_daily.csv` (prix ajustés `adj_close`) et `data/raw/fx_usdcad_daily.csv` (taux USD/CAD de la Banque du Canada), calendrier commun aux marchés, arrêtées au 2026-11-12.
- Cas de base : du 2021-11-12 au 2026-11-12, 1227 rendements quotidiens en CAD, portefeuille rééquilibré chaque jour.
- Chaque valeur du rapport est recalculée par le code (`src/alphaforge/sensitivity.py`) avec les mêmes fonctions que les outils des agents ; le cas de base redonne exactement leurs chiffres.

## Hypothèses testées

| Variante | Ce qui change | Hypothèse |
| --- | --- | --- |
| `base` | Cas de base | Période complète (environ 5 ans), CAD au taux du jour, rendements quotidiens, seuils de l'équipe. |
| `window_3y` | Fenêtre de 3 ans | Seulement les 3 dernières années : l'épisode de baisse de 2022 sort de la période. |
| `window_1y` | Fenêtre de 1 an | Seulement la dernière année : indicatif, environ 250 rendements. |
| `currency_local` | Devise locale | Chaque actif dans sa devise de cotation : revient à supposer le change parfaitement couvert, sans coût. C'est une hypothèse, pas un fait. |
| `as_of_2024` | Données arrêtées au 12 nov. 2024 | On se place deux ans plus tôt, sans aucune donnée postérieure (environ 3 ans de recul). L'univers et les portefeuilles restent ceux choisis en 2026. |
| `as_of_2025` | Données arrêtées au 12 nov. 2025 | On se place un an plus tôt, sans aucune donnée postérieure (environ 4 ans de recul). |
| `weekly` | Rendements hebdomadaires | Un point par semaine (dernier jour commun de la semaine) : atténue les décalages d'heure de clôture entre marchés et cryptoactifs. |
| `thresholds_strict` | Seuils 20 % plus stricts | Plafonds multipliés par 0,8 et planchers divisés par 0,8 ; exclusions et ESG inchangées. |
| `thresholds_loose` | Seuils 20 % plus souples | Plafonds multipliés par 1,2 et planchers divisés par 1,2 ; exclusions et ESG inchangées. |

Une perte maximale mesurée sur une période plus courte (fenêtre, bloc, date d'arrêt plus ancienne) ou sur des points hebdomadaires ne peut que baisser ou rester égale : son statut est marqué « non comparable », n'est pas compté comme un changement, et garde son statut du cas de base dans le verdict financier comparé. Un verdict suivi de (*) aurait été différent en comptant cette règle.

## Synthèse par variante

Les variantes ne sont ni indépendantes ni équiprobables : ce décompte n'est pas une probabilité.

| Variante | Cas dont le verdict financier change | Règles qui changent de statut, par persona (nombre de cas) |
| --- | --- | --- |
| Fenêtre de 3 ans | 0 sur 15 : aucun | Mateo R2 Volatilité annuelle (1) |
| Fenêtre de 1 an | 0 sur 15 : aucun | Mateo R2 Volatilité annuelle (1), Robert R2 Volatilité annuelle (1) |
| Devise locale | 4 sur 15 : Amira, NVDA 15 % : conforme devient tension<br>Amira, BTC-USD 10 % : conforme devient tension<br>Mateo, TSLA 25 % : conforme devient tension<br>Robert, NVDA 15 % : conforme devient tension | Amira R2 Volatilité annuelle (1), Amira R3 Perte maximale historique (2), Mateo R3 Perte maximale historique (1), Robert R3 Perte maximale historique (1) |
| Données arrêtées au 12 nov. 2024 | 2 sur 15 : Amira, NVDA 15 % : conforme devient tension<br>Amira, BTC-USD 10 % : conforme devient tension | Amira R2 Volatilité annuelle (2), Amira R8 Plafond par groupe corrélé (2) |
| Données arrêtées au 12 nov. 2025 | 2 sur 15 : Amira, NVDA 15 % : conforme devient tension<br>Amira, BTC-USD 10 % : conforme devient tension | Amira R2 Volatilité annuelle (2), Amira R8 Plafond par groupe corrélé (2) |
| Rendements hebdomadaires | 0 sur 15 : aucun | Mateo R2 Volatilité annuelle (1) |
| Seuils 20 % plus stricts | 7 sur 15 : Amira, NVDA 15 % : conforme devient tension<br>Amira, BTC-USD 10 % : conforme devient tension<br>Mateo, TSLA 25 % : conforme devient conflit<br>Mateo, NVDA 15 % : conforme devient tension<br>Mateo, XOM 15 % : conforme devient tension<br>Robert, NVDA 15 % : conforme devient tension<br>Robert, XOM 15 % : conforme devient tension | Amira R2 Volatilité annuelle (2), Amira R3 Perte maximale historique (2), Amira R8 Plafond par groupe corrélé (3), Mateo R1 Concentration par actif (1), Mateo R2 Volatilité annuelle (1), Mateo R3 Perte maximale historique (2), Mateo R4 Part défensive minimale (3), Robert R1 Concentration par actif (3), Robert R2 Volatilité annuelle (1), Robert R3 Perte maximale historique (2), Robert R4 Part défensive minimale (1) |
| Seuils 20 % plus souples | 2 sur 15 : Amira, TSLA 25 % : tension devient conforme<br>Robert, TSLA 25 % : conflit devient tension | Amira R1 Concentration par actif (1), Amira R3 Perte maximale historique (1), Mateo R2 Volatilité annuelle (1), Mateo R4 Part défensive minimale (1), Robert R1 Concentration par actif (1), Robert R2 Volatilité annuelle (1), Robert R3 Perte maximale historique (1), Robert R4 Part défensive minimale (1) |

Règles dont le statut ne change avec aucune variante de fenêtre, devise, date d'arrêt ou fréquence (les identifiants sont propres à chaque persona) : Amira : R1, R4, R5, R6 ; Mateo : R1, R4, R5, R6, R7 ; Robert : R1, R4, R5, R6. Ce sont des règles sur les poids du portefeuille (concentration, part défensive, classes d'actifs, exclusions, préférence ESG), qui ne dépendent pas des prix.

## Grille des verdicts financiers

Verdict financier après l'idée (les règles ESG sont à part : sans source ESG documentée, la règle d'exclusion ESG de Mateo reste en « information manquante » dans toutes les variantes).

| Persona | Idée | `base` | `window_3y` | `window_1y` | `currency_local` | `as_of_2024` | `as_of_2025` | `weekly` | `thresholds_strict` | `thresholds_loose` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Amira | TSLA 25 % | tension | tension (*) | tension (*) | tension | tension | tension | tension | tension | conforme |
| Amira | NVDA 15 % (sans effet) | conforme | conforme | conforme | tension | tension | tension | conforme | tension | conforme |
| Amira | BTC-USD 10 % (sans effet) | conforme | conforme | conforme | tension | tension | tension | conforme | tension | conforme |
| Amira | BTC-USD 40 % | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit |
| Amira | XOM 15 % | conforme | conforme | conforme | conforme | conforme | conforme | conforme | conforme | conforme |
| Mateo | TSLA 25 % | conforme | conforme | conforme | tension | conforme | conforme | conforme | conflit | conforme |
| Mateo | NVDA 15 % | conforme | conforme | conforme | conforme | conforme | conforme | conforme | tension | conforme |
| Mateo | BTC-USD 10 % | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit |
| Mateo | BTC-USD 40 % | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit |
| Mateo | XOM 15 % | conforme | conforme | conforme | conforme | conforme | conforme | conforme | tension | conforme |
| Robert | TSLA 25 % | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit | tension |
| Robert | NVDA 15 % | conforme | conforme | conforme | tension | conforme | conforme | conforme | tension | conforme |
| Robert | BTC-USD 10 % | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit |
| Robert | BTC-USD 40 % | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit | conflit |
| Robert | XOM 15 % | conforme | conforme | conforme | conforme | conforme | conforme | conforme | tension | conforme |

« Sans effet » : le poids visé est déjà le poids actuel du titre dans le portefeuille fictif.

## Détail : Robert, TSLA 25 %

| Variante | Période | Rendements | Volatilité annualisée | Perte maximale | R1 Concentration | R2 Volatilité | R3 Perte maximale | Verdict financier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cas de base | 2021-11-12 au 2026-11-12 | 1227 | 17,6 % | 26,04 % | conflit | tension | tension | conflit |
| Fenêtre de 3 ans | 2023-11-10 au 2026-11-12 | 738 | 17,34 % | 18,91 % | conflit | tension | conforme (non comparable) | conflit |
| Fenêtre de 1 an | 2025-11-12 au 2026-11-12 | 246 | 14,9 % | 9,18 % | conflit | conforme | conforme (non comparable) | conflit |
| Devise locale | 2021-11-12 au 2026-11-12 | 1227 | 18,06 % | 29 % | conflit | tension | tension | conflit |
| Données arrêtées au 12 nov. 2024 | 2021-11-12 au 2024-11-12 | 736 | 17,67 % | 26,04 % | conflit | tension | tension (non comparable) | conflit |
| Données arrêtées au 12 nov. 2025 | 2021-11-12 au 2025-11-12 | 981 | 18,22 % | 26,04 % | conflit | tension | tension (non comparable) | conflit |
| Rendements hebdomadaires | 2021-11-12 au 2026-11-12 | 261 | 16,12 % | 24,41 % | conflit | tension | tension (non comparable) | conflit |
| Seuils 20 % plus stricts | 2021-11-12 au 2026-11-12 | 1227 | 17,6 % | 26,04 % | conflit | tension | tension | conflit |
| Seuils 20 % plus souples | 2021-11-12 au 2026-11-12 | 1227 | 17,6 % | 26,04 % | tension | conforme | tension | tension |

### Jusqu'où les seuils peuvent bouger

Facteur d'échelle des seuils auquel le statut d'une règle change (cas de base), dans le même sens que les variantes de seuils : en dessous de 1, seuils plus stricts (plafond abaissé, plancher relevé) ; au-dessus de 1, plus souples. Exemple : un facteur de 1,25 sur le seuil d'attention veut dire qu'avec un facteur de 1,25 ou plus (seuils plus souples), la valeur mesurée ne le franchit plus ; un facteur de 0,82 veut dire qu'avec un facteur de 0,82 ou moins (seuils plus stricts), elle le franchit.

| Règle | Valeur mesurée | Seuil d'attention | Facteur (attention) | Limite | Facteur (limite) |
| --- | --- | --- | --- | --- | --- |
| R1 Concentration par actif | 25 % | 20 % | 1,25 | 22 % | 1,14 |
| R2 Volatilité annuelle | 17,6 % | 16 % | 1,10 | 25 % | 0,70 |
| R3 Perte maximale historique | 26,04 % | 20 % | 1,30 | 35 % | 0,74 |
| R4 Part défensive minimale | 48,75 % | 40 % | 0,82 | 30 % | 0,62 |
| R6 Concentration en actions individuelles | 25 % | 65 % | 0,38 | 80 % | 0,31 |

## Blocs annuels disjoints : TSLA 25 %

Chaque bloc est une seule année observée. Ces épisodes décrivent le passé (dont la baisse de 2022), ils ne prévoient rien. La perte maximale d'une année n'est pas comparable aux seuils fixés pour 5 ans. La date de début d'un bloc est sa date de base (dernier prix du bloc précédent) : les rendements de deux blocs ne se recouvrent pas.

**Amira**

| Bloc | Rendements | Volatilité annualisée | Perte maximale (non comparable) | R2 Volatilité | Verdict financier |
| --- | --- | --- | --- | --- | --- |
| Du 2021-11-12 au 2022-11-11 | 244 | 38,02 % | 40,3 % | tension | tension |
| Du 2022-11-11 au 2023-11-10 | 245 | 24,96 % | 18,44 % | conforme | tension (*) |
| Du 2023-11-10 au 2024-11-12 | 247 | 25,03 % | 15,21 % | conforme | tension (*) |
| Du 2024-11-12 au 2025-11-12 | 245 | 31,52 % | 31,5 % | tension | tension |
| Du 2025-11-12 au 2026-11-12 | 246 | 23,55 % | 15,54 % | conforme | tension (*) |

**Mateo**

| Bloc | Rendements | Volatilité annualisée | Perte maximale (non comparable) | R2 Volatilité | Verdict financier |
| --- | --- | --- | --- | --- | --- |
| Du 2021-11-12 au 2022-11-11 | 244 | 22,12 % | 20,68 % | tension | tension |
| Du 2022-11-11 au 2023-11-10 | 245 | 17,21 % | 14,87 % | conforme | conforme |
| Du 2023-11-10 au 2024-11-12 | 247 | 17,59 % | 9,94 % | conforme | conforme |
| Du 2024-11-12 au 2025-11-12 | 245 | 21 % | 20,92 % | conforme | conforme |
| Du 2025-11-12 au 2026-11-12 | 246 | 15,1 % | 8,75 % | conforme | conforme |

**Robert**

| Bloc | Rendements | Volatilité annualisée | Perte maximale (non comparable) | R2 Volatilité | Verdict financier |
| --- | --- | --- | --- | --- | --- |
| Du 2021-11-12 au 2022-11-11 | 244 | 19,67 % | 19,02 % | tension | conflit |
| Du 2022-11-11 au 2023-11-10 | 245 | 16,12 % | 14,21 % | tension | conflit |
| Du 2023-11-10 au 2024-11-12 | 247 | 17,02 % | 10,28 % | tension | conflit |
| Du 2024-11-12 au 2025-11-12 | 245 | 19,79 % | 18,91 % | tension | conflit |
| Du 2025-11-12 au 2026-11-12 | 246 | 14,9 % | 9,18 % | conforme | conflit |

## Limites

- Un seul choix change à la fois : les effets combinés ne sont pas testés.
- Les variantes de période réutilisent l'univers et les portefeuilles choisis en 2026 (biais de survie) : se placer en 2024 ne reproduit pas ce qu'on savait en 2024.
- Une fenêtre d'un an compte environ 250 rendements : indicatif seulement.
- La devise locale suppose un change parfaitement couvert, sans coût : c'est une convention de calcul, pas une stratégie disponible.
- La volatilité et la perte maximale décrivent le passé ; elles sont un indicateur de risque parmi d'autres (horizon, diversification, préférences).
- La composition (poids, classes, secteurs) ne change pas d'une variante à l'autre : seuls les risques mesurés sur les prix et le groupe corrélé sont recalculés.
