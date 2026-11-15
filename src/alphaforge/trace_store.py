"""Stockage des traces d'execution (S3 prive) et copies locales.

Une trace documente ce que le code a fait : outils appeles, statuts de
gouvernance, validation, interventions du garde-fou. Elle ne contient jamais de
secret (tout passe par ``redact``) ni de raisonnement interne de modele (aucun
n'est demande ni lu). Les donnees du dossier sont fictives.

Regles de securite appliquees ici :
- avant la premiere ecriture, le compartiment doit avoir les quatre options
  Block Public Access activees, sinon rien n'est ecrit ;
- chiffrement cote serveur demande a chaque ecriture ;
- chaque appel S3 porte ``ExpectedBucketOwner`` (compte des identifiants courants, lu par STS) :
  un compartiment du meme nom appartenant a un autre compte est refuse ;
- aucune ecriture ne doit faire planter l'application : les erreurs deviennent
  ``TraceStoreError`` et l'appelant continue.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from .bedrock_client import redact
from .contracts import AnalysisResult, ExplanationResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_TRACE_DIR = PROJECT_ROOT / "outputs" / "reports" / "traces"
SCHEMA_VERSION = 1
DISCLAIMER_FR = (
    "Simulation educative sur des donnees fictives. Ce n'est pas un conseil financier personnalise."
)
_BLOCK_FLAGS = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")


class TraceStoreError(Exception):
    """Ecriture ou verification impossible. Le message ne contient aucun secret."""


def build_trace_document(
    analysis: AnalysisResult, explanation: ExplanationResult | None = None
) -> dict[str, Any]:
    """Document JSON d'une trace, masque. ``explanation`` ajoute les etapes 4 a 6 d'un niveau."""
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "disclaimer": DISCLAIMER_FR,
        "note": "Trace construite par le code a partir des appels reels. Aucun raisonnement interne de modele.",
        "analysis": analysis,
    }
    if explanation is not None:
        document["explanation"] = {
            "level": explanation["output"]["level"],
            "origin": explanation["output"]["origin"],
            "model_id": explanation["output"]["model_id"],
            "prompt_version": explanation["output"]["prompt_version"],
            "attempt": explanation["output"]["attempt"],
            "validation": explanation["validation"],
            "guardrail": explanation["guardrail"],
            "rendered_markdown": explanation["rendered_markdown"],
            "trace": explanation["trace"],
        }
    return redact(document)


def trace_key(document: dict[str, Any], *, prefix: str = "traces") -> str:
    analysis = document["analysis"]
    suffix = f"-explication-{document['explanation']['level']}" if "explanation" in document else ""
    return f"{prefix}/{str(analysis['created_at'])[:10]}/{analysis['run_id']}{suffix}.json"


def _dump(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def save_local_copy(document: dict[str, Any], directory: Path | None = None) -> Path:
    """Copie locale (pour ``outputs/reports/`` avant l'expiration du compte AWS)."""
    target = (directory or LOCAL_TRACE_DIR) / Path(trace_key(document)).name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_dump(document))
    return target


class TraceStore:
    """Ecrit les traces dans un compartiment S3 prive, apres verification du blocage public."""

    def __init__(self, bucket: str, s3_client: Any | None = None, *, region: str = "us-east-1",
                 prefix: str = "traces", expected_owner: str | None = None, sts_client: Any | None = None) -> None:
        if not bucket:
            raise TraceStoreError("Compartiment de traces non configure (ALPHAFORGE_TRACE_BUCKET).")
        self.bucket = bucket
        self.prefix = prefix
        self._region = region
        self._s3 = s3_client
        self._sts = sts_client
        self._expected_owner = expected_owner
        # Client S3 cree ici (usage reel) : le proprietaire est toujours verifie. Client injecte (tests) :
        # verifie seulement si un proprietaire ou un client STS est fourni. Un code applicatif qui injecte
        # son propre client doit donc passer aussi ``expected_owner`` ou ``sts_client``.
        self._check_owner = s3_client is None or expected_owner is not None or sts_client is not None
        self._verified = False

    @property
    def s3(self) -> Any:
        if self._s3 is None:
            import boto3  # import tardif : les tests n'en ont pas besoin

            self._s3 = boto3.client("s3", region_name=self._region)
        return self._s3

    def _owner(self) -> dict[str, str]:
        """Parametre ``ExpectedBucketOwner`` des appels S3. Le numero de compte n'est jamais affiche."""
        if not self._check_owner:
            return {}
        if self._expected_owner is None:
            try:
                if self._sts is None:
                    import boto3  # import tardif : les tests n'en ont pas besoin

                    self._sts = boto3.client("sts", region_name=self._region)
                self._expected_owner = str(self._sts.get_caller_identity()["Account"])
            except (ClientError, BotoCoreError, KeyError, TypeError) as error:
                raise TraceStoreError(
                    f"Proprietaire du compartiment non verifiable ({type(error).__name__}) : ecriture refusee.") from error
        return {"ExpectedBucketOwner": self._expected_owner}

    def assert_private(self) -> None:
        """Exige les quatre options Block Public Access. Resultat memorise apres un succes."""
        if self._verified:
            return
        try:
            config = self.s3.get_public_access_block(
                Bucket=self.bucket, **self._owner())["PublicAccessBlockConfiguration"]
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "Unknown")
            raise TraceStoreError(f"Blocage d'acces public non verifiable ({code}) : ecriture refusee.") from error
        except BotoCoreError as error:
            raise TraceStoreError(f"Verification du compartiment impossible : {type(error).__name__}.") from error
        missing = [flag for flag in _BLOCK_FLAGS if not config.get(flag)]
        if missing:
            raise TraceStoreError(
                "Le compartiment n'a pas les quatre options Block Public Access activees : ecriture refusee.")
        self._verified = True

    def save(self, document: dict[str, Any]) -> str:
        """Ecrit le document et rend la cle de l'objet (jamais d'identifiant de compte)."""
        self.assert_private()
        key = trace_key(document, prefix=self.prefix)
        try:
            self.s3.put_object(
                Bucket=self.bucket, Key=key, Body=_dump(document),
                ContentType="application/json", ServerSideEncryption="AES256", **self._owner())
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "Unknown")
            raise TraceStoreError(f"Ecriture de la trace impossible ({code}).") from error
        except BotoCoreError as error:
            raise TraceStoreError(f"Ecriture de la trace impossible : {type(error).__name__}.") from error
        return key
