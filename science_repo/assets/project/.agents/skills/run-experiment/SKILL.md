---
name: run-experiment
description: Create, execute, inspect, or review a Science Workbench experiment with reproducible provenance.
---

# Run Experiment

1. Read the project `AGENTS.md`, `science-project.yaml`, and `docs/INDEX.md`.
2. Create experiments with `science new`; do not handcraft a divergent layout.
3. Predeclare the hypothesis, metrics, exclusions, and stopping criteria before inspecting results.
4. Require human authorization for external resources, instruments, sensitive data, or material cost.
5. Implement only declared outputs and never mutate `data/raw/` or completed run records.
6. Run `science validate`, then `science run <id>` and `science review <id>`.
7. Report observations separately from interpretation, including failures and limitations.
