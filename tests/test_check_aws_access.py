"""Tests de scripts/check_aws_access.py avec des clients simulés (aucun appel AWS)."""
from pathlib import Path
import re
import sys

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import check_aws_access as caa  # noqa: E402

# Identifiants entièrement inventés, au format AWS, pour vérifier le masquage.
FAKE_ACCOUNT = "0" * 12  # construit à l'exécution : aucun numéro de compte écrit dans le source
FAKE_ARN = f"arn:aws:sts::{FAKE_ACCOUNT}:assumed-role/FictionalRole/fictional-session"
TWELVE_DIGITS = re.compile(r"(?<!\d)\d{12}(?!\d)")


def client_error(code, message="message fictif", operation="Op"):
    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


class FakeSts:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0

    def get_caller_identity(self):
        self.calls += 1
        if self.error:
            raise self.error
        return {"Account": FAKE_ACCOUNT, "Arn": FAKE_ARN, "UserId": "FICTIONALUSERID:session"}


class FakeBedrock:
    def __init__(self):
        self.profile_calls = []

    def list_foundation_models(self, **kwargs):
        assert kwargs == {"byOutputModality": "TEXT"}
        return {"modelSummaries": [
            {"modelId": "provider-a.text-model-v1", "providerName": "A", "modelName": "Texte",
             "inputModalities": ["TEXT"], "outputModalities": ["TEXT"],
             "inferenceTypesSupported": ["ON_DEMAND"], "responseStreamingSupported": True,
             "modelLifecycle": {"status": "ACTIVE"}},
            {"modelId": "provider-a.old-model", "providerName": "A",
             "inputModalities": ["TEXT"], "outputModalities": ["TEXT"],
             "modelLifecycle": {"status": "LEGACY"}},
            {"modelId": "provider-b.image-model", "providerName": "B",
             "inputModalities": ["TEXT"], "outputModalities": ["IMAGE"],
             "modelLifecycle": {"status": "ACTIVE"}},
            {"modelId": "provider-c.future-model", "providerName": "C",
             "inputModalities": ["TEXT", "IMAGE"], "outputModalities": ["TEXT"],
             "inferenceTypesSupported": ["INFERENCE_PROFILE"], "toolUseSupported": True,
             "modelLifecycle": {"status": "ACTIVE"}},
        ]}

    def list_inference_profiles(self, **kwargs):
        self.profile_calls.append(kwargs)
        arn = f"arn:aws:bedrock:us-east-1:{FAKE_ACCOUNT}:inference-profile/us.fictional"
        if not kwargs:
            return {"inferenceProfileSummaries": [
                {"inferenceProfileId": "us.provider-c.future-model", "inferenceProfileName": "P1",
                 "inferenceProfileArn": arn, "status": "ACTIVE", "type": "SYSTEM_DEFINED",
                 "models": [{}, {}]}], "nextToken": "page2"}
        return {"inferenceProfileSummaries": [
            {"inferenceProfileId": "global.provider-c.future-model", "inferenceProfileName": "P2",
             "inferenceProfileArn": arn, "status": "ACTIVE", "type": "SYSTEM_DEFINED", "models": [{}]}]}


class FakeRuntime:
    def __init__(self, errors=None):
        self.errors = list(errors or [])
        self.requests = []

    def converse(self, **kwargs):
        self.requests.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return {
            "stopReason": "tool_use",
            "output": {"message": {"role": "assistant", "content": [
                {"text": "Je vais appeler l'outil."},
                {"toolUse": {"toolUseId": "t1", "name": "get_fictional_metric",
                             "input": {"ticker": "FICTIF"}}},
                {"text": "Fin."},
            ]}},
        }


def factory_for(clients):
    created = []

    def factory(region):
        def make(service):
            created.append(service)
            return clients[service]
        return make

    factory.created = created
    return factory


# --- Masquage ---------------------------------------------------------------

def test_mask_account_and_arn_hide_identifiers():
    assert FAKE_ACCOUNT not in caa.mask_account_id(FAKE_ACCOUNT)
    masked = caa.mask_arn(FAKE_ARN)
    assert FAKE_ACCOUNT not in masked
    assert "FictionalRole" not in masked and "fictional-session" not in masked
    assert masked.startswith("arn:aws:sts::")
    assert "assumed-role/" in masked
    assert caa.principal_type(FAKE_ARN) == "assumed-role"


def test_redact_text_removes_arn_and_account():
    # Aucune valeur au format de clé d'accès, même fictive, n'est écrite ici (règle 6).
    text = f"User: {FAKE_ARN} is not authorized; account {FAKE_ACCOUNT}"
    redacted = caa.redact_text(text)
    assert not TWELVE_DIGITS.search(redacted)
    assert "FictionalRole" not in redacted


def test_check_identity_is_masked_and_checks_region():
    result = caa.check_identity(FakeSts(), "us-east-1")
    assert result["account_responds"] is True
    assert result["region_ok"] is True
    assert FAKE_ACCOUNT not in str(result)
    assert caa.check_identity(FakeSts(), "eu-west-1")["region_ok"] is False


# --- Erreurs -----------------------------------------------------------------

@pytest.mark.parametrize("code", ["ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"])
def test_credential_errors_give_french_message(code):
    message = caa.describe_aws_error(client_error(code))
    assert code in message
    assert "identifiants temporaires" in message


