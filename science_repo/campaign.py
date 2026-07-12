from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any


def _normalize_write_scope(value: Any) -> str | None:
    """Return a comparable repository-relative scope, or None when unsafe."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("\\", "/")
    path = PurePosixPath(raw)
    segments = raw.split("/")
    if (
        path.is_absolute()
        or raw.startswith("/")
        or (segments and segments[0].endswith(":"))
        or any(part in (".", "..") for part in segments)
        or any(not part for part in segments[:-1])
    ):
        return None
    # PurePosixPath removes a trailing slash, making ``work/a`` and ``work/a/`` equivalent.
    return path.as_posix()


def _scopes_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    common = min(len(left_parts), len(right_parts))
    return left_parts[:common] == right_parts[:common]


def validate_campaign(
    data: dict[str, Any],
    schema_path: Path | None = None,
    instance_path: Path | None = None,
    project_manifest: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    if schema_path is not None:
        from .contracts import pinned_contract_errors

        structural = pinned_contract_errors(
            data,
            schema_path,
            instance_path or Path("campaign.yaml"),
            "campaign",
            project_manifest,
        )
        errors.extend(structural)
        if structural:
            return errors
    for field in ("schema_version", "id", "title", "objective", "status", "owner", "tasks"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        return errors + ["tasks must be an array"]
    task_ids = [task.get("id") for task in tasks if isinstance(task, dict)]
    if len(task_ids) != len(set(task_ids)):
        errors.append("task ids must be unique")
    known = set(task_ids)
    graph: dict[str, list[str]] = {}
    scopes: dict[str, list[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("every task must be a mapping")
            continue
        task_id = task.get("id", "<missing-id>")
        dependencies = task.get("depends_on", [])
        graph[str(task_id)] = list(dependencies)
        missing = set(dependencies) - known
        if missing:
            errors.append(f"{task_id}: unknown dependencies {sorted(missing)}")
        if not task.get("write_scope"):
            errors.append(f"{task_id}: write_scope must not be empty")
        elif not isinstance(task.get("write_scope"), list):
            errors.append(f"{task_id}: write_scope must be an array")
        else:
            normalized: list[str] = []
            for scope in task["write_scope"]:
                safe_scope = _normalize_write_scope(scope)
                if safe_scope is None:
                    errors.append(f"{task_id}: unsafe write_scope {scope!r}; use a repository-relative path")
                else:
                    normalized.append(safe_scope)
            scopes[str(task_id)] = normalized

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            errors.append(f"dependency cycle: {' -> '.join(trail + [node])}")
            return
        if node in visited or node not in graph:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(str(dependency), trail + [node])
        visiting.remove(node)
        visited.add(node)

    for task_id in graph:
        visit(task_id, [])

    def depends_on(task_id: str, dependency_id: str, seen: set[str] | None = None) -> bool:
        if task_id == dependency_id:
            return True
        seen = set() if seen is None else seen
        if task_id in seen:
            return False
        seen.add(task_id)
        return any(
            str(dependency) == dependency_id or depends_on(str(dependency), dependency_id, seen)
            for dependency in graph.get(task_id, [])
        )

    # Unordered tasks can be dispatched concurrently. Their declared write sets must be disjoint;
    # an explicit dependency is the opt-in mechanism for serial access to the same path.
    scope_tasks = sorted(scopes)
    for index, left_id in enumerate(scope_tasks):
        for right_id in scope_tasks[index + 1 :]:
            if depends_on(left_id, right_id) or depends_on(right_id, left_id):
                continue
            collisions = sorted(
                {f"{left} <> {right}" for left in scopes[left_id] for right in scopes[right_id] if _scopes_overlap(left, right)}
            )
            if collisions:
                errors.append(
                    f"concurrent write_scope overlap: {left_id} and {right_id}: {', '.join(collisions)}"
                )
    return errors
