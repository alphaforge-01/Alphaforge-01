"""Client Bedrock minimal pour le flux C.

Ce module ne contient aucune logique financiere. Il fait trois choses :
- lire la configuration depuis l'environnement (jamais de valeur codee en dur) ;
- appeler l'API Converse avec un delai exponentiel sur les limitations ;
- appeler ApplyGuardrail et traduire la reponse en ``GuardrailResult``.

Les identifiants viennent uniquement de la chaine par defaut de boto3
(variables d'environnement, profil, role). Rien n'est lu ni affiche ici.
Les messages d'erreur passent par ``redact_text`` avant de remonter.
"""
from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from .contracts import GuardrailResult

DEFAULT_REGION = "us-east-1"

# Codes d'erreur AWS regroupes par comportement attendu de l'application.
AUTH_ERROR_CODES = frozenset({
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "AccessDeniedException",
})
RETRYABLE_ERROR_CODES = frozenset({
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "ModelNotReadyException",
})

# Limites documentees du controle d'ancrage (en caracteres).
GROUNDING_SOURCE_MAX_CHARS = 100_000
GROUNDING_QUERY_MAX_CHARS = 1_000
GROUNDING_ANSWER_MAX_CHARS = 5_000

# Motifs de secrets a masquer dans tout texte qui sort de ce module.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"bedrock-api-key-[A-Za-z0-9+/=_%.\-]+"), "[CLE_BEDROCK_MASQUEE]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"), "[CLE_AWS_MASQUEE]"),
    (re.compile(r"(?i)\"?(SecretAccessKey|SessionToken|AccessKeyId)\"?\s*[:=]\s*\"?[^\s\",}]+\"?"), r"\1=[MASQUE]"),
    (re.compile(r"(?i)([?&](?:X-Amz-Signature|X-Amz-Security-Token|X-Amz-Credential|token|access_token)=)[^&\s\"']+"),
     r"\1[MASQUE]"),
    (re.compile(r"(?<![A-Za-z0-9/+=])(?=[A-Za-z0-9/+]*[A-Z])(?=[A-Za-z0-9/+]*[a-z])(?=[A-Za-z0-9/+]*\d)[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])"),
     "[SECRET_PRESUME_MASQUE]"),
    (re.compile(r"(?<![A-Za-z0-9/+=_-])[A-Za-z0-9/+_-]{120,}={0,2}(?![A-Za-z0-9/+=_-])"), "[JETON_PRESUME_MASQUE]"),
    (re.compile(r"arn:aws[a-z\-]*:[a-z0-9\-]*:[a-z0-9\-]*:\d{12}:[^\s\"',]+"), "[ARN_MASQUE]"),
    (re.compile(r"(?i)(aws_secret_access_key|aws_session_token|aws_bearer_token_bedrock)\s*[=:]\s*\S+"),
     r"\1=[MASQUE]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=\-]{20,}"), "Bearer [MASQUE]"),
    (re.compile(r"(?<![A-Za-z0-9])\d{12}(?![A-Za-z0-9])"), "[COMPTE_MASQUE]"),
)
_SENSITIVE_KEY = re.compile(r"(?i)(secret|token(?!s)|password|passwd|authorization|credential|api[_-]?key)")


def redact_text(text: str) -> str:
    """Masque les motifs de secrets connus (cles, ARN, numeros de compte)."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def redact(obj: Any) -> Any:
    """Copie recursive d'une structure JSON dont les secrets sont masques.

    Les valeurs dont le nom de cle evoque un secret sont remplacees en bloc,
    les autres chaines passent par ``redact_text``.
    """
    if isinstance(obj, Mapping):
        return {
            key: ("[MASQUE]" if _SENSITIVE_KEY.search(str(key)) and obj[key] is not None else redact(obj[key]))
            for key in obj
        }
    if isinstance(obj, (list, tuple)):
        return [redact(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


class BedrockError(Exception):
    """Erreur Bedrock generique, message deja masque."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(redact_text(message))
        self.code = code


class BedrockAuthError(BedrockError):
    """Identifiants absents, expires ou refuses : demander de nouveaux identifiants."""


class BedrockThrottledError(BedrockError):
    """Limitation persistante apres toutes les nouvelles tentatives."""


