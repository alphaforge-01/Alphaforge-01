"""Tests du stockage des traces. Aucun appel AWS : client S3 remplace par un double ecrit a la main."""
from pathlib import Path
import copy
import json
import sys

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alphaforge.trace_store import (
    DISCLAIMER_FR, SCHEMA_VERSION, TraceStore, TraceStoreError, build_trace_document, save_local_copy, trace_key,
)

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_KEY = "AKIA" + "X" * 16
FAKE_ACCOUNT = "1234" + "5678" + "9012"
FAKE_ARN = "arn:aws:iam::" + FAKE_ACCOUNT + ":role/test-role"
ALL_BLOCKED = {flag: True for flag in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}


def analysis():
    return json.loads((FIXTURES / "analysis_result_robert_tsla.json").read_text(encoding="utf-8"))


def explanation(level="novice"):
    return {
        "output": {"level": level, "origin": "llm", "model_id": "model-test", "prompt_version": "explainer_v1",
                   "attempt": 1, "summary": "Texte."},
        "validation": {"is_valid": True, "rejections": [], "checked_references": ["G1"]},
        "guardrail": {"check": "output_grounding", "action": "none", "denied_topics": [],
                      "grounding_score": 0.8, "relevance_score": 0.9, "mode": "detect"},
        "rendered_markdown": "Texte rendu.",
        "trace": [{"step": 4, "name": "explanation", "actor": "agent", "status": "ok", "details": {}}],
    }


def client_error(code, operation="Op"):
    return ClientError({"Error": {"Code": code, "Message": "message brut " + FAKE_ACCOUNT}}, operation)


class FakeS3:
    """Double de client S3 : enregistre les appels, peut simuler des erreurs."""

    def __init__(self, config=None, head_error=None, put_error=None):
        self._config = ALL_BLOCKED if config is None else config
        self._head_error, self._put_error = head_error, put_error
        self.head_calls, self.puts = 0, []

    def get_public_access_block(self, Bucket):
        self.head_calls += 1
        if self._head_error:
            raise self._head_error
        return {"PublicAccessBlockConfiguration": dict(self._config)}

    def put_object(self, **kwargs):
        if self._put_error:
            raise self._put_error
        self.puts.append(kwargs)
        return {}


# ---- build_trace_document ----

def test_document_with_explanation_has_expected_keys():
    doc = build_trace_document(analysis(), explanation())
    assert doc["schema_version"] == SCHEMA_VERSION and doc["disclaimer"] == DISCLAIMER_FR
    assert doc["analysis"]["run_id"] == analysis()["run_id"]
    assert set(doc["explanation"]) == {
        "level", "origin", "model_id", "prompt_version", "attempt", "validation", "guardrail",
        "rendered_markdown", "trace"}
    assert doc["explanation"]["level"] == "novice" and doc["explanation"]["origin"] == "llm"
    assert doc["explanation"]["model_id"] == "model-test"


def test_document_without_explanation_has_no_explanation_key():
    doc = build_trace_document(analysis())
    assert "explanation" not in doc and "analysis" in doc


def test_document_masks_secrets_in_values_and_sensitive_keys():
    data = analysis()
    data["note_libre"] = f"cle {FAKE_KEY} et role {FAKE_ARN}"
    data["secret_token"] = "valeur-quelconque"
    text = json.dumps(build_trace_document(data), ensure_ascii=False)
    assert FAKE_KEY not in text and FAKE_ARN not in text and FAKE_ACCOUNT not in text
    assert "valeur-quelconque" not in text
    doc = build_trace_document(data)
    assert doc["analysis"]["secret_token"] == "[MASQUE]"


def test_document_does_not_mutate_input():
    data = analysis()
    data["note_libre"] = FAKE_KEY
    before = copy.deepcopy(data)
    build_trace_document(data)
    assert data == before


# ---- trace_key et copie locale ----

def test_trace_key_format_and_explanation_suffix():
    data = analysis()
    day = data["created_at"][:10]
    assert trace_key(build_trace_document(data)) == f"traces/{day}/{data['run_id']}.json"
    assert trace_key(build_trace_document(data, explanation("pro"))) == \
        f"traces/{day}/{data['run_id']}-explication-pro.json"
    assert trace_key(build_trace_document(data), prefix="autre") == f"autre/{day}/{data['run_id']}.json"


