"""Auditable, runtime-neutral campaign handoff coordination.

The coordinator does not start agents and does not mutate campaign manifests or
``TaskRuntime`` leases.  It accepts only handoffs carrying a matching audit
receipt, records the resulting outcome atomically, and exposes scheduler
decisions that callers may use to claim the next task.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Iterator, Mapping
from uuid import uuid4

from .campaign import validate_campaign
from .handoff import validate_handoff
from .scheduler import RetryPolicy, ScheduleDecision, schedule_campaign


class CoordinationError(RuntimeError):
    """An untrusted or inconsistent coordination input was rejected."""


@dataclass(frozen=True)
class AuditReceipt:
    """Evidence that a named auditor checked one authoritative dispatch result."""

    campaign_id: str
    task_id: str
    agent_role: str
    auditor: str
    audited_at: str
    handoff_sha256: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Acceptance:
    task_state: Mapping[str, Any]
    schedule: ScheduleDecision
    idempotent: bool = False


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CampaignCoordinator:
    """Persist accepted outcomes and compute the campaign's next decisions."""

    def __init__(self, root: str | Path, *, lock_timeout: float = 5.0, stale_lock_after: float = 30.0):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "coordinator-state.json"
        self.events_path = self.root / "coordinator-events.jsonl"
        self.lock_path = self.root / "coordinator.lock"
        self.lock_timeout = lock_timeout
        self.stale_lock_after = stale_lock_after

    def inspect(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"schema_version": 1, "campaign_id": None, "tasks": {}}
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise CoordinationError("coordinator state must be a mapping")
        return value

    def accept_handoff(
        self,
        campaign: dict[str, Any],
        handoff: dict[str, Any],
        receipt: AuditReceipt | None,
        *,
        runtime_states: Mapping[str, Mapping[str, Any] | None] | None = None,
        reviewer_approved: bool = False,
        human_gate_approved: bool = False,
        retry_policy: RetryPolicy | None = None,
        now: datetime | None = None,
    ) -> Acceptance:
        """Accept an audited handoff exactly once and return newly-ready work.

        Review and human gates fail closed: a nominally complete handoff remains
        blocked until the corresponding explicit approvals are supplied.
        """
        self._validate_authority(campaign, handoff, receipt)
        task = next(task for task in campaign["tasks"] if task["id"] == handoff["task_id"])
        status, reason = self._outcome(task, handoff, reviewer_approved, human_gate_approved)
        fingerprint = self._fingerprint(handoff, receipt, reviewer_approved, human_gate_approved)
        timestamp = _iso_now() if now is None else self._iso(now)

        with self._lock():
            state = self.inspect()
            campaign_id = state.get("campaign_id")
            if campaign_id not in (None, campaign["id"]):
                raise CoordinationError("coordinator state belongs to another campaign")
            tasks = dict(state.get("tasks", {}))
            previous = tasks.get(handoff["task_id"])
            if previous and previous.get("acceptance_fingerprint") == fingerprint:
                schedule = self.schedule(campaign, runtime_states, tasks, retry_policy=retry_policy, now=now)
                return Acceptance(dict(previous), schedule, True)

            attempt = self._attempt(runtime_states, handoff["task_id"], previous)
            task_state = {
                "task_id": handoff["task_id"],
                "status": status,
                "reason": reason,
                "attempt": attempt,
                "accepted_at": timestamp,
                "acceptance_fingerprint": fingerprint,
                "auditor": receipt.auditor,  # type: ignore[union-attr]
            }
            # The event is a write-ahead record.  If state replacement fails, a
            # retry finds this fingerprint and deterministically completes it.
            pending = self._latest_event_for_task(handoff["task_id"])
            if pending is not None and pending.get("acceptance_fingerprint") != fingerprint:
                pending = None
            if pending is not None:
                recovered = dict(pending["task_state"])
                tasks[handoff["task_id"]] = recovered
                self._write_atomic({"schema_version": 1, "campaign_id": campaign["id"], "tasks": tasks})
                schedule = self.schedule(campaign, runtime_states, tasks, retry_policy=retry_policy, now=now)
                return Acceptance(recovered, schedule, True)

            tasks[handoff["task_id"]] = task_state
            new_state = {"schema_version": 1, "campaign_id": campaign["id"], "tasks": tasks}
            self._append_event({
                "event": "handoff_accepted",
                "at": timestamp,
                "campaign_id": campaign["id"],
                "task_id": handoff["task_id"],
                "status": status,
                "reason": reason,
                "attempt": attempt,
                "acceptance_fingerprint": fingerprint,
                "auditor": receipt.auditor,  # type: ignore[union-attr]
                "previous_status": previous.get("status") if previous else None,
                "task_state": task_state,
            })
            self._write_atomic(new_state)
            schedule = self.schedule(campaign, runtime_states, tasks, retry_policy=retry_policy, now=now)
            return Acceptance(task_state, schedule)

    def schedule(
        self,
        campaign: dict[str, Any],
        runtime_states: Mapping[str, Mapping[str, Any] | None] | None = None,
        coordinator_states: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        retry_policy: RetryPolicy | None = None,
        now: datetime | None = None,
    ) -> ScheduleDecision:
        """Overlay accepted outcomes on lease snapshots, preserving attempts."""
        combined = {key: dict(value) if value else None for key, value in (runtime_states or {}).items()}
        states = coordinator_states if coordinator_states is not None else self.inspect().get("tasks", {})
        for task_id, accepted in states.items():
            current = combined.get(task_id) or {}
            scheduler_status = "cancelled" if accepted.get("status") == "blocked" else accepted.get("status")
            combined[task_id] = {
                **current,
                **accepted,
                "status": scheduler_status,
                "attempt": max(int(current.get("attempt", 0)), int(accepted.get("attempt", 0))),
            }
        return schedule_campaign(campaign, combined, retry_policy=retry_policy, now=now)

    @staticmethod
    def _validate_authority(campaign: dict[str, Any], handoff: dict[str, Any], receipt: AuditReceipt | None) -> None:
        campaign_errors = validate_campaign(campaign)
        if campaign_errors:
            raise CoordinationError("invalid authoritative campaign: " + "; ".join(campaign_errors))
        if receipt is None:
            raise CoordinationError("an audit receipt is required")
        if not receipt.auditor.strip() or not receipt.audited_at.strip():
            raise CoordinationError("audit receipt must identify auditor and time")
        try:
            audited_at = datetime.fromisoformat(receipt.audited_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise CoordinationError("audit receipt audited_at must be timezone-aware ISO") from error
        if audited_at.tzinfo is None:
            raise CoordinationError("audit receipt audited_at must be timezone-aware ISO")
        if receipt.errors:
            raise CoordinationError("handoff audit failed: " + "; ".join(receipt.errors))
        for field in ("campaign_id", "task_id", "agent_role"):
            if getattr(receipt, field) != handoff.get(field):
                raise CoordinationError(f"audit receipt {field} does not match handoff")
        errors = validate_handoff(handoff, campaign)
        if errors:
            raise CoordinationError("handoff is not valid for authoritative campaign: " + "; ".join(errors))
        if receipt.handoff_sha256 != CampaignCoordinator.handoff_sha256(handoff):
            raise CoordinationError("audit receipt handoff_sha256 does not match canonical handoff")

    @staticmethod
    def handoff_sha256(handoff: Mapping[str, Any]) -> str:
        canonical = json.dumps(handoff, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _outcome(task: Mapping[str, Any], handoff: Mapping[str, Any], reviewer: bool, gate: bool) -> tuple[str, str]:
        status = str(handoff["status"])
        if status != "complete":
            return status, f"handoff_{status}"
        if task.get("review_required") and not reviewer:
            return "blocked", "review_required"
        if task.get("human_gate") and not gate:
            return "blocked", "human_gate_required"
        return "completed", "handoff_complete"

    @staticmethod
    def _attempt(runtime: Mapping[str, Mapping[str, Any] | None] | None, task_id: str, previous: Mapping[str, Any] | None) -> int:
        raw = ((runtime or {}).get(task_id) or {}).get("attempt", (previous or {}).get("attempt", 0))
        try:
            attempt = int(raw)
        except (TypeError, ValueError) as error:
            raise CoordinationError("runtime attempt must be a non-negative integer") from error
        if attempt < 0:
            raise CoordinationError("runtime attempt must be a non-negative integer")
        return attempt

    @staticmethod
    def _fingerprint(handoff: Mapping[str, Any], receipt: AuditReceipt | None, reviewer: bool, gate: bool) -> str:
        document = {"handoff": handoff, "receipt": receipt.__dict__ if receipt else None, "reviewer_approved": reviewer, "human_gate_approved": gate}
        return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _write_atomic(self, state: Mapping[str, Any]) -> None:
        temporary = self.state_path.with_name(f".{self.state_path.name}.{uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)

    def _append_event(self, event: Mapping[str, Any]) -> None:
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _latest_event_for_task(self, task_id: str) -> dict[str, Any] | None:
        if not self.events_path.exists():
            return None
        for line in reversed(self.events_path.read_text(encoding="utf-8").splitlines()):
            event = json.loads(line)
            if event.get("task_id") == task_id:
                return event
        return None

    @contextmanager
    def _lock(self) -> Iterator[None]:
        deadline = time.monotonic() + self.lock_timeout
        nonce = uuid4().hex
        while True:
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, json.dumps({"pid": os.getpid(), "nonce": nonce, "created_at": _iso_now()}).encode())
                os.close(descriptor)
                break
            except (FileExistsError, PermissionError) as error:
                try:
                    observed = self.lock_path.read_text(encoding="utf-8")
                    if time.time() - self.lock_path.stat().st_mtime > self.stale_lock_after:
                        # Re-read before unlinking so a newly-created live lock is
                        # never removed using an observation of its predecessor.
                        if self.lock_path.read_text(encoding="utf-8") == observed:
                            self.lock_path.unlink()
                            continue
                except (FileNotFoundError, PermissionError, OSError, json.JSONDecodeError):
                    pass
                if time.monotonic() >= deadline:
                    raise CoordinationError("timed out acquiring coordinator lock") from error
                time.sleep(0.01)
        try:
            yield
        finally:
            try:
                owner = json.loads(self.lock_path.read_text(encoding="utf-8"))
                if owner.get("nonce") == nonce:
                    self.lock_path.unlink()
            except FileNotFoundError:
                pass
