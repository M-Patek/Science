from __future__ import annotations

import json
import shutil
from pathlib import Path

from science_repo.review import review_run
from science_repo.runner import run_experiment
from science_repo.validate import validate_repository
from science_repo.cli import ASSETS, cmd_campaign_validate, cmd_validate
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
    # This disposable fixture is intentionally separate from the repository's
    # append-only evidence. Always remove the generated test record afterward.
    isolated = ROOT / "tests" / "fixtures" / "runner-repo"
    target = isolated / "experiments" / "linear-demo"
    schemas = isolated / "schemas"
    schemas.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "schemas" / "lineage.schema.json", schemas)
    shutil.copy2(ROOT / "schemas" / "run.schema.json", schemas)
    project_manifest = isolated / "science-project.yaml"
    project_manifest.write_text(
        "contracts:\n  experiment: 1\n  campaign: 1\n  handoff: 1\n", encoding="utf-8"
    )
    code, run_dir = run_experiment(isolated, "linear-demo")
    try:
        assert code == 0
        assert run_dir.parent == target / "records"
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        assert record["status"] == "succeeded"
        passed, report = review_run(run_dir)
        assert passed
        assert report.is_file()
        review = json.loads(report.read_text(encoding="utf-8"))
        assert any(
            check["name"] == "acceptance:slope_absolute_error" for check in review["checks"]
        )
    finally:
        shutil.rmtree(run_dir)
        shutil.rmtree(schemas)
        project_manifest.unlink()


class TestValidateCommand:
    """Tests for `science validate` command with --format option."""

    def test_valid_project_default_output(self, capsys):
        """Valid project should print human-readable success message."""
        args = Namespace(project=str(ROOT), format="human")
        exit_code = cmd_validate(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Repository validation passed." in captured.out

    def test_valid_project_json_output(self, capsys):
        """Valid project should return JSON with valid=true, sorted keys, no timestamps."""
        args = Namespace(project=str(ROOT), format="json")
        exit_code = cmd_validate(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out)
        assert output["valid"] is True
        assert output["errors"] == []
        assert "project_path" in output
        # No timestamps in output
        assert "time" not in captured.out.lower()
        # Deterministic ordering: keys should be sorted
        assert list(json.loads(captured.out, object_pairs_hook=lambda pairs: pairs).keys()) == sorted(output.keys())

    def test_invalid_project_default_output(self, capsys, tmp_path):
        """Invalid project should print human-readable error message and return exit code 1."""
        args = Namespace(project=str(tmp_path), format="human")
        exit_code = cmd_validate(args)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Validation failed:" in captured.out

    def test_invalid_project_json_output(self, capsys, tmp_path):
        """Invalid project should return JSON with valid=false and sorted errors."""
        args = Namespace(project=str(tmp_path), format="json")
        exit_code = cmd_validate(args)
        captured = capsys.readouterr()
        assert exit_code == 1
        output = json.loads(captured.out)
        assert output["valid"] is False
        assert len(output["errors"]) > 0
        # Errors should be sorted
        assert output["errors"] == sorted(output["errors"])

    def test_json_deterministic_ordering(self, capsys):
        """JSON output must be deterministic (sorted keys and errors)."""
        args = Namespace(project=str(ROOT), format="json")
        results = []
        for _ in range(3):
            cmd_validate(args)
            captured = capsys.readouterr()
            results.append(captured.out)
        assert results[0] == results[1] == results[2]

    def test_json_relative_path_privacy(self, capsys, tmp_path):
        """When user supplies relative path, project_path should be relative."""
        # Create a valid project in tmp_path
        (tmp_path / "science-project.yaml").write_text(
            "kind: research-project\nschema_version: 1\ncontracts:\n  experiment: 1\n",
            encoding="utf-8"
        )
        (tmp_path / "docs" / "_machine").mkdir(parents=True, exist_ok=True)
        (tmp_path / "docs" / "_machine" / "experiments.json").write_text(
            '{"schema_version": 1, "experiments": []}', encoding="utf-8"
        )
        (tmp_path / "experiments").mkdir(exist_ok=True)
        (tmp_path / "schemas").mkdir(exist_ok=True)

        # Use relative path from current directory
        rel_path = tmp_path.relative_to(Path.cwd())
        args = Namespace(project=str(rel_path), format="json")
        exit_code = cmd_validate(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out)
        # Should preserve relative path
        assert not Path(output["project_path"]).is_absolute()

    def test_json_absolute_path_when_supplied(self, capsys, tmp_path):
        """When user supplies absolute path, project_path should be absolute."""
        # Create a valid project in tmp_path
        (tmp_path / "science-project.yaml").write_text(
            "kind: research-project\nschema_version: 1\ncontracts:\n  experiment: 1\n",
            encoding="utf-8"
        )
        (tmp_path / "docs" / "_machine").mkdir(parents=True, exist_ok=True)
        (tmp_path / "docs" / "_machine" / "experiments.json").write_text(
            '{"schema_version": 1, "experiments": []}', encoding="utf-8"
        )
        (tmp_path / "experiments").mkdir(exist_ok=True)
        (tmp_path / "schemas").mkdir(exist_ok=True)

        # Use absolute path
        args = Namespace(project=str(tmp_path), format="json")
        exit_code = cmd_validate(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out)
        # Should preserve absolute path
        assert Path(output["project_path"]).is_absolute()
