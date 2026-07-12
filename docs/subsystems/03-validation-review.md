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
registry drift. It executes project-local pinned JSON Schemas and, in framework source, detects packaged
schema drift. Mechanical review verifies execution status, frozen manifest and environment snapshots,
and the type and content hashes of declared inputs and artifacts.

Campaigns, handoffs, and run records are also checked against project-local pinned schemas. Review treats
missing or malformed records, snapshots, results, and evidence shapes as failed checks and still writes a
review report; corrupt evidence must not crash the reviewer.

This critic intentionally makes no claim about causal inference, statistics, citation fidelity, image
interpretation, research ethics, or domain correctness. Those require explicit specialist and human
review gates in later versions.

Explicitly registered trusted in-process plugins receive a minimal frozen evidence view. Advisory
`unknown`, plugin failure, and malformed output fail closed. Plugins cannot create human approval or
establish scientific validity. Lineage integrity is a mechanical review gate for new lineage-bearing runs.

## Review extensions

Trusted, explicitly registered in-process plugins may add deterministic mechanical or scientific-advisory checks. They cannot claim human review, fail closed on malformed output, and are not an isolation or timeout boundary. Human approval remains separate.
