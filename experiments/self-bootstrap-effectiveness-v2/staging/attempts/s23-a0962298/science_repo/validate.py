from __future__ import annotations

import json
from pathlib import Path

from .io import load_yaml
from .models import Experiment, validate_manifest
from .contracts import contract_pin_errors, schema_errors, schema_parity_errors
from .lifecycle import LifecycleError, read_stage_history


REQUIRED_FILES = ("experiment.yaml", "hypothesis.md", "protocol.md", "README.md")


def validate_experiment(path: Path, schema_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_FILES:
        if not (path / name).is_file():
            errors.append(f"{path.name}: missing {name}")
    if errors or not (path / "experiment.yaml").exists():
        return errors
    try:
        exp = Experiment.load(path)
        if schema_path is not None and schema_path.is_file():
            structural = schema_errors(exp.manifest, schema_path, path / "experiment.yaml")
            errors.extend(structural)
            # Avoid duplicate or misleading semantic diagnostics for a manifest
            # that does not yet satisfy its pinned structural contract.
            if structural:
                return errors
        errors.extend(f"{path.name}: {e}" for e in validate_manifest(exp.manifest, path.name))
        for output in exp.outputs:
            output_path = (path / output).resolve()
            if path.resolve() not in output_path.parents:
                errors.append(f"{path.name}: output escapes experiment directory: {output}")
        try:
            history = read_stage_history(path)
            stage = exp.manifest.get("stage")
            if history and history[-1]["to_stage"] != stage:
                errors.append(f"{path.name}: stage history does not match manifest stage {stage!r}")
        except LifecycleError as error:
            errors.append(f"{path.name}: invalid stage history: {error}")
    except Exception as exc:
        errors.append(f"{path.name}: invalid manifest: {exc}")
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    if not ((root / "science-project.yaml").is_file() or (root / "science-framework.yaml").is_file()):
        errors.append("missing science-project.yaml or science-framework.yaml")
    project_manifest = root / "science-project.yaml"
    schemas_dir = root / "schemas"
    if (root / "science-framework.yaml").is_file():
        errors.extend(schema_parity_errors(root))
    if project_manifest.is_file():
        try:
            project = load_yaml(project_manifest)
            project_schema = schemas_dir / "project.schema.json"
            if project_schema.is_file():
                errors.extend(schema_errors(project, project_schema, project_manifest))
            errors.extend(contract_pin_errors(project, schemas_dir, project_manifest))
            if project.get("kind") != "research-project":
                errors.append("science-project.yaml: kind must be research-project")
            if project.get("schema_version") != 1:
                errors.append("science-project.yaml: unsupported schema_version")
        except Exception as exc:
            errors.append(f"invalid science-project.yaml: {exc}")
    experiments_dir = root / "experiments"
    for path in sorted(experiments_dir.iterdir() if experiments_dir.exists() else []):
        if path.is_dir() and not path.name.startswith("."):
            errors.extend(validate_experiment(path, schemas_dir / "experiment.schema.json"))
    registry_path = root / "docs" / "_machine" / "experiments.json"
    if not registry_path.is_file():
        errors.append("missing docs/_machine/experiments.json")
        return errors
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registered = {entry["id"] for entry in registry.get("experiments", [])}
        actual = {
            p.name for p in experiments_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
        }
        if registered != actual:
            errors.append(
                f"registry drift: registered={sorted(registered)}, actual={sorted(actual)}"
            )
    except Exception as exc:
        errors.append(f"invalid experiment registry: {exc}")
    return errors
