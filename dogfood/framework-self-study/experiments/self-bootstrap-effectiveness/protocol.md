# Protocol - self-bootstrap effectiveness cohort v1

## Registration and dispatch block

This changes a hypothesis and protocol, not implementation, observations, or interpretation. The design
baseline is `aa398ebdc13d5cb8d44cc83c5e097faade766da3`. Before dispatch, record the verified full
implementation commit and hashes of this protocol, cohort, rubric, prompts, tool policy, all 12 fixtures,
and the seeded allocation ledger. `task-fixtures-v1.yaml` is currently empty and pending. No dispatch is
allowed until all twelve fixtures and allocation entries are frozen and independently checked. Updating
the implementation revision before execution is explicit and must never be described as a completed run.

## Unit, arms, isolation, and allocation

One unit is a fresh isolated session completing one bounded task fixture. Twelve blocks comprise three
fixtures in each preregistered stratum: contract/schema, runtime/provenance, orchestration, and
documentation/agent DX. A human-recorded seed fixes block and arm order before any outcome is visible.
Each block has one solo Main Agent control and one structured multi-wave treatment. Treatment uses bounded
subagents, disjoint write scopes, structured handoffs, and an agent reviewer; Science does not replace the
host's native delegation transport. Control has identical task, tools, limits, and no subagents.

Each session uses a clean worktree at the same commit and fixture. It cannot see the alternate arm,
rubric, answer key, earlier transcript, scores, or aggregate result. Cross-session communication is
forbidden. Scoring packets replace arm labels with opaque attempt labels.

## Sample, attempts, and stopping

The ITT design contains 24 first authorized attempts, one for every block-arm cell. A cell permits at
most two attempts. Attempt two is allowed only when attempt one meets a predeclared setup/infrastructure
censoring reason, and follows the frozen seeded replacement order. Both remain recorded. Never replace
timeout, refusal, poor delegation, test failure, or another outcome failure. Do not stop early or add
fixtures after outcomes. Stop an attempt at completion, 90 minutes, context exhaustion, explicit block,
critical violation, or infrastructure failure.

## Required identity and metadata

Before scoring record provider, model name, exact immutable model/version ID, inference runtime/version,
agent harness/version, role, prompt hashes or unavailable reason, tools/permissions/network policy,
sampling parameters, context limit, task-receipt and final-candidate UTC, token counts when reported,
worktree/commit/fixture verification, transcript and diff hashes, dispatch/handoff hashes, waves and
subagent count, and stop reason. Provider, exact model/version ID, runtime/version, and harness/version
are mandatory. Missing any censors the attempt as `identity-missing`; retain it and never infer a value.

## Outcomes and blinded scoring

Two independent scorers who did not implement or review the attempt assign the five bounded integer
components in `rubric.md`, totaling 0 through 10. They cannot see arm labels or each other's decisions.
After scoring, each records an arm guess and confidence as a blinding diagnostic. A distinct adjudicator
preserves both initial scores, evidence, disagreements, and the adjudicated score.

For both arms, total elapsed time starts at recorded session/task receipt and ends at final candidate.
Separately report Main Agent integration minutes, aggregate agent-minutes across roles, input/output/cached
tokens, and monetary cost (or `unavailable` with reason). These quantities are not interchangeable. Also
report test outcome, conflicts, rework, changed lines, deviations, and critical violations.

## Censoring, leakage, safety, and authorization

Censor only wrong revision/fixture/allocation; mandatory identity missing; non-fresh/shared workspace;
arm, rubric, answer-key, prior-result, or cross-session leakage; extra coordinator hints; missing evidence
needed for scoring; or infrastructure failure before task evidence. Record deviations before aggregate
analysis. Post-hoc exclusion is forbidden. Report censoring rate and replacement flow by arm.

Critical violations include fabricated evidence or approval, modifying existing raw data, rewriting
completed records, escaping scope/worktree, exposing secrets/private data, or using external compute,
paid resources, instruments, or publication without explicit recorded human authorization. Stop safely
and retain the attempt. Agent review is not human review. Publication requires an independent human
review receipt; a campaign agent cannot produce or impersonate it.

The experiment operator writes only `staging/observations-v2.candidate.csv`, never `data/raw`. A distinct
controlled-ingestion task verifies registration, schema, row identity, and candidate digest, then creates
`data/raw/observations-v2.csv` exactly once and emits a digest audit. It must fail if raw v2 already exists.

## Analysis and interpretation

Primary analysis is intention-to-treat using the first authorized attempt in each cell. Outcome failures
remain; censored cells remain missing, not silently substituted. Report replacement-based per-protocol
sensitivity separately. Average paired treatment-minus-control quality differences equally over blocks
and show strata. Report paired median total-elapsed-time ratio, while integration minutes, agent-minutes,
tokens, and cost remain separate.

The joint claim is supported only with 12 evaluable ITT pairs, mean quality difference at least 0.5,
median elapsed-time ratio at most 1.25, and zero critical violations. Any critical violation makes the
joint claim inconclusive. A threshold failure without a critical violation fails the claim. Freeze the raw
digest before analysis and separate observation, mechanical provenance review, inference, human review,
and publication decision.
