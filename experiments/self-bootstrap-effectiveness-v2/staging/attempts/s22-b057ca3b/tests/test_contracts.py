from __future__ import annotations

from pathlib import Path

from science_repo.contracts import contract_pin_errors, schema_errors, schema_parity_errors
from science_repo.io import load_yaml


ROOT = Path(__file__).resolve().parent.parent


def test_source_and_packaged_schemas_have_byte_parity():
    assert schema_parity_errors(ROOT) == []


def test_schema_error_includes_instance_and_field_context():
    manifest = load_yaml(ROOT / "experiments" / "linear-demo" / "experiment.yaml")
    manifest["execution"]["command"] = "python run.py"
    instance = ROOT / "example" / "experiment.yaml"
    errors = schema_errors(manifest, ROOT / "schemas" / "experiment.schema.json", instance)
    assert any(str(instance) in error and "execution.command" in error for error in errors)


def test_project_contract_pin_must_match_local_schema():
    project = {"contracts": {"experiment": 2, "campaign": 1, "handoff": 1}}
    manifest = ROOT / "example" / "science-project.yaml"
    errors = contract_pin_errors(project, ROOT / "schemas", manifest)
    assert len(errors) == 1
    assert "contracts.experiment=2" in errors[0]
    assert str(manifest) in errors[0]
