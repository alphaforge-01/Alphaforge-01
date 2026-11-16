# Déploiement de l'interface (Streamlit Community Cloud)

Simulation éducative : profils, portefeuilles et capitaux fictifs, aucun conseil, aucune transaction.

## Ce qui est déployé

L'application hébergée tourne en **mode hors ligne** : données réelles du dépôt, mêmes outils déterministes, même gouvernance, mêmes explications du code, **aucun appel AWS**. Le mode `offline` est le mode par défaut, donc aucun secret n'est nécessaire.

L'intégration AWS (Amazon Bedrock pour les deux agents et l'agent conversationnel, Bedrock Guardrails, Amazon S3 pour les traces) se démontre autrement : vidéo de démonstration, captures de la console dans `outputs/figures/`, traces dans `outputs/reports/` et mode `bedrock` en local avec `bash scripts/run_app_bedrock.sh`.

## Pourquoi aucune clé AWS dans les secrets de l'hébergeur

CLAUDE.md demande de placer les identifiants temporaires de l'atelier uniquement dans un terminal dédié, jamais dans un service tiers, un fichier ou le dépôt. Les secrets de Streamlit Community Cloud sont un service tiers. De plus, ces identifiants expirent au bout de quelques heures et le compte de l'atelier ferme le lundi 16 novembre à 13 h 59 : une application hébergée qui en dépendrait cesserait de fonctionner pour le jury. Un mode `bedrock` sans identifiants retombe sur le mode hors ligne, avec un message, comme dans le reste de l'interface.

## Paramètres à saisir dans Community Cloud

| Champ | Valeur |
| --- | --- |
| Repository | `alphaforge-01/Alphaforge-01` (organisation GitHub, dépôt privé : l'application GitHub de Streamlit doit avoir accès à l'organisation) |
| Branch | `chore/release-remise`, créée depuis `main` après la dernière fusion (voir « Gel ») |
| Main file path | `app/streamlit_app.py` |
| Python version | 3.12 (celle des essais : suite de tests verte et interface sans exception) |
| Secrets | aucun (facultatif : `ALPHAFORGE_MODE = "offline"`) |
| Visibilité | publique, le lien étant demandé sur Devpost |

Le dépôt peut rester privé : la visibilité du dépôt et celle de l'application se règlent séparément. Avant de rendre le dépôt public, confirmer auprès d'un mentor la redistribution des fichiers du jeu de départ (README, section Données).

## Gel

Community Cloud redéploie la branche choisie à chaque fusion. Aucune modification de l'outil n'est permise après le gel officiel (dimanche 15 novembre, 23 h 59). Pointer l'application sur `main` ferait donc évoluer l'outil remis. La procédure :

1. Après la dernière fusion de la remise, créer la branche : `git switch main && git pull && git switch -c chore/release-remise && git push -u origin chore/release-remise`.
2. Choisir cette branche dans Community Cloud. Ne plus rien y fusionner.
3. Lancer `bash scripts/final_checks.sh origin/chore/release-remise` avant la remise.

## Vérifications avant de publier

- Installation depuis `requirements.txt` seulement, sur Python 3.12 : `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- `python -m pytest -q -W error` : tous les tests passent.
- Ouvrir les pages et rejouer Robert, Amira et Mateo avec 25 % de TSLA, la création d'un profil fictif et une question dans le chat. Ouvrir l'application dans deux navigateurs pour vérifier que les sessions sont isolées.

## Retour arrière

Supprimer l'application dans Community Cloud, ou la redéployer sur la branche précédente. Aucune ressource AWS n'est créée par ce déploiement.
