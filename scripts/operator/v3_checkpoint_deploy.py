#!/usr/bin/env python3
"""Fail-closed, application-only V3 live-checkpoint deployment boundary."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORITY = ROOT / "deploy/v3-live-checkpoint/target-authority.json"
DEFAULT_COMPOSE = ROOT / "deploy/v3-live-checkpoint/compose.yml"
TARGET_SCHEMA = "ed-finder/v3-live-checkpoint-target-authority/v1"
RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-deployment-receipt/v1"
CURRENT_RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-current-receipt/v2"
SCHEMA_RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-schema-identity/v2"
PROJECT = "edfinder-v3-checkpoint"
LOCAL_DOCKER_ENDPOINT = "unix:///var/run/docker.sock"
TARGET_HOSTNAME = "vmi3542235"
TARGET_FQDN = "vmi3542235.contaboserver.net"
SERVICES = ("api", "web")
CONTAINERS = {
    "api": "edfinder-v3-checkpoint-api",
    "web": "edfinder-v3-checkpoint-web",
}
NETWORK_ALIASES = {
    service: frozenset((service, container))
    for service, container in CONTAINERS.items()
}
APP_NETWORK = "edfinder-v3-checkpoint-app"
RESOURCE_LIMITS = {
    "api": {"cpus": "1.50", "memory": "1536m", "pids": 256},
    "web": {"cpus": "0.50", "memory": "512m", "pids": 128},
}
RUNNER_SERVICES = {
    "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service",
    "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service",
    "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service",
}
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
LOOPBACK_ORIGIN = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})\Z")
MAX_JSON_BYTES = 1024 * 1024
MAX_SMOKE_BYTES = 2 * 1024 * 1024
SCHEMA_RECEIPT_MAX_AGE = timedelta(hours=24)
SCHEMA_RECEIPT_FUTURE_TOLERANCE = timedelta(minutes=5)
READINESS_TIMEOUT_SECONDS = 120.0
READINESS_INTERVAL_SECONDS = 2.0
ORIGIN_REQUEST_TIMEOUT_SECONDS = 10.0
DATABASE_QUERY_TIMEOUT_SECONDS = 10


class DeploymentError(ValueError):
    pass


class OperationFailed(DeploymentError):
    def __init__(self, receipt: dict[str, Any]):
        super().__init__("deployment operation failed")
        self.receipt = receipt


def load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise DeploymentError(f"{description} exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except DeploymentError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(
            f"unable to read {description}: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"{description} must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise DeploymentError(
            f"unable to checksum artifact: {type(exc).__name__}"
        ) from exc
    return digest.hexdigest()


def verify_checksum(document: Path, checksum: Path) -> str:
    try:
        fields = checksum.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise DeploymentError(f"unable to read checksum: {type(exc).__name__}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != document.name:
        raise DeploymentError("checksum must name only the adjacent manifest basename")
    expected = fields[0]
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise DeploymentError("checksum is not 64 lowercase hexadecimal characters")
    if sha256_file(document) != expected:
        raise DeploymentError("manifest checksum mismatch")
    return expected


def load_manifest_tool() -> Any:
    path = ROOT / "scripts/release/v3_release_manifest.py"
    spec = importlib.util.spec_from_file_location("v3_release_manifest", path)
    if spec is None or spec.loader is None:
        raise DeploymentError("release manifest verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_authority(authority: dict[str, Any]) -> list[str]:
    if authority.get("schema_version") != TARGET_SCHEMA:
        raise DeploymentError("unsupported target authority schema")
    target = authority.get("target")
    contract = authority.get("application_contract")
    external = authority.get("external_authority")
    if not isinstance(target, dict) or target.get("production") is not False:
        raise DeploymentError("target must be explicitly non-production")
    if (
        target.get("provider") != "contabo"
        or target.get("classification") != "live-checkpoint"
    ):
        raise DeploymentError("unexpected live-checkpoint target")
    if target.get("hostname") != TARGET_HOSTNAME or target.get("fqdn") != TARGET_FQDN:
        raise DeploymentError("unexpected Contabo host identity authority")
    if not isinstance(contract, dict) or contract.get("compose_project") != PROJECT:
        raise DeploymentError("unexpected Compose project authority")
    if contract.get("network") != APP_NETWORK or contract.get("named_volumes") != []:
        raise DeploymentError("checkpoint network/volume authority is invalid")
    service_contract = contract.get("services")
    if not isinstance(service_contract, dict) or set(service_contract) != set(SERVICES):
        raise DeploymentError(
            "application service allowlist must be exactly api and web"
        )
    for service, container in CONTAINERS.items():
        item = service_contract.get(service)
        if not isinstance(item, dict) or item.get("container_name") != container:
            raise DeploymentError(f"unexpected {service} container authority")
        if {key: item.get(key) for key in RESOURCE_LIMITS[service]} != RESOURCE_LIMITS[
            service
        ]:
            raise DeploymentError(f"unexpected {service} resource limit authority")
    runtime = authority.get("observed_runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime.get("runner_services", [])) != RUNNER_SERVICES
    ):
        raise DeploymentError("exact three-runner preservation authority is missing")
    status = authority.get("status")
    blockers = authority.get("blockers")
    if status not in {"authorized", "stopped"} or not isinstance(blockers, list):
        raise DeploymentError("target authority status/blockers are invalid")
    if status == "stopped":
        if not blockers or any(
            not isinstance(item, str) or not item for item in blockers
        ):
            raise DeploymentError("stopped target authority requires exact blockers")
        return sorted(set(blockers))
    if blockers:
        raise DeploymentError("authorized target authority cannot retain blockers")
    runtime_networks = runtime.get("docker_networks")
    if (
        not isinstance(runtime.get("container_runtime"), str)
        or not runtime["container_runtime"].strip()
        or not isinstance(runtime.get("compose"), str)
        or not runtime["compose"].strip()
        or not isinstance(runtime_networks, list)
        or APP_NETWORK not in runtime_networks
    ):
        raise DeploymentError(
            "authorized target requires proven Docker, Compose and app network facts"
        )
    required_external = {
        "api_env_file",
        "api_env_owner_uid",
        "api_env_mode",
        "database_source_authority",
        "schema_identity_receipt",
        "schema_identity_receipt_sha256",
        "origin_bind",
        "edge_route_authority",
        "receipt_directory",
        "receipt_owner_uid",
        "receipt_mode",
        "ghcr_pull_authority",
        "docker_config_directory",
        "docker_config_owner_uid",
        "docker_config_mode",
        "docker_context",
    }
    if not isinstance(external, dict) or set(external) != required_external:
        raise DeploymentError("external authority fields are incomplete")
    integer_authorities = {
        "api_env_owner_uid",
        "receipt_owner_uid",
        "docker_config_owner_uid",
    }
    string_authorities = required_external - integer_authorities
    if any(
        not isinstance(external[key], str) or not external[key].strip()
        for key in string_authorities
    ) or any(
        not isinstance(external[key], int) or external[key] < 0
        for key in integer_authorities
    ):
        raise DeploymentError("every external deployment authority must be explicit")
    for key in ("api_env_mode", "receipt_mode", "docker_config_mode"):
        if not re.fullmatch(r"0[0-7]{3}", external[key]):
            raise DeploymentError(
                "external file modes must be four-digit octal strings"
            )
    if not re.fullmatch(r"[0-9a-f]{64}", external["schema_identity_receipt_sha256"]):
        raise DeploymentError("schema identity receipt checksum authority is invalid")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", external["docker_context"]):
        raise DeploymentError("Docker context authority is invalid")
    match = LOOPBACK_ORIGIN.fullmatch(external["origin_bind"])
    if match is None or int(match.group(1)) > 65535:
        raise DeploymentError("origin authority must be an exact loopback HTTP origin")
    return []


def stopped_receipt(authority: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    target = (
        authority.get("target") if isinstance(authority.get("target"), dict) else {}
    )
    return {
        "schema_version": RECEIPT_SCHEMA,
        "operation": "v3-application-live-checkpoint-deploy",
        "status": "stopped",
        "target": {
            "provider": target.get("provider", "unknown"),
            "classification": target.get("classification", "live-checkpoint"),
            "production": False,
            "hostname": target.get("hostname", "unknown"),
        },
        "failures": sorted(set(failures)),
        "authorized_recreate_targets": list(SERVICES),
        "changed_resources": [],
        "database_access_performed": False,
        "migrations_performed": False,
        "service_changes_performed": False,
        "image_pulls_performed": False,
        "filesystem_writes_performed": False,
        "env_file_consumed_by_compose": False,
        "env_files_read": False,
        "private_keys_read": False,
    }


def validate_database_identity(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "database_name",
        "server_address",
        "server_port",
    }:
        raise DeploymentError("schema receipt database identity is invalid")
    database_name = value.get("database_name")
    server_address = value.get("server_address")
    server_port = value.get("server_port")
    if not isinstance(database_name, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,63}", database_name
    ):
        raise DeploymentError("schema receipt database name is invalid")
    try:
        if not isinstance(server_address, str):
            raise ValueError
        ipaddress.ip_address(server_address)
    except ValueError as exc:
        raise DeploymentError("schema receipt database address is invalid") from exc
    if not isinstance(server_port, int) or not 1 <= server_port <= 65535:
        raise DeploymentError("schema receipt database port is invalid")
    return value


def read_checkpoint_database_url(
    api_env_path: Path, *, on_read: Callable[[], None] | None = None
) -> str:
    """Read only the exact Compose-compatible DATABASE_URL assignment.

    The checkpoint contract deliberately requires a single unquoted literal URL.
    Rejecting interpolation and shell syntax makes the value used here identical
    to the value Compose gives the API without evaluating the env file.
    """

    try:
        if api_env_path.stat().st_size > MAX_JSON_BYTES:
            raise DeploymentError("authorized api_env_file exceeds the size limit")
        lines = api_env_path.read_text(encoding="utf-8").splitlines()
        if on_read is not None:
            on_read()
    except DeploymentError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise DeploymentError("unable to read authorized api_env_file") from exc
    values: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "DATABASE_URL":
            values.append(value.strip())
    if len(values) != 1:
        raise DeploymentError("api_env_file must contain exactly one DATABASE_URL")
    database_url = values[0]
    if (
        not database_url
        or any(character.isspace() for character in database_url)
        or database_url[0] in {'"', "'"}
        or "$" in database_url
        or "#" in database_url
    ):
        raise DeploymentError("api_env_file DATABASE_URL must be an unquoted literal")
    try:
        parsed = urllib.parse.urlsplit(database_url)
        database_name = urllib.parse.unquote(parsed.path.removeprefix("/"))
        port = parsed.port or 5432
        query_keys = {
            key.lower() for key, _value in urllib.parse.parse_qsl(parsed.query)
        }
    except ValueError as exc:
        raise DeploymentError("api_env_file DATABASE_URL is invalid") from exc
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or not database_name
        or "/" in database_name
        or parsed.fragment
        or "options" in query_keys
        or not 1 <= port <= 65535
    ):
        raise DeploymentError("api_env_file DATABASE_URL is invalid")
    return database_url


def freeze_authorized_env_file(
    source: Path,
    directory: Path,
    *,
    expected_uid: int,
    expected_mode: str,
    on_read: Callable[[], None] | None = None,
) -> tuple[Path, dict[str, Any], int]:
    """Copy one securely opened authority file into a private read-only snapshot."""

    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    snapshot: Path | None = None
    try:
        if not source.is_absolute():
            raise DeploymentError("authorized api_env_file path is unsafe")
        descriptor = os.open(source, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != expected_uid
            or stat.S_IMODE(before.st_mode) != int(expected_mode, 8)
            or before.st_size > MAX_JSON_BYTES
        ):
            raise DeploymentError("authorized api_env_file is missing or unsafe")
        data = bytearray()
        while len(data) <= MAX_JSON_BYTES:
            chunk = os.read(
                descriptor, min(1024 * 1024, MAX_JSON_BYTES + 1 - len(data))
            )
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_JSON_BYTES:
            raise DeploymentError("authorized api_env_file exceeds the size limit")
        after = os.fstat(descriptor)
        try:
            lexical = os.lstat(source)
        except OSError as exc:
            raise DeploymentError("authorized api_env_file changed while read") from exc
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_uid",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ) or (lexical.st_dev != after.st_dev or lexical.st_ino != after.st_ino):
            raise DeploymentError("authorized api_env_file changed while read")
        if on_read is not None:
            on_read()
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".v3-verified-api-env-", delete=False
        ) as handle:
            snapshot = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), 0o400)
            os.fsync(handle.fileno())
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        snapshot_stat = snapshot.stat()
        fingerprint = {
            "source_dev": after.st_dev,
            "source_ino": after.st_ino,
            "source_size": after.st_size,
            "source_mtime_ns": after.st_mtime_ns,
            "source_ctime_ns": after.st_ctime_ns,
            "sha256": hashlib.sha256(data).hexdigest(),
            "snapshot_dev": snapshot_stat.st_dev,
            "snapshot_ino": snapshot_stat.st_ino,
        }
        retained_descriptor = descriptor
        descriptor = None
        return snapshot, fingerprint, retained_descriptor
    except (OSError, ValueError) as exc:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)
        if isinstance(exc, DeploymentError):
            raise
        raise DeploymentError("unable to freeze authorized api_env_file") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def verify_frozen_env_snapshot(
    snapshot: Path,
    fingerprint: dict[str, Any],
) -> None:
    try:
        snapshot_stat = os.lstat(snapshot)
    except OSError as exc:
        raise DeploymentError("verified api_env_file snapshot changed") from exc
    if (
        not stat.S_ISREG(snapshot_stat.st_mode)
        or stat.S_IMODE(snapshot_stat.st_mode) != 0o400
        or snapshot_stat.st_dev != fingerprint["snapshot_dev"]
        or snapshot_stat.st_ino != fingerprint["snapshot_ino"]
        or sha256_file(snapshot) != fingerprint["sha256"]
    ):
        raise DeploymentError("verified api_env_file snapshot changed")


def verify_authorized_env_unchanged(
    source: Path,
    snapshot: Path,
    fingerprint: dict[str, Any],
    source_descriptor: int,
) -> None:
    """Prove the authority path did not drift and the snapshot is still exact."""

    try:
        source_stat = os.lstat(source)
        retained_source_stat = os.fstat(source_descriptor)
    except OSError as exc:
        raise DeploymentError("authorized api_env_file or snapshot changed") from exc
    if (
        stat.S_ISLNK(source_stat.st_mode)
        or not stat.S_ISREG(source_stat.st_mode)
        or source_stat.st_dev != fingerprint["source_dev"]
        or source_stat.st_ino != fingerprint["source_ino"]
        or source_stat.st_size != fingerprint["source_size"]
        or source_stat.st_mtime_ns != fingerprint["source_mtime_ns"]
        or source_stat.st_ctime_ns != fingerprint["source_ctime_ns"]
        or retained_source_stat.st_dev != fingerprint["source_dev"]
        or retained_source_stat.st_ino != fingerprint["source_ino"]
        or retained_source_stat.st_size != fingerprint["source_size"]
        or retained_source_stat.st_mtime_ns != fingerprint["source_mtime_ns"]
        or retained_source_stat.st_ctime_ns != fingerprint["source_ctime_ns"]
    ):
        raise DeploymentError("authorized api_env_file or snapshot changed")
    verify_frozen_env_snapshot(snapshot, fingerprint)


def remove_env_file_snapshot(
    snapshot: Path | None,
    fingerprint: dict[str, Any] | None,
    source_descriptor: int | None,
) -> None:
    try:
        if source_descriptor is not None:
            os.close(source_descriptor)
        if snapshot is not None and fingerprint is not None:
            snapshot_stat = os.lstat(snapshot)
            if (
                stat.S_ISREG(snapshot_stat.st_mode)
                and snapshot_stat.st_dev == fingerprint["snapshot_dev"]
                and snapshot_stat.st_ino == fingerprint["snapshot_ino"]
            ):
                snapshot.unlink()
                directory_fd = os.open(snapshot.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
    except FileNotFoundError:
        pass
    except OSError:
        # Do not replace the deployment/rollback outcome with a cleanup error.
        pass


def verify_database_schema(
    api_env_path: Path,
    schema_receipt: dict[str, Any],
    runner: Callable[..., subprocess.CompletedProcess[str]],
    *,
    on_env_file_read: Callable[[], None] | None = None,
    on_query_completed: Callable[[], None] | None = None,
) -> None:
    """Verify database and ledger identity through a bounded read-only query."""

    database_url = read_checkpoint_database_url(api_env_path, on_read=on_env_file_read)
    expected_identity = validate_database_identity(
        schema_receipt.get("database_identity")
    )
    expected_entries = schema_receipt["migration_set_entries"]
    database_env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        # libpq accepts a connection URI through PGDATABASE. Keeping it out of
        # argv and error text prevents credentials from entering receipts/logs.
        "PGDATABASE": database_url,
        "PGCONNECT_TIMEOUT": str(DATABASE_QUERY_TIMEOUT_SECONDS),
        "PGOPTIONS": (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={DATABASE_QUERY_TIMEOUT_SECONDS * 1000}"
        ),
    }
    query = """
