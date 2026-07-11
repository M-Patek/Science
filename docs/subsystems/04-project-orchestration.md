---
id: 04-project-orchestration
status: experimental
last_validated: 2026-07-10
code_anchors:
  - science_repo/cli.py:cmd_init
  - science_repo/campaign.py:validate_campaign
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

Current boundary: schemas and DAG validation exist, but leases, heartbeat, worktrees, retries, message
transport, and transactional task claiming remain future runtime work.

Unordered campaign tasks are assumed to be concurrently dispatchable. Their repository-relative
`write_scope` paths must therefore be disjoint; tasks that intentionally reuse a scope must be ordered
by an explicit dependency. Validation rejects absolute paths and traversal segments, but it does not
enforce filesystem access at runtime.
