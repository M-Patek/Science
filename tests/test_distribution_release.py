from __future__ import annotations

import json
from pathlib import Path
import zipfile

from scripts.verify_distribution import PACKAGED_SCHEMAS, create_release_manifest
from science_repo.release import verify_release_manifest


def test_distribution_manifest_binds_wheel_and_all_packaged_schemas(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "science_workbench-0.2.0.dev0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "science_workbench-0.2.0.dev0.dist-info/METADATA",
            "Name: science-workbench\nVersion: 0.2.0.dev0\n",
        )
        for name in PACKAGED_SCHEMAS:
            archive.writestr(name, "{}\n")

    manifest_path = create_release_manifest(tmp_path, wheel)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert verify_release_manifest(tmp_path, manifest) == []
    artifacts = {entry["path"]: entry for entry in manifest["artifacts"]}
    assert artifacts[f"dist/{wheel.name}"]["type"] == "wheel"
    assert any(path.endswith("lineage.schema.json") for path in artifacts)
    assert sum(entry["type"] == "packaged-schema" for entry in artifacts.values()) == len(
        PACKAGED_SCHEMAS
    )
    inventory = manifest["dependency_inventory"]
    assert inventory["kind"] == "observed-python-distribution-metadata"
    for boundary in ("vulnerability scan", "signature", "attestation"):
        assert boundary in inventory["limitations"]


def test_manifest_detects_mutated_extracted_schema(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "science_workbench-0.2.0.dev0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "science_workbench-0.2.0.dev0.dist-info/METADATA",
            "Name: science-workbench\nVersion: 0.2.0.dev0\n",
        )
        for name in PACKAGED_SCHEMAS:
            archive.writestr(name, "{}\n")
    manifest_path = create_release_manifest(tmp_path, wheel)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lineage = next(
        tmp_path / entry["path"]
        for entry in manifest["artifacts"]
        if entry["path"].endswith("lineage.schema.json")
    )
    lineage.write_text('{"changed": true}\n', encoding="utf-8")
    assert verify_release_manifest(tmp_path, manifest)