SELECT json_build_object(
  'database_name', current_database(),
  'server_address', inet_server_addr()::text,
  'server_port', inet_server_port(),
  'transaction_read_only', current_setting('transaction_read_only'),
  'migrations', COALESCE((
    SELECT json_agg(
      json_build_object('filename', filename, 'checksum_sha256', checksum_sha256)
      ORDER BY filename
    )
    FROM public.schema_migrations
  ), '[]'::json)
)::text;
""".strip()
    result = runner(
        [
            "psql",
            "-X",
            "--no-password",
            "--tuples-only",
            "--no-align",
            "--quiet",
            "--command",
            query,
        ],
        env=database_env,
    )
    if on_query_completed is not None:
        on_query_completed()
    try:
        observed = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise DeploymentError("database identity query returned invalid JSON") from exc
    if not isinstance(observed, dict) or set(observed) != {
        "database_name",
        "server_address",
        "server_port",
        "transaction_read_only",
        "migrations",
    }:
        raise DeploymentError("database identity query returned an invalid shape")
    if observed["transaction_read_only"] != "on":
        raise DeploymentError("database identity query was not read-only")
    observed_identity = {
        key: observed[key] for key in ("database_name", "server_address", "server_port")
    }
    if observed_identity != expected_identity:
        raise DeploymentError("configured database identity does not match receipt")
    migrations = observed["migrations"]
    if not isinstance(migrations, list) or any(
        not isinstance(item, dict)
        or set(item) != {"filename", "checksum_sha256"}
        or not isinstance(item["filename"], str)
        or not isinstance(item["checksum_sha256"], str)
        for item in migrations
    ):
        raise DeploymentError("database migration ledger query returned invalid data")
    expected_ledger = sorted(
        (
            {
                "filename": entry["path"].removeprefix("sql/"),
                "checksum_sha256": entry["sha256"],
            }
            for entry in expected_entries
        ),
        key=lambda item: item["filename"],
    )
    if migrations != expected_ledger:
        raise DeploymentError("configured database migration ledger has drifted")


def validate_release_inputs(
    *,
    mode: str,
    candidate_path: Path,
    candidate_checksum: Path,
    current_schema_path: Path,
    database_source_authority: str,
    rollback_path: Path | None,
    rollback_checksum: Path | None,
    prior_receipt_path: Path | None,
) -> dict[str, Any]:
    manifest_tool = load_manifest_tool()
    candidate_sum = verify_checksum(candidate_path, candidate_checksum)
    candidate = load_json(candidate_path, "candidate manifest")
    schema_receipt = load_json(current_schema_path, "schema identity receipt")
    if (
        set(schema_receipt)
        != {
            "schema_version",
            "database_source_authority",
            "database_identity",
            "migration_set_identity",
            "migration_set_entries",
            "captured_at",
        }
        or schema_receipt.get("schema_version") != SCHEMA_RECEIPT_SCHEMA
    ):
        raise DeploymentError("unsupported schema identity receipt")
    if schema_receipt.get("database_source_authority") != database_source_authority:
        raise DeploymentError("schema receipt does not match database source authority")
    captured_at = schema_receipt.get("captured_at")
    try:
        if not isinstance(captured_at, str):
            raise ValueError
        captured = datetime.strptime(captured_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise DeploymentError("schema identity receipt timestamp is invalid")
    now = datetime.now(timezone.utc)
    if captured > now + SCHEMA_RECEIPT_FUTURE_TOLERANCE:
        raise DeploymentError("schema identity receipt timestamp is in the future")
    if now - captured > SCHEMA_RECEIPT_MAX_AGE:
        raise DeploymentError("schema identity receipt is stale")
    current_schema = schema_receipt.get("migration_set_identity")
    if not isinstance(current_schema, str) or not SHA256.fullmatch(current_schema):
        raise DeploymentError("schema identity receipt has no valid migration identity")
    migration_entries = schema_receipt.get("migration_set_entries")
    if not isinstance(migration_entries, list) or not migration_entries:
        raise DeploymentError("schema identity receipt has no migration entries")
    canonical_entries: list[dict[str, str]] = []
    for index, entry in enumerate(migration_entries):
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "sha256"}:
            raise DeploymentError(
                f"schema migration entry {index} has an invalid shape"
            )
        if not isinstance(entry["path"], str) or not re.fullmatch(
            r"sql/[0-9]{3}_[a-z0-9_]+\.sql", entry["path"]
        ):
            raise DeploymentError(f"schema migration entry {index} has an invalid path")
        if (
            entry["mode"] not in {"auto", "manual"}
            or not isinstance(entry["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        ):
            raise DeploymentError(f"schema migration entry {index} is invalid")
        canonical_entries.append(entry)
    if len({entry["path"] for entry in canonical_entries}) != len(canonical_entries):
        raise DeploymentError("schema identity receipt repeats a migration path")
    calculated_schema = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                canonical_entries, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
    )
    if calculated_schema != current_schema:
        raise DeploymentError(
            "schema identity receipt migration identity is inconsistent"
        )
    validate_database_identity(schema_receipt.get("database_identity"))
    try:
        manifest_tool.validate_manifest(
            candidate, purpose="deploy", current_migration_set=current_schema
        )
    except manifest_tool.ManifestError as exc:
        raise DeploymentError(f"candidate manifest rejected: {exc}") from exc
    if candidate.get("rollback", {}).get("application_only_eligible") is not True:
        raise DeploymentError(
            "candidate must be eligible as the receipt-backed next rollback release"
        )

    if mode == "bootstrap":
        if any(
            value is not None
            for value in (rollback_path, rollback_checksum, prior_receipt_path)
        ):
            raise DeploymentError("bootstrap must not claim a prior release or receipt")
        rollback_identity: dict[str, Any] = {"kind": "predeploy_absence"}
    else:
        if (
            rollback_path is None
            or rollback_checksum is None
            or prior_receipt_path is None
        ):
            raise DeploymentError(
                "upgrade requires a prior manifest, checksum and durable receipt"
            )
        rollback_sum = verify_checksum(rollback_path, rollback_checksum)
        rollback = load_json(rollback_path, "rollback manifest")
        prior = load_json(prior_receipt_path, "prior deployment receipt")
        prior_target = prior.get("target")
        prior_smoke = prior.get("smoke")
        if (
            prior.get("schema_version") != RECEIPT_SCHEMA
            or prior.get("mode") not in {"bootstrap", "upgrade"}
            or not isinstance(prior_target, dict)
            or prior_target.get("production") is not False
            or prior_target.get("provider") != "contabo"
            or prior_target.get("classification") != "live-checkpoint"
            or prior_target.get("hostname") != TARGET_HOSTNAME
            or prior.get("compose_project") != PROJECT
            or prior.get("migration_set_identity") != current_schema
            or prior.get("changed_resources")
            != [CONTAINERS[service] for service in SERVICES]
            or not isinstance(prior_smoke, dict)
            or set(prior_smoke)
            != {"/", "/api/health", "/openapi.json", "/api/v1/auth/session"}
            or any(
                not isinstance(outcome, dict)
                or not 200 <= outcome.get("status", 0) < 300
                for outcome in prior_smoke.values()
            )
            or prior.get("database_mutation_performed") is not False
            or prior.get("infrastructure_changes_performed") is not False
        ):
            raise DeploymentError("prior deployment receipt target/schema is invalid")
        try:
            manifest_tool.validate_manifest(
                rollback, purpose="rollback", current_migration_set=current_schema
            )
        except manifest_tool.ManifestError as exc:
            raise DeploymentError(f"rollback manifest rejected: {exc}") from exc
        if candidate.get("git_sha") == rollback.get("git_sha"):
            raise DeploymentError("candidate cannot be its own rollback")
        expected_prior = {
            "status": "accepted",
            "source_sha": rollback.get("git_sha"),
            "images": rollback.get("images"),
            "manifest_sha256": rollback_sum,
        }
        prior_run_id = prior.get("release_run_id")
        if not isinstance(prior_run_id, str) or not RUN_ID.fullmatch(prior_run_id):
            raise DeploymentError("prior receipt release run ID is invalid")
        expected_prior["release_run_id"] = prior_run_id
        if any(prior.get(key) != value for key, value in expected_prior.items()):
            raise DeploymentError(
                "prior receipt does not authenticate the rollback release"
            )
        rollback_identity = {
            "kind": "accepted_release",
            "source_sha": rollback["git_sha"],
            "images": rollback["images"],
            "manifest_sha256": rollback_sum,
        }
        rollback_identity["release_run_id"] = prior_run_id
    return {
        "candidate": candidate,
        "candidate_sha256": candidate_sum,
        "current_schema": current_schema,
        "schema_receipt": schema_receipt,
        "rollback": rollback_identity,
    }


def compose_environment(
    authority: dict[str, Any],
    release: dict[str, Any],
    *,
    verified_api_env_file: Path | None = None,
) -> dict[str, str]:
    external = authority["external_authority"]
    match = LOOPBACK_ORIGIN.fullmatch(external["origin_bind"])
    assert match is not None
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "DOCKER_CONFIG": external["docker_config_directory"],
        "DOCKER_CONTEXT": external["docker_context"],
        "COMPOSE_PROJECT_NAME": PROJECT,
        "V3_CHECKPOINT_API_IMAGE": release["images"]["backend"],
        "V3_CHECKPOINT_WEB_IMAGE": release["images"]["web"],
        "V3_CHECKPOINT_SOURCE_SHA": release["git_sha"],
        "V3_CHECKPOINT_API_ENV_FILE": str(
            verified_api_env_file or external["api_env_file"]
        ),
        "V3_CHECKPOINT_ORIGIN_BIND": f"127.0.0.1:{match.group(1)}",
    }


def command_plan(compose_path: Path, env: dict[str, str]) -> list[list[str]]:
    base = ["docker", "compose", "--project-name", PROJECT, "--file", str(compose_path)]
    return [
        ["docker", "pull", env["V3_CHECKPOINT_API_IMAGE"]],
        ["docker", "pull", env["V3_CHECKPOINT_WEB_IMAGE"]],
        [
            *base,
            "up",
            "--detach",
            "--no-deps",
            "--force-recreate",
            "--pull",
            "never",
            *SERVICES,
        ],
    ]


def rollback_plan(
    compose_path: Path,
    mode: str,
    env: dict[str, str],
    rollback: dict[str, Any],
) -> tuple[list[list[str]], dict[str, str]]:
    base = ["docker", "compose", "--project-name", PROJECT, "--file", str(compose_path)]
    if mode == "bootstrap":
        return [
            [*base, "stop", *SERVICES],
            [*base, "rm", "--force", "--stop", *SERVICES],
        ], env
    prior_env = {
        **env,
        "V3_CHECKPOINT_API_IMAGE": rollback["images"]["backend"],
        "V3_CHECKPOINT_WEB_IMAGE": rollback["images"]["web"],
        "V3_CHECKPOINT_SOURCE_SHA": rollback["source_sha"],
    }
    return [
        [
            *base,
            "up",
            "--detach",
            "--no-deps",
            "--force-recreate",
            "--pull",
            "never",
            *SERVICES,
        ]
    ], prior_env


def run_command(
    argv: list[str], *, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError(f"command unavailable or timed out: {argv[0]}") from exc
    if result.returncode != 0:
        raise DeploymentError(f"bounded command failed: {argv[0]} {argv[1]}")
    return result


def validate_host_files(authority: dict[str, Any], compose_path: Path) -> None:
    target = authority["target"]
    if socket.gethostname().split(".")[0] != target["hostname"]:
        raise DeploymentError("host short identity does not match authority")
    if socket.getfqdn() != target["fqdn"]:
        raise DeploymentError("host FQDN does not match authority")
    if os.uname().machine != target["architecture"]:
        raise DeploymentError("host architecture does not match release platform")
    observed_capacity = authority.get("observed_capacity")
    if not isinstance(observed_capacity, dict):
        raise DeploymentError("audited host capacity is missing")
    if (os.cpu_count() or 0) < observed_capacity.get("logical_cpus", 0):
        raise DeploymentError(
            "host CPU capacity is below the audited checkpoint baseline"
        )
    try:
        memory_facts = {
            line.split(":", 1)[0]: int(line.split()[1])
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
            if line.startswith(("MemTotal:", "MemAvailable:"))
        }
        memory_total = memory_facts["MemTotal"]
        memory_available = memory_facts["MemAvailable"]
    except (OSError, KeyError, ValueError) as exc:
        raise DeploymentError("unable to verify host memory capacity") from exc
    if memory_total < observed_capacity.get("memory_total_kib", 0):
        raise DeploymentError("host memory is below the audited checkpoint baseline")
    app_memory_limit_kib = (1536 + 512) * 1024
    if memory_available < app_memory_limit_kib:
        raise DeploymentError("host cannot currently satisfy checkpoint memory limits")
    external = authority["external_authority"]
    api_env = Path(external["api_env_file"])
    if not api_env.is_absolute() or not api_env.is_file() or api_env.is_symlink():
        raise DeploymentError("authorized api_env_file is missing or unsafe")
    api_stat = api_env.stat()
    if (
        api_stat.st_uid != external["api_env_owner_uid"]
        or stat.filemode(api_stat.st_mode)[-9:]
        != stat.filemode(int(external["api_env_mode"], 8))[-9:]
    ):
        raise DeploymentError("authorized api_env_file ownership/mode mismatch")
    schema_path = Path(external["schema_identity_receipt"])
    if (
        not schema_path.is_absolute()
        or not schema_path.is_file()
        or schema_path.is_symlink()
    ):
        raise DeploymentError("authorized schema_identity_receipt is missing or unsafe")
    if sha256_file(schema_path) != external["schema_identity_receipt_sha256"]:
        raise DeploymentError("schema identity receipt checksum mismatch")
    receipt_dir = Path(external["receipt_directory"])
    if (
        not receipt_dir.is_absolute()
        or not receipt_dir.is_dir()
        or receipt_dir.is_symlink()
    ):
        raise DeploymentError("durable receipt directory is missing")
    receipt_stat = receipt_dir.stat()
    if (
        receipt_stat.st_uid != external["receipt_owner_uid"]
        or stat.filemode(receipt_stat.st_mode)[-9:]
        != stat.filemode(int(external["receipt_mode"], 8))[-9:]
    ):
        raise DeploymentError("durable receipt directory ownership/mode mismatch")
    docker_config = Path(external["docker_config_directory"])
    if (
        not docker_config.is_absolute()
        or not docker_config.is_dir()
        or docker_config.is_symlink()
    ):
        raise DeploymentError("authorized Docker config directory is missing or unsafe")
    docker_stat = docker_config.stat()
    if (
        docker_stat.st_uid != external["docker_config_owner_uid"]
        or stat.filemode(docker_stat.st_mode)[-9:]
        != stat.filemode(int(external["docker_config_mode"], 8))[-9:]
    ):
        raise DeploymentError("authorized Docker config ownership/mode mismatch")
    if not compose_path.is_file():
        raise DeploymentError("reviewed Compose file is missing")
    if sha256_file(compose_path) != authority["application_contract"].get(
        "compose_sha256"
    ):
        raise DeploymentError("reviewed Compose checksum does not match authority")


def validate_network_topology(
    mode: str,
    inspection_output: str,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    try:
        documents = json.loads(inspection_output)
    except json.JSONDecodeError as exc:
        raise DeploymentError("checkpoint network inspection is invalid") from exc
    if not isinstance(documents, list) or len(documents) != 1:
        raise DeploymentError("checkpoint network inspection is invalid")
    network = documents[0]
    network_id = network.get("Id") if isinstance(network, dict) else None
    if (
        not isinstance(network, dict)
        or not isinstance(network_id, str)
        or not re.fullmatch(r"[0-9a-f]{64}", network_id)
        or network.get("Name") != APP_NETWORK
        or network.get("Driver") != "bridge"
        or network.get("Scope") != "local"
        or network.get("Ingress") is not False
        or not isinstance(network.get("Containers"), dict)
    ):
        raise DeploymentError("checkpoint network topology is unauthorized")
    endpoints = network["Containers"]
    attached: dict[str, tuple[str, str]] = {}
    for container_id, endpoint in endpoints.items():
        endpoint_id = endpoint.get("EndpointID") if isinstance(endpoint, dict) else None
        if (
            not isinstance(container_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", container_id)
            or not isinstance(endpoint, dict)
            or not isinstance(endpoint.get("Name"), str)
            or not isinstance(endpoint_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", endpoint_id)
        ):
            raise DeploymentError("checkpoint network inspection is unverifiable")
        name = endpoint["Name"]
        if name not in CONTAINERS.values() or name in attached:
            raise DeploymentError("checkpoint network has an unexpected peer")
        attached[name] = (container_id, endpoint_id)
    if mode == "bootstrap":
        attachments_valid = not attached
    elif mode == "bootstrap-rollback":
        attachments_valid = set(attached).issubset(CONTAINERS.values())
    elif mode == "upgrade":
        attachments_valid = set(attached) == set(CONTAINERS.values())
    else:
        raise DeploymentError("checkpoint network deploy mode is invalid")
    if not attachments_valid:
        raise DeploymentError("checkpoint network attachments do not match deploy mode")
    for service, container in CONTAINERS.items():
        if container not in attached:
            continue
        attachment = runner(
            [
                "docker",
                "container",
                "inspect",
                container,
            ],
            env=env,
        )
        try:
            container_documents = json.loads(attachment.stdout)
        except json.JSONDecodeError as exc:
            raise DeploymentError("container network attachment is invalid") from exc
        if not isinstance(container_documents, list) or len(container_documents) != 1:
            raise DeploymentError("container network attachment is invalid")
        container_document = container_documents[0]
        networks = (
            container_document.get("NetworkSettings", {}).get("Networks")
            if isinstance(container_document, dict)
            else None
        )
        if not isinstance(networks, dict) or set(networks) != {APP_NETWORK}:
            raise DeploymentError("container network attachment is unauthorized")
        network_attachment = networks[APP_NETWORK]
        aliases = (
            network_attachment.get("Aliases")
            if isinstance(network_attachment, dict)
            else None
        )
        expected_container_id, expected_endpoint_id = attached[container]
        if (
            container_document.get("Id") != expected_container_id
            or not isinstance(network_attachment, dict)
            or network_attachment.get("NetworkID") != network_id
            or network_attachment.get("EndpointID") != expected_endpoint_id
            or not isinstance(aliases, list)
            or any(not isinstance(alias, str) for alias in aliases)
            or set(aliases) != NETWORK_ALIASES[service]
            or len(aliases) != len(NETWORK_ALIASES[service])
        ):
            raise DeploymentError("checkpoint container network aliases are invalid")


def inspect_network_topology(
    mode: str,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    inspection = runner(["docker", "network", "inspect", APP_NETWORK], env=env)
    validate_network_topology(mode, inspection.stdout, env, runner)


def validate_host_runtime(
    compose_path: Path,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
    *,
    mode: str = "bootstrap",
) -> None:
    runner(["psql", "--version"], env=env)
    context_endpoint = runner(
        [
            "docker",
            "context",
            "inspect",
            env["DOCKER_CONTEXT"],
            "--format",
            "{{json .Endpoints.docker.Host}}",
        ],
        env=env,
    )
    try:
        endpoint = json.loads(context_endpoint.stdout)
    except json.JSONDecodeError as exc:
        raise DeploymentError("Docker context endpoint inspection is invalid") from exc
    if endpoint != LOCAL_DOCKER_ENDPOINT:
        raise DeploymentError(
            "Docker context is not bound to the authorized local daemon"
        )
    runner(["docker", "compose", "version"], env=env)
    compose_base = [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "--file",
        str(compose_path),
        "config",
    ]
    rendered_services = runner([*compose_base, "--services"], env=env)
    if set(rendered_services.stdout.split()) != set(SERVICES):
        raise DeploymentError("rendered Compose service allowlist is invalid")
    rendered_volumes = runner([*compose_base, "--volumes"], env=env)
    if rendered_volumes.stdout.strip():
        raise DeploymentError("rendered Compose unexpectedly manages volumes")
    rendered_images = runner([*compose_base, "--images"], env=env)
    expected_images = {
        env["V3_CHECKPOINT_API_IMAGE"],
        env["V3_CHECKPOINT_WEB_IMAGE"],
    }
    if set(rendered_images.stdout.split()) != expected_images:
        raise DeploymentError("rendered Compose images are not exact release digests")
    inspect_network_topology(mode, env, runner)
    active_runners = runner(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--state=active",
            "--plain",
            "--no-legend",
            "actions.runner.*.service",
        ],
        env=env,
    )
    active_runner_names = {
        line.split()[0]
        for line in active_runners.stdout.splitlines()
        if line.strip().startswith("actions.runner.")
    }
    if active_runner_names != RUNNER_SERVICES:
        raise DeploymentError("active runner topology differs from exact authority")
    for service in sorted(RUNNER_SERVICES):
        runner(["systemctl", "is-active", "--quiet", service], env=env)
    project_containers = runner(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format",
            "{{.Names}}",
        ],
        env=env,
    )
    names = {
        line.strip() for line in project_containers.stdout.splitlines() if line.strip()
    }
    if not names.issubset(set(CONTAINERS.values())):
        raise DeploymentError("target project contains a non-allowlisted resource")
    project_volumes = runner(
        [
            "docker",
            "volume",
            "ls",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format",
            "{{.Name}}",
        ],
        env=env,
    )
    if project_volumes.stdout.strip():
        raise DeploymentError("target project contains a managed volume")


def verify_pulled_image(
    image: str,
    source_sha: str,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    result = runner(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            '{{json .RepoDigests}}|{{index .Config.Labels "org.opencontainers.image.revision"}}',
        ],
        env=env,
    )
    repo_digests, separator, revision = result.stdout.strip().partition("|")
    try:
        digests = json.loads(repo_digests)
    except json.JSONDecodeError as exc:
        raise DeploymentError("pulled image digest inspection is invalid") from exc
    if not separator or image not in digests or revision != source_sha:
        raise DeploymentError("pulled image digest/build identity mismatch")


def inspect_container(container: str, env: dict[str, str]) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["docker", "container", "inspect", container],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError("unable to inspect allowlisted app container") from exc
    if result.returncode != 0:
        return None
    try:
        documents = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DeploymentError("container inspection returned invalid JSON") from exc
    if not isinstance(documents, list) or len(documents) != 1:
        raise DeploymentError("container inspection returned an invalid result")
    return documents[0]


def verify_origin_state(origin: str, mode: str) -> None:
    match = LOOPBACK_ORIGIN.fullmatch(origin)
    if match is None:
        raise DeploymentError("origin authority is invalid")
    port = int(match.group(1))
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(1)
    try:
        if mode == "bootstrap":
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise DeploymentError(
                    "bootstrap origin listener is already occupied"
                ) from exc
        elif probe.connect_ex(("127.0.0.1", port)) != 0:
            raise DeploymentError("upgrade origin listener is not reachable")
    finally:
        probe.close()


def verify_app_containers(
    env: dict[str, str], source_sha: str, expected_images: dict[str, str]
) -> None:
    for service, container in CONTAINERS.items():
        document = inspect_container(container, env)
        role = "backend" if service == "api" else "web"
        if (
            document is None
            or document.get("Config", {}).get("Image") != expected_images[role]
        ):
            raise DeploymentError("running app container image identity mismatch")
        if (
            document.get("Config", {})
            .get("Labels", {})
            .get("org.opencontainers.image.revision")
            != source_sha
        ):
            raise DeploymentError("running app container build identity mismatch")
        labels = document.get("Config", {}).get("Labels", {})
        if (
            labels.get("com.docker.compose.project") != PROJECT
            or labels.get("com.docker.compose.service") != service
        ):
            raise DeploymentError("running app container Compose identity mismatch")
        if document.get("State", {}).get("Running") is not True:
            raise DeploymentError("allowlisted app container is not running")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def get_origin(
    origin: str,
    path: str,
    *,
    timeout_seconds: float = ORIGIN_REQUEST_TIMEOUT_SECONDS,
) -> tuple[int, bytes, str]:
    if timeout_seconds <= 0:
        raise DeploymentError("origin request timeout must be positive")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    request = urllib.request.Request(
        origin + path, headers={"Accept": "application/json,text/html"}
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_SMOKE_BYTES + 1)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except (OSError, urllib.error.URLError) as exc:
        raise DeploymentError(f"origin smoke failed for {path}") from exc
    if not 200 <= status < 300 or len(body) > MAX_SMOKE_BYTES:
        raise DeploymentError(f"origin smoke rejected for {path}")
    return status, body, content_type


def _validate_health_body(body: bytes, source_sha: str) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DeploymentError("origin health JSON is invalid") from exc
    if not isinstance(payload, dict) or not (
        payload.get("status") == "ok"
        and payload.get("database") == "connected"
        and payload.get("build_sha") == source_sha
    ):
        raise DeploymentError("health smoke build/database identity mismatch")


def wait_for_origin_ready(
    origin: str,
    source_sha: str,
    *,
    timeout_seconds: float = READINESS_TIMEOUT_SECONDS,
    interval_seconds: float = READINESS_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Poll the release health endpoint before the authoritative smoke suite."""

    if timeout_seconds <= 0 or interval_seconds <= 0:
        raise DeploymentError("readiness timeout and interval must be positive")
    deadline = clock() + timeout_seconds
    attempts = 0
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            raise DeploymentError("origin readiness timed out")
        attempts += 1
        try:
            _status, body, _content_type = get_origin(
                origin,
                "/api/health",
                timeout_seconds=min(ORIGIN_REQUEST_TIMEOUT_SECONDS, remaining),
            )
            _validate_health_body(body, source_sha)
            return attempts
        except DeploymentError as exc:
            remaining = deadline - clock()
            if remaining <= 0:
                raise DeploymentError("origin readiness timed out") from exc
            sleeper(min(interval_seconds, remaining))


