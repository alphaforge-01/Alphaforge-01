# Clés de preuves produites par le flux A

Référence pour l'interface (flux D, règle d'affichage 1 de `docs/ui_spec.md`) et pour la gouvernance (flux B). Chaque chiffre affiché est le `display_value` d'une preuve du registre, trouvée par son `evidence_key`. La source de vérité est le catalogue `EVIDENCE_METRICS` de `src/alphaforge/evidence.py`.

## Format des clés

- `evidence_key = "<metric>:<subject>"`. Construire les clés avec `alphaforge.evidence.evidence_key(metric, subject)` plutôt qu'à la main.
- `metric` ne contient jamais de deux-points. Les métriques composées sont `<famille>.<clé>`, par exemple `weight_by_asset_class.crypto` ou `weight_by_sector.Information Technology` (les secteurs ont des espaces et des parenthèses : parcourir les preuves par préfixe `weight_by_sector.` plutôt que construire les clés).
- `subject` :
  - `portfolio_before` : portefeuille fictif de départ (outil `analyze_portfolio`) ;
  - `portfolio_after` : portefeuille après l'idée (outil `simulate_portfolio_change`) ;
  - `variant:V1`, `explored:<call_id>` : réétiquetés par le pipeline (flux C) ;
  - un ticker (`TSLA`) : faits d'un actif (outil `get_asset_facts`) ;
  - `profile` : faits déclarés du profil fictif (outil `get_profile_facts`).
- `simulate_portfolio_change` ne produit **aucune** preuve `portfolio_before` : les chiffres "avant" viennent d'`analyze_portfolio`, pour qu'un couple (métrique, sujet) désigne une seule preuve.

## Métriques de série (période explicite, devise CAD)

Champs renseignés : `period_start`, `period_end`, `n_observations`, `currency = "CAD"`, `source_ids = ["prices_daily.csv", "fx_usdcad_daily.csv"]`.

Minimum de rendements : sous 60 rendements (`metrics.MIN_OBSERVATIONS_FOR_VOLATILITY`, environ trois mois de bourse), aucune volatilité annualisée n'est calculée ; l'outil rend alors le statut `missing_info` et **aucune** des preuves de ce tableau. « Toujours » ci-dessous s'entend donc à partir de 60 rendements.

