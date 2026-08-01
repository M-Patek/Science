# Protocol - self-bootstrap effectiveness cohort v1

## Freeze and fail-closed gates

This is a protocol change, not an observation or interpretation. Before dispatch, a reviewed cohort-freeze
must bind the implementation commit, normalized hashes of this protocol, cohort, rubric, tool policy, all
12 fixture prompts, a human-recorded allocation seed and complete ledger, and the schemas below. Runtime
identity must contain provider, model name, immutable model/version ID, inference runtime/version, and
agent harness/version. Human authorization must be represented by a trusted host-issued receipt bound to
the cohort, resource/cost boundaries, approver, and expiry. Missing or unverifiable identity, freeze, or
authorization blocks dispatch; an agent assertion or boolean cannot satisfy the gate.

## Cells, packets, and immutable attempts

The design has exactly 24 named cells: for every block 01 through 12, one `control` and one `treatment`
cell. The frozen allocation ledger maps each cell ID to a fresh session/worktree/context identity and a
dispatch order. No identity may be reused across cells. A sanitized subject packet is produced for each
cell from the frozen fixture. It contains the task prompt, baseline commit/tree, allowed tools, limits,
write scope, and opaque session/cell token, but excludes arm-comparison language, rubric, answer key,
allocation ledger, other attempts, and results. Packet hashes are fixed before receipt by the subject.

At task receipt, the operator creates one append-only attempt bundle conforming to
`schemas/attempt-bundle-v1.schema.json`. It binds the subject-packet digest, cell token, attempt ordinal,
verified commit/worktree/context identities, trusted runtime identity/authorization receipt references,
UTC receipt/end times, transcript/diff/command/output hashes, stopping reason, deviations, censor status,
and critical violations. The first authorized bundle is always the ITT bundle. A cell permits at most one
replacement (ordinal 2), only for a predeclared setup censoring event and in frozen replacement order.
Both bundles remain; timeout, refusal, poor work, delegation failure, or test failure is never replaced.
Exclusive creation and a digest ledger make a finalized bundle immutable; corrections create a new
versioned annotation, never rewrite the bundle.

Treatment may use bounded native subagents with disjoint scopes and structured handoffs. Control uses no
subagent. Both receive the same fixture, baseline, tools, limits, and elapsed-time origin. Stop at final
candidate, 90 minutes, context exhaustion, explicit block, critical violation, or infrastructure failure.

## Blinding and scoring

After controlled ingestion, a distinct packetizer validates bundle/schema/digest completeness and emits
one opaque blinded scoring packet per attempt using `schemas/blinded-scoring-packet-v1.schema.json`.
It preserves evidence needed by the rubric but removes arm, cell/block allocation, subject identity,
orchestration labels, and direct/indirect filenames or prose that disclose the arm. A private, frozen
mapping from opaque packet ID to attempt ID is inaccessible to scorers. If meaningful evidence cannot be
sanitized without revealing the arm, flag blinding failure and censor rather than silently redact evidence.

Two independent scorers use only their identical opaque packet, cannot see one another's score, and use
the anchored `rubric.md` including missing-evidence rules. They commit criterion scores and citations,
then record arm guess/confidence. A distinct adjudicator retains both originals and resolves disagreement
without unblinding. Unblinding and block pairing occur only after all adjudications are frozen.

## Outcomes, censoring, and analysis

Total elapsed time is task receipt to final candidate. Integration minutes, aggregate agent-minutes,
tokens, cost, conflicts, rework, changed lines, and test results are secondary and never substituted for
elapsed time. Setup censoring is limited to wrong frozen revision/fixture/allocation, mandatory identity
missing, non-fresh/shared workspace, prohibited leakage before task evidence, or infrastructure failure
before task evidence. Missing scoring evidence is scored under the rubric unless it makes the cell
unevaluable; all censoring and replacement flow are reported by arm.

Critical violations include fabricated evidence/approval, raw-data or completed-record rewrite,
scope/worktree escape, secret/private-data exposure, and unauthorized external compute, paid resource,
instrument, or publication. Stop and retain the bundle. Mechanical/agent review is not human approval.

The primary ITT analysis uses ordinal-1 bundles only and equally weights twelve within-block treatment
minus control comparisons. It reports 12-pair completeness, mean quality difference, paired median
elapsed-time ratio, zero/nonzero critical violations, strata, censoring, and missingness. Replacement-based
per-protocol analysis is sensitivity only. The joint claim requires exactly 12 evaluable ITT pairs,
quality difference >=0.5, elapsed ratio <=1.25, and zero critical violations. Any missing pair or critical
violation is inconclusive; otherwise either threshold failure falsifies the claim. Freeze the raw and
derived digests before `science run`; observations, inference, agent review, human review, and publication
decision remain distinct.
