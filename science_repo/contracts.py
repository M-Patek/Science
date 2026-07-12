from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


SCHEMA_NAMES = ("project", "experiment", "campaign", "handoff", "run")


def schema_errors(
    instance: Any,
    schema_path: Path,
    instance_path: Path,
    *,
    expected_version: int | None = None,
) -> list[str]:
    """Validate an instance against its pinned Draft 2020-12 JSON Schema."""
    from jsonschema import validators

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if expected_version is not None:
            declared = schema.get("properties", {}).get("schema_version", {}).get("const")
            if declared != expected_version:
                return [
                    f"{schema_path}: schema_version const {declared!r} does not match "
                    f"pinned contract version {expected_version!r}"
                ]
        validator_type = validators.validator_for(schema)
        validator_type.check_schema(schema)
        validator = validator_type(schema)
    except Exception as exc:
        return [f"{schema_path}: invalid JSON Schema: {exc}"]

    errors: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        schema_location = ".".join(str(part) for part in error.absolute_schema_path) or "<root>"
        errors.append(
            f"{instance_path}: schema violation at {location} "
            f"(schema {schema_path}#{schema_location}): {error.message}"
        )
    return errors


def pinned_contract_errors(
    instance: Any,
    schema_path: Path,
    instance_path: Path,
    contract_name: str,
    project_manifest: Path | None = None,
) -> list[str]:
    """Validate with a project-local schema without silently changing its version.

    Campaign and handoff versions are bound to ``science-project.yaml``. Run
    records are currently framework contract version 1 and are still required to
    use the project-local schema; they are never validated against packaged
    fallback assets.
    """
    if not schema_path.is_file():
        return [f"{schema_path}: missing pinned {contract_name} contract schema"]
    expected = 1
    if project_manifest is not None and project_manifest.is_file() and contract_name != "run":
        try:
            project = (
                json.loads(project_manifest.read_text(encoding="utf-8"))
                if project_manifest.suffix == ".json"
                else yaml.safe_load(project_manifest.read_text(encoding="utf-8"))
            )
            expected = project["contracts"][contract_name]
        except Exception as exc:
            return [f"{project_manifest}: cannot resolve {contract_name} contract pin: {exc}"]
        if not isinstance(expected, int):
            return [f"{project_manifest}: contracts.{contract_name} must be an integer"]
    return schema_errors(instance, schema_path, instance_path, expected_version=expected)


def schema_parity_errors(root: Path) -> list[str]:
    """Require framework-source schemas to be byte-identical to packaged assets."""
    source_dir = root / "schemas"
    packaged_dir = Path(__file__).resolve().parent / "assets" / "project" / "schemas"
    errors: list[str] = []
    for name in SCHEMA_NAMES:
        filename = f"{name}.schema.json"
        source = source_dir / filename
        packaged = packaged_dir / filename
        if not source.is_file() or not packaged.is_file():
            missing = source if not source.is_file() else packaged
            errors.append(f"{missing}: missing contract schema")
            continue
        source_bytes = source.read_bytes()
        packaged_bytes = packaged.read_bytes()
        if source_bytes != packaged_bytes:
            source_hash = hashlib.sha256(source_bytes).hexdigest()
            packaged_hash = hashlib.sha256(packaged_bytes).hexdigest()
            errors.append(
                f"{source}: packaged schema drift versus {packaged} "
                f"(sha256 {source_hash} != {packaged_hash})"
            )
    return errors


def contract_pin_errors(project: dict[str, Any], schemas_dir: Path, manifest_path: Path) -> list[str]:
    """Bind declared project contract versions to the project's pinned schema files."""
    errors: list[str] = []
    contracts = project.get("contracts")
    if not isinstance(contracts, dict):
        return errors  # project.schema.json reports the structural error
    # Projects created before schemas were embedded remain valid under their existing
    # semantic validators.  Crucially, do not substitute today's packaged schemas for
    # an absent project-local pin: that would silently upgrade an old project.
    if not schemas_dir.is_dir():
        return errors
    for name in ("experiment", "campaign", "handoff"):
        pin = contracts.get(name)
        schema_path = schemas_dir / f"{name}.schema.json"
        if not schema_path.is_file():
            errors.append(f"{schema_path}: missing schema for {name} contract pin")
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema_version = schema["properties"]["schema_version"]["const"]
        except Exception as exc:
            errors.append(f"{schema_path}: cannot read schema_version contract: {exc}")
            continue
        if pin != schema_version:
            errors.append(
                f"{manifest_path}: contracts.{name}={pin!r} does not match "
                f"{schema_path} schema_version const {schema_version!r}"
            )
    return errors
