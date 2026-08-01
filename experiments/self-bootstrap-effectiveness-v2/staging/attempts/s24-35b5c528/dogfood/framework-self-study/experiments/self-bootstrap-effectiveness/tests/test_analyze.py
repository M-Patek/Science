from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "src" / "analyze.py"
SPEC = importlib.util.spec_from_file_location("self_bootstrap_analyze", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _rows(*, difference: float = 1.0, critical: int = 0):
    rows = []
    for block in range(1, 13):
        for arm, score, elapsed in (("control", 6.0, 100.0), ("treatment", 6.0 + difference, 120.0)):
            rows.append({"block": str(block), "arm": arm, "attempt_ordinal": "1", "evaluable": "true", "adjudicated_total": str(score), "elapsed_seconds": str(elapsed), "critical_violation_count": str(critical if block == 1 and arm == "control" else 0)})
    return rows


def test_supported_requires_all_twelve_pairs_and_zero_critical_violations():
    result = MODULE.analyze(_rows())
    assert result["evaluable_itt_pairs"] == 12
    assert result["mean_quality_difference"] == 1.0
    assert result["median_total_elapsed_time_ratio"] == 1.2
    assert result["joint_claim"] == "supported"


def test_missing_pair_or_critical_violation_fails_closed():
    missing = _rows()[:-1]
    assert MODULE.analyze(missing)["joint_claim"] == "inconclusive"
    critical = MODULE.analyze(_rows(critical=1))
    assert critical["joint_claim"] == "inconclusive"
    assert critical["acceptance_supported"] is False
