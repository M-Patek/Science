import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "dogfood/framework-self-study/experiments/framework-onboarding/src/run.py"
)
SPEC = importlib.util.spec_from_file_location("framework_onboarding_analysis", MODULE_PATH)
analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(analysis)


def _rows():
    rows = []
    for task_id in analysis.TASK_IDS:
        for repeat in range(3):
            rows.append(
                {
                    "session_id": f"{task_id}-{repeat}",
                    "task_id": task_id,
                    "censor_status": "uncensored",
                    "censor_reason": "",
                    "protocol_deviation": "no",
                    "deviation_reason": "",
                    "scorer_1_decision": "pass",
                    "scorer_2_decision": "pass",
                    "adjudicated_decision": "pass",
                    "critical_protocol_violations": "0",
                    "onboarding_tokens_status": "measured",
                    "onboarding_tokens": "1200",
                }
            )
    return rows


def test_balanced_stratified_analysis():
    result = analysis.analyze_rows(_rows())
    assert result["sessions"] == 15
    assert result["task_success_rate"] == 1.0
    assert set(result["task_counts"].values()) == {3}
    assert result["onboarding_token_claim"] == "evaluable"


def test_missing_tokens_make_only_token_claim_inconclusive():
    rows = _rows()
    rows[0]["onboarding_tokens_status"] = "unavailable"
    rows[0]["onboarding_tokens"] = ""
    result = analysis.analyze_rows(rows)
    assert result["task_success_rate"] == 1.0
    assert result["estimated_onboarding_tokens"] is None
    assert result["onboarding_token_claim"] == "inconclusive"


def test_empty_or_unbalanced_observations_are_blocked():
    with pytest.raises(ValueError, match="No observations"):
        analysis.analyze_rows([])
    with pytest.raises(ValueError, match="exactly 15"):
        analysis.analyze_rows(_rows()[:-1])
