import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
import yaml

from science_repo.campaign import validate_campaign
from science_repo.handoff import validate_handoff
from science_repo.review import review_run


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def contract_root():
    path = Path(__file__).parent / "fixtures" / f"contracts-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _campaign() -> dict:
    return {
        "schema_version": 1,
        "id": "contract-test",
        "title": "Contract test",
        "objective": "Test pinned schemas",
        "status": "draft",
        "owner": "test",
        "tasks": [{
            "id": "task",
            "role": "worker",
            "status": "pending",
            "depends_on": [],
            "inputs": [],
            "outputs": ["work/result.txt"],
            "write_scope": ["work"],
            "review_required": True,
            "human_gate": False,
        }],
    }


def test_campaign_schema_error_reports_instance_and_schema_paths() -> None:
    data = _campaign()
    data["tasks"][0]["review_required"] = "yes"
    errors = validate_campaign(
        data,
        ROOT / "schemas" / "campaign.schema.json",
        Path("campaigns/c/campaign.yaml"),
    )
    assert "campaigns" in errors[0] and "campaign.yaml" in errors[0]
    assert "tasks.0.review_required" in errors[0]
    assert "properties.tasks.items.properties.review_required.type" in errors[0]


def test_campaign_rejects_schema_whose_version_disagrees_with_project_pin(contract_root: Path) -> None:
    schema = json.loads((ROOT / "schemas" / "campaign.schema.json").read_text(encoding="utf-8"))
    schema["properties"]["schema_version"]["const"] = 2
    schema_path = contract_root / "campaign.schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    project = contract_root / "science-project.yaml"
    project.write_text(yaml.safe_dump({"contracts": {"campaign": 1}}), encoding="utf-8")
    errors = validate_campaign(_campaign(), schema_path, Path("campaign.yaml"), project)
    assert any("pinned contract version 1" in error for error in errors)


def test_handoff_executes_pinned_schema_before_policy() -> None:
    handoff = {
        "schema_version": 1,
        "campaign_id": "contract-test",
        "task_id": "task",
        "agent_role": "worker",
        "status": "complete",
        "summary": "done",
        "outputs": ["work/result.txt"],
        "evidence": [7],
        "unresolved": [],
        "recommended_next": [],
    }
    errors = validate_handoff(
        handoff,
        _campaign(),
        ROOT / "schemas" / "handoff.schema.json",
        Path("handoffs/task.yaml"),
    )
    assert any("evidence.0" in error and "schema " in error for error in errors)


def test_review_fails_malformed_run_record_without_key_error(contract_root: Path) -> None:
    project = contract_root
    (project / "schemas").mkdir()
    (project / "schemas" / "run.schema.json").write_bytes(
        (ROOT / "schemas" / "run.schema.json").read_bytes()
    )
    experiment = project / "experiments" / "demo"
    run_dir = experiment / "records" / "bad"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    (run_dir / "manifest.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    (run_dir / "environment.json").write_text("{}", encoding="utf-8")

    passed, report_path = review_run(run_dir)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert not passed
    contract = next(check for check in report["checks"] if check["name"] == "run_contract")
    assert not contract["passed"]
    assert any("run.json" in error and "required" in error for error in contract["errors"])
