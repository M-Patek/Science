from __future__ import annotations

import json
from pathlib import Path

import yaml

from science_repo.lineage import lineage_digest
from science_repo.runner import run_experiment


def _project(tmp_path: Path, script: str, *, inputs=(), outputs=()) -> Path:
    root = tmp_path / "project"
    exp = root / "experiments" / "demo"
    exp.mkdir(parents=True)
    (exp / "worker.py").write_text(script, encoding="utf-8")
    manifest = {
        "schema_version": 1, "id": "demo", "title": "demo", "stage": "designed",
        "question": "q", "hypothesis": "h",
        "inputs": [{"path": value} for value in inputs],
        "execution": {"command": ["{python}", "worker.py"], "outputs": list(outputs)},
    }
    (exp / "experiment.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return root


def _records(run_dir: Path):
    return (json.loads((run_dir / "run.json").read_text()),
            json.loads((run_dir / "lineage.json").read_text()))


def test_success_lineage_binds_input_output_and_run(tmp_path: Path) -> None:
    root = _project(tmp_path, "from pathlib import Path\nPath('out.txt').write_text('result')\n",
                    inputs=("input.txt",), outputs=("out.txt",))
    (root / "experiments/demo/input.txt").write_text("source", encoding="utf-8")
    code, run_dir = run_experiment(root, "demo")
    run, lineage = _records(run_dir)
    assert code == 0
    assert run["lineage"]["sha256"] == lineage_digest(lineage)
    assert run["lineage"]["validation"]["status"] == "not_validated_no_pinned_schema"
    assert {entity["kind"] for entity in lineage["entities"]} == {"run", "code", "dataset", "artifact"}
    assert {relation["kind"] for relation in lineage["relations"]} == {"used", "generated_by", "code_at"}
    command_code = next(entity for entity in lineage["entities"] if entity.get("path", "").endswith("worker.py"))
    assert command_code["digest"].startswith("sha256:")


def test_failed_run_records_absence_without_fake_entity(tmp_path: Path) -> None:
    root = _project(tmp_path, "raise SystemExit(3)\n", outputs=("missing.txt",))
    code, run_dir = run_experiment(root, "demo")
    run, lineage = _records(run_dir)
    assert code == 3 and run["status"] == "failed"
    assert not any(entity["kind"] == "artifact" for entity in lineage["entities"])
    run_entity = next(entity for entity in lineage["entities"] if entity["kind"] == "run")
    assert run_entity["metadata"]["missing_outputs"] == ["missing.txt"]


def test_directory_input_has_bound_digest(tmp_path: Path) -> None:
    root = _project(tmp_path, "pass\n", inputs=("dataset",))
    directory = root / "experiments/demo/dataset"
    directory.mkdir()
    (directory / "part.txt").write_text("value", encoding="utf-8")
    _, run_dir = run_experiment(root, "demo")
    run, lineage = _records(run_dir)
    dataset = next(entity for entity in lineage["entities"] if entity["kind"] == "dataset")
    assert dataset["metadata"]["kind"] == "directory"
    assert dataset["digest"] == "sha256:" + run["inputs"][0]["sha256"]


def test_tampering_breaks_run_lineage_digest_binding(tmp_path: Path) -> None:
    root = _project(tmp_path, "pass\n")
    _, run_dir = run_experiment(root, "demo")
    run, lineage = _records(run_dir)
    lineage["entities"][0]["metadata"]["status"] = "tampered"
    assert lineage_digest(lineage) != run["lineage"]["sha256"]
