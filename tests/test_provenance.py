from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
import yaml

from science_repo.review import review_run
from science_repo.runner import run_experiment


@pytest.fixture
def provenance_root():
    path = Path(__file__).parent / "fixtures" / f"provenance-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _experiment(tmp_path: Path, command: list[str], *, outputs: list[str] | None = None,
                inputs: list[str] | None = None, timeout: float | None = None) -> Path:
    schemas = tmp_path / "schemas"
    schemas.mkdir(exist_ok=True)
    shutil.copy2(Path(__file__).parents[1] / "schemas" / "lineage.schema.json", schemas)
    shutil.copy2(Path(__file__).parents[1] / "schemas" / "run.schema.json", schemas)
    (tmp_path / "science-project.yaml").write_text(
        "contracts:\n  experiment: 1\n  campaign: 1\n  handoff: 1\n", encoding="utf-8"
    )
    root = tmp_path / "experiments" / "provenance-test"
    (root / "records").mkdir(parents=True)
    execution = {"command": command, "outputs": outputs or []}
    if timeout is not None:
        execution["timeout_seconds"] = timeout
    manifest = {
        "schema_version": 1, "id": "provenance-test", "title": "test",
        "stage": "running", "question": "q", "hypothesis": "h",
        "inputs": [{"path": item} for item in inputs or []], "execution": execution,
    }
    (root / "experiment.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return root


def _record(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def test_startup_failure_still_writes_complete_failed_record(provenance_root: Path):
    tmp_path = provenance_root
    _experiment(tmp_path, ["executable-that-does-not-exist-science-test"])
    code, run_dir = run_experiment(tmp_path, "provenance-test")
    record = _record(run_dir)
    assert code == 127
    assert record["status"] == "failed"
    assert record["execution_error"]["type"] == "startup_error"
    assert (run_dir / "manifest.yaml").is_file()
    assert (run_dir / "environment.json").is_file()
    assert (run_dir / "stdout.log").is_file()
    assert "failed to start" in (run_dir / "stderr.log").read_text(encoding="utf-8")


def test_timeout_still_writes_failed_record_and_logs(provenance_root: Path):
    tmp_path = provenance_root
    _experiment(tmp_path, ["{python}", "-c", "import time; time.sleep(2)"], timeout=0.01)
    code, run_dir = run_experiment(tmp_path, "provenance-test")
    assert code == 124
    assert _record(run_dir)["execution_error"]["type"] == "timeout"
    assert "timed out" in (run_dir / "stderr.log").read_text(encoding="utf-8")


def test_directory_evidence_is_hashed_and_review_detects_mutation(provenance_root: Path):
    tmp_path = provenance_root
    root = _experiment(tmp_path, ["{python}", "-c", "print('ok')"], inputs=["dataset"])
    (root / "dataset").mkdir()
    (root / "dataset" / "a.txt").write_text("original", encoding="utf-8")
    code, run_dir = run_experiment(tmp_path, "provenance-test")
    assert code == 0
    assert _record(run_dir)["inputs"][0]["kind"] == "directory"
    assert review_run(run_dir)[0]
    (root / "dataset" / "a.txt").write_text("changed", encoding="utf-8")
    assert not review_run(run_dir)[0]


def test_review_checks_frozen_manifest_and_environment(provenance_root: Path):
    tmp_path = provenance_root
    _experiment(tmp_path, ["{python}", "-c", "print('ok')"])
    _, run_dir = run_experiment(tmp_path, "provenance-test")
    assert review_run(run_dir)[0]
    (run_dir / "environment.json").write_text("{}\n", encoding="utf-8")
    passed, report = review_run(run_dir)
    assert not passed
    checks = json.loads(report.read_text(encoding="utf-8"))["checks"]
    assert not next(item for item in checks if item["name"] == "environment_snapshot_integrity")["passed"]


def test_inputs_are_snapshotted_before_command_mutates_them(provenance_root: Path):
    tmp_path = provenance_root
    root = _experiment(
        tmp_path,
        ["{python}", "-c", "from pathlib import Path; Path('input.txt').write_text('after')"],
        inputs=["input.txt"],
    )
    (root / "input.txt").write_text("before", encoding="utf-8")
    _, run_dir = run_experiment(tmp_path, "provenance-test")
    record = _record(run_dir)
    import hashlib
    assert record["inputs"][0]["sha256"] == hashlib.sha256(b"before").hexdigest()
    assert not review_run(run_dir)[0]


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is privilege-dependent on Windows")
def test_symlinked_evidence_is_rejected(provenance_root: Path):
    tmp_path = provenance_root
    root = _experiment(tmp_path, ["{python}", "-c", "print('ok')"], inputs=["linked"])
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (root / "linked").symlink_to(outside)
    code, run_dir = run_experiment(tmp_path, "provenance-test")
    assert code != 0
    assert _record(run_dir)["inputs"][0]["exists"] is False
