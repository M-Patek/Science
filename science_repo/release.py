"""Offline, deterministic release integrity manifests.

This module hashes only files explicitly supplied by the caller.  It does not
discover release inputs, contact a registry, scan for vulnerabilities, or sign
artifacts.
"""

from __future__ import annotations

from hashlib import sha256
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Iterable, Mapping, Any
import zipfile


MANIFEST_VERSION = 1
_WHEEL_VERSION = re.compile(r"^[^-]+-(?P<version>[^-]+)-[^-]+-[^-]+-[^-]+\.whl$")


class ReleaseIntegrityError(ValueError):
    """Raised when a release input or manifest is unsafe or inconsistent."""


def _is_linklike(path: Path) -> bool:
    """Detect symlinks and, where the runtime exposes it, Windows reparse points."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    try:
        if is_junction is not None and is_junction():
            return True
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except (OSError, ValueError):
        # Let resolve(strict=True) below provide the definitive missing/access error.
        return False
    fallback_flag = 0x400 if os.name == "nt" else 0
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", fallback_flag)
    return bool(reparse_flag and attributes & reparse_flag)


def _safe_file(root: Path, supplied: str | Path) -> tuple[Path, str]:
    root = root.resolve(strict=True)
    path = Path(supplied)
    candidate = path if path.is_absolute() else root / path

    # Resolve only after checking every existing component: resolve() would
    # otherwise hide a symlink that happens to point back inside the root.
    try:
        relative_candidate = candidate.relative_to(root)
    except ValueError as exc:
        raise ReleaseIntegrityError(f"path is outside release root: {supplied}") from exc
    current = root
    for part in relative_candidate.parts:
        if part in ("", ".", ".."):
            raise ReleaseIntegrityError(f"unsafe release path: {supplied}")
        current = current / part
        if _is_linklike(current):
            raise ReleaseIntegrityError(
                f"symlinks, junctions, and reparse points are not release evidence: {supplied}"
            )
    resolved = candidate.resolve(strict=True)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ReleaseIntegrityError(f"path escapes release root: {supplied}") from exc
    if not resolved.is_file():
        raise ReleaseIntegrityError(f"release input is not a regular file: {supplied}")
    return resolved, relative.as_posix()


def _artifact_type(path: str, schema_paths: set[str]) -> str:
    if path in schema_paths:
        return "packaged-schema"
    if path.endswith(".whl"):
        return "wheel"
    if path.endswith((".tar.gz", ".zip")):
        return "source-distribution"
    return "file"


def _safe_version(path: Path, artifact_type: str) -> str | None:
    if artifact_type != "wheel":
        return None
    match = _WHEEL_VERSION.match(path.name)
    if not match:
        return None
    filename_version = match.group("version")
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(candidates) != 1:
                return None
            info = archive.getinfo(candidates[0])
            if info.file_size > 1_000_000:
                return None
            raw = archive.read(info).decode("utf-8", errors="strict")
        versions = [line[9:].strip() for line in raw.splitlines() if line.startswith("Version: ")]
        return versions[0] if len(versions) == 1 and versions[0] == filename_version else None
    except (OSError, UnicodeError, zipfile.BadZipFile, KeyError):
        return None


def observed_python_dependencies() -> dict[str, Any]:
    """Return installed distribution metadata, explicitly scoped as observation."""
    packages: dict[tuple[str, str], dict[str, str]] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if name and version:
            key = (name.casefold(), version)
            packages[key] = {"name": name, "version": version}
    return {
        "kind": "observed-python-distribution-metadata",
        "packages": [packages[key] for key in sorted(packages)],
        "limitations": (
            "Observed from the generating Python environment; this is not a dependency lock, "
            "vulnerability scan, license audit, signature, or attestation."
        ),
    }


def generate_release_manifest(
    root: str | Path,
    files: Iterable[str | Path],
    *,
    packaged_schemas: Iterable[str | Path] = (),
    include_dependencies: bool = False,
) -> dict[str, Any]:
    """Hash explicitly listed release files relative to *root*."""
    root_path = Path(root)
    schema_entries = [_safe_file(root_path, item) for item in packaged_schemas]
    schema_paths = {relative for _, relative in schema_entries}
    if len(schema_paths) != len(schema_entries):
        raise ReleaseIntegrityError("duplicate packaged schema path")
    entries = [_safe_file(root_path, item) for item in files]
    paths = [relative for _, relative in entries]
    if len(set(paths)) != len(paths):
        raise ReleaseIntegrityError("duplicate release file path")
    if not schema_paths.issubset(paths):
        missing = sorted(schema_paths - set(paths))
        raise ReleaseIntegrityError(f"packaged schemas must also be listed as files: {missing}")

    artifacts = []
    for path, relative in sorted(entries, key=lambda item: item[1]):
        artifact_type = _artifact_type(relative, schema_paths)
        content = path.read_bytes()
        entry: dict[str, Any] = {
            "path": relative,
            "sha256": sha256(content).hexdigest(),
            "size": len(content),
            "type": artifact_type,
        }
        version = _safe_version(path, artifact_type)
        if version is not None:
            entry["version"] = version
        artifacts.append(entry)
    result: dict[str, Any] = {"manifest_version": MANIFEST_VERSION, "artifacts": artifacts}
    if include_dependencies:
        result["dependency_inventory"] = observed_python_dependencies()
    return result


def manifest_json(manifest: Mapping[str, Any]) -> str:
    """Serialize a manifest reproducibly."""
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def verify_release_manifest(root: str | Path, manifest: Mapping[str, Any]) -> list[str]:
    """Return deterministic mismatch descriptions; unsafe manifests raise."""
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ReleaseIntegrityError("unsupported release manifest version")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReleaseIntegrityError("manifest artifacts must be a list")
    seen: set[str] = set()
    mismatches: list[str] = []
    for entry in artifacts:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
            raise ReleaseIntegrityError("invalid release artifact entry")
        raw_path = entry["path"]
        if PurePosixPath(raw_path).is_absolute() or "\\" in raw_path:
            raise ReleaseIntegrityError(f"unsafe manifest path: {raw_path}")
        path, relative = _safe_file(Path(root), raw_path)
        if relative != raw_path or relative in seen:
            raise ReleaseIntegrityError(f"duplicate or non-canonical manifest path: {raw_path}")
        seen.add(relative)
        expected_hash = entry.get("sha256")
        expected_size = entry.get("size")
        artifact_type = entry.get("type")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ReleaseIntegrityError(f"invalid sha256 in manifest: {relative}")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size < 0:
            raise ReleaseIntegrityError(f"invalid size in manifest: {relative}")
        if artifact_type not in {"file", "wheel", "source-distribution", "packaged-schema"}:
            raise ReleaseIntegrityError(f"invalid artifact type in manifest: {relative}")
        inferred = _artifact_type(relative, {relative} if artifact_type == "packaged-schema" else set())
        if inferred != artifact_type:
            raise ReleaseIntegrityError(f"artifact type disagrees with path: {relative}")
        if "version" in entry and not isinstance(entry["version"], str):
            raise ReleaseIntegrityError(f"invalid version in manifest: {relative}")
        content = path.read_bytes()
        actual_hash = sha256(content).hexdigest()
        actual_size = len(content)
        if entry.get("sha256") != actual_hash:
            mismatches.append(f"{relative}: sha256 mismatch")
        if entry.get("size") != actual_size:
            mismatches.append(f"{relative}: size mismatch")
    return sorted(mismatches)
