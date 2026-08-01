"""Controlled transitions for an experiment's epistemic lifecycle.

``experiment.yaml`` remains the current-state projection.  Successful changes
are also recorded in ``stage-history.jsonl``; existing experiments without that
file are treated as legacy experiments and can make their first transition.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .io import load_yaml


TRANSITIONS: dict[str, frozenset[str]] = {
    "idea": frozenset({"designed", "abandoned"}),
    "designed": frozenset({"running", "abandoned"}),
    "running": frozenset({"analyzed", "abandoned"}),
    "analyzed": frozenset({"reviewed", "abandoned"}),
    "reviewed": frozenset({"published", "abandoned"}),
    # Terminal states deliberately have no escape hatch.  A correction or a
    # resumed line of inquiry must be represented by a new experiment.
    "published": frozenset(),
    "abandoned": frozenset(),
}

HISTORY_FILENAME = "stage-history.jsonl"


class LifecycleError(ValueError):
    """Raised when a lifecycle transition or its audit history is invalid."""


def allowed_transitions(stage: str) -> frozenset[str]:
    """Return the possible next stages, rejecting unknown source stages."""

    if stage not in TRANSITIONS:
        raise LifecycleError(f"unknown experiment stage: {stage!r}")
    return TRANSITIONS[stage]


def read_stage_history(experiment_root: Path) -> list[dict[str, str]]:
    """Read and validate the append-only stage history.

    A history is allowed to start at any stage so that experiments created
    before lifecycle auditing was introduced remain compatible.
    """

    path = Path(experiment_root) / HISTORY_FILENAME
    if not path.exists():
        return []

    entries: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise LifecycleError(f"{HISTORY_FILENAME}:{line_number}: empty line")
        try:
            entry: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LifecycleError(f"{HISTORY_FILENAME}:{line_number}: invalid JSON") from exc
        required = {"from_stage", "to_stage", "reason", "actor", "timestamp"}
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise LifecycleError(f"{HISTORY_FILENAME}:{line_number}: invalid transition entry")
        if any(not isinstance(entry[key], str) or not entry[key].strip() for key in required):
            raise LifecycleError(f"{HISTORY_FILENAME}:{line_number}: transition fields must be non-empty strings")
        source, target = entry["from_stage"], entry["to_stage"]
        if target not in allowed_transitions(source):
            raise LifecycleError(f"{HISTORY_FILENAME}:{line_number}: forbidden transition {source!r} -> {target!r}")
        _parse_timestamp(entry["timestamp"])
        if entries and entries[-1]["to_stage"] != source:
            raise LifecycleError(f"{HISTORY_FILENAME}:{line_number}: transition chain is discontinuous")
        entries.append({key: entry[key] for key in ("from_stage", "to_stage", "reason", "actor", "timestamp")})
    return entries


def transition_stage(
    experiment_root: Path,
    to_stage: str,
    *,
    reason: str,
    actor: str,
    timestamp: str | datetime | None = None,
) -> dict[str, str]:
    """Apply one permitted stage transition and append its audit event.

    Validation happens before either file is changed.  The manifest is replaced
    atomically and the history entry is appended with an fsync.  If appending
    fails, a best-effort atomic rollback restores the original manifest.
    """

    root = Path(experiment_root)
    manifest_path = root / "experiment.yaml"
    manifest = load_yaml(manifest_path)
    source = manifest.get("stage")
    if not isinstance(source, str):
        raise LifecycleError("experiment manifest has no valid stage")
    if to_stage not in allowed_transitions(source):
        raise LifecycleError(f"forbidden transition {source!r} -> {to_stage!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise LifecycleError("transition reason must be a non-empty string")
    if not isinstance(actor, str) or not actor.strip():
        raise LifecycleError("transition actor must be a non-empty string")

    history = read_stage_history(root)
    if history and history[-1]["to_stage"] != source:
        raise LifecycleError("stage history does not match the manifest stage")

    instant = _normalise_timestamp(timestamp)
    entry = {
        "from_stage": source,
        "to_stage": to_stage,
        "reason": reason.strip(),
        "actor": actor.strip(),
        "timestamp": instant,
    }
    original = manifest_path.read_bytes()
    updated = dict(manifest)
    updated["stage"] = to_stage
    _atomic_write_yaml(manifest_path, updated)
    try:
        history_path = root / HISTORY_FILENAME
        with history_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        _atomic_write_bytes(manifest_path, original)
        raise
    return entry


def _normalise_timestamp(value: str | datetime | None) -> str:
    if value is None:
        instant = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        instant = value
    elif isinstance(value, str):
        instant = _parse_timestamp(value)
    else:
        raise LifecycleError("transition timestamp must be an ISO-8601 string or datetime")
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise LifecycleError("transition timestamp must include a timezone")
    return instant.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise LifecycleError("transition timestamp must be valid ISO-8601") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise LifecycleError("transition timestamp must include a timezone")
    return instant


def _atomic_write_yaml(path: Path, value: dict[str, Any]) -> None:
    payload = yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode("utf-8")
    _atomic_write_bytes(path, payload)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
