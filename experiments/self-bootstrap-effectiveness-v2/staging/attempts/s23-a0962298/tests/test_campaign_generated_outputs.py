import json

from science_repo.campaign import validate_generated_task_outputs


def test_register_task_rejects_handwritten_untrusted_freeze(tmp_path):
    (tmp_path / "science-project.yaml").write_text("schema_version: 1\nid: framework-self-study\n", encoding="utf-8")
    output = "registration/cohort-freeze.json"
    (tmp_path / "registration").mkdir()
    (tmp_path / output).write_text(json.dumps({
        "schema_version": 1, "dispatch_allowed": True,
        "runtime_identity": {"receipt_verification": "agent-self-report"},
    }), encoding="utf-8")
    campaign = {"id": "self-bootstrap-v2", "tasks": [{"id": "register-executable-cohort", "outputs": [output]}]}
    errors = validate_generated_task_outputs(tmp_path, campaign, "register-executable-cohort")
    assert errors
    assert any("unexpected runtime receipt verification state" in error for error in errors)


def test_packet_task_rejects_arbitrary_manifest(tmp_path):
    (tmp_path / "science-project.yaml").write_text("schema_version: 1\nid: framework-self-study\n", encoding="utf-8")
    freeze = "registration/cohort-freeze.json"
    output = "staging/packet-manifest.json"
    (tmp_path / "registration").mkdir()
    (tmp_path / "staging").mkdir()
    (tmp_path / freeze).write_text("{}", encoding="utf-8")
    (tmp_path / output).write_text('{"packet_count":24}', encoding="utf-8")
    campaign = {"id": "self-bootstrap-v2", "tasks": [{
        "id": "prepare-sanitized-subject-packets", "inputs": [freeze], "outputs": [output],
    }]}
    errors = validate_generated_task_outputs(tmp_path, campaign, "prepare-sanitized-subject-packets")
    assert errors and "generated packet validation failed" in errors[0]


def test_unrelated_project_may_reuse_task_id_without_study_coupling(tmp_path):
    (tmp_path / "science-project.yaml").write_text("schema_version: 1\nid: unrelated-project\n", encoding="utf-8")
    campaign = {"id": "other-campaign", "tasks": [{
        "id": "register-executable-cohort", "outputs": ["arbitrary.json"],
    }]}
    assert validate_generated_task_outputs(tmp_path, campaign, "register-executable-cohort") == []
