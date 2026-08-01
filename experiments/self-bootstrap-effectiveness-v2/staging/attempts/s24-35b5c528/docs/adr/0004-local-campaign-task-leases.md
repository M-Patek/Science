---
id: adr-0004
status: accepted
date: 2026-07-11
last_validated: 2026-07-11
---

# ADR 0004: Local capability-based campaign task leases

## Context

Validated DAGs and disjoint write scopes make concurrent dispatch describable, but they do not prevent
two workers from claiming the same task or an expired worker from submitting as the current owner.

## Decision

Provide a runtime-neutral local reference implementation using per-task exclusive locks, atomic state
replacement, expiring leases, opaque capability tokens, heartbeats, releases, attempt counters, and an
append-only JSONL audit. Require handoffs to bind to the campaign task and remain inside its declared
write scope. Expose these operations through explicit CLI commands.

Runtime state is operational coordination data under `campaigns/<id>/runtime/` and is ignored by Git.
Scientific evidence and accepted handoffs remain versioned artifacts. Tokens must not be committed or
treated as authentication beyond the local coordinator.

## Consequences

This supports auditable single-host coordination and crash recovery without prescribing a cloud
scheduler. State replacement and audit append are not a cross-file crash transaction. The file runtime
does not provide distributed consensus, sandbox enforcement, or protection against a malicious local
worker; those require a future backend contract.

Acceptance evidence: runtime, concurrency, handoff, and CLI tests plus repository validation,
documentation checks, campaign validation, and the full test suite.
