"""Deterministic, non-secret comparison of captured execution environments.

This module deliberately consumes snapshots rather than probing the host.  It can
therefore assess an old run without changing the evidence or contacting external
services.
"""

from __future__ import annotations

import json
import hashlib
import math
import re
from pathlib import Path
from typing import Any, Mapping


_UNAVAILABLE = {"", "n/a", "none", "null", "unavailable", "not available"}
_ENV_SIGNAL_GROUPS = {
    "container": ("CONTAINER", "KUBERNETES_SERVICE_HOST"),
    "gpu": ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES"),
    "orchestration": (
        "CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILD_ID", "SLURM_JOB_ID",
        "SLURM_CLUSTER_NAME", "PBS_JOBID", "LSB_JOBID",
    ),
}
_SAFE_ENUMS = {
    "docker", "podman", "containerd", "singularity", "apptainer",
    "nvidia", "amd", "intel", "cuda", "rocm",
    "ci", "hpc", "slurm", "pbs", "lsf", "kubernetes",
}


def load_environment(path: str | Path) -> dict[str, Any]:
    """Load an environment snapshot, requiring a JSON object."""
    value = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON number is not allowed: {token}")
        ),
    )
    if not isinstance(value, dict):
        raise ValueError("environment snapshot must be a JSON object")
    _validate_json(value)
    return value


def _validate_json(value: Any, path: str = "$") -> None:
    """Reject Python-only or non-portable values before comparison."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string object key at {path}")
            _validate_json(item, f"{path}.{key}")
        return
    raise ValueError(f"non-JSON value at {path}: {type(value).__name__}")


def _state(value: Any) -> str:
    if value is _MISSING:
        return "unknown"
    if value is None or value is False:
        return "unavailable"
    if isinstance(value, str) and value.strip().lower() in _UNAVAILABLE:
        return "unavailable"
    return "observed"


class _Missing:
    pass


_MISSING = _Missing()


def _fingerprint(value: Any) -> dict[str, str]:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


def _safe_value(value: Any) -> Any:
    """Expose only explicitly safe enums; fingerprint every arbitrary value."""
    if isinstance(value, str) and value.strip().lower() in _SAFE_ENUMS:
        return value.strip().lower()
    return _fingerprint(value)


def _comparison(reference: Any, current: Any, *, expose: bool = True) -> dict[str, Any]:
    rs, cs = _state(reference), _state(current)
    if rs != "observed" or cs != "observed":
        status = "unavailable" if "unavailable" in (rs, cs) else "unknown"
    else:
        status = "match" if reference == current else "mismatch"
    result: dict[str, Any] = {
        "status": status,
        "reference_state": rs,
        "current_state": cs,
    }
    if expose:
        if rs == "observed":
            result["reference"] = _safe_value(reference)
        if cs == "observed":
            result["current"] = _safe_value(current)
    return result


def _python_version(snapshot: Mapping[str, Any]) -> Any:
    value = snapshot.get("python", _MISSING)
    if not isinstance(value, str):
        return value
    match = re.match(r"\s*(\d+\.\d+(?:\.\d+)?)", value)
    return match.group(1) if match else value.strip()


def _packages(snapshot: Mapping[str, Any]) -> Any:
    value = snapshot.get("packages", _MISSING)
    if value is _MISSING or value is None:
        return value
    if not isinstance(value, list):
        return _MISSING
    normalized: dict[str, str] = {}
    for item in value:
        if not isinstance(item, str) or "==" not in item:
            continue
        name, version = item.split("==", 1)
        if name.strip():
            normalized[name.strip().lower().replace("_", "-")] = version.strip()
    return normalized


def _package_comparison(reference: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    left, right = _packages(reference), _packages(current)
    base = _comparison(left, right, expose=False)
    if _state(left) == _state(right) == "observed":
        names = sorted(set(left) | set(right))
        base["added"] = [_fingerprint(f"{n}=={right[n]}") for n in names if n not in left]
        base["removed"] = [_fingerprint(f"{n}=={left[n]}") for n in names if n not in right]
        base["changed"] = [
            {
                "name_sha256": _fingerprint(n)["sha256"],
                "reference_sha256": _fingerprint(left[n])["sha256"],
                "current_sha256": _fingerprint(right[n])["sha256"],
            }
            for n in names if n in left and n in right and left[n] != right[n]
        ]
        base["reference_count"] = len(left)
        base["current_count"] = len(right)
    return base


def _nested(snapshot: Mapping[str, Any], section: str, fields: tuple[str, ...]) -> Any:
    value = snapshot.get(section, _MISSING)
    if value is _MISSING or value is None or value is False:
        return value
    if not isinstance(value, Mapping):
        return _MISSING
    safe = {field: value[field] for field in fields if field in value}
    return safe if safe else _MISSING


def _signal_presence(snapshot: Mapping[str, Any], group: str) -> Any:
    selected = snapshot.get("selected_environment", _MISSING)
    if selected is _MISSING:
        return _MISSING
    if not isinstance(selected, Mapping):
        return _MISSING
    # Values are intentionally discarded: job IDs, device selections, and CI
    # variables may disclose tenant or infrastructure details.
    return sorted(key for key in _ENV_SIGNAL_GROUPS[group] if key in selected)


def _clue(snapshot: Mapping[str, Any], section: str, fields: tuple[str, ...]) -> Any:
    structured = _nested(snapshot, section, fields)
    if _state(structured) == "observed":
        return structured
    signals = _signal_presence(snapshot, section)
    return signals if _state(signals) == "observed" and signals else structured


def assess_reproduction(
    reference: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare two snapshots without leaking captured environment variable values.

    Missing evidence is ``unknown`` and explicit absence is ``unavailable``;
    neither is treated as a match.  The returned object is stable and JSON-safe.
    """
    _validate_json(reference)
    _validate_json(current)
    dimensions = {
        "python": _comparison(_python_version(reference), _python_version(current)),
        "packages": _package_comparison(reference, current),
        "platform": _comparison(reference.get("platform", _MISSING), current.get("platform", _MISSING)),
        "container": _comparison(
            _clue(reference, "container", ("runtime", "image", "image_digest")),
            _clue(current, "container", ("runtime", "image", "image_digest")),
        ),
        "gpu": _comparison(
            _clue(reference, "gpu", ("vendor", "model", "driver", "runtime")),
            _clue(current, "gpu", ("vendor", "model", "driver", "runtime")),
        ),
        "orchestration": _comparison(
            _clue(reference, "orchestration", ("kind", "provider", "runner", "scheduler")),
            _clue(current, "orchestration", ("kind", "provider", "runner", "scheduler")),
        ),
    }
    statuses = [item["status"] for item in dimensions.values()]
    overall = "mismatch" if "mismatch" in statuses else (
        "indeterminate" if any(s in {"unknown", "unavailable"} for s in statuses) else "match"
    )
    return {"schema_version": 1, "overall_status": overall, "dimensions": dimensions}


def assess_environment_files(reference: str | Path, current: str | Path) -> dict[str, Any]:
    """Convenience wrapper around :func:`assess_reproduction`."""
    return assess_reproduction(load_environment(reference), load_environment(current))
