# Post-pilot and outcome-informed design declarations

The following v2 choices were made after inspection of the five onboarding engineering pilots and are not
represented as confirmatory decisions made before that history:

- accept a narrowly scoped `host-observed-unsigned` local evidence policy instead of requiring
  cryptographic host attestation;
- keep token counts measurement-only and remove the earlier 3,000-token eligibility rule;
- require transcript/event, command, diff, output, session-to-artifact and one-run-per-attempt bindings;
- disallow replacement attempts so packet and protocol contracts agree;
- preserve T3/T4 contradictions and missing evidence as failures rather than resolving them from summaries;
- use two independent scorers plus distinct adjudication and require an arm guess.

The inherited 12-pair, 0.5-quality and 1.25-time thresholds predate v2 observations but were already present
in the older self-bootstrap v1 design. They are prospective for v2 only, not preregistered relative to the
onboarding pilots.

## Prospective design-remediation amendment (DR-001 through DR-005)

This amendment was made after the outcome-blind independent design review and before any allocation seed,
cohort freeze, subject dispatch, fixture execution, observation, or score existed. It changes the protocol
and implementation contracts, not the hypothesis thresholds or any data/interpretation. The rejected
review remains immutable. The amendment closes cohort/packet/allocation/baseline linkage; finite censor,
stop, critical, timing and retrievable-evidence invariants; deterministic blinded packetization and
independent score/adjudication commitments; source-linked controlled derived ingestion; and canonical
arm delivery, allocation ranking, tie breaking, and eight-wave construction. All changes require a new
independent outcome-blind review before freeze.

## Prospective rereview remediation amendment

The outcome-blind negative rereview reproduced five remaining fail-open paths before freeze. This
amendment changes protocol and implementation contracts only; it does not change the hypothesis, inspect
outcomes, generate an allocation seed, authorize freeze, or authorize dispatch. Consuming verifiers now
revalidate complete freeze-ledger-packet lineage, setup-censored bundles reject every task artifact,
packetization and ingestion validate schemas and finalized digests with exact no-surplus coverage,
critical violations force adjudicated score zero, and the selected frozen arm-policy bytes, tools, and
fixture write scope are materialized and checked in each subject packet. The reproduced substitutions
are retained as deterministic negative tests. A fresh independent outcome-blind review is still required.
