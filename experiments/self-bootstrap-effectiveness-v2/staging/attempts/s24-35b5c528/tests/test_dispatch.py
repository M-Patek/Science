import pytest

from science_repo.dispatch import audit_dispatch_handoff, create_dispatch_envelope


def campaign():
    return {
        "schema_version": 1,
        "id": "bootstrap",
        "title": "Bootstrap",
        "objective": "Improve the framework using bounded native agents.",
        "status": "approved",
        "owner": "maintainer",
        "tasks": [
            {
                "id": "dx",
                "role": "developer",
                "depends_on": [],
                "inputs": ["docs/INDEX.md"],
                "outputs": ["science_repo/dispatch.py"],
                "write_scope": ["science_repo/dispatch.py", "tests/test_dispatch.py"],
                "review_required": True,
                "human_gate": False,
            }
        ],
    }


def handoff(**changes):
    value = {
        "schema_version": 1,
        "campaign_id": "bootstrap",
        "task_id": "dx",
        "agent_role": "developer",
        "status": "complete",
        "summary": "Added a runtime-neutral dispatch packet.",
        "outputs": ["science_repo/dispatch.py"],
        "changed_files": ["science_repo/dispatch.py", "tests/test_dispatch.py"],
        "evidence": ["pytest tests/test_dispatch.py"],
        "unresolved": [],
        "recommended_next": ["Expose this pure API through the CLI later."],
    }
    value.update(changes)
    return value


def test_envelope_is_small_deterministic_and_platform_neutral():
    first = create_dispatch_envelope(campaign(), "dx")
    second = create_dispatch_envelope(campaign(), "dx")
    assert first == second
    assert first["task"]["inputs"] == ["docs/INDEX.md"]
    assert first["task"]["write_scope"] == ["science_repo/dispatch.py", "tests/test_dispatch.py"]
    assert "spawn_agent" not in first["prompt"]
    assert "required_fields" in first["handoff_contract"]


def test_invalid_campaign_or_unknown_task_cannot_be_dispatched():
    invalid = campaign()
    invalid["tasks"][0]["write_scope"] = ["../escape"]
    with pytest.raises(ValueError, match="invalid campaign"):
        create_dispatch_envelope(invalid, "dx")
    with pytest.raises(ValueError, match="unknown campaign task"):
        create_dispatch_envelope(campaign(), "missing")


def test_returned_handoff_is_bound_to_dispatch_and_authoritative_scope():
    envelope = create_dispatch_envelope(campaign(), "dx")
    assert audit_dispatch_handoff(envelope, handoff(), campaign()) == []

    errors = audit_dispatch_handoff(
        envelope,
        handoff(changed_files=["docs/unauthorized.md"]),
        campaign(),
    )
    assert any("outside task write_scope" in error for error in errors)

    errors = audit_dispatch_handoff(envelope, handoff(task_id="other"), campaign())
    assert any("task_id does not match dispatch" in error for error in errors)


def test_tampered_envelope_cannot_authorize_a_different_role():
    envelope = create_dispatch_envelope(campaign(), "dx")
    envelope["agent_role"] = "reviewer"
    errors = audit_dispatch_handoff(envelope, handoff(agent_role="reviewer"), campaign())
    assert any("agent_role does not match campaign task role" in error for error in errors)
