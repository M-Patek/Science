# Can a fresh agent reproduce the framework workflow with bounded context?

Experiment ID: `framework-onboarding`

Read `hypothesis.md`, then `protocol.md`, then `experiment.yaml`. Generated outputs belong in
`artifacts/`; immutable execution evidence belongs in `records/<run-id>/`.

## Observation contract

`data/raw/observations-v2.csv` is the pre-observation, session-level input. Each row is one fresh
session assigned exactly one registered task. Never correct it in place after collection begins: retain
the version and create a new raw-data version with recorded provenance. `observations-v1.csv` is retained
as immutable history but is not an analysis input because its task-count rows do not match the protocol.

The companion `observations-v2.schema.json` documents the columns. Censored attempts remain as rows and
require a reason; they are excluded only from the primary denominator. Deviations are independently
recorded and do not imply censoring. Both initial scorer decisions and the adjudicated decision are
required. `onboarding_tokens_status=unavailable` requires a blank token value and makes the token claim
inconclusive rather than passed.

Analysis refuses to run unless there are exactly 15 uncensored sessions, three in each task stratum.
The primary success rate is the equally weighted mean of the five stratum rates. Critical violations
are reported across every retained attempt. With an empty v2 file, execution remains intentionally
blocked and no artifact is written.

