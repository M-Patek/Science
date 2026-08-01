from __future__ import annotations
import copy
import pytest
from test_preparation_contracts import load, materials
from test_attempt_contract import VERIFY, bind, bundle, finalized
from test_scoring_contract import score, adjudication

PACK = load("packetize_scoring_v2.py")
INGEST = load("ingest_adjudicated_v2.py")


def zero_adjudication(record):
    record = copy.deepcopy(record)
    record["resolution"]["criteria"] = [0, 0, 0, 0, 0]
    record["resolution"]["total_0_10"] = 0
    record["resolution_commitment_sha256"] = INGEST.digest(
        {
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
    )
    record["record_sha256"] = INGEST.digest(
        {k: v for k, v in record.items() if k != "record_sha256"}
    )
    return record


def lineage(*, setup_index=None, critical_index=None):
    store = {}
    freeze, ledger, ps = materials()
    bundles = []
    for i, p in enumerate(ps["packets"]):
        if i == setup_index:
            v = bundle(
                store,
                p,
                i + 1,
                stop="infrastructure-failure",
                censor="setup-censored",
                reason="pre-task-infrastructure-failure",
            )
        elif i == critical_index:
            v = bundle(
                store, p, i + 1, stop="critical-violation", critical=["scope-or-worktree-escape"]
            )
        else:
            v = bundle(store, p, i + 1)
        bundles.append(bind(v, ps))
    am = VERIFY.build_attempt_manifest(
        freeze=freeze,
        allocation_ledger=ledger,
        packet_set=ps,
        bundles=bundles,
        artifact_reader=store.__getitem__,
    )
    packets, pm = PACK.build_scoring_packets(
        attempt_manifest=am, bundles=bundles, artifact_reader=store.__getitem__
    )
    by_attempt = {p["source_attempt_sha256"]: p for p in packets}
    scores = []
    adjs = []
    for i, entry in enumerate(am["entries"]):
        packet = by_attempt[entry["bundle_sha256"]]
        cell = next(e for e in ledger["entries"] if e["cell_id"] == entry["cell_id"])
        a = score(packet, "scorer-a", "2026-07-13T00:01:00Z", "2026-07-13T00:02:00Z")
        b = score(packet, "scorer-b", "2026-07-13T00:01:30Z", "2026-07-13T00:02:30Z")
        scores.extend([a, b])
        adj = adjudication(packet, [a, b], cell["arm"])
        if next(b for b in bundles if b["finalized_sha256"] == entry["bundle_sha256"])[
            "critical_violations"
        ]:
            adj = zero_adjudication(adj)
        adjs.append(adj)
    return freeze, ledger, ps, am, packets, pm, bundles, scores, adjs, store


def invoke(values):
    freeze, ledger, ps, am, packets, pm, bundles, scores, adjs, store = values
    return INGEST.build_derived_dataset(
        freeze=freeze,
        allocation_ledger=ledger,
        packet_set=ps,
        attempt_manifest=am,
        scoring_packets=packets,
        scoring_packet_manifest=pm,
        bundles=bundles,
        scores=scores,
        adjudications=adjs,
        artifact_reader=store.__getitem__,
    )


def build(setup_index=None):
    values = lineage(setup_index=setup_index)
    return invoke(values), values


def test_controlled_ingestion_builds_exact_source_linked_cells_and_preserves_setup_censor():
    data = invoke(lineage())
    assert (
        data["row_count"] == 24
        and len({r["cell_id"] for r in data["rows"]}) == 24
        and all(r["evaluable"] for r in data["rows"])
    )
    censored = invoke(lineage(setup_index=0))
    row = next(r for r in censored["rows"] if not r["evaluable"])
    assert (
        row["adjudicated_total"] is None
        and row["task_elapsed_seconds"] is None
        and row["censor_status"] == "setup-censored"
    )


def test_ingestion_rejects_score_omission_arm_substitution_and_manifest_tampering():
    values = lineage()
    freeze, ledger, ps, am, packets, pm, bundles, scores, adjs, store = values
    with pytest.raises(ValueError, match="coverage"):
        invoke((freeze, ledger, ps, am, packets, pm, bundles, scores[:-1], adjs, store))
    bad = copy.deepcopy(adjs)
    bad[0]["arm_reveal"]["arm"] = (
        "treatment" if bad[0]["arm_reveal"]["arm"] == "control" else "control"
    )
    bad[0]["record_sha256"] = INGEST.digest(
        {k: v for k, v in bad[0].items() if k != "record_sha256"}
    )
    with pytest.raises(ValueError, match="arm mismatch"):
        invoke((freeze, ledger, ps, am, packets, pm, bundles, scores, bad, store))
    bad_am = copy.deepcopy(am)
    bad_am["freeze_sha256"] = "0" * 64
    bad_am["manifest_sha256"] = INGEST.digest(
        {k: v for k, v in bad_am.items() if k != "manifest_sha256"}
    )
    bad_pm = copy.deepcopy(pm)
    bad_pm["attempt_manifest_sha256"] = bad_am["manifest_sha256"]
    bad_pm["manifest_sha256"] = INGEST.digest(
        {k: v for k, v in bad_pm.items() if k != "manifest_sha256"}
    )
    with pytest.raises(ValueError, match="lineage substitution"):
        invoke((freeze, ledger, ps, bad_am, packets, bad_pm, bundles, scores, adjs, store))


@pytest.mark.parametrize(
    "field,value",
    [
        ("cell_id", "substituted-cell"),
        ("arm", "opposite-arm"),
        ("attempt_ordinal", 2),
        ("subject_packet_sha256", "0" * 64),
        ("freeze_sha256", "0" * 64),
        ("allocation_ledger_sha256", "0" * 64),
        ("packet_set_sha256", "0" * 64),
    ],
)
def test_ingestion_rejects_bundle_lineage_substitutions(field, value):
    values = list(lineage())
    bundles = copy.deepcopy(values[6])
    value = (
        ("control" if bundles[0]["arm"] == "treatment" else "treatment")
        if value == "opposite-arm"
        else value
    )
    bundles[0][field] = value
    finalized(bundles[0], "finalized_sha256")
    values[6] = bundles
    with pytest.raises(ValueError, match="lineage|omission"):
        invoke(tuple(values))


def test_critical_violation_forces_zero_adjudicated_score():
    values = list(lineage(critical_index=0))
    data = invoke(tuple(values))
    assert next(r for r in data["rows"] if r["critical_violation_count"])["adjudicated_total"] == 0
    adjs = copy.deepcopy(values[8])
    critical_bundle = next(b for b in values[6] if b["critical_violations"])
    entry = next(
        e for e in values[3]["entries"] if e["bundle_sha256"] == critical_bundle["finalized_sha256"]
    )
    packet_entry = next(
        e for e in values[5]["entries"] if e["source_attempt_sha256"] == entry["bundle_sha256"]
    )
    index = next(
        i for i, a in enumerate(adjs) if a["opaque_packet_id"] == packet_entry["opaque_packet_id"]
    )
    packet = next(p for p in values[4] if p["opaque_packet_id"] == packet_entry["opaque_packet_id"])
    group = [s for s in values[7] if s["opaque_packet_id"] == packet["opaque_packet_id"]]
    adjs[index] = adjudication(
        packet,
        group,
        next(e["arm"] for e in values[1]["entries"] if e["cell_id"] == entry["cell_id"]),
    )
    values[8] = adjs
    with pytest.raises(ValueError, match="score zero"):
        invoke(tuple(values))


def test_ingestion_rejects_surplus_duplicate_and_scoring_packet_digest_substitution():
    values = list(lineage())
    values[6] = values[6] + [copy.deepcopy(values[6][0])]
    with pytest.raises(ValueError, match="surplus|duplicate"):
        invoke(tuple(values))
    values = list(lineage())
    packets = copy.deepcopy(values[4])
    packets[0]["packet_sha256"] = "0" * 64
    values[4] = packets
    with pytest.raises(ValueError, match="coverage|mismatch"):
        invoke(tuple(values))
