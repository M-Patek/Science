# Independent review of engineering pilots 001–005

Date: 2026-07-13
Change class: interpretation and evidence classification; no pilot summary or completed run was rewritten.

## Evidence boundary

The review used the frozen rubric, the five submitted pilot summaries, the current Git diff, and the
immutable `onboarding-smoke` run directories. No complete subject transcript, command/event log,
session-specific Git diff, assignment ledger, or subject-to-artifact receipt was available. Therefore
the summaries are useful engineering evidence but do not meet the protocol's formal scoring boundary.

| Pilot | Submitted summary SHA-256 | Engineering score | Formal disposition |
|---|---|---:|---|
| pilot-001 | `f6f92d6323445bb3b57e495801bf31f1bd7e8cd91d6ad027b4b96588abfa8d10` | 85/100 | not evaluable |
| pilot-002 | `804d22824869678601e907aa2e8d301607ce550232ffa97e24f6de94e17947f3` | 60/100 | not evaluable |
| pilot-003 | `1d800704a4206a97805f15587469146735cfb6b7e1eadb528c2738d947ee693d` | 25/100 | fail as reported; not admissible as a formal row |
| pilot-004 | `a6a6738af7516e6df36e059fa99b943e9080317bee5756e35730d503a6a556eb` | 90/100 | not evaluable |
| pilot-005 | `6ab4432eea694333168fe657c127da517f8a0382b37a076a9747974370ffb637` | 75/100 | not evaluable |

## Mechanical findings

1. T3 is internally inconsistent: `pilot-003.md` reports `missing README.md`, while the v2 row reports
   an uppercase-ID defect. The original validator log is absent.
2. T4 has three immutable run records. The first is failed with a failed review; the last is succeeded
   with a passing review after framework changes. The summaries do not bind a subject session to exactly
   one of those records, and the final table in `pilot-005.md` contradicts the T4 narrative.
3. Token values in every pilot summary differ from the values appended to v2. No measurement-method or
   identity mapping resolves the difference.
4. The cohort manifest remained dispatch-blocked under its own unsigned-receipt policy.
5. Five single-task pilots cannot satisfy the planned fifteen-session, three-per-task estimand.

## Decision

Preserve all pilot materials and negative runs. Do not count any submitted pilot as a formal cohort
pass. `observations-v2.csv` remains immutable superseded history. Formal analysis restarts from the
header-only `observations-v3.csv` after a new revision and evidence-capture path are frozen.
