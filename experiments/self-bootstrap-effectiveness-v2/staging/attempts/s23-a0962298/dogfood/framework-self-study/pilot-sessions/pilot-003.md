# Pilot Session Configuration — Cohort v1

## Session metadata

- **pilot_id**: pilot-003
- **purpose**: Test T3-validate-experiment task before full cohort execution
- **model**: claude-opus-4-8 (via Agent tool)
- **task**: T3-validate-experiment
- **fixture**: Generated Science Workbench project at frozen commit
- **evidence_level**: host-observed-unsigned
- **isolation**: fresh agent context, no cross-session messages

## Task prompt (from cohort-v1.yaml)

> Validate the generated project and its prepared invalid experiment using the documented project-aware command. Diagnose the validation defect from command evidence, make the smallest valid correction, rerun validation, and report the actual outcome. Do not modify existing raw data or completed records.

## Expected outputs

1. **Transcript**: Complete conversation log
2. **Token count**: Recorded descriptively (no hard threshold)
3. **Success/failure**: Did the agent correctly validate, diagnose, fix, and re-validate?
4. **Observations row**: CSV row for `observations-v2.csv`

## Acceptance criteria

- Project validation command executed correctly
- Validation defect diagnosed from command output
- Smallest valid correction made
- Validation rerun and passes
- No modification of existing raw data or completed records

## Notes

This is a **pilot**, not a full cohort session. The task requires the agent to find and fix a prepared invalid experiment. The agent must not know in advance what the defect is.

---

# Pilot Results

## Execution metadata

- **agent_id**: a789ccc1d19018034
- **subagent_tokens**: 29,032
- **tool_uses**: 18
- **duration_ms**: 72,682
- **timestamp**: 2026-07-13

## Findings

### What the agent did

1. **Ran validation**: `python -m science_repo.cli --project dogfood/framework-self-study validate`
2. **Found the defect**: Validation failed with `onboarding-smoke: missing README.md`
3. **Root cause**: The `onboarding-smoke` experiment directory was missing a required `README.md` file
4. **Smallest valid correction**: Created a minimal `README.md` with the experiment title and pointer to other files
5. **Reran validation**: Passed successfully with `Repository validation passed.`

### Files touched

- **Created**: `dogfood/framework-self-study/experiments/onboarding-smoke/README.md`

### Validation transcript

```
# Initial validation
$ python -m science_repo.cli --project dogfood/framework-self-study validate
onboarding-smoke: missing README.md

# After fix
$ python -m science_repo.cli --project dogfood/framework-self-study validate
Repository validation passed.
```

### Task Success Assessment

| Criterion | Result | Notes |
|---|---|---|
| Validation command executed | ✅ Pass | Agent correctly ran the validation command |
| Defect diagnosed from output | ✅ Pass | Correctly identified missing README.md |
| Smallest valid correction | ✅ Pass | Created only README.md, no other changes |
| Validation rerun and passes | ✅ Pass | Confirmed with second validation run |
| No critical violations | ✅ Pass | No existing raw data or records modified |

## Assessment

### What went well

1. ✅ **Correct command usage**: Agent used the proper validation command with `--project` flag
2. ✅ **Accurate diagnosis**: Identified the exact issue (missing README.md) from error output
3. ✅ **Minimal fix**: Created only the missing file, no unnecessary changes
4. ✅ **Verification**: Reran validation to confirm the fix worked
5. ✅ **No critical violations**: Did not modify existing data or records

### Token Analysis

- **subagent_tokens**: 29,032
- **Note**: Measurement-only per revised protocol

### Issues observed

1. ⚠️ **Validation command required `--project` flag**: The agent initially tried `python -m science_repo.cli validate` which only works from the root directory. Had to use `--project` flag when running from the project directory.

## Conclusion

**Pilot-003 SUCCESS**: The agent correctly validated, diagnosed, fixed, and re-validated the experiment. All criteria met.

## Pilot Progress

1. ✅ T1-locate-contracts: Completed (correct, token high)
2. ✅ T2-create-experiment: Completed (all criteria met)
3. ✅ T3-validate-experiment: Completed (all criteria met)
4. ⏳ T4-run-review: Pending
5. ⏳ T5-human-gate: Pending