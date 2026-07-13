---
id: adr-0014
status: accepted
date: 2026-07-13
last_validated: 2026-07-13
---

# ADR 0014 — Require explicit evidence roots and separate pilots from formal observations

## Context

An engineering pilot declared project-level inputs using paths that were historically interpreted
relative to the experiment directory. A proposed fix retried missing paths against the project root.
That fallback made a typo or missing experiment input silently bind to unrelated project content and
caused lineage to name a different path from the bytes actually hashed.

Five onboarding pilot summaries were also appended directly to a formal raw observation file as passes,
although required transcripts, command logs, diffs, and subject-to-artifact bindings were absent and
some summaries contradicted one another.

## Decision

Contract-v1 input declarations default to `scope: experiment`. A project-level input must explicitly
declare `scope: project`. Run records carry the declared scope and canonical project path; lineage uses
that bound path. Missing inputs never trigger an alternative-root lookup. Outputs remain
experiment-relative in contract v1.

Pilot summaries are retained as engineering evidence but are not automatically admissible formal
observations. Raw corrections create a new version with provenance; prior raw versions and completed
run records are never rewritten. Unsigned harness environment receipts may describe a local runtime but
cannot, by themselves, establish an immutable provider build or open a dispatch gate.

## Consequences

- Existing manifests remain experiment-relative unless they explicitly opt into project scope.
- Generated projects ship the updated schema, and review recomputes evidence against the recorded scope.
- Historical pilot and negative-run evidence remains visible.
- Formal onboarding analysis restarts with an empty corrected raw-data version until admissible evidence
  is captured.
