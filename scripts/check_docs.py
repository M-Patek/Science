from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIRED = ("id", "status", "last_validated")
root = Path(__file__).resolve().parent.parent
errors: list[str] = []
for path in sorted((root / "docs").rglob("*.md")):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        errors.append(f"{path.relative_to(root)}: missing frontmatter")
        continue
    for key in REQUIRED:
        if not re.search(rf"^{key}:", match.group(1), re.MULTILINE):
            errors.append(f"{path.relative_to(root)}: missing {key}")
    for link in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
        if link.startswith(("http://", "https://", "#")):
            continue
        target = (path.parent / link.split("#", 1)[0]).resolve()
        if not target.exists():
            errors.append(f"{path.relative_to(root)}: broken link {link}")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print("Documentation checks passed.")

