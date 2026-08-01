import copy
import json
from pathlib import Path

import pytest

from science_repo.cohort_freeze import STATIC_RUNTIME_IDENTITY_FIELDS, build_cohort_freeze
from science_repo.subject_packets import SubjectPacketError, build_subject_packet_set


def _rehash(freeze):
    unsigned = dict(freeze); unsigned.pop("freeze_sha256", None)
    freeze["freeze_sha256"] = __import__("hashlib").sha256(
        (json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def _freeze(root: Path):
    fixtures = []
    for index in range(12):
        path = root / f"f{index}"
        path.mkdir()
        (path / "prompt.txt").write_text(f"task {index}\n", encoding="utf-8")
        fixtures.append((f"F{index}", path))
    baseline = root / "baseline.txt"; baseline.write_text("baseline\n", encoding="utf-8")
    identity = {key: f"known-{key}" for key in STATIC_RUNTIME_IDENTITY_FIELDS}
    encoded = (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    receipt = {"receipt_id":"r", "authority_id":"a", "source":"host", "issued_at":"now", "identity_sha256":__import__("hashlib").sha256(encoded).hexdigest()}
    return build_cohort_freeze(cohort_id="C", registration_root=root, fixtures=fixtures,
        baseline_materials=[baseline], human_supplied_seed="human", runtime_identity=identity,
        runtime_identity_receipt=receipt)


def test_builds_24_unique_fail_closed_explicit_packets(tmp_path):
    artifact = build_subject_packet_set(freeze=_freeze(tmp_path), source_root=tmp_path)
    assert artifact["packet_count"] == 24 and artifact["dispatch_allowed"] is False
    assert artifact["host_enforcement"] == "unverified"
    packets = artifact["packets"]
    assert len({p["session_id"] for p in packets}) == 24
    assert len({p["worktree_id"] for p in packets}) == 24
    assert len({p["context_id"] for p in packets}) == 24
    assert all(p["attempt_ordinal"] == 1 and p["replacement_policy"]["maximum_replacements"] == 0 for p in packets)
    assert all(p["workspace_contract"]["fork_context_required"] == "none" for p in packets)


def test_rejects_mutation_bad_freeze_and_unsafe_content(tmp_path):
    freeze = _freeze(tmp_path)
    (tmp_path / "f0" / "prompt.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(SubjectPacketError, match="hash mismatch"):
        build_subject_packet_set(freeze=freeze, source_root=tmp_path)
    freeze = _freeze(tmp_path / "new") if (tmp_path / "new").mkdir() is None else None
    bad = copy.deepcopy(freeze); bad["assignment_ledger"][0]["cell_id"] = "tampered"
    with pytest.raises(SubjectPacketError, match="freeze hash"):
        build_subject_packet_set(freeze=bad, source_root=tmp_path / "new")


def test_negative_content_audit_rejects_absolute_paths_and_secrets(tmp_path):
    freeze = _freeze(tmp_path)
    target = tmp_path / "f0" / "prompt.txt"
    target.write_text("password=do-not-copy\n", encoding="utf-8")
    # Rebind the freeze only to exercise the independent content audit.
    data = target.read_bytes(); digest = __import__("hashlib").sha256(data).hexdigest()
    for material in freeze["fixtures"]:
        if material["fixture_id"] == "F0":
            material["files"][0]["sha256"] = digest
            material["tree_sha256"] = __import__("hashlib").sha256(
                (json.dumps(material["files"], sort_keys=True, separators=(",", ":")) + "\n").encode()
            ).hexdigest()
    unsigned = dict(freeze); unsigned.pop("freeze_sha256")
    freeze["freeze_sha256"] = __import__("hashlib").sha256((json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    with pytest.raises(SubjectPacketError, match="negative content audit"):
        build_subject_packet_set(freeze=freeze, source_root=tmp_path)


def test_rejects_duplicate_files_and_incomplete_or_duplicate_cells(tmp_path):
    freeze = _freeze(tmp_path)
    duplicate = copy.deepcopy(freeze["fixtures"][0]["files"][0])
    freeze["fixtures"][0]["files"].append(duplicate)
    freeze["fixtures"][0]["tree_sha256"] = __import__("hashlib").sha256(
        (json.dumps(freeze["fixtures"][0]["files"], sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    _rehash(freeze)
    with pytest.raises(SubjectPacketError, match="duplicate file paths"):
        build_subject_packet_set(freeze=freeze, source_root=tmp_path)

    freeze = _freeze(tmp_path / "cells") if (tmp_path / "cells").mkdir() is None else None
    freeze["assignment_ledger"][1]["fixture_id"] = freeze["assignment_ledger"][0]["fixture_id"]
    freeze["assignment_ledger"][1]["arm"] = freeze["assignment_ledger"][0]["arm"]
    _rehash(freeze)
    with pytest.raises(SubjectPacketError, match="cover every fixture-arm"):
        build_subject_packet_set(freeze=freeze, source_root=tmp_path / "cells")


def test_malformed_nested_freeze_fails_with_domain_error(tmp_path):
    freeze = _freeze(tmp_path)
    freeze["fixtures"][0]["files"][0]["path"] = 7
    _rehash(freeze)
    with pytest.raises(SubjectPacketError, match="schema is invalid"):
        build_subject_packet_set(freeze=freeze, source_root=tmp_path)
