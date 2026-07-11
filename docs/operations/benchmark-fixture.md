---
id: benchmark-fixture
status: experimental
last_validated: 2026-07-11
---

# Onboarding benchmark fixture audit

The `generated-project-onboarding-v1` fixture is a subject-facing generated project, not a copy of the
framework self-study experiment. `science benchmark-build TARGET` composes the packaged project template,
experiment template, and the two benchmark experiments. Its canonical tree hash covers sorted relative
POSIX paths, byte lengths, and file bytes; timestamps and the absolute target path are excluded.

## Registration checks

Before freezing a cohort, the coordinator must verify all of the following:

- two builds in different empty target paths have the same canonical tree hash;
- reviewer-only cohort, protocol-registration, rubric, answer-key, transcript, score, and prior-observation
  material is absent from the subject tree;
- `prepared-invalid` produces exactly one validator error, and changing only its lifecycle stage to
  `designed` makes the whole project valid;
- `deterministic-smoke` has frozen input and executable code but no completed record or generated result;
- the five registered prompts still correspond to the project pin, experiment template, prepared-invalid
  experiment, deterministic-smoke experiment, and the human-gate policy exposed to subjects;
- the resulting tree hash is written into the cohort manifest before an assignment ledger or observation
  is produced.

`subject_excludes` is a registration assertion, not an executable glob list. The generator provides the
isolation structurally by copying only packaged subject assets. Tests therefore inspect the resulting tree
rather than assuming that labels in the cohort manifest remove files.

## Freeze status

A deterministic fixture alone is insufficient to authorize observation. Revision `dd46404` contains the
audited generator, subject assets, packaged schemas, and conforming analysis; cohort v1 registers fixture
hash `9c1ffbf39ce642b96fdc00e1ba74b013e92c47d9a3123b1e06255d2292a71407`.
Observation remains blocked until exact runtime/model metadata is registered. Any later change to
subject-visible bytes requires a new fixture hash and, after the first subject starts, a new cohort.
