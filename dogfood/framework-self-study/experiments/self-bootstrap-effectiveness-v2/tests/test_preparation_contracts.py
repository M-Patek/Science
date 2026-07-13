from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from science_repo.cohort_freeze import STATIC_RUNTIME_IDENTITY_FIELDS
from science_repo.subject_packets import build_subject_packet_set


EXPERIMENT = Path(__file__).parents[1]
PROJECT = EXPERIMENT.parents[1]


def _load(name: str):
    path = EXPERIMENT / "src" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FREEZE = _load("freeze_v2.py")
ATTEMPTS = _load("verify_attempts.py")
H64 = "a" * 64
G40 = "b" * 40


def _freeze():
    identity = {key: f"declared-{key}" for key in STATIC_RUNTIME_IDENTITY_FIELDS}
    encoded = (json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    receipt = {"receipt_id": "design-test", "authority_id": "unsigned-local-test",
               "source": "test-declaration", "issued_at": "2026-07-13T00:00:00Z",
               "identity_sha256": hashlib.sha256(encoded).hexdigest()}
    return FREEZE.build_v2_freeze(project_root=PROJECT, human_seed="pre-outcome-test-seed",
        runtime_identity=identity, runtime_receipt=receipt, extra_review_materials=[])


def _bundle(packet, index):
    value = {
        "schema_version": 2, "attempt_id": f"attempt-{index:02d}",
        "opaque_cell_token": f"opaque-token-{index:04d}", "attempt_ordinal": 1,
        "subject_packet_sha256": packet["packet_sha256"],
        "baseline": {"git_commit": G40, "git_tree": G40},
        "identities": {
            "planned_session_id": packet["session_id"], "planned_worktree_id": packet["worktree_id"],
            "planned_context_id": packet["context_id"], "native_agent_id": f"native-{index:02d}",
            "observed_harness_session_id": f"harness-{index:02d}",
            "observed_cwd": packet["workspace_contract"]["cwd"], "observed_head_commit": G40,
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
        "deviations": [], "critical_violations": [],
    }
    value["finalized_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return value


def test_v2_freeze_binds_all_declared_design_materials_and_matches_contract():
    freeze = _freeze()
    schema = json.loads((PROJECT / "schemas" / "cohort-freeze.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(freeze)) == []
    frozen_paths = {row["path"] for row in freeze["registration_materials"]}
    expected = {(FREEZE.EXPERIMENT / name).as_posix() for name in FREEZE.FROZEN_REGISTRATION_MATERIALS}
    assert expected <= frozen_paths
    assert [row["path"] for row in freeze["baseline_materials"]] == [
        "experiments/self-bootstrap-effectiveness-v2/templates/baseline-v2.yaml"
    ]
    assert len(freeze["fixtures"]) == 12 and freeze["dispatch_allowed"] is False


def test_v2_attempt_manifest_is_exact_packet_bijection_and_rejects_schema_drift():
    packet_set = build_subject_packet_set(freeze=_freeze(), source_root=PROJECT)
    bundles = [_bundle(packet, index) for index, packet in enumerate(packet_set["packets"], 1)]
    manifest = ATTEMPTS.build_attempt_manifest(packet_set, bundles)
    assert manifest["attempt_count"] == 24 and len(manifest["entries"]) == 24
    with __import__("pytest").raises(ValueError, match="24-cell"):
        ATTEMPTS.build_attempt_manifest(packet_set, bundles[:-1])
    bad = copy.deepcopy(bundles); bad[0]["attempt_ordinal"] = 2
    with __import__("pytest").raises(ValueError, match="schema violation"):
        ATTEMPTS.build_attempt_manifest(packet_set, bad)
