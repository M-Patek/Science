from __future__ import annotations
import copy
import hashlib
from datetime import datetime, timedelta, timezone
import pytest
from test_preparation_contracts import load, materials

VERIFY = load("verify_attempts.py")
H = "a" * 64
ALL = [
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
]


def finalized(v, field):
    v.pop(field, None)
    v[field] = VERIFY.digest(v)
    return v


def bundle(
    store, packet, index=1, *, stop="completed", censor="not-censored", reason=None, critical=None
):
    artifacts = []
    kinds = (
        ["harness-receipt", "host-observation", "local-dispatch-acceptance", "execution-gate"]
        if censor == "setup-censored"
        else ALL
    )
    for kind in kinds:
        path = f"a{index}/{kind}.txt"
        content = f"synthetic {kind} evidence {index}\n".encode()
        store[path] = content
        artifacts.append(
            {
                "kind": kind,
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "byte_count": len(content),
            }
        )
    evidence = finalized(
        {"schema_version": 2, "attempt_id": f"attempt-{index:03d}", "artifacts": artifacts},
        "manifest_sha256",
    )
    setup = censor == "setup-censored"
    secs = 5400 if stop == "timeout" else 60
    start = datetime(2026, 7, 13, tzinfo=timezone.utc)
    received = None if setup else start + timedelta(seconds=10)
    end = start + timedelta(seconds=30 if setup else 10 + secs)

    def iso(value):
        return value.isoformat().replace("+00:00", "Z") if value else None

    return {
        "schema_version": 2,
        "cohort_id": packet["cohort_id"],
        "cell_id": packet["cell_id"],
        "arm": packet["arm"],
        "attempt_id": f"attempt-{index:03d}",
        "attempt_ordinal": 1,
        "freeze_sha256": packet["freeze_sha256"],
        "allocation_ledger_sha256": packet["allocation_ledger_sha256"],
        "packet_set_sha256": "PENDING",
        "subject_packet_sha256": packet["packet_sha256"],
        "baseline": packet["baseline"],
        "identities": {
            "planned_session_id": packet["session_id"],
            "planned_worktree_id": packet["worktree_id"],
            "planned_context_id": packet["context_id"],
            "native_agent_id": f"native-{index}",
            "observed_harness_session_id": f"harness-{index}",
            "observed_cwd": packet["workspace_contract"]["cwd"],
            "observed_head_commit": packet["baseline"]["git_commit"],
            "observed_head_tree": packet["baseline"]["git_tree"],
        },
        "local_evidence": {
            "evidence_level": "host-observed-unsigned",
            "harness_receipt_sha256": next(
                a["sha256"] for a in artifacts if a["kind"] == "harness-receipt"
            ),
            "local_dispatch_acceptance_sha256": next(
                a["sha256"] for a in artifacts if a["kind"] == "local-dispatch-acceptance"
            ),
            "execution_gate_sha256": next(
                a["sha256"] for a in artifacts if a["kind"] == "execution-gate"
            ),
        },
        "timing": {
            "bootstrap_started_utc": iso(start),
            "task_received_utc": iso(received),
            "ended_utc": iso(end),
            "bootstrap_elapsed_seconds": 30 if setup else 10,
            "task_elapsed_seconds": None if setup else secs,
        },
        "task_evidence_started": not setup,
        "evidence_manifest": evidence,
        "stop_reason": stop,
        "censor": {"status": censor, "reason": reason},
        "deviations": [],
        "critical_violations": critical or [],
    }


def bind(v, ps):
    v["packet_set_sha256"] = ps["packet_set_sha256"]
    return finalized(v, "finalized_sha256")


@pytest.mark.parametrize(
    "stop,critical",
    [
        ("completed", []),
        ("timeout", []),
        ("context-exhaustion", []),
        ("explicit-block", []),
        ("infrastructure-failure", []),
        ("refusal", []),
        ("test-failure", []),
        ("critical-violation", ["scope-or-worktree-escape"]),
    ],
)
def test_all_allowed_outcome_stops_are_closed_and_valid(stop, critical):
    store = {}
    _, _, ps = materials()
    v = bind(bundle(store, ps["packets"][0], stop=stop, critical=critical), ps)
    VERIFY.validate_attempt(v, ps["packets"][0], artifact_reader=store.__getitem__)


@pytest.mark.parametrize("stop", ["explicit-block", "infrastructure-failure"])
@pytest.mark.parametrize(
    "reason",
    [
        "wrong-frozen-material",
        "nonfresh-workspace-or-context",
        "duplicate-identity",
        "prohibited-registration-leakage",
        "host-capture-failure",
        "pre-task-infrastructure-failure",
    ],
)
def test_all_setup_censor_reasons_and_stops_are_valid(stop, reason):
    store = {}
    _, _, ps = materials()
    v = bind(bundle(store, ps["packets"][0], stop=stop, censor="setup-censored", reason=reason), ps)
    VERIFY.validate_attempt(v, ps["packets"][0], artifact_reader=store.__getitem__)