| Métrique | Unité | Exemple de `display_value` | Sujets | Présence |
| --- | --- | --- | --- | --- |
| `volatility_ann` | pct | `17,6 %` | avant, après, ticker | Si au moins 60 rendements (1re preuve de l'outil) ; sinon l'outil rend `missing_info` |
| `max_drawdown` | pct | `26,04 %` | avant, après, ticker | Toujours (2e preuve de l'outil) |
| `max_drawdown_cad` | cad | `26 040 $` | avant, après | Seulement si `capital_cad` est fourni |
| `max_drawdown_start` | text | `2021-12-29` | avant, après, ticker | Toujours (date du sommet) |
| `max_drawdown_end` | text | `2022-06-16` | avant, après, ticker | Toujours (date du creux) |
| `recovery_days` | days ou text | `412 jours` ou `non récupérée sur la période` | avant, après, ticker | Toujours ; `value = "not_recovered"` si pas de retour au sommet |
| `underwater_days` | days | `566 jours` | avant, après, ticker | Toujours |
| `total_return` | pct | `96,54 %` | avant, après, ticker | Toujours |
| `return_ann` | pct | `14,89 %` | avant, après, ticker | Seulement si au moins 252 rendements |

## Composition (sans période)

| Métrique | Unité | Exemple | Sources | Limites |
| --- | --- | --- | --- | --- |
| `top_asset_weight` | pct | `25 %` (libellé avec le ticker) | aucune (entrée fictive) | LM4 |
| `defensive_share` | pct | `48,75 %` | `assets_universe.csv` | LM1, LM4 |
| `weight_by_asset_class.<classe>` | pct | `25 %` | `assets_universe.csv` | LM1, LM4 |
| `weight_by_sector.<secteur>` | pct | `15 %` | `assets_universe.csv` | LM1, LM4 |
| `currency_exposure.CAD`, `currency_exposure.USD` | pct | `41,25 %` | `assets_universe.csv` | LM3, LM4 |
| `largest_correlated_group_weight` | pct | `30 %` (libellé avec les titres du groupe) | `prices_daily.csv`, `fx_usdcad_daily.csv` | LM1 à LM4 |

Exceptions de la ligne `largest_correlated_group_weight` : contrairement aux autres lignes de cette section, elle porte une période, un nombre d'observations et la devise CAD (la corrélation vient des rendements). Elle n'a pas d'écart `_delta` et n'existe pas quand moins de 60 rendements communs sont disponibles.
| `weights.<ticker>` | pct | `11,25 %` | aucune (entrée fictive) | LM4 |

Classes d'actifs possibles : `equity` (actions individuelles), `etf_equity`, `etf_bond`, `etf_commodity`, `crypto`. Une classe absente du portefeuille n'a pas de preuve (son poids est 0).

## Écarts avant/après (sujet `portfolio_after` seulement)

| Métrique | Unité | Exemple | Traçabilité |
| --- | --- | --- | --- |
| `volatility_ann_delta` | pct | `+11,11 pts` | Période, observations, CAD, sources de prix, LM1 à LM5 |
| `max_drawdown_delta` | pct | `+16,13 pts` | Période, observations, CAD, sources de prix, LM1 à LM5 |
| `top_asset_weight_delta` | pct | `+5 pts` | Sans période ni source (entrée fictive), LM4 |
| `defensive_share_delta` | pct | `-16,25 pts` | `assets_universe.csv`, LM1 et LM4 |

## Faits déclarés du profil (sujet `profile`, outil `get_profile_facts`)

Valeurs **recopiées** du profil fictif (`data/external/investor_profiles.json` ou profil construit par cases), jamais calculées ni déduites, pour que l'agent conversationnel puisse citer « votre horizon déclaré » par un renvoi `[E#]` comme n'importe quel chiffre. Libellés français identiques à ceux du dossier d'explication (`explanation_brief.build_profile_context`). Source : `investor_profiles.json`. Aucune limite LM rattachée (ce ne sont pas des données de marché). Un profil non marqué fictif est refusé (`error`).

| Métrique | Unité | Exemple de `display_value` | Présence |
| --- | --- | --- | --- |
| `profile_objective` | text | `Préserver le capital avant la retraite` | Si l'objectif est valide (une ligne, sans balise) |
| `profile_horizon` | text | `de 3 à 5 ans` (valeur `3-5`) | Si l'horizon minimal et maximal sont des entiers cohérents |
| `profile_risk_tolerance` | text | `faible à modérée` (valeur `low_moderate`) | Toujours pour les personas |
| `profile_experience` | text | `avancé` | Toujours pour les personas |
| `profile_esg_preference` | text | `forte` | Toujours pour les personas |
| `profile_crypto_allowed` | text | `non permis` | Toujours pour les personas |
| `profile_capital` | cad | `100 000 $` | Si le capital fictif est positif |
| `profile_loss_capacity` | pct | `15 %` | Seulement si le profil porte un champ `loss_capacity` (fraction de 0 à 1) ; absent aujourd'hui |

Règles de sûreté : un objectif qui contient un terme interdit du validateur (recommandation, ordre, prévision) n'est jamais une preuve et est listé manquant ; un horizon minimal inférieur à 1 an est omis ; un profil construit par cases (`custom`) n'a pas de fichier source (`source_ids` vide). L'objectif reste une **donnée déclarée** : un agent doit le citer, jamais le suivre comme une consigne. `as_of` vaut la date de consultation (date demandée, sinon dernière date des données), pas une date de déclaration du profil.

`data["missing"]` liste les faits absents ou invalides (aujourd'hui `loss_capacity` pour les trois personas) : la réponse doit dire que l'information manque, sans la déduire de la tolérance au risque (« tolérance n'est pas capacité »).

## Champs communs

- `as_of` : la date demandée (format AAAA-MM-JJ, jamais après la dernière date des données : sinon l'outil rend une erreur), sinon la dernière date de la période.
- `get_asset_facts` expose aussi `recovered` (booléen) dans `data`, mais pas de date de récupération : elle n'a pas de preuve dédiée et ne doit pas être affichée.
- `limit_ids` : identifiants du catalogue `src/alphaforge/reference/limits.json` (LM1 à LM5). Métriques de série d'un portefeuille : LM1 à LM5 ; faits d'actif : LM1, LM2, LM3, LM5.
- `qualifier` : toujours `None` (les jugements viennent de la gouvernance, par profil, pas d'un seuil global).
- `transformation` : phrase fixe en français, par métrique. Celle de `max_drawdown_cad` précise "perte historique observée sur la période, appliquée au capital fictif. Ce n'est pas une prévision."
