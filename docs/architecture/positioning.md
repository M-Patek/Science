---
id: positioning
status: stable
last_validated: 2026-07-10
---

# Positioning

Science Workbench is a reusable, version-controlled framework for generating independent computational
research projects. It unifies the research path without hiding the files that make results auditable.

The product boundary has three layers: framework (contracts, CLI, templates), project (durable scientific
record), and optional platform (coordination, compute, UI). A cloud platform must build on the repository
contracts rather than replace them as the source of truth.

## Goals

- Make an experiment legible to a new human or agent in minutes.
- Preserve hypothesis, protocol, data lineage, code, environment, logs, artifacts, and review.
- Support local, SSH, HPC, or connector-backed compute without coupling the record format to a vendor.
- Let specialist skills compose under a coordinating agent while keeping permissions human-controlled.

## Non-goals

- Autonomous authorization of physical experiments, sensitive data access, spending, or publication.
- Treating an LLM critic as proof of scientific validity.
- Copying notebooks as the only source of truth or committing large/private datasets by default.
- Optimizing for one model provider, scientific domain, scheduler, or package manager.
