"""Safe, deterministic execution-environment capture.

The capture boundary deliberately records capabilities and public version labels,
not machine identity or environment-variable values.  Probes are local, bounded,
injectable, and optional; failure means ``unknown`` rather than success.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from collections.abc import Callable, Mapping, Sequence
from typing import Any

Probe = Callable[[Sequence[str], float], tuple[int, str, str]]

_PACKAGE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)$")
_VERSION = re.compile(r"(?<![A-Za-z0-9])([0-9]+(?:\.[0-9]+){1,3})(?![A-Za-z0-9])")
_MAX_OUTPUT = 4096


def _clean_probe_environment() -> dict[str, str]:
    """Return a deliberately small, non-networking subprocess environment."""
    clean = {
        "LANG": "C", "LC_ALL": "C", "NO_PROXY": "*", "no_proxy": "*",
        "PIP_NO_INDEX": "1", "PYTHONNOUSERSITE": "1",
    }
    for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
        if value := os.environ.get(key):
            clean[key] = value
    return clean


def _terminate_probe(process: subprocess.Popen[str]) -> None:
    """Best-effort process-tree termination without relying on an untrusted PATH."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif os.name == "nt":
            system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
            taskkill = Path(system_root) / "System32" / "taskkill.exe"
            if taskkill.is_file():
                subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, timeout=2, check=False,
                    env=_clean_probe_environment(),
                )
            else:
                process.kill()
        else:
            process.kill()
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass


def _local_probe(argv: Sequence[str], timeout: float) -> tuple[int, str, str]:
    try:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            errors="replace", env=_clean_probe_environment(), shell=False,
            start_new_session=os.name == "posix", creationflags=creationflags,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_probe(process)
            stdout, stderr = process.communicate()
            return 124, stdout[:_MAX_OUTPUT], stderr[:_MAX_OUTPUT]
    except OSError:
        return 127, "", ""
    return process.returncode, stdout[:_MAX_OUTPUT], stderr[:_MAX_OUTPUT]


def _untrusted_location(path: Path) -> bool:
    """Conservatively reject executables in caller-controlled filesystem areas."""
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return True
    boundaries = [Path.cwd(), Path.home(), Path(tempfile.gettempdir())]
    for boundary in boundaries:
        try:
            resolved.relative_to(boundary.resolve())
            return True
        except (OSError, ValueError):
            pass
    # A writable executable or containing directory is not stable evidence.
    return os.access(resolved, os.W_OK) or os.access(resolved.parent, os.W_OK)


