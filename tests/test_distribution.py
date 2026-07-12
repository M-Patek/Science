from __future__ import annotations

from pathlib import Path
import shutil

from scripts.verify_distribution import verify


def test_built_wheel_supports_independent_project_lifecycle():
    work = Path(__file__).parent / "fixtures" / "distribution-work"
    shutil.rmtree(work, ignore_errors=True)
    try:
        result = verify(work)
        assert result["wheel"].endswith("-py3-none-any.whl")
        assert Path(result["science_repo"]).is_file()
        assert Path(result["project"]).is_dir()
    finally:
        shutil.rmtree(work, ignore_errors=True)
