from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from science_repo.cohort_freeze import build_cohort_freeze


EXPERIMENT = Path("experiments/self-bootstrap-effectiveness-v2")
FROZEN_REGISTRATION_MATERIALS = (
    "experiment.yaml", "hypothesis.md", "protocol.md", "rubric.md", "cohort-design-v2.yaml",
    "task-fixtures-v2.yaml", "tool-policy-v2.yaml", "post-pilot-amendments.md",
    "schemas/attempt-bundle-v2.schema.json", "schemas/blinded-scoring-packet-v2.schema.json",
    "templates/subject-packet-v2.yaml", "templates/score-v2.csv",
    "src/analyze.py", "src/freeze_v2.py", "src/verify_attempts.py",
)


def build_v2_freeze(
    *, project_root: Path, human_seed: str, runtime_identity: Mapping[str, Any],
    runtime_receipt: Mapping[str, Any], extra_review_materials: Sequence[Path],
) -> dict[str, Any]:
    root = project_root.resolve(strict=True)
    experiment = root / EXPERIMENT
    manifest = yaml.safe_load((experiment / "task-fixtures-v2.yaml").read_text(encoding="utf-8"))
    fixtures = [(row["id"], experiment / row["prompt_path"]) for row in manifest["fixtures"]]
    baseline = [experiment / "templates" / "baseline-v2.yaml"]
    registration = [experiment / relative for relative in FROZEN_REGISTRATION_MATERIALS]
    registration.extend(root / path for path in extra_review_materials)
    return build_cohort_freeze(
        cohort_id="self-bootstrap-effectiveness-v2", registration_root=root,
        fixtures=fixtures, baseline_materials=baseline, registration_materials=registration,
        human_supplied_seed=human_seed,
        runtime_identity=runtime_identity, runtime_identity_receipt=runtime_receipt,
    )
