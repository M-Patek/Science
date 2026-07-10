from science_repo.models import validate_manifest
from science_repo import __version__
from science_repo.io import load_yaml
from pathlib import Path


def test_manifest_rejects_shell_string():
    data = {
        "schema_version": 1,
        "id": "abc",
        "title": "t",
        "stage": "idea",
        "question": "q",
        "hypothesis": "h",
        "execution": {"command": "python run.py", "outputs": []},
    }
    assert "execution.command must be a non-empty string array" in validate_manifest(data)


def test_manifest_accepts_minimal_valid_shape():
    data = {
        "schema_version": 1,
        "id": "abc",
        "title": "t",
        "stage": "idea",
        "question": "q",
        "hypothesis": "h",
        "execution": {"command": ["python", "run.py"], "outputs": []},
    }
    assert validate_manifest(data) == []


def test_framework_and_package_versions_match():
    root = Path(__file__).resolve().parent.parent
    assert load_yaml(root / "science-framework.yaml")["version"] == __version__
