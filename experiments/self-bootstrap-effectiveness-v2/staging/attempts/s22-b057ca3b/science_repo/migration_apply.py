"""Transactional application of a human-reviewed contract migration plan.

This module intentionally has no schema discovery.  Every source file must be
supplied by the caller and must match the digest recorded by the planner.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
from typing import Callable, Mapping
from contextlib import contextmanager

import yaml

from .io import atomic_write_text
from .migration import ContractStep, MigrationPlan


class MigrationApplyError(RuntimeError):
    """A migration was refused or failed and was rolled back."""


@dataclass(frozen=True)
class MigrationApplyResult:
    status: str
    plan_sha256: str
    backup_bundle: str | None
    changed_contracts: tuple[str, ...]


def _plan_bytes(plan: MigrationPlan) -> bytes:
    if not isinstance(plan, MigrationPlan):
        raise TypeError("plan must be a MigrationPlan")
    return json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


def plan_confirmation_token(plan: MigrationPlan) -> str:
    """Return the review token a human must explicitly pass to an apply call."""
    return "apply-contract-migration:" + hashlib.sha256(_plan_bytes(plan)).hexdigest()


def rollback_confirmation_token(plan_sha256: str) -> str:
    """Return the explicit token required to restore a migration backup."""
    return "rollback-contract-migration:" + plan_sha256


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
        return True
    except ValueError:
        return False


def _reject_link(path: Path, *, through: Path | None = None) -> None:
    """Reject symlinks/reparse-like resolved escapes along an existing path."""
    limit = through or Path(path.anchor)
    current = path
    while True:
        if current.exists():
            attributes = getattr(current.stat(follow_symlinks=False), "st_file_attributes", 0)
            reparse = bool(attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            if current.is_symlink() or reparse:
                raise MigrationApplyError(f"symbolic links or reparse points are not allowed: {current}")
        if current == limit or current.parent == current:
            break
        current = current.parent


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fsync_dir(path: Path) -> None:
    """Best-effort directory durability (not supported by Windows)."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


