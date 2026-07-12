from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any

from .io import dump_json, load_yaml, sha256_text
from .runner import _evidence_item
from .contracts import pinned_contract_errors


OPERATORS = {"<": operator.lt, "<=": operator.le, "==": operator.eq, ">=": operator.ge, ">": operator.gt}


def _read_json(path: Path, checks: list[dict[str, Any]], name: str) -> Any | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        checks.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"})
        return None
    checks.append({"name": name, "passed": True})
    return value


def review_run(run_dir: Path) -> tuple[bool, Path]:
    checks: list[dict[str, Any]] = []
    record = _read_json(run_dir / "run.json", checks, "run_record_readable")
    if not isinstance(record, dict):
        if record is not None:
            checks[-1] = {"name": "run_record_readable", "passed": False, "detail": "run.json must contain an object"}
        marker = run_dir / "run.in-progress.json"
        checks.append({
            "name": "run_completed", "passed": False,
            "detail": "in-progress marker exists; run did not finalize" if marker.exists() else "final run record is unavailable",
        })
        return _write_report(run_dir, run_dir.name, checks)

    run_id = record.get("run_id") if isinstance(record.get("run_id"), str) else run_dir.name
    experiment_root = run_dir.parent.parent
    project_root = experiment_root.parent.parent
    for candidate in (project_root, *project_root.parents):
        if (candidate / "science-project.yaml").is_file() or (candidate / "science-framework.yaml").is_file():
            project_root = candidate
            break
    contract_errors = pinned_contract_errors(
        record,
        project_root / "schemas" / "run.schema.json",
        run_dir / "run.json",
        "run",
        project_root / "science-project.yaml",
    )
    checks.append({"name": "run_contract", "passed": not contract_errors, "errors": contract_errors})
    checks.append({"name": "run_completed", "passed": not (run_dir / "run.in-progress.json").exists()})
    checks.append({
        "name": "process_succeeded", "passed": record.get("exit_code") == 0 and record.get("status") == "succeeded",
    })

    manifest_text: str | None = None
    try:
        manifest_text = (run_dir / "manifest.yaml").read_text(encoding="utf-8")
        checks.append({"name": "manifest_snapshot_integrity", "passed": sha256_text(manifest_text) == record.get("manifest_sha256")})
    except (OSError, UnicodeError) as error:
        checks.append({"name": "manifest_snapshot_integrity", "passed": False, "detail": f"{type(error).__name__}: {error}"})

    environment = _read_json(run_dir / "environment.json", checks, "environment_snapshot_readable")
    checks.append({
        "name": "environment_snapshot_integrity",
        "passed": environment is not None and sha256_text(json.dumps(environment, sort_keys=True)) == record.get("environment_sha256"),
    })

    for category in ("inputs", "artifacts"):
        items = record.get(category, [])
        if not isinstance(items, list):
            checks.append({"name": f"{category}_record_shape", "passed": False, "detail": f"{category} must be a list"})
            continue
        for index, source in enumerate(items):
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                checks.append({"name": f"{category}_record_shape:{index}", "passed": False, "detail": "evidence item requires string path"})
                continue
            current = _evidence_item(experiment_root, source["path"])
            checks.append({
                "name": f"{'input' if category == 'inputs' else 'artifact'}_integrity:{source['path']}",
                "passed": bool(current["exists"] and current["sha256"] == source.get("sha256") and current.get("kind") == source.get("kind", "file")),
            })

    manifest: dict[str, Any] | None = None
    if manifest_text is not None:
        try:
            manifest = load_yaml(run_dir / "manifest.yaml")
        except (OSError, UnicodeError, ValueError) as error:
            checks.append({"name": "manifest_snapshot_parseable", "passed": False, "detail": f"{type(error).__name__}: {error}"})
    results_path = experiment_root / "artifacts" / "results.json"
    if manifest and manifest.get("acceptance") and results_path.is_file():
        results = _read_json(results_path, checks, "acceptance_results_readable")
        if isinstance(results, dict):
            for criterion in manifest["acceptance"]:
                metric, op_name, threshold = criterion.get("metric"), criterion.get("operator"), criterion.get("threshold")
                actual, comparison = results.get(metric), OPERATORS.get(op_name)
                checks.append({
                    "name": f"acceptance:{metric}",
                    "passed": bool(comparison and isinstance(actual, (int, float)) and not isinstance(actual, bool)
                                   and isinstance(threshold, (int, float)) and not isinstance(threshold, bool)
                                   and comparison(actual, threshold)),
                    "actual": actual, "operator": op_name, "threshold": threshold,
                })
    return _write_report(run_dir, run_id, checks)


def _write_report(run_dir: Path, run_id: str, checks: list[dict[str, Any]]) -> tuple[bool, Path]:
    passed = bool(checks) and all(check["passed"] for check in checks)
    path = run_dir / "review.json"
    dump_json(path, {
        "schema_version": 1, "run_id": run_id, "verdict": "pass" if passed else "fail", "checks": checks,
        "scope": "mechanical provenance and artifact integrity; scientific validity requires human review",
    })
    return passed, path
