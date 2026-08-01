from __future__ import annotations
import copy
import hashlib
from pathlib import Path
import pytest
import yaml
from test_preparation_contracts import ALLOC, EXPERIMENT, materials


def inputs():
    f, ledger, _ = materials()
    fixtures = yaml.safe_load((EXPERIMENT / "task-fixtures-v2.yaml").read_text())["fixtures"]
    policies = {a: EXPERIMENT / "templates" / f"arm-{a}-v2.yaml" for a in ("control", "treatment")}
    return f, ledger, fixtures, policies


def test_allocation_is_reproducible_with_explicit_ties_and_eight_waves():
    _, ledger, _, _ = inputs()
    entries = ledger["entries"]
    assert [e["execution_order"] for e in entries] == list(range(1, 25))
    assert [sum(e["wave"] == w for e in entries) for w in range(1, 9)] == [3] * 8
    assert entries == sorted(entries, key=lambda e: (e["rank_sha256"], e["cell_id"]))
    assert ledger["seed_sha256"] == hashlib.sha256(b"pre-outcome-test-seed").hexdigest()


def test_allocation_rejects_seed_baseline_and_frozen_assignment_substitution():
    f, ledger, fixtures, policies = inputs()
    baseline = ledger["baseline"]
    with pytest.raises(ValueError, match="seed"):
        ALLOC.build_allocation_ledger(
            freeze=f,
            fixtures=fixtures,
            seed="different",
            arm_policy_files=policies,
            baseline=baseline,
        )
    bad_baseline = dict(baseline)
    bad_baseline["git_tree"] = "0" * 40
    with pytest.raises(ValueError, match="pinned baseline"):
        ALLOC.build_allocation_ledger(
            freeze=f,
            fixtures=fixtures,
            seed="pre-outcome-test-seed",
            arm_policy_files=policies,
            baseline=bad_baseline,
        )
    bad = copy.deepcopy(f)
    bad["assignment_ledger"][0], bad["assignment_ledger"][1] = (
        bad["assignment_ledger"][1],
        bad["assignment_ledger"][0],
    )
    bad.pop("freeze_sha256")
    bad["freeze_sha256"] = hashlib.sha256(ALLOC.canonical_bytes(bad) + b"\n").hexdigest()
    with pytest.raises(ValueError, match="reproduce"):
        ALLOC.build_allocation_ledger(
            freeze=bad,
            fixtures=fixtures,
            seed="pre-outcome-test-seed",
            arm_policy_files=policies,
            baseline=baseline,
        )


def test_policy_digests_are_computed_from_exact_frozen_bytes_and_drift_is_rejected(monkeypatch):
    f, ledger, fixtures, policies = inputs()
    assert {e["arm_policy_sha256"] for e in ledger["entries"]} == {
        hashlib.sha256(p.read_bytes()).hexdigest() for p in policies.values()
    }
    wrong = dict(policies)
    wrong["control"] = policies["treatment"]
    with pytest.raises(ValueError, match="path mismatch"):
        ALLOC.build_allocation_ledger(
            freeze=f,
            fixtures=fixtures,
            seed="pre-outcome-test-seed",
            arm_policy_files=wrong,
            baseline=ledger["baseline"],
        )
    original = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda p: original(p) + b"\nDRIFT" if p == policies["control"] else original(p),
    )
    with pytest.raises(ValueError, match="frozen registration"):
        ALLOC.build_allocation_ledger(
            freeze=f,
            fixtures=fixtures,
            seed="pre-outcome-test-seed",
            arm_policy_files=policies,
            baseline=ledger["baseline"],
        )


def test_bound_packets_materialize_exact_policy_tools_and_fixture_scope():
    _, ledger, packets = materials()
    by = {e["cell_id"]: e for e in ledger["entries"]}
    for packet in packets["packets"]:
        entry = by[packet["cell_id"]]
        assert (
            hashlib.sha256(packet["arm_policy"]["content"].encode()).hexdigest()
            == entry["arm_policy_sha256"]
        )
        assert packet["tools"] == entry["tools"]
        assert packet["write_scope"] == entry["write_scope"]
        assert packet["inputs"]["arm_policy_files"] == [
            {"source_path": entry["arm_policy_path"], "sha256": entry["arm_policy_sha256"]}
        ]


