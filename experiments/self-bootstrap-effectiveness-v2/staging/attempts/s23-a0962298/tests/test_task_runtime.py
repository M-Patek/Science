import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import time
from uuid import uuid4

import pytest

from science_repo.task_runtime import LeaseConflict, TaskRuntime


@pytest.fixture
def runtime_root():
    path = Path(__file__).parent / "fixtures" / f"task-runtime-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_concurrent_claim_has_exactly_one_winner(runtime_root):
    runtime = TaskRuntime(runtime_root)

    def claim(worker):
        try:
            return runtime.claim("task-1", worker, lease_seconds=10)
        except LeaseConflict:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, [f"worker-{index}" for index in range(8)]))
    assert len([result for result in results if result]) == 1
    events = [json.loads(line) for line in runtime.audit_path.read_text().splitlines()]
    assert [event["event"] for event in events] == ["claimed"]


def test_heartbeat_extends_lease_and_stale_capability_is_rejected(runtime_root):
    runtime = TaskRuntime(runtime_root)
    lease = runtime.claim("task", "worker", lease_seconds=1)
    renewed = runtime.heartbeat("task", "worker", lease["token"], lease_seconds=10)
    assert renewed["expires_at"] > lease["expires_at"]
    with pytest.raises(LeaseConflict):
        runtime.heartbeat("task", "intruder", lease["token"])


def test_expired_lease_is_reclaimed_and_audited(runtime_root):
    runtime = TaskRuntime(runtime_root)
    old = runtime.claim("task", "worker-a", lease_seconds=0.02)
    time.sleep(0.04)
    new = runtime.claim("task", "worker-b", lease_seconds=10)
    assert new["attempt"] == 2
    assert new["token"] != old["token"]
    with pytest.raises(LeaseConflict):
        runtime.release("task", "worker-a", old["token"])
    events = [json.loads(line) for line in runtime.audit_path.read_text().splitlines()]
    assert [event["event"] for event in events] == ["claimed", "reclaimed"]
    assert events[-1]["previous"]["worker_id"] == "worker-a"


def test_release_is_persisted_and_audited(runtime_root):
    runtime = TaskRuntime(runtime_root)
    lease = runtime.claim("task", "worker")
    released = runtime.release("task", "worker", lease["token"], outcome="completed")
    assert released["status"] == "completed"
    assert runtime.inspect("task")["status"] == "completed"
    assert [json.loads(line)["event"] for line in runtime.audit_path.read_text().splitlines()] == [
        "claimed",
        "released",
    ]


@pytest.mark.parametrize("task_id", ["../escape", "a/b", "", "."])
def test_task_id_cannot_escape_runtime(runtime_root, task_id):
    runtime = TaskRuntime(runtime_root)
    with pytest.raises(ValueError):
        runtime.claim(task_id, "worker")
