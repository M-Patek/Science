from __future__ import annotations

import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import atomic_write_text, dump_json, sha256_file, sha256_text
from .models import Experiment


def _git_revision(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _environment_snapshot() -> dict[str, Any]:
    try:
        packages = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"], text=True, capture_output=True, check=False
        ).stdout.splitlines()
    except OSError:
        packages = []
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "packages": sorted(packages),
        "selected_environment": {
            key: os.environ[key]
            for key in ("CUDA_VISIBLE_DEVICES", "OMP_NUM_THREADS", "SLURM_JOB_ID")
            if key in os.environ
        },
    }


def _safe_declared_path(root: Path, relative: str) -> Path | None:
    candidate = root / relative
    try:
        candidate.relative_to(root)
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    # Declared evidence must not acquire content through a symlink, including a
    # symlinked parent directory. This avoids both path escape and mutable aliasing.
    current = candidate
    while current != root:
        if current.is_symlink():
            return None
        current = current.parent
    return candidate


def _path_digest(path: Path) -> tuple[str, int, str] | None:
    if path.is_file():
        return sha256_file(path), path.stat().st_size, "file"
    if not path.is_dir():
        return None
    digest = hashlib.sha256()
    total = 0
    for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        if child.is_symlink():
            return None
        relative = child.relative_to(path).as_posix()
        kind = "dir" if child.is_dir() else "file" if child.is_file() else "other"
        digest.update(f"{kind}\0{relative}\0".encode())
        if kind == "file":
            size = child.stat().st_size
            total += size
            digest.update(sha256_file(child).encode())
        elif kind == "other":
            return None
        digest.update(b"\0")
    return digest.hexdigest(), total, "directory"


def _evidence_item(root: Path, relative: str) -> dict[str, Any]:
    path = _safe_declared_path(root, relative)
    value = _path_digest(path) if path is not None else None
    return {
        "path": relative,
        "exists": value is not None,
        "sha256": value[0] if value else None,
        "bytes": value[1] if value else None,
        "kind": value[2] if value else None,
    }


def _execute(command: list[str], cwd: Path, timeout: Any) -> tuple[str, str, int, dict[str, Any] | None]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=os.name != "nt", creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(timeout=float(timeout) if timeout is not None else None)
        return stdout, stderr, process.returncode, None
    except subprocess.TimeoutExpired as error:
        termination = "best_effort_process_tree"
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, check=False, timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                termination = "best_effort_parent_only_fallback"
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    process.kill()
                    termination = "best_effort_parent_only_fallback"
        tail_out, tail_err = process.communicate()
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes): stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes): stderr = stderr.decode(errors="replace")
        # communicate() after TimeoutExpired may return the complete buffered
        # stream, so prefer it rather than duplicating the prefix.
        stdout = tail_out if tail_out else stdout
        stderr = tail_err if tail_err else stderr
        stderr += f"\nscience runner: command timed out after {timeout} seconds\n"
        return stdout, stderr, 124, {
            "type": "timeout", "message": str(error), "termination": termination,
        }


def run_experiment(repo: Path, experiment_id: str) -> tuple[int, Path]:
    exp = Experiment.load(repo / "experiments" / experiment_id)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = exp.root / "records" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_text = (exp.root / "experiment.yaml").read_text(encoding="utf-8")
    atomic_write_text(run_dir / "manifest.yaml", manifest_text)
    environment = _environment_snapshot()
    dump_json(run_dir / "environment.json", environment)
    command = [sys.executable if part == "{python}" else part for part in exp.command]
    # Inputs describe what the process was given, so freeze them before the
    # command gets an opportunity to mutate them.
    inputs = [_evidence_item(exp.root, relative) for relative in exp.inputs]
    started = datetime.now(timezone.utc)
    start_clock = time.monotonic()
    marker = run_dir / "run.in-progress.json"
    dump_json(marker, {
        "schema_version": 1, "run_id": run_id, "experiment_id": experiment_id,
        "status": "in_progress", "started_at": started.isoformat(), "command": command,
    })
    stdout = ""
    stderr = ""
    exit_code = -1
    execution_error: dict[str, str] | None = None
    timeout = exp.manifest.get("execution", {}).get("timeout_seconds")
    try:
        stdout, stderr, exit_code, execution_error = _execute(command, exp.root, timeout)
    except OSError as error:
        stderr = f"science runner: failed to start command: {error}\n"
        exit_code = 127
        execution_error = {"type": "startup_error", "message": str(error)}
    ended = datetime.now(timezone.utc)
    atomic_write_text(run_dir / "stdout.log", stdout)
    atomic_write_text(run_dir / "stderr.log", stderr)
    artifacts = [_evidence_item(exp.root, relative) for relative in exp.outputs]
    record = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "status": "succeeded" if exit_code == 0 and all(x["exists"] for x in inputs + artifacts) else "failed",
        "started_at": started.isoformat(), "ended_at": ended.isoformat(),
        "duration_seconds": round(time.monotonic() - start_clock, 6),
        "command": command, "exit_code": exit_code, "git_revision": _git_revision(repo),
        "manifest_sha256": sha256_text(manifest_text),
        "environment_sha256": sha256_text(json.dumps(environment, sort_keys=True)),
        "inputs": inputs, "artifacts": artifacts,
    }
    if execution_error:
        record["execution_error"] = execution_error
    dump_json(run_dir / "run.json", record)
    marker.unlink(missing_ok=True)
    return (0 if record["status"] == "succeeded" else (exit_code or 1)), run_dir
