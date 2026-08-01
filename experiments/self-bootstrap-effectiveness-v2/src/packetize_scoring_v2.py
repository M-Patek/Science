from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas/blinded-scoring-packet-v2.schema.json").read_text(encoding="utf-8")
)
ATTEMPT_MANIFEST_SCHEMA = json.loads(
    (ROOT / "schemas/attempt-manifest-v2.schema.json").read_text(encoding="utf-8")
)
ATTEMPT_SCHEMA = json.loads(
    (ROOT / "schemas/attempt-bundle-v2.schema.json").read_text(encoding="utf-8")
)
EVIDENCE_SCHEMA = json.loads(
    (ROOT / "schemas/evidence-manifest-v2.schema.json").read_text(encoding="utf-8")
)
CUES = re.compile(
    r"(?i)\b(control|treatment|arm|solo|multi[- ]?agent|subagent|child agent|delegat(?:e|ion)|dispatch|envelope|handoff|scorer|reviewer|allocation|wave)\b"
)
KINDS = {"outputs": "acceptance", "patch": "diff", "tests": "tests"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _redact(text: str) -> tuple[str, int]:
    kept = []
    removed = 0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if CUES.search(line):
            removed += 1
        else:
            kept.append(line)
    result = "\n".join(kept)
    if CUES.search(result):
        raise ValueError("blinding disclosure remains after redaction")
    return result, removed


def build_scoring_packets(
    *,
    attempt_manifest: Mapping[str, Any],
    bundles: Iterable[Mapping[str, Any]],
    artifact_root: Path | None = None,
    artifact_reader: Callable[[str], bytes] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    errors = list(Draft202012Validator(ATTEMPT_MANIFEST_SCHEMA).iter_errors(attempt_manifest))
    if errors:
        raise ValueError(f"attempt manifest schema violation: {errors[0].message}")
    unsigned = dict(attempt_manifest)
    claimed = unsigned.pop("manifest_sha256")
    if digest(unsigned) != claimed:
        raise ValueError("attempt manifest digest mismatch")
    bundle_list = list(bundles)
    by_digest = {b.get("finalized_sha256"): b for b in bundle_list}
    entries = []
    packets = []
    expected = {e["bundle_sha256"] for e in attempt_manifest["entries"]}
    if (
        len(bundle_list) != 24
        or len(by_digest) != 24
        or len(expected) != 24
        or set(by_digest) != expected
    ):
        raise ValueError("scoring requires exact 24-attempt coverage with no surplus or duplicates")
    for bundle in bundle_list:
        errors = list(Draft202012Validator(ATTEMPT_SCHEMA).iter_errors(bundle))
        if errors:
            raise ValueError(f"attempt bundle schema violation: {errors[0].message}")
        unsigned = dict(bundle)
        claimed = unsigned.pop("finalized_sha256")
        if digest(unsigned) != claimed:
            raise ValueError("attempt bundle digest mismatch")
        evidence_manifest = bundle["evidence_manifest"]
        errors = list(Draft202012Validator(EVIDENCE_SCHEMA).iter_errors(evidence_manifest))
        if errors:
            raise ValueError(f"evidence manifest schema violation: {errors[0].message}")
        unsigned = dict(evidence_manifest)
        claimed = unsigned.pop("manifest_sha256")
        if digest(unsigned) != claimed:
            raise ValueError("evidence manifest digest mismatch")
    for entry in attempt_manifest["entries"]:
        bundle = by_digest.get(entry["bundle_sha256"])
        if (
            bundle is None
            or bundle["evidence_manifest"]["manifest_sha256"] != entry["evidence_manifest_sha256"]
        ):
            raise ValueError("attempt/evidence substitution")
        evidence = []
        removed = 0
        artifacts = {a["kind"]: a for a in bundle["evidence_manifest"]["artifacts"]}
        for kind, category in KINDS.items():
            row = artifacts.get(kind)
            if row is None:
                continue
            if artifact_reader is None:
                if artifact_root is None:
                    raise ValueError("source evidence retriever required")
                path = (artifact_root / row["path"]).resolve()
                root = artifact_root.resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise ValueError("source evidence not retrievable")
                raw = path.read_bytes()
            else:
                raw = artifact_reader(row["path"])
            if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("source evidence content mismatch")
            content, count = _redact(raw.decode("utf-8", errors="replace"))
            removed += count
            evidence.append(
                {
                    "category": category,
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "content": content,
                }
            )
        opaque = (
            "packet-"
            + hashlib.sha256(("opaque-scoring-v2\0" + entry["bundle_sha256"]).encode()).hexdigest()[
                :24
            ]
        )
        packet = {
            "schema_version": 2,
            "opaque_packet_id": opaque,
            "source_attempt_sha256": entry["bundle_sha256"],
            "source_evidence_manifest_sha256": entry["evidence_manifest_sha256"],
            "evidence": evidence,
            "limitations": [
                "Orchestration-bearing lines and non-rubric bootstrap artifacts are excluded deterministically.",
                "Missing retained evidence must lower the score under the frozen rubric.",
            ],
            "redaction_report": {
                "policy": "direct-and-orchestration-cues-v2",
                "removed_line_count": removed,
                "post_scan_disclosures": [],
            },
        }
        packet["packet_sha256"] = digest(packet)
        errors = list(Draft202012Validator(SCHEMA).iter_errors(packet))
        if errors:
            raise ValueError(errors[0].message)
        packets.append(packet)
        entries.append(
            {
                "opaque_packet_id": opaque,
                "packet_sha256": packet["packet_sha256"],
                "source_attempt_sha256": entry["bundle_sha256"],
            }
        )
    if len({e["opaque_packet_id"] for e in entries}) != 24:
        raise ValueError("opaque packet collision")
    manifest = {
        "schema_version": 2,
        "cohort_id": attempt_manifest["cohort_id"],
        "attempt_manifest_sha256": attempt_manifest["manifest_sha256"],
        "packet_count": 24,
        "entries": sorted(entries, key=lambda x: x["opaque_packet_id"]),
    }
    manifest["manifest_sha256"] = digest(manifest)
    return packets, manifest
