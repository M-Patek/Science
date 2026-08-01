from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from science_repo.workspace import WorkspaceError, WorkspaceManager


COMMIT = "a" * 40


@pytest.fixture
def workspace_root():
    path = Path(__file__).parent / "fixtures" / f"workspace-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


@dataclass
class Result:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeRunner:
    def __init__(self, head: str = COMMIT) -> None:
        self.head = head
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, command, cwd):
        command = list(command)
        self.calls.append((command, cwd))
        if command[1:3] == ["rev-parse", "--verify"]:
            return Result(stdout=COMMIT + "\n")
        if command[1:] == ["rev-parse", "HEAD"]:
            return Result(stdout=self.head + "\n")
        return Result()


def test_create_pins_revision_verifies_head_and_audits(workspace_root: Path) -> None:
    tmp_path = workspace_root
    runner = FakeRunner()
    manager = WorkspaceManager(tmp_path / "repo", tmp_path / "sessions", runner=runner)

    record = manager.create("agent-01", "release-v1")

    target = (tmp_path / "sessions" / "agent-01").resolve()
    assert record.status == "ready"
    assert record.resolved_revision == COMMIT
    assert runner.calls[1][0] == [
        "git", "worktree", "add", "--detach", str(target), COMMIT
    ]
    assert runner.calls[2] == (["git", "rev-parse", "HEAD"], target)
    assert manager.load("agent-01").commands == record.commands


@pytest.mark.parametrize("session_id", ["../escape", "x/y", ".", "", " space", "x\\y"])
def test_rejects_unsafe_session_ids(workspace_root: Path, session_id: str) -> None:
    tmp_path = workspace_root
    manager = WorkspaceManager(tmp_path / "repo", tmp_path / "sessions", runner=FakeRunner())
    with pytest.raises(WorkspaceError, match="unsafe session id"):
        manager.create(session_id, COMMIT)


def test_head_mismatch_is_failed_and_persisted(workspace_root: Path) -> None:
    tmp_path = workspace_root
    manager = WorkspaceManager(
        tmp_path / "repo", tmp_path / "sessions", runner=FakeRunner("b" * 40)
    )
    with pytest.raises(WorkspaceError, match="HEAD mismatch"):
        manager.create("agent", COMMIT)
    assert manager.load("agent").status == "failed"


def test_remove_uses_git_not_recursive_delete(workspace_root: Path) -> None:
    tmp_path = workspace_root
    runner = FakeRunner()
    manager = WorkspaceManager(tmp_path / "repo", tmp_path / "sessions", runner=runner)
    manager.create("agent", COMMIT)

    record = manager.remove("agent", force=True)

    assert record.status == "removed"
    assert runner.calls[-1][0] == [
        "git", "worktree", "remove", "--force", str((tmp_path / "sessions" / "agent").resolve())
    ]


def test_remove_rejects_tampered_workspace_boundary(workspace_root: Path) -> None:
    tmp_path = workspace_root
    runner = FakeRunner()
    manager = WorkspaceManager(tmp_path / "repo", tmp_path / "sessions", runner=runner)
    manager.create("agent", COMMIT)
    path = tmp_path / "sessions" / ".science-workspaces" / "agent.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["workspace"] = str((tmp_path / "outside").resolve())
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(WorkspaceError, match="bounded session target"):
        manager.remove("agent")
    assert runner.calls[-1][0] == ["git", "rev-parse", "HEAD"]


def test_command_failure_is_audited(workspace_root: Path) -> None:
    tmp_path = workspace_root
    def fail(command, cwd):
        return Result(returncode=2, stderr="bad revision")

    manager = WorkspaceManager(tmp_path / "repo", tmp_path / "sessions", runner=fail)
    with pytest.raises(WorkspaceError, match="bad revision"):
        manager.create("agent", COMMIT)
    record = manager.load("agent")
    assert record.status == "failed"
    assert record.commands[0][1:3] == ["rev-parse", "--verify"]
