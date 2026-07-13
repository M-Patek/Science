---
id: changelog
status: active
last_validated: 2026-07-10
---

# Changelog

## 2026-07-13 — Self-bootstrap cohort v2 pre-freeze baseline

- Added a new outcome-free `self-bootstrap-effectiveness-v2` design rather than rewriting either v1,
  explicitly classifying the design as prospective for v2 but informed by prior engineering pilots.
- Added a validated 52-task campaign with 24 explicit paired subject sessions in eight fail-closed waves,
  exact packet/attempt
  dependencies, baseline-negative and design review steps, blinded scoring, synthesis, and human gates.
- Preserved the header-only raw v1 file and planned any future controlled ingestion as raw v2; no v2
  observation, allocation, approval, freeze, or dispatch is claimed.
- Independent review rejected the first draft; the revision corrected output paths, ordinal/evidence
  contracts, numeric validation, raw immutability, and freeze inputs. A fresh re-review remains required
  before freeze, and the baseline-negative audit and human local-policy gate remain pending.
- Separated frozen registration materials from subject-visible baseline materials, preventing protocol
  and rubric leakage while retaining byte-complete preregistration provenance (ADR 0016).

## 2026-07-13 — Explicit local unsigned dispatch acceptance (T4)

- Added a second, deliberately weaker `local-host-observed-unsigned` trust track without changing the
  trusted-attestation or human-authorization boundary.
- Added two-phase, expiring per-cell acceptance bound to immutable preparation artifacts, logical and
  observed agent/session identities, a child harness receipt, actual workspace, and pinned Git HEAD.
- Kept cohort freezes and subject packets dispatch-blocked; local acceptance is a separate overlay and
  explicitly disclaims provider identity, immutable builds, host enforcement, and absolute isolation.
- Stopped inferring provider identity from a requested model environment alias and recorded ADR 0015.

## 2026-07-13 — Pilot evidence repair and explicit evidence roots (T4)

- Preserved five privately executed engineering pilots and three smoke run records, while independently
  classifying them as inadmissible formal cohort observations because required session evidence was not
  retained and T3/T4 summaries conflict.
- Added header-only `observations-v3.csv` plus provenance rather than rewriting the unverified v2 raw
  history; formal cohort observations remain at zero and dispatch remains blocked.
- Added a non-overwriting `science harness-receipt` diagnostic for `host-observed-unsigned` environment
  declarations without claiming an immutable provider build or trusted isolation.
- Replaced ambiguous missing-path fallback with explicit `scope: experiment|project` input binding.
  Run records and lineage now bind the exact project path whose bytes were hashed.
- Shipped the updated experiment schema in framework and generated-project schema packs, added regression
  tests, and recorded the workflow decision in ADR 0014.
- Made `scripts/refresh_registry.py` directly executable from the documented command and added explicit
  generated-project selection with `--project`.

## 2026-07-13

- Added strict 24-cell attempt capture and blinded-scoring verification after two independent no-ship
  reviews; authorization, scorer identity, time, packet coverage, and scoring context fail closed.
- Added atomic `subject-packets-build` and scoped self-study campaign closure semantics; recorded ADR 0013.

- Added fail-closed trusted host attestation and explicit 24-cell subject packet construction for the
  preregistered framework self-study.
- Independent review rejected the first attempt/blinding verifier; it remains unshipped design work.
- Recorded ADR 0012; these contracts do not claim host enforcement or authorize dispatch.

## 2026-07-13 - Formal self-research cohort preparation

- Added a fail-closed cohort freeze contract for twelve fixtures and twenty-four paired block-arm
  cells, with material hashes, a human-seed commitment, and externally supplied runtime identity.
- Added the first twelve four-stratum Science self-bootstrap fixtures without creating observations
  or execution authorization.
- Hardened the preregistered study design around immutable attempt evidence, blinded scoring, and
  explicit human and trusted-host gates.

## 2026-07-13 — Continuous self-bootstrap execution loop (T4)

- Connected dispatch audit to recoverable Campaign acceptance without implementing agent transport.
- Added automatic run lineage and made pinned lineage integrity a mechanical review gate.
- Added bounded, non-secret container/GPU/CI/HPC environment capture and reproduction comparison.
- Integrated trusted review plugins with minimal frozen evidence and fail-closed advisory policy.
- Added explicit migration apply with confirmation, backups, locking, WAL recovery, and rollback.
- Added an unattested-by-default external execution adapter with request-bound authorization verification.
- Added offline release manifests, fresh-wheel CLI coverage, and a planned cross-platform capability matrix.
- Preregistered the design-only self-bootstrap effectiveness study; no observations were recorded.

## 2026-07-12 — Self-bootstrap integrity and reproducibility (T4)

- Added pinned, path-safe data/run/code lineage validation and deterministic lineage digests.
- Added non-secret environment reproduction assessment with explicit unknown and unavailable states.
- Closed audited handoffs with hash-bound receipts, recoverable event-first state, gates, and retries.
- Added bounded review plugins that cannot manufacture human approval.
- Added read-only migration planning, repository diagnostics, and offline release manifests.

## 2026-07-12 — Complete contracts and resilient lifecycle records (T4)

- Applied pinned schemas to campaign, handoff, and run-record validation paths.
- Added atomic metadata/log/review writes and explicit in-progress run markers.
- Made review fail closed without crashing on missing, malformed, or incomplete evidence.
- Added best-effort cross-platform timeout process-tree cleanup with recorded termination scope.
- Added controlled experiment stage transitions with actor, reason, timestamp, and append-only history.
- Treated Windows lock-file sharing violations as contention so concurrent task claims retry deterministically.

## 2026-07-12 — Contract, provenance, and distribution integrity (T4)

- Enforced project-local JSON Schemas and source/package schema parity with contextual diagnostics.
- Added positive experiment timeouts, deterministic directory evidence hashes, and symlink rejection.
- Preserved complete failed run records for startup errors and timeouts; strengthened snapshot review.
- Added offline fresh-wheel verification of the complete independent-project CLI lifecycle.
- Packaged generated-project Agent skills and otherwise-empty contract directories explicitly.

## 2026-07-11 — Native delegation boundary and benchmark repair (T4)

- Defined dispatch envelopes and handoff audits around platform-native subagent capabilities instead of
  implementing another agent transport.
- Added the `run-campaign` Agent skill and documented the Main Agent integration boundary.
- Added a deterministic onboarding fixture with prepared validation and run/review tasks, leakage checks,
  and packaged schemas for isolated contract discovery.
- Independently reviewed and amended the onboarding preregistration before observations: 15 balanced
  sessions, task-stratified estimand, censoring/deviation rules, double scoring, and token missingness.
- Added immutable empty observations v2 and a conforming analysis implementation; execution remains
  blocked pending committed fixture/revision and exact runtime registration.

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