def test_setup_capture_failure_may_preserve_explicitly_missing_local_evidence_but_outcome_may_not():
    store = {}
    _, _, ps = materials()
    setup = bind(
        bundle(
            store,
            ps["packets"][0],
            stop="infrastructure-failure",
            censor="setup-censored",
            reason="host-capture-failure",
        ),
        ps,
    )
    setup["local_evidence"]["harness_receipt_sha256"] = None
    setup["local_evidence"]["local_dispatch_acceptance_sha256"] = None
    setup["evidence_manifest"]["artifacts"] = [
        a
        for a in setup["evidence_manifest"]["artifacts"]
        if a["kind"] not in {"harness-receipt", "local-dispatch-acceptance"}
    ]
    finalized(setup["evidence_manifest"], "manifest_sha256")
    finalized(setup, "finalized_sha256")
    VERIFY.validate_attempt(setup, ps["packets"][0], artifact_reader=store.__getitem__)
    outcome = bind(bundle(store, ps["packets"][1], index=2), ps)
    outcome["local_evidence"]["harness_receipt_sha256"] = None
    finalized(outcome, "finalized_sha256")
    with pytest.raises(ValueError, match="may not be null"):
        VERIFY.validate_attempt(outcome, ps["packets"][1], artifact_reader=store.__getitem__)


def test_attempt_rejects_cross_field_tree_and_retrieval_contradictions():
    store = {}
    _, _, ps = materials()
    base = bind(bundle(store, ps["packets"][0]), ps)
    for mutate in [
        lambda v: v["censor"].__setitem__("reason", "host-capture-failure"),
        lambda v: v["timing"].__setitem__("task_elapsed_seconds", 59),
        lambda v: v["identities"].__setitem__("observed_head_tree", "0" * 40),
        lambda v: v.__setitem__("stop_reason", "critical-violation"),
    ]:
        v = copy.deepcopy(base)
        mutate(v)
        finalized(v, "finalized_sha256")
        with pytest.raises(ValueError):
            VERIFY.validate_attempt(v, ps["packets"][0], artifact_reader=store.__getitem__)
    store.pop(base["evidence_manifest"]["artifacts"][0]["path"])
    with pytest.raises(ValueError, match="retrievable"):
        VERIFY.validate_attempt(base, ps["packets"][0], artifact_reader=store.__getitem__)


def test_manifest_is_bijective_and_rejects_missing_cell_and_tree_substitution():
    store = {}
    freeze, ledger, ps = materials()
    bundles = [bind(bundle(store, p, i), ps) for i, p in enumerate(ps["packets"], 1)]
    m = VERIFY.build_attempt_manifest(
        freeze=freeze,
        allocation_ledger=ledger,
        packet_set=ps,
        bundles=bundles,
        artifact_reader=store.__getitem__,
    )
    assert m["attempt_count"] == 24
    with pytest.raises(ValueError, match="24-cell"):
        VERIFY.build_attempt_manifest(
            freeze=freeze,
            allocation_ledger=ledger,
            packet_set=ps,
            bundles=bundles[:-1],
            artifact_reader=store.__getitem__,
        )
    bad = copy.deepcopy(bundles)
    bad[0]["identities"]["observed_head_tree"] = "0" * 40
    finalized(bad[0], "finalized_sha256")
    with pytest.raises(ValueError, match="commit/tree"):
        VERIFY.build_attempt_manifest(
            freeze=freeze,
            allocation_ledger=ledger,
            packet_set=ps,
            bundles=bad,
            artifact_reader=store.__getitem__,
        )
    bad_l = copy.deepcopy(ledger)
    bad_l["freeze_sha256"] = "0" * 64
    finalized(bad_l, "ledger_sha256")
    bad_ps = copy.deepcopy(ps)
    bad_ps["allocation_ledger_sha256"] = bad_l["ledger_sha256"]
    for packet in bad_ps["packets"]:
        packet["allocation_ledger_sha256"] = bad_l["ledger_sha256"]
        finalized(packet, "packet_sha256")
    finalized(bad_ps, "packet_set_sha256")
    bad_b = copy.deepcopy(bundles)
    by_cell = {p["cell_id"]: p for p in bad_ps["packets"]}
    for b in bad_b:
        b["allocation_ledger_sha256"] = bad_l["ledger_sha256"]
        b["subject_packet_sha256"] = by_cell[b["cell_id"]]["packet_sha256"]
        b["packet_set_sha256"] = bad_ps["packet_set_sha256"]
        finalized(b, "finalized_sha256")
    with pytest.raises(ValueError, match="freeze/cohort mismatch"):
        VERIFY.build_attempt_manifest(
            freeze=freeze,
            allocation_ledger=bad_l,
            packet_set=bad_ps,
            bundles=bad_b,
            artifact_reader=store.__getitem__,
        )


@pytest.mark.parametrize("kind", ["events", "commands", "patch", "outputs", "tests", "handoff"])
def test_setup_censored_attempt_rejects_each_task_artifact(kind):
    store = {}
    _, _, ps = materials()
    v = bind(
        bundle(
            store,
            ps["packets"][0],
            stop="infrastructure-failure",
            censor="setup-censored",
            reason="pre-task-infrastructure-failure",
        ),
        ps,
    )
    path = f"probe/{kind}"
    raw = b"prohibited task evidence"
    store[path] = raw
    v["evidence_manifest"]["artifacts"].append(
        {
            "kind": kind,
            "path": path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_count": len(raw),
        }
    )
    finalized(v["evidence_manifest"], "manifest_sha256")
    finalized(v, "finalized_sha256")
    with pytest.raises(ValueError, match="prohibited task evidence"):
        VERIFY.validate_attempt(v, ps["packets"][0], artifact_reader=store.__getitem__)
