"""Runtime-neutral boundary for authorized external execution.

This module deliberately contains no network transport.  Adapters receive an
already validated, immutable request and return an *unattested* provider
response; authenticity must be established by a separate trust mechanism.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, runtime_checkable

from .contracts import schema_errors

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SECRET_WORDS = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key)")
_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)
_SAFE_ENV = {"MODE": {"test", "development", "production"},
             "LOCALE": {"C", "C.UTF-8", "en_US.UTF-8"},
             "PYTHONUNBUFFERED": {"0", "1"}}


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def execution_idempotency_key(request: dict[str, Any]) -> str:
    """Bind idempotency to the complete request, excluding its caller key."""
    body = {key: value for key, value in request.items() if key != "idempotency_key"}
    return canonical_digest(body)


def _safe_path(value: Any, root: Path) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return "must be a non-empty normalized POSIX project-relative path"
    path = PurePosixPath(value)
    if path.is_absolute() or value == "." or any(p in {"", ".", ".."} for p in path.parts):
        return "must be a normalized project-relative path"
    for part in path.parts:
        if ":" in part or part.endswith((".", " ")) or _RESERVED.fullmatch(part):
            return "contains a platform-unsafe path segment"
        if any(ord(c) < 32 or ord(c) == 127 for c in part):
            return "contains control characters"
    base = root.resolve()
    try:
        (root / Path(*path.parts)).resolve(strict=False).relative_to(base)
    except ValueError:
        return "escapes the project root (including through a symlink)"
    return None


def validate_execution_request(
    request: dict[str, Any], request_path: Path, project_root: Path, *,
    schema_path: Path | None = None, expected_version: int = 1,
) -> list[str]:
    errors: list[str] = []
    if schema_path is not None:
        if not schema_path.is_file():
            errors.append(f"{schema_path}: missing pinned execution contract schema")
        else:
            errors.extend(schema_errors(request, schema_path, request_path,
                                        expected_version=expected_version))
    if request.get("schema_version") != expected_version:
        errors.append(f"{request_path}: schema_version must equal pinned version {expected_version}")
    for key in ("request_id", "project_id"):
        if not isinstance(request.get(key), str) or not _ID.fullmatch(request[key]):
            errors.append(f"{request_path}: {key} is invalid")
    if not isinstance(request.get("revision"), str) or not request["revision"]:
        errors.append(f"{request_path}: revision must be non-empty")
    command = request.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x and "\x00" not in x for x in command):
        errors.append(f"{request_path}: command must be a non-empty argv array")
    if any(key in request for key in ("shell", "command_string")):
        errors.append(f"{request_path}: shell strings are forbidden; use command argv")
    cwd = request.get("working_directory")
    problem = _safe_path(cwd, project_root)
    if problem:
        errors.append(f"{request_path}: working_directory {problem}")
    inputs = request.get("inputs")
    if not isinstance(inputs, list):
        errors.append(f"{request_path}: inputs must be an array")
    else:
        for i, item in enumerate(inputs):
            if not isinstance(item, dict) or not _DIGEST.fullmatch(str(item.get("digest", ""))):
                errors.append(f"{request_path}: inputs[{i}].digest must be a sha256 digest")
            elif (problem := _safe_path(item.get("path"), project_root)):
                errors.append(f"{request_path}: inputs[{i}].path {problem}")
    env = request.get("environment", {})
    if not isinstance(env, dict) or any(k not in _SAFE_ENV or v not in _SAFE_ENV.get(k, set())
                                        for k, v in env.items()):
        errors.append(f"{request_path}: environment is restricted to safe enumerated values; use env_refs for external values")
    env_refs = request.get("env_refs", [])
    if not isinstance(env_refs, list) or not all(isinstance(x, str) and _ID.fullmatch(x) for x in env_refs):
        errors.append(f"{request_path}: env_refs must contain opaque reference IDs")
    secret_refs = request.get("secret_refs", [])
    if not isinstance(secret_refs, list) or not all(isinstance(x, str) and _ID.fullmatch(x) for x in secret_refs):
        errors.append(f"{request_path}: secret_refs must contain opaque reference IDs")
    # Reject likely inline secrets anywhere except opaque reference names.
    for key in request:
        if key != "secret_refs" and _SECRET_WORDS.search(key):
            errors.append(f"{request_path}: inline secret field {key!r} is forbidden")
    auth = request.get("authorization")
    sensitive = request.get("sensitive_resources", {})
    resource = request.get("resources", {})
    if not isinstance(auth, dict) or not isinstance(auth.get("reference"), str) or not auth["reference"]:
        errors.append(f"{request_path}: human authorization reference is required")
    if not isinstance(resource, dict) or not isinstance(resource.get("cost_ceiling"), dict):
        errors.append(f"{request_path}: resources.cost_ceiling is required")
    else:
        ceiling = resource["cost_ceiling"]
        amount = ceiling.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            errors.append(f"{request_path}: cost ceiling amount must be a non-negative number")
    if not isinstance(sensitive, dict):
        errors.append(f"{request_path}: sensitive_resources must be an object")
    # Caller-provided authorization is only a routing reference.  It is never
    # treated as human approval; authorize_execution_submit performs attestation.
    expected = execution_idempotency_key(request)
    if request.get("idempotency_key") != expected:
        errors.append(f"{request_path}: idempotency_key does not match canonical request digest")
    return errors


def validate_execution_result(result: dict[str, Any], result_path: Path) -> list[str]:
    errors: list[str] = []
    if result.get("schema_version") != 1:
        errors.append(f"{result_path}: schema_version must equal 1")
    if result.get("status") not in {"planned", "accepted", "running", "succeeded", "failed", "cancelled"}:
        errors.append(f"{result_path}: invalid status")
    if result.get("authenticated") is not False:
        errors.append(f"{result_path}: adapter results are unattested and authenticated must be false")
    if not _DIGEST.fullmatch(str(result.get("request_digest", ""))):
        errors.append(f"{result_path}: request_digest must be a sha256 digest")
    return errors


@runtime_checkable
class ExecutionAdapter(Protocol):
    name: str
    def submit(self, request: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class AuthorizationVerifier(Protocol):
    """Trusted verifier boundary (implementation and trust roots are host-owned)."""
    def verify(self, receipt: dict[str, Any]) -> bool: ...


def validate_authorization_receipt(request: dict[str, Any], receipt: dict[str, Any], *,
                                   now: datetime | None = None) -> list[str]:
    """Mechanically bind an externally verified receipt to one exact request."""
    errors: list[str] = []
    digest = canonical_digest(request)
    if receipt.get("request_digest") != digest:
        errors.append("authorization receipt request digest mismatch")
    if receipt.get("resources_digest") != canonical_digest(request.get("resources", {})):
        errors.append("authorization receipt resource request mismatch")
    if receipt.get("cost_ceiling") != request.get("resources", {}).get("cost_ceiling"):
        errors.append("authorization receipt cost ceiling mismatch")
    required = {key for key, used in request.get("sensitive_resources", {}).items() if used}
    scopes = receipt.get("scopes")
    if not isinstance(scopes, list) or not required.issubset(set(scopes)):
        errors.append("authorization receipt scope mismatch")
    if not isinstance(receipt.get("approver"), str) or not receipt["approver"]:
        errors.append("authorization receipt approver is required")
    try:
        expiry = datetime.fromisoformat(str(receipt.get("expires_at", "")).replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= (now or datetime.now(timezone.utc)):
            errors.append("authorization receipt is expired")
    except ValueError:
        errors.append("authorization receipt expiry must be a timezone-aware ISO timestamp")
    return errors


def authorize_execution_submit(request: dict[str, Any], receipt: dict[str, Any] | None,
                               verifier: AuthorizationVerifier | None,
                               *, now: datetime | None = None) -> list[str]:
    """Fail closed before any real adapter submits sensitive/external work."""
    sensitive = any(request.get("sensitive_resources", {}).values())
    if not sensitive:
        return []
    if receipt is None or verifier is None:
        return ["attested human authorization is required for real submission"]
    errors = validate_authorization_receipt(request, receipt, now=now)
    if errors:
        return errors
    try:
        attested = verifier.verify(receipt)
    except Exception:
        return ["authorization verifier failed closed"]
    if attested is not True:
        return ["authorization receipt is unattested"]
    return []


class DryRunExecutionAdapter:
    """Local planning adapter: performs no execution and makes no trust claim."""
    name = "dry-run"

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"schema_version": 1, "adapter": self.name, "status": "planned",
                "request_id": request.get("request_id"),
                "request_digest": canonical_digest(request), "authenticated": False,
                "message": "validated plan only; no command or network action was performed"}


NullExecutionAdapter = DryRunExecutionAdapter


def submit_execution(adapter: ExecutionAdapter, request: dict[str, Any], *,
                     receipt: dict[str, Any] | None = None,
                     verifier: AuthorizationVerifier | None = None) -> dict[str, Any]:
    """The sanctioned submit boundary; real providers fail closed by default.

    Dry-run planning never consumes or implies authorization.  Every other
    adapter must cross the trusted receipt verifier before provider code runs.
    """
    if isinstance(adapter, DryRunExecutionAdapter):
        return adapter.submit(request)
    errors = authorize_execution_submit(request, receipt, verifier)
    if errors:
        raise PermissionError("; ".join(errors))
    return adapter.submit(request)
