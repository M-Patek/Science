---
name: run-experiment
description: Create, execute, inspect, or review a repository experiment with reproducible provenance. Use when a user asks to test a hypothesis, analyze data, generate scientific artifacts, or reproduce a prior result.
---

# Run Experiment

1. Read the root `AGENTS.md` and `docs/operations/experiment-workflow.md`.
2. If new, use `python -m science_repo.cli new ...`; do not handcraft a divergent layout.
3. Make the hypothesis falsifiable and predeclare metrics, exclusions, and stopping criteria.
4. Confirm human authorization for external resources, instruments, sensitive data, or material cost.
5. Implement outputs declared in `experiment.yaml`; never mutate `data/raw/`.
6. Validate, then run with `python -m science_repo.cli run <id>`.
7. Inspect logs and artifacts; run `python -m science_repo.cli review <id>`.
8. Report observed values separately from interpretation, including failures and limitations.

