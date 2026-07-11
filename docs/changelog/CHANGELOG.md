---
id: changelog
status: active
last_validated: 2026-07-10
---

# Changelog

## 2026-07-11 — Deterministic self-research dispatch (T4)

- Added pure DAG scheduling with lease awareness, dependency-failure propagation, and bounded retries.
- Added frozen-cohort integrity validation and deterministic, outcome-blind assignment ledgers.
- Added audited detached-worktree creation with revision verification and boundary-checked Git cleanup.
- Exposed campaign status, cohort validation/planning, and workspace lifecycle commands through the CLI.

## 2026-07-11 — Local multi-agent coordination baseline (T4)

- Added atomic local task claiming, expiring capability leases, heartbeat, release, retry attempts, and
  append-only coordination audit events.
- Added campaign-bound handoff validation, including role and write-scope enforcement.
- Added CLI commands for task leases and handoff validation and ignored ephemeral campaign runtime state.
- Froze onboarding cohort v1 at framework revision `d62e38c` with independent writable copies, immutable
  prompts/hashes, a binary rubric, metadata requirements, and censoring rules; no observations were added.

## 2026-07-11 — Self-bootstrap campaign safety (T4)

- Reject unsafe or overlapping write scopes for campaign tasks that may run concurrently.
- Permit scope reuse only when the dependency DAG explicitly serializes the tasks.
- Isolate runner tests from the repository's append-only demonstration records.
- Ran the first read-only onboarding observation; it is censored because the frozen revision and
  writable-session requirements were not satisfied, so it is not part of the formal cohort.

## 2026-07-10 — Framework/project separation and orchestration contracts (T4)

- Added a versioned framework manifest and `science init` project generator.
- Added distributable project/experiment assets and pinned contract versions.
- Added campaign DAG and structured agent handoff schemas plus validation.
- Began dogfooding through an independently generated framework self-study project.
- Defined the local self-research loop: dogfood evidence feeds reviewed changes back into the framework,
  while the framework remains the sole final product.

## 2026-07-10 — Initial workbench (T4)

- Added the Agent boot/navigation protocol and scientific repository constitution.
- Added experiment template, JSON Schemas, registry, CLI, provenance runner, and mechanical reviewer.
- Added an executable deterministic demonstration and unit/integration tests.
- Validation target: repository checks, demo run/review, and pytest.