def test_packet_lineage_rejects_recomputed_policy_input_substitution():
    f, ledger, packets = materials()
    bad = copy.deepcopy(packets)
    packet = bad["packets"][0]
    packet["inputs"]["arm_policy_files"][0]["sha256"] = "0" * 64
    packet.pop("packet_sha256")
    packet["packet_sha256"] = ALLOC.digest(packet)
    bad.pop("packet_set_sha256")
    bad["packet_set_sha256"] = ALLOC.digest(bad)
    with pytest.raises(ValueError, match="policy input binding"):
        ALLOC.validate_packet_lineage(f, ledger, bad)


def test_lineage_rejects_rehashed_policy_substitution_against_frozen_registration():
    freeze, ledger, packets = materials()
    bad_ledger = copy.deepcopy(ledger)
    bad_packets = copy.deepcopy(packets)
    substituted_content = (
        next(
            packet["arm_policy"]["content"]
            for packet in bad_packets["packets"]
            if packet["arm"] == "control"
        )
        + "\n# substituted after freeze\n"
    )
    substituted_sha = hashlib.sha256(substituted_content.encode()).hexdigest()
    for entry in bad_ledger["entries"]:
        if entry["arm"] == "control":
            entry["arm_policy_sha256"] = substituted_sha
    bad_ledger.pop("ledger_sha256")
    bad_ledger["ledger_sha256"] = ALLOC.digest(bad_ledger)
    bad_packets["allocation_ledger_sha256"] = bad_ledger["ledger_sha256"]
    for packet in bad_packets["packets"]:
        packet["allocation_ledger_sha256"] = bad_ledger["ledger_sha256"]
        if packet["arm"] == "control":
            packet["arm_policy"]["content"] = substituted_content
            packet["arm_policy"]["sha256"] = substituted_sha
            packet["inputs"]["arm_policy_files"][0]["sha256"] = substituted_sha
        packet.pop("packet_sha256")
        packet["packet_sha256"] = ALLOC.digest(packet)
    bad_packets.pop("packet_set_sha256")
    bad_packets["packet_set_sha256"] = ALLOC.digest(bad_packets)
    with pytest.raises(ValueError, match="frozen registration material"):
        ALLOC.validate_packet_lineage(freeze, bad_ledger, bad_packets)


def test_lineage_rejects_rehashed_fixture_write_scope_substitution():
    freeze, ledger, packets = materials()
    bad_ledger = copy.deepcopy(ledger)
    bad_packets = copy.deepcopy(packets)
    target = bad_ledger["entries"][0]
    target["write_scope"] = ["outside-authorized-fixture-scope"]
    bad_ledger.pop("ledger_sha256")
    bad_ledger["ledger_sha256"] = ALLOC.digest(bad_ledger)
    bad_packets["allocation_ledger_sha256"] = bad_ledger["ledger_sha256"]
    for packet in bad_packets["packets"]:
        packet["allocation_ledger_sha256"] = bad_ledger["ledger_sha256"]
        if packet["cell_id"] == target["cell_id"]:
            packet["write_scope"] = list(target["write_scope"])
        packet.pop("packet_sha256")
        packet["packet_sha256"] = ALLOC.digest(packet)
    bad_packets.pop("packet_set_sha256")
    bad_packets["packet_set_sha256"] = ALLOC.digest(bad_packets)
    with pytest.raises(ValueError, match="fixture block/write_scope mismatch"):
        ALLOC.validate_packet_lineage(freeze, bad_ledger, bad_packets)


@pytest.mark.parametrize("field", ["seed_sha256", "baseline_material_sha256"])
def test_allocation_lineage_rejects_rehashed_freeze_commitment_substitution(field):
    freeze, ledger, _ = materials()
    bad = copy.deepcopy(ledger)
    bad[field] = "0" * 64
    bad.pop("ledger_sha256")
    bad["ledger_sha256"] = ALLOC.digest(bad)
    with pytest.raises(ValueError, match="seed commitment|baseline material"):
        ALLOC.validate_allocation_lineage(freeze, bad)
