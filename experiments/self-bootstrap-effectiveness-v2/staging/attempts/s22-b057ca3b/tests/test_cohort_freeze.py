import json
from pathlib import Path

import pytest

from science_repo.cohort_freeze import (
    CohortFreezeError, STATIC_RUNTIME_IDENTITY_FIELDS, build_cohort_freeze, register_cohort_freeze,
)


def _inputs(tmp_path: Path):
    fixtures = []
    for number in range(12):
        path = tmp_path / f"fixture-{number:02d}"
        path.mkdir(exist_ok=True)
        (path / "task.txt").write_text(f"task {number}\n", encoding="utf-8")
        fixtures.append((f"F{number:02d}", path))
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("base\n", encoding="utf-8")
    runtime = {key: f"known-{key}" for key in STATIC_RUNTIME_IDENTITY_FIELDS}
    runtime["sampling_parameters"] = {"temperature": 0}
    runtime["tool_names_and_versions"] = ["science-test/1"]
    import hashlib
    encoded = (json.dumps(runtime, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    receipt = {"receipt_id": "host-receipt-1", "authority_id": "human-operator-1", "source": "host-runtime",
               "issued_at": "2026-07-13T00:00:00Z", "identity_sha256": hashlib.sha256(encoded).hexdigest()}
    return dict(cohort_id="self-study-1", registration_root=tmp_path, fixtures=fixtures,
                baseline_materials=[baseline], human_supplied_seed="human-chosen-seed", runtime_identity=runtime,
                runtime_identity_receipt=receipt)


def test_build_is_deterministic_balanced_and_records_no_authority_or_observations(tmp_path):
    values = _inputs(tmp_path)
    first = build_cohort_freeze(**values)
    assert first == build_cohort_freeze(**values)
    assert len(first["fixtures"]) == 12
    assert len(first["assignment_ledger"]) == 24
    assert len({row["cell_id"] for row in first["assignment_ledger"]}) == 24
    assert [row["execution_order"] for row in first["assignment_ledger"]] == list(range(1, 25))
    for fixture in first["fixtures"]:
        assert {row["arm"] for row in first["assignment_ledger"] if row["fixture_id"] == fixture["fixture_id"]} == {"control", "treatment"}
    assert first["authority"].startswith("none-")
    assert first["observations"] == "none-recorded"
    assert first["registration_status"] == "materials-frozen-dispatch-blocked"
    assert first["dispatch_allowed"] is False
    assert "human-chosen-seed" not in json.dumps(first)


def test_registration_is_idempotent_but_conflict_fails_closed(tmp_path):
    values = _inputs(tmp_path)
    output = tmp_path / "cohort-freeze.json"
    first = register_cohort_freeze(output, **values)
    assert register_cohort_freeze(output, **values) == first
    values["human_supplied_seed"] = "different-human-seed"
    with pytest.raises(CohortFreezeError, match="conflicting"):
        register_cohort_freeze(output, **values)
    assert json.loads(output.read_text(encoding="utf-8")) == first


def test_requires_exactly_twelve_complete_runtime_and_human_seed(tmp_path):
    values = _inputs(tmp_path)
    values["fixtures"] = values["fixtures"][:-1]
    with pytest.raises(CohortFreezeError, match="exactly 12"):
        build_cohort_freeze(**values)
    values = _inputs(tmp_path)
    values["runtime_identity"].pop("provider")
    with pytest.raises(CohortFreezeError, match="missing required"):
        build_cohort_freeze(**values)
    values = _inputs(tmp_path)
    values["runtime_identity_receipt"]["identity_sha256"] = "0" * 64
    with pytest.raises(CohortFreezeError, match="does not bind"):
        build_cohort_freeze(**values)
    values = _inputs(tmp_path)
    values["human_supplied_seed"] = ""
    with pytest.raises(CohortFreezeError, match="human-supplied"):
        build_cohort_freeze(**values)


def test_material_mutation_changes_freeze_and_links_are_rejected(tmp_path):
    values = _inputs(tmp_path)
    before = build_cohort_freeze(**values)
    (tmp_path / "fixture-00" / "task.txt").write_text("changed\n", encoding="utf-8")
    assert build_cohort_freeze(**values)["freeze_sha256"] != before["freeze_sha256"]
    link = tmp_path / "fixture-00" / "link.txt"
    try:
        link.symlink_to(tmp_path / "baseline.txt")
    except OSError:
        pytest.skip("links unavailable on this platform")
    with pytest.raises(CohortFreezeError, match="links"):
        build_cohort_freeze(**values)
