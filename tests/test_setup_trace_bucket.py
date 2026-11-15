"""Tests de scripts/setup_trace_bucket.py avec des clients simulés (aucun appel AWS)."""
from pathlib import Path
import json
import re
import sys

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import setup_trace_bucket as stb  # noqa: E402

FAKE_ACCOUNT = "0" * 12  # construit à l'exécution : aucun numéro de compte écrit dans le source
OTHER_ACCOUNT = "9" * 12
FAKE_ARN = "arn:aws:sts::" + FAKE_ACCOUNT + ":assumed-role/FictionalRole/fictional-session"
TWELVE_DIGITS = re.compile(r"(?<!\d)\d{12}(?!\d)")
ENV = {"AWS_REGION": "us-east-1"}


def client_error(code, message="message fictif", operation="Op"):
    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


class FakeSts:
    def __init__(self, error=None, account=FAKE_ACCOUNT):
        self.error = error
        self.account = account

    def get_caller_identity(self):
        if self.error:
            raise self.error
        return {"Account": self.account, "Arn": FAKE_ARN}


class FakeS3:
    """Double de S3 qui garde l'état des compartiments entre deux exécutions."""

    def __init__(self):
        self.buckets = {}          # nom -> réglages du compte courant
        self.foreign = set()       # noms détenus par un autre compte
        self.calls = []
        self.error = None

    def _log(self, name, kwargs):
        self.calls.append((name, kwargs))
        if self.error:
            raise self.error

    def _bucket(self, kwargs):
        if kwargs.get("ExpectedBucketOwner") != FAKE_ACCOUNT:
            raise client_error("AccessDenied")
        return self.buckets[kwargs["Bucket"]]

    def head_bucket(self, **kwargs):
        self._log("head_bucket", kwargs)
        name = kwargs["Bucket"]
        if name in self.foreign:
            raise client_error("403")
        if name not in self.buckets:
            raise client_error("404")
        return {}

    def create_bucket(self, **kwargs):
        self._log("create_bucket", kwargs)
        if kwargs["Bucket"] in self.foreign:
            raise client_error("BucketAlreadyExists")
        # Comme S3 aujourd'hui : SSE-S3 et blocage public par défaut, rien d'autre.
        self.buckets[kwargs["Bucket"]] = {
            "encryption": "AES256", "ownership": kwargs.get("ObjectOwnership"),
            "pab": None, "policy": None, "tags": None,
        }
        return {}

    # lectures
    def get_public_access_block(self, **kwargs):
        self._log("get_public_access_block", kwargs)
        value = self._bucket(kwargs)["pab"]
        if value is None:
            raise client_error("NoSuchPublicAccessBlockConfiguration")
        return {"PublicAccessBlockConfiguration": dict(value)}

    def get_bucket_encryption(self, **kwargs):
        self._log("get_bucket_encryption", kwargs)
        value = self._bucket(kwargs)["encryption"]
        if value is None:
            raise client_error("ServerSideEncryptionConfigurationNotFoundError")
        return {"ServerSideEncryptionConfiguration": {
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": value}}]}}

    def get_bucket_policy(self, **kwargs):
        self._log("get_bucket_policy", kwargs)
        value = self._bucket(kwargs)["policy"]
        if value is None:
            raise client_error("NoSuchBucketPolicy")
        return {"Policy": value}

    def get_bucket_ownership_controls(self, **kwargs):
        self._log("get_bucket_ownership_controls", kwargs)
        value = self._bucket(kwargs)["ownership"]
        if value is None:
            raise client_error("OwnershipControlsNotFoundError")
        return {"OwnershipControls": {"Rules": [{"ObjectOwnership": value}]}}

    def get_bucket_tagging(self, **kwargs):
        self._log("get_bucket_tagging", kwargs)
        value = self._bucket(kwargs)["tags"]
        if value is None:
            raise client_error("NoSuchTagSet")
        return {"TagSet": list(value)}

    # écritures
    def put_public_access_block(self, **kwargs):
        self._log("put_public_access_block", kwargs)
        self._bucket(kwargs)["pab"] = dict(kwargs["PublicAccessBlockConfiguration"])

    def put_bucket_encryption(self, **kwargs):
        self._log("put_bucket_encryption", kwargs)
        rule = kwargs["ServerSideEncryptionConfiguration"]["Rules"][0]
        self._bucket(kwargs)["encryption"] = rule["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]

    def put_bucket_policy(self, **kwargs):
        self._log("put_bucket_policy", kwargs)
        self._bucket(kwargs)["policy"] = kwargs["Policy"]

    def put_bucket_ownership_controls(self, **kwargs):
        self._log("put_bucket_ownership_controls", kwargs)
        self._bucket(kwargs)["ownership"] = kwargs["OwnershipControls"]["Rules"][0]["ObjectOwnership"]

    def put_bucket_tagging(self, **kwargs):
        self._log("put_bucket_tagging", kwargs)
        self._bucket(kwargs)["tags"] = list(kwargs["Tagging"]["TagSet"])

    def names(self):
        return [name for name, _ in self.calls]

    def kwargs_of(self, name):
        return [kwargs for call, kwargs in self.calls if call == name]


def factory(s3, sts=None, created=None):
    sts = sts or FakeSts()

    def make(region):
        assert region == "us-east-1"
        if created is not None:
            created.append(region)
        return lambda service: {"s3": s3, "sts": sts}[service]
    return make


EXPECTED_NAME = stb.bucket_name(stb.derive_suffix(FAKE_ACCOUNT))


def assert_no_account(text):
    assert FAKE_ACCOUNT not in text
    assert not TWELVE_DIGITS.search(text)
    assert "FictionalRole" not in text  # le type de principal peut rester, jamais son nom
    assert "fictional-session" not in text


# ---------------------------------------------------------------------------
# Nom et suffixe
# ---------------------------------------------------------------------------

def test_derived_suffix_is_stable_and_hides_account():
    first = stb.derive_suffix(FAKE_ACCOUNT)
    assert first == stb.derive_suffix(FAKE_ACCOUNT)
    assert re.fullmatch(r"[0-9a-f]{8}", first)
    assert first != stb.derive_suffix(OTHER_ACCOUNT)
    assert FAKE_ACCOUNT not in stb.bucket_name(first)
    assert stb.bucket_name(first).startswith("alphaforge-traces-")


@pytest.mark.parametrize("suffix", ["", "UPPER", "-bad", "bad-", "a_b", "x" * 60, "1" * 12])
def test_invalid_suffix_is_refused(suffix, capsys):
    assert stb.validate_suffix(suffix) is not None
    assert stb.main(["--suffix=" + suffix], environ=ENV) == stb.EXIT_CONFIG_ERROR


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def test_dry_run_creates_no_client_and_calls_nothing(capsys, monkeypatch):
    import boto3

    def forbidden(*args, **kwargs):
        raise AssertionError("aucun client AWS en simulation")
    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(boto3, "Session", forbidden)
    created = []
    s3 = FakeS3()
    assert stb.main([], client_factory=factory(s3, created=created), environ=ENV) == stb.EXIT_OK
    assert created == []
    assert s3.calls == []
    out = capsys.readouterr().out
    assert "simulation" in out
    assert "Block Public Access" in out


def test_dry_run_with_suffix_shows_name_and_env_reminder(capsys):
    assert stb.main(["--suffix", "demo01"], environ=ENV) == stb.EXIT_OK
    out = capsys.readouterr().out
    assert "alphaforge-traces-demo01" in out
    assert "ALPHAFORGE_TRACE_BUCKET=alphaforge-traces-demo01" in out


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def test_first_apply_creates_then_second_apply_creates_nothing(capsys):
    s3 = FakeS3()
    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    assert s3.names().count("create_bucket") == 1
    create = s3.kwargs_of("create_bucket")[0]
    assert create["Bucket"] == EXPECTED_NAME
    assert "CreateBucketConfiguration" not in create  # us-east-1 : pas de LocationConstraint
    first_out = capsys.readouterr().out
    assert "créé" in first_out
    assert f"ALPHAFORGE_TRACE_BUCKET={EXPECTED_NAME}" in first_out

    s3.calls.clear()
    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    assert "create_bucket" not in s3.names()
    assert not [n for n in s3.names() if n.startswith("put_")]
    assert "Aucun réglage à corriger" in capsys.readouterr().out


def test_apply_requests_the_four_flags_encryption_and_tls_policy():
    s3 = FakeS3()
    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    pab = s3.kwargs_of("put_public_access_block")[0]["PublicAccessBlockConfiguration"]
    assert pab == {"BlockPublicAcls": True, "IgnorePublicAcls": True,
                   "BlockPublicPolicy": True, "RestrictPublicBuckets": True}
    policy = json.loads(s3.kwargs_of("put_bucket_policy")[0]["Policy"])
    statement = policy["Statement"][0]
    assert statement["Effect"] == "Deny"
    assert statement["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}
    assert statement["Action"] == "s3:*"
    assert all(":::" + EXPECTED_NAME in r for r in statement["Resource"])
    assert not any(s["Effect"] == "Allow" for s in policy["Statement"])
    tags = s3.kwargs_of("put_bucket_tagging")[0]["Tagging"]["TagSet"]
    assert {"Key": "Project", "Value": "alphaforge"} in tags
    # le blocage public passe avant la politique
    names = s3.names()
    assert names.index("put_public_access_block") < names.index("put_bucket_policy")
    # chiffrement déjà présent (SSE-S3 par défaut) : pas réécrit
    assert "put_bucket_encryption" not in names
    assert all(kw.get("ExpectedBucketOwner") == FAKE_ACCOUNT
               for name, kw in s3.calls if name.startswith(("put_", "get_")))


def test_missing_encryption_is_set_to_sse_s3():
    s3 = FakeS3()
    stb.main(["--apply"], client_factory=factory(s3), environ=ENV)
    s3.buckets[EXPECTED_NAME]["encryption"] = None
    s3.calls.clear()
    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    config = s3.kwargs_of("put_bucket_encryption")[0]["ServerSideEncryptionConfiguration"]
    assert config["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"


def test_fix_only_missing_setting_without_deleting_anything():
    s3 = FakeS3()
    stb.main(["--apply"], client_factory=factory(s3), environ=ENV)
    bucket = s3.buckets[EXPECTED_NAME]
    other_statement = {"Sid": "TeamRead", "Effect": "Deny", "Principal": "*", "Action": "s3:DeleteBucket",
                       "Resource": "arn:aws:s3:::" + EXPECTED_NAME}
    bucket["policy"] = json.dumps({"Version": "2012-10-17", "Statement": [other_statement]})
    bucket["tags"] = [{"Key": "Owner", "Value": "flux-c"}]
    bucket["pab"]["RestrictPublicBuckets"] = False
    s3.calls.clear()

    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    puts = [n for n in s3.names() if n.startswith("put_")]
    assert sorted(puts) == ["put_bucket_policy", "put_bucket_tagging", "put_public_access_block"]
    assert not [n for n in s3.names() if n.startswith("delete")]
    policy = json.loads(bucket["policy"])
    assert other_statement in policy["Statement"]
    assert len(policy["Statement"]) == 2
    assert {"Key": "Owner", "Value": "flux-c"} in bucket["tags"]
    assert {"Key": "Project", "Value": "alphaforge"} in bucket["tags"]
    assert all(bucket["pab"].values())


def test_bucket_owned_by_other_account_is_refused(capsys):
    s3 = FakeS3()
    s3.foreign.add(EXPECTED_NAME)
    code = stb.main(["--apply"], client_factory=factory(s3), environ=ENV)
    assert code == stb.EXIT_BUCKET_CONFLICT
    assert "create_bucket" not in s3.names()
    assert not [n for n in s3.names() if n.startswith("put_")]
    out = capsys.readouterr().out
    assert "n'appartient pas" in out
    assert_no_account(out)


def test_race_on_create_with_foreign_owner_is_refused():
    s3 = FakeS3()

    def create(**kwargs):  # absent au head_bucket, pris par un autre compte juste avant la création
        s3.calls.append(("create_bucket", kwargs))
        raise client_error("BucketAlreadyExists")
    s3.create_bucket = create
    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_BUCKET_CONFLICT
    assert not [n for n in s3.names() if n.startswith("put_")]


# ---------------------------------------------------------------------------
# Vérification en lecture seule
# ---------------------------------------------------------------------------

def test_check_is_read_only_and_flags_missing_settings(capsys):
    s3 = FakeS3()
    assert stb.main(["--check"], client_factory=factory(s3), environ=ENV) == stb.EXIT_CHECK_FAILED
    assert "absent" in capsys.readouterr().out

    stb.main(["--apply"], client_factory=factory(s3), environ=ENV)
    s3.buckets[EXPECTED_NAME]["ownership"] = "ObjectWriter"
    s3.calls.clear()
    assert stb.main(["--check"], client_factory=factory(s3), environ=ENV) == stb.EXIT_CHECK_FAILED
    assert not [n for n in s3.names() if n.startswith(("put_", "create", "delete"))]
    out = capsys.readouterr().out
    assert "MANQUANT" in out and "ObjectWriter" in out


def test_check_ok_when_everything_is_configured(capsys):
    s3 = FakeS3()
    stb.main(["--apply"], client_factory=factory(s3), environ=ENV)
    capsys.readouterr()
    assert stb.main(["--check"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    out = capsys.readouterr().out
    assert "conformes" in out
    assert out.count(": ok") == 5


def test_kms_encryption_is_accepted_not_downgraded():
    s3 = FakeS3()
    stb.main(["--apply"], client_factory=factory(s3), environ=ENV)
    s3.buckets[EXPECTED_NAME]["encryption"] = "aws:kms"
    s3.calls.clear()
    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    assert "put_bucket_encryption" not in s3.names()


# ---------------------------------------------------------------------------
# Confidentialité et erreurs
# ---------------------------------------------------------------------------

def test_account_and_arn_never_printed(capsys):
    s3 = FakeS3()
    for argv in (["--apply"], ["--check"], ["--apply"]):
        stb.main(argv, client_factory=factory(s3), environ=ENV)
    assert_no_account(capsys.readouterr().out)


def test_custom_suffix_is_used():
    s3 = FakeS3()
    assert stb.main(["--apply", "--suffix", "demo01"], client_factory=factory(s3), environ=ENV) == stb.EXIT_OK
    assert "alphaforge-traces-demo01" in s3.buckets


def test_wrong_region_is_refused_before_any_client():
    created = []
    code = stb.main(["--apply"], client_factory=factory(FakeS3(), created=created),
                    environ={"AWS_REGION": "eu-west-1"})
    assert code == stb.EXIT_CONFIG_ERROR
    assert created == []


@pytest.mark.parametrize("code", ["ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"])
def test_credential_errors_give_french_message(code, capsys):
    sts = FakeSts(error=client_error(code, "jeton " + FAKE_ARN))
    s3 = FakeS3()
    assert stb.main(["--apply"], client_factory=factory(s3, sts), environ=ENV) == stb.EXIT_AWS_ERROR
    out = capsys.readouterr().out
    assert "Identifiants AWS expirés ou invalides" in out
    assert_no_account(out)
    assert s3.calls == []


def test_access_denied_on_s3_is_masked(capsys):
    s3 = FakeS3()
    s3.error = client_error("AccessDenied", "User: " + FAKE_ARN + " is not authorized")
    assert stb.main(["--apply"], client_factory=factory(s3), environ=ENV) == stb.EXIT_AWS_ERROR
    out = capsys.readouterr().out
    assert "Accès refusé" in out
    assert_no_account(out)


def test_missing_credentials(capsys):
    sts = FakeSts(error=NoCredentialsError())
    assert stb.main(["--check"], client_factory=factory(FakeS3(), sts), environ=ENV) == stb.EXIT_AWS_ERROR
    assert "Aucun identifiant AWS" in capsys.readouterr().out
