from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from science_repo.lineage import lineage_digest, load_lineage, validate_lineage


ZERO = "sha256:" + "0" * 64


def manifest() -> dict:
    return {
        "schema_version": 1,
        "entities": [
            {"id": "raw.v1", "kind": "dataset", "digest": ZERO, "path": "data/raw/v1.csv"},
            {"id": "run:1", "kind": "run", "digest": ZERO, "path": "records/run-1/run.json"},
            {"id": "result", "kind": "artifact", "digest": ZERO, "path": "results/out.json"},
        ],
        "relations": [
            {"source": "raw.v1", "target": "run:1", "kind": "used"},
            {"source": "run:1", "target": "result", "kind": "generated_by"},
        ],
    }


def schema() -> Path:
    return Path(__file__).parents[1] / "schemas" / "lineage.schema.json"


def test_valid_manifest_and_pinned_schema(tmp_path: Path) -> None:
    value = manifest()
    assert validate_lineage(value, tmp_path / "lineage.yaml", tmp_path, schema_path=schema()) == []


def test_digest_is_mapping_order_independent_and_content_sensitive() -> None:
    value = manifest()
    reordered = {"relations": deepcopy(value["relations"]), "entities": deepcopy(value["entities"]), "schema_version": 1}
    assert lineage_digest(value) == lineage_digest(reordered)
    reordered["entities"][0]["id"] = "changed"
    assert lineage_digest(value) != lineage_digest(reordered)


def test_load_json_yaml_and_reject_scalar(tmp_path: Path) -> None:
    json_path = tmp_path / "lineage.json"
    json_path.write_text(json.dumps(manifest()), encoding="utf-8")
    assert load_lineage(json_path) == manifest()
    yaml_path = tmp_path / "lineage.yaml"
    yaml_path.write_text("schema_version: 1\nentities: []\nrelations: []\n", encoding="utf-8")
    assert load_lineage(yaml_path)["entities"] == []
    yaml_path.write_text("- not-an-object\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        load_lineage(yaml_path)


@pytest.mark.parametrize(
    "unsafe",
    [
        "../secret",
        "/absolute",
        "a\\b",
        "a/../b",
        ".",
        "C:foo",
        "safe/file:stream",
        "CON",
        "dir/con.txt",
        "a.",
        "dir/a ",
        "bad\x01name",
        "bad\x7fname",
    ],
)
def test_rejects_unsafe_paths(tmp_path: Path, unsafe: str) -> None:
    value = manifest()
    value["entities"][0]["path"] = unsafe
    errors = validate_lineage(value, tmp_path / "lineage.yaml", tmp_path)
    assert any("entities[0].path" in error for error in errors)


def test_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    outside = tmp_path.parent / "lineage-outside"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is privilege-dependent")
    value = manifest()
    value["entities"][0]["path"] = "link/secret.csv"
    assert any("escapes" in error for error in validate_lineage(value, tmp_path / "m.yaml", tmp_path))


def test_rejects_duplicates_unknown_references_self_edges_and_cycles(tmp_path: Path) -> None:
    value = manifest()
    value["entities"].append(dict(value["entities"][0]))
    value["relations"].extend(
        [
            {"source": "missing", "target": "result", "kind": "used"},
            {"source": "result", "target": "result", "kind": "derived_from"},
            {"source": "result", "target": "raw.v1", "kind": "derived_from"},
            dict(value["relations"][0]),
        ]
    )
    joined = "\n".join(validate_lineage(value, tmp_path / "m.yaml", tmp_path))
    for phrase in ("duplicate entity", "unknown entity", "self relation", "duplicate relation", "acyclic"):
        assert phrase in joined


def test_semantic_validation_survives_absent_schema_and_checks_contract(tmp_path: Path) -> None:
    value = manifest()
    value["schema_version"] = 2
    value["entities"][0].update(kind="fiction", digest="not-a-digest")
    value["relations"][0]["kind"] = "invented"
    errors = validate_lineage(value, tmp_path / "m.yaml", tmp_path)
    assert any("schema_version" in error for error in errors)
    assert any("kind is unsupported" in error for error in errors)
    assert any("sha256 digest" in error for error in errors)


def test_explicit_missing_or_wrong_version_schema_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "schemas" / "lineage.schema.json"
    assert "missing pinned" in validate_lineage(
        manifest(), tmp_path / "m.yaml", tmp_path, schema_path=missing
    )[0]
    errors = validate_lineage(
        manifest(), tmp_path / "m.yaml", tmp_path, schema_path=schema(), expected_version=2
    )
    assert any("does not match pinned contract" in error for error in errors)
