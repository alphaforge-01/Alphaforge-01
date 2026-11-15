"""Création idempotente du compartiment S3 PRIVÉ des traces d'AlphaForge (US-16).

Le compartiment reçoit une trace JSON sans secret par analyse en mode
``bedrock`` (``src/alphaforge/trace_store.py``). Ce script le crée et le
garde conforme, sans jamais rien supprimer.

Trois modes :

- par défaut, SIMULATION : affiche le plan, sans créer le moindre client AWS ;
- ``--check`` : lecture seule, affiche l'état de chaque réglage et rend un code
  de sortie non nul si un réglage manque ou si le compartiment est absent ;
- ``--apply`` : crée le compartiment s'il n'existe pas, puis applique
  seulement les réglages qui manquent.

Réglages exigés :

1. les QUATRE options Block Public Access ;
2. chiffrement par défaut SSE-S3 (``AES256``) ; un chiffrement KMS déjà en
   place est accepté tel quel (jamais affaibli) ;
3. politique de compartiment qui refuse toute requête hors TLS
   (``aws:SecureTransport`` = ``false``), ajoutée aux énoncés existants sans
   en retirer aucun ;
4. propriété des objets ``BucketOwnerEnforced`` (ACL désactivées) ;
5. étiquette ``Project=alphaforge``, ajoutée aux étiquettes existantes.

Nom : ``alphaforge-traces-<suffixe>``. Le suffixe vient de ``--suffix`` ou,
par défaut, des 8 premiers caractères hexadécimaux du SHA-256 du numéro de
compte renvoyé par STS. Le numéro de compte n'est jamais affiché ni stocké :
il sert seulement à calculer le suffixe et à vérifier le propriétaire du
compartiment (``ExpectedBucketOwner``).

Aucune suppression, aucune politique publique, aucun accès croisé. Les
identifiants viennent uniquement de la chaîne par défaut de boto3.

Usage (depuis la racine, dans le terminal qui contient les identifiants
temporaires) ::

    python scripts/setup_trace_bucket.py             # simulation, aucun appel
    python scripts/setup_trace_bucket.py --check     # lecture seule
    python scripts/setup_trace_bucket.py --apply     # crée ou corrige

Codes de sortie : 0 succès, 1 erreur AWS ou d'identifiants, 2 configuration,
3 réglage manquant (``--check``), 4 nom déjà pris par un autre compte.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_aws_access import (  # noqa: E402
    EXIT_AWS_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_OK,
    default_client_factory,
    describe_aws_error,
    error_code,
    redact_text,
    resolve_region,
)

EXIT_CHECK_FAILED = 3
EXIT_BUCKET_CONFLICT = 4

BUCKET_REGION = "us-east-1"
BUCKET_PREFIX = "alphaforge-traces-"
BUCKET_ENV_VAR = "ALPHAFORGE_TRACE_BUCKET"
SUFFIX_LENGTH = 8
SUFFIX_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
MAX_BUCKET_NAME = 63

TAG_KEY = "Project"
TAG_VALUE = "alphaforge"
TLS_SID = "DenyInsecureTransport"
OWNERSHIP = "BucketOwnerEnforced"
BLOCK_FLAGS = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
ACCEPTED_SSE = ("AES256", "aws:kms", "aws:kms:dsse")

SETTINGS = ("public_access_block", "encryption", "tls_policy", "ownership", "tag")
SETTING_LABELS = {
    "public_access_block": "Block Public Access (quatre options)",
    "encryption": "Chiffrement par défaut SSE-S3 (AES256)",
    "tls_policy": "Politique : refus hors TLS (aws:SecureTransport)",
    "ownership": "Propriété des objets BucketOwnerEnforced",
    "tag": f"Étiquette {TAG_KEY}={TAG_VALUE}",
}

_NOT_FOUND_CODES = frozenset({"404", "NoSuchBucket", "NotFound"})
# HeadBucket ne renvoie pas de corps : un refus arrive sous le code "403". Un "AccessDenied"
# explicite (autres appels) reste une erreur d'accès ordinaire.
_FORBIDDEN_CODES = frozenset({"403", "Forbidden"})
_MISSING_CONFIG_CODES = {
    "public_access_block": frozenset({"NoSuchPublicAccessBlockConfiguration"}),
    "encryption": frozenset({"ServerSideEncryptionConfigurationNotFoundError"}),
    "tls_policy": frozenset({"NoSuchBucketPolicy"}),
    "ownership": frozenset({"OwnershipControlsNotFoundError"}),
    "tag": frozenset({"NoSuchTagSet", "NoSuchTagSetError"}),
}


class BucketConflictError(Exception):
    """Le nom existe déjà et n'appartient pas au compte courant (ou l'accès est refusé)."""


# ---------------------------------------------------------------------------
# Nom du compartiment
# ---------------------------------------------------------------------------

def derive_suffix(account_id: str) -> str:
    """Suffixe stable et non réversible : 8 caractères hexadécimaux du SHA-256 du compte."""
    if not account_id:
        raise ValueError("Numéro de compte absent : impossible de dériver le suffixe.")
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:SUFFIX_LENGTH]


def validate_suffix(suffix: str) -> str | None:
    """Rend un message d'erreur en français si le suffixe est invalide, sinon None."""
    if not suffix or not SUFFIX_PATTERN.match(suffix):
        return ("Suffixe invalide : lettres minuscules, chiffres et tirets seulement, "
                "sans tiret au début ni à la fin.")
    if len(BUCKET_PREFIX) + len(suffix) > MAX_BUCKET_NAME:
        return f"Suffixe trop long : le nom complet dépasse {MAX_BUCKET_NAME} caractères."
    if re.fullmatch(r"\d{12}", suffix):
        return "Suffixe refusé : il ressemble à un numéro de compte AWS."
    return None


