import copy
import hashlib
import json
import shutil
import uuid
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from science_repo.cohort_freeze import STATIC_RUNTIME_IDENTITY_FIELDS, build_cohort_freeze
from science_repo.cli import cmd_local_dispatch_accept
from science_repo.harness_receipt import HarnessReceipt
from science_repo.local_dispatch_acceptance import (
    LocalDispatchAcceptanceError, NON_CLAIMS, build_local_dispatch_acceptance,
    verify_local_dispatch_acceptance, verify_local_dispatch_policy,
)
from science_repo.subject_packets import build_subject_packet_set


NOW = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
HEAD = "1" * 40


@pytest.fixture
def tmp_path():
    """Use a workspace-local root; the host temp root can be ACL-restricted."""
    path = Path.cwd() / f".tmp-local-acceptance-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _study(root: Path):
    fixtures = []
    for index in range(12):
        path = root / f"f{index}"; path.mkdir()
        (path / "prompt.txt").write_text(f"task {index}\n", encoding="utf-8")
        fixtures.append((f"F{index}", path))
    baseline = root / "baseline.txt"; baseline.write_text("baseline\n", encoding="utf-8")
    identity = {key: f"known-{key}" for key in STATIC_RUNTIME_IDENTITY_FIELDS}
    identity_bytes = (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    source = {"receipt_id":"r", "authority_id":"a", "source":"host", "issued_at":"now",
              "identity_sha256":hashlib.sha256(identity_bytes).hexdigest()}
    freeze = build_cohort_freeze(cohort_id="C", registration_root=root, fixtures=fixtures,
        baseline_materials=[baseline], human_supplied_seed="human", runtime_identity=identity,
        runtime_identity_receipt=source)
    packet_set = build_subject_packet_set(freeze=freeze, source_root=root)
    packet = packet_set["packets"][0]
    cwd = root / packet["workspace_contract"]["cwd"]; cwd.mkdir(parents=True)
    return freeze, packet_set, packet, cwd


def _policy(**changes):
    value = {
        "schema_version":1, "policy_id":"local-v1", "cohort_id":"C",
        "mode":"local-host-observed-unsigned", "selected_at":"2026-07-13T09:00:00Z",
        "expires_at":"2026-07-13T12:00:00Z", "required_head_commit":HEAD,
        "maximum_acceptance_seconds":600,
        "allowed_scope":{"local_repository":True,"network":False,"private_data":False,
                         "external_compute":False,"cost_bearing":False,"instruments":False,"publication":False},
        "non_claims":list(NON_CLAIMS),
    }
    value.update(changes)
    value["policy_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return value


def _receipt(*, child=True, session="native-session-7"):
    return HarnessReceipt(receipt_id="hr-1", generated_at="2026-07-13T09:59:00Z",
        session_id=session, session_id_unavailable_reason=None, child_session=child,
        provider=None, model_name="requested-alias", exact_model_or_version_id=None,
        model_unavailable_reason=None, agent_harness_and_version="harness/1",
        harness_unavailable_reason=None, effort_setting="medium",
        effort_unavailable_reason=None).to_dict()


def _build(root: Path, **overrides):
    freeze, packet_set, packet, cwd = _study(root)
    args = dict(policy=_policy(), freeze=freeze, packet_set=packet_set, cell_id=packet["cell_id"],
                harness_receipt=_receipt(), native_agent_id="host-agent-9",
                observed_cwd=str(cwd.resolve()), observed_head_commit=HEAD, now=NOW)
    args.update(overrides)
    return build_local_dispatch_acceptance(**args), args


def test_build_and_verify_acceptance_keeps_preparation_fail_closed(tmp_path):
    acceptance, args = _build(tmp_path)
    assert args["freeze"]["dispatch_allowed"] is False
    assert args["packet_set"]["dispatch_allowed"] is False
    assert acceptance["status"] == "accepted-for-local-dispatch-under-unsigned-policy"
    assert acceptance["planned_identity"]["logical_session_id"] != acceptance["observed_identity"]["harness_session_id"]
    assert acceptance["boundary"]["non_claims"] == NON_CLAIMS
    assert verify_local_dispatch_acceptance(acceptance, policy=args["policy"], freeze=args["freeze"],
        packet_set=args["packet_set"], harness_receipt=args["harness_receipt"], now=NOW) == acceptance


@pytest.mark.parametrize("field,value,match", [
    ("native_agent_id", "", "native_agent_id"),
    ("observed_head_commit", "2" * 40, "HEAD"),
])
def test_rejects_missing_native_agent_or_wrong_head(tmp_path, field, value, match):
    freeze, packet_set, packet, cwd = _study(tmp_path)
    args = dict(policy=_policy(), freeze=freeze, packet_set=packet_set, cell_id=packet["cell_id"],
                harness_receipt=_receipt(), native_agent_id="agent", observed_cwd=str(cwd.resolve()),
                observed_head_commit=HEAD, now=NOW)
    args[field] = value
    with pytest.raises(LocalDispatchAcceptanceError, match=match):
        build_local_dispatch_acceptance(**args)


def test_rejects_non_child_and_logical_observed_session_conflation(tmp_path):
    freeze, packet_set, packet, cwd = _study(tmp_path)
    common = dict(policy=_policy(), freeze=freeze, packet_set=packet_set, cell_id=packet["cell_id"],
                  native_agent_id="agent", observed_cwd=str(cwd.resolve()), observed_head_commit=HEAD, now=NOW)
    with pytest.raises(LocalDispatchAcceptanceError, match="child session"):
        build_local_dispatch_acceptance(harness_receipt=_receipt(child=False), **common)
    with pytest.raises(LocalDispatchAcceptanceError, match="conflated"):
        build_local_dispatch_acceptance(harness_receipt=_receipt(session=packet["session_id"]), **common)


def test_policy_scope_and_expiry_fail_closed():
    expanded = _policy(allowed_scope={"local_repository":True,"network":True,"private_data":False,
        "external_compute":False,"cost_bearing":False,"instruments":False,"publication":False})
    with pytest.raises(LocalDispatchAcceptanceError, match="scope exceeds"):
        verify_local_dispatch_policy(expanded, now=NOW)
    with pytest.raises(LocalDispatchAcceptanceError, match="not currently valid"):
        verify_local_dispatch_policy(_policy(expires_at="2026-07-13T09:30:00Z"), now=NOW)


def test_tamper_cross_cell_and_expired_acceptance_are_rejected(tmp_path):
    acceptance, args = _build(tmp_path)
    tampered = copy.deepcopy(acceptance); tampered["observed_identity"]["native_agent_id"] = "other"
    with pytest.raises(LocalDispatchAcceptanceError, match="acceptance_sha256"):
        verify_local_dispatch_acceptance(tampered, policy=args["policy"], freeze=args["freeze"],
            packet_set=args["packet_set"], harness_receipt=args["harness_receipt"], now=NOW)
    replay = copy.deepcopy(acceptance); replay["bindings"]["cell_id"] = args["packet_set"]["packets"][1]["cell_id"]
    unsigned = dict(replay); unsigned.pop("acceptance_sha256")
    replay["acceptance_sha256"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(LocalDispatchAcceptanceError, match="bindings mismatch"):
        verify_local_dispatch_acceptance(replay, policy=args["policy"], freeze=args["freeze"],
            packet_set=args["packet_set"], harness_receipt=args["harness_receipt"], now=NOW)
    with pytest.raises(LocalDispatchAcceptanceError, match="expired"):
        verify_local_dispatch_acceptance(acceptance, policy=args["policy"], freeze=args["freeze"],
            packet_set=args["packet_set"], harness_receipt=args["harness_receipt"], now=NOW + timedelta(minutes=11))


@pytest.mark.parametrize("field", ["harness_and_version", "requested_model_alias", "claimed_effort"])
def test_verify_rebinds_receipt_derived_observations_even_after_public_rehash(tmp_path, field):
    acceptance, args = _build(tmp_path)
    tampered = copy.deepcopy(acceptance)
    tampered["observed_identity"][field] = "forged"
    unsigned = dict(tampered); unsigned.pop("acceptance_sha256")
    tampered["acceptance_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(LocalDispatchAcceptanceError, match="observed session binding"):
        verify_local_dispatch_acceptance(
            tampered, policy=args["policy"], freeze=args["freeze"],
            packet_set=args["packet_set"], harness_receipt=args["harness_receipt"], now=NOW,
        )


@pytest.mark.parametrize(
    "accepted_at,expires_at",
    [
        ("2026-07-13T10:01:00Z", "2026-07-13T10:11:00Z"),
        ("2026-07-13T10:00:00Z", "2026-07-13T11:00:00Z"),
    ],
)
def test_verify_rejects_publicly_rehashed_time_extension(tmp_path, accepted_at, expires_at):
    acceptance, args = _build(tmp_path)
    tampered = copy.deepcopy(acceptance)
    tampered["accepted_at"] = accepted_at
    tampered["expires_at"] = expires_at
    seed = {
        "policy": tampered["policy"]["policy_sha256"], "bindings": tampered["bindings"],
        "receipt": tampered["evidence"]["harness_receipt_sha256"],
        "observed": tampered["observed_identity"], "accepted_at": accepted_at,
    }
    tampered["acceptance_id"] = "local-" + hashlib.sha256(
        json.dumps(seed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
    unsigned = dict(tampered); unsigned.pop("acceptance_sha256")
    tampered["acceptance_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(LocalDispatchAcceptanceError, match="expired|policy-bound lifetime"):
        verify_local_dispatch_acceptance(
            tampered, policy=args["policy"], freeze=args["freeze"],
            packet_set=args["packet_set"], harness_receipt=args["harness_receipt"], now=NOW,
        )


def test_cli_requires_digest_confirmation_and_refuses_overwrite(tmp_path, capsys):
    (tmp_path / "science-project.yaml").write_text("id: local-test\n", encoding="utf-8")
    freeze, packet_set, packet, cwd = _study(tmp_path)
    policy = _policy(selected_at="2026-01-01T00:00:00Z", expires_at="2099-01-01T00:00:00Z")
    for name, value in (("policy.json", policy), ("freeze.json", freeze),
                        ("packets.json", packet_set), ("receipt.json", _receipt())):
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    args = Namespace(project=str(tmp_path), policy="policy.json", freeze="freeze.json",
        packet_set="packets.json", receipt="receipt.json", cell=packet["cell_id"],
        native_agent_id="native-1", observed_cwd=str(cwd.resolve()), observed_head=HEAD,
        confirm_policy_sha256="0" * 64, output="acceptance.json")
    assert cmd_local_dispatch_accept(args) == 2
    assert "confirmed policy digest" in capsys.readouterr().err
    args.confirm_policy_sha256 = policy["policy_sha256"]
    assert cmd_local_dispatch_accept(args) == 0
    assert (tmp_path / "acceptance.json").is_file()
    capsys.readouterr()
    assert cmd_local_dispatch_accept(args) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
