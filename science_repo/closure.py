"""High-level, runtime-neutral closure of one native-agent dispatch.

This module joins the deterministic dispatch audit to ``CampaignCoordinator``.
It deliberately does not start, authenticate, or communicate with an agent.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .coordinator import AuditReceipt, CampaignCoordinator
from .dispatch import audit_dispatch_handoff, create_dispatch_envelope
from .scheduler import RetryPolicy


class ClosureError(RuntimeError):
    """A dispatch result failed the integration boundary."""


def accept_dispatch_handoff(
    coordinator_root: str | Path,
    campaign: dict[str, Any],
    envelope: dict[str, Any],
    handoff: dict[str, Any],
    *,
    auditor: str,
    audited_at: str,
    reviewer_approved: bool = False,
    human_gate_approved: bool = False,
    runtime_states: Mapping[str, Mapping[str, Any] | None] | None = None,
    retry_policy: RetryPolicy | None = None,
    now: datetime | None = None,
    schema_path: Path | None = None,
    instance_path: Path | None = None,
    project_manifest: Path | None = None,
) -> dict[str, Any]:
    """Audit and accept one handoff, returning a JSON-serializable decision.

    ``audited_at`` is required rather than synthesized so retries can reuse the
    same evidence identity and remain idempotent. Review and human-gate approval
    are separate, explicit inputs and default to denial.
    """
    if not isinstance(auditor, str) or not auditor.strip():
        raise ClosureError("auditor must be a non-empty string")
    if not isinstance(audited_at, str) or not audited_at.strip():
        raise ClosureError("audited_at must be a non-empty timezone-aware ISO timestamp")
    if not isinstance(reviewer_approved, bool) or not isinstance(human_gate_approved, bool):
        raise ClosureError("gate approvals must be explicit booleans")
    try:
        audit_instant = datetime.fromisoformat(audited_at.strip().replace("Z", "+00:00"))
        offset = audit_instant.utcoffset()
    except (TypeError, ValueError, OverflowError) as error:
        raise ClosureError("audited_at must be a valid timezone-aware ISO timestamp") from error
    if audit_instant.tzinfo is None or offset is None:
        raise ClosureError("audited_at must be a valid timezone-aware ISO timestamp")
    normalized_audited_at = audit_instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    # The envelope crossed an untrusted boundary. It must be exactly the packet
    # derived from the current authoritative campaign, not merely agree on ids.
    try:
        expected = create_dispatch_envelope(campaign, str(envelope.get("task_id", "")))
    except (TypeError, ValueError) as error:
        raise ClosureError(str(error)) from error
    if envelope != expected:
        raise ClosureError("dispatch envelope does not match authoritative campaign")

    errors = audit_dispatch_handoff(
        envelope,
        handoff,
        campaign,
        schema_path=schema_path,
        instance_path=instance_path,
        project_manifest=project_manifest,
    )
    if errors:
        raise ClosureError("dispatch audit failed: " + "; ".join(errors))

    receipt = AuditReceipt(
        campaign_id=str(envelope["campaign_id"]),
        task_id=str(envelope["task_id"]),
        agent_role=str(envelope["agent_role"]),
        auditor=auditor.strip(),
        audited_at=normalized_audited_at,
        handoff_sha256=CampaignCoordinator.handoff_sha256(handoff),
        errors=(),
    )
    accepted = CampaignCoordinator(coordinator_root).accept_handoff(
        campaign,
        handoff,
        receipt,
        runtime_states=runtime_states,
        reviewer_approved=reviewer_approved,
        human_gate_approved=human_gate_approved,
        retry_policy=retry_policy,
        now=now,
    )
    return {
        "task_state": dict(accepted.task_state),
        "schedule": {"tasks": [asdict(task) for task in accepted.schedule.tasks]},
        "idempotent": accepted.idempotent,
    }
