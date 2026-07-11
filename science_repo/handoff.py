from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .campaign import _normalize_write_scope


REQUIRED_FIELDS = (
    "schema_version",
    "campaign_id",
    "task_id",
    "agent_role",
    "status",
    "summary",
    "outputs",
    "evidence",
    "unresolved",
    "recommended_next",
)
HANDOFF_STATUSES = {"complete", "blocked", "failed"}


def load_handoff(path: Path) -> dict[str, Any]:
    """Load a JSON or YAML handoff without applying campaign-specific policy."""
    text = path.read_text(encoding="utf-8")
    value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def _inside_scope(path: str, scopes: list[str]) -> bool:
    normalized = _normalize_write_scope(path)
    if normalized is None:
        return False
    parts = PurePosixPath(normalized).parts
    return any(parts[: len(PurePosixPath(scope).parts)] == PurePosixPath(scope).parts for scope in scopes)


def validate_handoff(data: dict[str, Any], campaign: dict[str, Any]) -> list[str]:
    """Validate the handoff contract and bind it to one campaign task.

    This deliberately returns errors instead of raising so schedulers can reject an
    untrusted worker response without losing the rest of a campaign validation report.
    """
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("campaign_id") != campaign.get("id"):
        errors.append("campaign_id does not match campaign")

    tasks = campaign.get("tasks", [])
    matching = [task for task in tasks if isinstance(task, dict) and task.get("id") == data.get("task_id")]
    if not matching:
        errors.append(f"unknown campaign task: {data.get('task_id')!r}")
        task: dict[str, Any] | None = None
    else:
        task = matching[0]
        if data.get("agent_role") != task.get("role"):
            errors.append("agent_role does not match campaign task role")

    status = data.get("status")
    if status not in HANDOFF_STATUSES:
        errors.append(f"invalid handoff status: {status!r}")
    if not isinstance(data.get("summary"), str) or not data.get("summary", "").strip():
        errors.append("summary must be a non-empty string")

    for field in ("outputs", "evidence", "unresolved", "recommended_next"):
        value = data.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(f"{field} must be an array of non-empty strings")

    changed_files = data.get("changed_files", [])
    if not isinstance(changed_files, list) or any(
        not isinstance(item, str) or not item.strip() for item in changed_files
    ):
        errors.append("changed_files must be an array of non-empty strings")

    if status == "complete" and not data.get("evidence"):
        errors.append("complete handoff must include evidence")
    if status in {"blocked", "failed"} and not data.get("unresolved"):
        errors.append(f"{status} handoff must describe unresolved work")

    if task is not None:
        scopes = [
            scope
            for value in task.get("write_scope", [])
            if (scope := _normalize_write_scope(value)) is not None
        ]
        for field in ("outputs", "changed_files"):
            value = data.get(field, [])
            if isinstance(value, list):
                for path in value:
                    if isinstance(path, str) and path.strip() and not _inside_scope(path, scopes):
                        errors.append(f"{field} path is outside task write_scope: {path}")
    return errors
