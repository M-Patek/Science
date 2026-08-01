---
id: adr-0005
status: accepted
date: 2026-07-11
last_validated: 2026-07-11
---

# ADR 0005: Deterministic campaign scheduling and session isolation

## Context

Task leases prevent duplicate ownership, but a coordinator still needs a reproducible way to decide
which DAG nodes are ready, prepare outcome-blind cohorts, and give each worker the exact registered Git
revision without unsafe directory manipulation.

## Decision

Keep scheduling decisions pure: combine a validated campaign with immutable runtime snapshots and a
bounded retry policy to classify every task. Generate cohort assignments deterministically before
outcomes exist and verify registered material hashes, revision pins, metadata, coverage, and isolation
rules.

Create agent sessions as detached Git worktrees beneath an explicit root. Resolve the requested revision
to a full commit, verify the resulting HEAD, persist an atomic audit record, and remove sessions only
through `git worktree remove` after rechecking the recorded boundary. Never recursively delete a path.

## Consequences

The framework can now prepare auditable work for an external Main Agent or scheduler, but it still does
not own a model-provider transport or autonomously spawn agents. Worktree creation is local Git state and
requires the caller's filesystem authorization. A frozen cohort remains unchanged when later framework
revisions add orchestration features.

Acceptance evidence: scheduler, cohort, workspace boundary, failure, CLI, repository, documentation, and
full-suite tests.
