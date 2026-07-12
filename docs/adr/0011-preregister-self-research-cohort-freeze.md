---
id: adr-0011
status: accepted
date: 2026-07-13
last_validated: 2026-07-13
---

# ADR 0011: Freeze self-research cohorts before subject dispatch

## Decision

A formal self-research cohort preparation must freeze twelve versioned fixtures, their baseline materials, a
human-supplied randomization-seed commitment, twenty-four paired block-arm cells, and static runtime
identity evidence before any subject attempt. The immutable freeze says explicitly that it contains
no authorization and no observation. Conflicting rewrites fail closed.

Runtime receipts supplied by a caller are content-bound but not thereby trusted, so this preparation
artifact is marked dispatch-blocked. A separate trusted host verifier and human execution gate remain
mandatory before dispatch.

## Consequences

Structural campaign validity can no longer be treated as evidence that a study is executable.
Fixture preparation and deterministic allocation are reproducible, while model identity, workspace
isolation, execution authorization, blinded scoring, and publication remain independent boundaries.
