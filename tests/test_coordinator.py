import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from science_repo.coordinator import AuditReceipt, CampaignCoordinator, CoordinationError
from science_repo.scheduler import RetryPolicy


NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


@pytest.fixture
def coordinator_root():
    path = Path(__file__).parent / "fixtures" / f"coordinator-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def campaign(*, review=False, gate=False):
    def task(task_id, depends=()):
        return {"id": task_id, "role": "developer", "status": "pending", "depends_on": list(depends), "inputs": [], "outputs": [f"work/{task_id}.txt"], "write_scope": [f"work/{task_id}.txt"], "review_required": review if task_id == "first" else False, "human_gate": gate if task_id == "first" else False}
    return {"schema_version": 1, "id": "study", "title": "Study", "objective": "Test", "status": "running", "owner": "main", "tasks": [task("first"), task("second", ("first",))]}


def handoff(status="complete", **changes):
    value = {"schema_version": 1, "campaign_id": "study", "task_id": "first", "agent_role": "developer", "status": status, "summary": "Work returned.", "outputs": ["work/first.txt"], "changed_files": [], "evidence": ["pytest"] if status == "complete" else [], "unresolved": [] if status == "complete" else ["work remains"], "recommended_next": []}
    value.update(changes)
    return value


def receipt(document=None, **changes):
    document = handoff() if document is None else document
    value = {"campaign_id": "study", "task_id": "first", "agent_role": "developer", "auditor": "main-agent", "audited_at": "2026-07-12T00:00:00Z", "handoff_sha256": CampaignCoordinator.handoff_sha256(document), "errors": ()}
    value.update(changes)
    return AuditReceipt(**value)


def test_complete_acceptance_is_atomic_audited_idempotent_and_unlocks_dependency(coordinator_root):
    coordinator = CampaignCoordinator(coordinator_root)
    accepted = coordinator.accept_handoff(campaign(), handoff(), receipt(), runtime_states={"first": {"attempt": 1}}, now=NOW)
    assert accepted.task_state["status"] == "completed"
    assert [item.task_id for item in accepted.schedule.ready] == ["second"]
    repeated = coordinator.accept_handoff(campaign(), handoff(), receipt(), runtime_states={"first": {"attempt": 1}}, now=NOW)
    assert repeated.idempotent
    assert len(coordinator.events_path.read_text().splitlines()) == 1
    assert json.loads(coordinator.state_path.read_text())["tasks"]["first"]["attempt"] == 1


@pytest.mark.parametrize("bad_receipt,match", [(None, "required"), (receipt(errors=("bad evidence",)), "audit failed"), (receipt(task_id="second"), "task_id")])
def test_unaudited_or_mismatched_handoff_is_rejected(coordinator_root, bad_receipt, match):
    with pytest.raises(CoordinationError, match=match):
        CampaignCoordinator(coordinator_root).accept_handoff(campaign(), handoff(), bad_receipt, now=NOW)


def test_authoritative_campaign_recheck_rejects_wrong_role_and_scope(coordinator_root):
    coordinator = CampaignCoordinator(coordinator_root)
    wrong_role = handoff(agent_role="reviewer")
    with pytest.raises(CoordinationError, match="agent_role"):
        coordinator.accept_handoff(campaign(), wrong_role, receipt(wrong_role, agent_role="reviewer"), now=NOW)
    escaped = handoff(outputs=["elsewhere/result.txt"])
    with pytest.raises(CoordinationError, match="outside"):
        coordinator.accept_handoff(campaign(), escaped, receipt(escaped), now=NOW)


def test_receipt_binds_canonical_handoff_and_timezone_aware_audit_time(coordinator_root):
    coordinator = CampaignCoordinator(coordinator_root)
    changed = handoff(summary="Changed after audit.")
    with pytest.raises(CoordinationError, match="handoff_sha256"):
        coordinator.accept_handoff(campaign(), changed, receipt(), now=NOW)
    with pytest.raises(CoordinationError, match="timezone-aware"):
        coordinator.accept_handoff(campaign(), handoff(), receipt(audited_at="2026-07-12T00:00:00"), now=NOW)


