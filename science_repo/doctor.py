"""Read-only, deterministic diagnostics for framework and generated projects."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


SCHEMAS = (
    "project", "experiment", "campaign", "handoff", "run", "lineage", "execution-envelope",
    "cohort-freeze", "trusted-attestation-receipt",
    "subject-packet-set",
    "attempt-manifest", "blinded-scoring-verification",
)


def _finding(severity: str, code: str, message: str, remediation: str | None = None) -> dict[str, str]:
    item = {"severity": severity, "code": code, "message": message}
    if remediation:
        item["remediation"] = remediation
    return item


def _git(root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    observed: dict[str, Any] = {"available": False, "revision": None, "dirty": None}
    findings: list[dict[str, str]] = []
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=root, text=True,
            capture_output=True, timeout=3, check=False,
        )
        if revision.returncode:
            findings.append(_finding("info", "git.repository-unavailable", "Git revision is not observable."))
            return observed, findings
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root,
            text=True, capture_output=True, timeout=3, check=False,
        )
        observed.update(available=True, revision=revision.stdout.strip(), dirty=None if status.returncode else bool(status.stdout))
        if status.returncode:
            findings.append(_finding("warning", "git.status-unavailable", "Git dirty state is not observable."))
        elif status.stdout:
            findings.append(_finding("info", "git.dirty", "The working tree has tracked or untracked changes.", "Record or commit the intended state before producing evidence."))
    except (OSError, subprocess.TimeoutExpired):
        findings.append(_finding("info", "git.command-unavailable", "Git executable or repository state is not observable."))
    return observed, findings


def diagnose(root: Path) -> dict[str, Any]:
    """Inspect *root* without modifying it, importing project code, or using a network."""
    root = root.resolve()
    findings: list[dict[str, str]] = []
    framework = (root / "science-framework.yaml").is_file()
    project = (root / "science-project.yaml").is_file()
    kind = "framework" if framework else "research-project" if project else "unknown"
    manifest_path = root / ("science-framework.yaml" if framework else "science-project.yaml")
    if kind == "unknown":
        findings.append(_finding("error", "project.manifest-missing", "No Science framework or project manifest was found.", "Run this command from a Science repository root."))

    required = ["AGENTS.md", "docs/INDEX.md", "docs/_machine/experiments.json", "experiments"]
    for relative in required:
        if not (root / relative).exists():
            findings.append(_finding("error", "project.required-path-missing", f"Required path is missing: {relative}", f"Restore {relative} from the appropriate project template or version control."))

    pins: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            pins = dict(sorted((manifest.get("contracts") or {}).items()))
        except Exception as exc:
            findings.append(_finding("error", "project.manifest-invalid", f"Manifest cannot be read: {type(exc).__name__}.", "Validate and repair the manifest without changing contract pins silently."))

    schemas = root / "schemas"
    if project and schemas.is_dir():
        for name in SCHEMAS:
            path = schemas / f"{name}.schema.json"
            if not path.is_file():
                findings.append(_finding("error", "contracts.schema-missing", f"Pinned schema is missing: schemas/{name}.schema.json", "Restore the exact schema version pinned by science-project.yaml."))
            else:
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    findings.append(_finding("error", "contracts.schema-invalid", f"Pinned schema is not valid JSON: schemas/{name}.schema.json", "Restore the exact pinned schema; do not substitute a newer contract."))
    elif project:
        findings.append(_finding("info", "contracts.legacy-no-local-schemas", "No project-local schemas directory exists; this may be a legacy project.", "Do not silently add current schemas; use an explicit migration workflow."))

    skills_dir = root / ".agents" / "skills"
    skills = sorted(p.parent.name for p in skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []
    if not skills:
        findings.append(_finding("warning", "agent.skills-missing", "No Agent skill manifests were discovered.", "Install or restore repository-scoped skills appropriate to this project."))

    campaigns = root / "campaigns"
    runtime_dirs = sorted(str(p.relative_to(root)).replace("\\", "/") for p in campaigns.glob("*/.runtime") if p.is_dir()) if campaigns.is_dir() else []
    if not campaigns.is_dir():
        findings.append(_finding("warning", "campaign.directory-missing", "The campaigns directory is missing.", "Create campaigns/ before using orchestration features."))

    dependencies = {name: importlib.util.find_spec(name) is not None for name in ("jsonschema", "yaml")}
    for name, available in dependencies.items():
        if not available:
            findings.append(_finding("error", "python.dependency-missing", f"Required Python dependency is unavailable: {name}", "Install the package from the framework's declared dependency set."))
    if sys.version_info < (3, 11):
        findings.append(_finding("error", "python.version-unsupported", f"Python {sys.version_info.major}.{sys.version_info.minor} is below 3.11.", "Use Python 3.11 or newer."))

    routes = []
    for relative in ("AGENTS.md", "docs/INDEX.md"):
        path = root / relative
        if path.is_file():
            size = path.stat().st_size
            routes.append({"path": relative, "bytes": size, "advice": "read first"})
    findings.append(_finding("info", "context.progressive-disclosure", "Start with routing files, then read only affected subsystem and experiment files; byte sizes are reported, not estimated tokens."))

    git, git_findings = _git(root)
    findings.extend(git_findings)
    findings.sort(key=lambda item: (item["severity"], item["code"], item["message"]))
    return {
        "schema_version": 1,
        "root": str(root),
        "kind": kind,
        "contract_pins": pins,
        "git": git,
        "campaign_runtime_dirs": runtime_dirs,
        "agent_skills": skills,
        "python": {"version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "dependencies": dependencies},
        "context_routes": routes,
        "findings": findings,
        "summary": {severity: sum(f["severity"] == severity for f in findings) for severity in ("error", "warning", "info")},
    }
