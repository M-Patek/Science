from copy import deepcopy
from pathlib import Path

import pytest

from science_repo.execution_adapter import (DryRunExecutionAdapter, authorize_execution_submit,
    canonical_digest, execution_idempotency_key, validate_execution_request,
    validate_execution_result, submit_execution)


def request():
    value = {"schema_version": 1, "request_id": "r-1", "project_id": "p-1",
             "revision": "git:abc", "command": ["python", "-m", "job"],
             "working_directory": "experiments/job", "inputs": [{"path": "data/input.csv", "digest": "sha256:" + "a"*64}],
             "environment": {"MODE": "test"}, "env_refs": ["config:job"], "secret_refs": ["vault:job-key"],
             "resources": {"cpu": 2, "cost_ceiling": {"amount": 3.5, "currency": "USD"}},
             "sensitive_resources": {"external_compute": True, "private_data": False, "instrument": False, "cost_bearing": True},
             "authorization": {"reference": "approval:42"}}
    value["idempotency_key"] = execution_idempotency_key(value)
    return value


def test_valid_request_and_dry_run(tmp_path: Path):
    req = request()
    schema = Path(__file__).parents[1] / "schemas/execution-envelope.schema.json"
    assert validate_execution_request(req, tmp_path / "request.json", tmp_path, schema_path=schema) == []
    result = DryRunExecutionAdapter().submit(req)
    assert result["status"] == "planned" and result["authenticated"] is False
    assert validate_execution_result(result, tmp_path / "result.json") == []


def test_digest_is_canonical_and_key_binds_content():
    req = request()
    assert canonical_digest(req) == canonical_digest(dict(reversed(list(req.items()))))
    changed = deepcopy(req); changed["command"].append("--changed")
    assert execution_idempotency_key(changed) != req["idempotency_key"]


@pytest.mark.parametrize("mutation,fragment", [
    (lambda r: r.update(command="python -m job"), "argv array"),
    (lambda r: r.update(command_string="python job.py"), "shell strings"),
    (lambda r: r.update(api_key="plaintext"), "inline secret"),
    (lambda r: r.update(environment={"MODE": "Bearer x"}), "safe enumerated"),
    (lambda r: r.update(working_directory="../escape"), "normalized project-relative"),
    (lambda r: r.update(working_directory="CON/file"), "platform-unsafe"),
])
def test_rejects_malicious_boundaries(tmp_path: Path, mutation, fragment):
    req = request(); mutation(req); req["idempotency_key"] = execution_idempotency_key(req)
    assert any(fragment in e for e in validate_execution_request(req, tmp_path/"r.json", tmp_path))


def test_caller_authorization_is_unattested_and_bad_key(tmp_path: Path):
    req = request(); req["authorization"]["reference"] = "approval:forged"
    errors = validate_execution_request(req, tmp_path/"r.json", tmp_path)
    assert any("idempotency_key" in e for e in errors)
    assert "attested human authorization" in authorize_execution_submit(req, None, None)[0]


def test_result_cannot_claim_authentication(tmp_path: Path):
    result = DryRunExecutionAdapter().submit(request()); result["authenticated"] = True
    assert any("unattested" in e for e in validate_execution_result(result, tmp_path/"x.json"))


class Verifier:
    def __init__(self, valid=True): self.valid = valid
    def verify(self, receipt): return self.valid


def receipt(req):
    return {"request_digest": canonical_digest(req),
            "resources_digest": canonical_digest(req["resources"]),
            "cost_ceiling": deepcopy(req["resources"]["cost_ceiling"]),
            "scopes": ["external_compute", "cost_bearing"], "approver": "human:alice",
            "expires_at": "2099-01-01T00:00:00Z"}


def test_trusted_verifier_attests_exact_receipt():
    req = request()
    assert authorize_execution_submit(req, receipt(req), Verifier()) == []
    assert "unattested" in authorize_execution_submit(req, receipt(req), Verifier(False))[0]


@pytest.mark.parametrize("change,fragment", [
    (lambda x: x.update(request_digest="sha256:" + "0"*64), "digest mismatch"),
    (lambda x: x.update(scopes=["cost_bearing"]), "scope mismatch"),
    (lambda x: x.update(expires_at="2000-01-01T00:00:00Z"), "expired"),
    (lambda x: x.update(resources_digest="sha256:" + "0"*64), "resource request mismatch"),
])
def test_forged_or_mismatched_receipt_is_rejected(change, fragment):
    req = request(); value = receipt(req); change(value)
    assert any(fragment in e for e in authorize_execution_submit(req, value, Verifier()))


def test_real_provider_is_not_called_without_attestation():
    class Provider:
        name = "remote"
        called = False
        def submit(self, req):
            self.called = True
            return {}
    provider = Provider()
    with pytest.raises(PermissionError, match="attested human authorization"):
        submit_execution(provider, request())
    assert provider.called is False


def test_dry_run_never_consumes_or_claims_authorization():
    result = submit_execution(DryRunExecutionAdapter(), request())
    assert result["status"] == "planned" and result["authenticated"] is False
