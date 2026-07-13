"""Host-observed harness receipt for self-study cohort runtime registration.

This module generates and verifies receipts from the agent harness environment.
Receipts are **declarative, not cryptographic**: they record values exposed to
the current process under harness environment naming conventions, but they do
not prove that the values are true.  The evidence label remains
``host-observed-unsigned`` for contract compatibility; it does not mean that an
OS, provider, or independent host authority observed or endorsed the values.

Environment variables read (all optional; missing values are recorded as
``unavailable`` with a reason):

- ``CLAUDE_CODE_SESSION_ID`` – opaque session identifier
- ``CLAUDE_CODE_CHILD_SESSION`` – ``1`` if this is a child/dispatch session
- ``ANTHROPIC_MODEL`` – model identifier (e.g. ``claude-opus-4-8``)
- ``AI_AGENT`` – harness name and version (e.g. ``claude-code_2-1-195_agent``)
- ``CLAUDE_EFFORT`` – effort/sampling setting (e.g. ``xhigh``)

These variables may be conventionally exposed by a harness and are **not**
cryptographically signed.  A user or parent process can override them.  The
receipt cannot open a dispatch gate by itself.  It may be referenced by an
explicit local unsigned-acceptance policy, or verified through a stronger
host-owned attestation path; those are separate trust tracks.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


class HarnessReceiptError(ValueError):
    """A receipt is malformed, inconsistent, or cannot be verified."""


@dataclass(frozen=True, slots=True)
class HarnessReceipt:
    """A host-observed declaration of the runtime environment.

    All string fields are non-empty when present; ``None`` means the value was
    not available from the harness.
    """

    receipt_id: str
    generated_at: str
    schema_version: int = 1
    evidence_level: str = "host-observed-unsigned"
    attestation_policy: str = "harness-env-declarative"

    # Identity
    session_id: str | None = None
    session_id_unavailable_reason: str | None = None
    child_session: bool | None = None

    # Model / runtime
    provider: str | None = None
    model_name: str | None = None
    exact_model_or_version_id: str | None = None
    model_unavailable_reason: str | None = None

    # Harness
    agent_harness_and_version: str | None = None
    harness_unavailable_reason: str | None = None

    # Configuration
    effort_setting: str | None = None
    effort_unavailable_reason: str | None = None

    # Canonical hash of the above (excluding this field itself)
    receipt_sha256: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, str) or not self.receipt_id.strip():
            raise HarnessReceiptError("receipt_id must be a non-empty string")
        if not isinstance(self.generated_at, str):
            raise HarnessReceiptError("generated_at must be a string")
        if self.attestation_policy != "harness-env-declarative":
            raise HarnessReceiptError("unsupported attestation policy")
        for name in (
            "session_id", "session_id_unavailable_reason", "provider", "model_name",
            "exact_model_or_version_id", "model_unavailable_reason",
            "agent_harness_and_version", "harness_unavailable_reason",
            "effort_setting", "effort_unavailable_reason",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise HarnessReceiptError(f"{name} must be a non-empty string or null")
        if self.child_session is not None and not isinstance(self.child_session, bool):
            raise HarnessReceiptError("child_session must be boolean or null")
        # Validate timestamps
        try:
            parsed = datetime.fromisoformat(self.generated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise HarnessReceiptError("generated_at must be timezone-aware")
        except ValueError as exc:
            raise HarnessReceiptError("generated_at must be a valid ISO timestamp") from exc

        # Validate evidence level
        if self.evidence_level != "host-observed-unsigned":
            raise HarnessReceiptError("unsupported evidence level")

        # Validate mutual exclusivity: value OR unavailable_reason, not both
        for value, reason, name in (
            (self.session_id, self.session_id_unavailable_reason, "session_id"),
            (self.model_name, self.model_unavailable_reason, "model"),
            (self.agent_harness_and_version, self.harness_unavailable_reason, "harness"),
            (self.effort_setting, self.effort_unavailable_reason, "effort"),
        ):
            if value is not None and reason is not None:
                raise HarnessReceiptError(f"{name} and its unavailable_reason are mutually exclusive")
            if value is None and reason is None:
                raise HarnessReceiptError(f"one of {name} or its unavailable_reason is required")

        # Compute and verify canonical hash
        canonical = self._canonical_dict()
        expected = _sha256(canonical)
        if not self.receipt_sha256:
            object.__setattr__(self, "receipt_sha256", expected)
        elif self.receipt_sha256 != expected:
            raise HarnessReceiptError("receipt_sha256 does not match canonical content")
        if not re.fullmatch(r"[0-9a-f]{64}", self.receipt_sha256):
            raise HarnessReceiptError("receipt_sha256 must be lowercase SHA-256 hex")

    def _canonical_dict(self) -> dict[str, Any]:
        """Return the canonical dict used for hashing (excludes receipt_sha256)."""
        d = asdict(self)
        d.pop("receipt_sha256")
        return d

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict including the receipt_sha256."""
        return asdict(self)


