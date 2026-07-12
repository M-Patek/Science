---
id: adr-0007
status: accepted
date: 2026-07-12
last_validated: 2026-07-12
---

# ADR 0007: Enforce distributed contracts and evidence integrity

## Context

Semantic Python checks did not fully execute the shipped JSON Schemas, source and packaged schemas could
drift, directory evidence could not be represented, and process startup/timeout failures could escape
without a complete run record. Wheel smoke checks also did not exercise a fresh independent project.

## Decision

Make `jsonschema` a runtime dependency and validate project and experiment manifests against project-local
pinned schemas. Framework validation requires source and packaged schema bytes to match. Never substitute
the current framework schema when an older project has no local schema, because that would be a silent
contract upgrade.

Hash declared file or directory evidence deterministically and reject symlinked evidence. Snapshot inputs
before execution. Startup errors and declared timeouts must still produce logs, environment, frozen
manifest, and a failed immutable run record. Mechanical review verifies the frozen manifest, environment,
status, evidence type, and content hashes.

Verify releases by building a wheel offline, installing it into a fresh virtual environment, and running
the generated-project lifecycle through the wheel's console script.

## Consequences

Minimal installations now include `jsonschema`. Projects generated before local schemas were shipped keep
their semantic validation behavior rather than being silently upgraded. Directory hashing is deterministic
but is not an atomic filesystem snapshot; concurrent mutation remains a documented boundary. Timeout
termination covers the direct process, not every descendant process on all platforms.

Acceptance evidence: schema/parity tests, provenance failure and mutation tests, fresh-wheel lifecycle,
repository and documentation validation, a new run/review record, and the full suite.
