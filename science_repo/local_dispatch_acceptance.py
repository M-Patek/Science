"""Explicit, unsigned local-dispatch acceptance without trust escalation.

This module is the weaker of two deliberately separate trust tracks.  It may
accept process-environment claims and main-agent observations for a narrowly
bounded local study.  It never produces a trusted attestation, human
authorization, provider identity, or proof of isolation.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .harness_receipt import HarnessReceiptError, verify_receipt


class LocalDispatchAcceptanceError(ValueError):
    """A local policy or acceptance is malformed, stale, or misbound."""


NON_CLAIMS = [
    "provider_identity",
    "immutable_model_build",
    "prompt_identity",
    "toolchain_completeness",
    "network_enforcement",
    "permission_enforcement",
    "context_isolation",
    "absolute_worktree_isolation",
]

_LOCAL_SCOPE = {
    "local_repository": True,
    "network": False,
    "private_data": False,
    "external_compute": False,
    "cost_bearing": False,
    "instruments": False,
    "publication": False,
}
_POLICY_FIELDS = {
    "schema_version", "policy_id", "cohort_id", "mode", "selected_at",
    "expires_at", "required_head_commit", "maximum_acceptance_seconds",
    "allowed_scope", "non_claims", "policy_sha256",
}
_ACCEPTANCE_FIELDS = {
    "schema_version", "acceptance_id", "status", "evidence_level",
    "accepted_at", "expires_at", "policy", "bindings", "planned_identity",
    "observed_identity", "evidence", "scope", "boundary", "acceptance_sha256",
}
_HEX = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def _canonical(value: Any, *, newline: bool = False) -> bytes:
    try:
        suffix = "\n" if newline else ""
        return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False) + suffix).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise LocalDispatchAcceptanceError("artifact must be canonically JSON serializable") from error


def _hash(value: Any, *, newline: bool = False) -> str:
    return hashlib.sha256(_canonical(value, newline=newline)).hexdigest()


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise LocalDispatchAcceptanceError(f"{field} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LocalDispatchAcceptanceError(f"{field} must be a timezone-aware ISO timestamp") from error
    if parsed.tzinfo is None:
        raise LocalDispatchAcceptanceError(f"{field} must be a timezone-aware ISO timestamp")
    return parsed


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _embedded_hash(artifact: Mapping[str, Any], field: str) -> str:
    claimed = artifact.get(field)
    if not isinstance(claimed, str) or not _HEX.fullmatch(claimed):
        raise LocalDispatchAcceptanceError(f"{field} must be lowercase SHA-256 hex")
    unsigned = dict(artifact)
    unsigned.pop(field, None)
    if claimed != _hash(unsigned, newline=True):
        raise LocalDispatchAcceptanceError(f"{field} does not match canonical content")
    return claimed


def verify_local_dispatch_policy(policy: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Validate an explicit local-only policy and its self-hash."""
    if set(policy) != _POLICY_FIELDS or policy.get("schema_version") != 1:
        raise LocalDispatchAcceptanceError("local dispatch policy fields or version mismatch")
    for field in ("policy_id", "cohort_id"):
        if not isinstance(policy.get(field), str) or not policy[field]:
            raise LocalDispatchAcceptanceError(f"policy {field} must be a non-empty string")
    if policy.get("mode") != "local-host-observed-unsigned":
        raise LocalDispatchAcceptanceError("unsupported local dispatch policy mode")
    if policy.get("allowed_scope") != _LOCAL_SCOPE:
        raise LocalDispatchAcceptanceError("policy scope exceeds local unsigned acceptance")
    if policy.get("non_claims") != NON_CLAIMS:
        raise LocalDispatchAcceptanceError("policy must preserve every required non-claim")
    head = policy.get("required_head_commit")
    if not isinstance(head, str) or not _COMMIT.fullmatch(head):
        raise LocalDispatchAcceptanceError("required_head_commit must be a full Git object id")
    seconds = policy.get("maximum_acceptance_seconds")
    if not isinstance(seconds, int) or isinstance(seconds, bool) or not 1 <= seconds <= 86400:
        raise LocalDispatchAcceptanceError("maximum_acceptance_seconds must be between 1 and 86400")
    selected = _timestamp(policy.get("selected_at"), "selected_at")
    expiry = _timestamp(policy.get("expires_at"), "expires_at")
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None or selected > instant or expiry <= instant or expiry <= selected:
        raise LocalDispatchAcceptanceError("local dispatch policy is not currently valid")
    claimed = policy.get("policy_sha256")
    unsigned = dict(policy); unsigned.pop("policy_sha256", None)
    if not isinstance(claimed, str) or claimed != _hash(unsigned):
        raise LocalDispatchAcceptanceError("policy_sha256 does not match canonical content")
    return json.loads(json.dumps(dict(policy), sort_keys=True))


