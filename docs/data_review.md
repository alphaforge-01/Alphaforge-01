# Données du projet AlphaForge AI

Synthèse en français de l'analyse du jeu fourni et des sources publiques évaluées le **14 novembre 2026**. Ce document centralise l'inventaire, les résultats du contrôle local, les trois compléments recommandés, leurs accès et leurs limites. Les observations externes correspondent aux versions consultées à cette date; elles ne prouvent pas une disponibilité permanente.

Les données brutes du starter restent dans [data/raw/](../data/raw/). Les chiffres ci-dessous décrivent cette copie précise. Les compléments recommandés n'ont pas été intégrés au jeu de départ.

> **Note de l'équipe.** Revue rédigée par Godwin, intégrée au dépôt avec les chemins mis à jour (le starter est maintenant dans `data/raw/` et `scripts/`). Ce qui s'écarte des décisions de l'équipe :
>
> - le périmètre du MVP est fixé par `docs/sprint_plan.md` : compositions de FNB et EDGAR sont hors périmètre ; WBA est la piste retenue pour l'ESG de Mateo si le P2 est atteint (social et éthique seulement) ;
> - les scénarios conditionnels ont été écartés par l'équipe ;
> - la structure `data/metadata/` proposée en section 12 n'est pas utilisée : les sources ajoutées sont documentées dans `data/external/sources.md` (règle 5 de `CLAUDE.md`).
>
> Conventions retenues pour le flux A (décision d'équipe du 14 novembre) : taux de change du même jour, calendrier commun limité aux jours où la TSX et les marchés américains sont tous deux ouverts (aucun prix inventé), crypto ramenée à ce calendrier et annualisée sur 252 jours, portefeuille à poids fixes rééquilibré chaque jour, devise de référence CAD.

## 1. Conclusion de l'analyse

**Conserver le starter comme base quantitative.** Il permet déjà de calculer les rendements historiques, la volatilité, les baisses maximales, les corrélations et l'effet du change sur un portefeuille fictif, après préparation des calendriers et devises.

Les enrichissements les plus utiles portent sur les explications et la cohérence du portefeuille :

1. **Compositions et caractéristiques des FNB chez leurs émetteurs** : comprendre les expositions indirectes, les chevauchements, les frais et la sensibilité obligataire.
2. **SEC EDGAR Company Facts et Submissions** : examiner les fondamentaux et retrouver les publications qui soutiennent une analyse.
3. **World Benchmarking Alliance, Social Benchmark / Core Social Indicators** : intégrer des critères sociaux et éthiques documentés, notamment pour Mateo.

Cette sélection est une recommandation pour l'équipe. L'énoncé n'impose ni ces sources ni les actifs du starter.

## 2. Cadre du Datathon à respecter

L'énoncé officiel en français (hors du dépôt, dans le dossier parent : `Datathon - Case Officiel 2026 FR.pdf`) constitue la référence :

- Utiliser des données financières publiques pour éclairer une décision et expliquer le résultat selon un profil fictif.
- Documenter les sources, dates, traitements, hypothèses, limites et conditions d'utilisation.
- Distinguer les faits observés des hypothèses et scénarios fictifs.
- Éviter toute information qui n'était pas encore accessible à la date d'une simulation historique.
- La page 18 ne demande pas de prédire les rendements futurs à partir du passé. Les scénarios conditionnels permettent d'éprouver une allocation sans affirmer qu'ils vont se réaliser.
- Aucun portefeuille initial, montant de capital ou titre détenu n'est attribué à Amira, Mateo ou Robert dans leurs fiches. Tout portefeuille de départ ajouté par l'équipe doit être présenté comme fictif.
- Aucune transaction réelle, donnée bancaire confidentielle ou donnée personnelle réelle dans le prototype.

## 3. Inventaire du starter

### Période, provenance et taille

- **Période principale des prix et du change :** du 12 novembre 2021 au 12 novembre 2026 inclus.
- **Date d'extraction déclarée :** 13 novembre 2026.
- **Univers :** 31 actifs, dont 13 cotés en CAD et 18 en USD.
- **Sources principales :** Yahoo Finance via `yfinance`, Banque du Canada via Valet, FRED.
- **Période choisie par les organisateurs :** cinq ans pour inclure 2022, année de baisse simultanée des actions et des obligations.

| Fichier local | Lignes de données | Contenu |
| --- | ---: | --- |
| [assets_universe.csv](../data/raw/assets_universe.csv) | 31 | Identité des actifs, classe, marché, devise et secteur simplifié. |
| [prices_daily.csv](../data/raw/prices_daily.csv) | 40 049 | Prix quotidiens OHLC, clôture ajustée et volume. |
| [corporate_actions.csv](../data/raw/corporate_actions.csv) | 658 | 651 dividendes et 7 événements classés comme fractionnements. |
| [fx_usdcad_daily.csv](../data/raw/fx_usdcad_daily.csv) | 1 245 | Taux USD/CAD et inverse arrondi. |
| [macro_rates.csv](../data/raw/macro_rates.csv) | 8 281 | Neuf séries canadiennes et américaines, quotidiennes ou mensuelles. |
| [sources_metadata.csv](../data/raw/sources_metadata.csv) | 6 | Provenance, date, fréquence, traitements, limites et conditions des fichiers. Deux lignes décrivent les deux fournisseurs du fichier macro. |
| [data_quality_warnings.txt](../data/raw/data_quality_warnings.txt) | Sans objet | Résultat des contrôles du script organisateur : « No warnings » pour cette version. |
| [build_dataset.py](../scripts/build_dataset.py) | Sans objet | Script de récupération et reconstruction du jeu. |
| [README.md](../data/raw/README.md) | Sans objet | Documentation bilingue, conventions et précautions des organisateurs. |

### Schémas des fichiers

| Fichier | Colonnes exactes |
| --- | --- |
| `assets_universe.csv` | `asset_id`, `ticker`, `name`, `asset_class`, `market`, `currency`, `sector` |
| `prices_daily.csv` | `date`, `ticker`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `currency` |
| `corporate_actions.csv` | `ex_date`, `ticker`, `action`, `value`, `unit` |
| `fx_usdcad_daily.csv` | `date`, `usdcad`, `cadusd` |
| `macro_rates.csv` | `date`, `series_id`, `value`, `unit`, `frequency`, `label`, `source` |
| `sources_metadata.csv` | `file`, `content`, `source`, `source_url`, `retrieved_on`, `coverage`, `frequency`, `processing`, `limitations`, `terms_of_use` |

Les clés naturelles sont `(date, ticker)` pour les prix et `(date, series_id)` pour les séries macro. Le change se joint sur la date selon une convention temporelle explicite. `ticker` relie les actifs aux prix et aux opérations sur titres.

## 4. Les 31 actifs disponibles

Les noms, secteurs et catégories viennent du fichier des organisateurs. Ils ne constituent pas une appréciation de la qualité ou de l'adéquation d'un placement.

| Groupe | Nombre | Symboles |
| --- | ---: | --- |
| Actions canadiennes | 10 | `RY.TO`, `TD.TO`, `MFC.TO`, `ENB.TO`, `CNQ.TO`, `CNR.TO`, `FTS.TO`, `ATD.TO`, `SHOP.TO`, `CSU.TO` |
| Actions américaines | 10 | `AAPL`, `MSFT`, `NVDA`, `GOOGL`, `AMZN`, `TSLA`, `JPM`, `JNJ`, `PG`, `XOM` |
| FNB d'actions | 4 | `XIU.TO`, `SPY`, `QQQ`, `ESGV` |
| FNB obligataires | 4 | `XBB.TO`, `ZST.TO`, `AGG`, `TLT` |
| FNB lié à l'or | 1 | `GLD` |
| Cryptoactifs | 2 | `BTC-USD`, `ETH-USD` |

### Expositions des FNB indiquées par le starter

| Symbole | Exposition décrite |
| --- | --- |
| `XIU.TO` | Actions canadiennes, indice S&P/TSX 60. |
| `SPY` | Actions américaines, indice S&P 500. |
| `QQQ` | Nasdaq-100, exposition importante aux grandes sociétés de croissance et technologiques. |
| `ESGV` | Actions américaines avec filtrage ESG; le nom ne suffit pas à valider les préférences de Mateo. |
| `XBB.TO` | Obligations canadiennes de marché large. |
| `ZST.TO` | Obligations à échéance très courte. |
| `AGG` | Obligations américaines de marché large. |
| `TLT` | Obligations du Trésor américain à longue échéance. |
| `GLD` | Or. |

Les 20 actions couvrent notamment la technologie, la finance, l'énergie, la consommation, l'industrie, les services publics, la communication et la santé. Cet univers est centré sur l'Amérique du Nord; il ne fournit pas une couverture complète des actions internationales ou de toutes les classes d'actifs.

## 5. Les neuf séries macroéconomiques

Les dates ci-dessous sont les dates d'observation présentes dans les CSV, pas une preuve des dates auxquelles les valeurs étaient publiquement connues.

| Identifiant | Description | Source | Observations | Première date | Dernière date |
| --- | --- | --- | ---: | --- | --- |
| `V39079` | Taux cible du financement à un jour au Canada. | Banque du Canada | 1 293 | 2021-11-12 | 2026-11-12 |
| `BD.CDN.2YR.DQ.YLD` | Rendement obligataire du gouvernement canadien à 2 ans. | Banque du Canada | 1 245 | 2021-11-12 | 2026-11-12 |
| `BD.CDN.10YR.DQ.YLD` | Rendement obligataire du gouvernement canadien à 10 ans. | Banque du Canada | 1 245 | 2021-11-12 | 2026-11-12 |
| `STATIC_TOTALCPICHANGE` | Variation annuelle de l'IPC canadien, en pourcentage. | Banque du Canada | 58 | 2021-12-01 | 2026-09-01 |
| `DFF` | Taux effectif des fonds fédéraux américains. | FRED | 1 826 | 2021-11-12 | 2026-11-11 |
| `DGS2` | Rendement du Trésor américain à 2 ans. | FRED | 1 248 | 2021-11-12 | 2026-11-10 |
| `DGS10` | Rendement du Trésor américain à 10 ans. | FRED | 1 248 | 2021-11-12 | 2026-11-10 |
| `CPIAUCSL` | Niveau de l'indice des prix américain, corrigé des variations saisonnières. | FRED | 59 | 2021-11-01 | 2026-10-01 |
| `UNRATE` | Taux de chômage américain, corrigé des variations saisonnières. | FRED | 59 | 2021-11-01 | 2026-10-01 |

Les séries n'ont donc pas toutes la même période effective ni la même fréquence. L'IPC américain est un **indice**, tandis que la série canadienne fournie est déjà une **variation annuelle en pourcentage** : elles ne sont pas directement interchangeables.

## 6. Qualité et préparation nécessaires

### Résultats du contrôle structurel local

- Aucune cellule manquante dans les cinq CSV de données : univers, prix, opérations sur titres, change et macro.
- Aucun doublon de prix pour `(ticker, date)`; les 31 actifs de l'univers sont présents.
- Aucune incohérence entre la devise d'un prix et celle de l'univers.
- Aucun prix OHLC ou ajusté non positif; aucune incohérence de fourchette OHLC détectée.
- Aucun doublon de taux de change par date ou de série macro par date.
- 1 255 observations par action/FNB et 1 827 par cryptoactif.
- Les valeurs `n/a` de certaines métadonnées correspondent à des champs non applicables.

Ces contrôles valident la structure de la copie fournie. Ils ne certifient pas l'exactitude de chaque observation auprès des fournisseurs ni l'exhaustivité de tous les événements.

### Particularités et précautions

| Point | Conséquence pour l'analyse |
| --- | --- |
| `adj_close` est ajusté pour dividendes et fractionnements. | L'utiliser pour les rendements selon la convention du fournisseur. Ne pas ajouter une seconde fois les dividendes déjà pris en compte. |
| `close` est déjà ajusté pour les fractionnements selon le README. | Ne pas appliquer les ratios de fractionnement une seconde fois. |
| Les prix ajustés sont recalculés rétrospectivement. | Garder la copie de départ et sa date d'extraction pour reproduire les résultats. |
| Prix dans leur devise de cotation. | Choisir une devise de référence et convertir de façon cohérente les valeurs et rendements. |
| `usdcad` signifie CAD pour 1 USD; `cadusd` est son inverse arrondi. | Un prix en USD multiplié par `usdcad` donne une valeur en CAD. |
| Le change Banque du Canada est publié autour de 16 h 30, heure de l'Est. | Une jointure sur la date seule peut utiliser un taux inconnu au moment d'une décision prise plus tôt. Documenter l'heure d'évaluation et la disponibilité des données. |
| Calendriers TSX, États-Unis et Banque du Canada différents. | Définir le calendrier, la politique de données absentes et l'utilisation éventuelle du dernier taux connu. Ne jamais utiliser un taux futur. |
| Cryptoactifs négociés 7 jours sur 7, lignes en journées UTC. | Ne pas les traiter automatiquement comme des clôtures boursières nord-américaines. Adapter les conventions d'annualisation. |
| Une ligne ZST.TO présente un volume nul le 6 juillet 2022. | La signaler; ne pas supprimer automatiquement un prix pour ce seul motif sans justification. |
| CNQ.TO a un événement « split » de 1,021 le 22 août 2022 et un dividende de 0,75 CAD. | Le README soupçonne une distribution spéciale. Vérifier la source de l'émetteur avant d'interpréter cet événement. |
| Macro mensuelle datée au mois de référence, valeurs FRED révisées. | Rechercher les dates de publication et, si nécessaire, les valeurs disponibles à l'époque. Un simple décalage ne supprime pas le biais de révision. |
| Univers sélectionné en 2026. | Signaler le biais de sélection/survivance dans tout résultat historique. |

Le script `build_dataset.py` reconstruit et écrase cinq CSV ainsi que le fichier d'avertissements. Il ne régénère pas le README ni les métadonnées manuelles. Une nouvelle exécution peut modifier les résultats historiques.

## 7. Ce que le starter permet et ce qui manque

| Question du projet | Avec le starter seul | Complément utile |
| --- | --- | --- |
| Comment un portefeuille fictif s'est-il comporté historiquement ? | Oui, après choix des poids, périodes, devises et conventions. | Aucun ajout indispensable pour un premier prototype. |
| Quels actifs ont fluctué ensemble ? | Corrélations historiques calculables. | Composition des FNB pour expliquer les facteurs communs. |
| Quel effet le CAD/USD a-t-il eu ? | Calculable avec une jointure temporelle adaptée. | Métadonnées de couverture de change des fonds si pertinentes. |
| Le portefeuille contient-il indirectement les mêmes entreprises plusieurs fois ? | Pas quantifiable précisément avec les seules catégories de l'univers. | Compositions datées des FNB. |
| Pourquoi un fonds obligataire est-il sensible aux taux ? | L'historique montre les variations, sans décrire toutes leurs causes. | Duration, maturité, qualité de crédit et composition. |
| L'entreprise est-elle rentable et quelle est sa situation financière ? | Non : les prix ne sont pas des états financiers. | SEC EDGAR, rapports des émetteurs, SEDAR+. |
| Les préférences ESG de Mateo sont-elles respectées ? | Non vérifiable avec les seules données fournies. | Indicateurs documentés et preuves adaptées à chaque critère. |
| Quel portefeuille est déjà détenu par un persona ? | Aucun portefeuille initial n'est fourni. | Hypothèses fictives créées et identifiées par l'équipe. |
| Quel rendement futur est certain ? | Aucun jeu historique ne permet de l'établir. | La prédiction de rendement n'est pas demandée par le défi. |

Le prix, la volatilité historique ou l'étiquette « obligations » ne suffisent pas à établir l'adéquation d'un actif à Robert. De même, le nom `ESGV` ne prouve pas une absence de controverses pour Mateo.

## 8. Complément recommandé no 1 : compositions et caractéristiques des FNB

### Source et accès

**Famille de données :** fichiers des positions et fiches produits des émetteurs officiels, avec iShares comme premier fournisseur à explorer. Cette famille de sources est mentionnée dans l'atelier AWS.

- [XBB : page officielle, positions et caractéristiques](https://www.blackrock.com/ca/investors/en/products/239493/ishares-canadian-universe-bond-index-etf)
- [XBB : export CSV des positions](https://www.blackrock.com/ca/investors/en/products/239493/ishares-canadian-universe-bond-index-etf/1464253357814.ajax?dataType=fund&fileName=XBB_holdings&fileType=csv)
- [TLT : page officielle iShares](https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf)

Le lien CSV est un export dynamique : vérifier la date indiquée dans le fichier après téléchargement. Ce n'est pas une archive immuable du 12 novembre.

### Vérification effectuée

Un export XBB daté du **12 novembre 2026** a été téléchargé et lu. Ses colonnes comprennent `Ticker`, `Name`, `Sector`, `Asset Class`, `Market Value`, `Weight (%)`, `Notional Value`, `Shares`, `Par Value`, `Price`, `Location`, `Exchange`, `Currency`, `Duration`, `FX Rate`, `Maturity`, `Coupon (%)`, `Market Currency` et `Effective Date`.

L'export contient des lignes de métadonnées avant l'en-tête et une ligne de fin sans position. Ses pondérations affichées sont arrondies : ne pas supposer une somme exactement égale à 100 % ni normaliser silencieusement un écart. Les champs peuvent varier selon le fonds et l'émetteur.

### Apport au projet

- **Amira :** vérifier la concentration et les expositions communes entre ses fonds et ses actions détenues directement.
- **Robert :** expliquer la sensibilité aux taux et la nature des actifs obligataires.
- **Mateo :** identifier les entreprises sous-jacentes avant d'appliquer ses critères.

iShares est l'émetteur de `XIU.TO`, `XBB.TO`, `AGG` et `TLT` du starter. Pour `SPY`, `QQQ`, `ESGV`, `ZST.TO` et `GLD`, utiliser les documents de leurs émetteurs respectifs plutôt que de supposer une couverture iShares.

### Limites et exploitation

Les fichiers sont publiquement consultables, mais cette accessibilité ne garantit pas un droit illimité de redistribution. Une composition actuelle ne reconstitue pas celle de 2021. Conserver la date des positions et la date de téléchargement.

La jointure requiert le symbole du fonds et un identifiant de chaque position sous-jacente. Un symbole obligataire peut désigner plusieurs émissions : ne pas traiter `Ticker` comme une clé unique de titre. Utiliser l'ISIN/CUSIP s'il est disponible et, sinon, une identification comprenant émetteur, échéance et coupon. Les métadonnées et identifiants disponibles dépendent de l'export choisi.

**Priorité recommandée : première intégration pour une analyse de portefeuille.**

## 9. Complément recommandé no 2 : SEC EDGAR

### Source et accès

**Jeux de données :** `Company Facts` pour les faits financiers XBRL; `Submissions` pour l'historique et les références des dépôts. C'est une source recommandée dans l'atelier AWS.

- [Documentation officielle des API de lecture EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [Ressources développeurs et règles d'accès](https://www.sec.gov/about/developer-resources)
- [Recherche publique des dépôts](https://www.sec.gov/search-filings)

Les API de lecture sont publiques, en JSON, sans clé. Les modèles d'adresses documentés sont :

```text
https://data.sec.gov/submissions/CIK##########.json
https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
```

Remplacer `##########` par le CIK de l'entreprise sur dix chiffres. Le CIK identifie l'émetteur; établir une table de correspondance avec les symboles du starter. Ne pas confondre ces API publiques de consultation avec les API EDGAR destinées au dépôt de documents par les déclarants.

### Données et usages

Selon l'émetteur et les concepts publiés, on peut retrouver revenus, bénéfices, actifs, passifs et flux de trésorerie, accompagnés de périodes et références de dépôt. Les facteurs de risque textuels se recherchent dans les rapports eux-mêmes; ils ne constituent pas un champ universel de `Company Facts`.

Pour un premier enrichissement, sélectionner quelques sociétés américaines du starter et des indicateurs comparables. Robert peut ainsi comparer une opportunité à des éléments financiers publiés; Amira peut confronter un récit de croissance aux résultats disponibles.

### Limites, dates et conditions

- Ne pas mélanger les données annuelles, trimestrielles et cumulées.
- Vérifier unités, dates de début/fin, formulaires, concepts et retraitements.
- Pour une simulation, filtrer selon la date de dépôt accessible à l'époque et conserver la référence du dépôt retenu.
- Les valeurs d'entreprises différentes ne sont pas automatiquement comparables pour tous les concepts.
- Les entreprises canadiennes présentes à la SEC peuvent publier selon d'autres formulaires ou taxonomies, notamment IFRS. La couverture ne doit pas être supposée pour les dix actions canadiennes.
- Les règles SEC imposent un accès automatisé identifié et au maximum **10 requêtes par seconde**. Télécharger seulement le nécessaire et mettre en cache.

**Vérification réalisée :** documentation officielle d'accès et de structure; aucun jeu complet SEC n'a été importé dans le projet.

**Priorité recommandée : deuxième intégration, sur un petit nombre d'entreprises.**

## 10. Complément recommandé no 3 : World Benchmarking Alliance

### Source et accès

**Jeu ciblé :** Social Benchmark / Core Social Indicators (CSI), pour les dimensions sociales et éthiques. Cette source a été trouvée en complément de la liste de l'atelier AWS.

- [Présentation du Social Benchmark](https://www.worldbenchmarkingalliance.org/benchmark/social-benchmark)
- [Portail Data Explorer](https://data.worldbenchmarkingalliance.org/)
- [Guide des téléchargements et de l'inscription](https://www.worldbenchmarkingalliance.org/documentation/user-guide)
- [Documentation de l'API](https://www.worldbenchmarkingalliance.org/documentation/api-specification)
- [Conditions et licence](https://www.worldbenchmarkingalliance.org/disclaimer)
- [Présentation du fichier historique publié en avril 2024](https://www.worldbenchmarkingalliance.org/latest/core-social-indicator-assessments-2000-largest-and-most-influential-companies-globally)
- [Téléchargement du fichier historique inspecté](https://www.worldbenchmarkingalliance.org/sites/default/files/2026-07/WBA-Latest-CSI-Assessments-2021-23-external-dataset-April-2024-version-2%20%281%29.xlsx)

Le chemin d'hébergement du dernier fichier comprend `2026-07`, mais son contenu correspond à la version d'avril 2024 et à des évaluations de 2021-2023. Ne pas interpréter le chemin du fichier comme l'année d'évaluation.

### Vérification sur le fichier historique

Le fichier réellement téléchargé contient **1 728 entreprises distinctes** et **18 indicateurs**, répartis en trois domaines : droits humains, travail décent et conduite éthique. Les années d'évaluation se répartissent en 51 entreprises pour 2021, 642 pour 2022 et 1 035 pour 2023.

Les cinq feuilles comprennent l'introduction, la méthodologie, les scores par indicateur, les scores par élément et l'évaluation détaillée. Cette dernière contient notamment explication, preuve, référence et lien documentaire. Le total historique est noté sur 20 : ne pas le confondre avec une autre édition ou un affichage sur 100.

Des correspondances au niveau de l'entreprise ont été identifiées pour **13 des 20 actions du starter** :

| Symbole du starter | Entreprise reconnue dans le fichier historique |
| --- | --- |
| `ATD.TO` | Couche-Tard |
| `GOOGL` | Alphabet |
| `AMZN` | Amazon |
| `AAPL` | Apple |
| `CNQ.TO` | Canadian Natural Resources |
| `XOM` | ExxonMobil |
| `JNJ` | Johnson & Johnson |
| `MFC.TO` | Manulife |
| `MSFT` | Microsoft |
| `NVDA` | Nvidia |
| `RY.TO` | Royal Bank of Canada |
| `TSLA` | Tesla |
| `JPM` | JP Morgan Chase |

Cette couverture concerne l'échantillon historique examiné, pas une garantie pour l'édition actuelle ni une correspondance automatique entre classes d'actions. Elle ne fournit pas une note aux FNB ou aux cryptos.

### Apport et limites pour Mateo

Les indicateurs permettent d'expliquer les critères sociaux documentés et les preuves associées. **Ils ne prouvent pas qu'une entreprise est exempte de controverses.** Ils ne couvrent pas à eux seuls toutes les dimensions environnementales et de gouvernance recherchées par Mateo.

Une évaluation fondée sur des publications ne mesure pas parfaitement toutes les pratiques réelles. Une absence de donnée n'est pas une bonne note ni une preuve de faute. Les évaluations 2021-2023 ne doivent pas être présentées comme l'état certain de l'entreprise en 2026.

Le portail actuel annonce environ 2 000 entreprises et des exports ZIP/CSV après inscription gratuite. Les données détaillées actuelles n'ont pas été téléchargées derrière ce compte. L'accès API nécessite une approbation pouvant prendre plusieurs jours : pour le Datathon, privilégier un téléchargement manuel d'une édition publiée et datée. Les publications et benchmarks WBA sont annoncés sous **CC BY 4.0**, avec attribution.

Pour la jointure, conserver les identifiants WBA, les ISIN lorsqu'ils existent et une table de correspondance d'émetteurs vérifiée. Alphabet peut être représenté par une autre classe d'actions. Ne pas associer `CSU.TO` (Constellation Software) à Constellation Brands ou Constellation Energy sur la seule ressemblance de nom.

**Priorité recommandée : troisième intégration, ou plus tôt si Mateo et les critères sociaux constituent le cas central.**

## 11. Autres sources étudiées ou présentes dans l'atelier AWS

| Source | Accès / rôle | Avis pour ce projet |
| --- | --- | --- |
| [Banque du Canada, Valet](https://www.bankofcanada.ca/valet/docs) | Séries de taux et de change publiques. | Déjà largement représentée dans le starter. Ajouter des séries seulement si elles répondent à une question précise. |
| [FRED](https://fred.stlouisfed.org/) | Macroéconomie américaine; conditions propres à chaque série. | Déjà représenté. Accumuler davantage de séries ne résout pas les lacunes sur les fonds, entreprises et préférences ESG. |
| [ALFRED](https://fred.stlouisfed.org/docs/api/fred/alfred.html) | Versions historiques des données FRED, avec périodes de disponibilité et révisions. | Pertinent si la simulation macro avec les données connues à l'époque devient centrale. Ce n'est pas un ajout indispensable pour un simple diagnostic de portefeuille. |
| [Statistique Canada](https://www.statcan.gc.ca/) | Indicateurs canadiens et dates de diffusion. | Complément éventuel au contexte canadien, après définition du besoin. Source citée dans l'atelier; aucune table supplémentaire n'a été auditée ici. |
| [SEDAR+](https://www.sedarplus.ca/) | Rapports et dépôts des émetteurs canadiens. | Utile pour les titres canadiens et les preuves documentaires. Vérifier les conditions du site avant toute collecte automatisée; ne pas supposer une API comparable à EDGAR. |
| Sites de relations investisseurs et rapports de durabilité | Documents des entreprises, datés. | Bon complément pour vérifier une affirmation précise; ce sont des déclarations des émetteurs à interpréter comme telles. |
| [GDELT dans le registre AWS](https://registry.opendata.aws/gdelt/) | Copie publique dans S3. | La fiche précise qu'elle n'est plus actualisée. Non retenue dans les trois priorités pour une analyse d'actualité. Cela ne signifie pas que tout le projet GDELT est arrêté. |
| [Violation Tracker Global](https://violationtrackerglobal.goodjobsfirst.org/pages/user-guide) | Consultation gratuite des cas; exports payants. | Potentiellement utile pour examiner une controverse, mais pas un jeu complet gratuitement téléchargeable. Couverture et absence d'événements doivent être interprétées avec prudence. |
| Jeux Kaggle ou notes ESG commerciales copiées ailleurs | Conditions, méthodes et dates variables. | Ne pas retenir sans provenance, licence, méthodologie et millésime vérifiables. Aucun jeu Kaggle précis n'a été validé dans cette revue. |

Page de l'atelier de référence : [Données financières publiques](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/50-datasets). L'accès peut nécessiter la connexion à l'événement. La synthèse des autres règles AWS est dans `AWS_WORKSHOP.md` (hors du dépôt).

## 12. Organisation et traçabilité recommandées

Pour tout ajout, enregistrer la date d'observation, la date de publication connue, la date de téléchargement, l'URL exacte, la licence applicable, l'unité et la devise. Conserver aussi les transformations effectuées et la version de la méthode.

Séparer les données téléchargées des données transformées. Une structure possible, non encore créée pour ces compléments :

```text
data/
  raw/          # Copies originales avec provenance et dates
  processed/    # Données nettoyées, jointures et indicateurs
  metadata/     # Sources, licences, correspondances d'identifiants
```

Avant de publier des données dans un dépôt public, vérifier les droits de redistribution. Lorsque ceux-ci sont limités, conserver le script et les instructions de récupération plutôt que republier les fichiers.

Les conditions générales Workshop Studio et les pages du Datathon ne formulent pas de la même manière les matériaux financiers autorisés. Comme indiqué dans `AWS_WORKSHOP.md` (hors du dépôt), faire confirmer par un mentor les fichiers publics utilisables dans le compte de l'événement avant leur importation. Cette revue de données n'a créé aucune ressource AWS et n'a envoyé aucun fichier du projet dans ce compte.

## 13. Ordre de travail proposé

1. Définir la décision à éclairer et les profils fictifs retenus pour la démonstration.
2. Préparer le starter : calendrier, devise, rendements ajustés, contrôles et hypothèses.
3. Intégrer quelques compositions de FNB pour expliquer les expositions.
4. Ajouter des fondamentaux EDGAR pour les entreprises réellement analysées.
5. Ajouter des indicateurs WBA si les critères sociaux sont utilisés; signaler explicitement les entreprises non couvertes et les preuves manquantes.
6. Présenter les résultats avec leurs sources et tester des scénarios conditionnels. Ne pas présenter les performances passées comme une prévision garantie.

## 14. Documents du projet

- `AGENTS.md` (hors du dépôt) : contexte général, exigences et décisions à venir.
- `AWS_WORKSHOP.md` (hors du dépôt) : inventaire de l'atelier, accès AWS et limites du compte.
- [README du starter](../data/raw/README.md) : conventions originales des organisateurs.
- [Métadonnées du starter](../data/raw/sources_metadata.csv) : provenance et conditions déclarées pour chaque fichier.
- Énoncé officiel français (hors du dépôt, dans le dossier parent : `Datathon - Case Officiel 2026 FR.pdf`) : objectifs, personas et règles du défi.
