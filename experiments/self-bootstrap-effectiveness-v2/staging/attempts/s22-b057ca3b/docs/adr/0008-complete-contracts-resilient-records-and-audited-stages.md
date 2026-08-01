---
id: adr-0008
status: accepted
date: 2026-07-12
last_validated: 2026-07-12
---

# ADR 0008: Complete contracts, resilient records, and audited stages

## Context

Campaign and handoff CLI paths still relied on semantic validators, review did not bind run records to
the local run schema, process crashes could leave ambiguous files, and stages could be edited without an
audit trail.

## Decision

Apply project-local pinned schemas to campaigns, handoffs, and run records before semantic checks. Preserve
legacy projects without local schemas rather than silently applying current packaged contracts.

Write snapshots, logs, markers, records, and reviews with same-directory atomic replacement. Create a
`run.in-progress.json` marker before process launch and remove it only after the final record is durable.
Review converts missing, malformed, incomplete, or structurally invalid evidence into an explicit fail
report. Timeout process-tree cleanup is best effort and recorded as such.

Make experiment stage changes through an explicit transition graph. Require actor, reason, and timezone-aware
timestamp; append each transition to `stage-history.jsonl`. Published and abandoned experiments are terminal.
Existing experiments without history may begin auditing from their current valid stage.

## Consequences

Structural errors stop deeper semantic validation to avoid misleading duplicate diagnostics. Atomic
replacement prevents partial individual files but is not a multi-file transaction, WORM storage, or a
guarantee across sudden power loss. Stage concurrency assumes one coordinating writer.

Acceptance evidence: contract, corrupt-record, lifecycle, CLI, fresh-wheel, run/review, repository,
documentation, and full-suite tests.
