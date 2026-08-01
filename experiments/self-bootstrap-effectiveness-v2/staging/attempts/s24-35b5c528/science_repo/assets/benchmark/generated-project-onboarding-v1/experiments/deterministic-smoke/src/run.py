from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
values = [int(line) for line in (root / "data" / "raw" / "integers.txt").read_text(encoding="utf-8").splitlines()]
(root / "artifacts").mkdir(exist_ok=True)
(root / "artifacts" / "results.json").write_text(
    json.dumps({"count": len(values), "total": sum(values)}, sort_keys=True) + "\n",
    encoding="utf-8",
)
