#!/usr/bin/env python3
"""Reviewed V3 production schema migration operation.

Applies committed V3 lineage migrations to the retained production PostgreSQL
database through the same fail-closed gates the application promotion path uses,
and is deliberately separate from it: that deployer is forbidden from changing
schema, and this operation is forbidden from changing services.

The desired state is the committed V3 lineage manifest. The operation reads what
the live database actually has, refuses unless the live ledger is an exact prefix
of the desired set, then applies the remainder in order. Each migration must
manage its own transaction, and its ledger row is inserted immediately before
that migration's commit so the schema and ledger advance atomically.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
MIGRATION_RECEIPT_SCHEMA = "ed-finder/v3-production-migration-receipt/v1"
EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
EXPECTED_DATABASE_PORT = 5432
POSTGRES_SOCKET = "/var/run/postgresql"
LEDGER_NAME = re.compile(r"(?:r[0-9]+_v3/)?[0-9]{3}_[a-z0-9_]+\.sql\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
MAX_MIGRATION_BYTES = 8 * 1024 * 1024


class MigrationError(ValueError):
    """A reviewed migration precondition was not met."""


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise MigrationError(f"{module_name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deployer_module() -> Any:
    """Reuse the promotion deployer's guards rather than duplicating them."""
    return _load("v3_production_deploy", ROOT / "scripts/operator/v3_production_deploy.py")


def identity_module() -> Any:
    return _load("v3_schema_identity", ROOT / "scripts/operator/v3_schema_identity.py")


def desired_entries(root: Path = ROOT) -> list[dict[str, str]]:
    """The committed V3 lineage as an ordered list, with hashes verified on disk."""
    try:
        entries = identity_module().derive_entries(root)
    except Exception as exc:  # the identity helper raises its own error type
        raise MigrationError(f"unable to derive the desired migration set: {exc}") from exc
    for entry in entries:
        if not LEDGER_NAME.fullmatch(str(entry.get("ledger_name", ""))):
            raise MigrationError("desired migration ledger name is invalid")
    return entries


