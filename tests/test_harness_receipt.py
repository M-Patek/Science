"""Tests for science_repo.harness_receipt."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from science_repo.harness_receipt import (
    HarnessReceipt,
    HarnessReceiptError,
    generate_cohort_runtime_registration,
    generate_receipt,
    verify_receipt,
)


class TestHarnessReceipt:
    """Unit tests for the HarnessReceipt dataclass."""

    def test_basic_receipt(self) -> None:
        receipt = HarnessReceipt(
            receipt_id="test-123",
            generated_at="2026-07-13T00:00:00Z",
            session_id="session-abc",
            session_id_unavailable_reason=None,
            model_name="claude-opus-4-8",
            model_unavailable_reason=None,
            agent_harness_and_version="claude-code_2-1-195_agent",
            harness_unavailable_reason=None,
            effort_setting="xhigh",
            effort_unavailable_reason=None,
            child_session=True,
            provider="anthropic",
            exact_model_or_version_id="claude-opus-4-8",
        )
        assert receipt.schema_version == 1
        assert receipt.receipt_id == "test-123"
        assert receipt.evidence_level == "host-observed-unsigned"
        assert receipt.attestation_policy == "harness-env-declarative"
        assert receipt.session_id == "session-abc"
        assert receipt.model_name == "claude-opus-4-8"
        assert receipt.receipt_sha256 != ""

    def test_receipt_hash_computed(self) -> None:
        receipt = HarnessReceipt(
            receipt_id="test-123",
            generated_at="2026-07-13T00:00:00Z",
            session_id="session-abc",
            session_id_unavailable_reason=None,
            model_name="claude-opus-4-8",
            model_unavailable_reason=None,
            agent_harness_and_version="claude-code_2-1-195_agent",
            harness_unavailable_reason=None,
            effort_setting="xhigh",
            effort_unavailable_reason=None,
            child_session=True,
            provider="anthropic",
            exact_model_or_version_id="claude-opus-4-8",
        )
        # Hash should be a valid 64-char hex string
        assert len(receipt.receipt_sha256) == 64
        assert all(c in "0123456789abcdef" for c in receipt.receipt_sha256)

    def test_receipt_hash_verified(self) -> None:
        receipt = HarnessReceipt(
            receipt_id="test-123",
            generated_at="2026-07-13T00:00:00Z",
            session_id="session-abc",
            session_id_unavailable_reason=None,
            model_name="claude-opus-4-8",
            model_unavailable_reason=None,
            agent_harness_and_version="claude-code_2-1-195_agent",
            harness_unavailable_reason=None,
            effort_setting="xhigh",
            effort_unavailable_reason=None,
            child_session=True,
            provider="anthropic",
            exact_model_or_version_id="claude-opus-4-8",
        )
        # Should not raise with correct hash
        receipt2 = HarnessReceipt(
            receipt_id="test-123",
            generated_at="2026-07-13T00:00:00Z",
            session_id="session-abc",
            session_id_unavailable_reason=None,
            model_name="claude-opus-4-8",
            model_unavailable_reason=None,
            agent_harness_and_version="claude-code_2-1-195_agent",
            harness_unavailable_reason=None,
            effort_setting="xhigh",
            effort_unavailable_reason=None,
            child_session=True,
            provider="anthropic",
            exact_model_or_version_id="claude-opus-4-8",
            receipt_sha256=receipt.receipt_sha256,
        )
        assert receipt2.receipt_sha256 == receipt.receipt_sha256

    def test_receipt_hash_mismatch(self) -> None:
        with pytest.raises(HarnessReceiptError, match="receipt_sha256 does not match"):
            HarnessReceipt(
                receipt_id="test-123",
                generated_at="2026-07-13T00:00:00Z",
                session_id="session-abc",
                session_id_unavailable_reason=None,
                model_name="claude-opus-4-8",
                model_unavailable_reason=None,
                agent_harness_and_version="claude-code_2-1-195_agent",
                harness_unavailable_reason=None,
                effort_setting="xhigh",
                effort_unavailable_reason=None,
                child_session=True,
                provider="anthropic",
                exact_model_or_version_id="claude-opus-4-8",
                receipt_sha256="a" * 64,
            )

    def test_mutual_exclusivity_violation(self) -> None:
        with pytest.raises(HarnessReceiptError, match="mutually exclusive"):
            HarnessReceipt(
                receipt_id="test-123",
                generated_at="2026-07-13T00:00:00Z",
                session_id="session-abc",
                session_id_unavailable_reason="reason",  # Both set!
                model_name="claude-opus-4-8",
                model_unavailable_reason=None,
                agent_harness_and_version="claude-code_2-1-195_agent",
                harness_unavailable_reason=None,
                effort_setting="xhigh",
                effort_unavailable_reason=None,
                child_session=True,
                provider="anthropic",
                exact_model_or_version_id="claude-opus-4-8",
            )

    def test_missing_reason(self) -> None:
        with pytest.raises(HarnessReceiptError, match="one of model or its unavailable_reason is required"):
            HarnessReceipt(
                receipt_id="test-123",
                generated_at="2026-07-13T00:00:00Z",
                session_id="session-abc",
                session_id_unavailable_reason=None,
                model_name=None,
                model_unavailable_reason=None,  # Both None!
                agent_harness_and_version="claude-code_2-1-195_agent",
                harness_unavailable_reason=None,
                effort_setting="xhigh",
                effort_unavailable_reason=None,
                child_session=True,
                provider="anthropic",
                exact_model_or_version_id="claude-opus-4-8",
            )

    def test_invalid_evidence_level(self) -> None:
        with pytest.raises(HarnessReceiptError, match="unsupported evidence level"):
            HarnessReceipt(
                receipt_id="test-123",
                generated_at="2026-07-13T00:00:00Z",
                evidence_level="cryptographic",
                session_id="session-abc",
                session_id_unavailable_reason=None,
                model_name="claude-opus-4-8",
                model_unavailable_reason=None,
                agent_harness_and_version="claude-code_2-1-195_agent",
                harness_unavailable_reason=None,
                effort_setting="xhigh",
                effort_unavailable_reason=None,
                child_session=True,
                provider="anthropic",
                exact_model_or_version_id="claude-opus-4-8",
            )

    def test_invalid_timestamp(self) -> None:
        with pytest.raises(HarnessReceiptError, match="generated_at must be a valid ISO timestamp"):
            HarnessReceipt(
                receipt_id="test-123",
                generated_at="not-a-timestamp",
                session_id="session-abc",
                session_id_unavailable_reason=None,
                model_name="claude-opus-4-8",
                model_unavailable_reason=None,
                agent_harness_and_version="claude-code_2-1-195_agent",
                harness_unavailable_reason=None,
                effort_setting="xhigh",
                effort_unavailable_reason=None,
                child_session=True,
                provider="anthropic",
                exact_model_or_version_id="claude-opus-4-8",
            )

    def test_to_dict_roundtrip(self) -> None:
        receipt = HarnessReceipt(
            receipt_id="test-123",
            generated_at="2026-07-13T00:00:00Z",
            session_id="session-abc",
            session_id_unavailable_reason=None,
            model_name="claude-opus-4-8",
            model_unavailable_reason=None,
            agent_harness_and_version="claude-code_2-1-195_agent",
            harness_unavailable_reason=None,
            effort_setting="xhigh",
            effort_unavailable_reason=None,
            child_session=True,
            provider="anthropic",
            exact_model_or_version_id="claude-opus-4-8",
        )
        d = receipt.to_dict()
        assert d["receipt_id"] == "test-123"
        assert d["schema_version"] == 1
        assert "receipt_sha256" in d


class TestGenerateReceipt:
    """Tests for generate_receipt."""

    def test_generates_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")

        receipt = generate_receipt()
        assert receipt.session_id == "test-session-id"
        assert receipt.model_name == "claude-test-model"
        assert receipt.exact_model_or_version_id is None
        assert receipt.agent_harness_and_version == "test-agent"
        assert receipt.effort_setting == "medium"
        assert receipt.provider is None
        assert receipt.evidence_level == "host-observed-unsigned"
        assert receipt.receipt_sha256 != ""

    def test_missing_env_records_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        monkeypatch.delenv("AI_AGENT", raising=False)
        monkeypatch.delenv("CLAUDE_EFFORT", raising=False)

        receipt = generate_receipt()
        assert receipt.session_id is None
        assert receipt.session_id_unavailable_reason is not None
        assert receipt.model_name is None
        assert receipt.model_unavailable_reason is not None
        assert receipt.agent_harness_and_version is None
        assert receipt.harness_unavailable_reason is not None
        assert receipt.effort_setting is None
        assert receipt.effort_unavailable_reason is not None

    def test_explicit_receipt_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")

        receipt = generate_receipt(receipt_id="custom-id")
        assert receipt.receipt_id == "custom-id"

    def test_explicit_now(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")

        now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
        receipt = generate_receipt(now=now)
        assert receipt.generated_at == "2026-07-13T12:00:00Z"


class TestVerifyReceipt:
    """Tests for verify_receipt."""

    def test_valid_receipt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")

        original = generate_receipt()
        d = original.to_dict()
        verified = verify_receipt(d)
        assert verified.receipt_id == original.receipt_id
        assert verified.receipt_sha256 == original.receipt_sha256

    def test_invalid_schema_version(self) -> None:
        # Must provide all required fields for the test to reach schema_version check
        with pytest.raises(HarnessReceiptError, match="schema_version must be 1"):
            verify_receipt({
                "schema_version": 2,
                "receipt_id": "x",
                "generated_at": "2026-07-13T00:00:00Z",
                "evidence_level": "host-observed-unsigned",
                "attestation_policy": "harness-env-declarative",
                "session_id": None,
                "session_id_unavailable_reason": "test",
                "child_session": None,
                "provider": None,
                "model_name": None,
                "exact_model_or_version_id": None,
                "model_unavailable_reason": "test",
                "agent_harness_and_version": None,
                "harness_unavailable_reason": "test",
                "effort_setting": None,
                "effort_unavailable_reason": "test",
                "receipt_sha256": "a" * 64,
            })

    def test_missing_fields(self) -> None:
        with pytest.raises(HarnessReceiptError, match="receipt fields mismatch"):
            verify_receipt({"schema_version": 1})

    def test_tampered_hash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")

        original = generate_receipt()
        d = original.to_dict()
        d["receipt_sha256"] = "a" * 64  # Tamper
        with pytest.raises(HarnessReceiptError, match="receipt_sha256 does not match"):
            verify_receipt(d)

    def test_rejects_wrong_field_type_before_hashing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")
        payload = generate_receipt().to_dict()
        payload["child_session"] = "true"
        with pytest.raises(HarnessReceiptError, match="child_session must be boolean"):
            verify_receipt(payload)


class TestCohortRuntimeRegistration:
    """Tests for generate_cohort_runtime_registration."""

    def test_generates_complete_registration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")

        reg = generate_cohort_runtime_registration(cohort_id="test-cohort")
        assert reg["cohort_id"] == "test-cohort"
        assert reg["status"] == "declarative-observed-dispatch-blocked"
        assert reg["evidence_level"] == "host-observed-unsigned"
        assert reg["provider"].startswith("unavailable:")
        assert "provider identity" in reg["provider"]
        assert reg["model_name"] == "claude-test-model"
        assert reg["exact_model_or_version_id"].startswith("unavailable:")
        assert reg["agent_harness_and_version"] == "test-agent"
        assert reg["sampling_parameters"] == "medium"
        assert reg["permission_and_network_policy"].startswith("unavailable:")
        assert "receipt_id" in reg
        assert "receipt_sha256" in reg
        assert "registered_at" in reg

    def test_includes_all_required_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
        monkeypatch.setenv("AI_AGENT", "test-agent")
        monkeypatch.setenv("CLAUDE_EFFORT", "medium")

        reg = generate_cohort_runtime_registration(cohort_id="test-cohort")
        # All required_model_metadata from cohort-v1.yaml should be present
        required = [
            "provider", "model_name", "exact_model_or_version_id",
            "inference_runtime_and_version", "agent_harness_and_version",
            "system_prompt_hash_or_unavailable_reason",
            "developer_prompt_hash_or_unavailable_reason",
            "tool_names_and_versions", "permission_and_network_policy",
            "sampling_parameters", "context_window_limit",
            "reported_input_output_cached_tokens_or_unavailable_reason",
        ]
        for field in required:
            assert field in reg, f"Missing required field: {field}"
