from __future__ import annotations
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]


def _load(name: str, file: str):
    path = ROOT / "src" / file
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ALLOCATE = _load("allocate_v2_for_ingestion", "allocate_v2.py")
VERIFY = _load("verify_attempts_for_ingestion", "verify_attempts.py")
SCORE_SCHEMA = json.loads(
    (ROOT / "schemas/score-record-v2.schema.json").read_text(encoding="utf-8-sig")
)
ADJ_SCHEMA = json.loads(
    (ROOT / "schemas/adjudication-record-v2.schema.json").read_text(encoding="utf-8-sig")
)
DERIVED_SCHEMA = json.loads(
    (ROOT / "schemas/derived-data-v2.schema.json").read_text(encoding="utf-8-sig")
)
ATTEMPT_MANIFEST_SCHEMA = json.loads(
    (ROOT / "schemas/attempt-manifest-v2.schema.json").read_text(encoding="utf-8-sig")
)
SCORING_PACKET_SCHEMA = json.loads(
    (ROOT / "schemas/blinded-scoring-packet-v2.schema.json").read_text(encoding="utf-8-sig")
)
SCORING_MANIFEST_SCHEMA = json.loads(
    (ROOT / "schemas/scoring-packet-manifest-v2.schema.json").read_text(encoding="utf-8-sig")
)
MAXIMA = [3, 2, 2, 2, 1]


def canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(v: Any) -> str:
    return hashlib.sha256(canonical(v)).hexdigest()


