from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any

from .io import dump_json, sha256_file
from .io import load_yaml


OPERATORS = {
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    ">=": operator.ge,
    ">": operator.gt,
}


def review_run(run_dir: Path) -> tuple[bool, Path]:
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    experiment_root = run_dir.parent.parent
    checks: list[dict[str, Any]] = []
    checks.append({"name": "process_succeeded", "passed": record["exit_code"] == 0})
    for source in record.get("inputs", []):
        path = experiment_root / source["path"]
        checks.append(
            {
                "name": f"input_integrity:{source['path']}",
                "passed": path.is_file() and sha256_file(path) == source.get("sha256"),
            }
        )
    for artifact in record.get("artifacts", []):
        path = experiment_root / artifact["path"]
        exists = path.is_file()
        digest_matches = exists and sha256_file(path) == artifact.get("sha256")
        checks.append(
            {
                "name": f"artifact_integrity:{artifact['path']}",
                "passed": bool(exists and digest_matches),
            }
        )
    manifest = load_yaml(run_dir / "manifest.yaml")
    results_path = experiment_root / "artifacts" / "results.json"
    if manifest.get("acceptance") and results_path.is_file():
        results = json.loads(results_path.read_text(encoding="utf-8"))
        for criterion in manifest["acceptance"]:
            metric = criterion.get("metric")
            op_name = criterion.get("operator")
            threshold = criterion.get("threshold")
            actual = results.get(metric)
            comparison = OPERATORS.get(op_name)
            criterion_passed = (
                comparison is not None
                and isinstance(actual, (int, float))
                and isinstance(threshold, (int, float))
                and comparison(actual, threshold)
            )
            checks.append(
                {
                    "name": f"acceptance:{metric}",
                    "passed": bool(criterion_passed),
                    "actual": actual,
                    "operator": op_name,
                    "threshold": threshold,
                }
            )
    passed = all(check["passed"] for check in checks)
    report = {
        "schema_version": 1,
        "run_id": record["run_id"],
        "verdict": "pass" if passed else "fail",
        "checks": checks,
        "scope": "mechanical provenance and artifact integrity; scientific validity requires human review",
    }
    path = run_dir / "review.json"
    dump_json(path, report)
    return passed, path