@contextmanager
def _migration_lock(root: Path):
    directory = root / ".science"
    _reject_link(directory, through=root)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "migration.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        try:
            pid = int(lock.read_text(encoding="ascii").strip().removeprefix("pid="))
            alive = _pid_alive(pid)
        except (OSError, ValueError):
            raise MigrationApplyError("migration lock is stale but cannot be safely verified") from exc
        if not alive:
            lock.unlink()
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        else:
            raise MigrationApplyError("another migration apply or rollback holds the project lock") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        os.fsync(descriptor)
        os.close(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        lock.unlink(missing_ok=True)
        _fsync_dir(directory)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        raise ValueError("invalid pid")
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise OSError("cannot inspect migration lock owner")
            return code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _validate_plan(plan: MigrationPlan) -> tuple[ContractStep, ...]:
    if plan.manifest != "science-project.yaml":
        raise MigrationApplyError("plan manifest must be science-project.yaml")
    if plan.errors or plan.status != "manual":
        raise MigrationApplyError("only an error-free manual migration plan can be applied")
    if any(step.status not in {"manual", "compatible"} for step in plan.steps):
        raise MigrationApplyError("plan contains a blocked or unsupported step")
    changed = tuple(step for step in plan.steps if step.status == "manual")
    if not changed:
        raise MigrationApplyError("plan contains no manual migration steps")
    for step in changed:
        if step.current_version is None or step.target_version is None:
            raise MigrationApplyError(f"{step.contract}: versions must be explicit")
        if step.target_version < step.current_version:
            raise MigrationApplyError(f"{step.contract}: downgrade is forbidden")
        if not step.schema_sha256 or step.destination_schema != f"schemas/{step.contract}.schema.json":
            raise MigrationApplyError(f"{step.contract}: incomplete or unsafe schema binding")
    return changed


def _recover_prepared_bundles(root: Path) -> None:
    """Recover interrupted pre-commit transactions, or fail closed on ambiguity."""
    directory = root / ".science" / "migrations"
    if not directory.exists():
        return
    _reject_link(directory, through=root)
    for bundle in sorted(path for path in directory.iterdir() if path.is_dir()):
        _reject_link(bundle, through=root)
        metadata_path = bundle / "manifest.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MigrationApplyError(f"blocked by unreadable migration bundle {bundle.name}: {exc}") from exc
        if metadata.get("state") != "prepared":
            continue
        try:
            phases = [json.loads(line)["phase"] for line in
                      (bundle / "wal.jsonl").read_text(encoding="utf-8").splitlines()]
        except Exception as exc:
            raise MigrationApplyError(f"blocked by invalid migration WAL {bundle.name}: {exc}") from exc
        if "committed" in phases:
            metadata["state"] = "committed"
            atomic_write_text(metadata_path, json.dumps(metadata, sort_keys=True, indent=2) + "\n")
            continue
        _restore_entries(root, bundle, metadata)
        with (bundle / "wal.jsonl").open("a", encoding="utf-8", newline="") as stream:
            stream.write(json.dumps({"phase": "startup-recovery",
                                     "at": datetime.now(timezone.utc).isoformat()}) + "\n")
            stream.flush(); os.fsync(stream.fileno())
        metadata["state"] = "rolled-back"
        atomic_write_text(metadata_path, json.dumps(metadata, sort_keys=True, indent=2) + "\n")


def _restore_entries(root: Path, bundle: Path, metadata: dict) -> tuple[str, ...]:
    entries = metadata.get("entries")
    if not isinstance(entries, list):
        raise MigrationApplyError("invalid backup manifest structure")
    restores: list[tuple[Path, bytes | None]] = []
    names: list[str] = []
    allowed = {"science-project.yaml", "schemas/campaign.schema.json",
               "schemas/experiment.schema.json", "schemas/handoff.schema.json"}
    for entry in entries:
        relative = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(relative, str) or relative not in allowed:
            raise MigrationApplyError("backup contains an unsafe path")
        destination = root / Path(relative)
        _reject_link(destination, through=root)
        if relative.startswith("schemas/"):
            names.append(Path(relative).stem.split(".")[0])
        if entry.get("existed") is True:
            backup = bundle / "backup" / Path(relative)
            _reject_link(backup, through=bundle)
            if not backup.is_file() or backup.is_symlink():
                raise MigrationApplyError(f"missing regular backup: {relative}")
            content = backup.read_bytes()
            if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
                raise MigrationApplyError(f"backup hash mismatch: {relative}")
            restores.append((destination, content))
        elif entry.get("existed") is False and entry.get("sha256") is None:
            restores.append((destination, None))
        else:
            raise MigrationApplyError(f"invalid backup entry: {relative}")
    restores.sort(key=lambda item: item[0].name == "science-project.yaml")
    for destination, content in restores:
        _reject_link(destination, through=root)
        if content is None:
            destination.unlink(missing_ok=True)
            _fsync_dir(destination.parent)
        else:
            _atomic_bytes(destination, content)
    return tuple(names)


def apply_contract_migration(
    project_root: Path,
    plan: MigrationPlan,
    source_schemas: Mapping[str, Path],
    *,
    confirmation_token: str | None = None,
    dry_run: bool = True,
    fault_injector: Callable[[str], None] | None = None,
) -> MigrationApplyResult:
    """Validate or transactionally apply *plan*; dry-run is the safe default.

    ``source_schemas`` is a per-contract explicit allow-list.  No packaged or
    planner host path is consulted.  ``fault_injector`` exists for crash-path
    testing and receives durable phase names.
    """
    changed = _validate_plan(plan)
    digest = hashlib.sha256(_plan_bytes(plan)).hexdigest()
    root = project_root.resolve(strict=True)
    if not root.is_dir():
        raise MigrationApplyError("project root is not a directory")
    manifest = root / "science-project.yaml"
    if not manifest.is_file() or manifest.is_symlink():
        raise MigrationApplyError("science-project.yaml must be a regular non-link file")
    _reject_link(manifest, through=root)

    try:
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        contracts = document["contracts"]
    except Exception as exc:
        raise MigrationApplyError(f"cannot read project contract pins: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(contracts, dict):
        raise MigrationApplyError("project manifest contracts must be a mapping")

    sources: dict[str, Path] = {}
    source_content: dict[str, bytes] = {}
    destinations: dict[str, Path] = {}
    already = True
    for step in changed:
        if step.contract not in source_schemas:
            raise MigrationApplyError(f"{step.contract}: explicit source schema is required")
        source = Path(source_schemas[step.contract])
        if not source.is_absolute():
            raise MigrationApplyError(f"{step.contract}: source schema path must be absolute")
        if not source.is_file() or source.is_symlink():
            raise MigrationApplyError(f"{step.contract}: source must be a regular non-link file")
        _reject_link(source)
        content = source.read_bytes()  # one read: hash and eventual write use identical bytes
        if hashlib.sha256(content).hexdigest() != step.schema_sha256:
            raise MigrationApplyError(f"{step.contract}: source schema hash does not match plan")
        destination = root / "schemas" / f"{step.contract}.schema.json"
        if not _inside(root, destination):
            raise MigrationApplyError(f"{step.contract}: destination escapes project")
        _reject_link(destination, through=root)
        current_pin = contracts.get(step.contract)
        if current_pin not in {step.current_version, step.target_version}:
            raise MigrationApplyError(f"{step.contract}: project pin changed since planning")
        is_done = current_pin == step.target_version and destination.is_file() and _hash(destination) == step.schema_sha256
        already = already and is_done
        sources[step.contract], source_content[step.contract] = source, content
        destinations[step.contract] = destination

    if already:
        return MigrationApplyResult("already-applied", digest, None, tuple(step.contract for step in changed))
    if dry_run:
        return MigrationApplyResult("dry-run", digest, None, tuple(step.contract for step in changed))
    if confirmation_token != plan_confirmation_token(plan):
        raise MigrationApplyError("explicit confirmation token does not match the reviewed plan")

    lock_context = _migration_lock(root)
    lock_context.__enter__()
    try:
        _recover_prepared_bundles(root)
        # Revalidate the mutable project state while holding the project lock.
        locked_document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        locked_contracts = locked_document.get("contracts") if isinstance(locked_document, dict) else None
        if not isinstance(locked_contracts, dict):
            raise MigrationApplyError("project manifest changed while acquiring migration lock")
        for step in changed:
            if locked_contracts.get(step.contract) != step.current_version:
                raise MigrationApplyError(f"{step.contract}: project pin changed while acquiring lock")
            _reject_link(destinations[step.contract], through=root)
        document, contracts = locked_document, locked_contracts
    except BaseException:
        lock_context.__exit__(None, None, None)
        raise

    migration_root = root / ".science" / "migrations"
    _reject_link(migration_root, through=root)
    bundle = migration_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + secrets.token_hex(8))
    bundle.mkdir(parents=True, exist_ok=False)
    _fsync_dir(bundle.parent)
    backups = bundle / "backup"
    backups.mkdir()
    _fsync_dir(bundle)
    originals: dict[Path, bytes | None] = {manifest: manifest.read_bytes()}
    for destination in destinations.values():
        originals[destination] = destination.read_bytes() if destination.is_file() else None
    entries = []
    for path, content in originals.items():
        relative = path.relative_to(root).as_posix()
        if content is not None:
            backup = backups / relative
            _atomic_bytes(backup, content)
            entries.append({"path": relative, "existed": True,
                            "sha256": hashlib.sha256(content).hexdigest()})
        else:
            entries.append({"path": relative, "existed": False, "sha256": None})
    backup_manifest = {"format": 1, "plan_sha256": digest, "state": "prepared", "entries": entries}
    atomic_write_text(bundle / "manifest.json", json.dumps(backup_manifest, sort_keys=True, indent=2) + "\n")
    wal = bundle / "wal.jsonl"

    def event(phase: str) -> None:
        with wal.open("a", encoding="utf-8", newline="") as stream:
            stream.write(json.dumps({"phase": phase, "at": datetime.now(timezone.utc).isoformat()}) + "\n")
            stream.flush(); os.fsync(stream.fileno())
        _fsync_dir(bundle)
        if fault_injector:
            fault_injector(phase)

    event("prepared")
    try:
        for step in changed:
            _reject_link(destinations[step.contract], through=root)
            _atomic_bytes(destinations[step.contract], source_content[step.contract])
            event(f"schema:{step.contract}")
        updated = dict(document)
        updated_contracts = dict(contracts)
        for step in changed:
            updated_contracts[step.contract] = step.target_version
        updated["contracts"] = updated_contracts
        # The manifest is deliberately the final replacement/commit point.
        atomic_write_text(manifest, yaml.safe_dump(updated, sort_keys=False, allow_unicode=True))
        event("committed")
        backup_manifest["state"] = "committed"
        atomic_write_text(bundle / "manifest.json", json.dumps(backup_manifest, sort_keys=True, indent=2) + "\n")
    except BaseException as exc:
        rollback_errors: list[str] = []
        for path, content in originals.items():
            try:
                _reject_link(path, through=root)
                if content is None:
                    path.unlink(missing_ok=True)
                    _fsync_dir(path.parent)
                else:
                    _atomic_bytes(path, content)
            except (OSError, MigrationApplyError) as restore_exc:
                rollback_errors.append(f"{path.relative_to(root).as_posix()}: {restore_exc}")
        try:
            event("rolled-back")
            backup_manifest["state"] = "rolled-back"
            atomic_write_text(bundle / "manifest.json", json.dumps(backup_manifest, sort_keys=True, indent=2) + "\n")
        except Exception:
            rollback_errors.append("could not durably record rollback state")
        lock_context.__exit__(None, None, None)
        if rollback_errors:
            raise MigrationApplyError(
                "migration failed and automatic rollback is incomplete; startup is blocked: "
                + "; ".join(rollback_errors)
            ) from exc
        raise MigrationApplyError(f"migration failed and rollback was attempted: {exc}") from exc
    result = MigrationApplyResult("applied", digest, bundle.relative_to(root).as_posix(),
                                  tuple(step.contract for step in changed))
    lock_context.__exit__(None, None, None)
    return result


def rollback_contract_migration(
    project_root: Path,
    backup_bundle: Path,
    *,
    confirmation_token: str | None = None,
) -> MigrationApplyResult:
    """Restore a verified backup bundle, with the project manifest restored last."""
    root = project_root.resolve(strict=True)
    allowed = root / ".science" / "migrations"
    bundle = backup_bundle if backup_bundle.is_absolute() else root / backup_bundle
    if not _inside(allowed.resolve(strict=False), bundle) or not bundle.is_dir():
        raise MigrationApplyError("backup bundle must be inside the project's migration directory")
    _reject_link(bundle, through=root)
    try:
        metadata = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        plan_digest = metadata["plan_sha256"]
        entries = metadata["entries"]
    except Exception as exc:
        raise MigrationApplyError(f"cannot read backup manifest: {exc}") from exc
    if confirmation_token != rollback_confirmation_token(plan_digest):
        raise MigrationApplyError("explicit rollback token does not match the backup")
    if not isinstance(entries, list) or not isinstance(plan_digest, str):
        raise MigrationApplyError("invalid backup manifest structure")
    try:
        with _migration_lock(root):
            # Re-read under lock so a concurrent/tampered bundle cannot swap metadata.
            locked_metadata = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            if locked_metadata != metadata:
                raise MigrationApplyError("backup manifest changed while acquiring migration lock")
            names = _restore_entries(root, bundle, metadata)
            with (bundle / "wal.jsonl").open("a", encoding="utf-8", newline="") as stream:
                stream.write(json.dumps({"phase": "explicit-rollback",
                                         "at": datetime.now(timezone.utc).isoformat()}) + "\n")
                stream.flush(); os.fsync(stream.fileno())
            metadata["state"] = "rolled-back"
            atomic_write_text(bundle / "manifest.json", json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    except OSError as exc:
        raise MigrationApplyError(f"rollback could not be completed: {exc}") from exc
    return MigrationApplyResult("rolled-back", plan_digest, bundle.relative_to(root).as_posix(), names)
