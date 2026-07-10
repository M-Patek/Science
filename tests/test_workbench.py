from __future__ import annotations

import json
from pathlib import Path

from science_repo.review import review_run
from science_repo.runner import run_experiment
from science_repo.validate import validate_repository
from science_repo.cli import ASSETS, cmd_campaign_validate
from argparse import Namespace


ROOT = Path(__file__).resolve().parent.parent


def test_repository_is_valid():
    assert validate_repository(ROOT) == []


def test_distributable_assets_and_dogfood_project_are_valid():
    assert (ASSETS / "project" / "science-project.yaml").is_file()
    assert (ASSETS / "experiment" / "experiment.yaml").is_file()
    project = ROOT / "dogfood" / "framework-self-study"
    assert validate_repository(project) == []
    assert cmd_campaign_validate(
        Namespace(project=str(project), id="framework-self-evaluation")
    ) == 0


def test_demo_run_and_review():
    code, run_dir = run_experiment(ROOT, "linear-demo")
    assert code == 0
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert record["status"] == "succeeded"
    passed, report = review_run(run_dir)
    assert passed
    assert report.is_file()
    review = json.loads(report.read_text(encoding="utf-8"))
    assert any(check["name"] == "acceptance:slope_absolute_error" for check in review["checks"])
