---
id: adr-0010
status: accepted
date: 2026-07-13
last_validated: 2026-07-13
---

# ADR 0010: Close the continuous self-bootstrap loop without owning agent transport

## Context

The framework could describe delegation and validate handoffs, but routine self-development still needed
manual state stitching. New lineage, migration, plugin, and remote-execution boundaries also required a
single trust model.

## Decision

Keep native agent lifecycle in the host. Join deterministic dispatch audit to a recoverable local
coordinator through content-bound receipts. Emit and mechanically review pinned lineage for new runs.
Treat plugin findings as trusted in-process advice, not human approval. Require explicit confirmation,
backups, locking, and recovery for contract migration. Treat all caller authorization fields as
unattested; only a trusted host verifier may authorize external, paid, private-data, or instrument work.

## Consequences

Main Agents can run an end-to-end audited development loop while Science remains transport-neutral.
Local filesystem logs are not distributed consensus or WORM storage. Declared command-file lineage is
not complete software provenance. Dry-run cloud planning and a valid schema do not authenticate a
provider, user, or approval. Human domain review and publication authorization remain external gates.
