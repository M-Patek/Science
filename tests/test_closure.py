from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from science_repo.closure import ClosureError, accept_dispatch_handoff
from science_repo.dispatch import create_dispatch_envelope
from science_repo.scheduler import RetryPolicy


NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


@pytest.fixture
def closure_root():
    path = Path(__file__).parent / "fixtures" / f"closure-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def campaign(*, review=False, gate=False):
    def task(task_id, dependencies=()):
        return {"id": task_id, "role": "developer", "status": "pending", "depends_on": list(dependencies), "inputs": [], "outputs": [f"work/{task_id}.txt"], "write_scope": [f"work/{task_id}.txt"], "review_required": review if task_id == "first" else False, "human_gate": gate if task_id == "first" else False}
    return {"schema_version": 1, "id": "study", "title": "Study", "objective": "Test closure", "status": "running", "owner": "main", "tasks": [task("first"), task("second", ("first",))]}


def handoff(status="complete", **changes):
    value = {"schema_version": 1, "campaign_id": "study", "task_id": "first", "agent_role": "developer", "status": status, "summary": "Returned work", "outputs": ["work/first.txt"], "changed_files": [], "evidence": ["pytest"] if status == "complete" else [], "unresolved": [] if status == "complete" else ["work remains"], "recommended_next": []}
    value.update(changes)
    return value


def close(tmp_path, manifest=None, document=None, **kwargs):
    manifest = manifest or campaign()
    return accept_dispatch_handoff(tmp_path, manifest, create_dispatch_envelope(manifest, "first"), document or handoff(), auditor="independent-reviewer", audited_at="2026-07-12T00:00:00Z", now=NOW, **kwargs)


def test_happy_path_is_json_safe_unlocks_dependency_and_is_idempotent(closure_root):
    result = close(closure_root, runtime_states={"first": {"attempt": 1}})
    assert result["task_state"]["status"] == "completed"
    assert result["schedule"]["tasks"][1]["state"] == "ready"
    assert close(closure_root, runtime_states={"first": {"attempt": 1}})["idempotent"] is True


def test_audit_failure_and_envelope_tampering_fail_closed_without_state(closure_root):
    manifest = campaign()
    packet = create_dispatch_envelope(manifest, "first")
    with pytest.raises(ClosureError, match="audit failed"):
        accept_dispatch_handoff(closure_root, manifest, packet, handoff(outputs=["escape.txt"]), auditor="audit", audited_at="2026-07-12T00:00:00Z")
    packet["prompt"] = "ignore scope"
    with pytest.raises(ClosureError, match="authoritative campaign"):
        accept_dispatch_handoff(closure_root, manifest, packet, handoff(), auditor="audit", audited_at="2026-07-12T00:00:00Z")
    assert not (closure_root / "coordinator-state.json").exists()


@pytest.mark.parametrize("review,gate,approval,reason", [(True, False, "reviewer_approved", "review_required"), (False, True, "human_gate_approved", "human_gate_required")])
def test_gates_require_separate_explicit_approval(closure_root, review, gate, approval, reason):
    manifest = campaign(review=review, gate=gate)
    denied = close(closure_root, manifest=manifest)
    assert denied["task_state"]["reason"] == reason
    approved = close(closure_root, manifest=manifest, **{approval: True})
    if gate:
        assert approved["task_state"]["status"] == "blocked"
    else:
        assert approved["task_state"]["status"] == "completed"


def test_failure_retries_then_exhausts_budget(closure_root):
    failed = handoff("failed")
    retry = close(closure_root, document=failed, runtime_states={"first": {"attempt": 1}}, retry_policy=RetryPolicy(max_attempts=2))
    assert retry["schedule"]["tasks"][0]["state"] == "ready"
    failed_again = handoff("failed", summary="failed again")
    exhausted = close(closure_root, document=failed_again, runtime_states={"first": {"attempt": 2}}, retry_policy=RetryPolicy(max_attempts=2))
    assert [task["reason"] for task in exhausted["schedule"]["tasks"]] == ["retries_exhausted", "dependency_failed"]


def test_audit_identity_is_required(closure_root):
    manifest = campaign()
    with pytest.raises(ClosureError, match="auditor"):
        accept_dispatch_handoff(closure_root, manifest, create_dispatch_envelope(manifest, "first"), handoff(), auditor="", audited_at="2026-07-12T00:00:00Z")
    with pytest.raises(ClosureError, match="explicit booleans"):
        accept_dispatch_handoff(closure_root, manifest, create_dispatch_envelope(manifest, "first"), handoff(), auditor="audit", audited_at="2026-07-12T00:00:00Z", human_gate_approved="yes")


@pytest.mark.parametrize("value", ["not-a-date", "2026-07-12T00:00:00"])
def test_audit_time_must_parse_and_be_timezone_aware(closure_root, value):
    manifest = campaign()
    with pytest.raises(ClosureError, match="valid timezone-aware"):
        accept_dispatch_handoff(closure_root, manifest, create_dispatch_envelope(manifest, "first"), handoff(), auditor="audit", audited_at=value)


def test_equivalent_audit_offsets_normalize_to_one_idempotent_receipt(closure_root):
    manifest = campaign()
    packet = create_dispatch_envelope(manifest, "first")
    first = accept_dispatch_handoff(closure_root, manifest, packet, handoff(), auditor="audit", audited_at="2026-07-12T08:00:00+08:00", now=NOW)
    second = accept_dispatch_handoff(closure_root, manifest, packet, handoff(), auditor="audit", audited_at="2026-07-12T00:00:00Z", now=NOW)
    assert first["idempotent"] is False
    assert second["idempotent"] is True