def test_save_local_copy_is_readable_and_sorted(tmp_path):
    doc = build_trace_document(analysis(), explanation())
    path = save_local_copy(doc, tmp_path / "traces")
    assert path.parent == tmp_path / "traces"
    assert path.name == f"{analysis()['run_id']}-explication-novice.json"
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == doc
    assert text == json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)


# ---- TraceStore ----

def test_empty_bucket_raises():
    with pytest.raises(TraceStoreError):
        TraceStore("", FakeS3())


@pytest.mark.parametrize("missing", ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"])
def test_assert_private_requires_all_four_options(missing):
    config = {**ALL_BLOCKED, missing: False}
    store = TraceStore("bucket-test", FakeS3(config))
    with pytest.raises(TraceStoreError):
        store.assert_private()


def test_assert_private_missing_option_key_counts_as_missing():
    config = {k: v for k, v in ALL_BLOCKED.items() if k != "BlockPublicPolicy"}
    with pytest.raises(TraceStoreError):
        TraceStore("bucket-test", FakeS3(config)).assert_private()


@pytest.mark.parametrize("code", ["NoSuchPublicAccessBlockConfiguration", "AccessDenied"])
def test_assert_private_client_errors_become_store_errors(code):
    store = TraceStore("bucket-test", FakeS3(head_error=client_error(code)))
    with pytest.raises(TraceStoreError) as info:
        store.assert_private()
    assert code in str(info.value) and FAKE_ACCOUNT not in str(info.value)


def test_assert_private_success_is_memorized():
    s3 = FakeS3()
    store = TraceStore("bucket-test", s3)
    doc = build_trace_document(analysis())
    store.save(doc)
    store.save(build_trace_document(analysis(), explanation()))
    assert s3.head_calls == 1 and len(s3.puts) == 2


def test_failed_check_is_not_memorized():
    s3 = FakeS3({**ALL_BLOCKED, "BlockPublicAcls": False})
    store = TraceStore("bucket-test", s3)
    for _ in range(2):
        with pytest.raises(TraceStoreError):
            store.assert_private()
    assert s3.head_calls == 2


def test_save_calls_put_object_with_encryption_and_key():
    s3 = FakeS3()
    doc = build_trace_document(analysis(), explanation())
    key = TraceStore("bucket-test", s3).save(doc)
    assert key == trace_key(doc)
    put = s3.puts[0]
    assert put["Bucket"] == "bucket-test" and put["Key"] == key
    assert put["ContentType"] == "application/json" and put["ServerSideEncryption"] == "AES256"
    assert json.loads(put["Body"].decode("utf-8")) == doc


def test_save_uses_custom_prefix():
    s3 = FakeS3()
    key = TraceStore("bucket-test", s3, prefix="demo").save(build_trace_document(analysis()))
    assert key.startswith("demo/")


def test_save_writes_nothing_if_bucket_not_private():
    s3 = FakeS3({**ALL_BLOCKED, "RestrictPublicBuckets": False})
    with pytest.raises(TraceStoreError):
        TraceStore("bucket-test", s3).save(build_trace_document(analysis()))
    assert s3.puts == []


def test_write_client_error_becomes_store_error_without_raw_message():
    s3 = FakeS3(put_error=client_error("InternalError", "PutObject"))
    with pytest.raises(TraceStoreError) as info:
        TraceStore("bucket-test", s3).save(build_trace_document(analysis()))
    message = str(info.value)
    assert "InternalError" in message and "message brut" not in message and FAKE_ACCOUNT not in message


def test_written_body_contains_no_key_or_account_number():
    data = analysis()
    data["note_libre"] = f"{FAKE_KEY} {FAKE_ARN} compte {FAKE_ACCOUNT}"
    s3 = FakeS3()
    TraceStore("bucket-test", s3).save(build_trace_document(data))
    body = s3.puts[0]["Body"].decode("utf-8")
    assert FAKE_KEY not in body and FAKE_ACCOUNT not in body and FAKE_ARN not in body
