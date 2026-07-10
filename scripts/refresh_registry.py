from pathlib import Path

from science_repo.cli import refresh_registry


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    refresh_registry(root)
    print("Refreshed docs/_machine/experiments.json")

