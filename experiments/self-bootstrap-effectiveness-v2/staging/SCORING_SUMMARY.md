# Cohort v2 Scoring Summary

## Status

24 attempt bundles built from available `outputs.json` files.

## Limitations

These are **minimal bundles** with missing bootstrap artifacts per protocol v2:
- Missing: harness-receipt, host-observation, local-dispatch-acceptance
- Missing: events, commands, patch, handoff, execution-gate

Available: outputs, tests (from outputs.json)

## Scoring Approach

Given missing artifacts, scoring uses available evidence:
- Test pass/fail status from outputs.json
- Implementation completeness from outputs.json
- Notes on baseline bugs and workarounds

## Results by Cell

| Block | Fixture | Control | Treatment |
|---|---|---|---|
| 1 | cs-01-experiment-metadata | s11: verified | s20: verified |
| 2 | cs-02-campaign-effort | s07: verified | s04: verified |
| 3 | cs-03-run-stop-reason | s21: implemented | s24: verified |
| 4 | rp-01-lineage-disconnected | s14: verified | s15: verified |
| 5 | rp-02-environment-size-cap | s23: verified | s17: implemented |
| 6 | rp-03-review-record-binding | s16: verified | s01: verified |
| 7 | or-01-scheduler-capacity | s12: verified | s10: implemented |
| 8 | or-02-handoff-output-uniqueness | s08: verified | s18: verified |
| 9 | or-03-coordinator-event-sequence | s02: verified | s05: verified |
| 10 | dx-01-validation-json | s09: implemented | s19: verified |
| 11 | dx-02-campaign-explain | s22: verified | s13: implemented |
| 12 | dx-03-doctor-remediation | s03: verified | s06: verified |

## Control vs Treatment Summary

- **Control (12 cells)**: All verified existing implementations or implemented new features
- **Treatment (12 cells)**: All verified existing implementations or implemented new features
- **Baseline bugs**: 1 pre-existing pytest .tmp file issue (task_runtime._write)
- **Critical violations**: 0
- **Setup censored**: 0

## Primary Endpoint

Mean treatment-minus-control adjudicated quality difference: **N/A** (formal scoring requires full bundles)
Median treatment/control elapsed-time ratio: **N/A**

## Recommendation

For formal scoring, the cohort needs complete attempt bundles with all 10 evidence artifacts.
The current execution captured task outputs but not bootstrap artifacts.
Consider: re-execution with full artifact capture, or protocol amendment for reduced evidence.
