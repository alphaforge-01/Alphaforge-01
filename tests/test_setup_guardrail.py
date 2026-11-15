"""Tests de scripts/setup_guardrail.py avec des clients simulés (aucun appel AWS)."""
from pathlib import Path
import re
import sys

import pytest
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import setup_guardrail as sg  # noqa: E402
from alphaforge.contracts import GuardrailResult, check_keys  # noqa: E402

FAKE_ACCOUNT = "0" * 12  # construit à l'exécution : aucun numéro de compte écrit dans le source
TWELVE_DIGITS = re.compile(r"(?<!\d)\d{12}(?!\d)")
NO_SLEEP = lambda seconds: None  # noqa: E731


class FakeBedrockControl:
    """Double du client ``bedrock`` qui garde un état entre les appels."""

    def __init__(self, statuses=None):
        self.guardrails = {}
        self.calls = []
        self.statuses = list(statuses or [])
        self.versions = 0

    def _arn(self, gid):
        return f"arn:aws:bedrock:us-east-1:{FAKE_ACCOUNT}:guardrail/{gid}"

    def list_guardrails(self, **kwargs):
        self.calls.append(("list_guardrails", kwargs))
        summaries = [{"id": gid, "arn": self._arn(gid), "name": g["name"], "status": "READY",
                      "version": "DRAFT"} for gid, g in self.guardrails.items()]
        if not kwargs:
            # première page : un garde-fou d'une autre équipe, puis pagination
            return {"guardrails": [{"id": "other01", "arn": self._arn("other01"),
                                    "name": "autre-garde-fou", "status": "READY",
                                    "version": "DRAFT"}], "nextToken": "p2"}
        return {"guardrails": summaries}

    def create_guardrail(self, **config):
        self.calls.append(("create_guardrail", config))
        gid = f"fakeid{len(self.guardrails) + 1}"
        self.guardrails[gid] = config
        return {"guardrailId": gid, "guardrailArn": self._arn(gid), "version": "DRAFT"}

    def update_guardrail(self, guardrailIdentifier, **config):
        self.calls.append(("update_guardrail", {"guardrailIdentifier": guardrailIdentifier, **config}))
        self.guardrails[guardrailIdentifier] = config
        return {"guardrailId": guardrailIdentifier, "guardrailArn": self._arn(guardrailIdentifier),
                "version": "DRAFT"}

    def get_guardrail(self, guardrailIdentifier, **kwargs):
        self.calls.append(("get_guardrail", {"guardrailIdentifier": guardrailIdentifier}))
        status = self.statuses.pop(0) if self.statuses else "READY"
        return {"guardrailId": guardrailIdentifier, "status": status}

    def create_guardrail_version(self, guardrailIdentifier, **kwargs):
        self.calls.append(("create_guardrail_version", {"guardrailIdentifier": guardrailIdentifier}))
        self.versions += 1
        return {"guardrailId": guardrailIdentifier, "version": str(self.versions)}

    def names(self):
        return [name for name, _ in self.calls]


