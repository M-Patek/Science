import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from science_repo.cli import refresh_registry


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.project.resolve()
    refresh_registry(root)
    print(f"Refreshed {root / 'docs' / '_machine' / 'experiments.json'}")
