from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import dump_json, sha256_file, sha256_text
from .models import Experiment


def _git_revision(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _environment_snapshot() -> dict[str, Any]:
    packages = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"], text=True, capture_output=True, check=False
    ).stdout.splitlines()
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


def run_experiment(repo: Path, experiment_id: str) -> tuple[int, Path]:
    exp = Experiment.load(repo / "experiments" / experiment_id)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = exp.root / "records" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil_manifest = (exp.root / "experiment.yaml").read_text(encoding="utf-8")
    (run_dir / "manifest.yaml").write_text(shutil_manifest, encoding="utf-8")
    environment = _environment_snapshot()
    command = [sys.executable if part == "{python}" else part for part in exp.command]
    started = datetime.now(timezone.utc)
    start_clock = time.monotonic()
    result = subprocess.run(command, cwd=exp.root, text=True, capture_output=True, check=False)
    ended = datetime.now(timezone.utc)
    (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    artifacts = []
    for relative in exp.outputs:
        path = exp.root / relative
        artifacts.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
                "bytes": path.stat().st_size if path.is_file() else None,
            }
        )
    inputs = []
    for relative in exp.inputs:
        path = exp.root / relative
        inputs.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
                "bytes": path.stat().st_size if path.is_file() else None,
            }
        )
    record = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "status": "succeeded"
        if result.returncode == 0
        and all(item["exists"] for item in inputs)
        and all(item["exists"] for item in artifacts)
        else "failed",
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": round(time.monotonic() - start_clock, 6),
        "command": command,
        "exit_code": result.returncode,
        "git_revision": _git_revision(repo),
        "manifest_sha256": sha256_file(exp.root / "experiment.yaml"),
        "environment_sha256": sha256_text(json.dumps(environment, sort_keys=True)),
        "inputs": inputs,
        "artifacts": artifacts,
    }
    dump_json(run_dir / "environment.json", environment)
    dump_json(run_dir / "run.json", record)
    exit_code = 0 if record["status"] == "succeeded" else (result.returncode or 1)
    return exit_code, run_dir
