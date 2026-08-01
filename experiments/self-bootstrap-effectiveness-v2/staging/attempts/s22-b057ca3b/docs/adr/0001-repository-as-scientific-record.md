---
id: adr-0001
status: accepted
last_validated: 2026-07-10
next_review: 2027-01-10
---

# ADR 0001 — Repository as Scientific Record

## Context

Scientific workflows fragment across chat, notebooks, scripts, databases, clusters, figures, and prose.
Agents amplify both productivity and the risk of generating unauditable but plausible output.

## Decision

Use a filesystem-first experiment directory as the durable record. A small manifest declares intent and
execution; append-only run directories capture provenance; artifacts retain their generating code; actor
and reviewer roles remain separate. Interfaces may be added, but files stay portable and inspectable.

## Consequences

The system works with git, local machines, SSH/HPC mounts, and multiple agents. It is easy to audit and
harder to hide failures. Large data need external storage references; concurrent registry writes and rich
queries will eventually need a transactional index.

