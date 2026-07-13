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
