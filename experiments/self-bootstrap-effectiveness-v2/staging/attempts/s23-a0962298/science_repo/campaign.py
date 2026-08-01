from __future__ import annotations

from pathlib import Path, PurePosixPath
import json
import yaml

from .contracts import schema_errors
from .subject_packets import SubjectPacketError, build_subject_packet_set
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


def validate_generated_task_outputs(project_root: Path, campaign: dict[str, Any], task_id: str) -> list[str]:
    """Apply pinned semantic checks to framework self-study generator tasks."""
    # These validators implement a preregistered study contract, not global
    # semantics for coincidentally identical task names in unrelated projects.
    try:
        project = yaml.safe_load((project_root / "science-project.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        project = None
    if campaign.get("id") != "self-bootstrap-v2" or not isinstance(project, dict) or project.get("id") != "framework-self-study":
        return []
    tasks = {task.get("id"): task for task in campaign.get("tasks", []) if isinstance(task, dict)}
    task = tasks.get(task_id)
    if task is None or task_id not in {"register-executable-cohort", "prepare-sanitized-subject-packets"}:
        return []
    outputs = task.get("outputs", [])
    if not isinstance(outputs, list):
        return [f"{task_id}: outputs must be an array"]
    if task_id == "register-executable-cohort":
        candidates = [item for item in outputs if str(item).endswith("cohort-freeze.json")]
        if len(candidates) != 1:
            return [f"{task_id}: exactly one cohort-freeze.json output is required"]
        path = project_root / candidates[0]
        try:
            freeze = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return [f"{task_id}: cohort freeze cannot be read: {error}"]
        schema = project_root / "schemas" / "cohort-freeze.schema.json"
        errors = schema_errors(freeze, schema, path, expected_version=1)
        verification = freeze.get("runtime_identity", {}).get("receipt_verification")
        if verification != "supplied-not-cryptographically-verified":
            errors.append(f"{task_id}: unexpected runtime receipt verification state")
        if freeze.get("dispatch_allowed") is not False:
            errors.append(f"{task_id}: preparation freeze must remain dispatch-blocked")
        if freeze.get("registration_status") != "materials-frozen-dispatch-blocked":
            errors.append(f"{task_id}: unexpected registration status")
        return errors
    candidates = [item for item in outputs if str(item).endswith("packet-manifest.json")]
    freeze_inputs = [item for item in task.get("inputs", []) if str(item).endswith("cohort-freeze.json")]
    if len(candidates) != 1 or len(freeze_inputs) != 1:
        return [f"{task_id}: one packet manifest and one cohort freeze are required"]
    try:
        freeze = json.loads((project_root / freeze_inputs[0]).read_text(encoding="utf-8"))
        actual = json.loads((project_root / candidates[0]).read_text(encoding="utf-8"))
        expected = build_subject_packet_set(freeze=freeze, source_root=project_root)
    except (OSError, ValueError, SubjectPacketError, KeyError) as error:
        return [f"{task_id}: generated packet validation failed: {error}"]
    return [] if actual == expected else [f"{task_id}: packet manifest is not the deterministic builder output"]
