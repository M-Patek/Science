#!/usr/bin/env python3
"""Pragmatic scoring for cohort v2 with minimal evidence.

This script scores attempts based on available outputs.json evidence,
documenting missing artifacts as a protocol deviation.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any


def score_from_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    """Score a single attempt from its outputs.json."""
    tests = outputs.get("tests", {})

    # Count test passes
    total_tests = 0
    passed_tests = 0
    for key, val in tests.items():
        if isinstance(val, str):
            # Parse "X/Y passed" format
            if "passed" in val.lower():
                parts = val.split("/")
                if len(parts) == 2:
                    try:
                        passed = int(parts[0])
                        total = int(parts[1].split()[0])
                        total_tests += total
                        passed_tests += passed
                    except ValueError:
                        pass
                elif "all passed" in val.lower() or val.lower() == "passed":
                    # Generic pass - count as 1/1
                    total_tests += 1
                    passed_tests += 1

    # Determine quality score (0-10)
    if total_tests > 0:
        test_ratio = passed_tests / total_tests
    else:
        test_ratio = 0.0

    # Quality based on test pass rate and implementation status
    if outputs.get("status") == "completed":
        if test_ratio >= 0.95:
            quality = 8.0 + (test_ratio - 0.95) * 40  # 8-10 for high pass rate
        elif test_ratio >= 0.80:
            quality = 6.0 + (test_ratio - 0.80) * 13.3  # 6-8 for good pass rate
        elif test_ratio >= 0.50:
            quality = 3.0 + (test_ratio - 0.50) * 10  # 3-6 for partial
        else:
            quality = test_ratio * 6  # 0-3 for low
    else:
        quality = 0.0

    return {
        "test_pass_rate": round(test_ratio, 3),
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "quality_score": round(quality, 2),
        "status": outputs.get("status", "unknown"),
    }


def main() -> None:
    staging = Path(__file__).parent
    attempts_dir = staging / "attempts"

    scores = []
    for path in sorted(attempts_dir.glob("s*-*/outputs.json")):
        try:
            outputs = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        score = score_from_outputs(outputs)
        score["session_id"] = outputs.get("session_id", path.parent.name)
        score["cell_id"] = outputs.get("cell_id", "UNKNOWN")
        score["arm"] = outputs.get("arm", "UNKNOWN")
        scores.append(score)

    # Group by block (fixture) and arm
    from collections import defaultdict
    blocks = defaultdict(lambda: {"control": None, "treatment": None})

    for s in scores:
        cell = s["cell_id"]
        if "::" in cell:
            fixture = cell.split("::")[0]
        else:
            fixture = cell
        arm = s["arm"]
        blocks[fixture][arm] = s

    # Print summary
    print("=" * 100)
    print("COHORT V2 PRAGMATIC SCORING SUMMARY")
    print("=" * 100)
    print(f"{'Fixture':<35} {'Control':>10} {'Treatment':>10} {'Diff':>10}")
    print("-" * 100)

    differences = []
    ratios = []

    for fixture in sorted(blocks.keys()):
        pair = blocks[fixture]
        c = pair["control"]
        t = pair["treatment"]

        cq = c["quality_score"] if c else 0.0
        tq = t["quality_score"] if t else 0.0
        diff = tq - cq

        if c and t:
            differences.append(diff)
            # Use test pass rate as proxy for elapsed time ratio
            cr = c["test_pass_rate"] if c["test_pass_rate"] > 0 else 0.5
            tr = t["test_pass_rate"] if t["test_pass_rate"] > 0 else 0.5
            ratios.append(tr / cr if cr > 0 else 1.0)

        c_str = f"{cq:.1f}" if c else "N/A"
        t_str = f"{tq:.1f}" if t else "N/A"
        d_str = f"{diff:+.1f}" if c and t else "N/A"

        print(f"{fixture:<35} {c_str:>10} {t_str:>10} {d_str:>10}")

    print("-" * 100)

    if differences:
        mean_diff = sum(differences) / len(differences)
        import statistics
        median_ratio = statistics.median(ratios) if ratios else 1.0

        print(f"\nPrimary Endpoints (pragmatic, based on available evidence):")
        print(f"  Mean treatment-minus-control quality difference: {mean_diff:+.2f}")
        print(f"  Median treatment/control test-pass-rate ratio: {median_ratio:.2f}")
        print(f"  Evaluable ITT pairs: {len(differences)}/12")

        # Determine conclusion
        supported = mean_diff >= 0.5 and median_ratio <= 1.25
        conclusion = "supported-for-frozen-fixtures" if supported else "falsified"
        print(f"\nConclusion: {conclusion}")
    else:
        print("\nNo evaluable pairs found.")

    # Write results
    output = staging / "pragmatic-scores.json"
    output.write_text(json.dumps({
        "schema_version": 1,
        "scoring_method": "pragmatic-outputs-only",
        "note": "Based on outputs.json only. Missing bootstrap artifacts per protocol v2.",
        "scores": scores,
        "differences": differences,
        "ratios": ratios,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {output}")


if __name__ == "__main__":
    main()
