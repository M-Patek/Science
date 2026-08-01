import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from science_repo.coordinator import (
    AuditReceipt,
    CampaignCoordinator,
    CoordinationError,
    HumanApprovalReceipt,
)


@pytest.fixture
def workdir():
    path = Path(__file__).parent / "fixtures" / f"coordinator-hardening-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def campaign(gate=False):
    return {"schema_version": 1, "id": "c", "title": "C", "objective": "O", "status": "running", "owner": "m",
            "tasks": [{"id": "t", "role": "dev", "status": "pending", "depends_on": [], "inputs": [],
                       "outputs": ["work/t"], "write_scope": ["work/t"], "review_required": False,
                       "human_gate": gate}]}


def handoff():
    return {"schema_version": 1, "campaign_id": "c", "task_id": "t", "agent_role": "dev", "status": "complete",
            "summary": "done", "outputs": ["work/t"], "changed_files": [], "evidence": ["test"],
            "unresolved": [], "recommended_next": []}


def audit(h):
    return AuditReceipt("c", "t", "dev", "auditor", "2026-07-12T00:00:00Z",
                        CampaignCoordinator.handoff_sha256(h))


def approval(h):
    return HumanApprovalReceipt("c", "t", "human", "2026-07-12T00:00:00Z",
                                CampaignCoordinator.handoff_sha256(h), "signed:opaque")


def test_legacy_gate_boolean_is_only_an_unattested_assertion(workdir):
    h = handoff()
    result = CampaignCoordinator(workdir).accept_handoff(campaign(True), h, audit(h), human_gate_approved=True)
    assert result.task_state["status"] == "blocked"
    assert result.task_state["reason"] == "human_gate_unattested"
    assert result.task_state["human_gate_assertion"] == "unattested"


def test_only_host_verified_bound_approval_opens_human_gate(workdir):
    h = handoff()
    denied = CampaignCoordinator(workdir / "denied", approval_verifier=lambda _receipt: False)
    assert denied.accept_handoff(campaign(True), h, audit(h), human_approval_receipt=approval(h)).task_state["status"] == "blocked"
    allowed = CampaignCoordinator(workdir / "allowed", approval_verifier=lambda receipt: receipt.attestation.startswith("signed:"))
    assert allowed.accept_handoff(campaign(True), h, audit(h), human_approval_receipt=approval(h)).task_state["status"] == "completed"


def test_old_live_lock_times_out_even_when_age_threshold_elapsed(workdir):
    coordinator = CampaignCoordinator(workdir, lock_timeout=.03, stale_lock_after=0)
    coordinator.lock_path.write_text(json.dumps({"pid": os.getpid(), "process_start": coordinator._process_start_identity(os.getpid()),
                                                  "nonce": "other"}), encoding="utf-8")
    with pytest.raises(CoordinationError, match="timed out"):
        with coordinator._lock():
            pass
    assert coordinator.lock_path.exists()


def test_dead_owner_lock_is_reclaimed(workdir, monkeypatch):
    coordinator = CampaignCoordinator(workdir, stale_lock_after=0)
    coordinator.lock_path.write_text(json.dumps({"pid": 123, "process_start": "old", "nonce": "dead"}), encoding="utf-8")
    monkeypatch.setattr(coordinator, "_owner_is_dead", lambda _owner: True)
    with coordinator._lock():
        assert coordinator.lock_path.exists()


def test_torn_jsonl_tail_is_diagnosed_repaired_and_middle_damage_fails_closed(workdir):
    coordinator = CampaignCoordinator(workdir)
    good = json.dumps({"task_id": "other"}).encode() + b"\n"
    coordinator.events_path.write_bytes(good + b'{"task_id":')
    assert coordinator._latest_event_for_task("t") is None
    assert any("torn" in item for item in coordinator.diagnostics)
    coordinator._append_event({"task_id": "t"})
    assert coordinator._latest_event_for_task("t") == {"task_id": "t"}
    coordinator.events_path.write_bytes(b"not-json\n{}\n")
    with pytest.raises(CoordinationError, match="line 1"):
        coordinator._latest_event_for_task("t")


def test_atomic_replace_attempts_parent_directory_fsync(workdir, monkeypatch):
    coordinator = CampaignCoordinator(workdir)
    seen = []
    monkeypatch.setattr(coordinator, "_fsync_parent", lambda path: seen.append(Path(path)))
    coordinator._write_atomic({"schema_version": 1, "tasks": {}})
    assert seen == [workdir]
