from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "attempt-bundle-v2.schema.json").read_text(encoding="utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_attempt_manifest(packet_set: dict[str, Any], bundles: Iterable[dict[str, Any]]) -> dict[str, Any]:
    packets = packet_set.get("packets", [])
    if packet_set.get("packet_count") != 24 or len(packets) != 24:
        raise ValueError("packet set must contain exactly 24 packets")
    by_digest = {packet.get("packet_sha256"): packet for packet in packets}
    if len(by_digest) != 24 or None in by_digest:
        raise ValueError("packet digests must be unique and present")

    validator = Draft202012Validator(SCHEMA)
    entries = []
    used_packets: set[str] = set()
    unique: dict[str, set[str]] = {name: set() for name in (
        "attempt_id", "planned_session_id", "planned_worktree_id", "planned_context_id",
        "native_agent_id", "observed_harness_session_id",
    )}
    for bundle in bundles:
        errors = sorted(validator.iter_errors(bundle), key=lambda error: list(error.path))
        if errors:
            raise ValueError(f"attempt schema violation: {errors[0].message}")
        unsigned = dict(bundle); claimed = unsigned.pop("finalized_sha256")
        if claimed != _sha(unsigned):
            raise ValueError("attempt finalized_sha256 mismatch")
        digest = bundle["subject_packet_sha256"]
        packet = by_digest.get(digest)
        if packet is None or digest in used_packets:
            raise ValueError("attempt-to-packet coverage is missing or duplicated")
        used_packets.add(digest)
        identities = bundle["identities"]
        expected = {
            "planned_session_id": packet["session_id"],
            "planned_worktree_id": packet["worktree_id"],
            "planned_context_id": packet["context_id"],
        }
        if any(identities[name] != value for name, value in expected.items()):
            raise ValueError("attempt planned identity does not match packet")
        if identities["observed_head_commit"] != bundle["baseline"]["git_commit"]:
            raise ValueError("attempt observed HEAD does not match bundle baseline")
        values = {"attempt_id": bundle["attempt_id"], **{name: identities[name] for name in unique if name != "attempt_id"}}
        for name, value in values.items():
            if value in unique[name]:
                raise ValueError(f"duplicate attempt identity: {name}")
            unique[name].add(value)
        entries.append({
            "cell_id": packet["cell_id"], "attempt_id": bundle["attempt_id"],
            "packet_sha256": digest, "bundle_sha256": claimed,
        })
    if len(entries) != 24 or used_packets != set(by_digest):
        raise ValueError("attempt manifest must be a 24-cell packet bijection")
    result = {"schema_version": 2, "cohort_id": packet_set["cohort_id"],
              "attempt_count": 24, "entries": sorted(entries, key=lambda row: row["cell_id"])}
    result["manifest_sha256"] = _sha(result)
    return result
