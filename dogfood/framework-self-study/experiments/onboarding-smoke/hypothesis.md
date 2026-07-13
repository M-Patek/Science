# Hypothesis — Smoke-test validation of the Science Workbench experiment creation workflow

## Claim and estimand

For a **single fresh agent session** operating within the Science Workbench framework, following only the documented boot protocol (`AGENTS.md`), project index (`docs/INDEX.md`), and existing experiment templates, the agent will produce a complete, valid experiment definition consisting of `experiment.yaml`, `hypothesis.md`, and `protocol.md`.

The primary estimand is a binary indicator: did the session produce a valid experiment definition with (a) a falsifiable hypothesis, (b) a protocol containing a stopping rule, and (c) predeclared acceptance criteria, while committing zero critical protocol violations?

## Rationale and prior evidence

The Science Workbench framework is designed around progressive disclosure, machine-readable contracts, and reproducible research workflows. The experiment creation workflow is a foundational operation that every user of the framework must be able to execute correctly. Prior evidence is limited to the framework design itself; this experiment tests whether the design is sufficient for a fresh agent to produce a valid experiment without prior domain-specific knowledge.

## Falsification criteria

Reject or revise the claim if any of the following occur:

1. The produced `hypothesis.md` lacks a specific, testable claim with an expected direction.
2. The produced `protocol.md` does not include an predeclared stopping rule.
3. The `experiment.yaml` acceptance criteria are absent, post-hoc, or inconsistent with the hypothesis.
4. Any critical protocol violation occurs (modification of existing raw data or completed records, invention of observations, fabrication of evidence).
5. The experiment files are structurally invalid or incomplete (missing required sections).

Report every deviation and the reason for any threshold failure. No post-hoc exclusions are permitted.