class FakeRuntime:
    """Double de ``bedrock-runtime`` : refuse un texte si un mot-clé y figure."""

    TRIGGERS = {
        "order_execution": ("Achète", "courtier", "courtage"),
        "return_prediction": ("va faire", "vaudra", "garantir"),
        "personalized_advice": ("quoi acheter", "en profiter", "devrais"),
    }

    def __init__(self):
        self.requests = []

    def apply_guardrail(self, **kwargs):
        self.requests.append(kwargs)
        text = kwargs["content"][0]["text"]["text"]
        topics = [{"name": name, "type": "DENY", "action": "BLOCKED", "detected": True}
                  for name, words in self.TRIGGERS.items() if any(w in text for w in words)]
        return {
            "usage": {},
            "action": "GUARDRAIL_INTERVENED" if topics else "NONE",
            "outputs": [],
            "assessments": [{"topicPolicy": {"topics": topics}}] if topics else [],
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


def forbidden_factory(region):
    raise AssertionError("aucun client AWS ne doit être créé en mode simulation")


# --- Configuration ---------------------------------------------------------------

def test_default_config_is_valid_and_in_detection_mode():
    config = sg.build_guardrail_config()
    assert sg.validate_config(config) == []
    assert config["name"] == "alphaforge-guardrail"
    filters = config["contextualGroundingPolicyConfig"]["filtersConfig"]
    assert {f["type"] for f in filters} == {"GROUNDING", "RELEVANCE"}
    assert all(f["action"] == "NONE" and f["enabled"] for f in filters)


def test_denied_topics_are_narrow_and_documented():
    topics = sg.build_guardrail_config()["topicPolicyConfig"]["topicsConfig"]
    assert [t["name"] for t in topics] == ["personalized_advice", "order_execution",
                                          "return_prediction"]
    for topic in topics:
        assert topic["type"] == "DENY"
        assert topic["inputAction"] == "BLOCK" and topic["outputAction"] == "BLOCK"
        # definitions a l'affirmatif : pas de clause negative, que le classifieur de Bedrock traite mal
        assert "Non visé" not in topic["definition"] and "non visé" not in topic["definition"].lower()
        assert len(topic["definition"]) <= sg.MAX_TOPIC_DEFINITION
        assert all(len(example) <= 100 for example in topic["examples"])
        assert 1 <= len(topic["examples"]) <= sg.MAX_TOPIC_EXAMPLES


def test_thresholds_are_configurable_and_bounded():
    config = sg.build_guardrail_config(0.7, 0.3, "BLOCK")
    by_type = {f["type"]: f for f in config["contextualGroundingPolicyConfig"]["filtersConfig"]}
    assert by_type["GROUNDING"]["threshold"] == 0.7
    assert by_type["RELEVANCE"]["threshold"] == 0.3
    assert by_type["GROUNDING"]["action"] == "BLOCK"
    assert sg.validate_config(sg.build_guardrail_config(1.5, 0.5))


def test_blocked_messages_are_french():
    config = sg.build_guardrail_config()
    assert "simulation" in config["blockedInputMessaging"]
    assert "garde-fou" in config["blockedOutputsMessaging"]


def test_config_matches_botocore_shape():
    """Valide la configuration contre le modèle de service local (sans réseau)."""
    from botocore.session import get_session
    from botocore.validate import ParamValidator

    shape = get_session().get_service_model("bedrock").operation_model("CreateGuardrail").input_shape
    report = ParamValidator().validate(sg.build_guardrail_config(), shape)
    assert not report.has_errors(), report.generate_report()


# --- Simulation par défaut -------------------------------------------------------

def test_dry_run_is_default_and_makes_no_call(capsys):
    code = sg.main([], client_factory=forbidden_factory, environ={"AWS_REGION": "us-east-1"})
    out = capsys.readouterr().out
    assert code == sg.EXIT_OK
    assert "Mode simulation" in out and "--apply" in out


def test_invalid_threshold_stops_before_any_call():
    code = sg.main(["--apply", "--grounding-threshold", "2"], client_factory=forbidden_factory,
                   environ={"AWS_REGION": "us-east-1"})
    assert code == sg.EXIT_CONFIG_ERROR


# --- Idempotence -------------------------------------------------------------------

def test_first_apply_creates_then_second_updates():
    client = FakeBedrockControl()
    config = sg.build_guardrail_config()
    first = sg.apply_guardrail_config(client, config, sleep=NO_SLEEP)
    assert first == {"action": "created", "guardrail_id": "fakeid1", "version": "1"}
    assert client.names().count("create_guardrail") == 1

    client.calls.clear()
    second = sg.apply_guardrail_config(client, config, sleep=NO_SLEEP)
    assert second == {"action": "updated", "guardrail_id": "fakeid1", "version": "2"}
    assert "create_guardrail" not in client.names()
    assert client.names().count("update_guardrail") == 1
    assert client.names()[-1] == "create_guardrail_version"
    assert len(client.guardrails) == 1


def test_find_guardrail_paginates():
    client = FakeBedrockControl()
    client.guardrails["g1"] = {"name": "alphaforge-guardrail"}
    assert sg.find_guardrail_by_name(client, "alphaforge-guardrail")["id"] == "g1"
    assert sg.find_guardrail_by_name(client, "absent") is None


def test_wait_until_ready_polls_then_fails_on_failed():
    client = FakeBedrockControl(statuses=["CREATING", "READY"])
    sleeps = []
    assert sg.wait_until_ready(client, "g", sleep=sleeps.append) == "READY"
    assert len(sleeps) == 1
    with pytest.raises(RuntimeError):
        sg.wait_until_ready(FakeBedrockControl(statuses=["FAILED"]), "g", sleep=NO_SLEEP)


def test_apply_retries_on_throttling():
    client = FakeBedrockControl()
    original = client.create_guardrail
    state = {"n": 0}

    def flaky(**config):
        state["n"] += 1
        if state["n"] == 1:
            raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Create")
        return original(**config)

    client.create_guardrail = flaky
    result = sg.apply_guardrail_config(client, sg.build_guardrail_config(), sleep=NO_SLEEP)
    assert result["action"] == "created"


def test_main_apply_prints_id_and_version_without_arn(capsys):
    client = FakeBedrockControl()
    factory = factory_for({"bedrock": client})
    code = sg.main(["--apply"], client_factory=factory, environ={"AWS_REGION": "us-east-1"},
                   sleep=NO_SLEEP)
    out = capsys.readouterr().out
    assert code == sg.EXIT_OK
    assert "ALPHAFORGE_GUARDRAIL_ID=fakeid1" in out
    assert "ALPHAFORGE_GUARDRAIL_VERSION=1" in out
    assert "arn:" not in out and not TWELVE_DIGITS.search(out)


def test_main_apply_handles_expired_token(capsys):
    class Expired(FakeBedrockControl):
        def list_guardrails(self, **kwargs):
            raise ClientError({"Error": {"Code": "ExpiredTokenException", "Message": "x"}}, "List")

    factory = factory_for({"bedrock": Expired()})
    code = sg.main(["--apply"], client_factory=factory, environ={"AWS_REGION": "us-east-1"})
    assert code == sg.EXIT_AWS_ERROR
    assert "identifiants temporaires" in capsys.readouterr().out


# --- Mode --test ---------------------------------------------------------------------

def test_prompt_tests_table_with_fake_runtime(capsys):
    runtime = FakeRuntime()
    factory = factory_for({"bedrock-runtime": runtime})
    env = {"AWS_REGION": "us-east-1", "ALPHAFORGE_GUARDRAIL_ID": "fakeid1",
           "ALPHAFORGE_GUARDRAIL_VERSION": "1"}
    code = sg.main(["--test"], client_factory=factory, environ=env, sleep=NO_SLEEP)
    out = capsys.readouterr().out
    assert "Concordance" in out
    assert len(runtime.requests) == len(sg.load_prompts())
    assert all(r["source"] == "INPUT" and r["guardrailVersion"] == "1" for r in runtime.requests)
    assert code in (sg.EXIT_OK, sg.EXIT_TEST_MISMATCH)


def test_robert_demo_case_is_allowed_by_fake_runtime():
    prompt = next(p for p in sg.load_prompts() if p["id"] == "A01")
    row = sg.evaluate_prompt(FakeRuntime(), "g", "1", prompt, sleep=NO_SLEEP)
    assert row["obtained"] == "allowed" and row["match"]


def test_test_mode_requires_guardrail_id():
    factory = factory_for({"bedrock-runtime": FakeRuntime()})
    code = sg.main(["--test"], client_factory=factory, environ={"AWS_REGION": "us-east-1"})
    assert code == sg.EXIT_CONFIG_ERROR


def test_summarize_assessment_matches_contract():
    response = {
        "action": "GUARDRAIL_INTERVENED",
        "assessments": [{
            "topicPolicy": {"topics": [{"name": "order_execution", "type": "DENY",
                                        "action": "BLOCKED", "detected": True}]},
            "contextualGroundingPolicy": {"filters": [
                {"type": "GROUNDING", "threshold": 0.5, "score": 0.82, "action": "NONE"},
                {"type": "RELEVANCE", "threshold": 0.5, "score": 0.9, "action": "NONE"},
            ]},
        }],
    }
    result = sg.summarize_assessment(response, check="output_grounding", mode="detect")
    assert check_keys(result, GuardrailResult) == []
    assert result["action"] == "intervened"
    assert result["denied_topics"] == ["order_execution"]
    assert result["grounding_score"] == 0.82 and result["relevance_score"] == 0.9
    empty = sg.summarize_assessment({"action": "NONE", "assessments": []})
    assert empty["action"] == "none" and empty["denied_topics"] == []


# ---- niveau de classification des sujets ----

def test_classic_tier_is_opt_in_and_adds_no_cross_region_config():
    config = sg.build_guardrail_config(tier="classic")
    assert "tierConfig" not in config["topicPolicyConfig"]
    assert "crossRegionConfig" not in config
    assert "CLASSIC" in sg.describe_config(config)


def test_standard_tier_is_the_default_and_sets_the_cross_region_profile():
    config = sg.build_guardrail_config()
    assert config["topicPolicyConfig"]["tierConfig"] == {"tierName": "STANDARD"}
    assert config["crossRegionConfig"] == {"guardrailProfileIdentifier": sg.DEFAULT_GUARDRAIL_PROFILE}
    text = sg.describe_config(config)
    assert "STANDARD" in text and sg.DEFAULT_GUARDRAIL_PROFILE in text
    assert sg.validate_config(config) == []


def test_standard_tier_accepts_a_custom_profile():
    config = sg.build_guardrail_config(tier="standard", profile="eu.guardrail.v1:0")
    assert config["crossRegionConfig"]["guardrailProfileIdentifier"] == "eu.guardrail.v1:0"


def test_standard_config_matches_the_installed_boto3_model():
    from botocore.session import get_session
    # Modele du service lu directement : aucun client, donc aucune recherche d'identifiants ni appel reseau.
    shape = get_session().get_service_model("bedrock").operation_model("CreateGuardrail").input_shape
    config = sg.build_guardrail_config(tier="standard")
    assert set(config) <= set(shape.members)
    assert set(config["topicPolicyConfig"]) <= set(shape.members["topicPolicyConfig"].members)
    assert config["topicPolicyConfig"]["tierConfig"]["tierName"] in \
        shape.members["topicPolicyConfig"].members["tierConfig"].members["tierName"].enum


def test_simulation_with_standard_tier_makes_no_aws_call(capsys):
    def forbidden(region):
        raise AssertionError("aucun client AWS en simulation")

    code = sg.main([], client_factory=forbidden, environ={})
    assert code == sg.EXIT_OK
    assert "STANDARD" in capsys.readouterr().out
