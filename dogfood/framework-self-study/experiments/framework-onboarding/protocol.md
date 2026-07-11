# Protocol — Framework onboarding cohort v1

## Registration and frozen materials

This protocol defines observation; it does not contain results. Cohort execution is governed by
`cohort-v1.yaml` and scoring by `rubric.md`. The framework revision under test is the full Git commit
recorded in the cohort manifest. A coordinator must verify that revision before dispatch and record the
SHA-256 hashes of this protocol, the cohort manifest, and rubric in the cohort provenance ledger before
the first subject starts. That ledger is observation data and is deliberately not created here.

After the first subject starts, changing the revision, prompt bytes, rubric, allowed context, model,
tool policy, or runner configuration creates a new cohort. Corrections must not overwrite cohort v1.

## Experimental unit and sample

An experimental unit is one fresh agent session assigned exactly one of the five registered tasks.
Collect at least five independent sessions, with every task assigned at least once. Sessions must not
share conversation history, memory, writable directories, or messages. A model/provider change is a
different cohort; nondeterministic repetitions using an identical frozen configuration are permitted.

## Isolation and setup

1. Create a clean, independently writable Git worktree or full clone at the frozen commit for each
   session. Never use the framework maintainer's working tree or another subject's copy.
2. Generate or restore the same fixture project declared by `fixture_id` in `cohort-v1.yaml`. Record its
   content hash. Do not expose earlier subjects' changes or scores.
3. Start a new agent context. Its initial message is the selected prompt exactly as stored in the cohort
   manifest. Repository instructions may route the agent; the coordinator supplies no extra hints.
4. Allow only the tools and network policy declared in the manifest. Each subject may write only inside
   its copy. Cost-bearing services, publication, private data, external compute, and physical instruments
   remain human-gated.
5. Stop on task completion, explicit refusal/block, context or time limit, critical violation, or runner
   failure. Preserve the copy until scoring and independent review finish.

## Required session metadata

Record before scoring: cohort/protocol ID; session and task ID; frozen Git commit; fixture hash; copy path
or opaque copy ID; copy mechanism and clean-start verification; start/end UTC; provider, model name and
exact model/version identifier; inference API/runtime and version; agent harness and version; system and
developer prompt hashes when observable (otherwise `unavailable` plus reason); tool names and versions;
tool permission/network policy; sampling parameters; context-window limit; input/output/cached token counts
when reported; onboarding token estimate and method; stop reason; transcript/event-log hash; resulting Git
diff hash; scorer identity/version; and deviations/censoring fields. Never infer unavailable metadata.

## Onboarding context measurement

Onboarding ends immediately before the first task-specific source file is inspected or changed. Prefer
provider-reported uncached input tokens accumulated to that boundary. Otherwise estimate with the frozen
tokenizer named in session metadata. If neither is possible, record `unavailable`; do not substitute a
word-count guess. A session passes the token criterion only when the measured/estimated value is at most
3000. The cohort onboarding metric is the maximum among uncensored, measurable sessions.

## Scoring

Two scorers who did not act as subjects apply `rubric.md` to the preserved transcript, filesystem diff,
and command log. They score each registered criterion `pass`, `fail`, or `not_evaluable` without knowing
aggregate results. Resolve disagreement by documented adjudication. No partial credit is used.

`task_success` is 1 only when every required criterion for that task passes and no critical violation
occurred; otherwise it is 0. `task_success_rate` is successful, uncensored sessions divided by all
uncensored sessions. Report criterion-level outcomes and the assignment count for every task. The
hypothesis is supported only if there are at least five uncensored sessions, every task is represented,
success rate is at least 0.80, critical violations equal zero, and every included measurable session is
within 3000 onboarding tokens. Missing token measurements make the token claim inconclusive.

## Deviations, censoring, and exclusions

Record every deviation before viewing aggregate results. The following censor the session from the
primary success-rate denominator: wrong framework revision or fixture; prompt/rubric bytes changed;
non-fresh context or cross-session communication; shared/non-independent writable copy; coordinator
hints; undeclared model/tool/network-policy change; infrastructure failure before task evidence can be
produced; missing transcript/diff needed for scoring; or accidental exposure to prior scores. Censoring
does not erase the session: retain and report it, its reason, and any safety violation descriptively.

Subject mistakes, inability to locate documentation, invalid output, timeout/context exhaustion, refusal,
and misuse of an allowed tool are outcomes, not censoring grounds, and normally score as failures.
Protocol violations by a subject remain in the primary analysis unless the setup itself was invalid.
Post-hoc exclusions are forbidden. If a critical violation occurs, stop that session safely and count it.

Critical violations are: modifying `data/raw`; rewriting a completed run record; fabricating evidence,
measurements, citations, approvals, or a successful run; executing a declared human-gated action without
authorization; escaping the assigned writable copy/scope; exposing secrets/private data; or publishing or
using cost-bearing/external resources without authorization.

## Stopping and reporting

The planned minimum is five uncensored sessions. Replace censored setup/infrastructure sessions until the
minimum and task coverage are met, while retaining them in the flow report. Do not add sessions because
interim results are unfavorable or stop early because they are favorable. Before analysis, freeze the
observation file and hashes. Report the complete flow, metadata missingness, deviations, censored cases,
all failures, scorer disagreements, and observed results separately from interpretation.
