---
name: run-campaign
description: Coordinate a validated Science Workbench campaign through the host platform's native subagents, with bounded scopes, structured handoffs, and independent review. Use when a main agent is asked to delegate or parallelize campaign tasks.
---

# Run Campaign

This skill is an Agent-friendly operating layer, not an agent transport. Science Workbench defines and
audits work; the host platform's native delegation primitive (for example `spawn_agent`) starts agents.

1. Read the root `AGENTS.md`, `docs/operations/dogfooding.md`, and the selected project's
   `science-project.yaml` and campaign manifest.
2. Validate the campaign, then inspect schedulable work:
   `science --project PROJECT campaign-validate CAMPAIGN` and
   `science --project PROJECT campaign-status CAMPAIGN`.
3. For each ready task, persist its dispatch packet before delegation:
   `science --project PROJECT dispatch-envelope CAMPAIGN TASK > ENVELOPE.json`.
4. Invoke a platform-native subagent with the envelope's prompt and task contract. Preserve its role,
   inputs, outputs, dependencies, and `write_scope`; do not broaden scope in transit.
5. Require the worker to return a JSON handoff matching `handoff_contract`, including truthful
   `complete`, `blocked`, or `failed` status and `changed_files` when files changed.
6. Audit the result before integration:
   `science --project PROJECT dispatch-audit CAMPAIGN ENVELOPE.json HANDOFF.json`.
   Treat audit failure as a failed integration boundary, not evidence of task completion.
7. Recompute `campaign-status` after accepted handoffs. Dispatch only tasks that are ready, and do not
   parallelize overlapping write scopes unless the validated dependency order makes them sequential.
8. Assign required review to an independent agent that did not execute or materially assist the work
   being reviewed. Give it the evidence and contracts, not an instruction to ratify the worker.
9. The main agent remains responsible for agent selection, native delegation, conflict resolution,
   integration, and the final scientific or engineering claim.

Never claim that Science Workbench itself spawned, supervised, or authenticated a subagent. The
dispatch envelope is deterministic data and the audit checks contract conformance; neither substitutes
for platform-native agent lifecycle controls or human domain review.
