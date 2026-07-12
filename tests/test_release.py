from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

import science_repo.release as release_module
from science_repo.release import (
    ReleaseIntegrityError,
    generate_release_manifest,
    manifest_json,
    observed_python_dependencies,
    verify_release_manifest,
)


def test_manifest_is_deterministic_and_verifiable(tmp_path: Path) -> None:
    (tmp_path / "schema.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "artifact.txt").write_text("evidence\n", encoding="utf-8")
    first = generate_release_manifest(
        tmp_path, ["schema.json", "artifact.txt"], packaged_schemas=["schema.json"]
    )
    second = generate_release_manifest(
        tmp_path, ["artifact.txt", "schema.json"], packaged_schemas=["schema.json"]
    )
    assert first == second
    assert [entry["path"] for entry in first["artifacts"]] == ["artifact.txt", "schema.json"]
    assert first["artifacts"][1]["type"] == "packaged-schema"
    assert verify_release_manifest(tmp_path, first) == []
    assert json.loads(manifest_json(first)) == first


def test_verifier_reports_content_changes(tmp_path: Path) -> None:
    target = tmp_path / "dist.whl"
    target.write_bytes(b"before")
    manifest = generate_release_manifest(tmp_path, [target])
    target.write_bytes(b"after-content")
    assert verify_release_manifest(tmp_path, manifest) == [
        "dist.whl: sha256 mismatch",
        "dist.whl: size mismatch",
    ]


def test_duplicate_and_escape_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("a", encoding="utf-8")
    with pytest.raises(ReleaseIntegrityError, match="duplicate"):
        generate_release_manifest(tmp_path, ["a", Path("a")])
    with pytest.raises(ReleaseIntegrityError, match="outside|unsafe"):
        generate_release_manifest(tmp_path, ["../escape"])
    manifest = generate_release_manifest(tmp_path, ["a"])
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    with pytest.raises(ReleaseIntegrityError, match="duplicate"):
        verify_release_manifest(tmp_path, manifest)

    malformed = generate_release_manifest(tmp_path, ["a"])
    malformed["artifacts"][0]["sha256"] = "not-a-digest"
    with pytest.raises(ReleaseIntegrityError, match="invalid sha256"):
        verify_release_manifest(tmp_path, malformed)


def test_symlink_is_rejected_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ReleaseIntegrityError, match="symlink"):
        generate_release_manifest(tmp_path, [link])


def test_simulated_intermediate_reparse_point_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "junction"
    directory.mkdir()
    (directory / "artifact").write_text("x", encoding="utf-8")
    actual = release_module._is_linklike

    def simulated(path: Path) -> bool:
        return path.name == "junction" or actual(path)

    monkeypatch.setattr(release_module, "_is_linklike", simulated)
    with pytest.raises(ReleaseIntegrityError, match="junctions"):
        generate_release_manifest(tmp_path, ["junction/artifact"])


def test_wheel_version_is_only_reported_when_metadata_agrees(tmp_path: Path) -> None:
    wheel = tmp_path / "demo-1.2-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("demo-1.2.dist-info/METADATA", "Name: demo\nVersion: 1.2\n")
    manifest = generate_release_manifest(tmp_path, [wheel])
    assert manifest["artifacts"][0]["version"] == "1.2"


def test_dependency_inventory_truthfully_labels_limitations() -> None:
    inventory = observed_python_dependencies()
    assert inventory["kind"] == "observed-python-distribution-metadata"
    assert inventory["packages"] == sorted(
        inventory["packages"], key=lambda item: (item["name"].casefold(), item["version"])
    )
    assert "not a dependency lock" in inventory["limitations"]
    assert "vulnerability scan" in inventory["limitations"]