def bucket_name(suffix: str) -> str:
    return f"{BUCKET_PREFIX}{suffix}"


# ---------------------------------------------------------------------------
# Configuration attendue
# ---------------------------------------------------------------------------

def public_access_block_config() -> dict:
    return {flag: True for flag in BLOCK_FLAGS}


def encryption_config() -> dict:
    return {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}


def tls_statement(bucket: str) -> dict:
    """Énoncé qui refuse toute requête non chiffrée. ARN S3 sans numéro de compte."""
    return {
        "Sid": TLS_SID,
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
    }


def merge_tls_policy(existing: dict | None, bucket: str) -> dict:
    """Ajoute l'énoncé TLS à la politique existante sans retirer aucun autre énoncé."""
    policy = copy.deepcopy(existing) if existing else {"Version": "2012-10-17", "Statement": []}
    statements = policy.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    statements = [s for s in statements if s.get("Sid") != TLS_SID]
    statements.append(tls_statement(bucket))
    policy["Statement"] = statements
    policy.setdefault("Version", "2012-10-17")
    return policy


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def has_tls_statement(policy: dict | None) -> bool:
    """Vrai si un énoncé ``Deny`` couvre ``s3:*`` quand ``aws:SecureTransport`` vaut false."""
    if not policy:
        return False
    for statement in _as_list(policy.get("Statement")):
        if statement.get("Effect") != "Deny":
            continue
        if "s3:*" not in _as_list(statement.get("Action")):
            continue
        condition = statement.get("Condition", {}).get("Bool", {})
        values = [str(v).lower() for v in _as_list(condition.get("aws:SecureTransport"))]
        if "false" in values:
            return True
    return False


# ---------------------------------------------------------------------------
# Inspection (lecture seule)
# ---------------------------------------------------------------------------

def bucket_exists(s3: Any, bucket: str, account_id: str) -> bool:
    """Vrai si le compartiment existe et appartient au compte, False s'il est absent.

    Lève ``BucketConflictError`` s'il existe sans appartenir au compte courant.
    """
    try:
        s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account_id)
        return True
    except Exception as exc:  # noqa: BLE001 - tri par code juste après
        code = error_code(exc)
        if code in _NOT_FOUND_CODES:
            return False
        if code in _FORBIDDEN_CODES:
            raise BucketConflictError(bucket) from exc
        raise


def _read(fetch: Callable[[], Any], setting: str) -> Any:
    """Lit un réglage ; rend None s'il n'est pas configuré, relance les autres erreurs."""
    try:
        return fetch()
    except Exception as exc:  # noqa: BLE001 - tri par code juste après
        if error_code(exc) in _MISSING_CONFIG_CODES[setting]:
            return None
        raise


