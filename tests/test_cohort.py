from copy import deepcopy
from pathlib import Path

from science_repo.cohort import (
    generate_preassignment,
    load_cohort,
    validate_cohort,
    validate_preassignment,
)


ROOT = Path(__file__).parents[1]
PROJECT = ROOT / "dogfood" / "framework-self-study"
COHORT = PROJECT / "experiments" / "framework-onboarding" / "cohort-v1.yaml"
CAMPAIGN = PROJECT / "campaigns" / "framework-self-evaluation" / "campaign.yaml"


def test_frozen_cohort_is_ready():
    assert validate_cohort(COHORT, campaign_path=CAMPAIGN, project_path=PROJECT / "science-project.yaml") == []


def test_preassignment_is_deterministic_and_independent():
    cohort = load_cohort(COHORT)
    ids = [f"subject-{number}" for number in range(1, 6)]
    first = generate_preassignment(cohort, ids)
    assert first == generate_preassignment(cohort, ids)
    assert validate_preassignment(cohort, first) == []
    assert {row["task_id"] for row in first["assignments"]} == {task["id"] for task in cohort["tasks"]}


def test_preassignment_rejects_shared_copy_and_tampering():
    cohort = load_cohort(COHORT)
    ledger = generate_preassignment(cohort, [f"s{i}" for i in range(5)])
    broken = deepcopy(ledger)
    broken["assignments"][1]["copy_id"] = broken["assignments"][0]["copy_id"]
    errors = validate_preassignment(cohort, broken)
    assert any("copy_id" in error for error in errors)
    assert any("assignment_sha256" in error for error in errors)


def test_preassignment_requires_registered_minimum():
    cohort = load_cohort(COHORT)
    try:
        generate_preassignment(cohort, ["s1"])
    except ValueError as error:
        assert "at least 5" in str(error)
    else:
        raise AssertionError("expected undersized cohort to fail")
