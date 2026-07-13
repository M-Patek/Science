from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).parents[1]
INPUT = ROOT / "data" / "derived" / "adjudicated-v1.csv"
OUTPUT = ROOT / "artifacts" / "results-v1.json"
ARMS = {"control", "treatment"}


def _integer(row: dict[str, str], name: str) -> int:
    value = int(row[name])
    if str(value) != row[name].strip():
        raise ValueError(f"{name} must be a canonical integer")
    return value


def analyze(rows: list[dict[str, str]]) -> dict[str, object]:
    first: dict[tuple[int, str], dict[str, str]] = {}
    critical_count = 0
    for row in rows:
        block = _integer(row, "block")
        ordinal = _integer(row, "attempt_ordinal")
        arm = row["arm"]
        if block not in range(1, 13) or arm not in ARMS or ordinal != 1:
            raise ValueError("invalid block, arm, or attempt ordinal")
        critical = _integer(row, "critical_violation_count")
        if critical < 0:
            raise ValueError("critical_violation_count must be non-negative")
        critical_count += critical
        key = (block, arm)
        if key in first:
            raise ValueError(f"duplicate ITT cell: {key}")
        first[key] = row

    quality_differences: list[float] = []
    elapsed_ratios: list[float] = []
    missing_pairs: list[int] = []
    for block in range(1, 13):
        pair = [first.get((block, arm)) for arm in ("control", "treatment")]
        if any(row is None or row["evaluable"].lower() != "true" for row in pair):
            missing_pairs.append(block)
            continue
        control, treatment = pair
        assert control is not None and treatment is not None
        control_quality = float(control["adjudicated_total"])
        treatment_quality = float(treatment["adjudicated_total"])
        control_elapsed = float(control["elapsed_seconds"])
        treatment_elapsed = float(treatment["elapsed_seconds"])
        if not all(math.isfinite(value) for value in (control_quality, treatment_quality, control_elapsed, treatment_elapsed)):
            raise ValueError("quality and elapsed values must be finite")
        if not (0 <= control_quality <= 10 and 0 <= treatment_quality <= 10):
            raise ValueError("adjudicated_total must be within 0..10")
        if control_elapsed <= 0 or treatment_elapsed <= 0:
            raise ValueError("evaluable elapsed_seconds must be positive")
        quality_differences.append(treatment_quality - control_quality)
        elapsed_ratios.append(treatment_elapsed / control_elapsed)

    pair_count = len(quality_differences)
    mean_difference = statistics.fmean(quality_differences) if pair_count else None
    median_ratio = statistics.median(elapsed_ratios) if pair_count else None
    evaluable = pair_count == 12 and critical_count == 0
    supported = bool(evaluable and mean_difference is not None and median_ratio is not None and mean_difference >= 0.5 and median_ratio <= 1.25)
    if critical_count or pair_count != 12:
        conclusion = "inconclusive"
    elif supported:
        conclusion = "supported-for-frozen-fixtures"
    else:
        conclusion = "falsified"
    return {
        "schema_version": 1,
        "analysis": "preregistered-itt-ordinal-1",
        "evaluable_itt_pairs": pair_count,
        "missing_pair_blocks": missing_pairs,
        "mean_quality_difference": mean_difference,
        "median_total_elapsed_time_ratio": median_ratio,
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
        raise SystemExit("No adjudicated-v1.csv; authorized ingestion, blinding, and adjudication remain blocked.")
    with INPUT.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("No adjudicated observations; analysis cannot run.")
    try:
        result = analyze(rows)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid adjudicated observations: {exc}") from exc
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
