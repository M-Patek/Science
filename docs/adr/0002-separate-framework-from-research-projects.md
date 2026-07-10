---
id: adr-0002
status: accepted
last_validated: 2026-07-10
next_review: 2027-01-10
---

# ADR 0002 — Separate Framework from Research Projects

## Context

The initial prototype mixed reusable implementation, templates, example execution, and the durable
record of future research. That makes upgrades ambiguous and encourages experiments to depend on an
unversioned checkout of the framework.

## Decision

Treat this repository as the versioned framework. `science init` creates independent projects with a
`science-project.yaml` that pins the framework and contract versions. Repository files remain the source
of scientific truth; a future local or cloud platform consumes the same contracts. Campaign and handoff
schemas define multi-agent coordination without coupling projects to one agent vendor or runtime.

The framework may retain small conformance experiments and dogfood projects, but production research
belongs in independent repositories generated from the project template.

## Consequences

Framework and research histories can evolve independently, project migrations become explicit, and the
same project can run locally, over SSH/HPC, or on a future platform. Template assets must ship with the
Python package, and contract evolution now requires migrations and compatibility testing.

