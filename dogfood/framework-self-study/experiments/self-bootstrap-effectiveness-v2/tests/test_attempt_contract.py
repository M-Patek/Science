from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "attempt-bundle-v2.schema.json").read_text(encoding="utf-8"))
H64 = "a" * 64
G40 = "b" * 40


def _bundle():
    return {
        "schema_version": 2,
        "attempt_id": "attempt-001",
        "opaque_cell_token": "opaque-token-0001",
        "attempt_ordinal": 1,
        "subject_packet_sha256": H64,
        "baseline": {"git_commit": G40, "git_tree": G40},
        "identities": {
            "planned_session_id": "planned-1", "planned_worktree_id": "worktree-1",
            "planned_context_id": "context-1", "native_agent_id": "native-1",
            "observed_harness_session_id": "harness-1", "observed_cwd": "subject-workspaces/one",
            "observed_head_commit": G40,
        },
        "local_evidence": {
            "evidence_level": "host-observed-unsigned", "harness_receipt_sha256": H64,
            "local_dispatch_acceptance_sha256": H64, "execution_gate_sha256": H64,
            "non_claims": ["provider_identity", "immutable_model_build", "prompt_identity",
                           "toolchain_completeness", "network_enforcement", "permission_enforcement",
                           "context_isolation", "absolute_worktree_isolation"],
        },
        "timing": {"task_received_utc": "2026-07-13T00:00:00Z", "ended_utc": "2026-07-13T00:01:00Z", "elapsed_seconds": 60},
        "evidence": {name: H64 for name in ("transcript_or_events_sha256", "command_log_sha256", "patch_sha256", "outputs_sha256", "tests_sha256", "handoff_sha256")},
        "stop_reason": "completed", "censor": {"status": "not-censored", "reason": None},
        "deviations": [], "critical_violations": [], "finalized_sha256": H64,
    }


def test_attempt_v2_requires_exact_ordinal_one_and_explicit_evidence():
    validator = Draft202012Validator(SCHEMA)
    assert list(validator.iter_errors(_bundle())) == []
    replacement = _bundle(); replacement["attempt_ordinal"] = 2
    assert list(validator.iter_errors(replacement))
    missing = copy.deepcopy(_bundle()); del missing["evidence"]["command_log_sha256"]
    assert list(validator.iter_errors(missing))
    missing_deviation = _bundle(); del missing_deviation["deviations"]
    assert list(validator.iter_errors(missing_deviation))
