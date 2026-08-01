from __future__ import annotations

from pathlib import Path

from science_repo.contracts import contract_pin_errors, schema_errors, schema_parity_errors
from science_repo.io import load_yaml
from science_repo.models import validate_manifest


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


def test_tags_omission_is_valid():
    """Tags are optional and can be omitted."""
    data = {
        "schema_version": 1,
        "id": "test-exp",
        "title": "Test",
        "stage": "idea",
        "question": "Q?",
        "hypothesis": "H",
        "execution": {"command": ["echo", "hi"], "outputs": []},
    }
    errors = validate_manifest(data)
    assert not any("tags" in e for e in errors)


def test_tags_valid_list():
    """Valid tags are accepted."""
    data = {
        "schema_version": 1,
        "id": "test-exp",
        "title": "Test",
        "stage": "idea",
        "question": "Q?",
        "hypothesis": "H",
        "execution": {"command": ["echo", "hi"], "outputs": []},
        "tags": ["alpha", "beta-gamma", "x123"],
    }
    errors = validate_manifest(data)
    assert "tags" not in str(errors)


def test_tags_duplicates_rejected():
    """Duplicate tags are rejected."""
    data = {
        "schema_version": 1,
        "id": "test-exp",
        "title": "Test",
        "stage": "idea",
        "question": "Q?",
        "hypothesis": "H",
        "execution": {"command": ["echo", "hi"], "outputs": []},
        "tags": ["alpha", "alpha"],
    }
    errors = validate_manifest(data)
    assert any("duplicate" in e for e in errors)


def test_tags_uppercase_rejected():
    """Uppercase letters in tags are rejected."""
    data = {
        "schema_version": 1,
        "id": "test-exp",
        "title": "Test",
        "stage": "idea",
        "question": "Q?",
        "hypothesis": "H",
        "execution": {"command": ["echo", "hi"], "outputs": []},
        "tags": ["Alpha"],
    }
    errors = validate_manifest(data)
    assert any("kebab-case" in e for e in errors)


def test_tags_empty_string_rejected():
    """Empty string tags are rejected."""
    data = {
        "schema_version": 1,
        "id": "test-exp",
        "title": "Test",
        "stage": "idea",
        "question": "Q?",
        "hypothesis": "H",
        "execution": {"command": ["echo", "hi"], "outputs": []},
        "tags": [""],
    }
    errors = validate_manifest(data)
    assert any("empty" in e or "kebab-case" in e for e in errors)
