from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .contracts import schema_errors


ENTITY_KINDS = frozenset({"dataset", "artifact", "run", "code"})
RELATION_KINDS = frozenset({"derived_from", "generated_by", "used", "code_at"})
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WINDOWS_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE)


def load_lineage(path: Path) -> dict[str, Any]:
    """Load a lineage manifest without applying a framework-current contract."""
    data = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".json"
        else yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if not isinstance(data, dict):
        raise ValueError(f"{path}: lineage manifest must be an object")
    return data


def lineage_digest(manifest: dict[str, Any]) -> str:
    """Return a stable digest independent of mapping order and presentation."""
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _safe_project_path(value: Any, root: Path) -> str | None:
    if not isinstance(value, str) or not value:
        return "must be a non-empty string"
    if "\\" in value:
        return "must use POSIX separators"
    candidate = PurePosixPath(value)
    if value == "." or candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        return "must be a normalized project-relative path"
    for part in candidate.parts:
        if any(ord(character) < 32 or ord(character) == 127 for character in part):
            return "must not contain control characters"
        if ":" in part:
            return "must not contain drive or alternate-data-stream separators"
        if part.endswith((".", " ")):
            return "must not contain segments ending in a dot or space"
        if _WINDOWS_RESERVED.fullmatch(part):
            return "must not contain Windows reserved device names"
    resolved_root = root.resolve()
    resolved = (root / Path(*candidate.parts)).resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return "escapes the project root (including through a symlink)"
    return None


def validate_lineage(
    manifest: dict[str, Any],
    manifest_path: Path,
    project_root: Path,
    *,
    schema_path: Path | None = None,
    expected_version: int = 1,
) -> list[str]:
    """Validate structural, path, reference, and DAG lineage invariants.

    A schema is used only when explicitly supplied. This prevents legacy or
    generated projects from being silently upgraded to the installed contract.
    """
    errors: list[str] = []
    if schema_path is not None:
        if not schema_path.is_file():
            errors.append(f"{schema_path}: missing pinned lineage contract schema")
        else:
            errors.extend(
                schema_errors(
                    manifest, schema_path, manifest_path, expected_version=expected_version
                )
            )

    if manifest.get("schema_version") != expected_version:
        errors.append(
            f"{manifest_path}: schema_version must equal pinned version {expected_version}"
        )

    entities = manifest.get("entities")
    relations = manifest.get("relations")
    if not isinstance(entities, list):
        errors.append(f"{manifest_path}: entities must be an array")
    if not isinstance(relations, list):
        errors.append(f"{manifest_path}: relations must be an array")
    if not isinstance(entities, list) or not isinstance(relations, list):
        return errors

    ids: set[str] = set()
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            errors.append(f"{manifest_path}: entities[{index}] must be an object")
            continue
        entity_id = entity.get("id")
        if not isinstance(entity_id, str) or not _ID_RE.fullmatch(entity_id):
            errors.append(f"{manifest_path}: entities[{index}].id is not a valid lineage ID")
        elif entity_id in ids:
            errors.append(f"{manifest_path}: duplicate entity id {entity_id!r}")
        else:
            ids.add(entity_id)
        if entity.get("kind") not in ENTITY_KINDS:
            errors.append(f"{manifest_path}: entities[{index}].kind is unsupported")
        digest = entity.get("digest")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            errors.append(f"{manifest_path}: entities[{index}].digest must be a sha256 digest")
        location = entity.get("path")
        if location is not None:
            problem = _safe_project_path(location, project_root)
            if problem:
                errors.append(f"{manifest_path}: entities[{index}].path {problem}")

    graph: dict[str, set[str]] = {entity_id: set() for entity_id in ids}
    seen_edges: set[tuple[str, str, str]] = set()
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append(f"{manifest_path}: relations[{index}] must be an object")
            continue
        source, target, kind = (
            relation.get("source"), relation.get("target"), relation.get("kind")
        )
        if kind not in RELATION_KINDS:
            errors.append(f"{manifest_path}: relations[{index}].kind is unsupported")
        if source not in ids:
            errors.append(f"{manifest_path}: relations[{index}].source references unknown entity {source!r}")
        if target not in ids:
            errors.append(f"{manifest_path}: relations[{index}].target references unknown entity {target!r}")
        if source == target and source in ids:
            errors.append(f"{manifest_path}: relations[{index}] is a self relation")
        edge = (source, target, kind)
        if edge in seen_edges:
            errors.append(f"{manifest_path}: duplicate relation {edge!r}")
        seen_edges.add(edge)
        if source in ids and target in ids and source != target:
            graph[source].add(target)

    indegree = {node: 0 for node in graph}
    for children in graph.values():
        for child in children:
            indegree[child] += 1
    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    consumed = 0
    while ready:
        node = ready.pop(0)
        consumed += 1
        for child in sorted(graph[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()
    if consumed != len(graph):
        errors.append(f"{manifest_path}: lineage relations must form a directed acyclic graph")
    return errors