def _select_packet(freeze: Mapping[str, Any], packet_set: Mapping[str, Any], cell_id: str) -> tuple[dict[str, Any], str, str]:
    freeze_sha = _embedded_hash(freeze, "freeze_sha256")
    packet_set_sha = _embedded_hash(packet_set, "packet_set_sha256")
    if freeze.get("dispatch_allowed") is not False or packet_set.get("dispatch_allowed") is not False:
        raise LocalDispatchAcceptanceError("frozen preparation artifacts must remain dispatch-blocked")
    if packet_set.get("host_enforcement") != "unverified":
        raise LocalDispatchAcceptanceError("packet set must not claim verified host enforcement")
    if packet_set.get("cohort_id") != freeze.get("cohort_id") or packet_set.get("freeze_sha256") != freeze_sha:
        raise LocalDispatchAcceptanceError("packet set is not bound to the supplied cohort freeze")
    packets = packet_set.get("packets")
    matches = [item for item in packets if isinstance(item, dict) and item.get("cell_id") == cell_id] if isinstance(packets, list) else []
    if len(matches) != 1:
        raise LocalDispatchAcceptanceError("cell_id must select exactly one subject packet")
    packet = matches[0]
    packet_sha = packet.get("packet_sha256")
    unsigned = dict(packet); unsigned.pop("packet_sha256", None)
    if not isinstance(packet_sha, str) or packet_sha != _hash(unsigned, newline=True):
        raise LocalDispatchAcceptanceError("packet_sha256 does not match canonical content")
    if packet.get("dispatch_allowed") is not False:
        raise LocalDispatchAcceptanceError("subject packet must remain dispatch-blocked")
    workspace = packet.get("workspace_contract")
    if not isinstance(workspace, dict) or workspace.get("network_required") is not False:
        raise LocalDispatchAcceptanceError("local unsigned acceptance forbids network-requiring packets")
    if workspace.get("dedicated_worktree_required") is not True or workspace.get("fork_context_required") != "none":
        raise LocalDispatchAcceptanceError("packet does not require the local study isolation preconditions")
    return packet, freeze_sha, packet_set_sha


def _validate_observed_cwd(observed_cwd: str, logical_cwd: str) -> str:
    if not isinstance(observed_cwd, str) or not observed_cwd:
        raise LocalDispatchAcceptanceError("observed_cwd must be a non-empty absolute path")
    path = Path(observed_cwd)
    if not path.is_absolute() or not path.is_dir():
        raise LocalDispatchAcceptanceError("observed_cwd must name an existing absolute directory")
    actual = PurePosixPath(path.resolve().as_posix())
    expected = PurePosixPath(logical_cwd)
    if not expected.parts or ".." in expected.parts or tuple(actual.parts[-len(expected.parts):]) != expected.parts:
        raise LocalDispatchAcceptanceError("observed_cwd does not match the packet workspace binding")
    return path.resolve().as_posix()


