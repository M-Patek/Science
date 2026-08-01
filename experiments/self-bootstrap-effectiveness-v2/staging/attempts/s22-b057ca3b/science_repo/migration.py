"""Read-only planning for explicit project contract migrations.

The planner deliberately does not provide an apply operation.  A plan is evidence
for a human-reviewed migration; constructing it never changes the project.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


KNOWN_CONTRACTS = ("campaign", "experiment", "handoff")


@dataclass(frozen=True)
class ContractStep:
    contract: str
    current_version: int | None
    target_version: int | None
    status: str
    actions: tuple[str, ...]
    reason: str
    source_schema: str | None = None
    destination_schema: str | None = None
    schema_sha256: str | None = None
    source_schema_host_uri: str | None = None


@dataclass(frozen=True)
class MigrationPlan:
    manifest: str
    status: str
    legacy_without_local_schemas: bool
    steps: tuple[ContractStep, ...]
    errors: tuple[str, ...] = ()

    def to_dict(self, *, include_host_local: bool = False) -> dict[str, Any]:
        """Return the reproducible plan, optionally including diagnostic host URIs.

        Project paths and schema labels are POSIX, root-relative identifiers.  An
        absolute source location is deliberately excluded from the default form so
        identical inputs planned on Windows and POSIX have identical summaries.
        """
        result = asdict(self)
        if not include_host_local:
            for step in result["steps"]:
                step.pop("source_schema_host_uri", None)
        return result


def _version(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _schema_version(path: Path) -> tuple[int | None, str | None]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        value = document["properties"]["schema_version"]["const"]
        version = _version(value)
        if version is None:
            return None, "schema_version const must be a positive integer"
        return version, None
    except Exception as exc:
        return None, f"cannot read schema contract: {exc}"


def _overall_status(steps: tuple[ContractStep, ...], errors: tuple[str, ...]) -> str:
    if errors or any(step.status == "blocked" for step in steps):
        return "blocked"
    if any(step.status == "manual" for step in steps):
        return "manual"
    return "compatible"


def plan_contract_migration(
    project_root: Path,
    target_contracts: Mapping[str, object],
    available_schemas: Path,
) -> MigrationPlan:
    """Compare pinned contracts with an explicitly requested target.

    ``available_schemas`` is only inspected; schemas are never copied.  Version
    changes are classified ``manual`` even when a matching schema exists because
    JSON Schema equality cannot establish semantic compatibility.
    """
    root = project_root.resolve()
    manifest = root / "science-project.yaml"
    manifest_label = "science-project.yaml"
    errors: list[str] = []
    project: object = None
    try:
        project = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{manifest_label}: cannot read project manifest: {exc}")
    if not isinstance(project, dict):
        errors.append(f"{manifest_label}: project manifest must be a mapping")
        project = {}
    current = project.get("contracts")
    if not isinstance(current, dict):
        errors.append(f"{manifest_label}: contracts must be a mapping")
        current = {}

    unknown = sorted((set(current) | set(target_contracts)) - set(KNOWN_CONTRACTS))
    errors.extend(f"unknown contract: {name}" for name in unknown)
    local_schemas = root / "schemas"
    legacy = not local_schemas.is_dir()
    source_root = available_schemas.resolve()
    steps: list[ContractStep] = []

    for name in KNOWN_CONTRACTS:
        raw_current = current.get(name)
        raw_target = target_contracts.get(name)
        current_version = _version(raw_current)
        target_version = _version(raw_target)
        destination = local_schemas / f"{name}.schema.json"
        destination_label = f"schemas/{name}.schema.json"
        source = source_root / f"{name}.schema.json"
        source_label = f"available-schemas/{name}.schema.json"
        source_host_uri = source.as_uri()
        actions: tuple[str, ...] = ()

        if name not in target_contracts:
            steps.append(ContractStep(name, current_version, None, "blocked", (),
                                      "explicit target version is required"))
            continue
        if current_version is None or target_version is None:
            bad = "current" if current_version is None else "target"
            steps.append(ContractStep(name, current_version, target_version, "blocked", (),
                                      f"{bad} version must be a positive integer"))
            continue
        if target_version < current_version:
            steps.append(ContractStep(name, current_version, target_version, "blocked", (),
                                      "contract downgrades are not planned automatically"))
            continue

        schema_version, schema_error = _schema_version(source) if source.is_file() else (None, "schema is unavailable")
        if schema_error or schema_version != target_version:
            detail = schema_error or f"schema declares version {schema_version}, not {target_version}"
            steps.append(ContractStep(name, current_version, target_version, "blocked", (), detail,
                                      source_schema=source_label, destination_schema=destination_label,
                                      source_schema_host_uri=source_host_uri))
            continue

        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        local_matches = destination.is_file() and destination.read_bytes() == source.read_bytes()
        if current_version == target_version and local_matches:
            reason = "pin and project-local schema already match the requested contract"
            status = "compatible"
        elif current_version == target_version:
            actions = (f"copy schema to schemas/{name}.schema.json", f"validate {name} instances")
            reason = "pin is unchanged but the project-local schema is absent or differs"
            status = "manual"
        else:
            actions = (
                f"copy schema to schemas/{name}.schema.json",
                f"update contracts.{name} from {current_version} to {target_version}",
                f"validate {name} instances",
            )
            reason = "matching target schema is available; semantic review is still required"
            status = "manual"
        steps.append(ContractStep(name, current_version, target_version, status, actions, reason,
                                  source_label, destination_label, digest, source_host_uri))

    frozen_steps = tuple(steps)
    frozen_errors = tuple(errors)
    return MigrationPlan(manifest_label, _overall_status(frozen_steps, frozen_errors), legacy,
                         frozen_steps, frozen_errors)
