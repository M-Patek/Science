import os
from pathlib import Path

import science_repo.environment as environment


def test_default_probe_rejects_executable_resolved_inside_cwd(monkeypatch):
    malicious = Path.cwd() / "docker"
    calls = []
    monkeypatch.setattr(environment.shutil, "which", lambda name, path=None: str(malicious))
    monkeypatch.setattr(environment, "_local_probe", lambda argv, timeout: calls.append(argv) or (0, "1.2.3", ""))

    snapshot = environment.capture_environment(environ={"PATH": str(Path.cwd())})

    # Python itself may be probed for packages, but the PATH-resolved program is not.
    assert not any(call and call[0] == str(malicious) for call in calls)
    assert snapshot["container"] == {"state": "unknown"}


def test_explicit_trusted_executable_is_absolute_and_used(monkeypatch):
    trusted = (Path.cwd() / ".test-trusted" / "docker.exe").resolve()
    calls = []
    monkeypatch.setattr(environment, "_local_probe", lambda argv, timeout: calls.append(argv) or (0, "Docker 26.1.0", ""))

    snapshot = environment.capture_environment(
        environ={"PATH": str(Path.cwd())}, trusted_executables={"docker": str(trusted)}
    )

    assert (str(trusted), "--version") in calls
    assert snapshot["container"]["runtime"] == "docker"


def test_supplied_identity_fields_are_not_claimed_as_observed():
    snapshot = environment.capture_environment(
        environ={}, probe=lambda argv, timeout: (127, "", ""),
        python_version="3.99", platform_value="test-platform",
    )
    assert snapshot["sources"] == {"python": "supplied", "platform": "supplied"}


def test_local_probe_cleans_environment_and_terminates_timed_out_group(monkeypatch):
    captured = {}

    class Process:
        pid = 1234
        returncode = None

        def communicate(self, timeout=None):
            if timeout is not None:
                raise environment.subprocess.TimeoutExpired(["trusted"], timeout)
            return "partial", "timed out"

        def kill(self):
            captured["killed"] = True

    def popen(argv, **kwargs):
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr(environment.subprocess, "Popen", popen)
    monkeypatch.setattr(environment, "_terminate_probe", lambda process: captured.__setitem__("tree", process.pid))
    code, _, _ = environment._local_probe((os.path.abspath("trusted"), "--version"), 0.01)

    assert code == 124
    assert captured["tree"] == 1234
    assert "PATH" not in captured["env"]
    assert captured["shell"] is False
    assert captured["start_new_session"] is (os.name == "posix")