def dt(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def checked(record: Mapping[str, Any], field: str, *, newline: bool = False) -> None:
    u = dict(record)
    claimed = u.pop(field)
    actual = hashlib.sha256(canonical(u) + (b"\n" if newline else b"")).hexdigest()
    if actual != claimed:
        raise ValueError(f"{field} mismatch")


def schema_check(schema: Mapping[str, Any], value: Mapping[str, Any], name: str) -> None:
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ValueError(f"{name} schema violation: {errors[0].message}")


def validate_score(record: Mapping[str, Any]) -> None:
    schema_check(SCORE_SCHEMA, record, "score")
    checked(record, "record_sha256")
    score = record["score"]
    criteria = score["criteria"]
    if any(v > m for v, m in zip(criteria, MAXIMA)) or sum(criteria) != score["total_0_10"]:
        raise ValueError("score criterion/total inconsistency")
    commitment = {
        k: record[k]
        for k in ("opaque_packet_id", "source_packet_sha256", "scorer_id", "score", "committed_at")
    }
    if digest(commitment) != record["score_commitment_sha256"]:
        raise ValueError("score commitment mismatch")
    if dt(record["arm_guess"]["recorded_at"]) <= dt(record["committed_at"]):
        raise ValueError("arm guess must follow score commitment")


def validate_adjudication(
    record: Mapping[str, Any],
    scores: list[Mapping[str, Any]],
    arm: str,
    *,
    critical_violation: bool = False,
) -> None:
    schema_check(ADJ_SCHEMA, record, "adjudication")
    checked(record, "record_sha256")
    if len(scores) != 2 or len({s["scorer_id"] for s in scores}) != 2:
        raise ValueError("two distinct scorers required")
    if set(record["score_record_sha256"]) != {s["record_sha256"] for s in scores} or set(
        record["scorer_ids"]
    ) != {s["scorer_id"] for s in scores}:
        raise ValueError("adjudication score linkage mismatch")
    if record["adjudicator_id"] in set(record["scorer_ids"]):
        raise ValueError("adjudicator must be distinct")
    if record["source_packet_sha256"] != scores[0]["source_packet_sha256"] or any(
        s["source_packet_sha256"] != record["source_packet_sha256"] for s in scores
    ):
        raise ValueError("source packet mismatch")
    resolution = record["resolution"]
    if (
        any(v > m for v, m in zip(resolution["criteria"], MAXIMA))
        or sum(resolution["criteria"]) != resolution["total_0_10"]
    ):
        raise ValueError("adjudication total inconsistency")
    if critical_violation and (
        resolution["criteria"] != [0, 0, 0, 0, 0] or resolution["total_0_10"] != 0
    ):
        raise ValueError("critical violation requires adjudicated score zero")
    commitment = {
        k: record[k]
        for k in (
            "opaque_packet_id",
            "source_packet_sha256",
            "score_record_sha256",
            "scorer_ids",
            "adjudicator_id",
            "resolution",
            "committed_at",
        )
    }
    if digest(commitment) != record["resolution_commitment_sha256"]:
        raise ValueError("adjudication resolution commitment mismatch")
    if dt(record["committed_at"]) <= max(dt(s["arm_guess"]["recorded_at"]) for s in scores):
        raise ValueError("adjudication must follow both committed blind guesses")
    if (
        dt(record["arm_reveal"]["recorded_at"]) <= dt(record["committed_at"])
        or record["arm_reveal"]["arm"] != arm
    ):
        raise ValueError("unblinding order or arm mismatch")


def build_derived_dataset(
    *,
    freeze: Mapping[str, Any],
    allocation_ledger: Mapping[str, Any],
    packet_set: Mapping[str, Any],
    attempt_manifest: Mapping[str, Any],
    scoring_packets: Iterable[Mapping[str, Any]],
    scoring_packet_manifest: Mapping[str, Any],
    bundles: Iterable[Mapping[str, Any]],
    scores: Iterable[Mapping[str, Any]],
    adjudications: Iterable[Mapping[str, Any]],
    artifact_root: Path | None = None,
    artifact_reader=None,
) -> dict[str, Any]:
    ALLOCATE.validate_packet_lineage(freeze, allocation_ledger, packet_set)
    schema_check(ATTEMPT_MANIFEST_SCHEMA, attempt_manifest, "attempt manifest")
    schema_check(SCORING_MANIFEST_SCHEMA, scoring_packet_manifest, "scoring packet manifest")
    checked(attempt_manifest, "manifest_sha256")
    checked(scoring_packet_manifest, "manifest_sha256")
    if (
        attempt_manifest["freeze_sha256"] != freeze["freeze_sha256"]
        or attempt_manifest["allocation_ledger_sha256"] != allocation_ledger["ledger_sha256"]
        or attempt_manifest["packet_set_sha256"] != packet_set["packet_set_sha256"]
        or attempt_manifest["baseline"] != allocation_ledger["baseline"]
        or scoring_packet_manifest["cohort_id"] != freeze["cohort_id"]
        or scoring_packet_manifest["attempt_manifest_sha256"] != attempt_manifest["manifest_sha256"]
    ):
        raise ValueError("manifest lineage substitution")
    allocation = {e["cell_id"]: e for e in allocation_ledger["entries"]}
    packet_set_map = {p["packet_sha256"]: p for p in packet_set["packets"]}
    attempts = {e["bundle_sha256"]: e for e in attempt_manifest["entries"]}
    bundle_list = list(bundles)
    bundle_map = {b.get("finalized_sha256"): b for b in bundle_list}
    scoring_packet_list = list(scoring_packets)
    scoring_packet_map = {p.get("packet_sha256"): p for p in scoring_packet_list}
    packet_by_attempt = {e["source_attempt_sha256"]: e for e in scoring_packet_manifest["entries"]}
    if (
        any(
            len(v) != 24
            for v in (
                allocation,
                packet_set_map,
                attempts,
                bundle_map,
                scoring_packet_map,
                packet_by_attempt,
            )
        )
        or len(bundle_list) != 24
        or len(scoring_packet_list) != 24
    ):
        raise ValueError(
            "each source manifest must have exact unique 24-cell coverage with no surplus or duplicate entries"
        )
    if {e["packet_sha256"] for e in scoring_packet_manifest["entries"]} != set(scoring_packet_map):
        raise ValueError("scoring packet manifest coverage mismatch")
    for scoring_packet in scoring_packet_list:
        schema_check(SCORING_PACKET_SCHEMA, scoring_packet, "scoring packet")
        checked(scoring_packet, "packet_sha256")
    score_groups: dict[str, list[Mapping[str, Any]]] = {}
    for s in scores:
        validate_score(s)
        score_groups.setdefault(s["opaque_packet_id"], []).append(s)
    adj_list = list(adjudications)
    adj_map = {a["opaque_packet_id"]: a for a in adj_list}
    if (
        any(len(v) != 2 for v in score_groups.values())
        or len(score_groups) != 24
        or len(adj_map) != 24
        or len(adj_list) != 24
    ):
        raise ValueError("exact two-score and one-adjudication coverage required")
    rows = []
    for bundle_sha, attempt in attempts.items():
        bundle = bundle_map.get(bundle_sha)
        packet = packet_by_attempt.get(bundle_sha)
        cell = allocation.get(attempt["cell_id"])
        if bundle is None or packet is None or cell is None:
            raise ValueError("derived lineage omission")
        subject_packet = packet_set_map.get(attempt["packet_sha256"])
        scoring_packet = scoring_packet_map.get(packet["packet_sha256"])
        if subject_packet is None or scoring_packet is None:
            raise ValueError("packet lineage omission")
        if any(
            (
                attempt["cell_id"] != subject_packet["cell_id"],
                attempt["arm"] != subject_packet["arm"],
                bundle.get("cell_id") != cell["cell_id"],
                bundle.get("arm") != cell["arm"],
                bundle.get("attempt_id") != attempt["attempt_id"],
                bundle.get("attempt_ordinal") != 1,
                bundle.get("subject_packet_sha256") != subject_packet["packet_sha256"],
                bundle.get("freeze_sha256") != freeze["freeze_sha256"],
                bundle.get("allocation_ledger_sha256") != allocation_ledger["ledger_sha256"],
                bundle.get("packet_set_sha256") != packet_set["packet_set_sha256"],
                bundle.get("baseline") != allocation_ledger["baseline"],
                scoring_packet.get("source_attempt_sha256") != bundle_sha,
                scoring_packet.get("opaque_packet_id") != packet["opaque_packet_id"],
            )
        ):
            raise ValueError("attempt, bundle, packet, or allocation lineage substitution")
        VERIFY.validate_attempt(
            bundle, subject_packet, artifact_root=artifact_root, artifact_reader=artifact_reader
        )
        group = score_groups.get(packet["opaque_packet_id"])
        adj = adj_map.get(packet["opaque_packet_id"])
        if group is None or adj is None or packet["packet_sha256"] != adj["source_packet_sha256"]:
            raise ValueError("scoring lineage substitution")
        critical = bool(bundle["critical_violations"])
        validate_adjudication(adj, group, cell["arm"], critical_violation=critical)
        censored = bundle["censor"]["status"] == "setup-censored"
        rows.append(
            {
                "cell_id": cell["cell_id"],
                "block": cell["block"],
                "arm": cell["arm"],
                "attempt_ordinal": 1,
                "attempt_id": attempt["attempt_id"],
                "bundle_sha256": bundle_sha,
                "packet_sha256": packet["packet_sha256"],
                "score_record_sha256": sorted(s["record_sha256"] for s in group),
                "adjudication_record_sha256": adj["record_sha256"],
                "evaluable": not censored,
                "adjudicated_total": None if censored else adj["resolution"]["total_0_10"],
                "task_elapsed_seconds": bundle["timing"]["task_elapsed_seconds"],
                "censor_status": bundle["censor"]["status"],
                "critical_violation_count": len(bundle["critical_violations"]),
            }
        )
    if len(rows) != 24 or len({r["cell_id"] for r in rows}) != 24:
        raise ValueError("derived dataset must preserve exact planned cells")
    result = {
        "schema_version": 2,
        "cohort_id": freeze["cohort_id"],
        "freeze_sha256": freeze["freeze_sha256"],
        "allocation_ledger_sha256": allocation_ledger["ledger_sha256"],
        "attempt_manifest_sha256": attempt_manifest["manifest_sha256"],
        "scoring_packet_manifest_sha256": scoring_packet_manifest["manifest_sha256"],
        "row_count": 24,
        "rows": sorted(rows, key=lambda r: r["cell_id"]),
    }
    result["dataset_sha256"] = digest(result)
    schema_check(DERIVED_SCHEMA, result, "derived dataset")
    return result
