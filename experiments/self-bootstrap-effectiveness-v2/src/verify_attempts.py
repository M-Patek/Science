from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]
ATTEMPT_SCHEMA = json.loads(
    (ROOT / "schemas/attempt-bundle-v2.schema.json").read_text(encoding="utf-8-sig")
)
EVIDENCE_SCHEMA = json.loads(
    (ROOT / "schemas/evidence-manifest-v2.schema.json").read_text(encoding="utf-8-sig")
)


def _load_allocate():
    path = ROOT / "src" / "allocate_v2.py"
    spec = importlib.util.spec_from_file_location("allocate_v2_for_attempt_verifier", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ALLOCATE = _load_allocate()
ATTEMPT_MANIFEST_SCHEMA = json.loads(
    (ROOT / "schemas" / "attempt-manifest-v2.schema.json").read_text(encoding="utf-8")
)
ALL_ARTIFACTS = {
    "harness-receipt",
    "host-observation",
    "local-dispatch-acceptance",
    "events",
    "commands",
    "patch",
    "outputs",
    "tests",
    "handoff",
    "execution-gate",
}
SETUP_ARTIFACTS = {
    "harness-receipt",
    "host-observation",
    "local-dispatch-acceptance",
    "execution-gate",
}
TASK_ARTIFACTS = ALL_ARTIFACTS - SETUP_ARTIFACTS


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _check_digest(value: Mapping[str, Any], field: str, *, newline: bool = False) -> None:
    unsigned = dict(value)
    claimed = unsigned.pop(field)
    if (
        claimed
        != hashlib.sha256(canonical_bytes(unsigned) + (b"\n" if newline else b"")).hexdigest()
    ):
        raise ValueError(f"{field} mismatch")


def validate_attempt(
    bundle: Mapping[str, Any],
    packet: Mapping[str, Any],
    *,
    artifact_root: Path | None = None,
    artifact_reader: Callable[[str], bytes] | None = None,
) -> None:
    errors = sorted(
        Draft202012Validator(ATTEMPT_SCHEMA, format_checker=FormatChecker()).iter_errors(bundle),
        key=lambda e: list(e.path),
    )
    if errors:
        raise ValueError(f"attempt schema violation: {errors[0].message}")
    manifest = bundle["evidence_manifest"]
    evidence_errors = list(Draft202012Validator(EVIDENCE_SCHEMA).iter_errors(manifest))
    if evidence_errors:
        raise ValueError(f"evidence manifest schema violation: {evidence_errors[0].message}")
    _check_digest(manifest, "manifest_sha256")
    _check_digest(bundle, "finalized_sha256")
    if manifest["attempt_id"] != bundle["attempt_id"]:
        raise ValueError("evidence manifest attempt mismatch")
    expected = {
        "cohort_id": packet["cohort_id"],
        "cell_id": packet["cell_id"],
        "arm": packet["arm"],
        "freeze_sha256": packet["freeze_sha256"],
        "allocation_ledger_sha256": packet["allocation_ledger_sha256"],
        "subject_packet_sha256": packet["packet_sha256"],
        "baseline": packet["baseline"],
    }
    if any(bundle[name] != value for name, value in expected.items()):
        raise ValueError("attempt packet/freeze/allocation/baseline binding mismatch")
    identities = bundle["identities"]
    for name, packet_name in (
        ("planned_session_id", "session_id"),
        ("planned_worktree_id", "worktree_id"),
        ("planned_context_id", "context_id"),
    ):
        if identities[name] != packet[packet_name]:
            raise ValueError("attempt planned identity mismatch")
    if (
        identities["observed_head_commit"] != packet["baseline"]["git_commit"]
        or identities["observed_head_tree"] != packet["baseline"]["git_tree"]
    ):
        raise ValueError("observed commit/tree does not match frozen baseline")
    timing, censor = bundle["timing"], bundle["censor"]
    start, end = _dt(timing["bootstrap_started_utc"]), _dt(timing["ended_utc"])
    if end < start:
        raise ValueError("negative bootstrap interval")
    if censor["status"] == "setup-censored":
        if (
            censor["reason"] is None
            or timing["task_received_utc"] is not None
            or timing["task_elapsed_seconds"] is not None
            or bundle["task_evidence_started"]
        ):
            raise ValueError("setup censor timing/evidence contradiction")
        if timing["bootstrap_elapsed_seconds"] != (end - start).total_seconds():
            raise ValueError("bootstrap timestamp arithmetic mismatch")
        if (
            bundle["stop_reason"] not in {"explicit-block", "infrastructure-failure"}
            or bundle["critical_violations"]
        ):
            raise ValueError("setup censor stop/critical contradiction")
    else:
        if (
            censor["reason"] is not None
            or timing["task_received_utc"] is None
            or timing["task_elapsed_seconds"] is None
            or not bundle["task_evidence_started"]
        ):
            raise ValueError("outcome timing/censor contradiction")
        received = _dt(timing["task_received_utc"])
        if not start <= received <= end:
            raise ValueError("timestamp order contradiction")
        if (
            timing["bootstrap_elapsed_seconds"] != (received - start).total_seconds()
            or timing["task_elapsed_seconds"] != (end - received).total_seconds()
        ):
            raise ValueError("timestamp arithmetic mismatch")
        if bundle["stop_reason"] == "timeout" and timing["task_elapsed_seconds"] != 5400:
            raise ValueError("timeout must occur at 5400 seconds")
        if bundle["stop_reason"] != "timeout" and timing["task_elapsed_seconds"] >= 5400:
            raise ValueError("non-timeout may not reach wall-clock limit")
    critical = bundle["critical_violations"]
    if (bundle["stop_reason"] == "critical-violation") != bool(critical):
        raise ValueError("critical stop/taxonomy contradiction")
    artifacts = manifest["artifacts"]
    kinds = [row["kind"] for row in artifacts]
    if len(kinds) != len(set(kinds)):
        raise ValueError("evidence artifact kinds duplicated")
    if censor["status"] == "setup-censored":
        if not set(kinds) <= SETUP_ARTIFACTS:
            raise ValueError("setup-censored attempt contains prohibited task evidence")
    elif set(kinds) != ALL_ARTIFACTS:
        raise ValueError("outcome evidence artifact coverage must be exact")
    by_kind = {row["kind"]: row["sha256"] for row in artifacts}
    links = {
        "harness_receipt_sha256": "harness-receipt",
        "local_dispatch_acceptance_sha256": "local-dispatch-acceptance",
        "execution_gate_sha256": "execution-gate",
    }
    for field, kind in links.items():
        claimed = bundle["local_evidence"][field]
        if claimed is not None and by_kind.get(kind) != claimed:
            raise ValueError("local evidence digest/manifest contradiction")
        if censor["status"] == "not-censored" and claimed is None:
            raise ValueError("outcome attempt local evidence may not be null")
        if claimed is None and kind in by_kind:
            raise ValueError("unclaimed setup evidence artifact")
    if artifact_reader is None:
        if artifact_root is None:
            raise ValueError("an evidence artifact retriever is required")
        root = artifact_root.resolve()

        def artifact_reader(relative: str) -> bytes:
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("evidence artifact is not retrievable")
            return path.read_bytes()

    for row in artifacts:
        try:
            content = artifact_reader(row["path"])
        except (OSError, KeyError):
            raise ValueError("evidence artifact is not retrievable")
        if (
            len(content) != row["byte_count"]
            or hashlib.sha256(content).hexdigest() != row["sha256"]
        ):
            raise ValueError("evidence artifact content mismatch")


def build_attempt_manifest(
    *,
    freeze: Mapping[str, Any],
    allocation_ledger: Mapping[str, Any],
    packet_set: Mapping[str, Any],
    bundles: Iterable[Mapping[str, Any]],
    artifact_root: Path | None = None,
    artifact_reader: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    ALLOCATE.validate_packet_lineage(freeze, allocation_ledger, packet_set)
    packets = {row["packet_sha256"]: row for row in packet_set["packets"]}
    if len(packets) != 24 or packet_set["cohort_id"] != freeze["cohort_id"]:
        raise ValueError("packet set must be exact expected cohort")
    entries = []
    used = set()
    identities = {
        name: set()
        for name in (
            "attempt_id",
            "native_agent_id",
            "observed_harness_session_id",
            "planned_session_id",
            "planned_worktree_id",
            "planned_context_id",
        )
    }
    for bundle in bundles:
        packet = packets.get(bundle.get("subject_packet_sha256"))
        if packet is None or packet["packet_sha256"] in used:
            raise ValueError("attempt-to-packet coverage missing or duplicated")
        if bundle.get("packet_set_sha256") != packet_set["packet_set_sha256"]:
            raise ValueError("attempt packet-set substitution")
        validate_attempt(
            bundle, packet, artifact_root=artifact_root, artifact_reader=artifact_reader
        )
        used.add(packet["packet_sha256"])
        values = {
            "attempt_id": bundle["attempt_id"],
            **{k: bundle["identities"][k] for k in identities if k != "attempt_id"},
        }
        for k, v in values.items():
            if v in identities[k]:
                raise ValueError(f"duplicate attempt identity: {k}")
            identities[k].add(v)
        entries.append(
            {
                "cell_id": packet["cell_id"],
                "arm": packet["arm"],
                "attempt_id": bundle["attempt_id"],
                "packet_sha256": packet["packet_sha256"],
                "bundle_sha256": bundle["finalized_sha256"],
                "evidence_manifest_sha256": bundle["evidence_manifest"]["manifest_sha256"],
            }
        )
    if len(entries) != 24 or used != set(packets):
        raise ValueError("attempt manifest must be a 24-cell packet bijection")
    result = {
        "schema_version": 2,
        "cohort_id": freeze["cohort_id"],
        "freeze_sha256": freeze["freeze_sha256"],
        "allocation_ledger_sha256": allocation_ledger["ledger_sha256"],
        "packet_set_sha256": packet_set["packet_set_sha256"],
        "baseline": dict(allocation_ledger["baseline"]),
        "attempt_count": 24,
        "entries": sorted(entries, key=lambda r: r["cell_id"]),
    }
    result["manifest_sha256"] = digest(result)
    errors = list(Draft202012Validator(ATTEMPT_MANIFEST_SCHEMA).iter_errors(result))
    if errors:
        raise ValueError(f"attempt manifest schema violation: {errors[0].message}")
    return result
