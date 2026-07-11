from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from .io import dump_json, dump_yaml, load_yaml
from .campaign import validate_campaign
from .cohort import generate_preassignment, load_cohort, validate_cohort, validate_preassignment
from .handoff import load_handoff, validate_handoff
from .models import ID_RE
from .review import review_run
from .runner import run_experiment
from .scheduler import RetryPolicy, schedule_campaign
from .task_runtime import LeaseConflict, TaskRuntime
from .workspace import WorkspaceError, WorkspaceManager
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


def _campaign(root: Path, campaign_id: str) -> tuple[Path, dict]:
    directory = root / "campaigns" / campaign_id
    path = directory / "campaign.yaml"
    if not path.is_file():
        raise SystemExit(f"campaign not found: {path}")
    return directory, load_yaml(path)


def _task_runtime(root: Path, campaign_id: str) -> TaskRuntime:
    directory, campaign = _campaign(root, campaign_id)
    errors = validate_campaign(campaign)
    if errors:
        raise SystemExit("campaign must validate before task dispatch: " + "; ".join(errors))
    return TaskRuntime(directory / "runtime")


def _ensure_campaign_task(root: Path, campaign_id: str, task_id: str) -> None:
    _, campaign = _campaign(root, campaign_id)
    if not any(
        isinstance(task, dict) and task.get("id") == task_id for task in campaign.get("tasks", [])
    ):
        raise SystemExit(f"campaign task not found: {task_id}")


def cmd_task_claim(args: argparse.Namespace) -> int:
    root = selected_project(args)
    _ensure_campaign_task(root, args.campaign, args.task)
    runtime = _task_runtime(root, args.campaign)
    try:
        state = runtime.claim(args.task, args.worker, lease_seconds=args.lease_seconds)
    except LeaseConflict as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(state, indent=2))
    return 0


def cmd_task_heartbeat(args: argparse.Namespace) -> int:
    root = selected_project(args)
    _ensure_campaign_task(root, args.campaign, args.task)
    runtime = _task_runtime(root, args.campaign)
    try:
        state = runtime.heartbeat(
            args.task, args.worker, args.token, lease_seconds=args.lease_seconds
        )
    except LeaseConflict as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(state, indent=2))
    return 0


def cmd_task_release(args: argparse.Namespace) -> int:
    root = selected_project(args)
    _ensure_campaign_task(root, args.campaign, args.task)
    runtime = _task_runtime(root, args.campaign)
    try:
        state = runtime.release(args.task, args.worker, args.token, outcome=args.outcome)
    except LeaseConflict as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(state, indent=2))
    return 0


def cmd_handoff_validate(args: argparse.Namespace) -> int:
    root = selected_project(args)
    _, campaign = _campaign(root, args.campaign)
    handoff = load_handoff(Path(args.handoff))
    errors = validate_handoff(handoff, campaign)
    if errors:
        print("Handoff validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Handoff validation passed: {args.handoff}")
    return 0


def cmd_campaign_status(args: argparse.Namespace) -> int:
    root = selected_project(args)
    _, campaign = _campaign(root, args.campaign)
    runtime = _task_runtime(root, args.campaign)
    snapshots = {
        task["id"]: runtime.inspect(task["id"])
        for task in campaign.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }
    decision = schedule_campaign(
        campaign, snapshots, retry_policy=RetryPolicy(max_attempts=args.max_attempts)
    )
    print(json.dumps({"campaign_id": args.campaign, "tasks": [asdict(item) for item in decision.tasks]}, indent=2))
    return 0


def _cohort_paths(root: Path, experiment_id: str, cohort_name: str, campaign_id: str):
    experiment = root / "experiments" / experiment_id
    return (
        experiment / cohort_name,
        root / "campaigns" / campaign_id / "campaign.yaml",
        root / "science-project.yaml",
    )


def cmd_cohort_validate(args: argparse.Namespace) -> int:
    root = selected_project(args)
    cohort_path, campaign_path, project_path = _cohort_paths(
        root, args.experiment, args.cohort, args.campaign
    )
    errors = validate_cohort(cohort_path, campaign_path=campaign_path, project_path=project_path)
    if errors:
        print("Cohort validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Cohort validation passed: {cohort_path.relative_to(root)}")
    return 0


