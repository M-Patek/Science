# Science Workbench — Agent Boot Protocol

This repository is a scientific workbench. Optimize for **truth, traceability, reproducibility, and
human control**, not for producing a plausible-looking result.

## START

1. Read `docs/INDEX.md` (routing only; keep initial context small).
2. Identify the affected subsystem IDs and read their files in `docs/subsystems/`.
3. For an experiment, read in order:
   `experiment.yaml` → `hypothesis.md` → `protocol.md` → latest `records/*/run.json`.
4. State whether you are changing a hypothesis, protocol, implementation, data, or interpretation.
5. In a generated project, read `science-project.yaml`; do not silently upgrade pinned contracts.

## EXECUTION RULES

- Never edit files under `data/raw/`; add a new version and record provenance instead.
- Never invent citations, measurements, approvals, sample sizes, or successful runs.
- Separate observed results from inference. Negative results remain first-class artifacts.
- Predeclare acceptance criteria before inspecting results; flag post-hoc changes explicitly.
- Every generated claim must be traceable to code, data, a run record, or a cited source.
- Use `science run <id>` rather than running experiment code directly when producing evidence.
- External compute, private data, instruments, cost-bearing resources, and publication always require
  explicit human authorization. Do not encode secrets in manifests or records.
- A mechanical reviewer checks provenance, not scientific truth. Human domain review is mandatory.
- Do not rewrite completed run records. Rerun and produce a new immutable record.
- In campaign work, respect task `write_scope` and return a handoff matching `handoff.schema.json`.

## EXIT

For code, protocol, schema, or experiment changes:

```text
python -m science_repo.cli validate
python scripts/check_docs.py
pytest
```

For generated projects, pass `--project PATH`. Validate campaign DAGs with
`science --project PATH campaign-validate <id>` before parallel execution.

If execution behavior changed, also run the smallest relevant experiment and review its new record.
Update `docs/changelog/CHANGELOG.md` for non-trivial changes and refresh
`docs/_machine/experiments.json` with `python scripts/refresh_registry.py` after manifest edits.

## CHANGE CLASSIFICATION

| Type | Example | Required evidence |
|---|---|---|
| T1 | prose/format only | doc check |
| T2 | refactor, no behavior change | unit tests |
| T3 | behavior or experiment implementation | tests + run record |
| T4 | schema/workflow/contract | all checks + ADR review |

Accepted ADRs are immutable; supersede them with a new ADR.
