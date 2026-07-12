"""Small, local-file task lease runtime for campaign workers.

The runtime deliberately does not interpret campaign manifests.  A coordinator passes a
validated task id here and receives a capability token which must accompany subsequent
heartbeats or releases.  State replacement and audit appends happen while holding the same
per-task exclusive lock.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterator
from uuid import uuid4


class LeaseConflict(RuntimeError):
    """The task is leased by another worker, or the supplied capability is stale."""


class LockTimeout(RuntimeError):
    """A task lock could not be acquired within the configured timeout."""


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TaskRuntime:
    """Coordinate task leases through an auditable directory on a local filesystem."""

    def __init__(self, root: str | Path, *, lock_timeout: float = 5.0, stale_lock_after: float = 30.0):
        self.root = Path(root)
        self.states = self.root / "tasks"
        self.audit_path = self.root / "events.jsonl"
        self.lock_timeout = lock_timeout
        self.stale_lock_after = stale_lock_after
        self.states.mkdir(parents=True, exist_ok=True)

    def claim(self, task_id: str, worker_id: str, *, lease_seconds: float = 300) -> dict[str, Any]:
        """Atomically acquire an unleased task, reclaiming an expired lease if necessary."""
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._lock(task_id):
            now = _utcnow()
            previous = self._read(task_id)
            active = previous and previous.get("status") == "leased" and _parse(previous["expires_at"]) > now
            if active:
                raise LeaseConflict(f"task {task_id!r} is leased by {previous['worker_id']!r}")
            reclaimed = bool(previous and previous.get("status") == "leased")
            state = {
                "task_id": task_id,
                "status": "leased",
                "worker_id": worker_id,
                "token": uuid4().hex,
                "claimed_at": _iso(now),
                "heartbeat_at": _iso(now),
                "expires_at": _iso(now + timedelta(seconds=lease_seconds)),
                "attempt": int((previous or {}).get("attempt", 0)) + 1,
            }
            self._write(task_id, state)
            self._audit("reclaimed" if reclaimed else "claimed", state, now, previous=previous)
            return dict(state)

    def heartbeat(self, task_id: str, worker_id: str, token: str, *, lease_seconds: float = 300) -> dict[str, Any]:
        """Extend a live lease; expired or superseded capabilities are rejected."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._lock(task_id):
            now = _utcnow()
            state = self._require_live(task_id, worker_id, token, now)
            state["heartbeat_at"] = _iso(now)
            state["expires_at"] = _iso(now + timedelta(seconds=lease_seconds))
            self._write(task_id, state)
            self._audit("heartbeat", state, now)
            return dict(state)

    def release(self, task_id: str, worker_id: str, token: str, *, outcome: str = "released") -> dict[str, Any]:
        """End a live lease, recording a terminal/requeue outcome chosen by the coordinator."""
        if not outcome.strip():
            raise ValueError("outcome must not be empty")
        with self._lock(task_id):
            now = _utcnow()
            state = self._require_live(task_id, worker_id, token, now)
            state.update(status=outcome, released_at=_iso(now))
            self._write(task_id, state)
            self._audit("released", state, now)
            return dict(state)

    def inspect(self, task_id: str) -> dict[str, Any] | None:
        """Return a snapshot. This read is informational and does not acquire a lease."""
        self._validate_id(task_id)
        state = self._read(task_id)
        return dict(state) if state else None

    def _require_live(self, task_id: str, worker_id: str, token: str, now: datetime) -> dict[str, Any]:
        state = self._read(task_id)
        if not state or state.get("status") != "leased":
            raise LeaseConflict(f"task {task_id!r} has no live lease")
        if state.get("worker_id") != worker_id or state.get("token") != token:
            raise LeaseConflict(f"task {task_id!r} lease capability does not match")
        if _parse(state["expires_at"]) <= now:
            raise LeaseConflict(f"task {task_id!r} lease has expired")
        return state

    def _validate_id(self, task_id: str) -> None:
        if not isinstance(task_id, str) or not _SAFE_ID.fullmatch(task_id):
            raise ValueError("task_id must be a safe filename component")

    def _path(self, task_id: str) -> Path:
        self._validate_id(task_id)
        return self.states / f"{task_id}.json"

    def _read(self, task_id: str) -> dict[str, Any] | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, task_id: str, state: dict[str, Any]) -> None:
        path = self._path(task_id)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _audit(self, event: str, state: dict[str, Any], now: datetime, **extra: Any) -> None:
        record = {"event": event, "at": _iso(now), "task_id": state["task_id"], "state": state, **extra}
        with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @contextmanager
    def _lock(self, task_id: str) -> Iterator[None]:
        path = self._path(task_id).with_suffix(".lock")
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, json.dumps({"pid": os.getpid(), "created_at": _iso(_utcnow())}).encode())
                os.close(descriptor)
                break
            except (FileExistsError, PermissionError) as lock_error:
                try:
                    if time.time() - path.stat().st_mtime > self.stale_lock_after:
                        path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                except PermissionError:
                    # Windows may report sharing violations as PermissionError
                    # while another thread/process owns the exclusive lock.
                    pass
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"timed out acquiring lock for {task_id!r}") from lock_error
                time.sleep(0.01)
        try:
            yield
        finally:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
