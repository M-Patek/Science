from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any

from .io import dump_json, load_yaml, sha256_text
from .runner import _evidence_item
from .contracts import pinned_contract_errors
from .lineage import lineage_digest, load_lineage, validate_lineage
from .review_plugins import ReviewPluginRegistry


OPERATORS = {"<": operator.lt, "<=": operator.le, "==": operator.eq, ">=": operator.ge, ">": operator.gt}


def _review_lineage(
    record: dict[str, Any], run_dir: Path, project_root: Path, checks: list[dict[str, Any]]
) -> None:
    """Verify the runner's deliberately bounded, command-file lineage claim."""
    reference = record.get("lineage")
    if reference is None:
        checks.append({
            "name": "lineage_not_present_legacy", "passed": True,
            "detail": "legacy run has no lineage reference; complete provenance is not asserted",
        })
        return
    if not isinstance(reference, dict):
        checks.append({"name": "lineage_reference", "passed": False, "detail": "lineage must be an object"})
        return

    expected_path = run_dir / "lineage.json"
    try:
        declared = reference.get("path")
        if not isinstance(declared, str) or not declared or "\\" in declared:
            raise ValueError("lineage.path must be a non-empty project-relative POSIX path")
        lineage_path = (project_root / Path(*declared.split("/"))).resolve(strict=False)
        if lineage_path != expected_path.resolve(strict=False):
            raise ValueError("lineage.path must identify this run's lineage.json")
        lineage = load_lineage(lineage_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        checks.append({"name": "lineage_readable", "passed": False, "detail": f"{type(error).__name__}: {error}"})
        return
    checks.append({"name": "lineage_readable", "passed": True})

    try:
        digest_ok = lineage_digest(lineage) == reference.get("sha256")
        digest_detail = None
    except (TypeError, ValueError) as error:
        digest_ok = False
        digest_detail = f"canonicalization failed: {type(error).__name__}"
    checks.append({
        "name": "lineage_canonical_digest", "passed": digest_ok, "detail": digest_detail
    })
    validation = reference.get("validation")
    declared_valid = (
        isinstance(validation, dict)
        and validation.get("status") == "valid"
        and validation.get("schema") == "schemas/lineage.schema.json"
    )
    checks.append({
        "name": "lineage_declared_validation", "passed": declared_valid,
        "detail": None if declared_valid else "lineage must declare valid validation against the pinned schema",
    })
    errors = validate_lineage(
        lineage, lineage_path, project_root,
        schema_path=project_root / "schemas" / "lineage.schema.json",
    )
    checks.append({"name": "lineage_contract_and_dag", "passed": not errors, "errors": errors})

    observation = dict(record)
    observation.pop("lineage", None)
    observation_digest = sha256_text(json.dumps(
        observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ))
    run_entities = [
        entity for entity in lineage.get("entities", [])
        if isinstance(entity, dict) and entity.get("kind") == "run"
        and isinstance(entity.get("metadata"), dict)
        and entity["metadata"].get("digest_basis") == "canonical_run_observation_v1"
    ]
    bound = (
        len(run_entities) == 1
        and run_entities[0].get("digest") == f"sha256:{observation_digest}"
        and run_entities[0]["metadata"].get("run_id") == record.get("run_id")
        and run_entities[0]["metadata"].get("status") == record.get("status")
    )
    checks.append({"name": "lineage_run_observation_binding", "passed": bound})


def _read_json(path: Path, checks: list[dict[str, Any]], name: str) -> Any | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        checks.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"})
        return None
    checks.append({"name": name, "passed": True})
    return value


def review_run(
    run_dir: Path, *, plugin_registry: ReviewPluginRegistry | None = None
) -> tuple[bool, Path]:
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
        return _write_report(
            run_dir, run_dir.name, checks, plugin_checks=[],
            plugin_execution="skipped_invalid_evidence" if plugin_registry is not None else "not_requested",
        )

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
    _review_lineage(record, run_dir, project_root, checks)

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
            scope = source.get("scope", "experiment") if category == "inputs" else "experiment"
            if scope not in {"experiment", "project"}:
                checks.append({
                    "name": f"{category}_scope:{index}",
                    "passed": False,
                    "detail": "evidence scope must be experiment or project",
                })
                continue
            root = project_root if scope == "project" else experiment_root
            current = _evidence_item(root, source["path"])
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
    plugin_checks: list[dict[str, Any]] = []
    plugin_execution = "not_requested"
    if plugin_registry is not None:
        # Deliberately exclude snapshot contents, command lines, environment values, and
        # log text.  Plugins receive only the minimum facts needed to inspect the
        # mechanical review, and ReviewPluginRegistry recursively freezes this bundle.
        evidence_items: list[dict[str, Any]] = []
        for category in ("inputs", "artifacts"):
            items = record.get(category, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                relevant_check = next(
                    (
                        check for check in checks
                        if check["name"] == f"{'input' if category == 'inputs' else 'artifact'}_integrity:{item['path']}"
                    ),
                    None,
                )
                evidence_items.append({
                    "category": category,
                    "path": item["path"],
                    "kind": item.get("kind", "file"),
                    "integrity_passed": bool(relevant_check and relevant_check["passed"]),
                })
        plugin_checks = plugin_registry.run({
            "schema_version": 1,
            "run": {"run_id": run_id, "status": record.get("status"), "exit_code": record.get("exit_code")},
            "mechanical_checks": tuple(
                {"name": check["name"], "passed": bool(check["passed"])} for check in checks
            ),
            "evidence": tuple(evidence_items),
        })
        plugin_execution = "completed"
    return _write_report(
        run_dir, run_id, checks, plugin_checks=plugin_checks, plugin_execution=plugin_execution
    )


def _write_report(
    run_dir: Path,
    run_id: str,
    checks: list[dict[str, Any]],
    *,
    plugin_checks: list[dict[str, Any]],
    plugin_execution: str,
) -> tuple[bool, Path]:
    passed = (
        bool(checks)
        and all(check["passed"] for check in checks)
        and all(check.get("status") == "pass" for check in plugin_checks)
    )
    path = run_dir / "review.json"
    dump_json(path, {
        "schema_version": 1, "run_id": run_id, "verdict": "pass" if passed else "fail", "checks": checks,
        "plugin_checks": plugin_checks,
        "plugin_policy": {
            "execution": plugin_execution,
            "decision": "every registered plugin check must pass; fail, unknown, and plugin errors fail closed",
            "dynamic_loading": False,
            "human_approval": "not assessed; remains a separate required domain-review gate",
        },
        "scope": (
            "mechanical integrity of declared evidence and, when present, runner-captured lineage "
            "limited to declared inputs/outputs, manifest, and declared command files; legacy absence "
            "does not establish complete provenance; scientific validity requires human review"
        ),
    })
    return passed, path