def _sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_env(name: str) -> tuple[str | None, str | None]:
    """Read an environment variable; return (value, unavailable_reason)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None, f"environment variable {name} not set or empty"
    return raw.strip(), None


def _read_env_bool(name: str) -> tuple[bool | None, str | None]:
    """Read an environment variable as a boolean."""
    raw = os.environ.get(name)
    if raw is None:
        return None, f"environment variable {name} not set"
    return raw.strip() == "1", None


def generate_receipt(
    *,
    receipt_id: str | None = None,
    now: datetime | None = None,
) -> HarnessReceipt:
    """Generate a harness receipt from the current environment.

    All metadata is read from well-known environment variables set by the
    Claude Code CLI.  Missing variables are recorded as ``unavailable``.

    Args:
        receipt_id: Optional explicit receipt ID; defaults to a UUIDv4.
        now: Optional explicit generation time; defaults to UTC now.

    Returns:
        A frozen ``HarnessReceipt`` with a canonical SHA-256.
    """
    if receipt_id is None:
        from uuid import uuid4
        receipt_id = str(uuid4())

    generated_at = (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")

    session_id, session_id_unavailable_reason = _read_env("CLAUDE_CODE_SESSION_ID")
    child_session, child_unavailable = _read_env_bool("CLAUDE_CODE_CHILD_SESSION")

    model_name, model_unavailable_reason = _read_env("ANTHROPIC_MODEL")
    # ANTHROPIC_MODEL identifies the requested model/alias, not an immutable
    # provider build. Do not upgrade it into stronger provenance.
    exact_model_or_version_id = None

    harness, harness_unavailable_reason = _read_env("AI_AGENT")
    effort, effort_unavailable_reason = _read_env("CLAUDE_EFFORT")

    # A requested model alias does not establish provider identity.  Keep the
    # provider unknown rather than upgrading an environment claim into a fact.
    provider = None

    return HarnessReceipt(
        receipt_id=receipt_id,
        generated_at=generated_at,
        session_id=session_id,
        session_id_unavailable_reason=session_id_unavailable_reason,
        child_session=child_session,
        provider=provider,
        model_name=model_name,
        exact_model_or_version_id=exact_model_or_version_id,
        model_unavailable_reason=model_unavailable_reason,
        agent_harness_and_version=harness,
        harness_unavailable_reason=harness_unavailable_reason,
        effort_setting=effort,
        effort_unavailable_reason=effort_unavailable_reason,
    )


def verify_receipt(receipt_dict: Mapping[str, Any]) -> HarnessReceipt:
    """Verify a receipt dict and reconstruct the ``HarnessReceipt``.

    Checks:
    - Schema version is 1
    - All required fields are present with correct types
    - Canonical SHA-256 matches the content
    - Evidence level is ``host-observed-unsigned``
    - Timestamps are valid and timezone-aware
    - Mutual exclusivity of value vs. unavailable_reason holds

    Args:
        receipt_dict: A dict produced by ``HarnessReceipt.to_dict()``.

    Returns:
        A validated ``HarnessReceipt``.

    Raises:
        HarnessReceiptError: If any check fails.
    """
    required_fields = {
        "schema_version", "receipt_id", "generated_at", "evidence_level",
        "attestation_policy", "session_id", "session_id_unavailable_reason",
        "child_session", "provider", "model_name", "exact_model_or_version_id",
        "model_unavailable_reason", "agent_harness_and_version",
        "harness_unavailable_reason", "effort_setting", "effort_unavailable_reason",
        "receipt_sha256",
    }
    if set(receipt_dict) != required_fields:
        raise HarnessReceiptError(f"receipt fields mismatch: expected {sorted(required_fields)}, got {sorted(receipt_dict)}")

    if receipt_dict.get("schema_version") != 1:
        raise HarnessReceiptError("schema_version must be 1")

    receipt_sha256 = receipt_dict.get("receipt_sha256")
    if not isinstance(receipt_sha256, str) or not receipt_sha256:
        raise HarnessReceiptError("receipt_sha256 must be a non-empty string")

    # Build the receipt; __post_init__ validates everything including the hash
    try:
        return HarnessReceipt(
            schema_version=1,
            receipt_id=receipt_dict["receipt_id"],
            generated_at=receipt_dict["generated_at"],
            evidence_level=receipt_dict["evidence_level"],
            attestation_policy=receipt_dict["attestation_policy"],
            session_id=receipt_dict["session_id"],
            session_id_unavailable_reason=receipt_dict["session_id_unavailable_reason"],
            child_session=receipt_dict["child_session"],
            provider=receipt_dict["provider"],
            model_name=receipt_dict["model_name"],
            exact_model_or_version_id=receipt_dict["exact_model_or_version_id"],
            model_unavailable_reason=receipt_dict["model_unavailable_reason"],
            agent_harness_and_version=receipt_dict["agent_harness_and_version"],
            harness_unavailable_reason=receipt_dict["harness_unavailable_reason"],
            effort_setting=receipt_dict["effort_setting"],
            effort_unavailable_reason=receipt_dict["effort_unavailable_reason"],
            receipt_sha256=receipt_sha256,
        )
    except TypeError as exc:
        raise HarnessReceiptError(f"receipt field type error: {exc}") from exc


def generate_cohort_runtime_registration(
    *,
    cohort_id: str,
    receipt_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Generate a complete runtime-registration payload for a cohort manifest.

    This is the bridge between the harness receipt and the cohort registration
    contract.  It populates all ``required_model_metadata`` fields from
    ``cohort-v1.yaml``.

    Args:
        cohort_id: The cohort identifier (must match the manifest).
        receipt_id: Optional explicit receipt ID.
        now: Optional explicit generation time.

    Returns:
        A dict ready to be inserted into ``cohort-v1.yaml`` under
        ``runtime_registration``.
    """
    receipt = generate_receipt(receipt_id=receipt_id, now=now)
    r = receipt.to_dict()

    # Map receipt fields to cohort required_model_metadata
    # Fields that are unavailable in the harness receipt are passed through
    # as ``unavailable`` with the reason.
    def _val(field: str, unavailable_field: str) -> str:
        value = r.get(field)
        if value is not None:
            return str(value)
        reason = r.get(unavailable_field, "unknown")
        return f"unavailable: {reason}"

    return {
        "schema_version": 1,
        "cohort_id": cohort_id,
        "status": "declarative-observed-dispatch-blocked",
        "registered_at": r["generated_at"],
        "receipt_id": r["receipt_id"],
        "receipt_sha256": r["receipt_sha256"],
        "evidence_level": r["evidence_level"],
        "attestation_policy": r["attestation_policy"],

        # Required model metadata (cohort-v1.yaml required_model_metadata)
        "provider": "unavailable: process environment does not attest provider identity",
        "model_name": _val("model_name", "model_unavailable_reason"),
        "exact_model_or_version_id": "unavailable: harness exposes a model identifier, not an immutable provider build",
        "inference_runtime_and_version": "unavailable: not exposed by Claude Code CLI",
        "agent_harness_and_version": _val("agent_harness_and_version", "harness_unavailable_reason"),
        "system_prompt_hash_or_unavailable_reason": "unavailable: system prompt not exposed by harness",
        "developer_prompt_hash_or_unavailable_reason": "unavailable: developer prompt not exposed by harness",
        "tool_names_and_versions": "unavailable: tool versions not exposed by harness",
        "permission_and_network_policy": "unavailable: harness receipt does not observe host permission or network enforcement",
        "sampling_parameters": _val("effort_setting", "effort_unavailable_reason"),
        "context_window_limit": "unavailable: not exposed by Claude Code CLI",
        "reported_input_output_cached_tokens_or_unavailable_reason": "unavailable: token counts not exposed at session start",

        # Additional harness-specific metadata
        "session_id": _val("session_id", "session_id_unavailable_reason"),
        "child_session": (
            str(r["child_session"])
            if r["child_session"] is not None
            else "unavailable: CLAUDE_CODE_CHILD_SESSION not set"
        ),
    }
