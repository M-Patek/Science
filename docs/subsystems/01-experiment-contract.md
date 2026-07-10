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
