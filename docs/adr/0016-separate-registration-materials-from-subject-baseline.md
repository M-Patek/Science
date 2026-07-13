---
id: adr-0016
status: accepted
date: 2026-07-13
last_validated: 2026-07-13
---

# ADR 0016 — Separate registration materials from the subject baseline

## Context

The cohort freeze bound fixtures and `baseline_materials`, and subject-packet construction copied both
categories into every packet. A self-study registration must also bind its hypothesis, protocol, rubric,
schemas, analysis and review artifacts. Treating those files as subject baseline would leak the rubric and
arm-comparison design to subjects and could fail the packet negative-content audit. Not binding them would
make the preregistration incomplete.

## Decision

The freeze contract gains an optional `registration_materials` collection. It uses the same path, file
type and byte-hash rules as other frozen materials but is never copied into a subject packet.
`baseline_materials` remains the minimal subject-visible baseline description; actual repository bytes
come from the separately pinned and verified Git worktree. Existing v1 freezes without the new property
remain schema-valid. New builders emit the property, including an empty array when unused.

## Consequences

- Registration code can prove exactly which design and review bytes were frozen without leaking them.
- Packet construction continues to verify only fixtures and subject baseline materials.
- A registration-material hash is provenance, not execution authorization or host enforcement.
- Changing registered design bytes still requires a new freeze/cohort; completed artifacts are immutable.
