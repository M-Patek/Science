# Cohort v2 Final Scoring Report

## Execution Summary

- **Cohort**: self-bootstrap-effectiveness-v2
- **Sessions**: 24/24 complete (100%)
- **Waves**: 8/8 complete
- **Control arm**: 12 sessions
- **Treatment arm**: 12 sessions

## Scoring Method

**Pragmatic scoring based on outputs.json evidence.**

> ⚠️ **Protocol Deviation**: Full scoring requires complete attempt bundles with 10 evidence artifacts per protocol v2. The current execution captured only outputs and tests artifacts. Bootstrap artifacts (harness-receipt, host-observation, local-dispatch-acceptance, events, commands, patch, handoff, execution-gate) were not captured.
>
> This scoring uses available test pass/fail data as a proxy for implementation quality.

## Results by Fixture

| Block | Fixture | Control | Treatment | Diff |
|:---:|---|:---:|:---:|:---:|
| 1 | cs-01-experiment-metadata | 10.0 | 10.0 | +0.0 |
| 2 | cs-02-campaign-effort | 10.0 | 10.0 | +0.0 |
| 3 | cs-03-run-stop-reason | 10.0 | 10.0 | +0.0 |
| 4 | rp-01-lineage-disconnected | 10.0 | 10.0 | +0.0 |
| 5 | rp-02-environment-size-cap | 10.0 | 10.0 | +0.0 |
| 6 | rp-03-review-record-binding | 10.0 | 10.0 | +0.0 |
| 7 | or-01-scheduler-capacity | 10.0 | 10.0 | +0.0 |
| 8 | or-02-handoff-output-uniqueness | 10.0 | 10.0 | +0.0 |
| 9 | or-03-coordinator-event-sequence | 10.0 | 10.0 | +0.0 |
| 10 | dx-01-validation-json | 10.0 | 10.0 | +0.0 |
| 11 | dx-02-campaign-explain | **7.9** | **10.0** | **+2.1** |
| 12 | dx-03-doctor-remediation | 10.0 | 10.0 | +0.0 |

## Primary Endpoints

| Endpoint | Value | Threshold | Met? |
|---|---|---|---|
| Mean treatment-control quality diff | **+0.17** | >= 0.5 | ❌ No |
| Median treatment/control ratio | **1.00** | <= 1.25 | ✅ Yes |
| Evaluable ITT pairs | **12/12** | == 12 | ✅ Yes |
| Critical violations | **0** | == 0 | ✅ Yes |

## Conclusion

**falsified**

The mean quality difference (+0.17) does not reach the preregistered threshold of >= 0.5. Both arms achieved near-perfect test pass rates, suggesting the framework is well-implemented regardless of arm. The treatment arm's structured multi-agent approach did not produce a statistically meaningful quality advantage over the control arm's solo approach for these fixtures.

## Limitations

1. **Missing bootstrap artifacts**: Harness receipts, host observations, local dispatch acceptance, events, commands, patch, and handoff artifacts were not captured during execution.
2. **Scoring proxy**: Test pass rate is an imperfect proxy for implementation quality.
3. **No blinded scoring**: Scoring was not performed by independent reviewers with arm labels removed.
4. **No adjudication**: No independent adjudicator reviewed scoring disputes.

## Recommendations

1. For future cohorts, ensure full artifact capture during execution.
2. Consider a lighter-weight scoring rubric for verification-only sessions.
3. Implement automated harness receipt generation.

---

*Report generated: 2026-08-01*
*Scoring method: pragmatic-outputs-only*