def _resolve_tools(
    env: Mapping[str, str], trusted: Mapping[str, str] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in ("docker", "podman", "apptainer", "singularity", "nvidia-smi"):
        if trusted is not None and name in trusted:
            candidate = Path(trusted[name])
            if candidate.is_absolute():
                result[name] = str(candidate)
            continue
        found = shutil.which(name, path=env.get("PATH", ""))
        if found:
            candidate = Path(found)
            if candidate.is_absolute() and not _untrusted_location(candidate):
                result[name] = str(candidate)
    return result


def _run(probe: Probe, argv: Sequence[str], timeout: float) -> tuple[int, str]:
    """Normalize an untrusted probe result and cap attacker-controlled output."""
    try:
        code, stdout, stderr = probe(tuple(argv), timeout)
        if not isinstance(code, int) or not isinstance(stdout, str) or not isinstance(stderr, str):
            return 127, ""
    except Exception:  # a probe is evidence collection, never a run-failure source
        return 127, ""
    return code, (stdout + "\n" + stderr)[:_MAX_OUTPUT]


def _version(text: str) -> str | None:
    match = _VERSION.search(text)
    return match.group(1) if match else None


def _packages(probe: Probe, timeout: float) -> list[str]:
    code, output = _run(probe, (sys.executable, "-m", "pip", "freeze", "--local"), timeout)
    if code != 0:
        return []
    # Direct references can contain credentials, private hosts, usernames or paths.
    safe: dict[str, str] = {}
    for line in output.splitlines():
        match = _PACKAGE.fullmatch(line.strip())
        if match:
            safe[match.group(1).lower().replace("_", "-")] = match.group(2)
    return [f"{name}=={safe[name]}" for name in sorted(safe)]


def _runtime(probe: Probe, timeout: float, env: Mapping[str, str], tools: Mapping[str, str] | None = None) -> dict[str, Any]:
    if "KUBERNETES_SERVICE_HOST" in env:
        return {"state": "observed", "runtime": "kubernetes"}
    for name in ("docker", "podman", "apptainer", "singularity"):
        executable = name if tools is None else tools.get(name)
        if not executable:
            continue
        code, output = _run(probe, (executable, "--version"), timeout)
        if code == 0:
            result: dict[str, Any] = {"state": "observed", "runtime": name}
            version = _version(output)
            if version:
                result["version"] = version
            return result
    return {"state": "unknown"}


def _gpu(probe: Probe, timeout: float, env: Mapping[str, str], tools: Mapping[str, str] | None = None) -> dict[str, Any]:
    executable = "nvidia-smi" if tools is None else tools.get("nvidia-smi")
    if executable:
        code, output = _run(
            probe,
            (executable, "--query-gpu=driver_version", "--format=csv,noheader"),
            timeout,
        )
    else:
        code, output = 127, ""
    if code == 0:
        result: dict[str, Any] = {"state": "observed", "vendor": "nvidia"}
        version = _version(output)
        if version:
            result["driver"] = version
        return result
    if "ROCR_VISIBLE_DEVICES" in env:
        return {"state": "observed", "vendor": "amd"}
    if "CUDA_VISIBLE_DEVICES" in env or "NVIDIA_VISIBLE_DEVICES" in env:
        return {"state": "observed", "vendor": "nvidia"}
    return {"state": "unknown"}


def _orchestration(env: Mapping[str, str]) -> dict[str, Any]:
    # Presence is useful evidence; values (job/repository/tenant IDs) are not.
    providers = (
        ("github", ("GITHUB_ACTIONS",)), ("gitlab", ("GITLAB_CI",)),
        ("azure", ("TF_BUILD",)), ("jenkins", ("JENKINS_URL",)),
    )
    schedulers = (
        ("slurm", ("SLURM_JOB_ID",)), ("pbs", ("PBS_JOBID",)),
        ("lsf", ("LSB_JOBID",)),
    )
    for provider, keys in providers:
        if any(key in env for key in keys):
            return {"state": "observed", "kind": "ci", "provider": provider}
    for scheduler, keys in schedulers:
        if any(key in env for key in keys):
            return {"state": "observed", "kind": "hpc", "scheduler": scheduler}
    if "CI" in env:
        return {"state": "observed", "kind": "ci", "provider": "unknown"}
    return {"state": "unknown"}


def capture_environment(
    *, environ: Mapping[str, str] | None = None, probe: Probe | None = None,
    timeout: float = 2.0, python_version: str | None = None,
    platform_value: str | None = None,
    trusted_executables: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the runner-ready, JSON-only environment snapshot.

    ``probe`` is injectable for tests and alternative runners.  It must not use a
    shell.  The default only invokes local executables and never accesses a network.
    """
    if timeout <= 0 or timeout > 10:
        raise ValueError("probe timeout must be greater than zero and at most 10 seconds")
    env = os.environ if environ is None else environ
    runner = _local_probe if probe is None else probe
    # Injected probes retain logical command names for backwards-compatible tests;
    # the real local probe only receives resolved, trusted absolute paths.
    tools = None if probe is not None else _resolve_tools(env, trusted_executables)
    signals = sorted(key for key in (
        "CI", "GITHUB_ACTIONS", "GITLAB_CI", "TF_BUILD", "JENKINS_URL",
        "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES",
        "SLURM_JOB_ID", "PBS_JOBID", "LSB_JOBID", "KUBERNETES_SERVICE_HOST", "CONTAINER",
    ) if key in env)
    return {
        "schema_version": 1,
        "python": python_version or platform.python_version(),
        "platform": platform_value or f"{platform.system().lower()}-{platform.machine().lower()}",
        "sources": {
            "python": "supplied" if python_version is not None else "observed",
            "platform": "supplied" if platform_value is not None else "observed",
        },
        "packages": _packages(runner, timeout),
        "container": _runtime(runner, timeout, env, tools),
        "gpu": _gpu(runner, timeout, env, tools),
        "orchestration": _orchestration(env),
        "selected_environment": {key: "present" for key in signals},
    }


runner_environment_snapshot = capture_environment
