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
