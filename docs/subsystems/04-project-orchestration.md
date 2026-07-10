---
id: 04-project-orchestration
status: experimental
last_validated: 2026-07-10
code_anchors:
  - science_repo/cli.py:cmd_init
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

