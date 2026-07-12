from __future__ import annotations

import json
from pathlib import Path

import yaml

from science_repo.migration import plan_contract_migration


def _schema(path: Path, version: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"properties": {"schema_version": {"const": version}}}), encoding="utf-8")


def _project(path: Path, contracts: dict[str, object], *, local_versions: dict[str, int] | None = None) -> None:
    path.mkdir(parents=True)
    (path / "science-project.yaml").write_text(yaml.safe_dump({"contracts": contracts}), encoding="utf-8")
    for name, version in (local_versions or {}).items():
        _schema(path / "schemas" / f"{name}.schema.json", version)


def test_matching_pins_and_schemas_are_compatible_and_read_only(tmp_path: Path):
    project, available = tmp_path / "project", tmp_path / "available"
    versions = {"campaign": 1, "experiment": 1, "handoff": 1}
    _project(project, versions, local_versions=versions)
    for name in versions:
        _schema(available / f"{name}.schema.json", 1)
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}

    plan = plan_contract_migration(project, versions, available)

    assert plan.status == "compatible"
    assert not plan.legacy_without_local_schemas
    assert [step.contract for step in plan.steps] == ["campaign", "experiment", "handoff"]
    assert all(step.status == "compatible" for step in plan.steps)
    assert before == {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}


def test_upgrade_is_manual_and_describes_copy_update_and_validation(tmp_path: Path):
    project, available = tmp_path / "project", tmp_path / "available"
    current = {"campaign": 1, "experiment": 1, "handoff": 1}
    target = {"campaign": 2, "experiment": 1, "handoff": 1}
    _project(project, current, local_versions=current)
    for name, version in target.items():
        _schema(available / f"{name}.schema.json", version)

    plan = plan_contract_migration(project, target, available)
    campaign = plan.steps[0]
    assert plan.status == "manual"
    assert campaign.status == "manual"
    assert campaign.current_version == 1 and campaign.target_version == 2
    assert campaign.schema_sha256
    assert campaign.actions == (
        "copy schema to schemas/campaign.schema.json",
        "update contracts.campaign from 1 to 2",
        "validate campaign instances",
    )
    assert yaml.safe_load((project / "science-project.yaml").read_text())["contracts"]["campaign"] == 1


def test_legacy_project_is_explicit_and_can_only_produce_manual_copy_plan(tmp_path: Path):
    project, available = tmp_path / "legacy", tmp_path / "available"
    versions = {"campaign": 1, "experiment": 1, "handoff": 1}
    _project(project, versions)
    for name in versions:
        _schema(available / f"{name}.schema.json", 1)

    plan = plan_contract_migration(project, versions, available)

    assert plan.legacy_without_local_schemas
    assert plan.status == "manual"
    assert all(step.status == "manual" for step in plan.steps)
    assert not (project / "schemas").exists()


def test_missing_wrong_unknown_and_downgrade_targets_are_blocked(tmp_path: Path):
    project, available = tmp_path / "project", tmp_path / "available"
    _project(project, {"campaign": 2, "experiment": 1, "handoff": 1, "future": 1})
    _schema(available / "campaign.schema.json", 1)
    _schema(available / "experiment.schema.json", 7)

    plan = plan_contract_migration(
        project, {"campaign": 1, "experiment": 2, "future": 3}, available
    )

    assert plan.status == "blocked"
    assert plan.errors == ("unknown contract: future",)
    assert plan.steps[0].reason.startswith("contract downgrades")
    assert "declares version 7" in plan.steps[1].reason
    assert plan.steps[2].reason == "explicit target version is required"


def test_malformed_manifest_returns_deterministic_blocked_plan(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "science-project.yaml").write_text("contracts: [", encoding="utf-8")

    first = plan_contract_migration(project, {}, tmp_path / "available")
    second = plan_contract_migration(project, {}, tmp_path / "available")

    assert first == second
    assert first.status == "blocked"
    assert first.errors
    assert [step.contract for step in first.steps] == sorted([step.contract for step in first.steps])


def test_plan_serialization_uses_cross_platform_stable_path_contract(tmp_path: Path):
    versions = {"campaign": 1, "experiment": 1, "handoff": 1}
    plans = []
    for root_name in ("windows-simulated", "posix-simulated"):
        project = tmp_path / root_name / "project"
        available = tmp_path / root_name / "available"
        _project(project, versions, local_versions=versions)
        for name in versions:
            _schema(available / f"{name}.schema.json", 1)
        plans.append(plan_contract_migration(project, versions, available))

    assert plans[0].to_dict() == plans[1].to_dict()
    serialized = plans[0].to_dict()
    assert serialized["manifest"] == "science-project.yaml"
    assert serialized["steps"][0]["source_schema"] == "available-schemas/campaign.schema.json"
    assert serialized["steps"][0]["destination_schema"] == "schemas/campaign.schema.json"
    assert "source_schema_host_uri" not in serialized["steps"][0]
    diagnostics = plans[0].to_dict(include_host_local=True)
    assert diagnostics["steps"][0]["source_schema_host_uri"].startswith("file:")
