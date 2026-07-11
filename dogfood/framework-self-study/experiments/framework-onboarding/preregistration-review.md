# Independent preregistration review — cohort v1

Date: 2026-07-11  
Review point: before observation (`observations-v1.csv` contained its header and zero rows)  
Role: scientific-method reviewer; no implementation or outcome scoring performed

## Observed findings

1. The registered unit was one session assigned one task, but `src/run.py` computes a ratio from
   `tasks_passed/tasks_total`. This permits multiple task trials per row and cannot implement the stated
   session-level estimand, censoring, task balance, token missingness, or scorer reconciliation.
2. Five sessions with one prompt each perfectly confounded task difficulty with the only replicate and
   made the 80% boundary a single-session jump. Pooling those heterogeneous prompts without task strata
   obscured which workflow capability was measured.
3. The fixture construction did not freeze the prepared invalid experiment or deterministic smoke
   experiment and had no registered tree hash. Therefore nominally identical sessions could receive
   different tasks even at one Git revision.
4. The framework worktree contains this rubric and protocol. The isolation text did not require their
   removal from subject copies, allowing direct scoring-criterion leakage.
5. The manifest named required model metadata but did not register one exact configuration before
   assignment. “A model/provider change is a different cohort” was therefore unenforceable.
6. The hypothesis generalized to a “fresh general-purpose coding agent,” although one model/runtime and
   a convenience sample of five prompts can only support a descriptive claim about that configuration
   and prompt mixture.
7. The onboarding aggregate was described both as a maximum and as a requirement for every included
   measurable session. Missingness was discussed, but the analysis implementation coerces every value
   to integer and cannot represent `unavailable`.

## Inference and risk assessment

Without amendment, a favorable result could be driven by the task allocation, changed fixture bytes,
rubric exposure, or task-count weighting rather than agent onboarding quality. Repeated sessions from
one configuration are useful operational replications, but treating them as a population sample would
be pseudoreplication. Revision pinning alone does not fix fixture or runtime ambiguity.

## Pre-observation disposition

The hypothesis was narrowed to its identifiable descriptive estimand; allocation was balanced at three
sessions per task; reviewer material was excluded from subject fixtures; fixture/runtime registration
became mandatory; and the nonconforming analysis implementation was explicitly blocked. These are
design changes made with zero observed outcomes. They do not authorize observation until all pending
fields are resolved. The session-level v2 analysis contract was implemented before observation; fixture
and runtime registration, plus refreshed frozen-material hashes, remain required before execution.
