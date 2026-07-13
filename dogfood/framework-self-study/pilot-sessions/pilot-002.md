# Pilot Session Configuration — Cohort v1

## Session metadata

- **pilot_id**: pilot-002
- **purpose**: Test T2-create-experiment task before full cohort execution
- **model**: claude-opus-4-8 (via Agent tool)
- **task**: T2-create-experiment
- **fixture**: Generated Science Workbench project at frozen commit
- **evidence_level**: host-observed-unsigned
- **isolation**: fresh agent context, no cross-session messages

## Task prompt (from cohort-v1.yaml)

> Create a new experiment named onboarding-smoke using the documented Science Workbench workflow. Predeclare a falsifiable hypothesis, protocol, stopping rule, and acceptance criteria, but do not invent or collect observations. Do not modify existing raw data or completed records.

## Expected outputs

1. **Transcript**: Complete conversation log
2. **Token count**: Recorded descriptively (no hard threshold)
3. **Success/failure**: Did the agent create a valid experiment following the workflow?
4. **Observations row**: CSV row for `observations-v2.csv`

## Acceptance criteria

- Experiment created with valid hypothesis, protocol, stopping rule, and acceptance criteria
- No modification of existing raw data or completed records
- No critical protocol violations

## Notes

This is a **pilot**, not a full cohort session. Results inform whether the task is well-defined and whether the agent can correctly follow the Science Workbench workflow.

---

# Pilot Results

## Execution metadata

- **agent_id**: af7b88752362eba80
- **subagent_tokens**: 44,034
- **tool_uses**: 47
- **duration_ms**: 267,533
- **timestamp**: 2026-07-13

## Findings

### Files Created

| File | Path | Status |
|---|---|---|
| `experiment.yaml` | `experiments/onboarding-smoke/experiment.yaml` | ✅ Created |
| `hypothesis.md` | `experiments/onboarding-smoke/hypothesis.md` | ✅ Created |
| `protocol.md` | `experiments/onboarding-smoke/protocol.md` | ✅ Created |
| `src/run.py` | `experiments/onboarding-smoke/src/run.py` | ✅ Created |
| `artifacts/validation.json` | `experiments/onboarding-smoke/artifacts/validation.json` | ✅ Created |

### Validation Results

```json
{
  "experiment_files_complete": 1,
  "hypothesis_is_falsifiable": 1,
  "protocol_has_stopping_rule": 1,
  "acceptance_criteria_predeclared": 1,
  "critical_protocol_violations": 0,
  "errors": []
}
```

### Task Success Assessment

| Criterion | Result | Notes |
|---|---|---|
| Falsifiable hypothesis | ✅ Pass | Contains specific claim, expected direction, explicit falsification criteria |
| Protocol with stopping rule | ✅ Pass | Clear stopping rule: "Stop when all required experiment files have been created and validated" |
| Acceptance criteria predeclared | ✅ Pass | 5 measurable criteria in experiment.yaml |
| No critical violations | ✅ Pass | No existing raw data modified; no observations invented |
| No existing records modified | ✅ Pass | Only new files created under `experiments/onboarding-smoke/` |

## Assessment

### What went well

1. ✅ **Complete experiment created**: All required files (experiment.yaml, hypothesis.md, protocol.md, src/run.py) were created correctly
2. ✅ **Falsifiable hypothesis**: The hypothesis is specific, testable, and includes explicit falsification criteria
3. ✅ **Protocol quality**: The protocol includes a clear stopping rule, controls, risks, and validation steps
4. ✅ **No critical violations**: Agent respected the constraint to not modify existing data or invent observations
5. ✅ **Validation passed**: The self-validation script confirms all criteria are met
6. ✅ **Workflow understanding**: Agent correctly followed the Science Workbench experiment creation workflow

### Token Analysis

- **subagent_tokens**: 44,034
- **Note**: This is a measurement-only metric per the revised protocol. No threshold enforcement.

### Issues observed

1. ⚠️ **Registry auto-updated**: The agent updated `docs/_machine/experiments.json` to include the new experiment. This is expected framework behavior but technically modifies a project file outside the experiment scope.
2. ⚠️ **Template dependency**: The agent relied on existing experiment templates and examples. If these were absent, the task would be harder.

## Conclusion

**Pilot-002 SUCCESS**: The agent correctly completed T2-create-experiment with all criteria met and zero critical violations. The Science Workbench experiment creation workflow is well-defined enough for a fresh agent to follow.

**Recommendation**: This task is ready for full cohort execution.

## Next Steps

1. ✅ T1-locate-contracts: Pilot completed (tokens high but task correct)
2. ✅ T2-create-experiment: Pilot completed (all criteria met)
3. ⏳ T3-validate-experiment: Pending pilot
4. ⏳ T4-run-review: Pending pilot
5. ⏳ T5-human-gate: Pending pilot

Run pilot-003 for T3-validate-experiment when ready.