import json
import shutil
from pathlib import Path
from uuid import uuid4

from science_repo.handoff import load_handoff, validate_handoff


def campaign():
    return {
        "id": "self-study",
        "tasks": [
            {"id": "implement", "role": "developer", "write_scope": ["science_repo/handoff.py", "tests/"]}
        ],
    }


def handoff(**changes):
    value = {
        "schema_version": 1,
        "campaign_id": "self-study",
        "task_id": "implement",
        "agent_role": "developer",
        "status": "complete",
        "summary": "Implemented and tested handoff validation.",
        "outputs": ["science_repo/handoff.py"],
        "changed_files": ["tests/test_handoff.py"],
        "evidence": ["pytest tests/test_handoff.py"],
        "unresolved": [],
        "recommended_next": ["Integrate with the scheduler."],
    }
    value.update(changes)
    return value


def test_load_handoff_supports_json_and_yaml():
    directory = Path(__file__).parent / "fixtures" / f"handoff-{uuid4().hex}"
    directory.mkdir()
    try:
        json_path = directory / "handoff.json"
        json_path.write_text(json.dumps(handoff()), encoding="utf-8")
        yaml_path = directory / "handoff.yaml"
        yaml_path.write_text("schema_version: 1\ntask_id: implement\n", encoding="utf-8")
        assert load_handoff(json_path)["task_id"] == "implement"
        assert load_handoff(yaml_path)["task_id"] == "implement"
    finally:
        shutil.rmtree(directory)


def test_valid_handoff_is_accepted():
    assert validate_handoff(handoff(), campaign()) == []


def test_handoff_must_identify_campaign_task_and_role():
    errors = validate_handoff(
        handoff(campaign_id="other", task_id="missing", agent_role="reviewer"), campaign()
    )
    assert any("campaign_id" in error for error in errors)
    assert any("unknown campaign task" in error for error in errors)


def test_outputs_and_changed_files_must_be_in_write_scope():
    errors = validate_handoff(
        handoff(outputs=["../escape.txt"], changed_files=["docs/unauthorized.md"]), campaign()
    )
    assert any("outputs path" in error for error in errors)
    assert any("changed_files path" in error for error in errors)


def test_status_requires_appropriate_evidence_or_unresolved_work():
    assert any("include evidence" in error for error in validate_handoff(handoff(evidence=[]), campaign()))
    errors = validate_handoff(handoff(status="blocked", unresolved=[]), campaign())
    assert any("describe unresolved work" in error for error in errors)


def test_required_arrays_are_structured():
    errors = validate_handoff(handoff(evidence="pytest"), campaign())
    assert any("evidence must be an array" in error for error in errors)
