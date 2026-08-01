"""Pure campaign scheduling decisions.

This module deliberately performs no I/O and starts no workers.  Callers provide a
campaign manifest and snapshots returned by :class:`TaskRuntime`; the result says
which tasks may be claimed and why the others may not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


_COMPLETE = frozenset({"complete", "completed"})
_FAILURE = frozenset({"failed", "cancelled", "canceled"})


@dataclass(frozen=True)
class RetryPolicy:
    """Bound attempts for failed or expired work (the initial claim is attempt 1)."""

    max_attempts: int = 3
    retryable_outcomes: frozenset[str] = frozenset({"failed", "released"})

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


@dataclass(frozen=True)
class TaskDecision:
    task_id: str
    state: str
    reason: str
    attempt: int = 0


@dataclass(frozen=True)
class ScheduleDecision:
    tasks: tuple[TaskDecision, ...]

    def with_state(self, state: str) -> tuple[TaskDecision, ...]:
        return tuple(task for task in self.tasks if task.state == state)

    @property
    def ready(self) -> tuple[TaskDecision, ...]:
        return self.with_state("ready")

    @property
    def blocked(self) -> tuple[TaskDecision, ...]:
        return self.with_state("blocked")

    @property
    def leased(self) -> tuple[TaskDecision, ...]:
        return self.with_state("leased")

    @property
    def completed(self) -> tuple[TaskDecision, ...]:
        return self.with_state("completed")


def schedule_campaign(
    campaign: Mapping[str, Any],
    runtime_states: Mapping[str, Mapping[str, Any] | None] | None = None,
    *,
    retry_policy: RetryPolicy | None = None,
    now: datetime | None = None,
) -> ScheduleDecision:
    """Classify campaign tasks in manifest order without mutating runtime state.

    An expired lease is treated like a retryable failure.  Once its attempt budget
    is exhausted, failure is propagated transitively to dependent tasks.
    """

    policy = retry_policy or RetryPolicy()
    snapshots = runtime_states or {}
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    task_list = campaign.get("tasks", [])
    if not isinstance(task_list, list):
        raise ValueError("campaign tasks must be an array")
    tasks: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    for task in task_list:
        if not isinstance(task, Mapping) or not isinstance(task.get("id"), str):
            raise ValueError("every campaign task must have a string id")
        task_id = task["id"]
        if task_id in tasks:
            raise ValueError(f"duplicate task id: {task_id}")
        tasks[task_id] = task
        order.append(task_id)

    decisions: dict[str, TaskDecision] = {}
    visiting: set[str] = set()

    def decide(task_id: str) -> TaskDecision:
        if task_id in decisions:
            return decisions[task_id]
        if task_id in visiting:
            raise ValueError(f"dependency cycle involving {task_id}")
        if task_id not in tasks:
            raise ValueError(f"unknown dependency: {task_id}")
        visiting.add(task_id)
        task = tasks[task_id]
        runtime = snapshots.get(task_id) or {}
        attempt = _attempt(runtime)
        manifest_status = str(task.get("status", "pending")).lower()
        runtime_status = str(runtime.get("status", "")).lower()

        if manifest_status in _COMPLETE or runtime_status in _COMPLETE:
            result = TaskDecision(task_id, "completed", "completed", attempt)
        elif runtime_status == "leased" and not _expired(runtime, instant):
            result = TaskDecision(task_id, "leased", "active_lease", attempt)
        else:
            dependencies = task.get("depends_on", [])
            if not isinstance(dependencies, list):
                raise ValueError(f"{task_id}: depends_on must be an array")
            dependency_decisions = [decide(str(dependency)) for dependency in dependencies]
            failed_dependencies = [
                dependency.task_id
                for dependency in dependency_decisions
                if dependency.state == "blocked"
                and dependency.reason in {"retries_exhausted", "dependency_failed", "terminal_failure"}
            ]
            incomplete = [dependency.task_id for dependency in dependency_decisions if dependency.state != "completed"]
            exhausted = attempt >= policy.max_attempts and (
                runtime_status in policy.retryable_outcomes or (runtime_status == "leased" and _expired(runtime, instant))
            )
            if manifest_status in _FAILURE or (runtime_status in _FAILURE and runtime_status not in policy.retryable_outcomes):
                result = TaskDecision(task_id, "blocked", "terminal_failure", attempt)
            elif exhausted:
                result = TaskDecision(task_id, "blocked", "retries_exhausted", attempt)
            elif failed_dependencies:
                result = TaskDecision(task_id, "blocked", "dependency_failed", attempt)
            elif incomplete:
                result = TaskDecision(task_id, "blocked", "dependencies_incomplete", attempt)
            else:
                reason = "retry" if attempt else "dependencies_satisfied"
                result = TaskDecision(task_id, "ready", reason, attempt)
        visiting.remove(task_id)
        decisions[task_id] = result
        return result

    return ScheduleDecision(tuple(decide(task_id) for task_id in order))


def _attempt(state: Mapping[str, Any]) -> int:
    try:
        attempt = int(state.get("attempt", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("runtime attempt must be a non-negative integer") from error
    if attempt < 0:
        raise ValueError("runtime attempt must be a non-negative integer")
    return attempt


def _expired(state: Mapping[str, Any], now: datetime) -> bool:
    expires_at = state.get("expires_at")
    if not isinstance(expires_at, str):
        return True
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expiry.tzinfo is None:
        return True
    return expiry <= now
