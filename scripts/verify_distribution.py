"""Offline source-to-wheel distribution smoke test.

This intentionally builds without isolation or dependency downloads.  The disposable
venv inherits only third-party runtime dependencies from the invoking interpreter;
Science Workbench itself must be loaded from the newly built wheel.
"""

from __future__ import annotations

import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ASSETS = {
    "science_repo/assets/project/schemas/experiment.schema.json",
    "science_repo/assets/project/schemas/campaign.schema.json",
    "science_repo/assets/project/schemas/handoff.schema.json",
    "science_repo/assets/project/schemas/project.schema.json",
    "science_repo/assets/project/schemas/run.schema.json",
    "science_repo/assets/project/.agents/skills/run-experiment/SKILL.md",
    "science_repo/assets/experiment/experiment.yaml",
    "science_repo/assets/experiment/src/run.py",
}


def run(*args: str | Path, cwd: Path, env: dict[str, str] | None = None) -> str:
    command = [str(arg) for arg in args]
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def verify(work_root: Path) -> dict[str, str]:
    work_root.mkdir(parents=True, exist_ok=True)
    process_env = os.environ.copy()
    process_temp = work_root / "tmp"
    process_temp.mkdir()
    process_env.update({"TMP": str(process_temp), "TEMP": str(process_temp)})
    dist = work_root / "dist"
    # Invoke the declared PEP 517 backend directly. This remains offline and
    # avoids frontends that insist on an OS temp directory inaccessible in
    # some managed sandboxes.
    run(
        sys.executable,
        "-c",
        "from setuptools import build_meta; build_meta.build_wheel(r'" + str(dist) + "')",
        cwd=ROOT,
        env=process_env,
    )
    wheels = list(dist.glob("science_workbench-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel, found: {wheels}")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        missing = sorted(EXPECTED_ASSETS - names)
        if missing:
            raise RuntimeError(f"wheel is missing package data: {missing}")
        entry_points = archive.read(
            next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        ).decode()
        if "science = science_repo.cli:main" not in entry_points:
            raise RuntimeError("wheel does not expose the science console script")

    environment = work_root / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    science = environment / ("Scripts/science.exe" if os.name == "nt" else "bin/science")
    run(python, "-m", "pip", "install", "--no-deps", wheel, cwd=work_root)
    clean_env = process_env.copy()
    clean_env.pop("PYTHONPATH", None)
    clean_env["PYTHONNOUSERSITE"] = "1"
    imported = run(
        python,
        "-c",
        "import pathlib,science_repo; print(pathlib.Path(science_repo.__file__).resolve())",
        cwd=work_root,
        env=clean_env,
    ).strip()
    if (ROOT / "science_repo") == Path(imported).parent:
        raise RuntimeError(f"science_repo leaked from source tree: {imported}")

    project = work_root / "independent-project"
    run(science, "init", project, "--name", "Distribution Smoke", "--id", "dist-smoke", cwd=work_root, env=clean_env)
    for relative in (
        "schemas/experiment.schema.json",
        ".agents/skills/run-experiment/SKILL.md",
        "templates/experiment/experiment.yaml",
    ):
        if not (project / relative).is_file():
            raise RuntimeError(f"generated project is missing {relative}")
    manifest = (project / "science-project.yaml").read_text(encoding="utf-8")
    if "version: 0.2.0.dev0" not in manifest:
        raise RuntimeError("generated project's framework version is not pinned to wheel version")

    run(science, "--project", project, "validate", cwd=work_root, env=clean_env)
    run(science, "--project", project, "new", "smoke-exp", "--title", "Smoke", cwd=work_root, env=clean_env)
    (project / "experiments" / "smoke-exp" / "data" / "raw" / "input.csv").write_text(
        "value\n1\n", encoding="utf-8"
    )
    run(science, "--project", project, "validate", cwd=work_root, env=clean_env)
    run(science, "--project", project, "run", "smoke-exp", cwd=work_root, env=clean_env)
    run(science, "--project", project, "review", "smoke-exp", cwd=work_root, env=clean_env)

    campaign = project / "campaigns" / "smoke-campaign"
    campaign.mkdir()
    (campaign / "campaign.yaml").write_text(
        "schema_version: 1\nid: smoke-campaign\ntitle: Smoke\n"
        "objective: Verify the packaged campaign contract.\nstatus: approved\nowner: verifier\n"
        "tasks:\n  - id: smoke-task\n    role: operator\n    depends_on: []\n"
        "    inputs: []\n    outputs: [evidence/smoke.json]\n"
        "    write_scope: [evidence]\n    review_required: false\n    human_gate: false\n",
        encoding="utf-8",
    )
    run(science, "--project", project, "campaign-validate", "smoke-campaign", cwd=work_root, env=clean_env)
    return {"wheel": wheel.name, "science_repo": imported, "project": str(project)}


def main() -> int:
    # A fixed, caller-cleanable directory avoids platform sandbox policies that
    # make OS-created random temporary directories unreadable to child processes.
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", type=Path, default=ROOT / ".distribution-smoke")
    args = parser.parse_args()
    work_root = args.work_root.resolve()
    if work_root.exists() and any(work_root.iterdir()):
        raise SystemExit(f"distribution work directory is not empty; remove it first: {work_root}")
    print(json.dumps(verify(work_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
