from __future__ import annotations

import pytest

from science_repo.review_plugins import (
    MAX_CHECKS_PER_PLUGIN,
    PluginCheck,
    REVIEW_SCOPE,
    ReviewPluginRegistry,
)


def test_registry_is_explicit_deterministic_and_structured() -> None:
    registry = ReviewPluginRegistry()
    registry.register("zeta", lambda evidence: PluginCheck("b", "unknown", ("run.json",)))
    registry.register("alpha", lambda evidence: [PluginCheck("a", "pass", detail="ok")])

    checks = registry.run({"run": {"status": "succeeded"}})

    assert [check["id"] for check in checks] == ["alpha:a", "zeta:b"]
    assert checks[0]["passed"] is True
    assert checks[1]["passed"] is False
    assert checks[1]["evidence_refs"] == ["run.json"]
    assert all(check["reviewer_kind"] == "mechanical" for check in checks)
    assert all(check["scope"] == REVIEW_SCOPE for check in checks)


def test_evidence_is_detached_and_recursively_immutable() -> None:
    evidence = {"items": [{"value": 1}]}

    def critic(view):
        with pytest.raises(TypeError):
            view["new"] = True
        with pytest.raises(TypeError):
            view["items"][0]["value"] = 2
        return PluginCheck("immutable", "pass")

    registry = ReviewPluginRegistry()
    registry.register("immutability", critic)
    assert registry.run(evidence)[0]["status"] == "pass"
    assert evidence == {"items": [{"value": 1}]}


def test_plugin_exception_and_malformed_output_fail_closed() -> None:
    registry = ReviewPluginRegistry()
    registry.register("boom", lambda evidence: 1 / 0)
    registry.register("empty", lambda evidence: [])

    checks = registry.run({})

    assert [check["status"] for check in checks] == ["fail", "fail"]
    assert checks[0]["id"] == "boom:plugin_error"
    assert checks[0]["error_code"] == "review_plugin_failed"
    assert "ZeroDivisionError" not in checks[0]["detail"]


def test_duplicate_plugin_and_check_ids_are_rejected() -> None:
    registry = ReviewPluginRegistry()
    registry.register("same", lambda evidence: PluginCheck("one", "pass"))
    with pytest.raises(ValueError, match="duplicate review plugin"):
        registry.register("same", lambda evidence: PluginCheck("two", "pass"))

    duplicate_checks = ReviewPluginRegistry()
    duplicate_checks.register(
        "critic", lambda evidence: [PluginCheck("same", "pass"), PluginCheck("same", "pass")]
    )
    result = duplicate_checks.run({})
    assert result[-1]["id"] == "critic:plugin_error"
    assert result[-1]["status"] == "fail"


def test_reviewer_kind_is_explicit_but_never_claims_approval() -> None:
    registry = ReviewPluginRegistry()
    registry.register(
        "domain",
        lambda evidence: PluginCheck("plausibility", "unknown"),
        reviewer_kind="scientific-advisory",
    )
    check = registry.run({})[0]
    assert check["reviewer_kind"] == "scientific-advisory"
    assert "human approval" in check["scope"]

    with pytest.raises(ValueError, match="unsupported reviewer kind"):
        registry.register("bad", lambda evidence: PluginCheck("x", "pass"), reviewer_kind="oracle")


def test_human_kind_is_forbidden_and_human_approval_remains_a_separate_gate() -> None:
    registry = ReviewPluginRegistry()
    with pytest.raises(ValueError, match="unsupported reviewer kind"):
        registry.register(
            "human", lambda evidence: PluginCheck("approval", "pass"), reviewer_kind="human"
        )


def test_unbounded_plugin_output_is_bounded_and_fails_closed() -> None:
    def unbounded(evidence):
        index = 0
        while True:
            yield PluginCheck(str(index), "pass")
            index += 1

    registry = ReviewPluginRegistry()
    registry.register("unbounded", unbounded)
    checks = registry.run({})
    assert checks == [
        {
            "id": "unbounded:plugin_error",
            "plugin_id": "unbounded",
            "status": "fail",
            "passed": False,
            "reviewer_kind": "mechanical",
            "evidence_refs": [],
            "error_code": "review_plugin_failed",
            "detail": "registered review plugin failed closed",
            "scope": REVIEW_SCOPE,
        }
    ]
    assert MAX_CHECKS_PER_PLUGIN == 100
