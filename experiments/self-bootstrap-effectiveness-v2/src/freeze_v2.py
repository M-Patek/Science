from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import yaml
from science_repo.cohort_freeze import build_cohort_freeze

EXPERIMENT = Path("experiments/self-bootstrap-effectiveness-v2")
FROZEN_REGISTRATION_MATERIALS = (
    "experiment.yaml",
    "hypothesis.md",
    "protocol.md",
    "rubric.md",
    "cohort-design-v2.yaml",
    "task-fixtures-v2.yaml",
    "tool-policy-v2.yaml",
    "post-pilot-amendments.md",
    "schemas/attempt-bundle-v2.schema.json",
    "schemas/blinded-scoring-packet-v2.schema.json",
    "schemas/allocation-ledger-v2.schema.json",
    "schemas/packet-set-v2.schema.json",
    "schemas/evidence-manifest-v2.schema.json",
    "schemas/attempt-manifest-v2.schema.json",
    "schemas/scoring-packet-manifest-v2.schema.json",
    "schemas/score-record-v2.schema.json",
    "schemas/adjudication-record-v2.schema.json",
    "schemas/derived-data-v2.schema.json",
    "templates/subject-packet-v2.yaml",
    "templates/arm-control-v2.yaml",
    "templates/arm-treatment-v2.yaml",
    "templates/score-v2.csv",
    "src/analyze.py",
    "src/freeze_v2.py",
    "src/allocate_v2.py",
    "src/verify_attempts.py",
    "src/packetize_scoring_v2.py",
    "src/ingest_adjudicated_v2.py",
    "tests/test_preparation_contracts.py",
    "tests/test_attempt_contract.py",
    "tests/test_allocation_contract.py",
    "tests/test_scoring_contract.py",
    "tests/test_derived_ingestion_contract.py",
    "tests/test_analyze.py",
)


def canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _allocation_module(experiment: Path):
    path = experiment / "src" / "allocate_v2.py"
    spec = importlib.util.spec_from_file_location("allocate_v2_for_freeze", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def build_v2_freeze(
    *,
    project_root: Path,
    human_seed: str,
    runtime_identity: Mapping[str, Any],
    runtime_receipt: Mapping[str, Any],
    extra_review_materials: Sequence[Path],
) -> dict[str, Any]:
    root = project_root.resolve(strict=True)
    experiment = root / EXPERIMENT
    manifest = yaml.safe_load((experiment / "task-fixtures-v2.yaml").read_text(encoding="utf-8"))
    fixtures = [(row["id"], experiment / row["prompt_path"]) for row in manifest["fixtures"]]
    registration = [experiment / relative for relative in FROZEN_REGISTRATION_MATERIALS]
    registration.extend(root / path for path in extra_review_materials)
    freeze = build_cohort_freeze(
        cohort_id="self-bootstrap-effectiveness-v2",
        registration_root=root,
        fixtures=fixtures,
        baseline_materials=[experiment / "templates" / "baseline-v2.yaml"],
        registration_materials=registration,
        human_supplied_seed=human_seed,
        runtime_identity=runtime_identity,
        runtime_identity_receipt=runtime_receipt,
    )
    ranked = _allocation_module(experiment).ranked_assignments(manifest["fixtures"], human_seed)
    freeze["randomization"]["method"] = "sha256-ranked-cells-v1"
    freeze["assignment_ledger"] = [
        {k: r[k] for k in ("cell_id", "fixture_id", "arm", "execution_order")} for r in ranked
    ]
    freeze.pop("freeze_sha256", None)
    freeze["freeze_sha256"] = hashlib.sha256(canonical(freeze) + b"\n").hexdigest()
    return freeze
