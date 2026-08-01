from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
DOMAIN = b"science-self-bootstrap-allocation-v1\0"
ARMS = ("control", "treatment")
BASELINE_COMMIT = "722cceed959e8ac9c45cdfd519a4c387e614c58f"
BASELINE_TREE = "f28c8500c7f4f5223234e87d1b0d2376fbb9539a"
FIXTURE_MANIFEST_RELATIVE = (
    "experiments/self-bootstrap-effectiveness-v2/task-fixtures-v2.yaml"
)


def canonical_bytes(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(v: Any) -> str:
    return hashlib.sha256(canonical_bytes(v)).hexdigest()


def file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _final(v: Mapping[str, Any], field: str, newline: bool = False) -> bool:
    u = dict(v)
    claimed = u.pop(field, None)
    return claimed == hashlib.sha256(canonical_bytes(u) + (b"\n" if newline else b"")).hexdigest()


def _schema(name: str, v: Mapping[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(v))
    if errors:
        raise ValueError(f"{name} violation: {errors[0].message}")


def seed_bytes(seed: str) -> bytes:
    if not isinstance(seed, str) or not seed or seed != seed.strip():
        raise ValueError(
            "allocation seed must be a non-empty exact UTF-8 string without surrounding whitespace"
        )
    return seed.encode()


def ranked_assignments(fixtures: Sequence[Mapping[str, Any]], seed: str) -> list[dict[str, Any]]:
    raw = seed_bytes(seed)
    rows = []
    for f in fixtures:
        for arm in ARMS:
            cell = f"{f['id']}::{arm}"
            rank = hashlib.sha256(DOMAIN + raw + b"\0" + cell.encode()).hexdigest()
            rows.append(
                {
                    "cell_id": cell,
                    "fixture_id": f["id"],
                    "block": int(f["block"]),
                    "arm": arm,
                    "rank_sha256": rank,
                }
            )
    rows.sort(key=lambda r: (r["rank_sha256"], r["cell_id"]))
    if len(rows) != 24 or len({r["cell_id"] for r in rows}) != 24:
        raise ValueError("allocation requires twelve unique fixtures and exactly 24 cells")
    for i, r in enumerate(rows, 1):
        r["execution_order"] = i
        r["wave"] = (i - 1) // 3 + 1
    return rows


def _frozen_file_sha(freeze: Mapping[str, Any], relative: str) -> str:
    found = []
    for group in freeze.get("registration_materials", []):
        found.extend(row["sha256"] for row in group.get("files", []) if row.get("path") == relative)
    if len(found) != 1:
        raise ValueError(f"frozen registration file binding missing or duplicated: {relative}")
    return found[0]


def _frozen_fixture_map(freeze: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    path = ROOT / "task-fixtures-v2.yaml"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _frozen_file_sha(freeze, FIXTURE_MANIFEST_RELATIVE):
        raise ValueError("fixture manifest bytes do not match frozen registration material")
    document = yaml.safe_load(raw.decode("utf-8"))
    fixtures = document.get("fixtures") if isinstance(document, dict) else None
    if not isinstance(fixtures, list) or len(fixtures) != 12:
        raise ValueError("frozen fixture manifest must contain exactly twelve fixtures")
    fixture_map = {
        fixture.get("id"): fixture for fixture in fixtures if isinstance(fixture, dict)
    }
    if len(fixture_map) != 12 or None in fixture_map:
        raise ValueError("frozen fixture manifest ids must be unique and present")
    return fixture_map


def _policy_tools(arm: str, content: str) -> dict[str, Any]:
    doc = yaml.safe_load(content)
    tools = doc.get("tools") if isinstance(doc, dict) else None
    if (
        doc.get("schema_version") != 2
        or not isinstance(doc.get("instructions"), list)
        or not isinstance(tools, dict)
    ):
        raise ValueError("arm policy shape invalid")
    native = tools.get("native_subagents")
    if arm == "control" and native != "forbidden":
        raise ValueError("control delegation policy drift")
    if arm == "treatment" and (
        not isinstance(native, dict)
        or native.get("allowed") is not True
        or native.get("maximum_concurrent") != 3
        or native.get("maximum_child_attempts") != 4
    ):
        raise ValueError("treatment delegation policy drift")
    return tools


def _policy(arm: str, path: Path, freeze: Mapping[str, Any]) -> dict[str, Any]:
    expected = f"experiments/self-bootstrap-effectiveness-v2/templates/arm-{arm}-v2.yaml"
    if path.name != f"arm-{arm}-v2.yaml":
        raise ValueError("arm policy path mismatch")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if _frozen_file_sha(freeze, expected) != sha:
        raise ValueError("arm policy bytes do not match frozen registration material")
    content = raw.decode("utf-8")
    tools = _policy_tools(arm, content)
    return {"path": expected, "sha256": sha, "content": content, "tools": tools}


def build_allocation_ledger(
    *,
    freeze: Mapping[str, Any],
    fixtures: Sequence[Mapping[str, Any]],
    seed: str,
    arm_policy_files: Mapping[str, Path],
    baseline: Mapping[str, str],
) -> dict[str, Any]:
    if not _final(freeze, "freeze_sha256", True):
        raise ValueError("freeze digest mismatch")
    if freeze.get("cohort_id") != "self-bootstrap-effectiveness-v2":
        raise ValueError("unexpected cohort_id")
    if (
        freeze.get("randomization", {}).get("seed_sha256")
        != hashlib.sha256(seed_bytes(seed)).hexdigest()
    ):
        raise ValueError("seed does not match frozen seed commitment")
    if baseline.get("git_commit") != BASELINE_COMMIT or baseline.get("git_tree") != BASELINE_TREE:
        raise ValueError("baseline commit/tree does not match the preregistered pinned baseline")
    fb = freeze.get("baseline_materials", [])
    if (
        len(fb) != 1
        or fb[0].get("path")
        != "experiments/self-bootstrap-effectiveness-v2/templates/baseline-v2.yaml"
    ):
        raise ValueError("frozen baseline material binding is missing")
    policies = {arm: _policy(arm, Path(arm_policy_files[arm]), freeze) for arm in ARMS}
    fixture_map = {f["id"]: f for f in fixtures}
    entries = ranked_assignments(fixtures, seed)
    frozen = [
        {k: r[k] for k in ("cell_id", "fixture_id", "arm", "execution_order")} for r in entries
    ]
    if freeze.get("assignment_ledger") != frozen:
        raise ValueError("allocation does not reproduce the frozen assignment ledger")
    for r in entries:
        pol = policies[r["arm"]]
        r.update(
            {
                "arm_policy_path": pol["path"],
                "arm_policy_sha256": pol["sha256"],
                "tools": pol["tools"],
                "write_scope": list(fixture_map[r["fixture_id"]]["write_scope"]),
            }
        )
    result = {
        "schema_version": 2,
        "cohort_id": freeze["cohort_id"],
        "freeze_sha256": freeze["freeze_sha256"],
        "seed_sha256": freeze["randomization"]["seed_sha256"],
        "algorithm": "sha256-ranked-cells-v1",
        "wave_size": 3,
        "wave_count": 8,
        "baseline": {"git_commit": baseline["git_commit"], "git_tree": baseline["git_tree"]},
        "baseline_material_sha256": fb[0]["tree_sha256"],
        "cell_count": 24,
        "entries": entries,
    }
    result["ledger_sha256"] = digest(result)
    _schema("allocation-ledger-v2.schema.json", result)
    return result


def validate_allocation_lineage(freeze: Mapping[str, Any], ledger: Mapping[str, Any]) -> None:
    _schema("allocation-ledger-v2.schema.json", ledger)
    if not _final(freeze, "freeze_sha256", True) or not _final(ledger, "ledger_sha256"):
        raise ValueError("freeze or allocation ledger digest mismatch")
    if (
        ledger["freeze_sha256"] != freeze["freeze_sha256"]
        or ledger["cohort_id"] != freeze["cohort_id"]
    ):
        raise ValueError("allocation ledger freeze/cohort mismatch")
    if ledger["baseline"] != {"git_commit": BASELINE_COMMIT, "git_tree": BASELINE_TREE}:
        raise ValueError("allocation ledger baseline mismatch")
    if ledger["seed_sha256"] != freeze.get("randomization", {}).get("seed_sha256"):
        raise ValueError("allocation ledger seed commitment mismatch")
    baseline_materials = freeze.get("baseline_materials", [])
    if (
        len(baseline_materials) != 1
        or baseline_materials[0].get("path")
        != "experiments/self-bootstrap-effectiveness-v2/templates/baseline-v2.yaml"
        or ledger["baseline_material_sha256"] != baseline_materials[0].get("tree_sha256")
    ):
        raise ValueError("allocation ledger baseline material mismatch")
    entries = ledger["entries"]
    fixture_map = _frozen_fixture_map(freeze)
    for entry in entries:
        fixture = fixture_map.get(entry["fixture_id"])
        if (
            fixture is None
            or entry["block"] != int(fixture["block"])
            or entry["write_scope"] != list(fixture["write_scope"])
        ):
            raise ValueError("allocation ledger fixture block/write_scope mismatch")
    for arm in ARMS:
        expected_path = f"experiments/self-bootstrap-effectiveness-v2/templates/arm-{arm}-v2.yaml"
        expected_sha = _frozen_file_sha(freeze, expected_path)
        arm_entries = [entry for entry in entries if entry["arm"] == arm]
        if len(arm_entries) != 12 or any(
            entry["arm_policy_path"] != expected_path or entry["arm_policy_sha256"] != expected_sha
            for entry in arm_entries
        ):
            raise ValueError("allocation ledger policy does not match frozen registration material")
    frozen = freeze.get("assignment_ledger", [])
    projection = [
        {k: r[k] for k in ("cell_id", "fixture_id", "arm", "execution_order")} for r in entries
    ]
    if projection != frozen:
        raise ValueError("allocation semantics do not match frozen assignment ledger")
    if (
        [r["execution_order"] for r in entries] != list(range(1, 25))
        or [r["wave"] for r in entries] != [(i - 1) // 3 + 1 for i in range(1, 25)]
        or entries != sorted(entries, key=lambda r: (r["rank_sha256"], r["cell_id"]))
    ):
        raise ValueError("allocation rank/order/wave semantics invalid")


def bind_packet_set(
    *,
    raw_packet_set: Mapping[str, Any],
    freeze: Mapping[str, Any],
    ledger: Mapping[str, Any],
    fixtures: Sequence[Mapping[str, Any]],
    arm_policy_files: Mapping[str, Path],
) -> dict[str, Any]:
    validate_allocation_lineage(freeze, ledger)
    if not _final(raw_packet_set, "packet_set_sha256", True):
        raise ValueError("raw packet-set digest mismatch")
    if raw_packet_set.get("freeze_sha256") != freeze["freeze_sha256"]:
        raise ValueError("packet set freeze substitution")
    raw = {r["cell_id"]: r for r in raw_packet_set.get("packets", [])}
    if len(raw) != 24:
        raise ValueError("raw packet set must cover exactly 24 cells")
    policies = {arm: _policy(arm, Path(arm_policy_files[arm]), freeze) for arm in ARMS}
    fixture_map = {f["id"]: f for f in fixtures}
    packets = []
    for a in ledger["entries"]:
        packet = raw.get(a["cell_id"])
        if packet is None or any(
            packet.get(k) != a[k] for k in ("arm", "fixture_id", "execution_order")
        ):
            raise ValueError("packet allocation mismatch")
        if not _final(packet, "packet_sha256", True):
            raise ValueError("raw subject-packet digest mismatch")
        pol = policies[a["arm"]]
        if (
            pol["sha256"] != a["arm_policy_sha256"]
            or pol["tools"] != a["tools"]
            or list(fixture_map[a["fixture_id"]]["write_scope"]) != a["write_scope"]
        ):
            raise ValueError("policy or fixture delivery drift")
        bound = dict(packet)
        inputs = dict(bound["inputs"])
        inputs["arm_policy_files"] = [{"source_path": pol["path"], "sha256": pol["sha256"]}]
        bound["inputs"] = inputs
        bound.update(
            {
                "cohort_id": ledger["cohort_id"],
                "freeze_sha256": ledger["freeze_sha256"],
                "allocation_ledger_sha256": ledger["ledger_sha256"],
                "baseline": dict(ledger["baseline"]),
                "wave": a["wave"],
                "arm_policy": {
                    "path": pol["path"],
                    "sha256": pol["sha256"],
                    "content": pol["content"],
                },
                "tools": pol["tools"],
                "write_scope": a["write_scope"],
            }
        )
        bound.pop("packet_sha256", None)
        bound["packet_sha256"] = digest(bound)
        packets.append(bound)
    if any(len({p[f] for p in packets}) != 24 for f in ("session_id", "worktree_id", "context_id")):
        raise ValueError("subject packet identities must be unique")
    result = {
        "schema_version": 2,
        "cohort_id": ledger["cohort_id"],
        "freeze_sha256": ledger["freeze_sha256"],
        "allocation_ledger_sha256": ledger["ledger_sha256"],
        "packet_count": 24,
        "dispatch_allowed": False,
        "packets": packets,
    }
    result["packet_set_sha256"] = digest(result)
    validate_packet_lineage(freeze, ledger, result)
    return result


def validate_packet_lineage(
    freeze: Mapping[str, Any], ledger: Mapping[str, Any], packet_set: Mapping[str, Any]
) -> None:
    validate_allocation_lineage(freeze, ledger)
    _schema("packet-set-v2.schema.json", packet_set)
    if not _final(packet_set, "packet_set_sha256"):
        raise ValueError("packet set digest mismatch")
    if (
        packet_set["freeze_sha256"] != freeze["freeze_sha256"]
        or packet_set["allocation_ledger_sha256"] != ledger["ledger_sha256"]
        or packet_set["cohort_id"] != freeze["cohort_id"]
    ):
        raise ValueError("packet-set lineage mismatch")
    by_cell = {p["cell_id"]: p for p in packet_set["packets"]}
    if len(by_cell) != 24:
        raise ValueError("packet cells duplicated")
    for a in ledger["entries"]:
        p = by_cell.get(a["cell_id"])
        if p is None or not _final(p, "packet_sha256"):
            raise ValueError("packet missing or digest mismatch")
        for key in ("fixture_id", "arm", "execution_order", "wave", "tools", "write_scope"):
            if p[key] != a[key]:
                raise ValueError(f"packet allocation/policy mismatch: {key}")
        if (
            p["arm_policy"]["path"] != a["arm_policy_path"]
            or p["arm_policy"]["sha256"] != a["arm_policy_sha256"]
            or hashlib.sha256(p["arm_policy"]["content"].encode()).hexdigest()
            != a["arm_policy_sha256"]
        ):
            raise ValueError("packet arm-policy bytes mismatch")
        if _policy_tools(a["arm"], p["arm_policy"]["content"]) != a["tools"]:
            raise ValueError("packet arm-policy semantics mismatch")
        expected_policy_input = [
            {"source_path": a["arm_policy_path"], "sha256": a["arm_policy_sha256"]}
        ]
        if p["inputs"].get("arm_policy_files") != expected_policy_input:
            raise ValueError("packet arm-policy input binding mismatch")
        if (
            p["baseline"] != ledger["baseline"]
            or p["freeze_sha256"] != freeze["freeze_sha256"]
            or p["allocation_ledger_sha256"] != ledger["ledger_sha256"]
        ):
            raise ValueError("packet frozen lineage mismatch")
