from __future__ import annotations
import json
import math
import statistics
import hashlib
from pathlib import Path
from typing import Any, Mapping
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
INPUT = ROOT / "data" / "derived" / "adjudicated-v2.json"
OUTPUT = ROOT / "artifacts" / "results-v1.json"
SCHEMA = json.loads((ROOT / "schemas/derived-data-v2.schema.json").read_text(encoding="utf-8-sig"))


def canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def analyze(dataset: Mapping[str, Any]) -> dict[str, object]:
    errors = list(Draft202012Validator(SCHEMA).iter_errors(dataset))
    if errors:
        raise ValueError(f"derived-data schema violation: {errors[0].message}")
    unsigned = dict(dataset)
    claimed = unsigned.pop("dataset_sha256")
    if hashlib.sha256(canonical(unsigned)).hexdigest() != claimed:
        raise ValueError("derived dataset digest mismatch")
    cells = {}
    critical_count = 0
    for row in dataset["rows"]:
        key = (row["block"], row["arm"])
        if key in cells:
            raise ValueError("duplicate ITT cell")
        if row["evaluable"] != (row["censor_status"] == "not-censored"):
            raise ValueError("evaluable/censor contradiction")
        if row["evaluable"] and (
            row["adjudicated_total"] is None or row["task_elapsed_seconds"] is None
        ):
            raise ValueError("evaluable endpoint missing")
        if not row["evaluable"] and row["adjudicated_total"] is not None:
            raise ValueError("setup-censored quality must remain null")
        critical_count += row["critical_violation_count"]
        cells[key] = row
    differences = []
    ratios = []
    missing = []
    for block in range(1, 13):
        pair = [cells.get((block, a)) for a in ("control", "treatment")]
        if any(r is None or not r["evaluable"] for r in pair):
            missing.append(block)
            continue
        control, treatment = pair
        cq, tq = float(control["adjudicated_total"]), float(treatment["adjudicated_total"])
        ce, te = float(control["task_elapsed_seconds"]), float(treatment["task_elapsed_seconds"])
        if not all(math.isfinite(v) for v in (cq, tq, ce, te)) or ce <= 0 or te <= 0:
            raise ValueError("evaluable endpoint must be finite and elapsed positive")
        differences.append(tq - cq)
        ratios.append(te / ce)
    count = len(differences)
    mean = statistics.fmean(differences) if count else None
    median = statistics.median(ratios) if count else None
    supported = bool(
        count == 12
        and critical_count == 0
        and mean is not None
        and median is not None
        and mean >= 0.5
        and median <= 1.25
    )
    conclusion = (
        "inconclusive"
        if count != 12 or critical_count
        else ("supported-for-frozen-fixtures" if supported else "falsified")
    )
    return {
        "schema_version": 1,
        "analysis": "preregistered-linked-itt-ordinal-1",
        "source_dataset_sha256": claimed,
        "evaluable_itt_pairs": count,
        "missing_pair_blocks": missing,
        "mean_quality_difference": mean,
        "median_total_elapsed_time_ratio": median,
        "critical_violation_count": critical_count,
        "joint_claim": conclusion,
        "acceptance_supported": supported,
        "limitations": [
            "Inference is limited to the frozen fixtures and baseline revision.",
            "Host-observed unsigned labels do not prove provider identity, model build, or isolation enforcement.",
        ],
    }


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(
            "No adjudicated-v2.json; authorized ingestion, blinding, and adjudication remain blocked."
        )
    try:
        result = analyze(json.loads(INPUT.read_text(encoding="utf-8")))
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid adjudicated observations: {exc}") from exc
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
