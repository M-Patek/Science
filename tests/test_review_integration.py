from __future__ import annotations

import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
import yaml

from science_repo.review import review_run
from science_repo.review_plugins import PluginCheck, ReviewPluginRegistry
from science_repo.runner import run_experiment


@pytest.fixture
def work_root():
    path = Path(__file__).parent / "fixtures" / f"review-integration-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _successful_run(tmp_path: Path) -> Path:
    schemas = tmp_path / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).parents[1] / "schemas" / "lineage.schema.json", schemas)
    shutil.copy2(Path(__file__).parents[1] / "schemas" / "run.schema.json", schemas)
    (tmp_path / "science-project.yaml").write_text(
        "contracts:\n  experiment: 1\n  campaign: 1\n  handoff: 1\n", encoding="utf-8"
    )
    experiment = tmp_path / "experiments" / "review-integration"
    (experiment / "records").mkdir(parents=True)
    (experiment / "experiment.yaml").write_text(
        yaml.safe_dump({
            "schema_version": 1,
            "id": "review-integration",
            "title": "review integration",
            "stage": "running",
            "question": "q",
            "hypothesis": "h",
            "inputs": [],
            "execution": {"command": ["{python}", "-c", "print('ok')"], "outputs": []},
        }),
        encoding="utf-8",
    )
    code, run_dir = run_experiment(tmp_path, "review-integration")
    assert code == 0
    return run_dir


def _registry(status: str) -> ReviewPluginRegistry:
    registry = ReviewPluginRegistry()
    registry.register("critic", lambda evidence: PluginCheck("decision", status))
    return registry


def test_default_review_remains_compatible(work_root: Path) -> None:
    passed, report_path = review_run(_successful_run(work_root))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert passed
    assert report["verdict"] == "pass"
    assert report["plugin_checks"] == []
    assert report["plugin_policy"]["execution"] == "not_requested"


def test_plugin_pass_is_structured_and_does_not_claim_human_approval(work_root: Path) -> None:
    passed, report_path = review_run(_successful_run(work_root), plugin_registry=_registry("pass"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert passed
    assert report["plugin_checks"][0]["id"] == "critic:decision"
    assert report["plugin_checks"][0]["status"] == "pass"
    assert "not assessed" in report["plugin_policy"]["human_approval"]


def test_plugin_fail_unknown_and_exception_all_fail_closed(work_root: Path) -> None:
    for status in ("fail", "unknown"):
        passed, report_path = review_run(_successful_run(work_root / status), plugin_registry=_registry(status))
        assert not passed
        assert json.loads(report_path.read_text(encoding="utf-8"))["verdict"] == "fail"

    registry = ReviewPluginRegistry()
    registry.register("broken", lambda evidence: (_ for _ in ()).throw(RuntimeError("TOP-SECRET")))
    passed, report_path = review_run(_successful_run(work_root / "exception"), plugin_registry=registry)
    report_text = report_path.read_text(encoding="utf-8")
    assert not passed
    assert "TOP-SECRET" not in report_text
    assert json.loads(report_text)["plugin_checks"][0]["error_code"] == "review_plugin_failed"


def test_plugin_gets_minimal_immutable_bundle_without_environment_secrets(work_root: Path) -> None:
    run_dir = _successful_run(work_root)
    environment_path = run_dir / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment["secret_for_test"] = "DO-NOT-LEAK"
    # The integrity check will fail, but neither the snapshot nor its values are plugin input.
    environment_path.write_text(json.dumps(environment), encoding="utf-8")
    observed = {}

    def critic(evidence):
        observed.update({"keys": tuple(evidence), "bundle": evidence})
        try:
            evidence["run"]["status"] = "changed"
        except TypeError:
            pass
        else:
            raise AssertionError("bundle was mutable")
        return PluginCheck("minimal", "pass")

    registry = ReviewPluginRegistry()
    registry.register("privacy", critic)
    passed, report_path = review_run(run_dir, plugin_registry=registry)
    assert not passed  # corrupted environment still fails closed
    assert observed["keys"] == ("schema_version", "run", "mechanical_checks", "evidence")
    assert "DO-NOT-LEAK" not in repr(observed["bundle"])
    assert "DO-NOT-LEAK" not in report_path.read_text(encoding="utf-8")


def test_corrupt_run_record_skips_plugins_and_fails_closed(work_root: Path) -> None:
    run_dir = _successful_run(work_root)
    (run_dir / "run.json").write_text("not-json", encoding="utf-8")
    called = False

    def critic(evidence):
        nonlocal called
        called = True
        return PluginCheck("x", "pass")

    registry = ReviewPluginRegistry()
    registry.register("critic", critic)
    passed, report_path = review_run(run_dir, plugin_registry=registry)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert not passed
    assert not called
    assert report["plugin_policy"]["execution"] == "skipped_invalid_evidence"
