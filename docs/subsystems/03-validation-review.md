---
id: 03-validation-review
status: experimental
last_validated: 2026-07-10
code_anchors:
  - science_repo/validate.py:validate_repository
  - science_repo/review.py:review_run
---

# 03 — Validation and Review

Repository validation detects missing experiment files, malformed manifests, path escape attempts, and
registry drift. Mechanical review re-hashes artifacts and verifies successful execution.

This critic intentionally makes no claim about causal inference, statistics, citation fidelity, image
interpretation, research ethics, or domain correctness. Those require explicit specialist and human
review gates in later versions.

