# Hypothesis — Agent onboarding with bounded context

## Claim

A fresh general-purpose coding agent that reads only `AGENTS.md`, `docs/INDEX.md`, and routed documents
will correctly complete at least 80% of the benchmark tasks, commit zero critical protocol violations,
and consume no more than 3000 estimated tokens before beginning task-specific source inspection.

## Rationale and prior evidence

The framework intentionally uses progressive disclosure and machine-readable contracts. This is a design
claim awaiting empirical testing; it is not yet an observed result.

## Falsification criteria

Reject or revise the claim if success is below 80%, any critical violation occurs, or onboarding context
exceeds 3000 estimated tokens. Report every failed task; do not exclude confusing cases post hoc.

