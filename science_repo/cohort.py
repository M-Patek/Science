"""Preparation contracts for registered, outcome-blind experiment cohorts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import yaml


REQUIRED_MODEL_METADATA = {
    "provider", "model_name", "exact_model_or_version_id",
    "inference_runtime_and_version", "agent_harness_and_version",
    "system_prompt_hash_or_unavailable_reason",
    "developer_prompt_hash_or_unavailable_reason", "tool_names_and_versions",
    "permission_and_network_policy", "sampling_parameters", "context_window_limit",
    "reported_input_output_cached_tokens_or_unavailable_reason",
}
REGISTERED_ONBOARDING_TASKS = {
    "T1-locate-contracts", "T2-create-experiment", "T3-validate-experiment",
    "T4-run-review", "T5-human-gate",
}


def _document_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def _prompt_hash(tasks: list[dict[str, Any]]) -> str:
    value = "\n".join(f"{task['id']}\n{task['prompt']}" for task in tasks)
    return hashlib.sha256(value.encode()).hexdigest()


def load_cohort(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("cohort manifest must be a mapping")
    return data


def validate_cohort(cohort_path: Path, *, campaign_path: Path, project_path: Path) -> list[str]:
    """Validate a frozen cohort without creating observation artifacts."""
    errors: list[str] = []
    cohort = load_cohort(cohort_path)
    base = cohort_path.parent
    campaign = yaml.safe_load(campaign_path.read_text(encoding="utf-8"))
    project = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    frozen = cohort.get("frozen_materials", {})
    for filename, key in (("protocol.md", "protocol_sha256"), ("rubric.md", "rubric_sha256")):
        if frozen.get(key) != _document_hash(base / filename):
            errors.append(f"{key} does not match {filename}")
    tasks = cohort.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty array")
        tasks = []
    else:
        ids = [task.get("id") for task in tasks if isinstance(task, dict)]
        if len(ids) != len(tasks) or len(ids) != len(set(ids)):
            errors.append("tasks must have unique ids")
        if set(ids) != REGISTERED_ONBOARDING_TASKS:
            errors.append("task set does not match the registered onboarding benchmark")
        if any(not isinstance(task.get("prompt"), str) or not task["prompt"] for task in tasks):
            errors.append("every task must have a non-empty prompt")
        if frozen.get("prompt_set_sha256") != _prompt_hash(tasks):
            errors.append("prompt_set_sha256 does not match registered tasks")
    revision = cohort.get("framework", {}).get("git_commit")
    if campaign.get("framework_revision_under_test") != revision:
        errors.append("campaign framework revision does not match cohort")
    framework = project.get("framework", {})
    if framework.get("version") != cohort.get("framework", {}).get("version"):
        errors.append("project framework version does not match cohort")
    if project.get("contracts") != cohort.get("contracts"):
        errors.append("project contract versions do not match cohort")
    minimum = cohort.get("minimum_uncensored_sessions")
    each_minimum = cohort.get("assignment", {}).get("each_task_minimum")
    if not isinstance(minimum, int) or minimum < 1:
        errors.append("minimum_uncensored_sessions must be a positive integer")
    elif isinstance(each_minimum, int) and minimum < len(tasks) * each_minimum:
        errors.append("minimum session count cannot cover every registered task")
    if not isinstance(each_minimum, int) or each_minimum < 1:
        errors.append("each_task_minimum must be a positive integer")
    missing = REQUIRED_MODEL_METADATA - set(cohort.get("required_model_metadata", []))
    if missing:
        errors.append(f"required model metadata missing: {sorted(missing)}")
    isolation = cohort.get("isolation", {})
    if isolation.get("writable_copy_per_session") is not True:
        errors.append("each session must have an independent writable copy")
    if isolation.get("fresh_agent_context") is not True:
        errors.append("each session must have a fresh agent context")
    if isolation.get("cross_session_messages") != "forbidden":
        errors.append("cross-session messages must be forbidden")
    return errors


def generate_preassignment(
    cohort: dict[str, Any], session_ids: Sequence[str], *, copy_mechanism: str = "git-worktree"
) -> dict[str, Any]:
    """Produce a deterministic ledger before outcomes exist.

    Caller-provided session IDs are stable opaque identities. Copy and context IDs are
    derived separately and are therefore mechanically checkable for independence.
    """
    minimum = cohort["minimum_uncensored_sessions"]
    tasks = cohort["tasks"]
    if len(session_ids) < minimum:
        raise ValueError(f"at least {minimum} sessions are required")
    if len(set(session_ids)) != len(session_ids) or any(not value for value in session_ids):
        raise ValueError("session ids must be non-empty and unique")
    accepted = cohort.get("isolation", {}).get("accepted_copy_mechanisms", [])
    if copy_mechanism not in accepted:
        raise ValueError(f"copy mechanism is not registered: {copy_mechanism}")
    rows = []
    for index, session_id in enumerate(session_ids):
        stable = hashlib.sha256(f"{cohort['cohort_id']}\n{session_id}".encode()).hexdigest()[:20]
        rows.append({
            "session_id": session_id,
            "task_id": tasks[index % len(tasks)]["id"],
            "copy_id": f"copy-{stable}",
            "copy_mechanism": copy_mechanism,
            "context_id": f"context-{stable}",
        })
    ledger = {"schema_version": 1, "cohort_id": cohort["cohort_id"], "assignments": rows}
    ledger["assignment_sha256"] = hashlib.sha256(
        json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ledger


def validate_preassignment(cohort: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = ledger.get("assignments", [])
    known = {task["id"] for task in cohort.get("tasks", [])}
    if ledger.get("cohort_id") != cohort.get("cohort_id"):
        errors.append("ledger cohort_id does not match cohort")
    if len(rows) < cohort.get("minimum_uncensored_sessions", 0):
        errors.append("ledger has fewer than the minimum sessions")
    for field in ("session_id", "copy_id", "context_id"):
        values = [row.get(field) for row in rows]
        if any(not value for value in values) or len(values) != len(set(values)):
            errors.append(f"{field} values must be non-empty and unique")
    accepted = set(cohort.get("isolation", {}).get("accepted_copy_mechanisms", []))
    if any(row.get("copy_mechanism") not in accepted for row in rows):
        errors.append("ledger contains an unregistered copy mechanism")
    counts = {task_id: 0 for task_id in known}
    for row in rows:
        if row.get("task_id") not in known:
            errors.append(f"unknown task assignment: {row.get('task_id')}")
        else:
            counts[row["task_id"]] += 1
    required = cohort.get("assignment", {}).get("each_task_minimum", 1)
    if any(count < required for count in counts.values()):
        errors.append("ledger does not satisfy per-task minimum coverage")
    expected = dict(ledger)
    supplied = expected.pop("assignment_sha256", None)
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if supplied != digest:
        errors.append("assignment_sha256 does not match ledger")
    return errors
