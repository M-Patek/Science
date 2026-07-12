from science_repo.platform_matrix import CAPABILITIES, capability_matrix, ci_job_plan


def test_unknown_is_not_ready_and_platform_aliases_are_normalized():
    matrix = capability_matrix(system="Darwin", python_version="3.12.1")
    assert matrix["platform"] == "macos"
    assert all(item["state"] == "unknown" for item in matrix["capabilities"].values())
    assert "core" in matrix["test_selection"]["ready"]
    assert "worktree" in matrix["test_selection"]["unknown"]
    assert "windows-junction" not in matrix["test_policy"]["optional"]


def test_three_platform_plans_are_deterministic_and_do_not_claim_execution():
    plan = ci_job_plan(platforms=("windows", "Darwin", "linux"), python_versions=("3.12",))
    assert plan == {
        "schema_version": 1,
        "evidence": "none",
        "jobs": [
            {"id": "linux-py3.12", "platform": "linux", "python": "3.12", "state": "planned"},
            {"id": "macos-py3.12", "platform": "macos", "python": "3.12", "state": "planned"},
            {"id": "windows-py3.12", "platform": "windows", "python": "3.12", "state": "planned"},
        ],
    }


def test_windows_missing_capability_degrades_without_hiding_optional_tests():
    observed = {name: True for name in CAPABILITIES}
    observed["filesystem.junction"] = False
    matrix = capability_matrix(system="windows", observations=observed, python_version="3.11")
    assert matrix["test_selection"]["blocked"] == ["windows-junction"]
    assert "filesystem-symlink" in matrix["test_selection"]["ready"]
    assert "windows-junction" in matrix["test_policy"]["optional"]


def test_injected_probe_failure_and_invalid_result_are_unknown():
    def probe(name):
        if name == "filesystem.fsync":
            return True
        if name == "filesystem.symlink":
            raise PermissionError("not permitted")
        return "yes"

    matrix = capability_matrix(system="linux", probe=probe)
    assert matrix["capabilities"]["filesystem.fsync"] == {"state": "available", "source": "probe"}
    assert matrix["capabilities"]["filesystem.symlink"]["state"] == "unknown"
    assert matrix["capabilities"]["tool.git_worktree"]["state"] == "unknown"


def test_explicit_observation_precedes_probe():
    calls = []
    matrix = capability_matrix(
        system="win32",
        observations={"tool.git_worktree": False},
        probe=lambda name: calls.append(name) or True,
    )
    assert "tool.git_worktree" not in calls
    assert matrix["capabilities"]["tool.git_worktree"] == {
        "state": "unavailable", "source": "observation"
    }
