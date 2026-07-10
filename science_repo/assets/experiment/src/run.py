from __future__ import annotations

import json
from pathlib import Path


root = Path(__file__).resolve().parent.parent
output = root / "artifacts" / "results.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"replace_me": 0}, indent=2) + "\n", encoding="utf-8")

