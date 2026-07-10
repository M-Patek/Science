---
id: constitution
status: accepted
last_validated: 2026-07-10
---

# Scientific Repository Constitution

1. **Claims need lineage.** Every result points to an input, implementation, run, or citation.
2. **Raw evidence is append-only.** Corrections create a new version; they do not erase history.
3. **Intent precedes outcome.** Hypotheses and acceptance criteria are recorded before analysis.
4. **Runs are immutable observations.** A changed environment or command creates a new run ID.
5. **Review is independent and scoped.** Actor and critic roles are distinct; reviewer limits are explicit.
6. **Local by default, permissioned outward.** New resources, secrets, cost, and sensitive data require a human.
7. **Failure is data.** Failed and negative runs remain discoverable and must not be silently discarded.
8. **Progressive disclosure beats giant prompts.** Index → subsystem → source minimizes stale context.
9. **Projects pin contracts.** Framework upgrades never silently reinterpret an existing scientific record.
10. **Platform is replaceable.** Repository files remain the portable source of truth.

Violating a rule requires a new ADR with rationale, blast radius, and migration/rollback plan.
