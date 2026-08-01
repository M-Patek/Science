from __future__ import annotations
import copy
import hashlib
import pytest
from test_preparation_contracts import load
from test_derived_ingestion_contract import build

ANALYZE = load("analyze.py")


def prepared(*, exact=False, setup=False, critical=0):
    data, _ = build(0 if setup else None)
    for row in data["rows"]:
        if row["evaluable"]:
            row["adjudicated_total"] = 6 + (
                1 if row["arm"] == "treatment" and (not exact or row["block"] <= 6) else 0
            )
            row["task_elapsed_seconds"] = 120 if row["arm"] == "treatment" else 100
        row["critical_violation_count"] = (
            critical if row["block"] == 1 and row["arm"] == "control" else 0
        )
    data.pop("dataset_sha256")
    data["dataset_sha256"] = hashlib.sha256(ANALYZE.canonical(data)).hexdigest()
    return data


def test_analysis_accepts_only_linked_dataset_and_supports_joint_rule():
    result = ANALYZE.analyze(prepared())
    assert (
        result["evaluable_itt_pairs"] == 12
        and result["mean_quality_difference"] == 1
        and result["median_total_elapsed_time_ratio"] == 1.2
        and result["joint_claim"] == "supported-for-frozen-fixtures"
    )
    exact = ANALYZE.analyze(prepared(exact=True))
    assert (
        exact["mean_quality_difference"] == 0.5
        and exact["joint_claim"] == "supported-for-frozen-fixtures"
    )


def test_setup_censor_or_critical_is_inconclusive_and_outcome_rows_remain_itt():
    assert ANALYZE.analyze(prepared(setup=True))["joint_claim"] == "inconclusive"
    assert ANALYZE.analyze(prepared(critical=1))["joint_claim"] == "inconclusive"
    data = prepared()
    row = data["rows"][0]
    row["adjudicated_total"] = 0
    data.pop("dataset_sha256")
    data["dataset_sha256"] = hashlib.sha256(ANALYZE.canonical(data)).hexdigest()
    assert ANALYZE.analyze(data)["evaluable_itt_pairs"] == 12


def test_analysis_rejects_digest_substitution_duplicate_and_censor_contradiction():
    data = prepared()
    bad = copy.deepcopy(data)
    bad["freeze_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest mismatch"):
        ANALYZE.analyze(bad)
    bad = prepared()
    bad["rows"][1]["cell_id"] = bad["rows"][0]["cell_id"]
    bad["rows"][1]["block"] = bad["rows"][0]["block"]
    bad["rows"][1]["arm"] = bad["rows"][0]["arm"]
    bad.pop("dataset_sha256")
    bad["dataset_sha256"] = hashlib.sha256(ANALYZE.canonical(bad)).hexdigest()
    with pytest.raises(ValueError, match="duplicate"):
        ANALYZE.analyze(bad)
    bad = prepared()
    bad["rows"][0]["evaluable"] = False
    bad.pop("dataset_sha256")
    bad["dataset_sha256"] = hashlib.sha256(ANALYZE.canonical(bad)).hexdigest()
    with pytest.raises(ValueError, match="contradiction"):
        ANALYZE.analyze(bad)
