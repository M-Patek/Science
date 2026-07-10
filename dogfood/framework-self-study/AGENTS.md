# Science Workbench Self Study — Agent Protocol

This project uses Science Workbench. Optimize for truth, traceability, reproducibility, and human
control. Read `science-project.yaml`, then `docs/INDEX.md`.

For experiments read: `experiment.yaml` → `hypothesis.md` → `protocol.md` → latest run record.
For campaigns read: `campaign.yaml` → assigned task → dependencies → handoffs.

- Never mutate `data/raw/` or completed run records.
- Never invent evidence, citations, measurements, approvals, or successful runs.
- Respect every task's `write_scope`; do not edit another agent's scope.
- A task is complete only with its declared outputs and a structured handoff.
- Human approval is required for external compute, sensitive data, instruments, spending, and release.

Before handoff run `science validate` and the smallest relevant experiment/review.

