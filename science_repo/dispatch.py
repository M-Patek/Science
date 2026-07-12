"""Runtime-neutral dispatch envelopes for platform-native agent delegation.

This module intentionally does not transport prompts or start agents.  It turns a
validated campaign task into a small, deterministic data packet which a main agent
can pass to an existing native delegation primitive (for example ``spawn_agent``),
then binds the returned handoff to that packet.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .campaign import validate_campaign
from .handoff import REQUIRED_FIELDS, validate_handoff


DISPATCH_SCHEMA_VERSION = 1
_TASK_FIELDS = (
    "id",
    "role",
    "depends_on",
    "inputs",
    "outputs",
    "write_scope",
    "review_required",
    "human_gate",
)


def create_dispatch_envelope(campaign: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Create a deterministic prompt envelope for one valid campaign task.

    The packet is pure data: callers remain responsible for choosing and invoking
    an agent platform.  Raising on an invalid campaign prevents a main agent from
    dispatching work whose DAG or concurrent write boundaries are already unsafe.
    """
    errors = validate_campaign(campaign)
    if errors:
        raise ValueError("invalid campaign: " + "; ".join(errors))

    matches = [
        task
        for task in campaign.get("tasks", [])
        if isinstance(task, dict) and task.get("id") == task_id
    ]
    if not matches:
        raise ValueError(f"unknown campaign task: {task_id!r}")
    task = matches[0]
    task_contract = {field: deepcopy(task.get(field)) for field in _TASK_FIELDS if field in task}

    prompt = (
        f"Execute campaign task {task_id!r} as role {task.get('role')!r}. "
        "Read only the listed inputs and repository instructions needed for the assigned scope. "
        "Do not modify paths outside write_scope or rewrite immutable evidence. "
        "Return a structured handoff matching handoff_contract; report blocked/failed work truthfully."
    )
    return {
        "schema_version": DISPATCH_SCHEMA_VERSION,
        "campaign_id": campaign["id"],
        "task_id": task_id,
        "agent_role": task.get("role"),
        "prompt": prompt,
        "task": task_contract,
        "handoff_contract": {
            "schema_version": 1,
            "required_fields": list(REQUIRED_FIELDS),
            "optional_fields": ["changed_files"],
            "allowed_statuses": ["complete", "blocked", "failed"],
        },
    }


def audit_dispatch_handoff(
    envelope: dict[str, Any],
    handoff: dict[str, Any],
    campaign: dict[str, Any],
    *,
    schema_path: Path | None = None,
    instance_path: Path | None = None,
    project_manifest: Path | None = None,
) -> list[str]:
    """Audit a worker handoff against both its dispatch packet and campaign."""
    errors: list[str] = []
    if envelope.get("schema_version") != DISPATCH_SCHEMA_VERSION:
        errors.append("dispatch schema_version must be 1")
    for field in ("campaign_id", "task_id", "agent_role"):
        if handoff.get(field) != envelope.get(field):
            errors.append(f"handoff {field} does not match dispatch envelope")

    # Also re-bind to the authoritative campaign.  The packet is convenient, not
    # an authority boundary, and may have crossed an untrusted transport.
    errors.extend(
        validate_handoff(
            handoff,
            campaign,
            schema_path=schema_path,
            instance_path=instance_path,
            project_manifest=project_manifest,
        )
    )
    return list(dict.fromkeys(errors))
