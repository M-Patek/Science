---
id: adr-0015
status: accepted
date: 2026-07-13
last_validated: 2026-07-13
---

# ADR 0015 — Separate local unsigned acceptance from trusted attestation

## Context

The local agent harness exposes useful session, requested-model, harness, child-session, and effort
labels through process environment variables. Those values are adequate for a deliberately weak local
engineering trust model, but they are mutable process claims. They do not prove provider identity,
an immutable model build, prompt identity, tool completeness, network or permission enforcement, or
absolute context/worktree isolation. Requiring a cryptographic host service would unnecessarily block
the local self-study, while weakening the existing trusted-attestation verifier would erase an
important security boundary.

The frozen cohort and subject packets are preparation artifacts. Their `dispatch_allowed: false`
values must remain immutable even when a separate operator-selected policy permits a local run.

## Decision

Science Workbench has two non-interchangeable trust tracks:

1. `trusted_attestation` continues to require a host-owned verifier and remains the only track for
   trusted runtime identity and human authorization.
2. A `local-host-observed-unsigned` policy may create a short-lived, per-cell acceptance overlay only
   for local repository work that requires no network, private data, external compute, cost-bearing
   resources, instruments, or publication.

Local acceptance is two phase. A native child agent is first dispatched for bootstrap observation only.
The main agent then binds the policy, cohort freeze, packet set, cell and attempt, logical session,
native-agent identifier, distinct harness session, process-environment receipt, expected workspace,
observed working directory, pinned Git HEAD, and expiry. Formal task execution begins only through a
subsequent native follow-up after that overlay validates.

The acceptance explicitly lists its non-claims. It says only that the main agent chose to proceed under
the weaker local policy; it does not set generic `dispatch_allowed: true`, claim host enforcement, or
serve as human authorization. A requested model alias cannot be promoted into provider identity.

## Consequences

- Local self-research can proceed without a signing service while preserving an inspectable trust
  decision and replay-resistant cell/attempt bindings.
- Freeze and packet contracts remain fail closed and can be compared byte-for-byte with preregistration.
- Logical packet IDs, native-agent IDs, and harness session IDs remain separate evidence dimensions.
- Any network, private-data, external-compute, cost, instrument, or publication requirement remains
  outside this policy and requires the existing explicit authorization/trusted path.
- This is an operational reproducibility boundary, not a claim of adversarial security or scientific
  truth.
