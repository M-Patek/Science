from __future__ import annotations
import copy
import hashlib
import pytest
from test_preparation_contracts import load, materials
from test_attempt_contract import VERIFY, bind, bundle, finalized

PACK = load("packetize_scoring_v2.py")
INGEST = load("ingest_adjudicated_v2.py")


def scoring_inputs():
    store = {}
    freeze, ledger, ps = materials()
    bundles = [bind(bundle(store, p, i), ps) for i, p in enumerate(ps["packets"], 1)]
    for i, b in enumerate(bundles):
        for row in b["evidence_manifest"]["artifacts"]:
            if row["kind"] in {"outputs", "patch", "tests"}:
                raw = f"kept task evidence {i}\ncontrol delegation disclosure\n".encode()
                store[row["path"]] = raw
                row["sha256"] = hashlib.sha256(raw).hexdigest()
                row["byte_count"] = len(raw)
        finalized(b["evidence_manifest"], "manifest_sha256")
        finalized(b, "finalized_sha256")
    manifest = VERIFY.build_attempt_manifest(
        freeze=freeze,
        allocation_ledger=ledger,
        packet_set=ps,
        bundles=bundles,
        artifact_reader=store.__getitem__,
    )
    return manifest, bundles, store


def score(packet, scorer, commit, guess):
    body = {
        "criteria": [3, 2, 2, 2, 1],
        "total_0_10": 10,
        "missing_evidence": [],
        "evidence_references": ["tests"],
        "rationale": "fully supported",
    }
    r = {
        "schema_version": 2,
        "opaque_packet_id": packet["opaque_packet_id"],
        "source_packet_sha256": packet["packet_sha256"],
        "scorer_id": scorer,
        "score": body,
        "committed_at": commit,
        "score_commitment_sha256": "PENDING",
        "arm_guess": {"recorded_at": guess, "guess": "unknown", "confidence": 0.0},
    }
    r["score_commitment_sha256"] = INGEST.digest(
        {
            k: r[k]
            for k in (
                "opaque_packet_id",
                "source_packet_sha256",
                "scorer_id",
                "score",
                "committed_at",
            )
        }
    )
    r["record_sha256"] = INGEST.digest(r)
    return r


def adjudication(packet, scores, arm="control"):
    r = {
        "schema_version": 2,
        "opaque_packet_id": packet["opaque_packet_id"],
        "source_packet_sha256": packet["packet_sha256"],
        "score_record_sha256": [s["record_sha256"] for s in scores],
        "scorer_ids": [s["scorer_id"] for s in scores],
        "adjudicator_id": "adjudicator-c",
        "resolution": {"criteria": [3, 2, 2, 2, 1], "total_0_10": 10, "rationale": "agreement"},
        "committed_at": "2026-07-13T00:04:00Z",
        "resolution_commitment_sha256": "PENDING",
        "arm_reveal": {"recorded_at": "2026-07-13T00:05:00Z", "arm": arm},
    }
    r["resolution_commitment_sha256"] = INGEST.digest(
        {
            k: r[k]
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
    )
    r["record_sha256"] = INGEST.digest(r)
    return r


def test_packetization_is_deterministic_digest_checked_bijective_and_cue_free():
    manifest, bundles, store = scoring_inputs()
    packets, pm = PACK.build_scoring_packets(
        attempt_manifest=manifest, bundles=bundles, artifact_reader=store.__getitem__
    )
    packets2, pm2 = PACK.build_scoring_packets(
        attempt_manifest=manifest, bundles=bundles, artifact_reader=store.__getitem__
    )
    assert packets == packets2 and pm == pm2 and len(packets) == 24
    assert all(
        not PACK.CUES.search(e["content"])
        and hashlib.sha256(e["content"].encode()).hexdigest() == e["sha256"]
        for p in packets
        for e in p["evidence"]
    )
    with pytest.raises(ValueError, match="24-attempt"):
        PACK.build_scoring_packets(
            attempt_manifest=manifest, bundles=bundles[:-1], artifact_reader=store.__getitem__
        )
    bad = dict(store)
    bad[next(k for k in bad if k.endswith("/outputs.txt"))] = b"substituted"
    with pytest.raises(ValueError, match="content mismatch"):
        PACK.build_scoring_packets(
            attempt_manifest=manifest, bundles=bundles, artifact_reader=bad.__getitem__
        )
    with pytest.raises(ValueError, match="no surplus"):
        PACK.build_scoring_packets(
            attempt_manifest=manifest,
            bundles=bundles + [copy.deepcopy(bundles[0])],
            artifact_reader=store.__getitem__,
        )
    tampered = copy.deepcopy(manifest)
    tampered["freeze_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest mismatch"):
        PACK.build_scoring_packets(
            attempt_manifest=tampered, bundles=bundles, artifact_reader=store.__getitem__
        )


def test_score_commitment_independence_and_adjudication_unblinding_order_fail_closed():
    manifest, bundles, store = scoring_inputs()
    packet = PACK.build_scoring_packets(
        attempt_manifest=manifest, bundles=bundles, artifact_reader=store.__getitem__
    )[0][0]
    a = score(packet, "scorer-a", "2026-07-13T00:01:00Z", "2026-07-13T00:02:00Z")
    b = score(packet, "scorer-b", "2026-07-13T00:01:30Z", "2026-07-13T00:02:30Z")
    INGEST.validate_score(a)
    INGEST.validate_score(b)
    adj = adjudication(packet, [a, b])
    INGEST.validate_adjudication(adj, [a, b], "control")
    same = copy.deepcopy(b)
    same["scorer_id"] = "scorer-a"
    same["record_sha256"] = INGEST.digest({k: v for k, v in same.items() if k != "record_sha256"})
    bad = adjudication(packet, [a, same])
    with pytest.raises(ValueError, match="distinct|unique"):
        INGEST.validate_adjudication(bad, [a, same], "control")
    early = copy.deepcopy(adj)
    early["arm_reveal"]["recorded_at"] = "2026-07-13T00:03:00Z"
    early["record_sha256"] = INGEST.digest({k: v for k, v in early.items() if k != "record_sha256"})
    with pytest.raises(ValueError, match="unblinding"):
        INGEST.validate_adjudication(early, [a, b], "control")
    tampered = copy.deepcopy(a)
    tampered["score"]["total_0_10"] = 9
    tampered["record_sha256"] = INGEST.digest(
        {k: v for k, v in tampered.items() if k != "record_sha256"}
    )
    with pytest.raises(ValueError):
        INGEST.validate_score(tampered)
