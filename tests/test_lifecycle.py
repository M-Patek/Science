import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
import yaml

from science_repo.lifecycle import LifecycleError, allowed_transitions, read_stage_history, transition_stage


@pytest.fixture
def tmp_path():
    path = Path(__file__).parent / "fixtures" / f"lifecycle-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def make_experiment(tmp_path, stage="idea"):
    root = tmp_path / "experiment"
    root.mkdir()
    (root / "experiment.yaml").write_text(
        yaml.safe_dump({"id": "test-experiment", "stage": stage, "title": "Test"}, sort_keys=False),
        encoding="utf-8",
    )
    return root


def test_forward_transition_updates_manifest_and_appends_audit_entry(tmp_path):
    root = make_experiment(tmp_path)
    entry = transition_stage(
        root,
        "designed",
        reason="Protocol was preregistered",
        actor="agent:planner",
        timestamp="2026-07-12T08:00:00+08:00",
    )

    assert yaml.safe_load((root / "experiment.yaml").read_text(encoding="utf-8"))["stage"] == "designed"
    assert entry == {
        "from_stage": "idea",
        "to_stage": "designed",
        "reason": "Protocol was preregistered",
        "actor": "agent:planner",
        "timestamp": "2026-07-12T08:00:00+08:00",
    }
    assert read_stage_history(root) == [entry]


def test_history_is_appended_and_chained(tmp_path):
    root = make_experiment(tmp_path)
    first = transition_stage(root, "designed", reason="ready", actor="alice")
    second = transition_stage(root, "running", reason="authorized", actor="bob")
    lines = (root / "stage-history.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [first, second]


@pytest.mark.parametrize("terminal", ["published", "abandoned"])
def test_terminal_stages_cannot_be_reopened(tmp_path, terminal):
    root = make_experiment(tmp_path, terminal)
    with pytest.raises(LifecycleError, match="forbidden transition"):
        transition_stage(root, "idea", reason="changed our minds", actor="operator")
    assert not (root / "stage-history.jsonl").exists()


def test_skipping_and_backward_transitions_are_rejected_without_mutation(tmp_path):
    root = make_experiment(tmp_path, "designed")
    before = (root / "experiment.yaml").read_bytes()
    with pytest.raises(LifecycleError, match="forbidden transition"):
        transition_stage(root, "reviewed", reason="skip", actor="operator")
    assert (root / "experiment.yaml").read_bytes() == before
    assert not (root / "stage-history.jsonl").exists()


def test_abandonment_is_permitted_before_publication(tmp_path):
    assert "abandoned" in allowed_transitions("idea")
    assert "abandoned" in allowed_transitions("reviewed")
    assert allowed_transitions("published") == frozenset()


def test_reason_actor_and_timezone_are_mandatory(tmp_path):
    root = make_experiment(tmp_path)
    for kwargs, message in [
        ({"reason": "", "actor": "alice"}, "reason"),
        ({"reason": "ready", "actor": ""}, "actor"),
        ({"reason": "ready", "actor": "alice", "timestamp": datetime(2026, 1, 1)}, "timezone"),
    ]:
        with pytest.raises(LifecycleError, match=message):
            transition_stage(root, "designed", **kwargs)
    assert yaml.safe_load((root / "experiment.yaml").read_text())["stage"] == "idea"


def test_legacy_experiment_without_history_can_transition(tmp_path):
    root = make_experiment(tmp_path, "analyzed")
    transition_stage(
        root,
        "reviewed",
        reason="Independent review complete",
        actor="reviewer",
        timestamp=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )
    assert read_stage_history(root)[0]["from_stage"] == "analyzed"


def test_tampered_or_discontinuous_history_blocks_transition(tmp_path):
    root = make_experiment(tmp_path, "designed")
    (root / "stage-history.jsonl").write_text(
        json.dumps(
            {
                "from_stage": "idea",
                "to_stage": "designed",
                "reason": "ready",
                "actor": "alice",
                "timestamp": "2026-07-12T00:00:00Z",
            }
        )
        + "\n"
        + json.dumps(
            {
                "from_stage": "running",
                "to_stage": "analyzed",
                "reason": "done",
                "actor": "alice",
                "timestamp": "2026-07-12T01:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(LifecycleError, match="discontinuous"):
        transition_stage(root, "running", reason="go", actor="alice")
