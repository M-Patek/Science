---
id: 04-project-orchestration
status: experimental
last_validated: 2026-07-10
code_anchors:
  - science_repo/cli.py:cmd_init
  - science_repo/campaign.py:validate_campaign
  - science_repo/task_runtime.py:TaskRuntime
  - science_repo/handoff.py:validate_handoff
  - science_repo/scheduler.py:schedule_campaign
  - science_repo/workspace.py:WorkspaceManager
  - science_repo/cohort.py:validate_cohort
  - science_repo/cohort_freeze.py:build_cohort_freeze
  - science_repo/dispatch.py:create_dispatch_envelope
  - science_repo/closure.py:accept_dispatch_handoff
  - science_repo/coordinator.py:CampaignCoordinator
  - science_repo/migration_apply.py:apply_contract_migration
  - science_repo/execution_adapter.py:submit_execution
  - science_repo/benchmark.py:build_onboarding_fixture
  - schemas/project.schema.json
  - schemas/campaign.schema.json
  - schemas/handoff.schema.json
---

# 04 — Project and Agent Orchestration Contracts

The framework and research projects are separate products. `science init` creates an independent,
portable project pinned to a framework and contract version. Framework updates must not silently change
the meaning of an existing project.

A campaign is a DAG of bounded tasks. Each task declares dependencies, inputs, outputs, a write scope,
review requirement, and whether it crosses a human gate. Main agents coordinate; specialist agents work
only inside assigned scopes and return a structured handoff. The contract is runtime-neutral: Codex,
Claude, local workers, or a future cloud scheduler can implement it.

Current boundary: schemas, DAG validation, a local task lease reference runtime, pure scheduling and
bounded retries, audited worktree isolation, cohort preparation, and handoff validation exist. Model
transport and a distributed scheduler remain future work.

Science Workbench deliberately does not implement model transport or agent spawning. A deterministic
dispatch envelope is passed to the host's native agent capability; the returned handoff is rebound to
the authoritative campaign before integration. Generated projects include their pinned schema files so
contract discovery does not depend on access to framework source.

Unordered campaign tasks are assumed to be concurrently dispatchable. Their repository-relative
`write_scope` paths must therefore be disjoint; tasks that intentionally reuse a scope must be ordered
by an explicit dependency. Validation rejects absolute paths and traversal segments, but it does not
enforce filesystem access at runtime.

The local coordinator atomically claims a task with an expiring capability token. Only the current
worker/token pair may heartbeat or release it; an expired claim creates a new attempt. Every transition
is appended to an audit log. A returned handoff must identify the declared campaign task and role, and
its output paths must remain within that task's normalized `write_scope`.

Scheduling is an outcome-free decision over the manifest and lease snapshots. Cohort assignments are
generated before observations and checked for unique session, copy, and context identities. Session
workspaces pin and verify a full Git commit and can only be removed through a boundary-checked Git
worktree operation.

Self-research cohorts can now freeze exactly twelve fixture materials into twenty-four paired
block-arm cells. The freeze binds fixture and baseline bytes, commits to a human-supplied seed,
records an externally supplied runtime-identity receipt, and explicitly carries neither execution
authorization nor observations. Because the receipt is only structurally and content-bound checked,
the artifact remains explicitly dispatch-blocked until a trusted host verifier attests it.

## Audited closure and upgrades

The coordinator accepts only audit receipts bound to canonical handoffs, writes an event-first recovery log, and then materializes task state. Review and human gates fail closed. Contract migration is a deterministic read-only plan; `science doctor` is diagnostic only. Neither command silently upgrades projects.

Campaign closure now joins authoritative dispatch audit to recoverable coordinator state. Caller-provided
approval flags are unattested and cannot open a human gate. Explicit contract migration apply uses a
confirmation digest, backups, WAL recovery, locking, and caller-supplied schema bytes. The execution
adapter is transport-neutral: dry-run never executes, while real submission requires a trusted verifier
and a receipt bound to the complete request, resources, cost ceiling, scope, approver, and expiry.
