# Independent preregistration review v2 — revision required

Status: `reviewed-rejected-revision-required`

An independent read-only agent review rejected the first draft. It found mismatched analysis output paths,
a planned raw-file overwrite, an attempt schema that allowed ordinal 2 and weak evidence bindings,
undeclared per-session packet/bundle dependencies, incomplete freeze/review inputs, missing numeric checks,
and a design YAML that was incorrectly presented as if it were the older pinned onboarding cohort contract.

The working revision now:

- uses `cohort-design-v2.yaml` explicitly as an outcome-free design input and reserves
  `registration/cohort-freeze.json` for the schema-validated immutable freeze;
- preserves header-only raw v1 and plans controlled ingestion into a new raw v2;
- aligns the campaign and experiment analysis output path;
- constrains the attempt schema to ordinal 1 and explicit local/session/evidence hashes;
- declares all 24 packet and attempt bundle dependencies;
- adds an independent baseline-negative audit task and expands review/freeze inputs;
- rejects negative critical counts and non-finite analysis values.

These remediations are not self-approval. A fresh independent reviewer must review this revision and the
baseline-negative audit before the freeze task may complete. No allocation, approval, dispatch or v2
observation exists.

A second independent read-only review also rejected the revision. It found incomplete receipt-derived
verification in the local acceptance overlay, missing seed/runtime/prompt inputs to the freeze task, no
full packet-set input for per-cell acceptance, and no declared output manifest for `outputs_sha256`.
Those issues were subsequently corrected in code, tests and the Campaign contract. This remains a record
of rejection, not a passing review; a later fresh review must evaluate the corrected state.

A third independent review found that a publicly rehashed acceptance could extend its lifetime and that
all 24 sessions could become ready before the two-failure pause rule was evaluated. Verification now
recomputes the exact policy-bounded lifetime and checks receipt time; regression tests cover public
rehashing. The campaign now dispatches eight waves of three cells with a fail-closed checkpoint between
waves. This third result was also a rejection, not retrospective approval.

A fourth ship review rejected use of the old v1 attempt verifier, broad raw-directory write scope, and an
under-specified freeze implementation. The revision now includes experiment-local v2 attempt-manifest and
freeze builders with mechanical tests, binds `experiment.yaml` and every declared design material, gives
the assembler the packet set/schema/verifier, and limits ingestion write scope to the new raw-v2 and
provenance-v2 paths. This is still remediation history, not an accepted preregistration review.
