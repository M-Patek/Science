from pathlib import Path

import pytest
import yaml

from science_repo.migration import plan_contract_migration
from science_repo.migration_apply import (
    MigrationApplyError,
    apply_contract_migration,
    plan_confirmation_token,
)


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "science-project.yaml").write_text(
        yaml.safe_dump({"contracts": {"campaign": 1, "experiment": 1, "handoff": 1}}),
        encoding="utf-8",
    )
    sources = tmp_path / "explicit-sources"
    sources.mkdir()
    repository_schemas = Path(__file__).parents[1] / "schemas"
    for name in ("campaign", "experiment", "handoff"):
        (sources / f"{name}.schema.json").write_bytes(
            (repository_schemas / f"{name}.schema.json").read_bytes()
        )
    return root, sources


def _sources(directory: Path) -> dict[str, Path]:
    return {name: (directory / f"{name}.schema.json").resolve()
            for name in ("campaign", "experiment", "handoff")}


def test_apply_is_dry_run_by_default_and_requires_explicit_token(tmp_path: Path) -> None:
    root, sources = _project(tmp_path)
    plan = plan_contract_migration(root, {name: 1 for name in _sources(sources)}, sources)
    result = apply_contract_migration(root, plan, _sources(sources))
    assert result.status == "dry-run"
    assert not (root / "schemas").exists()
    with pytest.raises(MigrationApplyError, match="confirmation token"):
        apply_contract_migration(root, plan, _sources(sources), dry_run=False)
    applied = apply_contract_migration(
        root, plan, _sources(sources), dry_run=False,
        confirmation_token=plan_confirmation_token(plan),
    )
    assert applied.status == "applied"
    assert apply_contract_migration(root, plan, _sources(sources), dry_run=False).status == "already-applied"


def test_source_tamper_is_rejected_before_writes(tmp_path: Path) -> None:
    root, sources = _project(tmp_path)
    mapping = _sources(sources)
    plan = plan_contract_migration(root, {name: 1 for name in mapping}, sources)
    mapping["campaign"].write_text("{}", encoding="utf-8")
    with pytest.raises(MigrationApplyError, match="hash does not match"):
        apply_contract_migration(root, plan, mapping, dry_run=False,
                                 confirmation_token=plan_confirmation_token(plan))
    assert not (root / "schemas").exists()


def test_fault_after_schema_copy_restores_original_state(tmp_path: Path) -> None:
    root, sources = _project(tmp_path)
    mapping = _sources(sources)
    plan = plan_contract_migration(root, {name: 1 for name in mapping}, sources)

    def fail(phase: str) -> None:
        if phase.startswith("schema:"):
            raise OSError("injected")

    with pytest.raises(MigrationApplyError, match="rollback was attempted"):
        apply_contract_migration(root, plan, mapping, dry_run=False,
                                 confirmation_token=plan_confirmation_token(plan),
                                 fault_injector=fail)
    assert not any((root / "schemas").glob("*.json"))
    assert yaml.safe_load((root / "science-project.yaml").read_text(encoding="utf-8"))["contracts"] == {
        "campaign": 1, "experiment": 1, "handoff": 1,
    }
