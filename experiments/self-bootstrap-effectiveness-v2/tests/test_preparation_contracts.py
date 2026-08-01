from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
import yaml
from jsonschema import Draft202012Validator
from science_repo.cohort_freeze import STATIC_RUNTIME_IDENTITY_FIELDS
from science_repo.subject_packets import build_subject_packet_set

EXPERIMENT = Path(__file__).parents[1]
PROJECT = EXPERIMENT.parents[1]


def load(name):
    p = EXPERIMENT / "src" / name
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s)
    assert s and s.loader
    s.loader.exec_module(m)
    return m


FREEZE = load("freeze_v2.py")
ALLOC = load("allocate_v2.py")


def freeze(seed="pre-outcome-test-seed"):
    identity = {k: f"declared-{k}" for k in STATIC_RUNTIME_IDENTITY_FIELDS}
    encoded = (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    receipt = {
        "receipt_id": "design-test",
        "authority_id": "unsigned-local-test",
        "source": "test-declaration",
        "issued_at": "2026-07-13T00:00:00Z",
        "identity_sha256": hashlib.sha256(encoded).hexdigest(),
    }
    return FREEZE.build_v2_freeze(
        project_root=PROJECT,
        human_seed=seed,
        runtime_identity=identity,
        runtime_receipt=receipt,
        extra_review_materials=[],
    )


def materials(seed="pre-outcome-test-seed"):
    f = freeze(seed)
    manifest = yaml.safe_load((EXPERIMENT / "task-fixtures-v2.yaml").read_text(encoding="utf-8"))
    baseline = yaml.safe_load(
        (EXPERIMENT / "templates/baseline-v2.yaml").read_text(encoding="utf-8")
    )
    policies = {a: EXPERIMENT / "templates" / f"arm-{a}-v2.yaml" for a in ("control", "treatment")}
    ledger = ALLOC.build_allocation_ledger(
        freeze=f,
        fixtures=manifest["fixtures"],
        seed=seed,
        arm_policy_files=policies,
        baseline=baseline,
    )
    raw = build_subject_packet_set(freeze=f, source_root=PROJECT)
    packets = ALLOC.bind_packet_set(
        raw_packet_set=raw,
        freeze=f,
        ledger=ledger,
        fixtures=manifest["fixtures"],
        arm_policy_files=policies,
    )
    return f, ledger, packets


def test_freeze_and_all_closed_contracts_validate_without_authorizing_dispatch():
    f, ledger, packets = materials()
    cohort_schema = json.loads(
        (PROJECT / "schemas/cohort-freeze.schema.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(cohort_schema).iter_errors(f)) == []
    for name, value in [
        ("allocation-ledger-v2.schema.json", ledger),
        ("packet-set-v2.schema.json", packets),
    ]:
        schema = json.loads((EXPERIMENT / "schemas" / name).read_text(encoding="utf-8-sig"))
        assert list(Draft202012Validator(schema).iter_errors(value)) == []
    assert (
        f["randomization"]["method"] == "sha256-ranked-cells-v1"
        and len(f["assignment_ledger"]) == 24
    )
    assert packets["dispatch_allowed"] is False and all(
        p["baseline"] == ledger["baseline"] for p in packets["packets"]
    )


def test_packet_binding_rejects_substituted_freeze_and_ledger():
    f, ledger, packets = materials()
    raw = build_subject_packet_set(freeze=f, source_root=PROJECT)
    fixtures = yaml.safe_load((EXPERIMENT / "task-fixtures-v2.yaml").read_text())["fixtures"]
    policies = {a: EXPERIMENT / "templates" / f"arm-{a}-v2.yaml" for a in ("control", "treatment")}
    bad = copy.deepcopy(f)
    bad["freeze_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest mismatch|substitution"):
        ALLOC.bind_packet_set(
            raw_packet_set=raw,
            freeze=bad,
            ledger=ledger,
            fixtures=fixtures,
            arm_policy_files=policies,
        )
    bad = copy.deepcopy(ledger)
    bad["freeze_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest mismatch|substitution"):
        ALLOC.bind_packet_set(
            raw_packet_set=raw, freeze=f, ledger=bad, fixtures=fixtures, arm_policy_files=policies
        )
