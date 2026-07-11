---
id: adr-0006
status: accepted
date: 2026-07-11
last_validated: 2026-07-11
---

# ADR 0006: Wrap rather than replace native agent delegation

## Context

Codex, Claude, and other hosts already provide agent creation, communication, interruption, and result
collection. Reimplementing those capabilities inside Science Workbench would duplicate platform behavior
and incorrectly imply that repository contracts supervise or authenticate workers.

## Decision

Science Workbench generates deterministic dispatch envelopes from validated campaign tasks and audits
structured handoffs against both the envelope and authoritative campaign. The Main Agent continues to
use the host platform's native delegation primitives and remains responsible for agent selection,
lifecycle, integration, and independent review.

Provide a deterministic, subject-facing onboarding fixture for empirical evaluation. Generated projects
ship pinned schema files so isolated agents can locate the contracts named by the benchmark without
access to framework source.

## Consequences

The framework remains portable and auditable without becoming an agent runtime. Dispatch envelopes are
data, not authority. Benchmark observations remain blocked until the amended preregistration has a
committed revision, fixture hash, exact runtime registration, and conforming analysis implementation.

Acceptance evidence: campaign/dispatch binding tests, fixture determinism and leakage tests, generated
project validation, analysis synthetic checks, documentation validation, and the full test suite.