def desired_digest(entries: list[dict[str, str]]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def live_ledger(
    deployer: Any, env: dict[str, str], runner: Callable[..., Any]
) -> list[dict[str, str]]:
    """Read the applied ledger under BEGIN READ ONLY, exactly as the deployer does."""
    result = runner(
        [
            "docker", "exec", deployer.POSTGRES_CONTAINER, "psql", "-X", "--no-password",
            "--tuples-only", "--no-align", "--quiet", "--field-separator", "\t",
            "--set", "ON_ERROR_STOP=1", "--username", deployer.DATABASE_USER,
            "--dbname", deployer.DATABASE_NAME, "--host", POSTGRES_SOCKET,
            "--port", str(EXPECTED_DATABASE_PORT), "--command", deployer.LEDGER_SQL,
        ],
        env=env,
    )
    if len(result.stdout.encode("utf-8")) > deployer.MAX_JSON:
        raise MigrationError("live migration ledger output exceeds size limit")
    try:
        observed = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise MigrationError("live migration ledger returned invalid JSON") from exc
    if not isinstance(observed, dict) or set(observed) != {
        "database_name", "server_address", "server_port",
        "transaction_read_only", "migrations",
    }:
        raise MigrationError("live migration ledger returned invalid shape")
    if observed["transaction_read_only"] != "on":
        raise MigrationError("live migration ledger was not read read-only")
    if (
        observed["database_name"] != deployer.DATABASE_NAME
        or observed["server_address"] != "local"
        or observed["server_port"] != EXPECTED_DATABASE_PORT
    ):
        raise MigrationError("live migration ledger came from an unexpected database server")
    ledger = observed["migrations"]
    if not isinstance(ledger, list):
        raise MigrationError("live migration ledger entries are invalid")
    for item in ledger:
        if (
            not isinstance(item, dict)
            or set(item) != {"filename", "checksum_sha256"}
            or not LEDGER_NAME.fullmatch(str(item["filename"]))
            or not HEX64.fullmatch(str(item["checksum_sha256"]))
        ):
            raise MigrationError("live migration ledger entries are invalid")
    if len({item["filename"] for item in ledger}) != len(ledger):
        raise MigrationError("live migration ledger has duplicate entries")
    return [
        {"ledger_name": item["filename"], "sha256": item["checksum_sha256"]}
        for item in ledger
    ]


def plan_migrations(
    desired: list[dict[str, str]], live: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return ``(applied, pending)`` or refuse on any divergence.

    The live ledger must be an exact prefix of the desired set: same order, same
    names, same hashes. Anything else means the database is not in the state this
    operation was written to advance, and guessing would be the whole risk.
    """
    if len(live) > len(desired):
        raise MigrationError(
            "live ledger is ahead of the committed lineage; refusing to guess"
        )
    for index, applied in enumerate(live):
        expected = desired[index]
        if applied["ledger_name"] != expected["ledger_name"]:
            raise MigrationError(
                f"live ledger diverges at position {index + 1}:"
                f" found {applied['ledger_name']}, expected {expected['ledger_name']}"
            )
        if applied["sha256"] != expected["sha256"]:
            raise MigrationError(
                f"live ledger hash mismatch for {applied['ledger_name']}"
            )
    return live, desired[len(live):]


def terminal_commit_span(text: str, label: str) -> tuple[int, int]:
    """A migration about to be applied must own its transaction.

    Without this, a migration that fails halfway could leave half its statements
    committed, and the operation would then have no honest choice but to stop with
    the database in an unexplained state.
    """
    statements: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            statements.append((offset + len(line) - len(line.lstrip()), stripped))
        offset += len(line)
    if (
        not statements
        or statements[0][1].upper() != "BEGIN;"
        or statements[-1][1].upper() != "COMMIT;"
    ):
        raise MigrationError(
            f"{label} does not manage its own transaction (needs BEGIN; ... COMMIT;)"
        )
    commit_start = statements[-1][0]
    return commit_start, commit_start + len("COMMIT;")


def require_self_transactional(text: str, label: str) -> None:
    terminal_commit_span(text, label)


def migration_with_atomic_ledger(entry: dict[str, str], text: str) -> str:
    """Insert the ledger row immediately before the validated terminal COMMIT."""
    commit_start, commit_end = terminal_commit_span(text, entry["path"])
    ledger = (
        "INSERT INTO v3_meta.schema_migration (migration_name, migration_sha256)\n"
        f"  VALUES ('{entry['ledger_name']}', decode('{entry['sha256']}', 'hex'));\n"
        "COMMIT;"
    )
    return text[:commit_start] + ledger + text[commit_end:]


def migration_text(entry: dict[str, str], root: Path = ROOT) -> str:
    path = root / entry["path"]
    try:
        if path.stat().st_size > MAX_MIGRATION_BYTES or path.is_symlink():
            raise MigrationError(f"{entry['path']} is oversized or unsafe")
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrationError(f"unable to read {entry['path']}") from exc
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != entry["sha256"]:
        raise MigrationError(f"{entry['path']} changed after the plan was derived")
    return text


def apply_migration(
    deployer: Any, entry: dict[str, str], env: dict[str, str],
    runner: Callable[..., Any], root: Path = ROOT,
) -> None:
    text = migration_text(entry, root)
    psql = [
        "docker", "exec", "-i", deployer.POSTGRES_CONTAINER, "psql", "-X", "--no-psqlrc",
        "--set", "ON_ERROR_STOP=1", "--username", deployer.DATABASE_USER,
        "--dbname", deployer.DATABASE_NAME, "--host", POSTGRES_SOCKET,
        "--port", str(EXPECTED_DATABASE_PORT),
    ]
    # Insert the ledger row before the migration's own terminal COMMIT, so DDL
    # and identity advance are one PostgreSQL transaction with no crash window.
    combined = migration_with_atomic_ledger(entry, text)
    runner(psql, env=env, input_text=combined)


def verify_schema_identity(deployer: Any, external: dict[str, Any]) -> str:
    """The pinned reviewed identity must match the host file before any DDL."""
    path = Path(str(external["schema_identity_file"]))
    deployer.secure_path(
        path, external["schema_identity_owner_uid"], external["schema_identity_mode"],
        directory=False,
    )
    digest = deployer.sha256_file(path)
    if digest != external["schema_identity_sha256"]:
        raise MigrationError("pinned production schema identity does not match the host file")
    return digest


def prefix_identities(identity: Any, desired: list[dict[str, str]]) -> list[str]:
    return [
        identity.migration_set_identity(desired[:count])
        for count in range(1, len(desired) + 1)
    ]


def inspect_schema_transition(
    deployer: Any, authority: dict[str, Any], external: dict[str, Any],
    desired: list[dict[str, str]], target_identity_path: Path,
    live: list[dict[str, str]],
) -> tuple[dict[str, Any], str, bool]:
    """Bind the live prefix, host identity and candidate target identity."""
    identity = identity_module()
    target_sha = str(external["schema_identity_sha256"])
    target = deployer.validate_schema_file(target_identity_path, target_sha)
    if target["migration_set_entries"] != desired:
        raise MigrationError("candidate schema identity does not match committed V3 lineage")
    transition = authority["schema_transition"]
    if target["migration_set_identity"] != transition["to_migration_set_identity"]:
        raise MigrationError("candidate schema identity does not match transition target")
    identities = prefix_identities(identity, desired)
    try:
        from_count = identities.index(transition["from_migration_set_identity"]) + 1
    except ValueError as exc:
        raise MigrationError("schema transition source is not a committed lineage prefix") from exc
    live_identity = identity.migration_set_identity(desired[:len(live)])
    if len(live) < from_count or live_identity not in identities[from_count - 1:]:
        raise MigrationError("live schema is outside the reviewed transition range")
    compatible = authority["accepted_release_schema_compatibility"][
        "compatible_migration_sets"
    ]
    missing = [item for item in identities[from_count - 1:] if item not in compatible]
    if missing:
        raise MigrationError("accepted release compatibility omits a transition prefix")

    host_path = Path(str(external["schema_identity_file"]))
    deployer.secure_path(
        host_path, external["schema_identity_owner_uid"],
        external["schema_identity_mode"], directory=False,
    )
    host_sha = deployer.sha256_file(host_path)
    if host_sha == target_sha:
        host = deployer.validate_schema_file(host_path, target_sha)
        if host != target or live_identity != target["migration_set_identity"]:
            raise MigrationError("installed target schema identity is ahead of the live ledger")
        return target, host_sha, False
    if host_sha != transition["from_schema_identity_sha256"]:
        raise MigrationError("installed schema identity is outside the reviewed transition")
    host = deployer.validate_schema_file(
        host_path, transition["from_schema_identity_sha256"]
    )
    if host["migration_set_identity"] != transition["from_migration_set_identity"]:
        raise MigrationError("installed schema identity does not match transition source")
    return target, host_sha, True


def verify_active_release_supports_target(
    deployer: Any, authority: dict[str, Any], target: dict[str, Any],
    env: dict[str, str], runner: Callable[..., Any],
) -> None:
    receipt_dir = Path(str(authority["external_authority"]["receipt_directory"]))
    receipt, manifest, _ = deployer.load_current(receipt_dir)
    deployer.validate_prior_runtime(
        receipt, manifest, target, env, runner,
        authority["accepted_release_schema_compatibility"],
    )


def install_schema_identity(
    deployer: Any, source: Path, target: Path, *, owner_uid: int, mode: str,
) -> None:
    """Atomically publish the target identity only after the ledger is complete."""
    body = source.read_bytes()
    handle, temp_name = tempfile.mkstemp(prefix=".schema-identity-", dir=target.parent)
    try:
        os.fchmod(handle, int(mode, 8))
        os.fchown(handle, owner_uid, target.stat(follow_symlinks=False).st_gid)
        with os.fdopen(handle, "wb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    if deployer.sha256_file(target) != deployer.sha256_file(source):
        raise MigrationError("installed target schema identity checksum mismatch")


def write_receipt(directory: Path, name: str, payload: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    sidecar_body = f"{digest}  {name}\n".encode("utf-8")
    receipt_handle, receipt_temp = tempfile.mkstemp(
        prefix=".v3-production-migration-receipt-", dir=directory
    )
    sidecar_handle = -1
    sidecar_temp: str | None = None
    try:
        sidecar_handle, sidecar_temp = tempfile.mkstemp(
            prefix=".v3-production-migration-sidecar-", dir=directory
        )
        os.fchmod(receipt_handle, 0o600)
        with os.fdopen(receipt_handle, "wb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.fchmod(sidecar_handle, 0o600)
        with os.fdopen(sidecar_handle, "wb") as output:
            output.write(sidecar_body)
            output.flush()
            os.fsync(output.fileno())

        # Publish the checksum first, then make the receipt itself the commit
        # marker. Directory fsyncs make both renames durable across host crash.
        os.replace(sidecar_temp, directory / f"{name}.sha256")
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
            os.replace(receipt_temp, directory / name)
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        for handle in (receipt_handle, sidecar_handle):
            try:
                os.close(handle)
            except OSError:
                pass
        for temp_name in (receipt_temp, sidecar_temp):
            if temp_name is None:
                continue
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
    return directory / name


def begin_audit_finalization(deployer: Any, controller: Any | None) -> None:
    """Make the short, durable audit publication phase cancellation-safe."""
    if controller is None:
        return
    # Block the race between deciding that mutation is over and changing the
    # handlers. mark_commit_started then ignores cancellation until the receipt
    # and checksum sidecar are durably published and the process exits.
    with deployer.cancellation_blocked():
        controller.mark_commit_started()


def observe_schema_identity(deployer: Any, external: dict[str, Any]) -> str:
    """Read the installed identity through the same host trust boundary."""
    path = Path(str(external["schema_identity_file"]))
    deployer.secure_path(
        path, external["schema_identity_owner_uid"],
        external["schema_identity_mode"], directory=False,
    )
    return deployer.sha256_file(path)


def reconcile_schema_identity_after_failure(
    deployer: Any, external: dict[str, Any], *,
    identity_before: str | None, identity_target: str | None,
) -> tuple[str | None, bool | None, list[str]]:
    """Report what an interrupted/failed atomic identity install actually left."""
    try:
        observed = observe_schema_identity(deployer, external)
    except Exception as exc:
        return (
            None,
            None,
            [f"post_failure_schema_identity_unverified:{type(exc).__name__}"],
        )
    failures = []
    if observed not in {identity_before, identity_target}:
        failures.append("post_failure_schema_identity_unexpected")
    updated = None if identity_before is None else identity_before != observed
    return observed, updated, failures


def receipt_payload(
    authority: dict[str, Any], *, status: str, desired: list[dict[str, str]],
    applied: list[dict[str, str]], pending: list[dict[str, str]],
    applied_now: list[dict[str, str]], identity_sha256: str | None,
    failures: list[str], writes: bool | None,
    source_sha: str | None = None, workflow_run_id: str | None = None,
    database_access: bool | None = True,
    identity_before_sha256: str | None = None,
    identity_after_sha256: str | None = None,
    identity_updated: bool | None = False,
    prior_release_compatibility_verified: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": MIGRATION_RECEIPT_SCHEMA,
        "operation": "production-migration",
        "status": status,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_sha": source_sha,
        "workflow_run_id": workflow_run_id,
        "target": {
            "production": True,
            "hostname": EXPECTED_HOST,
            "fqdn": EXPECTED_FQDN,
        },
        "desired_ledger_sha256": desired_digest(desired) if desired else None,
        "schema_identity_sha256": identity_sha256,
        "schema_identity_before_sha256": identity_before_sha256,
        "schema_identity_after_sha256": identity_after_sha256,
        "schema_identity_updated": identity_updated,
        "prior_release_compatibility_verified": prior_release_compatibility_verified,
        "applied_before": applied,
        "pending": pending,
        "applied_now": applied_now,
        "database_access_performed": database_access,
        "database_writes_performed": writes,
        "migrations_performed": (
            None if writes is None and not applied_now else bool(applied_now)
        ),
        "service_changes_performed": False,
        "edge_recreated": False,
        "protected_resources_changed": False,
        "failures": failures,
    }


def _main(deployer: Any, cancellation_controller: Any | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation", choices=("authority-gate", "plan", "apply"), default="authority-gate"
    )
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--candidate-schema-identity", type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    arguments = parser.parse_args()

    authority: dict[str, Any] = {}
    desired: list[dict[str, str]] = []
    applied: list[dict[str, str]] = []
    pending: list[dict[str, str]] = []
    identity_sha256: str | None = None
    identity_before: str | None = None
    identity_after: str | None = None
    identity_updated: bool | None = False
    database_access: bool | None = False
    source_sha = arguments.source_sha if SOURCE_SHA.fullmatch(arguments.source_sha) else None
    workflow_run_id = (
        arguments.workflow_run_id
        if RUN_ID.fullmatch(arguments.workflow_run_id)
        else None
    )
    try:
        if source_sha is None or workflow_run_id is None:
            raise MigrationError("workflow source SHA or run ID is invalid")
        authority = deployer.load_json(arguments.authority, "production target authority")
        deployer.validate_authority(authority)
        deployer.exact_host_guard(deployer.run_command)
        external = authority["external_authority"]
        identity_sha256 = str(external["schema_identity_sha256"])
        env = deployer.base_env(external)
        deployer.docker_context_guard(env, deployer.run_command)
        receipt_dir = Path(str(external["receipt_directory"]))
        deployer.secure_path(
            receipt_dir, external["receipt_owner_uid"], external["receipt_mode"],
            directory=True,
        )
        if arguments.candidate_schema_identity is None:
            raise MigrationError("candidate target schema identity is required")
        desired = desired_entries(arguments.root)
        database_access = None
        live = live_ledger(deployer, env, deployer.run_command)
        database_access = True
        applied = live
        applied, pending = plan_migrations(desired, live)
        target, identity_before, identity_install_pending = inspect_schema_transition(
            deployer, authority, external, desired,
            arguments.candidate_schema_identity, live,
        )
        verify_active_release_supports_target(
            deployer, authority, target, env, deployer.run_command
        )
    except Exception as exc:
        payload = receipt_payload(
            authority, status="stopped", desired=desired, applied=applied,
            pending=pending, applied_now=[], identity_sha256=identity_sha256,
            failures=[str(exc)], writes=False, source_sha=source_sha,
            workflow_run_id=workflow_run_id, database_access=database_access,
            identity_before_sha256=identity_before,
        )
        print(json.dumps(payload, sort_keys=True))
        return 78

    if arguments.operation == "authority-gate":
        print(json.dumps(
            {"status": "migration-authority-verified", "pending": len(pending)},
            sort_keys=True,
        ))
        return 0

    if arguments.operation == "plan":
        payload = receipt_payload(
            authority, status="planned", desired=desired, applied=applied, pending=pending,
            applied_now=[], identity_sha256=identity_sha256, failures=[], writes=False,
            source_sha=source_sha, workflow_run_id=workflow_run_id,
            database_access=database_access,
            identity_before_sha256=identity_before,
            identity_after_sha256=identity_before,
            identity_updated=False, prior_release_compatibility_verified=True,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0

    lock = None
    applied_now: list[dict[str, str]] = []
    migration_in_flight = False
    write_state: bool | None = False
    try:
        lock = deployer.acquire_lock(receipt_dir)
        # Re-evaluate every mutable input under the same lock used by application
        # promotion. A reviewed plan is evidence, not permission to use stale state.
        live = live_ledger(deployer, env, deployer.run_command)
        applied, pending = plan_migrations(desired, live)
        target, identity_before, identity_install_pending = inspect_schema_transition(
            deployer, authority, external, desired,
            arguments.candidate_schema_identity, live,
        )
        verify_active_release_supports_target(
            deployer, authority, target, env, deployer.run_command
        )
        for entry in pending:
            migration_in_flight = True
            apply_migration(deployer, entry, env, deployer.run_command, arguments.root)
            applied_now.append(entry)
            migration_in_flight = False
        final_live = live_ledger(deployer, env, deployer.run_command)
        plan_migrations(desired, final_live)
        if len(final_live) != len(desired):
            raise MigrationError("live ledger does not equal the committed lineage after apply")
        if identity_install_pending:
            install_schema_identity(
                deployer, arguments.candidate_schema_identity,
                Path(str(external["schema_identity_file"])),
                owner_uid=external["schema_identity_owner_uid"],
                mode=external["schema_identity_mode"],
            )
        identity_after = deployer.sha256_file(
            Path(str(external["schema_identity_file"]))
        )
        if identity_after != identity_sha256:
            raise MigrationError("target schema identity was not installed")
        identity_updated = identity_before != identity_after
        begin_audit_finalization(deployer, cancellation_controller)
        status = "applied"
        failures: list[str] = []
        write_state = bool(applied_now)
    except Exception as exc:
        # run_command reaps its child on cancellation, timeout and process
        # failure. Once control reaches this handler, preserve an exact audit
        # record even if the workflow sends another termination signal.
        begin_audit_finalization(deployer, cancellation_controller)
        status, failures = "stopped", [str(exc)]
        if migration_in_flight:
            try:
                after_failure = live_ledger(deployer, env, deployer.run_command)
                plan_migrations(desired, after_failure)
                if len(after_failure) < len(applied):
                    raise MigrationError("live ledger moved behind the locked apply state")
                applied_now = after_failure[len(applied):]
                write_state = bool(applied_now)
            except Exception as verify_exc:
                write_state = None
                failures.append(
                    "post_interruption_ledger_unverified:"
                    f"{type(verify_exc).__name__}"
                )
        else:
            write_state = bool(applied_now)
        identity_after, identity_updated, identity_failures = (
            reconcile_schema_identity_after_failure(
                deployer, external, identity_before=identity_before,
                identity_target=identity_sha256,
            )
        )
        failures.extend(identity_failures)
    finally:
        if lock is not None:
            lock.close()

    payload = receipt_payload(
        authority, status=status, desired=desired, applied=applied, pending=pending,
        applied_now=applied_now, identity_sha256=identity_sha256, failures=failures,
        writes=write_state, source_sha=source_sha, workflow_run_id=workflow_run_id,
        database_access=database_access, identity_before_sha256=identity_before,
        identity_after_sha256=identity_after,
        identity_updated=identity_updated,
        prior_release_compatibility_verified=True,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"migration-{desired_digest(desired)[7:19]}-{stamp}.json"
    path = write_receipt(receipt_dir, name, payload)
    print(json.dumps({**payload, "receipt": str(path)}, sort_keys=True))
    return 0 if status == "applied" else 78


def main() -> int:
    deployer = deployer_module()
    # Reuse the deployer's process-group-aware cancellation controller. If the
    # workflow is cancelled while psql is active, it terminates and reaps the
    # exact Docker subprocess before the stopped receipt is written.
    with deployer.controlled_cancellation() as cancellation_controller:
        return _main(deployer, cancellation_controller)


if __name__ == "__main__":
    raise SystemExit(main())