def cmd_cohort_plan(args: argparse.Namespace) -> int:
    root = selected_project(args)
    cohort_path, campaign_path, project_path = _cohort_paths(
        root, args.experiment, args.cohort, args.campaign
    )
    errors = validate_cohort(cohort_path, campaign_path=campaign_path, project_path=project_path)
    if errors:
        raise SystemExit("cohort must validate before assignment: " + "; ".join(errors))
    cohort = load_cohort(cohort_path)
    ledger = generate_preassignment(cohort, args.sessions, copy_mechanism=args.copy_mechanism)
    ledger_errors = validate_preassignment(cohort, ledger)
    if ledger_errors:
        raise SystemExit("generated cohort ledger is invalid: " + "; ".join(ledger_errors))
    print(json.dumps(ledger, indent=2))
    return 0


def cmd_workspace_create(args: argparse.Namespace) -> int:
    manager = WorkspaceManager(Path(args.repository), Path(args.sessions_root))
    try:
        record = manager.create(args.session, args.revision)
    except WorkspaceError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(asdict(record), indent=2))
    return 0


def cmd_workspace_remove(args: argparse.Namespace) -> int:
    manager = WorkspaceManager(Path(args.repository), Path(args.sessions_root))
    try:
        record = manager.remove(args.session, force=args.force)
    except WorkspaceError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(asdict(record), indent=2))
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
    claim = sub.add_parser("task-claim", help="atomically lease a validated campaign task")
    claim.add_argument("campaign")
    claim.add_argument("task")
    claim.add_argument("--worker", required=True)
    claim.add_argument("--lease-seconds", type=float, default=300)
    claim.set_defaults(func=cmd_task_claim)
    heartbeat = sub.add_parser("task-heartbeat", help="extend a campaign task lease")
    heartbeat.add_argument("campaign")
    heartbeat.add_argument("task")
    heartbeat.add_argument("--worker", required=True)
    heartbeat.add_argument("--token", required=True)
    heartbeat.add_argument("--lease-seconds", type=float, default=300)
    heartbeat.set_defaults(func=cmd_task_heartbeat)
    release = sub.add_parser("task-release", help="release a campaign task lease")
    release.add_argument("campaign")
    release.add_argument("task")
    release.add_argument("--worker", required=True)
    release.add_argument("--token", required=True)
    release.add_argument("--outcome", default="released")
    release.set_defaults(func=cmd_task_release)
    handoff = sub.add_parser("handoff-validate", help="validate a task handoff against its campaign")
    handoff.add_argument("campaign")
    handoff.add_argument("handoff")
    handoff.set_defaults(func=cmd_handoff_validate)
    status = sub.add_parser("campaign-status", help="compute ready and blocked campaign tasks")
    status.add_argument("campaign")
    status.add_argument("--max-attempts", type=int, default=3)
    status.set_defaults(func=cmd_campaign_status)
    cohort_validate = sub.add_parser("cohort-validate", help="validate a frozen experiment cohort")
    cohort_validate.add_argument("experiment")
    cohort_validate.add_argument("--campaign", required=True)
    cohort_validate.add_argument("--cohort", default="cohort-v1.yaml")
    cohort_validate.set_defaults(func=cmd_cohort_validate)
    cohort_plan = sub.add_parser("cohort-plan", help="generate an outcome-blind assignment ledger")
    cohort_plan.add_argument("experiment")
    cohort_plan.add_argument("sessions", nargs="+")
    cohort_plan.add_argument("--campaign", required=True)
    cohort_plan.add_argument("--cohort", default="cohort-v1.yaml")
    cohort_plan.add_argument("--copy-mechanism", default="git-worktree")
    cohort_plan.set_defaults(func=cmd_cohort_plan)
    workspace_create = sub.add_parser("workspace-create", help="create an audited detached worktree")
    workspace_create.add_argument("session")
    workspace_create.add_argument("revision")
    workspace_create.add_argument("--repository", required=True)
    workspace_create.add_argument("--sessions-root", required=True)
    workspace_create.set_defaults(func=cmd_workspace_create)
    workspace_remove = sub.add_parser("workspace-remove", help="remove an audited detached worktree")
    workspace_remove.add_argument("session")
    workspace_remove.add_argument("--repository", required=True)
    workspace_remove.add_argument("--sessions-root", required=True)
    workspace_remove.add_argument("--force", action="store_true")
    workspace_remove.set_defaults(func=cmd_workspace_remove)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
