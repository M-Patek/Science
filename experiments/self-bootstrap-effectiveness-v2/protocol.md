# Protocol 鈥?self-bootstrap effectiveness cohort v2

## Status and freeze

This is a new, outcome-free v2 protocol. The onboarding pilots and both older v1 designs are engineering
history, not observations for this cohort. Before formal dispatch, an independent review must accept the
design and a freeze must bind the baseline commit/tree, protocol, hypothesis, rubric, tool policy, all
twelve prompts, baseline-negative audit, allocation seed commitment and 24-cell ledger. Any material
change after that point creates a new cohort rather than rewriting the freeze.

## Arms and resource asymmetry

Both arms receive the same prompt, baseline, 90-minute wall-clock limit and local tools. Control forbids
delegation. Treatment uses Science dispatch envelopes and may use at most three concurrently running
native subagents, at most four child attempts in total, disjoint write scopes, structured handoffs and an
independent reviewer. The Main Agent integrates the result. Extra agent-minutes and tokens are secondary
costs; the design does not pretend that the arms consume equal compute.

Network, external or paid compute, private data, instruments and publication are forbidden. A separate
human authorization is required to change those limits.

## Local evidence policy

The cohort may use the separately frozen `local-host-observed-unsigned-v1` acceptance overlay. It accepts
weaker process-environment and Main-Agent observations for this local study; it does not prove provider
identity, an immutable model build, prompt or toolchain identity, network/permission enforcement, context
isolation or absolute worktree isolation. Freeze and subject-packet artifacts remain fail-closed. Each
cell uses a two-stage native dispatch: a bootstrap-only child reports its harness receipt, native-agent ID,
actual cwd and HEAD; a packet-bound, expiring local acceptance is then created before a follow-up allows
fixture execution. Logical packet session ID, observed harness session ID and native agent ID remain
distinct fields.

## Cells, evidence and stopping

There are exactly twelve blocks by two arms and one ordinal-1 attempt per cell. Each cell has unique
logical session/worktree/context identifiers and a dedicated verified Git worktree. The immutable attempt
bundle binds packet, freeze, local acceptance, observed receipt, native agent, commit/tree, transcript or
event log, command log, diff, outputs/tests, start/end UTC, stopping reason, deviations, censoring and
critical violations. Missing evidence remains missing; it is never reconstructed from a summary.
`src/verify_attempts.py` validates the v2 schema, finalized digest, exact packet bijection and unique
planned/observed identities before controlled ingestion; it does not reuse the incompatible v1 verifier.

A cell stops at final candidate, 90 minutes, context exhaustion, explicit block, critical violation or
terminal infrastructure failure. Formal dispatch proceeds in eight frozen waves of three cells. After
each wave, a distinct checkpoint inspects only setup/censor/critical status, not efficacy. Two consecutive
pre-task host/setup failures cause that checkpoint to return blocked, so the next wave cannot become ready
until human review. No efficacy interim is inspected. A material repair requires a new freeze/cohort.

Setup censoring is limited to wrong frozen material before task evidence, a non-fresh/shared workspace or
context, duplicate identity, prohibited rubric/arm/prior-result leakage, or host capture/infrastructure
failure before task evidence. No replacement is allowed. Timeout, refusal, poor work, test failure,
delegation failure and subject-caused evidence loss are outcomes. Fabricated evidence/approval, raw or
completed-record rewrite, scope/worktree escape, secret/private-data exposure, unauthorized resources or
cross-cell messaging are critical violations and stop the cell while preserving evidence.

## Blinding and analysis

A controlled ingester creates the new experiment's raw v1 dataset without editing it later. An opaque
packetizer removes arm and orchestration labels while retaining rubric evidence. Two scorers who did not
execute the cell independently score identical packets and commit an arm guess/confidence. A distinct
adjudicator freezes resolutions before unblinding.

The primary ITT analysis uses all ordinal-1 cells: mean of twelve treatment-minus-control adjudicated
quality differences, median of twelve treatment/control elapsed-time ratios, pair completeness and
critical-violation count. Secondary metrics include acceptance/test status, criterion scores, integration
minutes, agent-minutes, provider-reported tokens, conflicts, rework, changed lines and handoff/audit pass.
Secondary metrics never replace the primary endpoints. Observations, inference, engineering suggestions,
agent review, human review and publication decision remain distinct artifacts.

## Closed v2 provenance and allocation contracts (prospective amendment)

The human seed is an exact, non-empty UTF-8 string with no surrounding whitespace. Its commitment is
`sha256(seed_bytes)`. For each canonical cell ID `<fixture-id>::<arm>`, the allocation rank is
`sha256(b"science-self-bootstrap-allocation-v1\\0" + seed_bytes + b"\\0" + cell_id_utf8)`.
Cells sort by `(rank_sha256, cell_id)` ascending, so the cell ID is the deterministic collision tie-break.
Execution order is the one-based rank and wave is `floor((order-1)/3)+1`, yielding exactly eight frozen
three-cell waves. The freeze carries this exact ledger; the separately finalized allocation ledger binds
the freeze digest, seed commitment, baseline commit/tree, per-cell arm-policy digest, rank, order, and
wave. No seed may be generated or inspected by this amendment.

Each subject packet binds the expected cohort ID, cell/arm, freeze, allocation ledger, packet set, pinned
commit and tree, unique planned identities, fixture, scope, and exactly one frozen arm-policy file. The
control policy prohibits native delegation. The structured policy requires bounded native delegation,
disjoint scopes, audited handoffs, and independent review. Neither subject-visible policy mentions the
alternative policy or scoring rubric. Packet sets remain `dispatch_allowed: false`; these bindings are
not execution authorization.

An attempt's bootstrap interval begins before host capture. Setup-censored attempts have no task-received
time, no task elapsed time, and no task evidence; their reason is one of the closed setup taxonomy and
their stop is explicit block or pre-task infrastructure failure. All other attempts have task elapsed
seconds exactly equal to `ended_utc - task_received_utc`; timeout is exactly 5,400 seconds and another
stop cannot reach the limit. Critical stops and the closed critical taxonomy are mutually required.
Every evidence digest has a safe relative locator and byte count in a finalized manifest; validators
retrieve and rehash it. A setup-censored attempt may contain only harness receipt, host observation, local dispatch acceptance, and execution-gate capture artifacts; events, commands, patch, outputs, tests, and handoff are prohibited. A non-censored attempt requires the complete ten-artifact set (including the external execution-gate artifact). Contradictions,
substituted freezes/ledgers/packet sets/cohorts/commits/trees, duplicate identities, or missing artifacts
fail closed.

Opaque packetization retains only task outputs, patch, and test evidence, removes every line containing
a frozen direct or indirect orchestration cue, verifies source and retained-content digests, and requires
an empty post-redaction disclosure scan. It excludes bootstrap/event/command/handoff material because it
can reveal the delivery mechanism. Two distinct scorers commit records for each of all 24 identical
packet digests before blind guesses; a distinct adjudicator commits a resolution before the arm reveal.
The controlled ingester validates exact coverage and all commitment ordering, then constructs exactly one
immutable derived row per allocation cell from the verified attempt, scoring, and adjudication manifests.
Setup-censored rows remain present with null quality and are non-evaluable; subject outcome failures remain
evaluable and scored. Analysis accepts only this schema-validated, digest-bound dataset.
