from pathlib import Path

Path("artifacts/results.json").write_text('{"unused": true}\n', encoding="utf-8")
