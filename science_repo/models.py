from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io import load_yaml

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
STAGES = {"idea", "designed", "running", "analyzed", "reviewed", "published", "abandoned"}


@dataclass(frozen=True)
class Experiment:
    root: Path
    manifest: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.manifest["id"])

    @property
    def command(self) -> list[str]:
        return list(self.manifest["execution"]["command"])

    @property
    def outputs(self) -> list[str]:
        return list(self.manifest["execution"].get("outputs", []))

    @property
    def inputs(self) -> list[str]:
        return [str(item["path"]) for item in self.manifest.get("inputs", []) if "path" in item]

    @classmethod
    def load(cls, root: Path) -> "Experiment":
        return cls(root=root, manifest=load_yaml(root / "experiment.yaml"))


def validate_manifest(data: dict[str, Any], expected_id: str | None = None) -> list[str]:
    errors: list[str] = []
    required = ("schema_version", "id", "title", "stage", "question", "hypothesis", "execution")
    for key in required:
        if key not in data:
            errors.append(f"missing required field: {key}")
    exp_id = data.get("id")
    if exp_id is not None and not ID_RE.fullmatch(str(exp_id)):
        errors.append("id must match ^[a-z0-9][a-z0-9-]{2,63}$")
    if expected_id and exp_id != expected_id:
        errors.append(f"manifest id {exp_id!r} does not match directory {expected_id!r}")
    if data.get("stage") not in STAGES:
        errors.append(f"stage must be one of: {', '.join(sorted(STAGES))}")
    execution = data.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution must be a mapping")
    else:
        command = execution.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            errors.append("execution.command must be a non-empty string array")
        outputs = execution.get("outputs", [])
        if not isinstance(outputs, list) or not all(isinstance(x, str) for x in outputs):
            errors.append("execution.outputs must be a string array")
    for field in ("question", "hypothesis"):
        if field in data and not str(data[field]).strip():
            errors.append(f"{field} must not be empty")
    return errors
