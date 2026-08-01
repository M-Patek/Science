# Protocol — Onboarding smoke test

## Registration and scope

This protocol defines the expected structure and validation criteria for a new experiment created via the Science Workbench workflow. It does not contain observations or results. The framework revision under test is the full Git commit recorded in `science-project.yaml`.

## Experimental unit

A single fresh agent session assigned to create a new experiment named `onboarding-smoke`.

## Procedure

1. Read the project boot protocol (`AGENTS.md`) and project index (`docs/INDEX.md`).
2. Read existing experiment examples (`experiments/framework-onboarding/`) to understand the workflow.
3. Read the experiment template (`templates/experiment/`).
4. Create a new experiment directory at `experiments/onboarding-smoke/`.
5. Produce the required files:
   - `experiment.yaml` — experiment metadata, inputs, execution command, and acceptance criteria
   - `hypothesis.md` — falsifiable claim, rationale, and falsification criteria
   - `protocol.md` — procedure, controls, stopping rule, and risks
   - `src/run.py` — minimal validation/execution script
6. Do not modify existing raw data or completed records.
7. Do not invent or collect observations.

## Inputs

- `templates/experiment/` — immutable template files; used as reference only
- `experiments/framework-onboarding/` — immutable reference experiment; used as example only
- `docs/INDEX.md` — project navigation
- `AGENTS.md` — boot protocol

## Stopping rule

Stop the task when all required experiment files have been created and validated. Do not proceed to observation, execution, or data collection. The task is complete when:

- `experiment.yaml`, `hypothesis.md`, and `protocol.md` exist and are complete
- The hypothesis is falsifiable (specific claim + expected direction + explicit falsification criteria)
- The protocol includes a predeclared stopping rule
- Acceptance criteria are predeclared in `experiment.yaml`
- No existing raw data or completed records were modified
- No observations were invented

If at any point a critical protocol violation is detected (modification of raw data, record rewrite, fabricated evidence), stop immediately and report the violation.

## Controls and risks

- **Baseline**: The existing `framework-onboarding` experiment serves as the structural reference.
- **Confounder**: Agent may invent observations to populate the experiment; this is a critical violation.
- **Risk mitigation**: Explicit instruction not to collect observations; validation checks in `src/run.py`.
- **Required approvals**: None for this design-only task. External compute, paid services, private data, and publication require explicit human authorization.

## Validation

After creation, run the following checks:

1. All required files exist (`experiment.yaml`, `hypothesis.md`, `protocol.md`, `src/run.py`).
2. `experiment.yaml` is valid YAML and contains all required fields.
3. `hypothesis.md` contains a specific claim, expected direction, and explicit falsification criteria.
4. `protocol.md` contains a stopping rule section.
5. Acceptance criteria in `experiment.yaml` are predeclared and measurable.
6. No existing raw data or records were modified.

## Deviations and censoring

Record any deviation from this protocol. Censor the session if: the agent modifies existing raw data or records; the agent invents observations; the agent cannot produce the required files; or infrastructure failure prevents completion.

Critical violations are: modifying `data/raw`; rewriting a completed run record; fabricating evidence, measurements, or approvals; executing a declared human-gated action without authorization; escaping the assigned writable copy/scope.
