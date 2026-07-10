from __future__ import annotations

from typing import Any


def validate_campaign(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
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
    return errors