def test_access_denied_message_is_redacted():
    err = client_error("AccessDeniedException", f"User: {FAKE_ARN} is not authorized")
    message = caa.describe_aws_error(err)
    assert "Accès refusé" in message
    assert FAKE_ACCOUNT not in message and "FictionalRole" not in message


def test_no_credentials_message():
    assert "Workshop Studio" in caa.describe_aws_error(NoCredentialsError())


@pytest.mark.parametrize("code", ["ExpiredToken", "ExpiredTokenException",
                                  "InvalidClientTokenId", "AccessDeniedException"])
def test_main_returns_nonzero_on_credential_error(code, capsys):
    factory = factory_for({"sts": FakeSts(error=client_error(code, f"denied for {FAKE_ARN}"))})
    exit_code = caa.main([], client_factory=factory, environ={"AWS_REGION": "us-east-1"})
    out = capsys.readouterr().out
    assert exit_code == caa.EXIT_AWS_ERROR
    assert not TWELVE_DIGITS.search(out)


def test_main_requires_region():
    factory = factory_for({})
    assert caa.main([], client_factory=factory, environ={}) == caa.EXIT_CONFIG_ERROR
    assert factory.created == []


def test_main_flags_wrong_region(capsys):
    factory = factory_for({"sts": FakeSts(), "bedrock": FakeBedrock()})
    code = caa.main(["--skip-listing"], client_factory=factory, environ={"AWS_REGION": "eu-west-1"})
    assert code == caa.EXIT_CONFIG_ERROR


# --- Listes --------------------------------------------------------------------

def test_list_active_text_models_filters():
    models = caa.list_active_text_models(FakeBedrock())
    ids = [m["model_id"] for m in models]
    assert ids == ["provider-a.text-model-v1", "provider-c.future-model"]
    assert models[0]["tool_use"] is None  # non renvoyé par l'API
    assert models[1]["tool_use"] is True


def test_list_inference_profiles_paginates_without_arn():
    bedrock = FakeBedrock()
    profiles = caa.list_inference_profiles(bedrock)
    assert len(profiles) == 2
    assert bedrock.profile_calls == [{}, {"nextToken": "page2"}]
    assert FAKE_ACCOUNT not in str(profiles)


def test_main_full_report_has_no_account(capsys):
    factory = factory_for({"sts": FakeSts(), "bedrock": FakeBedrock()})
    code = caa.main([], client_factory=factory, environ={"AWS_REGION": "us-east-1"})
    out = capsys.readouterr().out
    assert code == caa.EXIT_OK
    assert "Le compte répond : oui" in out
    assert not TWELVE_DIGITS.search(out)
    assert "FictionalRole" not in out


# --- Converse ------------------------------------------------------------------

def test_try_converse_reads_all_blocks():
    runtime = FakeRuntime()
    result = caa.try_converse(runtime, "provider-a.text-model-v1", sleep=lambda s: None)
    assert result["tool_names"] == ["get_fictional_metric"]
    assert result["tool_call_ok"] is True
    assert result["text"] == "Je vais appeler l'outil. Fin."
    request = runtime.requests[0]
    assert request["modelId"] == "provider-a.text-model-v1"
    assert request["toolConfig"]["toolChoice"] == {"auto": {}}


def test_try_converse_any_tool_choice():
    runtime = FakeRuntime()
    caa.try_converse(runtime, "m", tool_choice="any", sleep=lambda s: None)
    assert runtime.requests[0]["toolConfig"]["toolChoice"] == {"any": {}}


def test_backoff_retries_throttling_then_succeeds():
    sleeps = []
    runtime = FakeRuntime(errors=[client_error("ThrottlingException")] * 2)
    result = caa.try_converse(runtime, "m", sleep=sleeps.append)
    assert result["tool_call_ok"] is True
    assert sleeps == [1.0, 2.0]


def test_backoff_does_not_retry_other_errors():
    sleeps = []
    runtime = FakeRuntime(errors=[client_error("ValidationException")])
    with pytest.raises(ClientError):
        caa.try_converse(runtime, "m", sleep=sleeps.append)
    assert sleeps == []


def test_backoff_gives_up_after_max_attempts():
    sleeps = []

    def always_throttled():
        raise client_error("ThrottlingException")

    with pytest.raises(ClientError):
        caa.call_with_backoff(always_throttled, max_attempts=3, sleep=sleeps.append)
    assert sleeps == [1.0, 2.0]


def test_main_converse_model_from_env(capsys):
    runtime = FakeRuntime()
    factory = factory_for({"sts": FakeSts(), "bedrock-runtime": runtime})
    env = {"AWS_REGION": "us-east-1", caa.MODEL_ENV_VAR: "provider-env.model"}
    code = caa.main(["--skip-listing", "--try-converse"], client_factory=factory, environ=env,
                    sleep=lambda s: None)
    assert code == caa.EXIT_OK
    assert runtime.requests[0]["modelId"] == "provider-env.model"
    assert "get_fictional_metric" in capsys.readouterr().out


def test_main_converse_without_model_is_config_error():
    factory = factory_for({})
    code = caa.main(["--try-converse"], client_factory=factory, environ={"AWS_REGION": "us-east-1"})
    assert code == caa.EXIT_CONFIG_ERROR
    assert factory.created == []


def test_no_model_id_hardcoded_in_script():
    source = (ROOT / "scripts" / "check_aws_access.py").read_text(encoding="utf-8")
    for vendor in ("anthropic.", "amazon.nova", "meta.llama", "mistral.", "claude"):
        assert vendor not in source.lower()
