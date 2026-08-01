from datetime import datetime, timezone

import pytest

from science_repo.scheduler import RetryPolicy, schedule_campaign


NOW = datetime(2026, 7, 11, tzinfo=timezone.utc)


def campaign(*tasks):
    return {"tasks": list(tasks)}


def task(task_id, *dependencies, status="pending"):
    return {"id": task_id, "status": status, "depends_on": list(dependencies)}


def states(decision):
    return {item.task_id: (item.state, item.reason) for item in decision.tasks}


def test_dag_classifies_ready_completed_and_dependency_blocked():
    result = schedule_campaign(
        campaign(task("done", status="complete"), task("next", "done"), task("last", "next")),
        now=NOW,
    )
    assert states(result) == {
        "done": ("completed", "completed"),
        "next": ("ready", "dependencies_satisfied"),
        "last": ("blocked", "dependencies_incomplete"),
    }
    assert [item.task_id for item in result.ready] == ["next"]


def test_live_and_expired_leases_are_distinguished():
    manifest = campaign(task("live"), task("expired"))
    runtime = {
        "live": {"status": "leased", "attempt": 1, "expires_at": "2026-07-11T00:01:00Z"},
        "expired": {"status": "leased", "attempt": 1, "expires_at": "2026-07-10T23:59:00Z"},
    }
    result = schedule_campaign(manifest, runtime, now=NOW)
    assert states(result) == {"live": ("leased", "active_lease"), "expired": ("ready", "retry")}


def test_retry_budget_exhaustion_propagates_failure_transitively():
    manifest = campaign(task("root"), task("child", "root"), task("grandchild", "child"))
    runtime = {"root": {"status": "failed", "attempt": 2}}
    result = schedule_campaign(manifest, runtime, retry_policy=RetryPolicy(max_attempts=2), now=NOW)
    assert states(result) == {
        "root": ("blocked", "retries_exhausted"),
        "child": ("blocked", "dependency_failed"),
        "grandchild": ("blocked", "dependency_failed"),
    }


def test_failed_attempt_with_budget_is_ready_to_retry():
    result = schedule_campaign(
        campaign(task("work")),
        {"work": {"status": "failed", "attempt": 1}},
        retry_policy=RetryPolicy(max_attempts=2),
        now=NOW,
    )
    assert states(result) == {"work": ("ready", "retry")}


def test_runtime_completion_unlocks_dependent_task():
    result = schedule_campaign(
        campaign(task("first"), task("second", "first")),
        {"first": {"status": "completed", "attempt": 1}},
        now=NOW,
    )
    assert states(result)["second"] == ("ready", "dependencies_satisfied")


@pytest.mark.parametrize(
    "manifest,error",
    [
        (campaign(task("same"), task("same")), "duplicate"),
        (campaign(task("task", "missing")), "unknown dependency"),
        (campaign(task("a", "b"), task("b", "a")), "cycle"),
    ],
)
def test_invalid_graph_is_rejected(manifest, error):
    with pytest.raises(ValueError, match=error):
        schedule_campaign(manifest, now=NOW)


def test_retry_policy_must_allow_initial_attempt():
    with pytest.raises(ValueError, match="at least 1"):
        RetryPolicy(max_attempts=0)
