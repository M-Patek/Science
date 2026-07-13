"""Fail-closed construction of explicit subject-task/workspace contracts."""
from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from science_repo.contracts import schema_errors


class SubjectPacketError(ValueError):
    """A freeze cannot be converted into safe subject packets."""


_ABSOLUTE = re.compile(r"(^|[\s'\"=(])(?:[A-Za-z]:[\\/]|/|\\\\)")
_SECRET = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|password|private[_-]?key)\s*[:=]")


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise SubjectPacketError("packet source path must be a string")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in value:
        raise SubjectPacketError(f"unsafe packet source path: {value!r}")
    if any(part in {".git", "data", "records", ".env"} for part in path.parts):
        raise SubjectPacketError(f"prohibited packet source path: {value!r}")
    return path


def _validate_freeze(freeze: Mapping[str, Any]) -> None:
    """Validate the pinned structure and the invariants used to construct packets."""
    if not isinstance(freeze, Mapping):
        raise SubjectPacketError("cohort freeze must be an object")
    schema = Path(__file__).resolve().parent / "assets" / "project" / "schemas" / "cohort-freeze.schema.json"
    errors = schema_errors(dict(freeze), schema, Path("<cohort-freeze>"), expected_version=1)
    if errors:
        raise SubjectPacketError(f"cohort freeze schema is invalid: {errors[0]}")

    fixtures = freeze["fixtures"]
    fixture_ids = [item["fixture_id"] for item in fixtures]
    if len(set(fixture_ids)) != 12:
        raise SubjectPacketError("cohort freeze fixture ids must be unique")
    material_keys: set[tuple[str, str]] = set()
    file_paths: set[str] = set()
    for kind, materials in (("fixture", fixtures), ("baseline", freeze["baseline_materials"])):
        for material in materials:
            if kind == "fixture" and (set(material) != {"fixture_id", "tree_sha256", "files"}):
                raise SubjectPacketError("fixture materials must have exactly fixture_id, tree_sha256, and files")
            if kind == "baseline" and (set(material) != {"path", "tree_sha256", "files"}):
                raise SubjectPacketError("baseline materials must have exactly path, tree_sha256, and files")
            identity = material.get("fixture_id") if kind == "fixture" else material.get("path")
            key = (kind, identity)
            if key in material_keys:
                raise SubjectPacketError("cohort freeze contains duplicate materials")
            material_keys.add(key)
            entries = material["files"]
            if material["tree_sha256"] != _hash(_canonical(entries)):
                raise SubjectPacketError("cohort freeze material tree hash is invalid")
            for item in entries:
                _safe_relative(item["path"])
                if item["path"] in file_paths:
                    raise SubjectPacketError("cohort freeze contains duplicate file paths")
                file_paths.add(item["path"])

    arms = freeze["randomization"]["arms"]
    expected = {(fixture_id, arm) for fixture_id in fixture_ids for arm in arms}
    ledger = freeze["assignment_ledger"]
    actual = {(row["fixture_id"], row["arm"]) for row in ledger}
    if actual != expected or len(actual) != 24:
        raise SubjectPacketError("assignment ledger does not cover every fixture-arm cell exactly once")
    if len({row["cell_id"] for row in ledger}) != 24:
        raise SubjectPacketError("assignment cell ids must be unique")
    if {row["execution_order"] for row in ledger} != set(range(1, 25)):
        raise SubjectPacketError("assignment execution orders must be unique and complete")


def _reject_link_components(root: Path, relative: PurePosixPath) -> Path:
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        try:
            info = candidate.lstat()
        except OSError as error:
            raise SubjectPacketError(f"packet source is missing: {relative}") from error
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or attributes & reparse:
            raise SubjectPacketError(f"packet source path contains a link or reparse point: {relative}")
    return candidate


