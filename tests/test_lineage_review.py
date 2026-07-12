from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from science_repo.review import review_run
from science_repo.runner import run_experiment


ASSETS = Path(__file__).parents[1] / "science_repo" / "assets" / "project" / "schemas"


def _run(tmp_path: Path, *, pinned: bool = True) -> Path:
    root = tmp_path / "project"
    exp = root / "experiments" / "demo"
    exp.mkdir(parents=True)
    (exp / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    (exp / "experiment.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "id": "demo", "title": "demo", "stage": "running",
        "question": "q", "hypothesis": "h", "inputs": [],
        "execution": {"command": ["{python}", "worker.py"], "outputs": []},
    }), encoding="utf-8")
    if pinned:
        schemas = root / "schemas"
        schemas.mkdir()
        for name in ("run.schema.json", "lineage.schema.json"):
            shutil.copyfile(ASSETS / name, schemas / name)
        (root / "science-project.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    code, run_dir = run_experiment(root, "demo")
    assert code == 0
    return run_dir


def _report(run_dir: Path) -> tuple[bool, dict]:
    passed, path = review_run(run_dir)
    return passed, json.loads(path.read_text(encoding="utf-8"))


def test_review_accepts_valid_bound_lineage(tmp_path: Path) -> None:
    passed, report = _report(_run(tmp_path))
    assert passed
    assert all(check["passed"] for check in report["checks"] if check["name"].startswith("lineage_"))
    assert "declared command files" in report["scope"]


def test_review_rejects_tampered_lineage(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    lineage_path = run_dir / "lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage["entities"][0]["metadata"]["status"] = "tampered"
    lineage_path.write_text(json.dumps(lineage), encoding="utf-8")
    passed, report = _report(run_dir)
    assert not passed
    assert not next(c for c in report["checks"] if c["name"] == "lineage_canonical_digest")["passed"]


def test_review_rejects_invalid_or_not_validated_declaration(tmp_path: Path) -> None:
    for status in ("invalid", "not_validated_no_pinned_schema"):
        run_dir = _run(tmp_path / status)
        path = run_dir / "run.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["lineage"]["validation"]["status"] = status
        path.write_text(json.dumps(record), encoding="utf-8")
        passed, report = _report(run_dir)
        assert not passed
        assert not next(c for c in report["checks"] if c["name"] == "lineage_declared_validation")["passed"]


def test_review_rejects_missing_pinned_lineage_schema(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    (tmp_path / "project" / "schemas" / "lineage.schema.json").unlink()
    passed, report = _report(run_dir)
    assert not passed
    check = next(c for c in report["checks"] if c["name"] == "lineage_contract_and_dag")
    assert not check["passed"] and "missing pinned lineage contract" in " ".join(check["errors"])


def test_legacy_run_without_lineage_remains_reviewable_without_full_claim(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    path = run_dir / "run.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record.pop("lineage")
    path.write_text(json.dumps(record), encoding="utf-8")
    passed, report = _report(run_dir)
    assert passed
    legacy = next(c for c in report["checks"] if c["name"] == "lineage_not_present_legacy")
    assert legacy["passed"] and "complete provenance is not asserted" in legacy["detail"]