def smoke_origin(origin: str, source_sha: str) -> dict[str, Any]:
    outcomes: dict[str, Any] = {}
    for path in ("/", "/api/health", "/openapi.json", "/api/v1/auth/session"):
        status, body, content_type = get_origin(origin, path)
        outcomes[path] = {"status": status, "bytes": len(body)}
        if path == "/":
            if "text/html" not in content_type.lower() or b"<html" not in body.lower():
                raise DeploymentError("root smoke is not the Svelte HTML application")
            continue
        if path == "/api/health":
            _validate_health_body(body, source_sha)
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DeploymentError(f"origin smoke JSON is invalid for {path}") from exc
        if not isinstance(payload, dict):
            raise DeploymentError(f"origin smoke payload is invalid for {path}")
        if path == "/openapi.json" and not (
            isinstance(payload.get("paths"), dict)
            and "/api/health" in payload["paths"]
            and "/api/v1/auth/session" in payload["paths"]
        ):
            raise DeploymentError("OpenAPI smoke lacks required route identity")
        if (
            path == "/api/v1/auth/session"
            and payload.get("authenticated") is not False
        ):
            raise DeploymentError("anonymous session smoke is not anonymous")
    return outcomes


def persist_receipt(
    directory: Path, receipt: dict[str, Any], accepted_manifest_path: Path
) -> Path:
    data = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    try:
        if accepted_manifest_path.stat().st_size > MAX_JSON_BYTES:
            raise OSError("accepted manifest exceeds the size limit")
        manifest_data = accepted_manifest_path.read_bytes()
    except OSError:
        raise
    manifest_digest = hashlib.sha256(manifest_data).hexdigest()
    if manifest_digest != receipt["manifest_sha256"]:
        raise OSError("accepted manifest changed before durable persistence")
    identity = (
        f"{receipt['source_sha']}-{receipt['release_run_id']}-"
        f"{receipt['manifest_sha256']}"
    )
    final = directory / f"{identity}.json"
    checksum = directory / f"{identity}.json.sha256"
    manifest = directory / f"{identity}.release.json"
    manifest_checksum = directory / f"{identity}.release.json.sha256"
    if any(path.exists() for path in (final, checksum, manifest, manifest_checksum)):
        raise OSError("immutable deployment receipt identity already exists")
    digest = hashlib.sha256(data).hexdigest()
    checksum_data = f"{digest}  {final.name}\n".encode()
    manifest_checksum_data = f"{manifest_digest}  {manifest.name}\n".encode()
    pointer_data = (
        json.dumps(
            {
                "schema_version": CURRENT_RECEIPT_SCHEMA,
                "receipt_file": final.name,
                "receipt_sha256": digest,
                "manifest_file": manifest.name,
                "manifest_sha256": manifest_digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    current = directory / "current.json"
    if current.is_symlink():
        raise OSError("current deployment receipt pointer is unsafe")
    previous_current = current.read_bytes() if current.exists() else None
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    temporaries: list[Path] = []
    final_created = False
    checksum_created = False
    manifest_created = False
    manifest_checksum_created = False
    current_replaced = False

    def staged(data_to_write: bytes, prefix: str) -> Path:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=prefix, delete=False
        ) as handle:
            path = Path(handle.name)
            temporaries.append(path)
            handle.write(data_to_write)
            handle.flush()
            os.fsync(handle.fileno())
        return path

    try:
        receipt_temporary = staged(data, ".v3-receipt-")
        checksum_temporary = staged(checksum_data, ".v3-checksum-")
        manifest_temporary = staged(manifest_data, ".v3-manifest-")
        manifest_checksum_temporary = staged(
            manifest_checksum_data, ".v3-manifest-checksum-"
        )
        current_temporary = staged(pointer_data, ".v3-current-")
        os.replace(receipt_temporary, final)
        temporaries.remove(receipt_temporary)
        final_created = True
        os.replace(checksum_temporary, checksum)
        temporaries.remove(checksum_temporary)
        checksum_created = True
        os.replace(manifest_temporary, manifest)
        temporaries.remove(manifest_temporary)
        manifest_created = True
        os.replace(manifest_checksum_temporary, manifest_checksum)
        temporaries.remove(manifest_checksum_temporary)
        manifest_checksum_created = True
        os.fsync(directory_fd)
        os.replace(current_temporary, current)
        temporaries.remove(current_temporary)
        current_replaced = True
        os.fsync(directory_fd)
        return final
    except OSError:
        # current.json is the acceptance commit point. Restore its previous
        # state and remove incomplete immutable artifacts before app rollback.
        if current_replaced:
            if previous_current is None:
                current.unlink(missing_ok=True)
            else:
                restore_temporary = staged(previous_current, ".v3-current-restore-")
                os.replace(restore_temporary, current)
                temporaries.remove(restore_temporary)
        if checksum_created:
            checksum.unlink(missing_ok=True)
        if final_created:
            final.unlink(missing_ok=True)
        if manifest_checksum_created:
            manifest_checksum.unlink(missing_ok=True)
        if manifest_created:
            manifest.unlink(missing_ok=True)
        os.fsync(directory_fd)
        raise
    finally:
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
        os.close(directory_fd)


def persist_failure_receipt(directory: Path, receipt: dict[str, Any]) -> Path:
    data = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    identity = (
        f"failed-{receipt['source_sha']}-{receipt['release_run_id']}-"
        f"{receipt['manifest_sha256']}-{attempt}"
    )
    final = directory / f"{identity}.json"
    if final.exists():
        raise OSError("immutable failure receipt identity already exists")
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".v3-failure-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, final)
        temporary = None
        os.fsync(directory_fd)
        return final
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        os.close(directory_fd)


def load_current_release(directory: Path) -> tuple[Path, Path, Path]:
    current_path = directory / "current.json"
    if current_path.is_symlink():
        raise DeploymentError("current deployment receipt pointer is unsafe")
    pointer = load_json(current_path, "current deployment receipt pointer")
    if set(pointer) != {
        "schema_version",
        "receipt_file",
        "receipt_sha256",
        "manifest_file",
        "manifest_sha256",
    }:
        raise DeploymentError("current deployment receipt pointer shape is invalid")
    if pointer.get("schema_version") != CURRENT_RECEIPT_SCHEMA:
        raise DeploymentError("current deployment receipt pointer schema is invalid")
    receipt_file = pointer.get("receipt_file")
    receipt_sha = pointer.get("receipt_sha256")
    manifest_file = pointer.get("manifest_file")
    manifest_sha = pointer.get("manifest_sha256")
    if not isinstance(receipt_file, str) or not re.fullmatch(
        r"[0-9a-f]{40}-[1-9][0-9]{0,19}-[0-9a-f]{64}\.json", receipt_file
    ):
        raise DeploymentError("current deployment receipt filename is invalid")
    if not isinstance(receipt_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", receipt_sha
    ):
        raise DeploymentError("current deployment receipt checksum is invalid")
    expected_manifest_file = receipt_file.removesuffix(".json") + ".release.json"
    if manifest_file != expected_manifest_file:
        raise DeploymentError("current accepted manifest filename is invalid")
    if not isinstance(manifest_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", manifest_sha
    ):
        raise DeploymentError("current accepted manifest checksum is invalid")
    receipt_path = directory / receipt_file
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise DeploymentError("current deployment receipt is missing or unsafe")
    receipt_checksum_path = Path(f"{receipt_path}.sha256")
    if receipt_checksum_path.is_symlink():
        raise DeploymentError("current deployment receipt sidecar is unsafe")
    if sha256_file(receipt_path) != receipt_sha:
        raise DeploymentError("current deployment receipt checksum mismatch")
    if verify_checksum(receipt_path, receipt_checksum_path) != receipt_sha:
        raise DeploymentError("current deployment receipt sidecar mismatch")
    manifest_path = directory / manifest_file
    manifest_checksum_path = Path(f"{manifest_path}.sha256")
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise DeploymentError("current accepted manifest is missing or unsafe")
    if manifest_checksum_path.is_symlink():
        raise DeploymentError("current accepted manifest sidecar is unsafe")
    if sha256_file(manifest_path) != manifest_sha:
        raise DeploymentError("current accepted manifest checksum mismatch")
    if verify_checksum(manifest_path, manifest_checksum_path) != manifest_sha:
        raise DeploymentError("current accepted manifest sidecar mismatch")
    prior = load_json(receipt_path, "current deployment receipt")
    if prior.get("manifest_sha256") != manifest_sha:
        raise DeploymentError("current receipt does not bind accepted manifest")
    return receipt_path, manifest_path, manifest_checksum_path


def path_exists_lexically(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DeploymentError("unable to inspect durable prior-state path") from exc
    return True


def load_current_receipt(directory: Path) -> Path:
    receipt_path, _manifest_path, _manifest_checksum_path = load_current_release(
        directory
    )
    return receipt_path


def acquire_deployment_lock(directory: Path) -> Any:
    try:
        handle = (directory / "deploy.lock").open("a+", encoding="utf-8")
        os.fchmod(handle.fileno(), 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as exc:
        try:
            handle.close()
        except UnboundLocalError:
            pass
        raise DeploymentError("live-checkpoint deployment lock is unavailable") from exc
    return handle


def release_deployment_lock(handle: Any) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def verify_bootstrap_absence(
    env: dict[str, str],
    origin: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    for container in CONTAINERS.values():
        listed = runner(
            [
                "docker",
                "ps",
                "--all",
                "--filter",
                f"name=^/{container}$",
                "--format",
                "{{.Names}}",
            ],
            env=env,
        )
        if listed.stdout.strip():
            raise DeploymentError("bootstrap requires proven predeploy app absence")
    verify_origin_state(origin, "bootstrap")


def operation_receipt(
    *,
    authority: dict[str, Any],
    args: argparse.Namespace,
    release_info: dict[str, Any],
    status: str,
    changed_resources: list[str],
    smokes: dict[str, Any],
    rollback: dict[str, Any],
    database_access_performed: bool,
    env_files_read: bool,
    env_file_consumed_by_compose: bool,
) -> dict[str, Any]:
    candidate = release_info["candidate"]
    return {
        "schema_version": RECEIPT_SCHEMA,
        "status": status,
        "mode": args.mode,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_sha": candidate["git_sha"],
        "release_run_id": args.candidate_run_id,
        "images": candidate["images"],
        "manifest_sha256": release_info["candidate_sha256"],
        "migration_set_identity": release_info["current_schema"],
        "target": {
            "provider": "contabo",
            "classification": "live-checkpoint",
            "production": False,
            "hostname": authority["target"]["hostname"],
        },
        "compose_project": PROJECT,
        "changed_resources": changed_resources,
        "smoke": smokes,
        "rollback": rollback,
        "database_access_performed": database_access_performed,
        "database_mutation_performed": False,
        "migrations_performed": False,
        "infrastructure_changes_performed": False,
        "service_changes_performed": status == "accepted",
        "image_pulls_performed": status == "accepted",
        "filesystem_writes_performed": True,
        "env_file_consumed_by_compose": env_file_consumed_by_compose,
        "env_files_read": env_files_read,
        "private_keys_read": False,
    }


def execute(
    args: argparse.Namespace,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    authority = load_json(args.authority, "target authority")
    blockers = validate_authority(authority)
    if blockers:
        raise DeploymentError("target authority stopped: " + ",".join(blockers))
    external = authority["external_authority"]
    if args.candidate_run_id is None or not RUN_ID.fullmatch(args.candidate_run_id):
        raise DeploymentError("candidate release run ID is required")
    receipt_directory = Path(external["receipt_directory"])
    validate_host_files(authority, args.compose)
    deployment_lock = acquire_deployment_lock(receipt_directory)
    release_info: dict[str, Any] | None = None
    image_pull_attempted = False
    pulled_images: list[str] = []
    service_mutation_attempted = False
    compose_recreate_attempted = False
    database_access_attempted = False
    database_access_performed = False
    env_file_read_attempted = False
    env_files_read = False
    env_file_consumed_by_compose = False
    verified_env_snapshot: Path | None = None
    verified_env_fingerprint: dict[str, Any] | None = None
    verified_env_source_descriptor: int | None = None
    smokes: dict[str, Any] = {}
    try:
        if args.mode == "upgrade":
            (
                prior_receipt_path,
                rollback_path,
                rollback_checksum,
            ) = load_current_release(receipt_directory)
        else:
            if path_exists_lexically(receipt_directory / "current.json"):
                raise DeploymentError("bootstrap requires proven prior receipt absence")
            prior_receipt_path = None
            rollback_path = None
            rollback_checksum = None
        release_info = validate_release_inputs(
            mode=args.mode,
            candidate_path=args.candidate,
            candidate_checksum=args.candidate_checksum,
            current_schema_path=Path(external["schema_identity_receipt"]),
            database_source_authority=external["database_source_authority"],
            rollback_path=rollback_path,
            rollback_checksum=rollback_checksum,
            prior_receipt_path=prior_receipt_path,
        )
        candidate = release_info["candidate"]

        def mark_env_file_read() -> None:
            nonlocal env_files_read
            env_files_read = True

        def mark_database_query_completed() -> None:
            nonlocal database_access_performed
            database_access_performed = True

        env_file_read_attempted = True
        (
            verified_env_snapshot,
            verified_env_fingerprint,
            verified_env_source_descriptor,
        ) = freeze_authorized_env_file(
            Path(external["api_env_file"]),
            receipt_directory,
            expected_uid=external["api_env_owner_uid"],
            expected_mode=external["api_env_mode"],
            on_read=mark_env_file_read,
        )
        database_access_attempted = True
        verify_database_schema(
            verified_env_snapshot,
            release_info["schema_receipt"],
            runner,
            on_query_completed=mark_database_query_completed,
        )
        verify_authorized_env_unchanged(
            Path(external["api_env_file"]),
            verified_env_snapshot,
            verified_env_fingerprint,
            verified_env_source_descriptor,
        )
        env = compose_environment(
            authority, candidate, verified_api_env_file=verified_env_snapshot
        )
        validate_host_runtime(args.compose, env, runner, mode=args.mode)
        if args.mode == "bootstrap":
            verify_bootstrap_absence(env, external["origin_bind"], runner)
        else:
            rollback = release_info["rollback"]
            verify_app_containers(env, rollback["source_sha"], rollback["images"])
            smoke_origin(external["origin_bind"], rollback["source_sha"])
            verify_origin_state(external["origin_bind"], "upgrade")

        verify_authorized_env_unchanged(
            Path(external["api_env_file"]),
            verified_env_snapshot,
            verified_env_fingerprint,
            verified_env_source_descriptor,
        )
        plan = command_plan(args.compose, env)
        for command in plan[:2]:
            image_pull_attempted = True
            runner(command, env=env)
            verify_pulled_image(command[-1], candidate["git_sha"], env, runner)
            pulled_images.append(command[-1])
        if args.mode == "upgrade":
            rollback = release_info["rollback"]
            for image in rollback["images"].values():
                image_pull_attempted = True
                runner(["docker", "pull", image], env=env)
                verify_pulled_image(image, rollback["source_sha"], env, runner)
                pulled_images.append(image)
        verify_authorized_env_unchanged(
            Path(external["api_env_file"]),
            verified_env_snapshot,
            verified_env_fingerprint,
            verified_env_source_descriptor,
        )
        inspect_network_topology(args.mode, env, runner)
        service_mutation_attempted = True
        compose_recreate_attempted = True
        runner(plan[2], env=env)
        env_file_consumed_by_compose = True
        wait_for_origin_ready(external["origin_bind"], candidate["git_sha"])
        verify_app_containers(env, candidate["git_sha"], candidate["images"])
        smokes = smoke_origin(external["origin_bind"], candidate["git_sha"])
        receipt = operation_receipt(
            authority=authority,
            args=args,
            release_info=release_info,
            status="accepted",
            changed_resources=[CONTAINERS[service] for service in SERVICES],
            smokes=smokes,
            rollback=release_info["rollback"],
            database_access_performed=database_access_performed,
            env_files_read=env_files_read,
            env_file_consumed_by_compose=env_file_consumed_by_compose,
        )
        persist_receipt(receipt_directory, receipt, args.candidate)
        return receipt
    except Exception as original:
        # A failure before release validation has no authenticated candidate
        # identity, but the lock file write still has to be reported truthfully.
        if release_info is None:
            failure_receipt = stopped_receipt(authority, [type(original).__name__])
            failure_receipt.update(
                filesystem_writes_performed=True,
                deployment_lock_acquired=True,
            )
            raise OperationFailed(failure_receipt) from original
        rollback_outcome: dict[str, Any] = {
            "identity": release_info["rollback"],
            "attempted": False,
            "status": "not-required",
        }
        if service_mutation_attempted:
            rollback_outcome.update(attempted=True, status="started")
            try:
                commands, rollback_env = rollback_plan(
                    args.compose, args.mode, env, release_info["rollback"]
                )
                inspect_network_topology(
                    "bootstrap-rollback" if args.mode == "bootstrap" else "upgrade",
                    rollback_env,
                    runner,
                )
                for command in commands:
                    verify_frozen_env_snapshot(
                        verified_env_snapshot, verified_env_fingerprint
                    )
                    if "up" in command:
                        compose_recreate_attempted = True
                    runner(command, env=rollback_env)
                    if "up" in command:
                        env_file_consumed_by_compose = True
                if args.mode == "bootstrap":
                    verify_bootstrap_absence(
                        rollback_env, external["origin_bind"], runner
                    )
                else:
                    rollback = release_info["rollback"]
                    wait_for_origin_ready(
                        external["origin_bind"], rollback["source_sha"]
                    )
                    verify_app_containers(
                        rollback_env, rollback["source_sha"], rollback["images"]
                    )
                    smoke_origin(external["origin_bind"], rollback["source_sha"])
                rollback_outcome["status"] = "verified"
            except Exception as rollback_error:
                rollback_outcome.update(
                    status="failed", failure=type(rollback_error).__name__
                )
        failure_receipt = operation_receipt(
            authority=authority,
            args=args,
            release_info=release_info,
            status="failed",
            changed_resources=(
                [CONTAINERS[service] for service in SERVICES]
                if service_mutation_attempted
                else []
            ),
            smokes=smokes,
            rollback=rollback_outcome,
            database_access_performed=database_access_performed,
            env_files_read=env_files_read,
            env_file_consumed_by_compose=env_file_consumed_by_compose,
        )
        failure_receipt.update(
            failure=type(original).__name__,
            image_pull_attempted=image_pull_attempted,
            image_pulls_performed=(
                True if pulled_images else None if image_pull_attempted else False
            ),
            image_pulls_may_have_been_performed=image_pull_attempted,
            pulled_images_verified=pulled_images,
            service_mutation_attempted=service_mutation_attempted,
            service_changes_performed=service_mutation_attempted,
            database_access_attempted=database_access_attempted,
            database_access_may_have_been_performed=(
                database_access_attempted and not database_access_performed
            ),
            env_file_read_attempted=env_file_read_attempted,
            env_files_may_have_been_read=(
                env_file_read_attempted and not env_files_read
            ),
            env_file_consumed_by_compose=env_file_consumed_by_compose,
            env_file_may_have_been_consumed_by_compose=(
                compose_recreate_attempted and not env_file_consumed_by_compose
            ),
        )
        try:
            failure_path = persist_failure_receipt(receipt_directory, failure_receipt)
            failure_receipt["durable_failure_receipt"] = failure_path.name
        except OSError:
            failure_receipt["durable_failure_receipt"] = None
            failure_receipt["receipt_persistence"] = "failed"
        raise OperationFailed(failure_receipt) from original
    finally:
        remove_env_file_snapshot(
            verified_env_snapshot,
            verified_env_fingerprint,
            verified_env_source_descriptor,
        )
        release_deployment_lock(deployment_lock)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    result.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    result.add_argument("--mode", choices=("bootstrap", "upgrade"), default="bootstrap")
    result.add_argument("--candidate", type=Path)
    result.add_argument("--candidate-checksum", type=Path)
    result.add_argument("--candidate-run-id")
    result.add_argument("--authority-gate", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    authority: dict[str, Any] = {}
    try:
        authority = load_json(args.authority, "target authority")
        blockers = validate_authority(authority)
        if blockers:
            print(json.dumps(stopped_receipt(authority, blockers), sort_keys=True))
            return 78
        if args.authority_gate:
            print(
                json.dumps(
                    {
                        "schema_version": RECEIPT_SCHEMA,
                        "status": "authority-verified",
                        "target": authority["target"],
                        "service_changes_performed": False,
                        "filesystem_writes_performed": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.candidate is None or args.candidate_checksum is None:
            raise DeploymentError("candidate manifest and checksum are required")
        receipt = execute(args)
    except OperationFailed as exc:
        print(json.dumps(exc.receipt, sort_keys=True), file=sys.stdout)
        return 78
    except DeploymentError as exc:
        print(
            json.dumps(stopped_receipt(authority, [str(exc)]), sort_keys=True),
            file=sys.stdout,
        )
        return 78
    except Exception as exc:
        print(
            json.dumps(
                stopped_receipt(authority, [f"internal_failure:{type(exc).__name__}"]),
                sort_keys=True,
            ),
            file=sys.stdout,
        )
        return 78
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
