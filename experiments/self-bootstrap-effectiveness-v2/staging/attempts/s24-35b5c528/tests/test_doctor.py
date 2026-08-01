from __future__ import annotations

import json
from pathlib import Path

import yaml

from science_repo.doctor import SCHEMAS, REMEDIATION_CODES, diagnose


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
    assert codes.count("contracts.schema-missing") == len(SCHEMAS) - 1
    assert report["summary"]["error"] >= 5


def test_doctor_unknown_root_has_actionable_errors(tmp_path: Path) -> None:
    report = diagnose(tmp_path)
    finding = next(f for f in report["findings"] if f["code"] == "project.manifest-missing")
    assert finding["severity"] == "error"
    assert "remediation" in finding
    assert set(report["git"]) == {"available", "revision", "dirty"}


def test_remediation_codes_present_for_failed_and_unknown_checks(tmp_path: Path) -> None:
    """Failed and unknown checks have remediation_code; passing checks do not."""
    report = diagnose(tmp_path)
    for finding in report["findings"]:
        if finding["severity"] in ("error", "warning"):
            assert "remediation_code" in finding, f"Missing remediation_code for {finding['code']}"
            assert finding["remediation_code"].startswith("REMEDIATE_")
        elif finding["severity"] == "info" and finding["code"] in REMEDIATION_CODES:
            assert "remediation_code" in finding, f"Missing remediation_code for info-level {finding['code']}"


def test_remediation_codes_absent_for_passing_checks(tmp_path: Path) -> None:
    """Checks that pass (no finding produced) have no remediation_code to emit."""
    _project(tmp_path)
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    for name in SCHEMAS:
        (schemas / f"{name}.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    report = diagnose(tmp_path)
    for finding in report["findings"]:
        if finding["severity"] == "info" and finding["code"] not in REMEDIATION_CODES:
            assert "remediation_code" not in finding, f"Unexpected remediation_code for {finding['code']}"


def test_remediation_code_stability() -> None:
    """Remediation codes are stable and come from the finite mapping."""
    assert "project.manifest-missing" in REMEDIATION_CODES
    assert REMEDIATION_CODES["project.manifest-missing"] == "REMEDIATE_RUN_FROM_ROOT"
    assert "contracts.schema-missing" in REMEDIATION_CODES
    assert REMEDIATION_CODES["contracts.schema-missing"] == "REMEDIATE_RESTORE_SCHEMA"
    assert "python.dependency-missing" in REMEDIATION_CODES
    assert REMEDIATION_CODES["python.dependency-missing"] == "REMEDIATE_INSTALL_DEPENDENCY"
    assert "python.version-unsupported" in REMEDIATION_CODES
    assert REMEDIATION_CODES["python.version-unsupported"] == "REMEDIATE_UPGRADE_PYTHON"


def test_remediation_codes_in_json_output(tmp_path: Path) -> None:
    """JSON serialization includes remediation_code fields without environment leakage."""
    report = diagnose(tmp_path)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    parsed = json.loads(serialized)
    for finding in parsed["findings"]:
        if "remediation_code" in finding:
            assert finding["remediation_code"].startswith("REMEDIATE_")
            assert "password" not in finding["remediation_code"].lower()
            assert "secret" not in finding["remediation_code"].lower()
            assert "token" not in finding["remediation_code"].lower()
    assert "root" in parsed


def test_no_leakage_of_environment_values(tmp_path: Path) -> None:
    """Diagnostic output does not embed sensitive environment values in findings."""
    _project(tmp_path)
    report = diagnose(tmp_path)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    for finding in report["findings"]:
        message = finding.get("message", "")
        remediation = finding.get("remediation", "")
        for field in (message, remediation):
            assert "HOME=" not in field
            assert "PATH=" not in field
            assert "TOKEN=" not in field
            assert "SECRET=" not in field
            assert "PASSWORD=" not in field
    assert "root" in serialized
