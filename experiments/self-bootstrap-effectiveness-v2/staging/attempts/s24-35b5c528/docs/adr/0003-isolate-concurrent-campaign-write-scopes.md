---
id: adr-0003
status: accepted
date: 2026-07-11
last_validated: 2026-07-11
---

# ADR 0003: Isolate concurrent campaign write scopes

## Context

Campaign tasks declare `write_scope`, but DAG validation previously accepted two unordered tasks whose
scopes were identical or nested. A main agent could therefore safely validate a campaign and then send
both tasks to subagents that mutate the same files. The resulting outcome depends on timing and cannot
be reliably attributed to either handoff.

## Decision

Treat unordered tasks as potentially concurrent. Reject a campaign when their normalized,
repository-relative write scopes overlap at a path-segment boundary. Tasks may deliberately reuse a
scope only when the dependency DAG orders them. Reject absolute scopes and scopes containing `.` or
`..` segments.

This is validation only: it does not claim paths, enforce filesystem access, or replace future leases
and worktree isolation.

## Compatibility and evidence

This tightens validation for campaigns that were previously accepted despite being unsafe to dispatch.
Such campaigns remain expressible by adding the intended dependency or separating their scopes. No
schema version changes and no existing manifest fields change.

Acceptance evidence: campaign unit tests cover unordered overlap, explicitly ordered reuse, unsafe
paths, cycles, and unknown dependencies; repository validation, documentation checks, and the full test
suite pass.
