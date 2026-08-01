from __future__ import annotations

import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from science_repo.io import dump_json
from science_repo.review import review_run


def _checks(report: Path) -> list[dict]:
    return json.loads(report.read_text(encoding="utf-8"))["checks"]


@pytest.fixture
def local_tmp():
    path = Path(__file__).parent / "fixtures" / f"resilience-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_review_missing_record_reports_failure(local_tmp: Path):
    tmp_path = local_tmp
    run_dir = tmp_path / "experiments" / "x" / "records" / "unfinished"
    run_dir.mkdir(parents=True)
    dump_json(run_dir / "run.in-progress.json", {"status": "in_progress"})
    passed, report = review_run(run_dir)
    assert not passed
    checks = _checks(report)
    assert next(item for item in checks if item["name"] == "run_record_readable")["passed"] is False
    assert "did not finalize" in next(item for item in checks if item["name"] == "run_completed")["detail"]


def test_review_malformed_record_reports_failure(local_tmp: Path):
    tmp_path = local_tmp
    run_dir = tmp_path / "experiments" / "x" / "records" / "broken"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{not json", encoding="utf-8")
    passed, report = review_run(run_dir)
    assert not passed
    assert "JSONDecodeError" in _checks(report)[0]["detail"]


def test_review_malformed_snapshots_and_evidence_shape_do_not_crash(local_tmp: Path):
    tmp_path = local_tmp
    run_dir = tmp_path / "experiments" / "x" / "records" / "broken-snapshots"
    run_dir.mkdir(parents=True)
    dump_json(run_dir / "run.json", {
        "run_id": "broken-snapshots", "status": "succeeded", "exit_code": 0,
        "manifest_sha256": "x", "environment_sha256": "x",
        "inputs": [{"path": 42}], "artifacts": "wrong",
    })
    (run_dir / "manifest.yaml").write_text("[not: valid", encoding="utf-8")
    (run_dir / "environment.json").write_text("nope", encoding="utf-8")
    passed, report = review_run(run_dir)
    assert not passed
    names = {item["name"] for item in _checks(report)}
    assert "environment_snapshot_readable" in names
    assert "inputs_record_shape:0" in names
    assert "artifacts_record_shape" in names
    assert "manifest_snapshot_parseable" in names


def test_dump_json_replaces_destination_without_temp_residue(local_tmp: Path):
    tmp_path = local_tmp
    target = tmp_path / "record.json"
    dump_json(target, {"generation": 1})
    dump_json(target, {"generation": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"generation": 2}
    assert list(tmp_path.glob(".record.json.*.tmp")) == []