@dataclass(frozen=True)
class BedrockConfig:
    """Configuration lue dans l'environnement. Aucune valeur secrete."""

    region: str = DEFAULT_REGION
    mode: str = "offline"
    analyst_model_id: str | None = None
    explainer_model_id: str | None = None
    guardrail_id: str | None = None
    guardrail_version: str | None = None
    trace_bucket: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "BedrockConfig":
        source = os.environ if env is None else env

        def get(name: str) -> str | None:
            value = source.get(name, "").strip()
            return value or None

        analyst = get("ALPHAFORGE_ANALYST_MODEL_ID")
        explainer = get("ALPHAFORGE_EXPLAINER_MODEL_ID") or analyst
        return cls(
            region=get("AWS_REGION") or DEFAULT_REGION,
            mode=(get("ALPHAFORGE_MODE") or "offline").lower(),
            analyst_model_id=analyst,
            explainer_model_id=explainer,
            guardrail_id=get("ALPHAFORGE_GUARDRAIL_ID"),
            guardrail_version=get("ALPHAFORGE_GUARDRAIL_VERSION"),
            trace_bucket=get("ALPHAFORGE_TRACE_BUCKET"),
        )

    @property
    def can_call_models(self) -> bool:
        return self.mode == "bedrock" and bool(self.analyst_model_id)

    @property
    def has_guardrail(self) -> bool:
        return bool(self.guardrail_id and self.guardrail_version)


def extract_text(response: Mapping[str, Any]) -> str:
    """Concatene tous les blocs ``text`` d'une reponse Converse.

    Ne suppose jamais que ``content[0]`` porte la reponse : un modele peut
    renvoyer des blocs de raisonnement ou d'outil avant le texte.
    """
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(block["text"] for block in blocks if isinstance(block, Mapping) and "text" in block)


