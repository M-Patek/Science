---
id: adr-0012
status: accepted
date: 2026-07-13
last_validated: 2026-07-13
---

# Fail-closed boundaries for self-study dispatch

## Decision

Formal self-study dispatch first requires two independently checkable artifacts: a trusted-host attestation
receipt and an explicit 24-cell subject-packet set. Attempt/blinding verification is deliberately not
accepted until it can avoid self-reported authorization, blinding, scorer identity, and timing.
Agent-provided booleans or identity strings never open a gate. Receipts bind the frozen cohort and the
relevant request, scope, subject, trust root, and expiry. Every cell gets fresh session/worktree/context
identities. The remaining attempt and scoring boundary must later provide trusted content, identity, and
time bindings before it may open dispatch.

## Consequences

The repository can prepare and reject malformed material without claiming that it spawned agents or
authenticated the host. A host integration must still supply verifiable receipts and isolation evidence.
Until then, the preregistered cohort remains non-executable and produces no observations. Independent
review rejected the initial attempt/blinding verifier, so it is intentionally excluded from this ADR.
