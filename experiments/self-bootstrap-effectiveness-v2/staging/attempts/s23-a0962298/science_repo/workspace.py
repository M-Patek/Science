"""Auditable, bounded Git workspaces for isolated agent sessions.

The manager deliberately delegates all Git operations to an injectable command
runner.  It never recursively deletes a directory: cleanup is performed by
``git worktree remove`` only after the persisted session boundary is checked.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol, Sequence


_SESSION_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_COMMIT_ID = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


class WorkspaceError(RuntimeError):
    """Raised when a workspace operation is unsafe or fails verification."""


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], Path], CommandResult]


def _default_runner(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command), cwd=cwd, text=True, capture_output=True, check=False
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkspaceRecord:
    session_id: str
    repository: str
    sessions_root: str
    workspace: str
    requested_revision: str
    resolved_revision: str | None
    status: str
    created_at: str
    updated_at: str
    commands: list[list[str]]
    error: str | None = None


class WorkspaceManager:
    """Create and remove detached worktrees under one explicit session root."""

    def __init__(
        self,
        repository: str | Path,
        sessions_root: str | Path,
        *,
        runner: CommandRunner | None = None,
    ) -> None:
        self.repository = Path(repository).resolve()
        self.sessions_root = Path(sessions_root).resolve()
        self.runner = runner or _default_runner

    def create(self, session_id: str, revision: str) -> WorkspaceRecord:
        target = self._target(session_id)
        if not revision or revision.startswith("-") or any(c.isspace() for c in revision):
            raise WorkspaceError("revision must be a non-empty Git revision without whitespace")
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self._records_dir().mkdir(parents=True, exist_ok=True)
        if target.exists() or self._record_path(session_id).exists():
            raise WorkspaceError(f"session already exists: {session_id}")

        timestamp = _now()
        record = WorkspaceRecord(
            session_id=session_id,
            repository=str(self.repository),
            sessions_root=str(self.sessions_root),
            workspace=str(target),
            requested_revision=revision,
            resolved_revision=None,
            status="creating",
            created_at=timestamp,
            updated_at=timestamp,
            commands=[],
        )
        self._write(record)
        try:
            resolved = self._run(
                ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
                self.repository,
                record,
            ).strip()
            if not _COMMIT_ID.fullmatch(resolved):
                raise WorkspaceError("git did not resolve revision to a full commit id")
            record.resolved_revision = resolved.lower()
            self._run(
                ["git", "worktree", "add", "--detach", str(target), resolved],
                self.repository,
                record,
            )
            head = self._run(["git", "rev-parse", "HEAD"], target, record).strip().lower()
            if head != record.resolved_revision:
                raise WorkspaceError(
                    f"workspace HEAD mismatch: expected {record.resolved_revision}, got {head}"
                )
            record.status = "ready"
            record.updated_at = _now()
            self._write(record)
            return record
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            record.updated_at = _now()
            self._write(record)
            if isinstance(exc, WorkspaceError):
                raise
            raise WorkspaceError(str(exc)) from exc

    def remove(self, session_id: str, *, force: bool = False) -> WorkspaceRecord:
        expected = self._target(session_id)
        record = self.load(session_id)
        if Path(record.sessions_root).resolve() != self.sessions_root:
            raise WorkspaceError("record sessions_root does not match manager boundary")
        if Path(record.workspace).resolve() != expected:
            raise WorkspaceError("record workspace does not match bounded session target")
        if record.status == "removed":
            raise WorkspaceError(f"session already removed: {session_id}")
        command = ["git", "worktree", "remove"]
        if force:
            command.append("--force")
        command.append(str(expected))
        self._run(command, self.repository, record)
        record.status = "removed"
        record.updated_at = _now()
        record.error = None
        self._write(record)
        return record

    def load(self, session_id: str) -> WorkspaceRecord:
        self._target(session_id)  # validate before accessing a record path
        path = self._record_path(session_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkspaceRecord(**data)
        except FileNotFoundError as exc:
            raise WorkspaceError(f"unknown session: {session_id}") from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"invalid workspace record: {path}") from exc

    def _target(self, session_id: str) -> Path:
        if not _SESSION_ID.fullmatch(session_id) or session_id in {".", ".."}:
            raise WorkspaceError(f"unsafe session id: {session_id!r}")
        target = (self.sessions_root / session_id).resolve()
        if target.parent != self.sessions_root:
            raise WorkspaceError("session target escapes sessions_root")
        return target

    def _records_dir(self) -> Path:
        return self.sessions_root / ".science-workspaces"

    def _record_path(self, session_id: str) -> Path:
        return self._records_dir() / f"{session_id}.json"

    def _run(
        self, command: list[str], cwd: Path, record: WorkspaceRecord
    ) -> str:
        record.commands.append(command.copy())
        record.updated_at = _now()
        self._write(record)
        result = self.runner(command, cwd)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise WorkspaceError(f"command failed ({result.returncode}): {detail}")
        return result.stdout

    def _write(self, record: WorkspaceRecord) -> None:
        path = self._record_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".json.tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(asdict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
