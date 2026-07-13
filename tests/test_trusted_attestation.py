from copy import deepcopy
from datetime import datetime, timezone

import pytest

from science_repo.trusted_attestation import (
    AttestationError, canonical_sha256, verify_human_authorization_receipt,
    verify_runtime_identity_receipt,
)

NOW = datetime(2026, 7, 13, 4, 0, tzinfo=timezone.utc)


class Verifier:
    def __init__(self, result=True, raises=False): self.result, self.raises = result, raises
    def verify(self, receipt):
        if self.raises: raise RuntimeError("host unavailable")
        return self.result


def receipt(kind="runtime_identity", subject=None):
    request = {"cell_id": "fx::control", "write_scope": ["runs/fx"]}
    subject = subject or {"provider": "host", "model": "immutable-v1"}
    return request, subject, {
        "schema_version": 1, "receipt_id": "r-1", "kind": kind,
        "authority_id": "host-keyring", "issued_at": "2026-07-13T03:00:00Z",
        "expires_at": "2026-07-13T05:00:00Z", "cohort_id": "cohort-1",
        "request_sha256": canonical_sha256(request), "scopes": ["dispatch", "runs/fx"],
        "subject_sha256": canonical_sha256(subject), "claims": {"source": "native-host"},
        "signature": {"algorithm": "host-defined", "key_id": "key-1", "value": "opaque"},
    }


def args(request):
    return dict(verifier=Verifier(), cohort_id="cohort-1", request=request,
                scopes=["runs/fx", "dispatch"], trusted_authorities=["host-keyring"], now=NOW)


def test_runtime_receipt_requires_external_trust_and_exact_bindings():
    request, identity, value = receipt()
    assert verify_runtime_identity_receipt(value, identity=identity, **args(request))["receipt_id"] == "r-1"
    for mutation in ("cohort", "request", "scope", "subject", "authority"):
        bad = deepcopy(value)
        if mutation == "cohort": bad["cohort_id"] = "other"
        if mutation == "request": bad["request_sha256"] = "0" * 64
        if mutation == "scope": bad["scopes"] = ["dispatch"]
        if mutation == "subject": bad["subject_sha256"] = "0" * 64
        if mutation == "authority": bad["authority_id"] = "self-reported"
        with pytest.raises(AttestationError):
            verify_runtime_identity_receipt(bad, identity=identity, **args(request))


@pytest.mark.parametrize("verifier", [None, Verifier(False), Verifier(raises=True)])
def test_missing_rejected_or_broken_verifier_fails_closed(verifier):
    request, identity, value = receipt()
    options = args(request); options["verifier"] = verifier
    with pytest.raises(AttestationError): verify_runtime_identity_receipt(value, identity=identity, **options)


def test_expired_or_future_receipt_fails_closed():
    request, identity, value = receipt()
    for field, stamp in (("expires_at", "2026-07-13T04:00:00Z"), ("issued_at", "2026-07-13T04:01:00Z")):
        bad = deepcopy(value); bad[field] = stamp
        with pytest.raises(AttestationError): verify_runtime_identity_receipt(bad, identity=identity, **args(request))


def test_human_authorization_requires_explicit_human_claims():
    authorization = {"decision": "approve", "limits": {"cost": 0}}
    request, _, value = receipt("human_authorization", authorization)
    value["claims"] = {"human_approved": True, "approver_id": "person-7"}
    assert verify_human_authorization_receipt(value, authorization=authorization, **args(request))["claims"]["human_approved"]
    value["claims"] = {"source": "agent"}
    with pytest.raises(AttestationError): verify_human_authorization_receipt(value, authorization=authorization, **args(request))
