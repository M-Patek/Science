---
id: adr-0009
status: accepted
date: 2026-07-12
last_validated: 2026-07-12
---

# ADR 0009: Integrity services for self-bootstrap development

## Context

Self-bootstrap development lacked first-class lineage, environment comparison, durable handoff
acceptance, safe review extension, and explicit upgrade planning.

## Decision

Add a pinned lineage contract; compare captured environments without exposing arbitrary values; accept
handoffs only with content-bound audit receipts through a recoverable event-first coordinator; restrict
review plugins to trusted mechanical or scientific-advisory checks; and keep contract migrations
read-only until a separately reviewed apply protocol exists. Add diagnostic and offline release-integrity
services without claims of scientific truth, human approval, signing, or vulnerability assessment.

## Consequences

The framework has a tighter audited feedback loop around native subagents without replacing host agent
transport. Local logs and locks are not distributed consensus or WORM storage. Human scientific and
migration review remain mandatory.
