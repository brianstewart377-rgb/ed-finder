#!/usr/bin/env python3
"""Reviewed V3 production schema migration operation.

Applies committed V3 lineage migrations to the retained production PostgreSQL
database through the same fail-closed gates the application promotion path uses,
and is deliberately separate from it: that deployer is forbidden from changing
schema, and this operation is forbidden from changing services.

The desired state is the committed V3 lineage manifest. The operation reads what
the live database actually has, refuses unless the live ledger is an exact prefix
of the desired set, then applies the remainder in order. Each migration must
manage its own transaction, and its ledger row is recorded only after that
migration commits.
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
LEDGER_NAME = re.compile(r"(?:r[0-9]+_v3/)?[0-9]{3}_[a-z0-9_]+\.sql\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
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
            "--dbname", deployer.DATABASE_NAME, "--command", deployer.LEDGER_SQL,
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


def require_self_transactional(text: str, label: str) -> None:
    """A migration about to be applied must own its transaction.

    Without this, a migration that fails halfway could leave half its statements
    committed, and the operation would then have no honest choice but to stop with
    the database in an unexplained state.
    """
    statements = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    if not statements or statements[0].upper() != "BEGIN;" or statements[-1].upper() != "COMMIT;":
        raise MigrationError(
            f"{label} does not manage its own transaction (needs BEGIN; ... COMMIT;)"
        )


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
    require_self_transactional(text, entry["path"])
    psql = [
        "docker", "exec", "-i", deployer.POSTGRES_CONTAINER, "psql", "-X", "--no-psqlrc",
        "--set", "ON_ERROR_STOP=1", "--username", deployer.DATABASE_USER,
        "--dbname", deployer.DATABASE_NAME,
    ]
    runner(psql, env=env, input_text=text)
    # The ledger row is recorded only once the migration has committed. The name
    # is validated against LEDGER_NAME above, so this interpolation is safe.
    runner(
        [*psql, "--command",
         "BEGIN;\n"
         f"INSERT INTO v3_meta.schema_migration (migration_name, migration_sha256)\n"
         f"  VALUES ('{entry['ledger_name']}', decode('{entry['sha256']}', 'hex'));\n"
         "COMMIT;\n"],
        env=env,
    )


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


def write_receipt(directory: Path, name: str, payload: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    handle, temp_name = tempfile.mkstemp(prefix=".v3-production-migration-", dir=directory)
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "wb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, directory / name)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    sidecar = directory / f"{name}.sha256"
    sidecar.write_text(f"{digest}  {name}\n", encoding="utf-8")
    os.chmod(sidecar, 0o600)
    return directory / name


def receipt_payload(
    authority: dict[str, Any], *, status: str, desired: list[dict[str, str]],
    applied: list[dict[str, str]], pending: list[dict[str, str]],
    applied_now: list[dict[str, str]], identity_sha256: str | None,
    failures: list[str], writes: bool,
) -> dict[str, Any]:
    target = authority.get("target") if isinstance(authority.get("target"), dict) else {}
    return {
        "schema_version": MIGRATION_RECEIPT_SCHEMA,
        "operation": "production-migration",
        "status": status,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target": {
            "production": True,
            "hostname": target.get("hostname"),
            "fqdn": target.get("fqdn"),
        },
        "desired_ledger_sha256": desired_digest(desired),
        "schema_identity_sha256": identity_sha256,
        "applied_before": applied,
        "pending": pending,
        "applied_now": applied_now,
        "database_access_performed": True,
        "database_writes_performed": writes,
        "migrations_performed": bool(applied_now),
        "service_changes_performed": False,
        "edge_recreated": False,
        "protected_resources_changed": False,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation", choices=("authority-gate", "plan", "apply"), default="authority-gate"
    )
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()

    deployer = deployer_module()
    try:
        authority = deployer.load_json(arguments.authority, "production target authority")
        deployer.validate_authority(authority)
        deployer.exact_host_guard(deployer.run_command)
        external = authority["external_authority"]
        env = deployer.base_env(external)
        deployer.docker_context_guard(env, deployer.run_command)
        identity_sha256 = verify_schema_identity(deployer, external)
        desired = desired_entries(arguments.root)
        live = live_ledger(deployer, env, deployer.run_command)
        applied, pending = plan_migrations(desired, live)
    except Exception as exc:
        print(json.dumps({"status": "stopped", "failures": [str(exc)]}, sort_keys=True))
        return 78

    if arguments.operation == "authority-gate":
        print(json.dumps(
            {"status": "migration-authority-verified", "pending": len(pending)},
            sort_keys=True,
        ))
        return 0

    receipt_dir = Path(str(external["receipt_directory"]))
    if arguments.operation == "plan":
        payload = receipt_payload(
            authority, status="planned", desired=desired, applied=applied, pending=pending,
            applied_now=[], identity_sha256=identity_sha256, failures=[], writes=False,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0

    lock = None
    applied_now: list[dict[str, str]] = []
    try:
        lock = deployer.acquire_lock(receipt_dir)
        for entry in pending:
            apply_migration(deployer, entry, env, deployer.run_command, arguments.root)
            applied_now.append(entry)
        final_live = live_ledger(deployer, env, deployer.run_command)
        plan_migrations(desired, final_live)
        if len(final_live) != len(desired):
            raise MigrationError("live ledger does not equal the committed lineage after apply")
        status = "applied"
        failures: list[str] = []
    except Exception as exc:
        status, failures = "stopped", [str(exc)]
    finally:
        if lock is not None:
            lock.close()

    payload = receipt_payload(
        authority, status=status, desired=desired, applied=applied, pending=pending,
        applied_now=applied_now, identity_sha256=identity_sha256, failures=failures,
        writes=bool(applied_now),
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"migration-{desired_digest(desired)[7:19]}-{stamp}.json"
    path = write_receipt(receipt_dir, name, payload)
    print(json.dumps({**payload, "receipt": str(path)}, sort_keys=True))
    return 0 if status == "applied" else 78


if __name__ == "__main__":
    raise SystemExit(main())
