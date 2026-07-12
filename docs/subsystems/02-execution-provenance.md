---
id: 02-execution-provenance
status: experimental
last_validated: 2026-07-10
code_anchors:
  - science_repo/runner.py:run_experiment
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

Known boundary: package capture is Python-oriented and does not yet capture containers, GPU drivers,
HPC scheduler metadata beyond selected environment variables, atomic directory snapshots, descendant
process-tree timeout cleanup, or OS-enforced WORM records.
