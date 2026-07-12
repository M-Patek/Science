from __future__ import annotations

import json
from pathlib import Path

import yaml

from science_repo.doctor import diagnose


def _project(root: Path) -> None:
    (root / "docs/_machine").mkdir(parents=True)
    (root / "experiments").mkdir()
    (root / "campaigns").mkdir()
    (root / ".agents/skills/run-experiment").mkdir(parents=True)
    (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
    (root / "docs/INDEX.md").write_text("routes", encoding="utf-8")
    (root / "docs/_machine/experiments.json").write_text('{"experiments": []}', encoding="utf-8")
    (root / ".agents/skills/run-experiment/SKILL.md").write_text("skill", encoding="utf-8")
    (root / "science-project.yaml").write_text(yaml.safe_dump({"kind": "research-project", "contracts": {"experiment": 1, "campaign": 1, "handoff": 1}}), encoding="utf-8")


def test_doctor_is_read_only_and_deterministic(tmp_path: Path) -> None:
    _project(tmp_path)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    first = diagnose(tmp_path)
    second = diagnose(tmp_path)
    assert first == second
    assert before == sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert first["kind"] == "research-project"
    assert first["agent_skills"] == ["run-experiment"]
    assert any(f["code"] == "contracts.legacy-no-local-schemas" for f in first["findings"])
    json.dumps(first)


def test_doctor_reports_missing_contracts_and_paths(tmp_path: Path) -> None:
    _project(tmp_path)
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "project.schema.json").write_text("not-json", encoding="utf-8")
    report = diagnose(tmp_path)
    codes = [item["code"] for item in report["findings"]]
    assert "contracts.schema-invalid" in codes
    assert codes.count("contracts.schema-missing") == 6
    assert report["summary"]["error"] >= 5


def test_doctor_unknown_root_has_actionable_errors(tmp_path: Path) -> None:
    report = diagnose(tmp_path)
    finding = next(f for f in report["findings"] if f["code"] == "project.manifest-missing")
    assert finding["severity"] == "error"
    assert "remediation" in finding
    assert set(report["git"]) == {"available", "revision", "dirty"}
