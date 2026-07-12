"""Explicit, fail-closed extension point for review checks.

Plugins registered here are trusted in-process assistants. There is no process
isolation or timeout, and this API is not a security boundary. Their output is
evidence for a review decision; it is never scientific truth or human approval.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal


ReviewStatus = Literal["pass", "fail", "unknown"]
ReviewerKind = Literal["mechanical", "scientific-advisory"]
MAX_CHECKS_PER_PLUGIN = 100
REVIEW_SCOPE = (
    "plugin checks are advisory evidence; mechanical checks do not establish scientific truth "
    "or human approval"
)


def _freeze(value: Any) -> Any:
    """Return a recursively immutable, detached evidence view."""
    if isinstance(value, Mapping):
        return MappingProxyType({deepcopy(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return deepcopy(value)


@dataclass(frozen=True)
class PluginCheck:
    """A structured check returned by a registered plugin."""

    check_id: str
    status: ReviewStatus
    evidence_refs: tuple[str, ...] = ()
    detail: str | None = None


PluginCallback = Callable[[Mapping[str, Any]], PluginCheck | Sequence[PluginCheck]]


@dataclass(frozen=True)
class _Registration:
    plugin_id: str
    reviewer_kind: ReviewerKind
    callback: PluginCallback


class ReviewPluginRegistry:
    """Registry for trusted callbacks; it provides no isolation, timeout, or safety boundary."""

    def __init__(self) -> None:
        self._plugins: dict[str, _Registration] = {}

    def register(
        self,
        plugin_id: str,
        callback: PluginCallback,
        *,
        reviewer_kind: ReviewerKind = "mechanical",
    ) -> None:
        if not plugin_id or not plugin_id.strip():
            raise ValueError("plugin_id must be a non-empty string")
        if plugin_id in self._plugins:
            raise ValueError(f"duplicate review plugin id: {plugin_id}")
        if reviewer_kind not in {"mechanical", "scientific-advisory"}:
            raise ValueError(f"unsupported reviewer kind: {reviewer_kind}")
        if not callable(callback):
            raise TypeError("review plugin callback must be callable")
        self._plugins[plugin_id] = _Registration(plugin_id, reviewer_kind, callback)

    def run(self, evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Run all plugins in stable order and convert errors to failed checks."""
        results: list[dict[str, Any]] = []
        seen_check_ids: set[str] = set()
        for plugin_id in sorted(self._plugins):
            registration = self._plugins[plugin_id]
            try:
                plugin_results: list[dict[str, Any]] = []
                plugin_check_ids: set[str] = set()
                output = registration.callback(_freeze(evidence))
                if isinstance(output, PluginCheck):
                    checks = [output]
                else:
                    iterator = iter(output)
                    checks = []
                    for _ in range(MAX_CHECKS_PER_PLUGIN + 1):
                        try:
                            checks.append(next(iterator))
                        except StopIteration:
                            break
                    if len(checks) > MAX_CHECKS_PER_PLUGIN:
                        raise ValueError(
                            f"plugin exceeded maximum of {MAX_CHECKS_PER_PLUGIN} checks"
                        )
                if not checks:
                    raise ValueError("plugin returned no checks")
                for check in checks:
                    if not isinstance(check, PluginCheck):
                        raise TypeError("plugin output must contain PluginCheck values")
                    qualified_id = f"{plugin_id}:{check.check_id}"
                    duplicate = qualified_id in seen_check_ids or qualified_id in plugin_check_ids
                    if not check.check_id or duplicate:
                        raise ValueError(f"duplicate or empty check id: {check.check_id!r}")
                    if check.status not in {"pass", "fail", "unknown"}:
                        raise ValueError(f"invalid check status: {check.status}")
                    plugin_check_ids.add(qualified_id)
                    plugin_results.append(self._serialize(registration, check))
                seen_check_ids.update(plugin_check_ids)
                results.extend(plugin_results)
            except Exception:  # A broken critic must not crash or leak details into the report.
                failure_id = f"{plugin_id}:plugin_error"
                results.append({
                    "id": failure_id,
                    "plugin_id": plugin_id,
                    "status": "fail",
                    "passed": False,
                    "reviewer_kind": registration.reviewer_kind,
                    "evidence_refs": [],
                    "error_code": "review_plugin_failed",
                    "detail": "registered review plugin failed closed",
                    "scope": REVIEW_SCOPE,
                })
        return sorted(results, key=lambda item: item["id"])

    @staticmethod
    def _serialize(registration: _Registration, check: PluginCheck) -> dict[str, Any]:
        return {
            "id": f"{registration.plugin_id}:{check.check_id}",
            "plugin_id": registration.plugin_id,
            "status": check.status,
            "passed": check.status == "pass",
            "reviewer_kind": registration.reviewer_kind,
            "evidence_refs": list(check.evidence_refs),
            **({"detail": check.detail} if check.detail is not None else {}),
            "scope": REVIEW_SCOPE,
        }
