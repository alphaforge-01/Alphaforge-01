#!/usr/bin/env bash
# Lance l'interface AlphaForge en mode bedrock, depuis le terminal qui contient
# les identifiants temporaires de l'atelier.
#
# Usage, depuis n'importe quel dossier :
#     bash scripts/run_app_bedrock.sh
#
# Le script :
#   1. charge le fichier .env de la racine s'il existe (réglages ALPHAFORGE_*, ignoré par Git) ;
#   2. vérifie que les réglages attendus sont définis (affiche les noms, jamais les valeurs) ;
#   3. vérifie la connexion AWS avec boto3 (affiche seulement le nom du rôle, sans numéro de compte) ;
#   4. démarre Streamlit sur 127.0.0.1.
# Les identifiants AWS ne sont jamais écrits ni affichés par ce script.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
STREAMLIT="$PROJECT_ROOT/.venv/bin/streamlit"
PORT="${PORT:-8501}"

cd "$PROJECT_ROOT"

if [[ ! -x "$PYTHON" || ! -x "$STREAMLIT" ]]; then
    echo "Environnement Python introuvable (.venv). Créez-le d'abord : python -m venv .venv puis .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# 1. Réglages de l'application
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
    echo "Réglages chargés depuis .env"
else
    echo "Pas de fichier .env : les réglages doivent déjà être exportés dans ce terminal."
fi

export AWS_REGION="${AWS_REGION:-us-east-1}"
export ALPHAFORGE_MODE="${ALPHAFORGE_MODE:-bedrock}"

# 2. Réglages attendus (noms seulement)
missing=()
for name in ALPHAFORGE_ANALYST_MODEL_ID ALPHAFORGE_EXPLAINER_MODEL_ID \
            ALPHAFORGE_GUARDRAIL_ID ALPHAFORGE_GUARDRAIL_VERSION ALPHAFORGE_TRACE_BUCKET; do
    if [[ -z "${!name:-}" ]]; then
        missing+=("$name")
    fi
done
if [[ "$AWS_REGION" != "us-east-1" ]]; then
    echo "Attention : AWS_REGION vaut $AWS_REGION, l'atelier utilise us-east-1."
fi
if (( ${#missing[@]} > 0 )); then
    echo "Réglages manquants : ${missing[*]}"
    echo "Ajoutez-les dans .env (voir .env.example) puis relancez. Sans eux, l'application revient au mode hors ligne."
    exit 1
fi
echo "Réglages présents : modèles, garde-fou, compartiment des traces (mode $ALPHAFORGE_MODE, région $AWS_REGION)."

# 3. Connexion AWS
missing_credentials=()
for name in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN; do
    if [[ -z "${!name:-}" ]]; then
        missing_credentials+=("$name")
    fi
done
if (( ${#missing_credentials[@]} > 0 )); then
    echo "Identifiants temporaires absents de ce terminal : ${missing_credentials[*]}"
    echo "Copiez le bloc 'export' de la page Workshop Studio dans ce terminal (jamais dans un fichier du dépôt), puis relancez."
    exit 1
fi

if ! role="$("$PYTHON" - <<'PY'
import sys
import boto3
from botocore.exceptions import BotoCoreError, ClientError

try:
    arn = boto3.client("sts", region_name="us-east-1").get_caller_identity()["Arn"]
except ClientError as error:
    code = error.response.get("Error", {}).get("Code", "inconnue")
    print(f"refus AWS ({code})", file=sys.stderr)
    sys.exit(1)
except BotoCoreError as error:
    print(f"connexion impossible ({type(error).__name__})", file=sys.stderr)
    sys.exit(1)
# Seul le nom du rôle est affiché : jamais le numéro de compte.
print(arn.split(":")[-1].split("/")[1] if "/" in arn else "rôle non affiché")
PY
)"; then
    echo "Connexion AWS refusée. Si l'erreur parle de ExpiredToken ou InvalidClientTokenId, récupérez de nouveaux identifiants sur Workshop Studio."
    exit 1
fi
echo "Connexion AWS valide (rôle : $role)."

# 4. Lancement
echo "Démarrage de l'interface sur http://127.0.0.1:$PORT/ (Ctrl+C pour arrêter)"
exec "$STREAMLIT" run app/streamlit_app.py --server.address 127.0.0.1 --server.port "$PORT"
