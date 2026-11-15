#!/bin/bash
# Controles mecaniques avant le depot final (regles 1, 2, 6 et 7 de CLAUDE.md). Lecture seule.
# Usage, depuis n'importe ou : bash scripts/final_checks.sh [reference-git]   (defaut : origin/main)
# Pour verifier aussi l'identifiant du garde-fou du compte, l'exporter avant : ALPHAFORGE_GUARDRAIL_ID (jamais ecrit ici).
# Rend 0 si tout est conforme, 1 sinon, 2 si la reference est introuvable. N'affiche jamais de valeur secrete :
# seulement des noms de fichiers.
cd "$(dirname "$0")/.." || exit 2
R="${1:-origin/main}"; FAIL=0
git fetch origin --prune >/dev/null 2>&1
check() { # nom, nombre de problemes, detail
  if [ "$2" -eq 0 ]; then printf "  OK      %s\n" "$1"; else printf "  ECHEC   %s (%s)\n" "$1" "$2"; FAIL=1; [ -n "$3" ] && printf "%s\n" "$3" | head -5 | sed 's/^/            /'; fi
}
git rev-parse --verify --quiet "$R" >/dev/null || { echo "Reference introuvable : $R"; exit 2; }
echo "Reference : $R ($(git rev-parse --short "$R"))"
SECRET='AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|bedrock-api-key-[A-Za-z0-9]{8}|aws_secret_access_key *= *[A-Za-z0-9/+]{20}|-----BEGIN [A-Z ]*PRIVATE KEY'
echo "Regle 6 : secrets"
f=$(git grep -lIE "$SECRET" "$R" -- . ':!tests' ':!src/alphaforge/bedrock_client.py' ':!scripts/check_aws_access.py' ':!scripts/setup_guardrail.py' ':!scripts/try_bedrock_run.py' ':!scripts/setup_trace_bucket.py' 2>/dev/null)
check "aucun secret dans l'arbre (hors fichiers de masquage et tests)" "$(printf '%s' "$f" | grep -c .)" "$f"
h=0; for c in $(git rev-list "$R"); do git grep -qIE "$SECRET" "$c" -- . ':!tests' ':!src/alphaforge/bedrock_client.py' ':!scripts' 2>/dev/null && h=$((h+1)); done
check "aucun secret dans l'historique de $R" "$h"
f=$(git ls-tree -r --name-only "$R" | grep -iE "(^|/)\.env$|\.pem$|\.key$|credentials|AWS_WORKSHOP|\.aws/")
check "aucun fichier sensible suivi" "$(printf '%s' "$f" | grep -c .)" "$f"
f=$(git grep -lIE "alphaforge-traces-[0-9a-f]{8}|arn:aws:[a-z0-9-]*:[a-z0-9-]*:[0-9]{12}" "$R" -- . ':!tests' 2>/dev/null)
check "aucun nom de compartiment ni ARN avec numero de compte dans le depot" "$(printf '%s' "$f" | grep -c .)" "$f"
if [ -n "$ALPHAFORGE_GUARDRAIL_ID" ]; then
  f=$(git grep -lIF -- "$ALPHAFORGE_GUARDRAIL_ID" "$R" 2>/dev/null)
  check "l'identifiant du garde-fou de ce compte n'est pas dans le depot" "$(printf '%s' "$f" | grep -c .)" "$f"
else
  echo "  IGNORE  identifiant du garde-fou (ALPHAFORGE_GUARDRAIL_ID absent de l'environnement)"
fi
echo "Regle 1 : ponctuation et emoji"
f=$(git grep -lIP "\x{2014}" "$R" -- . ':!data/raw' ':!*.csv' ':!*.pdf' ':!outputs/reports/demo_traces/*.json' 2>/dev/null)
check "aucun tiret cadratin" "$(printf '%s' "$f" | grep -c .)" "$f"
f=$(git grep -lIP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{1F000}-\x{1F2FF}]" "$R" -- . ':!*.pdf' ':!*.csv' 2>/dev/null)
check "aucun emoji" "$(printf '%s' "$f" | grep -c .)" "$f"
echo "Regle 2 : attributions"
n=$(git log "$R" --format=%B | grep -ciE "^co-authored-by|generated with \[?claude|noreply@anthropic")
check "aucune ligne Co-Authored-By ni attribution IA dans les messages" "$n"
echo "Regle 7 : donnees"
f=$(git ls-tree -r --name-only "$R" | grep -E "^data/(raw|external)/.*\.(csv|json|parquet)$" | while read p; do b=$(basename "$p"); git grep -q "$b" "$R" -- data/external/sources.md data/raw/sources_metadata.csv data/raw/README.md 2>/dev/null || echo "$p"; done)
check "chaque jeu de donnees est documente (sources.md, sources_metadata, README)" "$(printf '%s' "$f" | grep -c .)" "$f"
echo "Hygiene"
f=$(git ls-tree -r -l "$R" | awk '$4>5000000 {print $5}')
check "aucun fichier de plus de 5 Mo" "$(printf '%s' "$f" | grep -c .)" "$f"
f=$(git ls-tree -r --name-only "$R" | grep -E "^\.claude/worktrees|^outputs/reports/traces/")
check "ni worktrees ni traces locales suivis" "$(printf '%s' "$f" | grep -c .)" "$f"
echo; [ $FAIL -eq 0 ] && echo "RESULTAT : conforme" || echo "RESULTAT : des controles echouent"; exit $FAIL
