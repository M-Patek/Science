# Hypothesis — Agent onboarding with bounded context

## Claim and estimand

For the **single frozen model/provider/harness configuration** registered for cohort v1, fresh sessions
assigned in equal numbers to the five registered prompts will have a descriptive, session-level success
rate of at least 80%, commit zero critical protocol violations, and consume onboarding tokens that are
recorded descriptively without a hard threshold.

The primary estimand is the mean of the five task-specific success proportions (equivalently the pooled
session proportion only because allocation is balanced). It describes this prompt mixture and runtime;
it is not an estimate for all coding agents, all Science Workbench tasks, or a population of models.

## Rationale and prior evidence

The framework intentionally uses progressive disclosure and machine-readable contracts. This is a design
claim awaiting empirical testing; it is not yet an observed result.

## Falsification criteria

Reject or revise the claim if the predeclared descriptive success estimate is below 80%, any critical
violation occurs, or the onboarding token measurement is missing for all sessions. Report task strata
and every failed session; do not exclude confusing cases post hoc. No frequentist population-inference
claim is planned.