def inspect_settings(s3: Any, bucket: str, account_id: str) -> dict:
    """État de chaque réglage : ``{"ok": bool, "detail": str, "raw": ...}``."""
    owner = {"ExpectedBucketOwner": account_id}
    state: dict[str, dict] = {}

    pab = _read(lambda: s3.get_public_access_block(Bucket=bucket, **owner), "public_access_block")
    config = (pab or {}).get("PublicAccessBlockConfiguration", {})
    missing = [flag for flag in BLOCK_FLAGS if not config.get(flag)]
    state["public_access_block"] = {
        "ok": pab is not None and not missing,
        "detail": "absent" if pab is None else ("4/4" if not missing else f"manque {', '.join(missing)}"),
        "raw": config,
    }

    enc = _read(lambda: s3.get_bucket_encryption(Bucket=bucket, **owner), "encryption")
    rules = (enc or {}).get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
    algorithms = [r.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm") for r in rules]
    algorithms = [a for a in algorithms if a]
    state["encryption"] = {
        "ok": any(a in ACCEPTED_SSE for a in algorithms),
        "detail": ", ".join(algorithms) or "absent",
        "raw": algorithms,
    }

    pol = _read(lambda: s3.get_bucket_policy(Bucket=bucket, **owner), "tls_policy")
    policy = json.loads(pol["Policy"]) if pol and pol.get("Policy") else None
    tls_ok = has_tls_statement(policy)
    state["tls_policy"] = {
        "ok": tls_ok,
        "detail": "présente" if tls_ok else ("aucune politique" if policy is None else "énoncé TLS absent"),
        "raw": policy,
    }

    own = _read(lambda: s3.get_bucket_ownership_controls(Bucket=bucket, **owner), "ownership")
    own_rules = (own or {}).get("OwnershipControls", {}).get("Rules", [])
    ownership = own_rules[0].get("ObjectOwnership") if own_rules else None
    state["ownership"] = {"ok": ownership == OWNERSHIP, "detail": ownership or "absent", "raw": ownership}

    tags = _read(lambda: s3.get_bucket_tagging(Bucket=bucket, **owner), "tag")
    tag_set = list((tags or {}).get("TagSet", []))
    tag_ok = any(t.get("Key") == TAG_KEY and t.get("Value") == TAG_VALUE for t in tag_set)
    state["tag"] = {"ok": tag_ok, "detail": "présente" if tag_ok else "absente", "raw": tag_set}
    return state


def missing_settings(state: dict) -> list[str]:
    return [name for name in SETTINGS if not state[name]["ok"]]


# ---------------------------------------------------------------------------
# Corrections (seulement ce qui manque, jamais de suppression)
# ---------------------------------------------------------------------------

def fix_setting(s3: Any, bucket: str, account_id: str, setting: str, current: dict) -> None:
    owner = {"ExpectedBucketOwner": account_id}
    if setting == "public_access_block":
        s3.put_public_access_block(
            Bucket=bucket, PublicAccessBlockConfiguration=public_access_block_config(), **owner)
    elif setting == "encryption":
        s3.put_bucket_encryption(
            Bucket=bucket, ServerSideEncryptionConfiguration=encryption_config(), **owner)
    elif setting == "ownership":
        s3.put_bucket_ownership_controls(
            Bucket=bucket, OwnershipControls={"Rules": [{"ObjectOwnership": OWNERSHIP}]}, **owner)
    elif setting == "tls_policy":
        policy = merge_tls_policy(current.get("raw"), bucket)
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy), **owner)
    elif setting == "tag":
        tags = [t for t in current.get("raw") or [] if t.get("Key") != TAG_KEY]
        tags.append({"Key": TAG_KEY, "Value": TAG_VALUE})
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": tags}, **owner)
    else:  # pragma: no cover - liste fermée
        raise ValueError(setting)


# Ordre d'application : le blocage public d'abord, la politique après.
FIX_ORDER = ("public_access_block", "ownership", "encryption", "tls_policy", "tag")


def create_bucket(s3: Any, bucket: str) -> bool:
    """Crée le compartiment en us-east-1 (sans LocationConstraint). Rend True s'il a été créé."""
    try:
        s3.create_bucket(Bucket=bucket, ObjectOwnership=OWNERSHIP)
        return True
    except Exception as exc:  # noqa: BLE001 - tri par code juste après
        code = error_code(exc)
        if code == "BucketAlreadyOwnedByYou":
            return False
        if code == "BucketAlreadyExists":
            raise BucketConflictError(bucket) from exc
        raise


def ensure_bucket(s3: Any, bucket: str, account_id: str) -> dict:
    """Crée le compartiment si besoin puis corrige les réglages manquants.

    Rend ``{"created": bool, "fixed": [réglages corrigés], "state": état final}``.
    """
    created = False
    if not bucket_exists(s3, bucket, account_id):
        created = create_bucket(s3, bucket)
    state = inspect_settings(s3, bucket, account_id)
    fixed = []
    for setting in FIX_ORDER:
        if not state[setting]["ok"]:
            fix_setting(s3, bucket, account_id, setting, state[setting])
            fixed.append(setting)
    final = inspect_settings(s3, bucket, account_id) if fixed else state
    return {"created": created, "fixed": fixed, "state": final}


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------

def format_state(state: dict) -> str:
    lines = []
    for name in SETTINGS:
        mark = "ok" if state[name]["ok"] else "MANQUANT"
        lines.append(f"- {SETTING_LABELS[name]} : {mark} ({state[name]['detail']})")
    return "\n".join(lines)


