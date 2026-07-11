---
id: changelog
status: active
last_validated: 2026-07-10
---

# Changelog

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
