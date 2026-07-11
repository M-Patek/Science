from argparse import Namespace
import json
from pathlib import Path
import shutil
from uuid import uuid4

from science_repo.cli import (
    cmd_handoff_validate,
    cmd_task_claim,
    cmd_task_heartbeat,
    cmd_task_release,
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
