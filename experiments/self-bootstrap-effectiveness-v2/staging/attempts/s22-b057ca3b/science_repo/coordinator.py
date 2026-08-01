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
import errno
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterator, Mapping
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
class HumanApprovalReceipt:
    """An attested human decision bound to one exact handoff.

    The coordinator deliberately does not prescribe an identity provider.  A
    host-supplied verifier is the trust boundary; receipt presence alone is not
    approval.
    """

    campaign_id: str
    task_id: str
    approver: str
    approved_at: str
    handoff_sha256: str
    attestation: str


@dataclass(frozen=True)
class Acceptance:
    task_state: Mapping[str, Any]
    schedule: ScheduleDecision
    idempotent: bool = False


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CampaignCoordinator:
    """Persist accepted outcomes and compute the campaign's next decisions."""

    def __init__(self, root: str | Path, *, lock_timeout: float = 5.0, stale_lock_after: float = 30.0,
                 approval_verifier: Callable[[HumanApprovalReceipt], bool] | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "coordinator-state.json"
        self.events_path = self.root / "coordinator-events.jsonl"
        self.lock_path = self.root / "coordinator.lock"
        self.lock_timeout = lock_timeout
        self.stale_lock_after = stale_lock_after
        self.approval_verifier = approval_verifier
        self.diagnostics: list[str] = []

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
        human_approval_receipt: HumanApprovalReceipt | None = None,
        retry_policy: RetryPolicy | None = None,
        now: datetime | None = None,
    ) -> Acceptance:
        """Accept an audited handoff exactly once and return newly-ready work.

        Review and human gates fail closed: a nominally complete handoff remains
        blocked until the corresponding explicit approvals are supplied.
        """
        self._validate_authority(campaign, handoff, receipt)
        task = next(task for task in campaign["tasks"] if task["id"] == handoff["task_id"])
        human_attested = self._verify_human_approval(campaign, handoff, human_approval_receipt)
        status, reason = self._outcome(task, handoff, reviewer_approved, human_attested, human_gate_approved)
        fingerprint = self._fingerprint(handoff, receipt, reviewer_approved, human_gate_approved,
                                        human_approval_receipt, human_attested)
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
                "human_gate_assertion": "unattested" if human_gate_approved else None,
                "human_approval_attested": human_attested,
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
    def _outcome(task: Mapping[str, Any], handoff: Mapping[str, Any], reviewer: bool,
                 gate_attested: bool, legacy_gate_assertion: bool = False) -> tuple[str, str]:
        status = str(handoff["status"])
        if status != "complete":
            return status, f"handoff_{status}"
        if task.get("review_required") and not reviewer:
            return "blocked", "review_required"
        if task.get("human_gate") and not gate_attested:
            return "blocked", "human_gate_unattested" if legacy_gate_assertion else "human_gate_required"
        return "completed", "handoff_complete"

    def _verify_human_approval(self, campaign: Mapping[str, Any], handoff: Mapping[str, Any],
                               receipt: HumanApprovalReceipt | None) -> bool:
        if receipt is None:
            return False
        if (receipt.campaign_id != campaign.get("id") or receipt.task_id != handoff.get("task_id")
                or receipt.handoff_sha256 != self.handoff_sha256(handoff)):
            raise CoordinationError("human approval receipt does not match handoff authority")
        if not receipt.approver.strip() or not receipt.attestation.strip():
            raise CoordinationError("human approval receipt lacks identity or attestation")
        try:
            approved_at = datetime.fromisoformat(receipt.approved_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise CoordinationError("human approval receipt approved_at must be timezone-aware ISO") from error
        if approved_at.tzinfo is None:
            raise CoordinationError("human approval receipt approved_at must be timezone-aware ISO")
        if self.approval_verifier is None:
            return False
        try:
            return self.approval_verifier(receipt) is True
        except Exception as error:
            raise CoordinationError("human approval verifier failed closed") from error

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
    def _fingerprint(handoff: Mapping[str, Any], receipt: AuditReceipt | None, reviewer: bool, gate: bool,
                     approval: HumanApprovalReceipt | None = None, approval_verified: bool = False) -> str:
        document = {"handoff": handoff, "receipt": receipt.__dict__ if receipt else None,
                    "reviewer_approved": reviewer, "human_gate_approved": gate,
                    "human_approval_receipt": approval.__dict__ if approval else None,
                    "human_approval_verified": approval_verified}
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
        self._fsync_parent(self.state_path.parent)

    @staticmethod
    def _fsync_parent(directory: Path) -> None:
        """Best-effort durability for the rename itself (unsupported on Windows)."""
        try:
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass

    def _append_event(self, event: Mapping[str, Any]) -> None:
        self._repair_torn_event_tail()
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _repair_torn_event_tail(self) -> None:
        if not self.events_path.exists():
            return
        raw = self.events_path.read_bytes()
        if not raw or raw.endswith(b"\n"):
            return
        boundary = raw.rfind(b"\n") + 1
        tail = raw[boundary:]
        try:
            json.loads(tail.decode("utf-8"))
            # Preserve a valid final entry and add the missing record separator
            # before the next append.
            with self.events_path.open("ab") as handle:
                handle.write(b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.diagnostics.append("added missing trailing coordinator event newline")
            return
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Validate the durable prefix before repairing; corruption anywhere
            # except the incomplete tail is not recoverable automatically.
            for index, line in enumerate(raw[:boundary].splitlines()):
                try:
                    json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise CoordinationError(f"coordinator event log is corrupt at line {index + 1}") from error
            with self.events_path.open("r+b") as handle:
                handle.truncate(boundary)
                handle.flush()
                os.fsync(handle.fileno())
            self.diagnostics.append("truncated torn trailing coordinator event")

    def _latest_event_for_task(self, task_id: str) -> dict[str, Any] | None:
        if not self.events_path.exists():
            return None
        raw = self.events_path.read_bytes()
        lines = raw.splitlines()
        events: list[dict[str, Any]] = []
        for index, encoded in enumerate(lines):
            try:
                event = json.loads(encoded.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                is_torn_tail = index == len(lines) - 1 and not raw.endswith(b"\n")
                if is_torn_tail:
                    self.diagnostics.append("ignored torn trailing coordinator event")
                    continue
                raise CoordinationError(f"coordinator event log is corrupt at line {index + 1}") from error
            if not isinstance(event, dict):
                raise CoordinationError(f"coordinator event log entry {index + 1} must be a mapping")
            events.append(event)
        for event in reversed(events):
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
                os.write(descriptor, json.dumps({"pid": os.getpid(), "process_start": self._process_start_identity(os.getpid()),
                                                 "nonce": nonce, "created_at": _iso_now()}).encode())
                os.close(descriptor)
                break
            except (FileExistsError, PermissionError) as error:
                try:
                    observed = self.lock_path.read_text(encoding="utf-8")
                    owner = json.loads(observed)
                    if (time.time() - self.lock_path.stat().st_mtime > self.stale_lock_after
                            and self._owner_is_dead(owner)):
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

    @staticmethod
    def _process_start_identity(pid: int) -> str | None:
        """Return an OS process incarnation identifier where available."""
        proc_stat = Path(f"/proc/{pid}/stat")
        try:
            # Field 22; split after the comm field because it may contain spaces.
            tail = proc_stat.read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            return f"proc:{tail[19]}"
        except (OSError, IndexError):
            pass
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
            try:
                if not kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                                ctypes.byref(kernel), ctypes.byref(user)):
                    return None
                return f"win:{creation.dwHighDateTime:08x}{creation.dwLowDateTime:08x}"
            finally:
                kernel32.CloseHandle(handle)
        except (AttributeError, OSError):
            return None

    @classmethod
    def _owner_is_dead(cls, owner: Mapping[str, Any]) -> bool:
        try:
            pid = int(owner["pid"])
        except (KeyError, TypeError, ValueError):
            return False  # unknown ownership fails closed
        recorded = owner.get("process_start")
        current = cls._process_start_identity(pid)
        if current is not None:
            # A legacy/malformed lock without an incarnation identifier is
            # unknown, not dead.  A mismatch proves PID reuse.
            return recorded is not None and current != recorded
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        except OSError as error:
            return os.name == "nt" and error.errno in (errno.EINVAL, errno.ESRCH)
        return False
