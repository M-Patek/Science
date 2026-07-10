from __future__ import annotations

import csv
import json
from pathlib import Path


root = Path(__file__).resolve().parent.parent
source = root / "data" / "raw" / "observations-v1.csv"
with source.open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
if not rows:
    raise SystemExit("No observations recorded; benchmark execution is intentionally blocked.")
successes = sum(int(row["tasks_passed"]) for row in rows)
total = sum(int(row["tasks_total"]) for row in rows)
results = {
    "sessions": len(rows),
    "task_success_rate": successes / total,
    "critical_protocol_violations": sum(int(row["critical_protocol_violations"]) for row in rows),
    "estimated_onboarding_tokens": max(int(row["estimated_onboarding_tokens"]) for row in rows),
}
output = root / "artifacts" / "results.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

