import json
from pathlib import Path
from uuid import uuid4

import pytest

from science_repo.reproduce import assess_environment_files, assess_reproduction, load_environment


def test_assessment_is_deterministic_json_safe_and_reports_package_diff():
    reference = {"python": "3.12.2 (main)", "platform": "Linux-x86", "packages": ["B==2", "a==1"]}
    current = {"python": "3.12.2 other build", "platform": "Linux-x86", "packages": ["a==3", "c==4"]}
    result = assess_reproduction(reference, current)
    assert json.dumps(result, sort_keys=True) == json.dumps(assess_reproduction(reference, current), sort_keys=True)
    assert result["overall_status"] == "mismatch"
    assert result["dimensions"]["python"]["status"] == "match"
    packages = result["dimensions"]["packages"]
    assert len(packages["added"][0]["sha256"]) == 64
    assert len(packages["removed"][0]["sha256"]) == 64
    assert set(packages["changed"][0]) == {"name_sha256", "reference_sha256", "current_sha256"}
    assert "c==4" not in json.dumps(result)


def test_missing_and_explicit_unavailable_are_not_matches():
    result = assess_reproduction({}, {"python": None, "platform": "unavailable", "packages": []})
    assert result["overall_status"] == "indeterminate"
    assert result["dimensions"]["python"]["status"] == "unavailable"
    assert result["dimensions"]["container"]["status"] == "unknown"


def test_safe_structured_clues_and_environment_signal_values_never_leak():
    secret = "job-secret-123"
    reference = {
        "container": {"runtime": "docker", "image_digest": "sha256:abc", "token": secret},
        "gpu": {"vendor": "NVIDIA", "driver": "555", "serial": secret},
        "selected_environment": {"SLURM_JOB_ID": secret, "CUDA_VISIBLE_DEVICES": secret, "API_TOKEN": secret},
    }
    result = assess_reproduction(reference, reference)
    encoded = json.dumps(result, sort_keys=True)
    assert secret not in encoded
    assert "API_TOKEN" not in encoded
    assert result["dimensions"]["container"]["status"] == "match"
    assert result["dimensions"]["gpu"]["status"] == "match"
    assert len(result["dimensions"]["orchestration"]["reference"]["sha256"]) == 64


def test_arbitrary_structured_identifiers_are_fingerprinted():
    private = {
        "container": {
            "runtime": "docker",
            "image": "registry.private.example/tenant/research:secret",
            "image_digest": "sha256:private-digest",
            "password": "structured-secret",
        },
        "gpu": {"vendor": "NVIDIA", "model": "tenant-gpu-private", "driver": "private-driver"},
        "orchestration": {"kind": "CI", "provider": "tenant-provider", "runner": "secret-runner"},
        "python": "3.13 private-build",
        "platform": "private-hostname",
        "packages": ["private-package==tenant-version"],
    }
    encoded = json.dumps(assess_reproduction(private, private), sort_keys=True)
    for secret in (
        "registry.private.example", "tenant", "research", "structured-secret",
        "private-driver", "secret-runner", "private-hostname", "private-package",
    ):
        assert secret not in encoded


def test_file_wrapper_and_invalid_document():
    root = Path(".test-tmp-reproduce") / uuid4().hex
    root.mkdir(parents=True)
    left, right = root / "left.json", root / "right.json"
    try:
        left.write_text(json.dumps({"platform": "Windows"}), encoding="utf-8")
        right.write_text(json.dumps({"platform": "Windows"}), encoding="utf-8")
        assert assess_environment_files(left, right)["dimensions"]["platform"]["status"] == "match"
        left.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON object"):
            load_environment(left)
        left.write_text('{"value": NaN}', encoding="utf-8")
        with pytest.raises(ValueError, match="non-finite"):
            load_environment(left)
    finally:
        left.unlink(missing_ok=True)
        right.unlink(missing_ok=True)
        root.rmdir()


@pytest.mark.parametrize(
    "malicious",
    [
        {"value": b"bytes"},
        {"value": {"set"}},
        {1: "non-string key"},
        {"value": float("nan")},
        {"value": object()},
    ],
)
def test_assessment_rejects_non_json_inputs(malicious):
    with pytest.raises(ValueError):
        assess_reproduction(malicious, {})


def test_output_is_strict_json_for_nested_valid_input():
    result = assess_reproduction(
        {"container": {"runtime": "docker", "metadata": [1, 2.5, None, True]}},
        {"container": {"runtime": "docker", "metadata": [1, 2.5, None, True]}},
    )
    json.dumps(result, sort_keys=True, allow_nan=False)