def extract_tool_uses(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Liste les demandes d'outil (``toolUse``) d'une reponse Converse."""
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return [block["toolUse"] for block in blocks if isinstance(block, Mapping) and "toolUse" in block]


def tool_result_message(tool_use_id: str, payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    """Message utilisateur renvoyant le resultat d'un outil au modele."""
    block: dict[str, Any] = {
        "toolUseId": tool_use_id,
        "content": [{"json": payload}] if not isinstance(payload, str) else [{"text": payload}],
    }
    if is_error:
        block["status"] = "error"
    return {"role": "user", "content": [{"toolResult": block}]}


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", "Unknown"))


class BedrockClient:
    """Enveloppe fine autour du client ``bedrock-runtime`` de boto3.

    Le client boto3, la fonction de pause et la source d'aleatoire sont
    injectables pour que les tests ne contactent jamais AWS et n'attendent pas.
    """

    def __init__(
        self,
        config: BedrockConfig,
        runtime_client: Any | None = None,
        *,
        max_retries: int = 4,
        base_delay: float = 1.0,
        max_delay: float = 20.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.config = config
        self._runtime = runtime_client
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._sleep = sleep
        self._jitter = jitter
        self.retry_count = 0
        self.last_grounding_flags: dict[str, Any] = {}

    @property
    def runtime(self) -> Any:
        if self._runtime is None:
            import boto3  # import tardif : les tests n'en ont pas besoin

            self._runtime = boto3.client("bedrock-runtime", region_name=self.config.region)
        return self._runtime

    def _delay(self, attempt: int) -> float:
        return min(self.max_delay, self.base_delay * (2 ** attempt)) * (0.5 + self._jitter() / 2)

    def _call(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        """Appelle une operation avec delai exponentiel sur les limitations."""
        for attempt in range(self.max_retries + 1):
            try:
                return getattr(self.runtime, operation)(**kwargs)
            except NoCredentialsError as error:
                raise BedrockAuthError("Aucun identifiant AWS disponible dans l'environnement.") from None
            except ClientError as error:
                code = _error_code(error)
                if code in AUTH_ERROR_CODES:
                    raise BedrockAuthError(
                        f"Acces refuse ou jeton expire ({code}). Recuperer de nouveaux identifiants temporaires.",
                        code=code,
                    ) from None
                if code in RETRYABLE_ERROR_CODES:
                    if attempt >= self.max_retries:
                        raise BedrockThrottledError(
                            f"Limitation persistante sur {operation} apres {attempt + 1} essais ({code}).",
                            code=code,
                        ) from None
                    self.retry_count += 1
                    self._sleep(self._delay(attempt))
                    continue
                raise BedrockError(f"Erreur Bedrock sur {operation} ({code}).", code=code) from None
            except BotoCoreError as error:
                raise BedrockError(f"Erreur reseau ou configuration sur {operation} : {type(error).__name__}.") from None
        raise BedrockError(f"Appel {operation} sans resultat.")  # pragma: no cover

    def converse(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tool_config: dict[str, Any] | None = None,
        inference_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Un appel Converse. Aucune application de garde-fou ici : voir ``apply_guardrail``."""
        request: dict[str, Any] = {"modelId": model_id, "messages": messages}
        if system:
            request["system"] = [{"text": system}]
        if tool_config:
            request["toolConfig"] = tool_config
        if inference_config:
            request["inferenceConfig"] = inference_config
        return self._call("converse", **request)

    def apply_guardrail(self, source: str, content: list[dict[str, Any]]) -> dict[str, Any]:
        """Appelle ApplyGuardrail avec le garde-fou configure dans l'environnement."""
        if not self.config.has_guardrail:
            raise BedrockError("Garde-fou non configure : definir ALPHAFORGE_GUARDRAIL_ID et ALPHAFORGE_GUARDRAIL_VERSION.")
        return self._call(
            "apply_guardrail",
            guardrailIdentifier=self.config.guardrail_id,
            guardrailVersion=self.config.guardrail_version,
            source=source,
            content=content,
        )

    def check_request_topic(self, text: str, *, mode: str = "block") -> GuardrailResult:
        """Verifie une requete utilisateur contre les sujets refuses."""
        response = self.apply_guardrail("INPUT", [{"text": {"text": text}}])
        return parse_guardrail_response(response, check="request_topic", mode=mode)

    def check_output_grounding(
        self, source_text: str, query: str, answer: str, *, mode: str = "detect"
    ) -> GuardrailResult:
        """Controle d'ancrage : ``answer`` doit s'appuyer sur ``source_text`` (le dossier).

        Retourne ``not_run`` si une des limites de taille documentees est depassee,
        plutot que de tronquer en silence.
        """
        if (
            len(source_text) > GROUNDING_SOURCE_MAX_CHARS
            or len(query) > GROUNDING_QUERY_MAX_CHARS
            or len(answer) > GROUNDING_ANSWER_MAX_CHARS
        ):
            return GuardrailResult(
                check="output_grounding", action="not_run", denied_topics=[],
                grounding_score=None, relevance_score=None, mode=mode,
            )
        content = [
            {"text": {"text": source_text, "qualifiers": ["grounding_source"]}},
            {"text": {"text": query, "qualifiers": ["query"]}},
            {"text": {"text": answer, "qualifiers": ["guard_content"]}},
        ]
        response = self.apply_guardrail("OUTPUT", content)
        self.last_grounding_flags = grounding_flags(response)
        return parse_guardrail_response(response, check="output_grounding", mode=mode)


def grounding_flags(response: Mapping[str, Any]) -> dict[str, Any]:
    """Indique si un filtre d'ancrage a detecte un texte sous son seuil (mode detection).

    En mode detection, l'API renvoie ``action: NONE`` au niveau global et ``detected: true``
    sur le filtre : sans cette lecture, un ancrage faible passerait pour un succes.
    """
    below: list[str] = []
    for assessment in response.get("assessments", []) or []:
        for item in assessment.get("contextualGroundingPolicy", {}).get("filters", []) or []:
            if item.get("detected") or item.get("action") == "BLOCKED":
                below.append(str(item.get("type", "")))
    return {"below_threshold": bool(below), "filters": sorted(set(below))}


def parse_guardrail_response(response: Mapping[str, Any], *, check: str, mode: str = "detect") -> GuardrailResult:
    """Traduit une reponse ApplyGuardrail en ``GuardrailResult``.

    Seuls les sujets refuses declenches et les scores d'ancrage et de pertinence
    sont retenus. Les extraits du contenu ne sont pas recopies.
    """
    denied: list[str] = []
    grounding: float | None = None
    relevance: float | None = None
    for assessment in response.get("assessments", []) or []:
        for topic in assessment.get("topicPolicy", {}).get("topics", []) or []:
            if (topic.get("action") == "BLOCKED" or topic.get("detected")) and topic.get("name"):
                denied.append(str(topic["name"]))
        for item in assessment.get("contextualGroundingPolicy", {}).get("filters", []) or []:
            score = item.get("score")
            if score is None:
                continue
            if item.get("type") == "GROUNDING":
                grounding = float(score) if grounding is None else min(grounding, float(score))
            elif item.get("type") == "RELEVANCE":
                relevance = float(score) if relevance is None else min(relevance, float(score))
    intervened = response.get("action") == "GUARDRAIL_INTERVENED"
    return GuardrailResult(
        check=check,  # type: ignore[typeddict-item]
        action="intervened" if intervened else "none",
        denied_topics=sorted(set(denied)),
        grounding_score=grounding,
        relevance_score=relevance,
        mode=mode,  # type: ignore[typeddict-item]
    )
