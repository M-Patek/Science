from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


ASSETS = Path(__file__).resolve().parent / "assets"
FIXTURE_ID = "generated-project-onboarding-v1"


def _replace_text(root: Path, replacements: dict[str, str]) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token, value in replacements.items():
            text = text.replace(token, value)
        path.write_text(text, encoding="utf-8", newline="\n")


def build_onboarding_fixture(target: Path) -> str:
    """Create the frozen onboarding project and return its canonical tree hash.

    The caller must provide an absent or empty directory.  No clock, platform, or
    repository state is incorporated, so identical framework bytes produce an
    identical fixture hash.
    """
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"fixture target is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ASSETS / "project", target, dirs_exist_ok=True)
    shutil.copytree(ASSETS / "experiment", target / "templates" / "experiment")
    shutil.copytree(ASSETS / "benchmark" / FIXTURE_ID, target, dirs_exist_ok=True)
    _replace_text(
        target,
        {
            "{{PROJECT_NAME}}": "Framework onboarding benchmark",
            "{{PROJECT_ID}}": "framework-onboarding-benchmark",
            "{{OWNER}}": "benchmark-coordinator",
            "{{DATE}}": "2026-07-10",
        },
    )
    return canonical_tree_sha256(target)


def canonical_tree_sha256(root: Path) -> str:
    """Hash relative POSIX paths, file sizes, and bytes in sorted order."""
    digest = hashlib.sha256()
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
