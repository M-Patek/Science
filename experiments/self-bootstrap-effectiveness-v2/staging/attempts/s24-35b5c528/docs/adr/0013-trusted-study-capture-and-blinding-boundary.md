---
id: adr-0013
status: accepted
date: 2026-07-13
last_validated: 2026-07-13
---

# Trusted study capture and blinding boundary

## Decision

Self-study observation verification requires exact coverage of the 24 frozen cells, strict typed bundle
content, ledger-bound session/worktree/context identities, trusted content-bound authorization, canonical
evidence hashes, and the preregistered ordinal/replacement policy. Blinded scoring requires a bijection
between 24 verified attempt hashes and 24 opaque packets, a mechanical prohibited-field/content audit,
two trusted scorer identities, identical packet and scoring-context commitments, and trusted aware
commit-before-reveal timestamps.

Subject packet production is exposed through an atomic, idempotent CLI command. Campaign closure applies
the dogfood semantic checks only to the explicitly identified framework self-study project and campaign;
generic projects with similarly named tasks are unaffected. The registration step accepts only the
schema-required dispatch-blocked preparation artifact. Trusted activation remains a later host boundary.

## Consequences

Malformed, partial, duplicated, self-authorized, path-escaping, or prematurely revealed study material
fails closed. These verifiers establish artifact consistency, not scientific truth, host execution, or
human publication approval. Formal subject dispatch remains blocked until actual trusted receipts and
host isolation evidence exist.
