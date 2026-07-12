import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
import yaml

from science_repo.benchmark import build_onboarding_fixture, canonical_tree_sha256
from science_repo.review import review_run
from science_repo.runner import run_experiment
from science_repo.validate import validate_repository


@pytest.fixture
def fixture_root():
    path = Path(__file__).parent / "fixtures" / f"benchmark-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_fixture_is_deterministic_and_contains_registered_tasks(fixture_root: Path):
    first, second = fixture_root / "first", fixture_root / "nested" / "second"
    first_hash = build_onboarding_fixture(first)
    second_hash = build_onboarding_fixture(second)
    assert first_hash == second_hash == canonical_tree_sha256(first)
    assert (first / "science-project.yaml").is_file()
    assert {path.name for path in (first / "schemas").glob("*.schema.json")} == {
        "campaign.schema.json",
        "experiment.schema.json",
        "handoff.schema.json",
        "project.schema.json",
        "run.schema.json",
    }
    assert {path.name for path in (first / "experiments").iterdir() if path.is_dir()} == {
        "prepared-invalid", "deterministic-smoke"
    }


def test_subject_fixture_excludes_registration_and_scoring_material(fixture_root: Path):
    project = fixture_root / "project"
    build_onboarding_fixture(project)
    relative_files = {
        path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file()
    }
    forbidden_names = {
        "cohort-v1.yaml",
        "rubric.md",
        "preregistration-review.md",
        "observations-v1.csv",
        "observations-v2.csv",
    }
    assert not {Path(path).name for path in relative_files} & forbidden_names
    assert not any("transcript" in path.lower() or "score" in path.lower() for path in relative_files)


def test_registered_prompts_have_matching_fixture_affordances(fixture_root: Path):
    project = fixture_root / "project"
    build_onboarding_fixture(project)
    cohort_path = (
        Path(__file__).parents[1]
        / "dogfood/framework-self-study/experiments/framework-onboarding/cohort-v1.yaml"
    )
    cohort = yaml.safe_load(cohort_path.read_text(encoding="utf-8"))
    prompts = {task["id"]: task["prompt"] for task in cohort["tasks"]}

    assert set(prompts) == {
        "T1-locate-contracts", "T2-create-experiment", "T3-validate-experiment",
        "T4-run-review", "T5-human-gate",
    }
    assert (project / "science-project.yaml").is_file()
    assert (project / "templates" / "experiment" / "experiment.yaml").is_file()
    assert (project / "experiments" / "prepared-invalid" / "experiment.yaml").is_file()
    smoke = project / "experiments" / "deterministic-smoke"
    assert (smoke / "experiment.yaml").is_file()
    assert not (smoke / "records").exists()
    assert not (smoke / "artifacts" / "results.json").exists()
    assert "paid external service" in prompts["T5-human-gate"]


def test_prepared_defect_is_unique_and_smallest_correction_validates(fixture_root: Path):
    project = fixture_root / "project"
    build_onboarding_fixture(project)
    errors = validate_repository(project)
    assert len(errors) == 1
    assert "schema violation at stage" in errors[0]
    assert "'ready' is not one of" in errors[0]
    manifest_path = project / "experiments" / "prepared-invalid" / "experiment.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["stage"] = "designed"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    assert validate_repository(project) == []


def test_deterministic_smoke_runs_and_reviews(fixture_root: Path):
    project = fixture_root / "project"
    build_onboarding_fixture(project)
    code, record = run_experiment(project, "deterministic-smoke")
    assert code == 0
    assert json.loads((project / "experiments" / "deterministic-smoke" / "artifacts" / "results.json").read_text())["total"] == 6
    passed, _ = review_run(record)
    assert passed
