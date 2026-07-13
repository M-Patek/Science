"""Fail-closed boundary for host-issued study attestations.

This module validates bindings, but deliberately does not implement a signing
key store.  Signature verification belongs to a host-owned verifier supplied
by the caller; receipt fields are never accepted as self-attestation.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


class AttestationError(ValueError):
    """A receipt is malformed, untrusted, stale, or bound to other work."""


@runtime_checkable
class TrustedAttestationVerifier(Protocol):
    """Host-owned trust boundary (for example, an OS or service key store)."""

    def verify(self, receipt: Mapping[str, Any]) -> bool: ...


_FIELDS = {
    "schema_version", "receipt_id", "kind", "authority_id", "issued_at",
    "expires_at", "cohort_id", "request_sha256", "scopes", "subject_sha256",
    "claims", "signature",
}
_KINDS = {"runtime_identity", "human_authorization"}


def canonical_sha256(value: Any) -> str:
    try:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AttestationError("attested value must be canonically JSON serializable") from error
    return hashlib.sha256(payload).hexdigest()


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise AttestationError(f"{field} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AttestationError(f"{field} must be a timezone-aware ISO timestamp") from error
    if parsed.tzinfo is None:
        raise AttestationError(f"{field} must be a timezone-aware ISO timestamp")
    return parsed


def verify_attestation(
    receipt: Mapping[str, Any], *, verifier: TrustedAttestationVerifier | None,
    kind: str, cohort_id: str, request: Any, scopes: Sequence[str], subject: Any,
    trusted_authorities: Sequence[str], now: datetime | None = None,
) -> dict[str, Any]:
    """Verify trust and exact cohort/request/scope/subject/expiry bindings.

    A detached JSON copy is returned only after the external verifier succeeds.
    Missing verifier or trust roots always fails closed.
    """
    if verifier is None:
        raise AttestationError("a host-owned attestation verifier is required")
    if kind not in _KINDS:
        raise AttestationError("unsupported attestation kind")
    if set(receipt) != _FIELDS:
        raise AttestationError("receipt fields do not match the pinned contract")
    if receipt.get("schema_version") != 1 or receipt.get("kind") != kind:
        raise AttestationError("receipt version or kind mismatch")
    for field in ("receipt_id", "authority_id", "cohort_id", "request_sha256", "subject_sha256"):
        if not isinstance(receipt.get(field), str) or not receipt[field]:
            raise AttestationError(f"receipt {field} must be a non-empty string")
    authorities = set(trusted_authorities)
    if not authorities or receipt["authority_id"] not in authorities:
        raise AttestationError("receipt authority is not in the caller's trust roots")
    if receipt["cohort_id"] != cohort_id:
        raise AttestationError("receipt cohort binding mismatch")
    if receipt["request_sha256"] != canonical_sha256(request):
        raise AttestationError("receipt request binding mismatch")
    expected_scopes = sorted(set(scopes))
    if not expected_scopes or list(receipt.get("scopes", [])) != expected_scopes:
        raise AttestationError("receipt scope binding mismatch")
    if receipt["subject_sha256"] != canonical_sha256(subject):
        raise AttestationError("receipt subject binding mismatch")
    if not isinstance(receipt.get("claims"), dict) or not receipt["claims"]:
        raise AttestationError("receipt claims must be a non-empty object")
    signature = receipt.get("signature")
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "key_id", "value"}:
        raise AttestationError("receipt signature envelope is invalid")
    if any(not isinstance(signature[key], str) or not signature[key] for key in signature):
        raise AttestationError("receipt signature fields must be non-empty strings")
    issued = _timestamp(receipt.get("issued_at"), "issued_at")
    expiry = _timestamp(receipt.get("expires_at"), "expires_at")
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise AttestationError("verification time must be timezone-aware")
    if issued > instant or expiry <= instant or expiry <= issued:
        raise AttestationError("receipt is not currently valid")
    try:
        trusted = verifier.verify(receipt)
    except Exception as error:
        raise AttestationError("host attestation verifier failed closed") from error
    if trusted is not True:
        raise AttestationError("receipt signature is not trusted")
    return json.loads(json.dumps(dict(receipt), sort_keys=True))


def verify_runtime_identity_receipt(receipt: Mapping[str, Any], *, identity: Any, **kwargs: Any) -> dict[str, Any]:
    return verify_attestation(receipt, kind="runtime_identity", subject=identity, **kwargs)


def verify_human_authorization_receipt(receipt: Mapping[str, Any], *, authorization: Any, **kwargs: Any) -> dict[str, Any]:
    verified = verify_attestation(receipt, kind="human_authorization", subject=authorization, **kwargs)
    claims = verified["claims"]
    if claims.get("human_approved") is not True or not isinstance(claims.get("approver_id"), str) or not claims["approver_id"]:
        raise AttestationError("human authorization claims are incomplete")
    return verified