def env_reminder(bucket: str) -> str:
    return "\n".join([
        f"Compartiment des traces : {bucket}",
        "À définir dans le terminal dédié ou dans un .env ignoré par Git, jamais dans le dépôt :",
        f"{BUCKET_ENV_VAR}={bucket}",
    ])


def describe_plan(suffix: str | None) -> str:
    name = bucket_name(suffix) if suffix else f"{BUCKET_PREFIX}<8 caractères du SHA-256 du compte>"
    lines = [
        "Mode simulation : aucun client AWS créé, aucun appel.",
        f"Compartiment visé : {name} (région {BUCKET_REGION})",
        "Réglages qui seraient appliqués s'ils manquent :",
    ]
    lines += [f"- {SETTING_LABELS[name_]}" for name_ in SETTINGS]
    lines += [
        "Aucune suppression, aucune politique publique, aucun accès croisé.",
        "Relancer avec --check (lecture seule) ou --apply (création ou correction).",
    ]
    if suffix:
        lines += ["", env_reminder(bucket_name(suffix))]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crée ou vérifie le compartiment S3 privé des traces (simulation par défaut).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true",
                       help="Crée le compartiment ou corrige les réglages manquants (modifie le compte).")
    group.add_argument("--check", action="store_true",
                       help="Lecture seule : état de chaque réglage, code non nul si un réglage manque.")
    parser.add_argument("--suffix", help="Suffixe du nom (sinon dérivé du numéro de compte par SHA-256).")
    parser.add_argument("--region", help=f"Région AWS (sinon AWS_REGION ; doit valoir {BUCKET_REGION}).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *,
         client_factory: Callable[[str], Callable[[str], Any]] | None = None,
         environ: dict | None = None) -> int:
    """Point d'entrée mince. Aucun client AWS n'est créé sans --apply ou --check."""
    args = parse_args(argv)
    env = dict(os.environ) if environ is None else environ
    if args.suffix is not None:
        problem = validate_suffix(args.suffix)
        if problem:
            print(problem)
            return EXIT_CONFIG_ERROR

    if not args.apply and not args.check:
        print(describe_plan(args.suffix))
        return EXIT_OK

    region = resolve_region(args.region, env) or BUCKET_REGION
    if region != BUCKET_REGION:
        print(f"Région {region} refusée : le compartiment des traces vit en {BUCKET_REGION}. "
              "Définir AWS_REGION=us-east-1 dans ce terminal.")
        return EXIT_CONFIG_ERROR

    bucket = "<inconnu>"
    try:
        make_client = (client_factory or default_client_factory)(region)
        account_id = make_client("sts").get_caller_identity().get("Account")
        if not account_id:
            print("STS n'a renvoyé aucun compte : vérifier les identifiants temporaires.")
            return EXIT_AWS_ERROR
        bucket = bucket_name(args.suffix or derive_suffix(account_id))
        s3 = make_client("s3")
        if args.check:
            if not bucket_exists(s3, bucket, account_id):
                print(f"Compartiment {bucket} : absent. Le créer avec --apply.")
                return EXIT_CHECK_FAILED
            state = inspect_settings(s3, bucket, account_id)
            print(f"Compartiment {bucket} : présent (région attendue {BUCKET_REGION}).")
            print(format_state(state))
            missing = missing_settings(state)
            if missing:
                print(f"{len(missing)} réglage(s) manquant(s) : relancer avec --apply pour corriger.")
                return EXIT_CHECK_FAILED
            print("Tous les réglages sont conformes.")
            print(env_reminder(bucket))
            return EXIT_OK

        result = ensure_bucket(s3, bucket, account_id)
        print(f"Compartiment {bucket} : {'créé' if result['created'] else 'déjà présent'}.")
        if result["fixed"]:
            print("Réglages appliqués : " + ", ".join(SETTING_LABELS[s] for s in result["fixed"]) + ".")
        else:
            print("Aucun réglage à corriger.")
        print(format_state(result["state"]))
        print(env_reminder(bucket))
        if missing_settings(result["state"]):
            print("Au moins un réglage reste manquant après correction : vérifier dans la console.")
            return EXIT_CHECK_FAILED
    except BucketConflictError:
        print(f"Le nom {bucket} existe déjà mais n'appartient pas à ce compte (ou l'accès est refusé). "
              "Rien n'a été modifié. Choisir un autre nom avec --suffix.")
        return EXIT_BUCKET_CONFLICT
    except Exception as exc:  # noqa: BLE001 - message clair et masqué pour toute erreur AWS
        print(redact_text(describe_aws_error(exc)))
        return EXIT_AWS_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
