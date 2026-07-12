from __future__ import annotations

import csv
from pathlib import Path


path = Path(__file__).parents[1] / "data" / "raw" / "observations-v2.csv"
if not path.exists():
    raise SystemExit("No controlled-ingestion observations-v2.csv; execution remains blocked.")
with path.open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
if not rows:
    raise SystemExit("No observations: preregistration is intentionally not executable yet.")
raise SystemExit("Analysis implementation must be frozen before authorized cohort execution.")
