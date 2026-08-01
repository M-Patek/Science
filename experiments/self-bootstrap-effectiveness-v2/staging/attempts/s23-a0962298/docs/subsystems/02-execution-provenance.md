---
id: 02-execution-provenance
status: experimental
last_validated: 2026-07-10
code_anchors:
  - science_repo/runner.py:run_experiment
  - science_repo/environment.py:capture_environment
  - science_repo/lineage.py:validate_lineage
  - science_repo/reproduce.py:assess_reproduction
  - schemas/run.schema.json
---

# 02 — Execution and Provenance

The runner executes an argv array without a shell, captures stdout/stderr, timestamps and duration,
Python/platform/package context, git revision when available, manifest hash, and artifact hashes.

Records live under `records/<UTC timestamp>-<nonce>/` and are append-only. Startup failures and declared
timeouts still produce complete failed records and logs. The environment hash is a
compact comparison key; `environment.json` is the inspectable source. The runner snapshots the manifest
and hashes declared inputs before execution and outputs afterward. Files and directories have deterministic
content hashes; symlinked evidence is rejected. A missing declared input/output makes the run fail even if
the process returns zero.

Input paths are experiment-relative by default. Project-level evidence must declare `scope: project`;
the runner records both scope and canonical project path, and lineage uses that exact binding. Missing
paths never fall back to another root. Contract-v1 outputs remain experiment-relative.

Known boundary: package capture is Python-oriented and does not yet capture containers, GPU drivers,
HPC scheduler metadata beyond selected environment variables, atomic directory snapshots, descendant
process-tree timeout cleanup, or OS-enforced WORM records.

Each run creates `run.in-progress.json` before launching the command. The marker is removed only after the
final `run.json` is atomically replaced. A remaining marker is evidence of incomplete finalization. Timeout
process-tree termination uses platform facilities and records parent-only fallback; it remains best effort.

## Self-bootstrap integrity services

Lineage manifests bind hashed dataset, artifact, run, and code entities through validated acyclic relations and project-relative paths. Environment reproduction assessment compares captured snapshots without probing a host; missing dimensions remain unknown and arbitrary identifiers are stable fingerprints rather than disclosed values.

New runs emit `lineage.json` and bind its canonical digest from `run.json`. Mechanical review validates
the pinned lineage schema, DAG, digest, and canonical run observation. The code claim is deliberately
limited to the manifest and declared command files; it is not complete dependency or container provenance.
Environment probes are bounded local capability observations and never record selected environment values.
