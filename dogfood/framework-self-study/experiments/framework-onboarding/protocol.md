# Protocol — Framework onboarding cohort v1

## Registration and frozen materials

This protocol defines observation; it does not contain results. Cohort execution is governed by
`cohort-v1.yaml` and scoring by `rubric.md`. The framework revision under test is the full Git commit
recorded in the cohort manifest. A coordinator must verify that revision before dispatch and record the
SHA-256 hashes of this protocol, the cohort manifest, and rubric in the cohort provenance ledger before
the first subject starts. That ledger is observation data and is deliberately not created here.

The 2026-07-11 independent preregistration review found design and analysis blockers before any subject
started. Cohort v1 was therefore amended before observation; details are in
`preregistration-review.md`. The manifest remains non-executable until its fixture hash and one exact
model/runtime configuration are registered and the analysis contract is made consistent.

**2026-07-13: Declarative runtime registration captured; formal dispatch remains blocked.** A
model/provider/harness declaration was captured via a host-observed harness receipt
(`harness-env-declarative` policy, evidence level
`host-observed-unsigned`). This receipt reads environment variables set by the Claude Code CLI and is
**declarative, not cryptographic**. A malicious or curious user can override these variables. The
receipt therefore remains `dispatch-blocked` until a trusted host verifier (for example, an OS key
store or cloud attestation service) confirms the claims. See ADR 0011 for the trust model.

The currently declared configuration is:
- **Provider**: anthropic
- **Model**: claude-opus-4-8
- **Harness**: claude-code_2-1-195_agent
- **Sampling**: xhigh
- **Evidence level**: host-observed-unsigned

Five engineering pilots were subsequently inspected. They did not preserve the complete transcript,
command/event log, per-session Git diff, and subject-to-artifact binding required below; their summaries
also contain conflicting T3 and T4 claims. They are retained as pilot history and are **not formal cohort
observations**. The unverified rows originally appended to `observations-v2.csv` are not silently
rewritten; `observations-v3.csv` is the corrected immutable analysis input and currently contains no
formal observations. See `pilot-sessions/independent-review-20260713.md`.

After the first subject starts, changing the revision, prompt bytes, rubric, allowed context, model,
tool policy, or runner configuration creates a new cohort. Corrections must not overwrite cohort v1.

## Experimental unit and sample

An experimental unit is one fresh agent session assigned exactly one of the five registered tasks.
Collect exactly fifteen valid planned sessions, three per task, plus replacements only for censored
setup/infrastructure sessions. Sessions must not
share conversation history, memory, writable directories, or messages. A model/provider change is a
different cohort; nondeterministic repetitions using an identical frozen configuration are permitted.
These repetitions are operationally isolated but share a model and configuration; they must not be
presented as independent draws from a population of agents or models.

## Isolation and setup

1. Create a clean, independently writable Git worktree or full clone at the frozen commit for each
   session. Never use the framework maintainer's working tree or another subject's copy.
2. Generate or restore the same fixture project declared by `fixture_id` in `cohort-v1.yaml`. Before any
   session, register its canonical tree hash and an immutable construction manifest containing exact
   commands, inputs, prepared defects, smoke-experiment contents, and tool versions. The subject copy
   must exclude this experiment's hypothesis, protocol, rubric, cohort manifest, answer keys, prior
   transcripts, and scores. Do not expose earlier subjects' changes or scores.
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
word-count guess.

**Post-pilot token amendment**: The original protocol specified a 3000-token threshold. Pilot session
pilot-001 (2026-07-13) demonstrated that this threshold is unrealistically low for complex engineering
tasks with the Opus model. The threshold is therefore **relaxed to measurement-only** for a future
refrozen cohort. This amendment is explicitly outcome-informed and is not represented as preregistered.
Tokens are recorded as a descriptive metric, not a pass/fail criterion. The primary success metric
(task_success_rate ≥ 0.80) and critical violation count (= 0) remain the decisive criteria.

**Rationale**: Engineering tasks require substantial context (system prompts, tool definitions, file
exploration). A hard token limit would either exclude capable models or force artificial task
simplification, undermining external validity. Token measurements are retained for descriptive
reporting and future threshold calibration.

## Scoring

Two scorers who did not act as subjects apply `rubric.md` to the preserved transcript, filesystem diff,
and command log. Subject sessions must never be able to read the rubric or review materials. Scorers
independently score each registered criterion `pass`, `fail`, or `not_evaluable` before receiving the
other scorer's decisions or any aggregate result. Resolve disagreement by documented adjudication. No
partial credit is used. Record both initial decisions as well as the adjudicated decision.

`task_success` is 1 only when every required criterion for that task passes and no critical violation
occurred; otherwise it is 0. The primary success metric is the unweighted mean of the five task-specific
success proportions across the fifteen planned uncensored sessions. The pooled rate is equivalent only
under the registered balanced allocation. Report criterion-level outcomes and each task stratum. The
hypothesis is supported only if there are exactly three planned uncensored sessions per task, the primary
rate is at least 0.80, and critical violations equal zero. Onboarding token measurements are recorded
descriptively but do not determine pass/fail; missing token measurements are noted but do not invalidate
the session.

The corrected `src/run.py` and `observations-v3.csv` implement immutable session rows, task strata,
censoring/deviation fields, independent and adjudicated scorer decisions, token missingness, and exact
balance checks. `observations-v1.csv` and `observations-v2.csv` are retained as superseded raw-data
history and are not authorized analysis inputs. This resolves the analysis-contract blocker identified
by independent review; a newly frozen revision, session evidence capture, and runtime verification remain
separate blockers to formal observation.

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

The planned sample is fifteen uncensored sessions, exactly three per task. Replace a censored
setup/infrastructure session within its assigned task stratum until the planned cell is filled, while
retaining every censored attempt in the flow report. Do not add sessions because
interim results are unfavorable or stop early because they are favorable. Before analysis, freeze the
observation file and hashes. Report the complete flow, metadata missingness, deviations, censored cases,
all failures, scorer disagreements, and observed results separately from interpretation.
