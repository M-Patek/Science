---
id: 01-experiment-contract
status: stable
last_validated: 2026-07-10
code_anchors:
  - science_repo/models.py:Experiment
  - science_repo/assets/experiment/experiment.yaml
  - schemas/experiment.schema.json
---

# 01 — Experiment Contract

`experiment.yaml` is the machine-readable intent: identity, question, falsifiable hypothesis, lifecycle
stage, inputs, execution argv, expected outputs, acceptance criteria, owner, and ethics flags. Narrative
detail belongs in `hypothesis.md` and `protocol.md`; do not duplicate implementation line-by-line.

Allowed stages: `idea`, `designed`, `running`, `analyzed`, `reviewed`, `published`, `abandoned`.
Stage is epistemic state, not a task-progress percentage.

Generated projects carry their pinned JSON Schemas. Validation applies those local contracts and checks
that declared contract versions match each schema's `schema_version` constant. Framework source schemas
must remain byte-identical to the packaged project schemas. `execution.timeout_seconds`, when present,
must be a positive number.

Use `science transition` rather than editing `stage` directly. Allowed progress is
`idea → designed → running → analyzed → reviewed → published`; any pre-publication stage may instead become
`abandoned`. Published and abandoned are terminal. Each transition records actor, reason, timestamp, and
from/to stages in append-only `stage-history.jsonl`. Legacy experiments begin history at their current stage.
