---
id: experiment-workflow
status: stable
last_validated: 2026-07-12
---

# Experiment Workflow

1. **Frame:** create an experiment and write one answerable question.
2. **Predeclare:** record falsification, inputs, controls, exclusions, metrics, and stopping rules.
3. **Authorize:** obtain human approval for sensitive data, external compute, instruments, cost, or risk.
4. **Implement:** keep raw data immutable; write derived data and artifacts to their declared locations.
5. **Execute:** use `science run <id>` so code, environment, logs, and hashes stay together.
6. **Review:** run mechanical review, then statistical/domain/ethics review as applicable.
7. **Interpret:** label observations, inferences, limitations, negative results, and post-hoc analyses.
8. **Fork:** compare alternatives by new experiment or version; never overwrite a completed record.
9. **Publish/archive:** retain enough context for a new agent to reproduce the claim months later.

Advance epistemic state only after the corresponding evidence exists:

```powershell
science --project PROJECT transition EXPERIMENT --to designed --reason "Protocol preregistered" --actor "name-or-agent-id"
```

Do not edit `stage` or `stage-history.jsonl` by hand. A rerun does not require moving a stage backward. If a
published or abandoned inquiry must be reopened, create a new experiment/version and link the rationale.

## Human gates

Human approval is mandatory before accessing a new remote resource, using confidential/regulated data,
submitting compute with material cost, controlling an instrument, changing safety constraints, or
publishing externally.
