# Pilot Session Configuration — Cohort v1

## Session metadata

- **pilot_id**: pilot-004
- **purpose**: Test T4-run-review task before full cohort execution
- **model**: claude-opus-4-8 (via Agent tool)
- **task**: T4-run-review
- **fixture**: Generated Science Workbench project at frozen commit
- **evidence_level**: host-observed-unsigned
- **isolation**: fresh agent context, no cross-session messages

## Task prompt (from cohort-v1.yaml)

> Using the prepared deterministic smoke experiment, produce one new evidence record through the documented experiment runner and mechanically review that new record. Report observed output separately from provenance review and scientific interpretation. Do not alter prior records.

## Expected outputs

1. **Transcript**: Complete conversation log
2. **Token count**: Recorded descriptively (no hard threshold)
3. **Success/failure**: Did the agent correctly run the experiment and review the record?
4. **Observations row**: CSV row for `observations-v2.csv`

## Acceptance criteria

- Experiment runner executed correctly
- New evidence record produced
- Mechanical review performed
- Observed output reported separately from provenance and interpretation
- No prior records altered

## Notes

This is a **pilot**, not a full cohort session. The task requires the agent to run the `onboarding-smoke` experiment and review its output.

---

# Pilot Results

## Execution metadata

- **agent_id**: a78c49367e1e00d44
- **subagent_tokens**: 34,936
- **tool_uses**: 30
- **duration_ms**: 149,715
- **timestamp**: 2026-07-13

## Findings

### What the agent did

1. **Ran experiment**: `python -m science_repo.cli --project dogfood/framework-self-study/ run onboarding-smoke`
2. **Produced record**: `experiments/onboarding-smoke/records/20260713T024731Z-a0a69799/`
3. **Mechanical review**: Reviewed `run.json`, `manifest.yaml`, `lineage.json`, `review.json`
4. **Reported findings**: Separated observed output, provenance review, and scientific interpretation

### Record Contents

The record at `20260713T024731Z-a0a69799/` contains:
- `run.json` — run metadata (status: **failed**)
- `manifest.yaml` — frozen snapshot of experiment
- `environment.json` — Python/platform context
- `lineage.json` — DAG with SHA-256 digests
- `stdout.log` — "Validation passed. All criteria met."
- `stderr.log` — empty
- `review.json` — mechanical review report

### Mechanical Review Verdict: `fail`

Failed checks (6 of 15):
| Check | Reason |
|-------|--------|
| `run_contract` | Missing pinned run contract schema |
| `process_succeeded` | Run status is `failed`, not `succeeded` |
| `lineage_declared_validation` | Lineage validation status: `not_validated_no_pinned_schema` |
| `lineage_contract_and_dag` | Missing pinned lineage contract schema |
| `input_integrity:templates/experiment/` | Declared input path does not exist |
| `input_integrity:experiments/framework-onboarding/` | Declared input path does not exist |

### Task Success Assessment

| Criterion | Result | Notes |
|---|---|---|
| Experiment runner executed | ✅ Pass | Agent correctly ran the experiment |
| New evidence record produced | ✅ Pass | Record created at `records/20260713T024731Z-a0a69799/` |
| Mechanical review performed | ✅ Pass | Reviewed all record files |
| Output separated from provenance/interpretation | ✅ Pass | Three-section report |
| No prior records altered | ✅ Pass | Only new record created |

## Assessment

### What went well

1. ✅ **Correct command usage**: Agent used the proper run command with `--project` flag
2. ✅ **Record produced**: New evidence record created with all required files
3. ✅ **Mechanical review**: Reviewed all record components
4. ✅ **Separation of concerns**: Observed output, provenance, and interpretation clearly separated
5. ✅ **No prior records altered**: Only created new record

### Key Finding: Run failed despite script success

The experiment script (`src/run.py`) exited with code 0 and printed "Validation passed. All criteria met." However, the framework declared the run as **failed** because:

1. **Missing pinned schemas**: `schemas/run.schema.json` and `schemas/lineage.schema.json` do not exist in the project
2. **Input path resolution**: Declared inputs (`templates/experiment/`, `experiments/framework-onboarding/`) exist at project root but framework marks them as missing

This is a **negative result** — the experiment creation workflow produces valid files, but the framework's integrity checks fail due to project template gaps.

### Token Analysis

- **subagent_tokens**: 34,936
- **Note**: Measurement-only per revised protocol

## Conclusion

**Pilot-004 SUCCESS**: The agent correctly ran the experiment, produced a record, and performed a mechanical review. The run itself failed due to framework infrastructure gaps (missing schemas, path resolution), not agent error. This is a valuable negative result.

## Pilot Progress

1. ✅ T1-locate-contracts: Completed (correct)
2. ✅ T2-create-experiment: Completed (all criteria met)
3. ✅ T3-validate-experiment: Completed (all criteria met)
4. ✅ T4-run-review: Completed (run failed but agent performed correctly)
5. ⏳ T5-human-gate: Pending