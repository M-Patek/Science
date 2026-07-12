from argparse import Namespace
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from science_repo.cli import (
    cmd_campaign_status,
    cmd_cohort_plan,
    cmd_cohort_validate,
    cmd_dispatch_audit,
    cmd_dispatch_envelope,
    cmd_handoff_validate,
    cmd_task_claim,
    cmd_task_heartbeat,
    cmd_task_release,
    cmd_transition,
)
from science_repo.io import dump_yaml


def _project():
    root = Path(__file__).parent / "fixtures" / f"orchestration-{uuid4().hex}"
    campaign = root / "campaigns" / "demo"
    campaign.mkdir(parents=True)
    dump_yaml(root / "science-project.yaml", {"schema_version": 1, "id": "test-project"})
    dump_yaml(
        campaign / "campaign.yaml",
        {
            "schema_version": 1,
            "id": "demo",
            "title": "Demo",
            "objective": "Test orchestration commands",
            "status": "approved",
            "owner": "tests",
            "tasks": [
                {
                    "id": "implement",
                    "role": "developer",
                    "status": "pending",
                    "depends_on": [],
                    "inputs": [],
                    "outputs": ["work/result.json"],
                    "write_scope": ["work/"],
                    "review_required": True,
                    "human_gate": False,
                }
            ],
        },
    )
    return root


def test_cli_claim_heartbeat_release(capsys):
    root = _project()
    try:
        common = {"project": str(root), "campaign": "demo", "task": "implement", "worker": "agent-1"}
        assert cmd_task_claim(Namespace(**common, lease_seconds=30)) == 0
        lease = json.loads(capsys.readouterr().out)
        assert cmd_task_heartbeat(
            Namespace(**common, token=lease["token"], lease_seconds=30)
        ) == 0
        capsys.readouterr()
        assert cmd_task_release(
            Namespace(**common, token=lease["token"], outcome="completed")
        ) == 0
        released = json.loads(capsys.readouterr().out)
        assert released["status"] == "completed"
    finally:
        shutil.rmtree(root)


def test_cli_validates_handoff_against_campaign(capsys):
    root = _project()
    try:
        path = root / "handoff.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "campaign_id": "demo",
                    "task_id": "implement",
                    "agent_role": "developer",
                    "status": "complete",
                    "summary": "Done",
                    "outputs": ["work/result.json"],
                    "evidence": ["tests passed"],
                    "unresolved": [],
                    "recommended_next": [],
                }
            ),
            encoding="utf-8",
        )
        assert cmd_handoff_validate(
            Namespace(project=str(root), campaign="demo", handoff=str(path))
        ) == 0
        assert "passed" in capsys.readouterr().out
    finally:
        shutil.rmtree(root)


def test_cli_creates_and_audits_native_dispatch(capsys):
    root = _project()
    try:
        args = Namespace(project=str(root), campaign="demo", task="implement")
        assert cmd_dispatch_envelope(args) == 0
        envelope = json.loads(capsys.readouterr().out)
        envelope_path = root / "envelope.json"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        handoff_path = root / "handoff.json"
        handoff_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "campaign_id": "demo",
                    "task_id": "implement",
                    "agent_role": "developer",
                    "status": "complete",
                    "summary": "Done",
                    "outputs": ["work/result.json"],
                    "evidence": ["tests passed"],
                    "unresolved": [],
                    "recommended_next": [],
                }
            ),
            encoding="utf-8",
        )
        assert cmd_dispatch_audit(
            Namespace(
                project=str(root),
                campaign="demo",
                envelope=str(envelope_path),
                handoff=str(handoff_path),
            )
        ) == 0
    finally:
        shutil.rmtree(root)


def test_cli_reports_ready_campaign_task(capsys):
    root = _project()
    try:
        assert cmd_campaign_status(
            Namespace(project=str(root), campaign="demo", max_attempts=3)
        ) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["tasks"][0]["state"] == "ready"
    finally:
        shutil.rmtree(root)


def test_cli_applies_audited_stage_transition(capsys):
    root = _project()
    try:
        experiment = root / "experiments" / "demo-exp"
        experiment.mkdir(parents=True)
        (root / "docs" / "_machine").mkdir(parents=True)
        dump_yaml(
            experiment / "experiment.yaml",
            {"schema_version": 1, "id": "demo-exp", "title": "Demo", "stage": "idea"},
        )
        assert cmd_transition(
            Namespace(
                project=str(root), id="demo-exp", to="designed",
                reason="Protocol is ready", actor="test-agent",
            )
        ) == 0
        event = json.loads(capsys.readouterr().out)
        assert event["from_stage"] == "idea"
        assert event["to_stage"] == "designed"
        assert (experiment / "stage-history.jsonl").is_file()
        registry = json.loads((root / "docs" / "_machine" / "experiments.json").read_text())
        assert registry["experiments"][0]["stage"] == "designed"
    finally:
        shutil.rmtree(root)


def test_cli_validates_but_does_not_plan_blocked_cohort(capsys):
    root = Path(__file__).parents[1] / "dogfood" / "framework-self-study"
    common = {
        "project": str(root),
        "experiment": "framework-onboarding",
        "campaign": "framework-self-evaluation",
        "cohort": "cohort-v1.yaml",
    }
    assert cmd_cohort_validate(Namespace(**common)) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit, match="not frozen"):
        cmd_cohort_plan(
            Namespace(
                **common,
                sessions=[f"subject-{index}" for index in range(1, 16)],
                copy_mechanism="git-worktree",
            )
        )