def _verified_files(freeze: Mapping[str, Any], source_root: Path) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    root = source_root.resolve(strict=True)
    fixtures: dict[str, list[dict[str, str]]] = {}
    baseline: list[dict[str, str]] = []
    for material in list(freeze.get("fixtures", [])) + list(freeze.get("baseline_materials", [])):
        target = fixtures.setdefault(material["fixture_id"], []) if "fixture_id" in material else baseline
        for item in material.get("files", []):
            relative = _safe_relative(item["path"])
            candidate = _reject_link_components(root, relative)
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError) as error:
                raise SubjectPacketError(f"packet source missing or outside source root: {item['path']}") from error
            if candidate.is_symlink() or not stat.S_ISREG(candidate.stat().st_mode):
                raise SubjectPacketError(f"packet source must be a regular non-link file: {item['path']}")
            payload = resolved.read_bytes()
            if _hash(payload) != item.get("sha256"):
                raise SubjectPacketError(f"packet source hash mismatch: {item['path']}")
            if b"\x00" not in payload:
                text = payload.decode("utf-8", errors="strict")
                if _ABSOLUTE.search(text) or _SECRET.search(text):
                    raise SubjectPacketError(f"negative content audit rejected: {item['path']}")
            target.append({"source_path": item["path"], "sha256": item["sha256"]})
    return fixtures, baseline


def build_subject_packet_set(*, freeze: Mapping[str, Any], source_root: Path) -> dict[str, Any]:
    """Create 24 explicit contracts; this neither creates worktrees nor authorizes dispatch."""
    try:
        _validate_freeze(freeze)
        unsigned = dict(freeze)
        claimed = unsigned.pop("freeze_sha256", None)
        if not isinstance(claimed, str) or claimed != _hash(_canonical(unsigned)):
            raise SubjectPacketError("cohort freeze hash is invalid")
        ledger = freeze["assignment_ledger"]
        fixtures, baseline = _verified_files(freeze, source_root)
    except SubjectPacketError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OSError) as error:
        raise SubjectPacketError("cohort freeze contains malformed material values") from error
    packets = []
    identities: set[str] = set()
    for row in sorted(ledger, key=lambda value: value.get("execution_order", 0)):
        cell_id, fixture_id = row.get("cell_id"), row.get("fixture_id")
        if not isinstance(cell_id, str) or fixture_id not in fixtures:
            raise SubjectPacketError("assignment references an invalid cell or fixture")
        stem = _hash(f"{claimed}\n{cell_id}\n".encode())[:24]
        session, worktree, context = (f"session-{stem}", f"worktree-{stem}", f"context-{stem}")
        for identity in (session, worktree, context):
            if identity in identities:
                raise SubjectPacketError("session, worktree, and context identities must be globally unique")
            identities.add(identity)
        packet = {
            "cell_id": cell_id, "fixture_id": fixture_id, "arm": row.get("arm"),
            "execution_order": row.get("execution_order"), "attempt_ordinal": 1,
            "replacement_policy": {"maximum_replacements": 0, "rule": "no-implicit-replacement-censor-cell"},
            "session_id": session, "worktree_id": worktree, "context_id": context,
            "workspace_contract": {
                "cwd": f"subject-workspaces/{stem}", "dedicated_worktree_required": True,
                "fork_context_required": "none", "network_required": False,
                "host_enforcement": "required-but-not-attested-by-this-contract",
            },
            "inputs": {"fixture_files": fixtures[fixture_id], "baseline_files": baseline},
            "dispatch_allowed": False,
        }
        packet["packet_sha256"] = _hash(_canonical(packet))
        packets.append(packet)
    if len({row["cell_id"] for row in packets}) != 24 or sorted(row["execution_order"] for row in packets) != list(range(1, 25)):
        raise SubjectPacketError("assignment cell ids and execution orders must be unique and complete")
    result = {
        "schema_version": 1, "cohort_id": freeze.get("cohort_id"), "freeze_sha256": claimed,
        "packet_count": 24, "dispatch_allowed": False,
        "host_enforcement": "unverified", "negative_audit": "passed-path-content-and-hash-v1",
        "packets": packets,
    }
    result["packet_set_sha256"] = _hash(_canonical(result))
    return result