@pytest.mark.parametrize("review,gate,reason", [(True, False, "review_required"), (False, True, "human_gate_required")])
def test_review_and_human_gates_fail_closed_then_explicit_approval_completes(coordinator_root, review, gate, reason):
    coordinator = CampaignCoordinator(coordinator_root)
    blocked = coordinator.accept_handoff(campaign(review=review, gate=gate), handoff(), receipt(), now=NOW)
    assert (blocked.task_state["status"], blocked.task_state["reason"]) == ("blocked", reason)
    completed = coordinator.accept_handoff(campaign(review=review, gate=gate), handoff(), receipt(), reviewer_approved=review, human_gate_approved=gate, now=NOW)
    if gate:
        assert completed.task_state["status"] == "blocked"
    else:
        assert completed.task_state["status"] == "completed"
    assert len(coordinator.events_path.read_text().splitlines()) == 2


def test_failed_handoff_retries_with_budget_and_exhaustion_blocks_dependents(coordinator_root):
    coordinator = CampaignCoordinator(coordinator_root)
    first_failure = handoff("failed")
    retry = coordinator.accept_handoff(campaign(), first_failure, receipt(first_failure), runtime_states={"first": {"attempt": 1}}, retry_policy=RetryPolicy(max_attempts=2), now=NOW)
    assert [item.task_id for item in retry.schedule.ready] == ["first"]
    second_failure = handoff("failed", summary="Second failure.")
    exhausted = coordinator.accept_handoff(campaign(), second_failure, receipt(second_failure), runtime_states={"first": {"attempt": 2}}, retry_policy=RetryPolicy(max_attempts=2), now=NOW)
    reasons = {item.task_id: item.reason for item in exhausted.schedule.tasks}
    assert reasons == {"first": "retries_exhausted", "second": "dependency_failed"}


def test_blocked_handoff_remains_an_explicit_manual_block(coordinator_root):
    blocked_handoff = handoff("blocked")
    accepted = CampaignCoordinator(coordinator_root).accept_handoff(campaign(), blocked_handoff, receipt(blocked_handoff), now=NOW)
    assert accepted.task_state["status"] == "blocked"
    assert accepted.task_state["reason"] == "handoff_blocked"
    assert {item.task_id: item.state for item in accepted.schedule.tasks} == {
        "first": "blocked",
        "second": "blocked",
    }


def test_wal_retry_recovers_event_after_atomic_state_replace_failure(coordinator_root, monkeypatch):
    coordinator = CampaignCoordinator(coordinator_root)
    original = coordinator._write_atomic
    calls = 0

    def fail_once(state):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated replace failure")
        original(state)

    monkeypatch.setattr(coordinator, "_write_atomic", fail_once)
    with pytest.raises(OSError, match="replace"):
        coordinator.accept_handoff(campaign(), handoff(), receipt(), now=NOW)
    assert len(coordinator.events_path.read_text().splitlines()) == 1
    recovered = coordinator.accept_handoff(campaign(), handoff(), receipt(), now=NOW)
    assert recovered.idempotent
    assert coordinator.inspect()["tasks"]["first"]["status"] == "completed"
    assert len(coordinator.events_path.read_text().splitlines()) == 1


def test_append_failure_never_advances_state(coordinator_root, monkeypatch):
    coordinator = CampaignCoordinator(coordinator_root)

    def fail(_event):
        raise OSError("simulated append failure")

    monkeypatch.setattr(coordinator, "_append_event", fail)
    with pytest.raises(OSError, match="append"):
        coordinator.accept_handoff(campaign(), handoff(), receipt(), now=NOW)
    assert not coordinator.state_path.exists()


def test_stale_lock_is_reclaimed_but_live_lock_is_not_deleted(coordinator_root):
    stale = CampaignCoordinator(coordinator_root, stale_lock_after=0)
    stale.lock_path.write_text(json.dumps({"nonce": "dead"}), encoding="utf-8")
    with pytest.raises(CoordinationError, match="timed out"):
        stale.accept_handoff(campaign(), handoff(), receipt(), now=NOW)
    stale.lock_path.unlink()

    live_root = coordinator_root / "live"
    live = CampaignCoordinator(live_root, lock_timeout=0.02, stale_lock_after=60)
    live.lock_path.write_text(json.dumps({"nonce": "live"}), encoding="utf-8")
    with pytest.raises(CoordinationError, match="timed out"):
        live.accept_handoff(campaign(), handoff(), receipt(), now=NOW)
    assert live.lock_path.exists()
