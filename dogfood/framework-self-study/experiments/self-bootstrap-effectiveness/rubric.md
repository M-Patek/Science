# Frozen quality rubric (0–10)

Two blinded scorers independently assign integers before adjudication.

1. Correctness and acceptance evidence: integer 0 to 3.
2. Contract, safety, and write-scope compliance: integer 0 to 2.
3. Tests and reproducibility evidence: integer 0 to 2.
4. Traceability and truthful limitation reporting: integer 0 to 2.
5. Maintainability and minimal unjustified complexity: integer 0 to 1.

The total is the sum of these bounded integers and ranges from 0 to 10 inclusive.

A fabricated result or unauthorized human-gated action is a critical violation and forces total score 0.
Scorers retain criterion scores, rationale, evidence paths, disagreements, and adjudication separately.
Scoring packets use opaque labels. After scoring, each scorer records an arm guess and confidence solely
as a blinding diagnostic; this guess never changes the score.
