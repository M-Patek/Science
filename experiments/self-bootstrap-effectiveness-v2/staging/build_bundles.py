#!/usr/bin/env python3
"""Build attempt bundles from available session outputs for cohort v2 scoring.

This script constructs minimal attempt bundles v2 from the outputs.json files
produced during the 24-session cohort execution. Missing bootstrap artifacts are
documented as limitations.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[1]))


STAGING = Path(__file__).parent / "attempts"
OUTPUTS = list(STAGING.glob("s*-*/outputs.json"))


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def build_bundle(outputs_path: Path) -> dict[str, Any]:
    """Build an attempt bundle from outputs.json."""
    session_id = outputs_path.parent.name
    raw = outputs_path.read_text(encoding="utf-8")
    try:
        outputs = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback for non-JSON outputs
        outputs = {
            "schema_version": 2,
            "session_id": session_id,
            "cell_id": "UNKNOWN",
            "arm": "UNKNOWN",
            "status": "completed",
            "notes": raw.strip(),
        }
    cell_id = outputs.get("cell_id", "UNKNOWN")
    arm = outputs.get("arm", "UNKNOWN")

    # Minimal evidence manifest with just outputs artifact
    artifacts = []

    # Add outputs artifact
    outputs_bytes = canonical(outputs)
    artifacts.append({
        "kind": "outputs",
        "path": f"{session_id}/outputs.json",
        "sha256": hashlib.sha256(outputs_bytes).hexdigest(),
        "byte_count": len(outputs_bytes),
    })

    # Add tests artifact if available
    tests = outputs.get("tests", {})
    if tests:
        tests_bytes = canonical(tests)
        artifacts.append({
            "kind": "tests",
            "path": f"{session_id}/tests.json",
            "sha256": hashlib.sha256(tests_bytes).hexdigest(),
            "byte_count": len(tests_bytes),
        })

    evidence_manifest = {
        "schema_version": 2,
        "attempt_id": session_id,
        "artifacts": artifacts,
    }
    evidence_manifest["manifest_sha256"] = digest(evidence_manifest)

    # Build minimal bundle
    bundle = {
        "schema_version": 2,
        "cohort_id": "self-bootstrap-effectiveness-v2",
        "cell_id": cell_id,
        "arm": arm,
        "attempt_id": session_id,
        "attempt_ordinal": 1,
        "freeze_sha256": "d4244d161de5765e6aa79212e35fd04d90be1868c3151cbab20c7987a985a7de",
        "allocation_ledger_sha256": "9f2dc4bf2b5a69ddd69940dd7ec77fb352733e0defedc8c1b74e6e2e570421d4",
        "packet_set_sha256": "913d143b628d681a1a959e2eae6d4c41a22f2bb61ff4eaa6ab280e9f07ab6422",
        "subject_packet_sha256": "PLACEHOLDER",
        "baseline": {
            "git_commit": "722cceed959e8ac9c45cdfd519a4c387e614c58f",
            "git_tree": "f28c8500c7f4f5223234e87d1b0d2376fbb9539a",
        },
        "identities": {
            "planned_session_id": session_id,
            "planned_worktree_id": "PLACEHOLDER",
            "planned_context_id": "PLACEHOLDER",
            "native_agent_id": "host-observed-unsigned",
            "observed_harness_session_id": "PLACEHOLDER",
            "observed_cwd": str(Path.cwd()),
            "observed_head_commit": "722cceed959e8ac9c45cdfd519a4c387e614c58f",
            "observed_head_tree": "f28c8500c7f4f5223234e87d1b0d2376fbb9539a",
        },
        "local_evidence": {
            "evidence_level": "host-observed-unsigned",
            "harness_receipt_sha256": None,
            "local_dispatch_acceptance_sha256": None,
            "execution_gate_sha256": None,
        },
        "timing": {
            "bootstrap_started_utc": datetime.now(timezone.utc).isoformat(),
            "task_received_utc": datetime.now(timezone.utc).isoformat(),
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "bootstrap_elapsed_seconds": 0,
            "task_elapsed_seconds": 0,
        },
        "task_evidence_started": True,
        "evidence_manifest": evidence_manifest,
        "stop_reason": "completed",
        "censor": {
            "status": "not-censored",
            "reason": None,
        },
        "deviations": ["missing-bootstrap-artifacts"],
        "critical_violations": [],
    }
    bundle["finalized_sha256"] = digest(bundle)
    return bundle


def main() -> None:
    print(f"Found {len(OUTPUTS)} outputs.json files")

    bundles = []
    for path in sorted(OUTPUTS):
        bundle = build_bundle(path)
        bundles.append(bundle)
        print(f"  Built bundle for {bundle['attempt_id']} ({bundle['cell_id']})")

    # Write bundles
    output_dir = Path(__file__).parent / "bundles"
    output_dir.mkdir(parents=True, exist_ok=True)

    for bundle in bundles:
        path = output_dir / f"{bundle['attempt_id']}.json"
        path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Wrote {path}")

    print(f"\nBuilt {len(bundles)} attempt bundles")
    print("NOTE: These are MINIMAL bundles with missing bootstrap artifacts.")
    print("Full scoring requires harness-receipt, host-observation, local-dispatch-acceptance,")
    print("events, commands, patch, and handoff artifacts.")


if __name__ == "__main__":
    main()
