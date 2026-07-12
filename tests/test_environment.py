import json

import pytest

from science_repo.environment import capture_environment


class FakeProbe:
    def __init__(self, replies=None):
        self.replies = replies or {}
        self.calls = []

    def __call__(self, argv, timeout):
        self.calls.append((tuple(argv), timeout))
        return self.replies.get(argv[0], (127, "", ""))


def test_capture_is_deterministic_and_redacts_secrets():
    secret = "token@private.example/job-123"
    probe = FakeProbe({
        "docker": (0, f"Docker version 27.1.2, build {secret}", ""),
        "nvidia-smi": (0, f"550.54\n{secret}", ""),
    })
    env = {"GITHUB_ACTIONS": secret, "SLURM_JOB_ID": secret, "CUDA_VISIBLE_DEVICES": secret}
    first = capture_environment(environ=env, probe=probe, python_version="3.12.1", platform_value="linux-x86_64")
    second = capture_environment(environ=env, probe=probe, python_version="3.12.1", platform_value="linux-x86_64")
    encoded = json.dumps(first, sort_keys=True)
    assert first == second
    assert secret not in encoded
    assert first["container"] == {"state": "observed", "runtime": "docker", "version": "27.1.2"}
    assert first["gpu"] == {"state": "observed", "vendor": "nvidia", "driver": "550.54"}
    assert first["orchestration"] == {"state": "observed", "kind": "ci", "provider": "github"}


def test_linux_and_windows_are_explicitly_injectable():
    no_tools = FakeProbe()
    linux = capture_environment(environ={}, probe=no_tools, platform_value="linux-aarch64", python_version="3.11.9")
    windows = capture_environment(environ={}, probe=no_tools, platform_value="windows-amd64", python_version="3.11.9")
    assert linux["platform"] == "linux-aarch64"
    assert windows["platform"] == "windows-amd64"
    assert linux["container"] == linux["gpu"] == {"state": "unknown"}


def test_presence_only_hpc_and_gpu_fallback():
    snapshot = capture_environment(
        environ={"SLURM_JOB_ID": "private-42", "ROCR_VISIBLE_DEVICES": "0"},
        probe=FakeProbe(), platform_value="linux-x86_64",
    )
    assert snapshot["orchestration"] == {"state": "observed", "kind": "hpc", "scheduler": "slurm"}
    assert snapshot["gpu"] == {"state": "observed", "vendor": "amd"}
    assert snapshot["selected_environment"] == {"ROCR_VISIBLE_DEVICES": "present", "SLURM_JOB_ID": "present"}


def test_kubernetes_presence_does_not_capture_private_endpoint():
    snapshot = capture_environment(
        environ={"KUBERNETES_SERVICE_HOST": "10.20.30.40.internal"},
        probe=FakeProbe(), platform_value="linux-x86_64",
    )
    assert snapshot["container"] == {"state": "observed", "runtime": "kubernetes"}
    assert "10.20.30.40" not in json.dumps(snapshot)


def test_packages_reject_private_references_and_malicious_lines():
    import sys
    probe = FakeProbe({sys.executable: (0, "Safe_Pkg==1.2.3\nprivate @ https://user:token@host/x\nBad==1.0; x\n", "")})
    snapshot = capture_environment(environ={}, probe=probe, platform_value="windows-amd64")
    assert snapshot["packages"] == ["safe-pkg==1.2.3"]
    assert "token" not in json.dumps(snapshot)


def test_probe_exceptions_and_invalid_results_are_unknown():
    def broken(argv, timeout):
        raise RuntimeError("secret")
    snapshot = capture_environment(environ={}, probe=broken, platform_value="linux-x86_64")
    assert snapshot["packages"] == []
    assert snapshot["container"] == snapshot["gpu"] == {"state": "unknown"}


@pytest.mark.parametrize("timeout", [0, -1, 10.1])
def test_timeout_is_bounded(timeout):
    with pytest.raises(ValueError):
        capture_environment(environ={}, probe=FakeProbe(), timeout=timeout)
