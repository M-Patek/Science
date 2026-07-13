"""Fail-closed registration of an outcome-blind, two-arm research cohort."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

STATIC_RUNTIME_IDENTITY_FIELDS = {
    "provider", "model_name", "exact_model_or_version_id",
    "inference_runtime_and_version", "agent_harness_and_version",
    "system_prompt_hash_or_unavailable_reason",
    "developer_prompt_hash_or_unavailable_reason", "tool_names_and_versions",
    "permission_and_network_policy", "sampling_parameters", "context_window_limit",
}
RUNTIME_RECEIPT_FIELDS = {"receipt_id", "authority_id", "source", "issued_at", "identity_sha256"}


class CohortFreezeError(ValueError):
    """The proposed freeze is incomplete or conflicts with an existing freeze."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as error:
        raise CohortFreezeError(f"material is missing or outside registration root: {path}") from error


def _material_digest(path: Path, root: Path) -> tuple[str, list[dict[str, str]]]:
    """Hash names, types, and bytes; reject links and special files."""
    if path.is_symlink():
        raise CohortFreezeError(f"links are not allowed in frozen materials: {path}")
    relative = _relative(path, root)
    candidates = [path] if path.is_file() else sorted(path.rglob("*"), key=lambda item: item.as_posix())
    entries: list[dict[str, str]] = []
    for candidate in candidates:
        if candidate.is_symlink():
            raise CohortFreezeError(f"links are not allowed in frozen materials: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise CohortFreezeError(f"special files are not allowed in frozen materials: {candidate}")
        entries.append({"path": _relative(candidate, root), "sha256": _sha256(candidate.read_bytes())})
    if not entries:
        raise CohortFreezeError(f"frozen material has no files: {relative}")
    return _sha256(_canonical(entries)), entries


def _runtime_identity(value: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(STATIC_RUNTIME_IDENTITY_FIELDS - set(value))
    if missing:
        raise CohortFreezeError(f"runtime identity is missing required fields: {missing}")
    unknown = sorted(set(value) - STATIC_RUNTIME_IDENTITY_FIELDS)
    if unknown:
        raise CohortFreezeError(f"runtime identity has unknown fields: {unknown}")
    for key, item in value.items():
        if item is None or item == "" or item == [] or item == {}:
            raise CohortFreezeError(f"runtime identity field is empty: {key}")
    # JSON round-trip rejects non-serializable host objects and detaches caller data.
    try:
        identity = json.loads(json.dumps(dict(value), sort_keys=True))
    except (TypeError, ValueError) as error:
        raise CohortFreezeError("runtime identity must be JSON serializable") from error
    receipt_missing = sorted(RUNTIME_RECEIPT_FIELDS - set(receipt))
    if receipt_missing:
        raise CohortFreezeError(f"runtime identity receipt is missing required fields: {receipt_missing}")
    if set(receipt) != RUNTIME_RECEIPT_FIELDS or any(not isinstance(receipt[key], str) or not receipt[key] for key in receipt):
        raise CohortFreezeError("runtime identity receipt must contain only non-empty string fields")
    if receipt["identity_sha256"] != _sha256(_canonical(identity)):
        raise CohortFreezeError("runtime identity receipt does not bind the static identity")
    return {
        "static_identity": identity,
        "source_receipt": dict(receipt),
        "receipt_verification": "supplied-not-cryptographically-verified",
        "post_run_usage": "not-known-before-execution",
    }


def build_cohort_freeze(
    *,
    cohort_id: str,
    registration_root: Path,
    fixtures: Sequence[tuple[str, Path]],
    baseline_materials: Sequence[Path],
    registration_materials: Sequence[Path] = (),
    human_supplied_seed: str,
    runtime_identity: Mapping[str, Any],
    runtime_identity_receipt: Mapping[str, Any],
    arms: tuple[str, str] = ("control", "treatment"),
) -> dict[str, Any]:
    """Build a deterministic freeze. This does not authorize or execute any work."""
    if not cohort_id.strip():
        raise CohortFreezeError("cohort_id must be non-empty")
    if len(fixtures) != 12:
        raise CohortFreezeError("exactly 12 fixtures are required")
    fixture_ids = [item[0] for item in fixtures]
    if any(not value.strip() for value in fixture_ids) or len(set(fixture_ids)) != 12:
        raise CohortFreezeError("fixture ids must be non-empty and unique")
    if not isinstance(human_supplied_seed, str) or not human_supplied_seed:
        raise CohortFreezeError("a non-empty human-supplied seed is required")
    if len(arms) != 2 or len(set(arms)) != 2 or any(not arm for arm in arms):
        raise CohortFreezeError("exactly two distinct non-empty arms are required")
    root = registration_root.resolve(strict=True)
    frozen_fixtures = []
    for fixture_id, path in sorted(fixtures, key=lambda item: item[0]):
        digest, entries = _material_digest(path, root)
        frozen_fixtures.append({"fixture_id": fixture_id, "tree_sha256": digest, "files": entries})
    baselines = []
    for path in sorted(baseline_materials, key=lambda item: item.as_posix()):
        digest, entries = _material_digest(path, root)
        baselines.append({"path": _relative(path, root), "tree_sha256": digest, "files": entries})
    if not baselines:
        raise CohortFreezeError("at least one baseline material is required")
    registrations = []
    for path in sorted(registration_materials, key=lambda item: item.as_posix()):
        digest, entries = _material_digest(path, root)
        registrations.append({"path": _relative(path, root), "tree_sha256": digest, "files": entries})

    seed_commitment = _sha256(human_supplied_seed.encode("utf-8"))
    cells = [(fixture_id, arm) for fixture_id in fixture_ids for arm in arms]
    ranked = sorted(cells, key=lambda value: _sha256(
        f"{human_supplied_seed}\n{cohort_id}\n{value[0]}\n{value[1]}".encode()
    ))
    assignments = [
        {"cell_id": f"{fixture_id}::{arm}", "fixture_id": fixture_id, "arm": arm, "execution_order": index + 1}
        for index, (fixture_id, arm) in enumerate(ranked)
    ]
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "cohort_id": cohort_id,
        "registration_status": "materials-frozen-dispatch-blocked",
        "dispatch_allowed": False,
        "fixture_count": 12,
        "fixtures": frozen_fixtures,
        "baseline_materials": baselines,
        "registration_materials": registrations,
        "randomization": {"method": "sha256-ranked-cells-v1", "seed_sha256": seed_commitment, "arms": list(arms)},
        "assignment_ledger": assignments,
        "runtime_identity": _runtime_identity(runtime_identity, runtime_identity_receipt),
        "authority": "none-this-artifact-is-not-authorization",
        "observations": "none-recorded",
    }
    artifact["freeze_sha256"] = _sha256(_canonical(artifact))
    return artifact


def register_cohort_freeze(output_path: Path, **kwargs: Any) -> dict[str, Any]:
    """Atomically create a freeze; identical repeats succeed, conflicts fail closed."""
    artifact = build_cohort_freeze(**kwargs)
    payload = _canonical(artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        if output_path.read_bytes() == payload:
            return artifact
        raise CohortFreezeError(f"conflicting cohort freeze already exists: {output_path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output_path)
        except FileExistsError:
            if output_path.read_bytes() != payload:
                raise CohortFreezeError(f"conflicting cohort freeze already exists: {output_path}")
        return artifact
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
