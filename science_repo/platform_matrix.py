"""Deterministic, evidence-labelled cross-platform capability planning.

This module deliberately separates a *plan* from evidence that a job or feature
has actually run.  Capability probes are injectable and an absent observation is
``unknown`` -- never an implicit success.
"""

from __future__ import annotations

import platform
from collections.abc import Callable, Mapping, Sequence
from typing import Any


Probe = Callable[[str], bool | None]

CAPABILITIES = (
    "filesystem.fsync",
    "filesystem.junction",
    "filesystem.symlink",
    "process.tree_termination",
    "tool.git_worktree",
)
SYSTEMS = ("linux", "macos", "windows")

# Tests remain stable identifiers so CI configuration can consume this data.
TEST_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "core": (),
    "filesystem-fsync": ("filesystem.fsync",),
    "filesystem-symlink": ("filesystem.symlink",),
    "process-tree": ("process.tree_termination",),
    "worktree": ("tool.git_worktree",),
    "windows-junction": ("filesystem.junction",),
}


def _system(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {"darwin": "macos", "win32": "windows", "win": "windows"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in SYSTEMS:
        raise ValueError(f"unsupported platform label: {value!r}")
    return normalized


def _observed(value: object) -> str:
    # Strict identity checks avoid treating arbitrary truthy values as evidence.
    if value is True:
        return "available"
    if value is False:
        return "unavailable"
    return "unknown"


def capability_matrix(
    *,
    system: str | None = None,
    python_version: str | None = None,
    observations: Mapping[str, bool | None] | None = None,
    probe: Probe | None = None,
) -> dict[str, Any]:
    """Build a deterministic matrix from explicit or injected observations.

    A probe is called only for capabilities missing from ``observations``. Probe
    errors and non-boolean answers become ``unknown``. The default performs no
    privileged or mutating feature probes.
    """
    target = _system(system or platform.system())
    supplied = observations or {}
    capabilities: dict[str, dict[str, str]] = {}
    for name in CAPABILITIES:
        source = "observation" if name in supplied else "unobserved"
        value: object = supplied.get(name)
        if name not in supplied and probe is not None:
            source = "probe"
            try:
                value = probe(name)
            except Exception:
                value = None
        capabilities[name] = {"state": _observed(value), "source": source}

    applicable = {
        name: requirements
        for name, requirements in TEST_REQUIREMENTS.items()
        if name != "windows-junction" or target == "windows"
    }
    required = ["core", "filesystem-fsync", "process-tree", "worktree"]
    optional = sorted(set(applicable) - set(required))
    selection: dict[str, list[str]] = {"ready": [], "blocked": [], "unknown": []}
    for test, requirements in sorted(applicable.items()):
        states = [capabilities[item]["state"] for item in requirements]
        bucket = "blocked" if "unavailable" in states else "unknown" if "unknown" in states else "ready"
        selection[bucket].append(test)

    return {
        "schema_version": 1,
        "platform": target,
        "python": python_version or platform.python_version(),
        "capabilities": capabilities,
        "test_policy": {"required": required, "optional": optional},
        "test_selection": selection,
    }


def ci_job_plan(
    *, platforms: Sequence[str] = SYSTEMS,
    python_versions: Sequence[str] = ("3.11", "3.12", "3.13"),
) -> dict[str, Any]:
    """Return CI job-plan data; it is explicitly not execution evidence."""
    jobs = [
        {"id": f"{system}-py{version}", "platform": system, "python": version, "state": "planned"}
        for system in sorted({_system(item) for item in platforms})
        for version in sorted(set(python_versions))
    ]
    return {"schema_version": 1, "evidence": "none", "jobs": jobs}