def build_local_dispatch_acceptance(
    *, policy: Mapping[str, Any], freeze: Mapping[str, Any], packet_set: Mapping[str, Any],
    cell_id: str, harness_receipt: Mapping[str, Any], native_agent_id: str,
    observed_cwd: str, observed_head_commit: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Build a short-lived, cell-specific overlay after bootstrap observation."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise LocalDispatchAcceptanceError("acceptance time must be timezone-aware")
    checked_policy = verify_local_dispatch_policy(policy, now=instant)
    packet, freeze_sha, packet_set_sha = _select_packet(freeze, packet_set, cell_id)
    if checked_policy["cohort_id"] != freeze.get("cohort_id"):
        raise LocalDispatchAcceptanceError("policy cohort binding mismatch")
    if not isinstance(native_agent_id, str) or not native_agent_id.strip():
        raise LocalDispatchAcceptanceError("native_agent_id must be a non-empty host observation")
    if observed_head_commit != checked_policy["required_head_commit"]:
        raise LocalDispatchAcceptanceError("observed HEAD does not match the policy-pinned commit")
    logical_cwd = packet["workspace_contract"].get("cwd")
    normalized_cwd = _validate_observed_cwd(observed_cwd, logical_cwd)
    try:
        receipt = verify_receipt(harness_receipt)
    except HarnessReceiptError as error:
        raise LocalDispatchAcceptanceError(f"harness receipt is invalid: {error}") from error
    if receipt.child_session is not True:
        raise LocalDispatchAcceptanceError("bootstrap receipt must observe a child session")
    for name in ("session_id", "model_name", "agent_harness_and_version", "effort_setting"):
        if getattr(receipt, name) is None:
            raise LocalDispatchAcceptanceError(f"bootstrap receipt is missing required observation: {name}")
    if receipt.session_id == packet.get("session_id"):
        raise LocalDispatchAcceptanceError("observed harness session must not be conflated with logical session id")
    policy_expiry = _timestamp(checked_policy["expires_at"], "expires_at")
    expiry = min(policy_expiry, instant + timedelta(seconds=checked_policy["maximum_acceptance_seconds"]))
    bindings = {
        "cohort_id": freeze["cohort_id"], "freeze_sha256": freeze_sha,
        "packet_set_sha256": packet_set_sha, "packet_sha256": packet["packet_sha256"],
        "cell_id": cell_id, "attempt_ordinal": packet["attempt_ordinal"],
    }
    observed = {
        "native_agent_id": native_agent_id.strip(), "harness_session_id": receipt.session_id,
        "child_session": True, "harness_and_version": receipt.agent_harness_and_version,
        "requested_model_alias": receipt.model_name, "claimed_effort": receipt.effort_setting,
        "cwd": normalized_cwd, "head_commit": observed_head_commit,
    }
    seed = {"policy": checked_policy["policy_sha256"], "bindings": bindings,
            "receipt": receipt.receipt_sha256, "observed": observed, "accepted_at": _iso(instant)}
    result: dict[str, Any] = {
        "schema_version": 1, "acceptance_id": f"local-{_hash(seed)[:24]}",
        "status": "accepted-for-local-dispatch-under-unsigned-policy",
        "evidence_level": "host-observed-unsigned", "accepted_at": _iso(instant),
        "expires_at": _iso(expiry),
        "policy": {"policy_id": checked_policy["policy_id"], "policy_sha256": checked_policy["policy_sha256"]},
        "bindings": bindings,
        "planned_identity": {"logical_session_id": packet["session_id"], "worktree_id": packet["worktree_id"], "context_id": packet["context_id"]},
        "observed_identity": observed,
        "evidence": {"harness_receipt_id": receipt.receipt_id, "harness_receipt_sha256": receipt.receipt_sha256,
                     "process_environment_claims": True, "main_agent_host_observations": True},
        "scope": dict(_LOCAL_SCOPE),
        "boundary": {"workspace_preconditions": "main-agent-observed-not-isolation-proof", "non_claims": list(NON_CLAIMS)},
    }
    result["acceptance_sha256"] = _hash(result)
    return result


def verify_local_dispatch_acceptance(
    acceptance: Mapping[str, Any], *, policy: Mapping[str, Any], freeze: Mapping[str, Any],
    packet_set: Mapping[str, Any], harness_receipt: Mapping[str, Any], now: datetime | None = None,
) -> dict[str, Any]:
    """Rebind an acceptance to all source artifacts and reject expiry/tampering."""
    if set(acceptance) != _ACCEPTANCE_FIELDS or acceptance.get("schema_version") != 1:
        raise LocalDispatchAcceptanceError("local dispatch acceptance fields or version mismatch")
    claimed = acceptance.get("acceptance_sha256")
    unsigned = dict(acceptance); unsigned.pop("acceptance_sha256", None)
    if not isinstance(claimed, str) or claimed != _hash(unsigned):
        raise LocalDispatchAcceptanceError("acceptance_sha256 does not match canonical content")
    instant = now or datetime.now(timezone.utc)
    accepted_at = _timestamp(acceptance.get("accepted_at"), "accepted_at")
    expires_at = _timestamp(acceptance.get("expires_at"), "expires_at")
    if instant.tzinfo is None or accepted_at > instant or expires_at <= instant:
        raise LocalDispatchAcceptanceError("local dispatch acceptance is expired")
    if acceptance.get("status") != "accepted-for-local-dispatch-under-unsigned-policy" or acceptance.get("evidence_level") != "host-observed-unsigned":
        raise LocalDispatchAcceptanceError("acceptance status or evidence level mismatch")
    checked_policy = verify_local_dispatch_policy(policy, now=instant)
    policy_selected = _timestamp(checked_policy["selected_at"], "selected_at")
    policy_expiry = _timestamp(checked_policy["expires_at"], "expires_at")
    expected_expiry = min(
        policy_expiry,
        accepted_at + timedelta(seconds=checked_policy["maximum_acceptance_seconds"]),
    )
    if accepted_at < policy_selected or expires_at != expected_expiry:
        raise LocalDispatchAcceptanceError("acceptance timestamps exceed the policy-bound lifetime")
    if acceptance.get("policy") != {"policy_id": checked_policy["policy_id"], "policy_sha256": checked_policy["policy_sha256"]}:
        raise LocalDispatchAcceptanceError("acceptance policy binding mismatch")
    bindings = acceptance.get("bindings")
    if not isinstance(bindings, dict):
        raise LocalDispatchAcceptanceError("acceptance bindings must be an object")
    packet, freeze_sha, packet_set_sha = _select_packet(freeze, packet_set, bindings.get("cell_id"))
    expected_bindings = {"cohort_id": freeze["cohort_id"], "freeze_sha256": freeze_sha,
                         "packet_set_sha256": packet_set_sha, "packet_sha256": packet["packet_sha256"],
                         "cell_id": packet["cell_id"], "attempt_ordinal": packet["attempt_ordinal"]}
    if bindings != expected_bindings:
        raise LocalDispatchAcceptanceError("acceptance artifact bindings mismatch")
    planned = {"logical_session_id": packet["session_id"], "worktree_id": packet["worktree_id"], "context_id": packet["context_id"]}
    if acceptance.get("planned_identity") != planned:
        raise LocalDispatchAcceptanceError("acceptance logical identity binding mismatch")
    try:
        receipt = verify_receipt(harness_receipt)
    except HarnessReceiptError as error:
        raise LocalDispatchAcceptanceError(f"harness receipt is invalid: {error}") from error
    if _timestamp(receipt.generated_at, "harness generated_at") > accepted_at:
        raise LocalDispatchAcceptanceError("harness receipt was generated after acceptance")
    observed = acceptance.get("observed_identity")
    expected_observed_fields = {
        "harness_session_id": receipt.session_id,
        "child_session": True,
        "harness_and_version": receipt.agent_harness_and_version,
        "requested_model_alias": receipt.model_name,
        "claimed_effort": receipt.effort_setting,
    }
    if (
        not isinstance(observed, dict)
        or set(observed) != {
            "native_agent_id", "harness_session_id", "child_session", "harness_and_version",
            "requested_model_alias", "claimed_effort", "cwd", "head_commit",
        }
        or any(observed.get(key) != value for key, value in expected_observed_fields.items())
    ):
        raise LocalDispatchAcceptanceError("acceptance observed session binding mismatch")
    if not isinstance(observed.get("native_agent_id"), str) or not observed["native_agent_id"].strip():
        raise LocalDispatchAcceptanceError("acceptance native agent observation is missing")
    if observed.get("harness_session_id") == planned["logical_session_id"]:
        raise LocalDispatchAcceptanceError("observed harness session is conflated with logical session")
    if observed.get("head_commit") != checked_policy["required_head_commit"]:
        raise LocalDispatchAcceptanceError("acceptance HEAD binding mismatch")
    _validate_observed_cwd(observed.get("cwd"), packet["workspace_contract"]["cwd"])
    if acceptance.get("evidence") != {"harness_receipt_id": receipt.receipt_id, "harness_receipt_sha256": receipt.receipt_sha256,
                                       "process_environment_claims": True, "main_agent_host_observations": True}:
        raise LocalDispatchAcceptanceError("acceptance receipt binding mismatch")
    if acceptance.get("scope") != _LOCAL_SCOPE or acceptance.get("boundary") != {
        "workspace_preconditions": "main-agent-observed-not-isolation-proof", "non_claims": NON_CLAIMS,
    }:
        raise LocalDispatchAcceptanceError("acceptance scope or honest boundary mismatch")
    seed = {
        "policy": checked_policy["policy_sha256"], "bindings": expected_bindings,
        "receipt": receipt.receipt_sha256, "observed": observed,
        "accepted_at": acceptance.get("accepted_at"),
    }
    if acceptance.get("acceptance_id") != f"local-{_hash(seed)[:24]}":
        raise LocalDispatchAcceptanceError("acceptance_id does not bind canonical source observations")
    return json.loads(json.dumps(dict(acceptance), sort_keys=True))
