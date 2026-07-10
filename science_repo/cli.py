from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from .io import dump_json, dump_yaml, load_yaml
from .campaign import validate_campaign
from .models import ID_RE
from .review import review_run
from .runner import run_experiment
from .validate import validate_repository


ASSETS = Path(__file__).resolve().parent / "assets"


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "science-project.yaml").is_file():
            return candidate
        if (candidate / "science-framework.yaml").is_file() and (candidate / "experiments").is_dir():
            return candidate
    raise SystemExit("not inside a Science Workbench project; pass --project PATH")


def selected_project(args: argparse.Namespace) -> Path:
    return repo_root(Path(args.project)) if getattr(args, "project", None) else repo_root()


def refresh_registry(root: Path) -> None:
    entries = []
    for path in sorted((root / "experiments").iterdir()):
        if path.is_dir() and (path / "experiment.yaml").is_file():
            data = load_yaml(path / "experiment.yaml")
            entries.append({key: data.get(key) for key in ("id", "title", "stage", "owner")})
    dump_json(root / "docs" / "_machine" / "experiments.json", {"schema_version": 1, "experiments": entries})


def cmd_new(args: argparse.Namespace) -> int:
    root = selected_project(args)
    if not ID_RE.fullmatch(args.id):
        raise SystemExit("experiment id must be 3-64 lowercase letters, digits, or hyphens")
    target = root / "experiments" / args.id
    if target.exists():
        raise SystemExit(f"experiment already exists: {args.id}")
    template = root / "templates" / "experiment"
    if not template.is_dir():
        template = ASSETS / "experiment"
    shutil.copytree(template, target)
    manifest = load_yaml(target / "experiment.yaml")
    manifest.update({"id": args.id, "title": args.title, "owner": args.owner})
    dump_yaml(target / "experiment.yaml", manifest)
    for name in ("README.md", "hypothesis.md", "protocol.md"):
        path = target / name
        path.write_text(path.read_text(encoding="utf-8").replace("{{EXPERIMENT_ID}}", args.id).replace("{{TITLE}}", args.title), encoding="utf-8")
    refresh_registry(root)
    print(target.relative_to(root))
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    errors = validate_repository(selected_project(_))
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repository validation passed.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    root = selected_project(args)
    code, run_dir = run_experiment(root, args.id)
    print(run_dir.relative_to(root))
    return code


def cmd_review(args: argparse.Namespace) -> int:
    root = selected_project(args)
    records = root / "experiments" / args.id / "records"
    run_dir = records / args.run if args.run else sorted(p for p in records.iterdir() if p.is_dir())[-1]
    passed, report = review_run(run_dir)
    print(json.dumps(json.loads(report.read_text(encoding="utf-8")), indent=2))
    return 0 if passed else 1


def _replace_tree_tokens(root: Path, replacements: dict[str, str]) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token, value in replacements.items():
            text = text.replace(token, value)
        path.write_text(text, encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    if not ID_RE.fullmatch(args.id):
        raise SystemExit("project id must be 3-64 lowercase letters, digits, or hyphens")
    target = Path(args.target).resolve()
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"target is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ASSETS / "project", target, dirs_exist_ok=True)
    shutil.copytree(ASSETS / "experiment", target / "templates" / "experiment")
    _replace_tree_tokens(
        target,
        {
            "{{PROJECT_NAME}}": args.name,
            "{{PROJECT_ID}}": args.id,
            "{{OWNER}}": args.owner,
            "{{DATE}}": date.today().isoformat(),
        },
    )
    print(target)
    print(f"Next: science --project {target} new first-experiment --title \"First question\"")
    return 0


def cmd_campaign_validate(args: argparse.Namespace) -> int:
    root = selected_project(args)
    path = root / "campaigns" / args.id / "campaign.yaml"
    if not path.is_file():
        raise SystemExit(f"campaign not found: {path}")
    data = load_yaml(path)
    errors = validate_campaign(data)
    if errors:
        print("Campaign validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Campaign validation passed: {args.id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="science", description="Auditable experiment workbench")
    parser.add_argument("--project", help="project path; otherwise discover from current directory")
    sub = parser.add_subparsers(required=True)
    init = sub.add_parser("init", help="create an independent research project from the framework")
    init.add_argument("target")
    init.add_argument("--name", required=True)
    init.add_argument("--id", required=True)
    init.add_argument("--owner", default="unassigned")
    init.set_defaults(func=cmd_init)
    new = sub.add_parser("new", help="create an experiment from the canonical template")
    new.add_argument("id")
    new.add_argument("--title", required=True)
    new.add_argument("--owner", default="unassigned")
    new.set_defaults(func=cmd_new)
    validate = sub.add_parser("validate", help="validate manifests, layout, and registry")
    validate.set_defaults(func=cmd_validate)
    run = sub.add_parser("run", help="execute an experiment and capture provenance")
    run.add_argument("id")
    run.set_defaults(func=cmd_run)
    review = sub.add_parser("review", help="mechanically review the latest or selected run")
    review.add_argument("id")
    review.add_argument("--run")
    review.set_defaults(func=cmd_review)
    campaign = sub.add_parser("campaign-validate", help="validate a multi-agent campaign DAG")
    campaign.add_argument("id")
    campaign.set_defaults(func=cmd_campaign_validate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
