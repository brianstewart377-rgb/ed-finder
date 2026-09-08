#!/usr/bin/env python3
"""Fail-closed, production-in-place V3 application promotion.

This production authority is intentionally separate from the Contabo checkpoint.
It never builds, resolves dependencies, pulls source, runs migrations, or owns
PostgreSQL, Redis, NATS, the public-auth edge, Octopus, or unrelated containers.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
DEFAULT_COMPOSE = ROOT / "deploy/v3-production/compose.yml"
TARGET_SCHEMA = "ed-finder/v3-production-target-authority/v1"
SCHEMA_IDENTITY_SCHEMA = "ed-finder/v3-production-schema-identity/v1"
RECEIPT_SCHEMA = "ed-finder/v3-production-deployment-receipt/v1"
CURRENT_SCHEMA = "ed-finder/v3-production-current-release/v1"
PROJECT = "edfinder-v3-production"
EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
EXPECTED_ARCH = "x86_64"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
LEGACY_API = "edfinder-v3-api"
LEGACY_ORIGIN = "edfinder-v3-proxy"
PUBLIC_EDGE = "edfinder-v3-public-auth-edge"
LOCAL_DOCKER_ENDPOINT = "unix:///var/run/docker.sock"
SLOTS = ("blue", "green")
SERVICES = tuple(f"{kind}-{slot}" for slot in SLOTS for kind in ("api", "web"))
CONTAINERS = {
    f"{kind}-{slot}": f"edfinder-v3-production-{kind}-{slot}"
    for slot in SLOTS for kind in ("api", "web")
}
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
MODE = re.compile(r"0[0-7]{3}\Z")
MAX_JSON = 2 * 1024 * 1024
MAX_SMOKE = 4 * 1024 * 1024
MAX_ENV_FILE = 256 * 1024
MAX_REGISTRY_TOKEN = 64 * 1024
MAX_CONTAINERS = 256
COMMAND_TIMEOUT = 120
PROCESS_TERMINATION_GRACE = 5
READINESS_TIMEOUT = 120.0
CANCELLATION_SIGNALS = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
LEDGER_SQL = r"""
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10000ms';
SELECT json_build_object(
  'database_name', current_database(),
  'server_address', COALESCE(inet_server_addr()::text, 'local'),
  'server_port', COALESCE(inet_server_port(), current_setting('port')::int),
  'transaction_read_only', current_setting('transaction_read_only'),
  'migrations', COALESCE((
    SELECT json_agg(
      json_build_object('filename', filename, 'checksum_sha256', checksum_sha256)
      ORDER BY filename
    ) FROM public.schema_migrations
  ), '[]'::json)
)::text;
COMMIT;
""".strip()


class DeploymentError(ValueError):
    pass


class OperationFailed(DeploymentError):
    def __init__(self, receipt: dict[str, Any]):
        super().__init__("production promotion failed")
        self.receipt = receipt


class OperationCancelled(DeploymentError):
    def __init__(self, signum: int):
        self.signum = signum
        super().__init__(f"operation_cancelled:{signal.Signals(signum).name}")


class CancellationController:
    """Turn the first termination signal into one catchable deployment failure."""

    def __init__(self) -> None:
        self.received: int | None = None
        self.commit_started = False
        self.previous: dict[int, Any] = {}

    def handler(self, signum: int, _frame: Any) -> None:
        if self.commit_started or self.received is not None:
            return
        self.received = signum
        # Rollback, failure-receipt persistence, and cleanup must not be
        # interrupted by repeated cancellation signals.
        for handled in CANCELLATION_SIGNALS:
            signal.signal(handled, signal.SIG_IGN)
        raise OperationCancelled(signum)

    def mark_commit_started(self) -> None:
        # Cutover has already passed every verification gate. From this point
        # the small atomic receipt transaction must finish without interruption.
        self.commit_started = True
        for handled in CANCELLATION_SIGNALS:
            signal.signal(handled, signal.SIG_IGN)


_CANCELLATION_CONTROLLER: CancellationController | None = None
_PREMUTATION_FAILURE_RECEIPT_DIR: Path | None = None


@contextlib.contextmanager
def controlled_cancellation() -> Any:
    global _CANCELLATION_CONTROLLER
    controller = CancellationController()
    prior_controller = _CANCELLATION_CONTROLLER
    _CANCELLATION_CONTROLLER = controller
    try:
        for handled in CANCELLATION_SIGNALS:
            controller.previous[handled] = signal.getsignal(handled)
            signal.signal(handled, controller.handler)
        yield controller
    finally:
        for handled, previous in controller.previous.items():
            signal.signal(handled, previous)
        _CANCELLATION_CONTROLLER = prior_controller


@contextlib.contextmanager
def cancellation_blocked() -> Any:
    if _CANCELLATION_CONTROLLER is None or not hasattr(signal, "pthread_sigmask"):
        yield
        return
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, CANCELLATION_SIGNALS)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def terminate_and_reap(process: subprocess.Popen[str]) -> None:
    if _CANCELLATION_CONTROLLER is not None:
        # Once child cleanup starts, no later signal may interrupt the bounded
        # TERM/KILL/reap sequence and leak a Docker/Compose subprocess.
        for handled in CANCELLATION_SIGNALS:
            signal.signal(handled, signal.SIG_IGN)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=PROCESS_TERMINATION_GRACE)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.communicate()


def run_command(
    argv: list[str], *, env: dict[str, str] | None = None, input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    process: subprocess.Popen[str] | None = None
    try:
        # A pending cancellation is delivered only after Popen returns and the
        # new process-group leader is assigned to ``process``.
        with cancellation_blocked():
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True,
            )
        stdout, stderr = process.communicate(
            input=input_text, timeout=COMMAND_TIMEOUT
        )
    except OperationCancelled:
        if process is not None:
            terminate_and_reap(process)
        raise
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            terminate_and_reap(process)
        raise DeploymentError("bounded command failed: TimeoutExpired") from exc
    except OSError as exc:
        if process is not None:
            terminate_and_reap(process)
        raise DeploymentError(f"bounded command failed: {type(exc).__name__}") from exc
    except BaseException:
        if process is not None:
            terminate_and_reap(process)
        raise
    assert process is not None
    result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    if result.returncode != 0:
        raise DeploymentError(f"bounded command failed: {Path(argv[0]).name}")
    return result


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON or path.is_symlink():
            raise DeploymentError(f"{label} is oversized or unsafe")
        value = json.loads(path.read_text(encoding="utf-8"))
    except DeploymentError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"unable to read {label}") from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"{label} must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise DeploymentError("unable to checksum file") from exc
    return digest.hexdigest()


def verify_checksum(document: Path, sidecar: Path) -> str:
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise DeploymentError("unable to read checksum") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != document.name:
        raise DeploymentError("checksum must name only the adjacent manifest basename")
    if not re.fullmatch(r"[0-9a-f]{64}", fields[0]):
        raise DeploymentError("checksum must be 64 lowercase hexadecimal characters")
    if sha256_file(document) != fields[0]:
        raise DeploymentError("manifest checksum mismatch")
    return fields[0]


def manifest_tool() -> Any:
    path = ROOT / "scripts/release/v3_release_manifest.py"
    spec = importlib.util.spec_from_file_location("v3_release_manifest", path)
    if spec is None or spec.loader is None:
        raise DeploymentError("release manifest verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stopped_receipt(
    authority: dict[str, Any], failures: list[str], *, operation: str = "production-promotion",
) -> dict[str, Any]:
    target = authority.get("target") if isinstance(authority.get("target"), dict) else {}
    return {
        "schema_version": RECEIPT_SCHEMA,
        "operation": operation,
        "status": "stopped",
        "target": {
            "production": True,
            "hostname": target.get("hostname", EXPECTED_HOST),
            "fqdn": target.get("fqdn", EXPECTED_FQDN),
        },
        "failures": failures,
        "database_access_performed": False,
        "database_writes_performed": False,
        "migrations_performed": False,
        "application_data_writes_performed": False,
        "image_pulls_performed": False,
        "service_changes_performed": False,
        "edge_recreated": False,
        "protected_resources_changed": False,
        "filesystem_writes_performed": False,
        "env_files_read": False,
        "env_contents_recorded": False,
        "private_keys_read": False,
    }


def validate_authority(value: dict[str, Any]) -> list[str]:
    if value.get("schema_version") != TARGET_SCHEMA:
        raise DeploymentError("unsupported production target authority")
    target = value.get("target")
    if not isinstance(target, dict) or target != {
        "provider": "mevspace", "classification": "production", "production": True,
        "hostname": EXPECTED_HOST, "fqdn": EXPECTED_FQDN, "architecture": EXPECTED_ARCH,
    }:
        raise DeploymentError("exact production target identity authority is invalid")
    contract = value.get("application_contract")
    if not isinstance(contract, dict):
        raise DeploymentError("production application contract is missing")
    if contract.get("compose_project") != PROJECT or contract.get("slots") != list(SLOTS):
        raise DeploymentError("production Compose project/slot authority is invalid")
    if contract.get("services") != list(SERVICES):
        raise DeploymentError("production service allowlist is invalid")
    if contract.get("containers") != [CONTAINERS[item] for item in SERVICES]:
        raise DeploymentError("production container allowlist is invalid")
    if contract.get("named_volumes") != []:
        raise DeploymentError("production application Compose must not own volumes")
    preservation = value.get("preservation_contract")
    if not isinstance(preservation, dict) or preservation.get("never_recreate_or_remove") is not True:
        raise DeploymentError("production preservation contract is invalid")
    required = {PUBLIC_EDGE, POSTGRES_CONTAINER, "edfinder-v3-support-redis", "edfinder-v3-support-nats"}
    if set(preservation.get("exact_containers", [])) != required:
        raise DeploymentError("production exact preservation allowlist is invalid")
    status = value.get("status")
    blockers = value.get("blockers")
    if status not in {"stopped", "authorized"} or not isinstance(blockers, list):
        raise DeploymentError("production authority status is invalid")
    if status == "stopped":
        if not blockers or any(not isinstance(item, str) or not item for item in blockers):
            raise DeploymentError("stopped production authority requires concrete blockers")
        return sorted(set(blockers))
    if blockers:
        raise DeploymentError("authorized production authority cannot retain blockers")
    external = value.get("external_authority")
    if not isinstance(external, dict) or any(item is None for item in external.values()):
        raise DeploymentError("authorized production external authority is incomplete")
    capacity = value.get("reviewed_capacity")
    if (
        not isinstance(capacity, dict)
        or not isinstance(capacity.get("logical_cpus"), int)
        or capacity["logical_cpus"] < 12
        or not isinstance(capacity.get("memory_available_kib"), int)
        or capacity["memory_available_kib"] < 15 * 1024 * 1024
        or capacity.get("blue_green_peak")
        != {"cpus": "6.00", "memory": "10240m"}
    ):
        raise DeploymentError("reviewed production blue/green capacity is insufficient")
    if external.get("active_origin_bind") != "127.0.0.1:58080" or external.get("staging_origin_bind") != "127.0.0.1:58081":
        raise DeploymentError("production origin authority is invalid")
    if external.get("public_origin") != "https://ed-finder.app":
        raise DeploymentError("production public origin authority is invalid")
    if external.get("edge_route_authority") != {
        "strategy": "verified-loopback-blue-green-port-swap",
        "edge_container": PUBLIC_EDGE,
        "active_origin_bind": "127.0.0.1:58080",
        "evidence": "reviewed-production-inventory-receipt",
    }:
        raise DeploymentError("production unchanged-edge cutover authority is invalid")
    network_allowlist = external.get("application_network_allowed_containers")
    if (
        not isinstance(network_allowlist, list)
        or not network_allowlist
        or any(
            not isinstance(item, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", item)
            for item in network_allowlist
        )
        or len(network_allowlist) != len(set(network_allowlist))
    ):
        raise DeploymentError("production application network allowlist is invalid")
    if external.get("docker_context") != "default":
        raise DeploymentError("production Docker context authority must be default")
    for key in ("api_env_owner_uid", "receipt_owner_uid", "schema_identity_owner_uid"):
        if not isinstance(external.get(key), int) or external[key] < 0:
            raise DeploymentError(f"{key} is invalid")
    for key in ("api_env_mode", "receipt_mode", "schema_identity_mode"):
        if not isinstance(external.get(key), str) or not MODE.fullmatch(external[key]):
            raise DeploymentError(f"{key} is invalid")
    if (
        external["api_env_mode"] != "0600"
        or external["schema_identity_mode"] != "0600"
        or external["receipt_mode"] != "0700"
    ):
        raise DeploymentError("production secret/schema/receipt modes are not restrictive")
    if not re.fullmatch(r"[0-9a-f]{64}", str(external.get("schema_identity_sha256", ""))):
        raise DeploymentError("production schema identity checksum authority is invalid")
    return []


def exact_host_guard(runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    if socket.gethostname().split(".")[0] != EXPECTED_HOST:
        raise DeploymentError("unexpected production hostname")
    fqdn = runner(["hostname", "-f"]).stdout.strip()
    if fqdn != EXPECTED_FQDN or runner(["uname", "-m"]).stdout.strip() != EXPECTED_ARCH:
        raise DeploymentError("unexpected production FQDN or architecture")


def secure_path(path: Path, uid: int, mode: str, *, directory: bool) -> None:
    if not path.is_absolute() or path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise DeploymentError("authorized production path is missing or unsafe")
    details = path.stat()
    if details.st_uid != uid or stat.S_IMODE(details.st_mode) != int(mode, 8):
        raise DeploymentError("authorized production path ownership/mode mismatch")


def live_capacity_guard() -> dict[str, int]:
    memory_available_kib: int | None = None
    try:
        with Path("/proc/meminfo").open(encoding="utf-8") as memory_file:
            for line in memory_file:
                key, separator, value = line.partition(":")
                fields = value.split()
                if separator and key == "MemAvailable" and fields and fields[0].isdigit():
                    memory_available_kib = int(fields[0])
                    break
        filesystem = os.statvfs("/")
    except OSError as exc:
        raise DeploymentError("live production capacity inspection failed") from exc
    logical_cpus = os.cpu_count()
    root_available_bytes = filesystem.f_bavail * filesystem.f_frsize
    if (
        logical_cpus is None
        or logical_cpus < 12
        or memory_available_kib is None
        or memory_available_kib < 15 * 1024 * 1024
        or root_available_bytes < 10 * 1024 * 1024 * 1024
    ):
        raise DeploymentError("live production blue/green capacity is insufficient")
    return {
        "logical_cpus": logical_cpus,
        "memory_available_kib": memory_available_kib,
        "root_available_bytes": root_available_bytes,
    }


def base_env(external: dict[str, Any]) -> dict[str, str]:
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C", "LC_ALL": "C", "DOCKER_CONTEXT": external["docker_context"],
    }


def docker_context_guard(env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    context = json.loads(runner(["docker", "context", "inspect", env["DOCKER_CONTEXT"]], env=env).stdout)
    if not isinstance(context, list) or len(context) != 1:
        raise DeploymentError("Docker context inspection is ambiguous")
    endpoint = ((context[0].get("Endpoints") or {}).get("docker") or {}).get("Host")
    if endpoint != LOCAL_DOCKER_ENDPOINT:
        raise DeploymentError("Docker context is not the local rootful daemon")


def container_snapshot(names: set[str], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in sorted(names):
        raw = runner(["docker", "inspect", "--format", "{{.Id}}\t{{.State.Running}}", name], env=env).stdout.strip().split("\t")
        if len(raw) != 2 or not re.fullmatch(r"[0-9a-f]{64}", raw[0]) or raw[1] != "true":
            raise DeploymentError(f"protected container unavailable: {name}")
        result[name] = raw[0]
    return result


def all_container_snapshot(
    env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]
) -> dict[str, str]:
    output = runner(
        [
            "docker", "ps", "--all", "--no-trunc", "--format",
            "{{.Names}}\t{{.ID}}\t{{.State}}",
        ],
        env=env,
    ).stdout
    result: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", fields[0]):
            raise DeploymentError("complete container inventory is malformed")
        if not re.fullmatch(r"[0-9a-f]{64}", fields[1]):
            raise DeploymentError("complete container identity is malformed")
        result[fields[0]] = fields[1] + ":" + fields[2]
    if not result:
        raise DeploymentError("complete container inventory is empty")
    return result


def verify_unrelated_snapshot(
    before: dict[str, str], controlled: set[str], env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    after = all_container_snapshot(env, runner)
    expected = {key: value for key, value in before.items() if key not in controlled}
    observed = {key: after.get(key) for key in expected}
    if observed != expected:
        raise DeploymentError("unrelated production container identity/state changed")


def verify_snapshot(before: dict[str, str], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    if container_snapshot(set(before), env, runner) != before:
        raise DeploymentError("protected production container identity changed")


def validate_network(
    external: dict[str, Any], schema: dict[str, Any], managed_slots: set[str],
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    raw = runner(
        ["docker", "network", "inspect", external["application_network"]], env=env
    ).stdout
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeploymentError("production application network inspection invalid") from exc
    if not isinstance(values, list) or len(values) != 1:
        raise DeploymentError("production application network inspection ambiguous")
    value = values[0]
    if (
        value.get("Name") != external["application_network"]
        or value.get("Driver") != "bridge"
        or value.get("Scope") != "local"
        or value.get("Internal") is not False
        or value.get("Ingress") is not False
    ):
        raise DeploymentError("production application network is not an external local bridge")
    attachments = value.get("Containers")
    if not isinstance(attachments, dict):
        raise DeploymentError("production application network attachments invalid")
    names = sorted(
        item.get("Name") for item in attachments.values()
        if isinstance(item, dict) and isinstance(item.get("Name"), str)
    )
    allowed = external.get("application_network_allowed_containers")
    expected_names = list(allowed) if isinstance(allowed, list) else []
    if not managed_slots <= set(SLOTS):
        raise DeploymentError("production application network slot authority is invalid")
    for slot in sorted(managed_slots):
        expected_names.extend([CONTAINERS[f"api-{slot}"], CONTAINERS[f"web-{slot}"]])
    if not isinstance(allowed, list) or names != sorted(expected_names):
        raise DeploymentError("production application network attachment authority drifted")
    database_container = schema["database_identity"]["container"]
    if database_container not in names:
        raise DeploymentError("production database is not attached to the authorized app network")


def published_port_bindings(
    protected_ports: set[int], env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[int, list[dict[str, Any]]]:
    """Return every Docker binding for a protected host port without deduping."""
    if not protected_ports or any(not 1 <= port <= 65535 for port in protected_ports):
        raise DeploymentError("protected port inventory request is invalid")
    names = runner(
        ["docker", "ps", "--no-trunc", "--format", "{{.Names}}"], env=env
    ).stdout.splitlines()
    if (
        len(names) > MAX_CONTAINERS
        or len(names) != len(set(names))
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) for name in names)
    ):
        raise DeploymentError("running container inventory is malformed")
    bindings: dict[int, list[dict[str, Any]]] = {
        port: [] for port in protected_ports
    }
    for name in names:
        raw = runner(
            [
                "docker", "inspect", "--format",
                "{{json .NetworkSettings.Ports}}", name,
            ],
            env=env,
        ).stdout
        try:
            mappings = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeploymentError("published port inventory is malformed") from exc
        if not isinstance(mappings, dict):
            raise DeploymentError("published port inventory is malformed")
        for target, host_bindings in mappings.items():
            match = re.fullmatch(r"([0-9]{1,5})/(tcp|udp)", str(target))
            if match is None or not 1 <= int(match.group(1)) <= 65535:
                raise DeploymentError("published port inventory is malformed")
            if host_bindings is None:
                continue
            if not isinstance(host_bindings, list):
                raise DeploymentError("published port inventory is malformed")
            for host_binding in host_bindings:
                if not isinstance(host_binding, dict) or set(host_binding) != {
                    "HostIp", "HostPort"
                }:
                    raise DeploymentError("published port inventory is malformed")
                host_ip = host_binding["HostIp"]
                host_port = host_binding["HostPort"]
                if (
                    not isinstance(host_ip, str)
                    or not 0 < len(host_ip) <= 64
                    or not isinstance(host_port, str)
                    or not host_port.isdigit()
                    or not 1 <= int(host_port) <= 65535
                ):
                    raise DeploymentError("published port inventory is malformed")
                observed_host_port = int(host_port)
                if observed_host_port in protected_ports:
                    bindings[observed_host_port].append(
                        {
                            "container": name,
                            "bind_address": host_ip,
                            "host_port": observed_host_port,
                            "container_port": int(match.group(1)),
                            "protocol": match.group(2),
                        }
                    )
    return bindings


def listening_addresses(
    env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]
) -> dict[int, list[str]]:
    output = runner(["ss", "-H", "-lnt"], env=env).stdout
    listeners: dict[int, list[str]] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            raise DeploymentError("production listener inventory is malformed")
        address, separator, raw_port = fields[3].rpartition(":")
        if (
            not separator
            or not raw_port.isdigit()
            or not 1 <= int(raw_port) <= 65535
            or not address
        ):
            raise DeploymentError("production listener inventory is malformed")
        normalized = address.removeprefix("[").removesuffix("]")
        listeners.setdefault(int(raw_port), []).append(normalized)
    return listeners


def verify_exact_origin_bindings(
    active_owner: str, staging_owner: str | None, env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    listeners = listening_addresses(env, runner)
    bindings = published_port_bindings({58080, 58081}, env, runner)
    active_bindings = bindings[58080]
    staging_bindings = bindings[58081]
    if (
        len(active_bindings) != 1
        or active_bindings[0]["container"] != active_owner
        or active_bindings[0]["bind_address"] != "127.0.0.1"
        or active_bindings[0]["protocol"] != "tcp"
    ):
        raise DeploymentError("production active origin ownership drifted")
    active_listeners = listeners.get(58080, [])
    if not active_listeners:
        raise DeploymentError("production active origin listener is missing")
    if any(address != "127.0.0.1" for address in active_listeners):
        raise DeploymentError("production active origin listener is not exact loopback")
    staging_listeners = listeners.get(58081, [])
    if staging_owner is None:
        if staging_bindings or staging_listeners:
            raise DeploymentError("production staging origin port is already owned")
    elif (
        len(staging_bindings) != 1
        or staging_bindings[0]["container"] != staging_owner
        or staging_bindings[0]["bind_address"] != "127.0.0.1"
        or staging_bindings[0]["protocol"] != "tcp"
        or not staging_listeners
        or any(address != "127.0.0.1" for address in staging_listeners)
    ):
        raise DeploymentError("production staging origin ownership drifted")


def verify_origin_ownership(
    mode: str, prior_slot: str | None, env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    active_owner = LEGACY_ORIGIN if mode == "bootstrap" else (
        CONTAINERS[f"web-{prior_slot}"] if prior_slot in SLOTS else "invalid"
    )
    verify_exact_origin_bindings(active_owner, None, env, runner)


def verify_edge_routes_to_active_origin() -> None:
    origin_status, origin_body, _ = get("http://127.0.0.1:58080", "/api/health")
    public_status, public_body, _ = get("https://ed-finder.app", "/api/health")
    if (
        origin_status != 200
        or public_status != 200
        or origin_body != public_body
        or len(origin_body) > MAX_SMOKE
    ):
        raise DeploymentError("production edge-to-loopback route authority is unproved")


def wait_for_preserved_edge_route() -> None:
    deadline = time.monotonic() + READINESS_TIMEOUT
    while time.monotonic() < deadline:
        try:
            verify_edge_routes_to_active_origin()
            status, _body, _content_type = get(
                "http://127.0.0.1:58080", "/api/auth/session"
            )
            if status == 200:
                return
        except DeploymentError:
            pass
        time.sleep(2)
    raise DeploymentError("preserved production origin readiness timed out")


def validate_compose(compose: Path, authority: dict[str, Any], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    if sha256_file(compose) != authority["application_contract"]["compose_sha256"]:
        raise DeploymentError("production Compose checksum mismatch")
    compose_env = {
        **env,
        "V3_PRODUCTION_API_IMAGE": "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + "0" * 64,
        "V3_PRODUCTION_WEB_IMAGE": "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "1" * 64,
        "V3_PRODUCTION_SOURCE_SHA": "0" * 40,
        "V3_PRODUCTION_API_ENV_FILE": authority["external_authority"]["api_env_file"],
        "V3_PRODUCTION_ORIGIN_BIND": authority["external_authority"]["staging_origin_bind"],
        "V3_PRODUCTION_APP_NETWORK": authority["external_authority"]["application_network"],
    }
    base = ["docker", "compose", "--project-name", PROJECT, "--file", str(compose)]
    services = runner([*base, "config", "--services"], env=compose_env).stdout.split()
    volumes = runner([*base, "config", "--volumes"], env=compose_env).stdout.split()
    if services != list(SERVICES) or volumes:
        raise DeploymentError("rendered production Compose escapes app-only authority")


def validate_schema_file(path: Path, expected_sha: str) -> dict[str, Any]:
    if sha256_file(path) != expected_sha:
        raise DeploymentError("production schema identity checksum mismatch")
    value = load_json(path, "production schema identity")
    expected_keys = {"schema_version", "database_identity", "migration_set_identity", "migration_set_entries", "evidence"}
    if set(value) != expected_keys or value.get("schema_version") != SCHEMA_IDENTITY_SCHEMA:
        raise DeploymentError("production schema identity shape is invalid")
    identity = value.get("database_identity")
    if identity != {
        "container": POSTGRES_CONTAINER,
        "database_name": "edfinder",
        "database_user": "edfinder",
        "application_host": POSTGRES_CONTAINER,
        "server_address": "local",
        "server_port": 5432,
    }:
        raise DeploymentError("production database identity is invalid")
    entries = value.get("migration_set_entries")
    if not isinstance(entries, list) or not entries:
        raise DeploymentError("production schema identity has no entries")
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "mode", "sha256"}:
            raise DeploymentError("production schema entry shape is invalid")
        if not re.fullmatch(r"sql/[0-9]{3}_[a-z0-9_]+\.sql", str(item["path"])) or item["mode"] not in {"auto", "manual"} or not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])):
            raise DeploymentError("production schema entry is invalid")
    if len({item["path"] for item in entries}) != len(entries):
        raise DeploymentError("production schema entries are duplicated")
    evidence = value.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise DeploymentError("production schema identity lacks reviewed evidence")
    if re.search(
        r"(?i)(password|passwd|secret|private[-_ ]?key|access[-_ ]?token|dsn|credential)",
        evidence,
    ) or re.search(r"(?i)[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@", evidence):
        raise DeploymentError("production schema evidence contains secret-like text")
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    calculated = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if value.get("migration_set_identity") != calculated:
        raise DeploymentError("production schema identity is inconsistent")
    return value


def database_identity_from_env(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DeploymentError("unable to read verified production API env snapshot") from exc
    assignments: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if separator and key.strip() == "DATABASE_URL":
            assignments.append(raw_value.strip())
    if len(assignments) != 1:
        raise DeploymentError("production API env must contain exactly one DATABASE_URL")
    value = assignments[0]
    if (
        not value
        or value[0] in {"'", '"'}
        or "$" in value
        or "`" in value
        or any(character.isspace() for character in value)
    ):
        raise DeploymentError("production DATABASE_URL must be one unquoted literal")
    try:
        parsed = urllib.parse.urlsplit(value)
        database_name = urllib.parse.unquote(parsed.path.removeprefix("/"))
        username = urllib.parse.unquote(parsed.username or "")
        password = parsed.password
        port = parsed.port
    except (ValueError, UnicodeError) as exc:
        raise DeploymentError("production DATABASE_URL identity is invalid") from exc
    if (
        parsed.scheme not in {"postgresql", "postgres"}
        or username != "edfinder"
        or not password
        or parsed.hostname != POSTGRES_CONTAINER
        or port not in {None, 5432}
        or database_name != "edfinder"
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentError("production DATABASE_URL does not target retained PostgreSQL")
    return {
        "container": POSTGRES_CONTAINER,
        "database_name": database_name,
        "database_user": username,
        "application_host": parsed.hostname,
        "server_address": "local",
        "server_port": port or 5432,
    }


def verify_live_schema(schema: dict[str, Any], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    result = runner(
        ["docker", "exec", POSTGRES_CONTAINER, "psql", "-X", "--no-password", "--tuples-only", "--no-align", "--quiet", "--field-separator", "\t", "--set", "ON_ERROR_STOP=1", "--username", "edfinder", "--dbname", "edfinder", "--command", LEDGER_SQL],
        env=env,
    )
    if len(result.stdout.encode("utf-8")) > MAX_JSON:
        raise DeploymentError("production migration ledger output exceeds size limit")
    try:
        observed = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise DeploymentError("production migration ledger returned invalid JSON") from exc
    if not isinstance(observed, dict) or set(observed) != {
        "database_name", "server_address", "server_port",
        "transaction_read_only", "migrations",
    }:
        raise DeploymentError("production migration ledger returned invalid shape")
    ledger = observed["migrations"]
    if (
        not isinstance(ledger, list)
        or any(
            not isinstance(item, dict)
            or set(item) != {"filename", "checksum_sha256"}
            or not re.fullmatch(r"[0-9]{3}_[a-z0-9_]+\.sql", str(item["filename"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["checksum_sha256"]))
            for item in ledger
        )
        or len({item["filename"] for item in ledger}) != len(ledger)
    ):
        raise DeploymentError("production migration ledger entries are invalid")
    expected = sorted(
        (
            {
                "filename": item["path"].removeprefix("sql/"),
                "checksum_sha256": item["sha256"],
            }
            for item in schema["migration_set_entries"]
        ),
        key=lambda item: item["filename"],
    )
    if (
        observed["database_name"] != "edfinder"
        or observed["server_address"] != "local"
        or observed["server_port"] != 5432
        or observed["transaction_read_only"] != "on"
        or ledger != expected
    ):
        raise DeploymentError("production_migration_authority_absent_or_schema_incompatible")


def validate_candidate(
    candidate_path: Path, checksum_path: Path, schema: dict[str, Any]
) -> tuple[dict[str, Any], str, bytes]:
    checksum = verify_checksum(candidate_path, checksum_path)
    try:
        candidate_bytes = candidate_path.read_bytes()
        candidate = json.loads(candidate_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError("unable to freeze candidate manifest") from exc
    if (
        not isinstance(candidate, dict)
        or hashlib.sha256(candidate_bytes).hexdigest() != checksum
    ):
        raise DeploymentError("candidate manifest changed during validation")
    tool = manifest_tool()
    try:
        tool.validate_manifest(candidate, purpose="deploy", current_migration_set=schema["migration_set_identity"])
    except tool.ManifestError as exc:
        raise DeploymentError(f"candidate manifest is not production-schema compatible: {exc}") from exc
    if candidate.get("rollback", {}).get("application_only_eligible") is not True:
        raise DeploymentError("candidate is not eligible as an application-only rollback release")
    return candidate, checksum, candidate_bytes


def compose_env(external: dict[str, Any], release: dict[str, Any], env_file: Path, origin: str, docker_env: dict[str, str]) -> dict[str, str]:
    return {
        **docker_env,
        "V3_PRODUCTION_API_IMAGE": release["images"]["backend"],
        "V3_PRODUCTION_WEB_IMAGE": release["images"]["web"],
        "V3_PRODUCTION_SOURCE_SHA": release["git_sha"],
        "V3_PRODUCTION_API_ENV_FILE": str(env_file),
        "V3_PRODUCTION_ORIGIN_BIND": origin,
        "V3_PRODUCTION_APP_NETWORK": external["application_network"],
    }


def compose_base(compose: Path) -> list[str]:
    return ["docker", "compose", "--project-name", PROJECT, "--file", str(compose)]


def verify_image(image: str, sha: str, env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    raw = runner(["docker", "image", "inspect", "--format", "{{json .}}", image], env=env).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeploymentError("pulled image inspection is invalid") from exc
    labels = (value.get("Config") or {}).get("Labels") or {}
    digests = value.get("RepoDigests") or []
    if labels.get("org.opencontainers.image.revision") != sha or image not in digests:
        raise DeploymentError("pulled image digest/build SHA verification failed")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def get(origin: str, path: str) -> tuple[int, bytes, str]:
    request = urllib.request.Request(origin + path, headers={"User-Agent": "edfinder-v3-production-promote/1"})
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect
        ).open(request, timeout=10) as response:
            body = response.read(MAX_SMOKE + 1)
            return response.status, body, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_SMOKE + 1), exc.headers.get("Content-Type", "")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise DeploymentError("origin request failed") from exc


def smoke(origin: str, sha: str) -> dict[str, Any]:
    outcomes: dict[str, Any] = {}
    bodies: dict[str, bytes] = {}
    for path in ("/", "/api/health", "/openapi.json", "/api/auth/session"):
        status, body, content_type = get(origin, path)
        if not 200 <= status < 300 or len(body) > MAX_SMOKE:
            raise DeploymentError(f"smoke failed: {path}")
        outcomes[path] = {"status": status, "bytes": len(body), "content_type": content_type[:128]}
        bodies[path] = body
    try:
        health = json.loads(bodies["/api/health"])
        session = json.loads(bodies["/api/auth/session"])
        openapi = json.loads(bodies["/openapi.json"])
    except json.JSONDecodeError as exc:
        raise DeploymentError("smoke JSON response invalid") from exc
    if health.get("status") != "ok" or health.get("database") != "connected" or health.get("build_sha") != sha:
        raise DeploymentError("health release identity mismatch")
    if session.get("authenticated") is not False or session.get("user") is not None:
        raise DeploymentError("anonymous session smoke failed")
    paths = openapi.get("paths") if isinstance(openapi, dict) else None
    if not isinstance(paths, dict) or not {"/api/health", "/api/auth/session"}.issubset(paths):
        raise DeploymentError("OpenAPI smoke routes missing")
    marker = f'name="edfinder-build-sha" content="{sha}"'.encode()
    if bodies["/"].count(marker) != 1:
        raise DeploymentError("Svelte HTML release identity mismatch")
    return outcomes


def wait_ready(origin: str, sha: str) -> None:
    deadline = time.monotonic() + READINESS_TIMEOUT
    while time.monotonic() < deadline:
        try:
            status, body, _ = get(origin, "/api/health")
            value = json.loads(body)
            if status == 200 and value.get("status") == "ok" and value.get("database") == "connected" and value.get("build_sha") == sha:
                return
        except (DeploymentError, json.JSONDecodeError):
            pass
        time.sleep(2)
    raise DeploymentError("candidate readiness timed out")


def load_current(directory: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    pointer = load_json(directory / "current.json", "current production release pointer")
    if set(pointer) != {"schema_version", "receipt_file", "receipt_sha256", "manifest_file", "manifest_sha256"} or pointer.get("schema_version") != CURRENT_SCHEMA:
        raise DeploymentError("current production release pointer is invalid")
    for key in ("receipt_file", "manifest_file"):
        if not isinstance(pointer[key], str) or Path(pointer[key]).name != pointer[key]:
            raise DeploymentError("current production release filename is unsafe")
    if not re.fullmatch(
        r"[0-9a-f]{40}-[1-9][0-9]{0,19}-[0-9a-f]{64}\.json",
        pointer["receipt_file"],
    ) or pointer["manifest_file"] != pointer["receipt_file"].removesuffix(
        ".json"
    ) + ".release.json":
        raise DeploymentError("current production release filename is invalid")
    receipt_path = directory / pointer["receipt_file"]
    manifest_path = directory / pointer["manifest_file"]
    receipt_sidecar = Path(str(receipt_path) + ".sha256")
    manifest_sidecar = Path(str(manifest_path) + ".sha256")
    if any(
        path.is_symlink()
        for path in (receipt_path, manifest_path, receipt_sidecar, manifest_sidecar)
    ):
        raise DeploymentError("current production release path is unsafe")
    if (
        sha256_file(receipt_path) != pointer["receipt_sha256"]
        or sha256_file(manifest_path) != pointer["manifest_sha256"]
        or verify_checksum(receipt_path, receipt_sidecar) != pointer["receipt_sha256"]
        or verify_checksum(manifest_path, manifest_sidecar) != pointer["manifest_sha256"]
    ):
        raise DeploymentError("current production release checksum mismatch")
    receipt = load_json(receipt_path, "accepted production receipt")
    manifest = load_json(manifest_path, "accepted production manifest")
    if (
        receipt.get("schema_version") != RECEIPT_SCHEMA
        or receipt.get("status") != "accepted"
        or receipt.get("target", {}).get("hostname") != EXPECTED_HOST
        or receipt.get("target", {}).get("fqdn") != EXPECTED_FQDN
        or receipt.get("target", {}).get("production") is not True
        or receipt.get("compose_project") != PROJECT
        or receipt.get("source_sha") != manifest.get("git_sha")
        or receipt.get("images") != manifest.get("images")
        or receipt.get("manifest_sha256") != pointer["manifest_sha256"]
        or not RUN_ID.fullmatch(str(receipt.get("release_run_id", "")))
    ):
        raise DeploymentError("accepted production receipt does not bind its release")
    return receipt, manifest, manifest_path


def validate_prior_runtime(
    receipt: dict[str, Any], manifest: dict[str, Any], schema: dict[str, Any],
    env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]],
) -> str:
    slot = receipt.get("active_slot")
    if slot not in SLOTS or receipt.get("migration_set_identity") != schema["migration_set_identity"]:
        raise DeploymentError("prior accepted production receipt is schema-incompatible")
    tool = manifest_tool()
    try:
        tool.validate_manifest(
            manifest,
            purpose="rollback",
            current_migration_set=schema["migration_set_identity"],
        )
    except tool.ManifestError as exc:
        raise DeploymentError("prior accepted release is not rollback-compatible") from exc
    for image in manifest["images"].values():
        verify_image(image, manifest["git_sha"], env, runner)
    for service in (f"api-{slot}", f"web-{slot}"):
        raw = runner(
            [
                "docker", "inspect", "--format",
                "{{.State.Running}}\t{{.Config.Image}}\t"
                "{{index .Config.Labels \"org.opencontainers.image.revision\"}}",
                CONTAINERS[service],
            ],
            env=env,
        ).stdout.strip().split("\t")
        expected_image = manifest["images"][
            "backend" if service.startswith("api-") else "web"
        ]
        if raw != ["true", expected_image, manifest["git_sha"]]:
            raise DeploymentError("prior accepted application container drifted")
    smoke("http://127.0.0.1:58080", manifest["git_sha"])
    return slot


def persist_accepted(
    directory: Path, receipt: dict[str, Any], manifest_bytes: bytes
) -> None:
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    stem = f"{receipt['source_sha']}-{receipt['release_run_id']}-{receipt['manifest_sha256']}"
    receipt_name = stem + ".json"
    manifest_name = stem + ".release.json"
    receipt_sidecar = receipt_name + ".sha256"
    manifest_sidecar = manifest_name + ".sha256"
    for name in (
        receipt_name, manifest_name, receipt_sidecar, manifest_sidecar,
        "current.json",
    ):
        if Path(name).name != name:
            raise DeploymentError("unsafe receipt identity")
    def atomic(name: str, data: bytes) -> None:
        handle, temp_name = tempfile.mkstemp(prefix=".v3-production-", dir=directory)
        try:
            os.fchmod(handle, 0o600)
            with os.fdopen(handle, "wb") as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            os.replace(temp_name, directory / name)
        finally:
            try: os.unlink(temp_name)
            except FileNotFoundError: pass
    if any(
        (directory / name).exists()
        for name in (receipt_name, manifest_name, receipt_sidecar, manifest_sidecar)
    ):
        raise DeploymentError("immutable production receipt identity already exists")
    created: list[str] = []
    try:
        atomic(receipt_name, receipt_bytes)
        created.append(receipt_name)
        atomic(manifest_name, manifest_bytes)
        created.append(manifest_name)
        atomic(
            receipt_sidecar,
            f"{hashlib.sha256(receipt_bytes).hexdigest()}  {receipt_name}\n".encode(),
        )
        created.append(receipt_sidecar)
        atomic(
            manifest_sidecar,
            f"{hashlib.sha256(manifest_bytes).hexdigest()}  {manifest_name}\n".encode(),
        )
        created.append(manifest_sidecar)
        pointer = {
            "schema_version": CURRENT_SCHEMA,
            "receipt_file": receipt_name,
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "manifest_file": manifest_name,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        }
        directory_handle = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_handle)
        finally:
            os.close(directory_handle)
        atomic(
            "current.json",
            (json.dumps(pointer, sort_keys=True, indent=2) + "\n").encode(),
        )
        directory_handle = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_handle)
        except OSError:
            # The pointer and every target are already complete and consistent;
            # never delete its targets after advancing it.
            pass
        finally:
            os.close(directory_handle)
    except Exception:
        for name in reversed(created):
            try:
                (directory / name).unlink()
            except OSError:
                pass
        raise


def persist_failure(directory: Path, receipt: dict[str, Any]) -> str:
    data = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    basename = (
        f"failed-{receipt.get('source_sha', 'unknown')}-"
        f"{receipt.get('release_run_id', 'unknown')}-{stamp}-{os.getpid()}.json"
    )
    if Path(basename).name != basename:
        raise DeploymentError("unsafe failure receipt identity")
    path = directory / basename
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    sidecar = Path(str(path) + ".sha256")
    checksum = hashlib.sha256(data).hexdigest()
    sidecar.write_text(f"{checksum}  {basename}\n", encoding="utf-8")
    os.chmod(sidecar, 0o600)
    return basename


def freeze_env(
    source: Path, directory: Path, expected_uid: int, expected_mode: str,
) -> tuple[Path, tuple[int, int, int, int, int, str]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != expected_uid
            or stat.S_IMODE(before.st_mode) != int(expected_mode, 8)
        ):
            raise DeploymentError("authorized production API env file is unsafe")
        if before.st_size > MAX_ENV_FILE:
            raise DeploymentError("authorized production API env file exceeds size limit")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        current = source.lstat()
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mode, before.st_uid)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mode, after.st_uid)
            or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise DeploymentError("authorized production API env file changed while opening")
    finally:
        os.close(descriptor)
    fingerprint = (
        before.st_dev, before.st_ino, before.st_size, before.st_mode,
        before.st_uid, hashlib.sha256(data).hexdigest(),
    )
    handle, name = tempfile.mkstemp(prefix=".v3-production-env-", dir=directory)
    os.fchmod(handle, 0o600)
    with os.fdopen(handle, "wb") as output:
        output.write(data); output.flush(); os.fsync(output.fileno())
    return Path(name), fingerprint


def verify_env_unchanged(
    source: Path, fingerprint: tuple[int, int, int, int, int, str],
) -> None:
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_ENV_FILE:
            raise DeploymentError("authorized production API env file is unsafe")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        current = source.lstat()
    finally:
        os.close(descriptor)
    observed = (
        before.st_dev, before.st_ino, before.st_size, before.st_mode,
        before.st_uid, digest.hexdigest(),
    )
    stable = (
        before.st_dev, before.st_ino, before.st_size, before.st_mode, before.st_uid
    ) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mode, after.st_uid
    )
    if (
        observed != fingerprint
        or not stable
        or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise DeploymentError("authorized production API env file changed during promotion")


def acquire_lock(directory: Path) -> Any:
    handle = (directory / "deploy.lock").open("a+", encoding="utf-8")
    os.fchmod(handle.fileno(), 0o600)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise DeploymentError("production deployment lock unavailable") from exc
    return handle


def validate_runtime_directory(supplied: Path) -> Path:
    runtime_directory = supplied.resolve()
    if (
        not supplied.is_absolute()
        or supplied != runtime_directory
        or supplied.is_symlink()
        or not runtime_directory.is_dir()
        or runtime_directory.stat().st_uid != os.geteuid()
        or stat.S_IMODE(runtime_directory.stat().st_mode) != 0o700
    ):
        raise DeploymentError("private production operation runtime directory is unsafe")
    return runtime_directory


def promote(args: argparse.Namespace, authority: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]] = run_command) -> dict[str, Any]:
    global _PREMUTATION_FAILURE_RECEIPT_DIR
    _PREMUTATION_FAILURE_RECEIPT_DIR = None
    external = authority["external_authority"]
    receipt_operation = (
        "production-preflight" if args.operation == "preflight" else "production-promotion"
    )
    env = base_env(external)
    exact_host_guard(runner)
    secure_path(Path(external["api_env_file"]), external["api_env_owner_uid"], external["api_env_mode"], directory=False)
    receipt_dir = Path(external["receipt_directory"])
    secure_path(receipt_dir, external["receipt_owner_uid"], external["receipt_mode"], directory=True)
    # Only an exact verified host and receipt store may receive a durable
    # pre-mutation cancellation receipt.
    _PREMUTATION_FAILURE_RECEIPT_DIR = receipt_dir
    schema_path = Path(external["schema_identity_file"])
    secure_path(
        schema_path, external["schema_identity_owner_uid"],
        external["schema_identity_mode"], directory=False,
    )
    docker_context_guard(env, runner)
    validate_compose(args.compose, authority, env, runner)
    schema = validate_schema_file(schema_path, external["schema_identity_sha256"])
    network_slots: set[str] = set()
    if args.mode == "upgrade":
        network_receipt, _network_manifest, _network_path = load_current(receipt_dir)
        network_active_slot = network_receipt.get("active_slot")
        if network_active_slot not in SLOTS:
            raise DeploymentError("accepted production network slot is invalid")
        network_slots.add(network_active_slot)
    validate_network(external, schema, network_slots, env, runner)
    live_capacity = live_capacity_guard()
    try:
        api_database_identity = database_identity_from_env(
            Path(external["api_env_file"])
        )
    except DeploymentError as exc:
        receipt = stopped_receipt(
            authority, [str(exc)], operation=receipt_operation
        )
        receipt["env_files_read"] = True
        raise OperationFailed(receipt) from exc
    if api_database_identity != schema["database_identity"]:
        receipt = stopped_receipt(
            authority,
            ["production API database target does not match schema authority"],
            operation=receipt_operation,
        )
        receipt["env_files_read"] = True
        raise OperationFailed(receipt)
    candidate, candidate_sum, candidate_bytes = validate_candidate(
        args.candidate, args.candidate_checksum, schema
    )
    if not RUN_ID.fullmatch(args.candidate_run_id or ""):
        raise DeploymentError("authenticated candidate release run ID required")
    protected = set(authority["preservation_contract"]["exact_containers"])
    protected_before = container_snapshot(protected, env, runner)
    all_before = all_container_snapshot(env, runner)

    if args.mode == "bootstrap":
        prior_slot_for_preflight = None
        if set(CONTAINERS.values()) & set(all_before):
            raise DeploymentError("bootstrap requires production slot absence")
        for legacy_name in (LEGACY_API, LEGACY_ORIGIN):
            if not all_before.get(legacy_name, "").endswith(":running"):
                raise DeploymentError("bootstrap requires running legacy application services")
    else:
        prior_for_preflight, prior_manifest_for_preflight, _ = load_current(
            receipt_dir
        )
        prior_slot_for_preflight = validate_prior_runtime(
            prior_for_preflight, prior_manifest_for_preflight, schema, env, runner
        )
    verify_origin_ownership(args.mode, prior_slot_for_preflight, env, runner)
    verify_edge_routes_to_active_origin()

    if args.operation == "preflight":
        try:
            verify_live_schema(schema, env, runner)
            verify_snapshot(protected_before, env, runner)
            verify_unrelated_snapshot(all_before, set(), env, runner)
            live_capacity = live_capacity_guard()
        except DeploymentError as exc:
            receipt = stopped_receipt(
                authority, [str(exc)], operation="production-preflight"
            )
            receipt.update(
                database_access_performed=None,
                database_access_may_have_been_performed=True,
                env_files_read=True,
            )
            raise OperationFailed(receipt) from exc
        return {
            **stopped_receipt(authority, [], operation="production-preflight"),
            "status": "preflight-passed", "mode": args.mode,
            "source_sha": candidate["git_sha"], "release_run_id": args.candidate_run_id,
            "manifest_sha256": candidate_sum, "migration_set_identity": schema["migration_set_identity"],
            "images": candidate["images"],
            "rollback_compatible": args.mode == "upgrade",
            "live_capacity": live_capacity,
            "database_access_performed": True,
            "env_files_read": True,
        }

    if args.runtime_directory is None:
        raise DeploymentError("private production operation runtime directory required")
    runtime_directory = validate_runtime_directory(args.runtime_directory)
    lock = acquire_lock(receipt_dir)
    snapshot: Path | None = None
    docker_config: str | None = None
    mutation_started = False
    cutover_started = False
    image_pull_attempted = False
    pulled_images: list[str] = []
    database_verified = False
    prior_receipt: dict[str, Any] | None = None
    prior_manifest: dict[str, Any] | None = None
    target_slot = "blue"
    try:
        live_capacity = live_capacity_guard()
        verify_live_schema(schema, env, runner)
        database_verified = True
        current_path = receipt_dir / "current.json"
        if args.mode == "bootstrap":
            if current_path.exists():
                raise DeploymentError("bootstrap requires no accepted production release")
            prior_slot = None
        else:
            prior_receipt, prior_manifest, _ = load_current(receipt_dir)
            prior_slot = validate_prior_runtime(
                prior_receipt, prior_manifest, schema, env, runner
            )
            if prior_manifest.get("git_sha") == candidate.get("git_sha"):
                raise DeploymentError("candidate cannot be its own prior release")
            target_slot = "green" if prior_slot == "blue" else "blue"
        validate_network(
            external, schema, {prior_slot} if prior_slot is not None else set(),
            env, runner,
        )
        verify_origin_ownership(args.mode, prior_slot, env, runner)
        verify_edge_routes_to_active_origin()
        snapshot, fingerprint = freeze_env(
            Path(external["api_env_file"]), runtime_directory,
            external["api_env_owner_uid"], external["api_env_mode"],
        )
        if database_identity_from_env(snapshot) != schema["database_identity"]:
            raise DeploymentError("frozen production API database target does not match schema authority")
        verify_env_unchanged(Path(external["api_env_file"]), fingerprint)
        if (
            args.registry_token_file is None
            or not args.registry_token_file.is_file()
            or args.registry_token_file.is_symlink()
            or not isinstance(args.registry_username, str)
            or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", args.registry_username)
        ):
            raise DeploymentError("ephemeral production registry authority is missing")
        token_details = args.registry_token_file.stat(follow_symlinks=False)
        if (
            token_details.st_uid != os.geteuid()
            or stat.S_IMODE(token_details.st_mode) != 0o600
            or token_details.st_nlink != 1
        ):
            raise DeploymentError("ephemeral registry token path is unsafe")
        if args.registry_token_file.stat().st_size > MAX_REGISTRY_TOKEN:
            raise DeploymentError("ephemeral registry token exceeds size limit")
        token = args.registry_token_file.read_text(encoding="utf-8").strip()
        if not token or "\n" in token or "\r" in token:
            raise DeploymentError("ephemeral registry token is invalid")
        docker_config = tempfile.mkdtemp(
            prefix=".v3-production-docker-", dir=runtime_directory
        )
        os.chmod(docker_config, 0o700)
        env["DOCKER_CONFIG"] = docker_config
        runner(
            [
                "docker", "login", "ghcr.io", "--username",
                args.registry_username, "--password-stdin",
            ],
            env=env,
            input_text=token + "\n",
        )
        token = ""
        for image in candidate["images"].values():
            image_pull_attempted = True
            runner(["docker", "pull", image], env=env)
            verify_image(image, candidate["git_sha"], env, runner)
            pulled_images.append(image)
        release_env = compose_env(external, candidate, snapshot, external["staging_origin_bind"], env)
        base = compose_base(args.compose)
        selected = [f"api-{target_slot}", f"web-{target_slot}"]
        mutation_started = True
        runner([*base, "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never", *selected], env=release_env)
        wait_ready("http://" + external["staging_origin_bind"], candidate["git_sha"])
        staging_smoke = smoke("http://" + external["staging_origin_bind"], candidate["git_sha"])
        active_owner = LEGACY_ORIGIN if args.mode == "bootstrap" else CONTAINERS[
            f"web-{prior_slot}"
        ]
        verify_exact_origin_bindings(
            active_owner, CONTAINERS[f"web-{target_slot}"], env, runner
        )
        verify_snapshot(protected_before, env, runner)
        controlled = {CONTAINERS[item] for item in selected}
        verify_unrelated_snapshot(all_before, controlled, env, runner)
        verify_env_unchanged(Path(external["api_env_file"]), fingerprint)
        verify_live_schema(schema, env, runner)
        staged_slots = {target_slot}
        if prior_slot is not None:
            staged_slots.add(prior_slot)
        validate_network(external, schema, staged_slots, env, runner)

        cutover_started = True
        if args.mode == "bootstrap":
            runner(["docker", "stop", LEGACY_ORIGIN], env=env)
        else:
            assert prior_slot is not None
            runner([*base, "stop", f"web-{prior_slot}"], env=release_env)
        active_env = compose_env(external, candidate, snapshot, external["active_origin_bind"], env)
        runner([*base, "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never", f"web-{target_slot}"], env=active_env)
        wait_ready("http://" + external["active_origin_bind"], candidate["git_sha"])
        verify_exact_origin_bindings(
            CONTAINERS[f"web-{target_slot}"], None, env, runner
        )
        active_smoke = smoke("http://" + external["active_origin_bind"], candidate["git_sha"])
        public_smoke = smoke(external["public_origin"], candidate["git_sha"])
        verify_live_schema(schema, env, runner)
        verify_env_unchanged(Path(external["api_env_file"]), fingerprint)
        verify_snapshot(protected_before, env, runner)
        controlled.add(LEGACY_ORIGIN if args.mode == "bootstrap" else CONTAINERS[f"web-{prior_slot}"])
        if args.mode == "upgrade":
            assert prior_slot is not None
            runner([*base, "stop", f"api-{prior_slot}"], env=active_env)
            controlled.add(CONTAINERS[f"api-{prior_slot}"])
            runner(
                [*base, "rm", "--force", f"api-{prior_slot}", f"web-{prior_slot}"],
                env=active_env,
            )
        else:
            runner(["docker", "stop", LEGACY_API], env=env)
            controlled.add(LEGACY_API)
        validate_network(external, schema, {target_slot}, env, runner)
        verify_unrelated_snapshot(all_before, controlled, env, runner)
        changed_resources = [CONTAINERS[item] for item in selected]
        if args.mode == "bootstrap":
            changed_resources.extend([LEGACY_API, LEGACY_ORIGIN])
        else:
            assert prior_slot is not None
            changed_resources.extend(
                [CONTAINERS[f"api-{prior_slot}"], CONTAINERS[f"web-{prior_slot}"]]
            )
        receipt = {
            "schema_version": RECEIPT_SCHEMA, "operation": "production-promotion", "status": "accepted",
            "mode": args.mode, "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target": authority["target"], "compose_project": PROJECT, "active_slot": target_slot,
            "source_sha": candidate["git_sha"], "release_run_id": args.candidate_run_id,
            "images": candidate["images"], "manifest_sha256": candidate_sum,
            "migration_set_identity": schema["migration_set_identity"],
            "changed_resources": changed_resources,
            "preserved_resources": protected_before, "staging_smoke": staging_smoke,
            "live_capacity": live_capacity,
            "active_smoke": active_smoke, "public_smoke": public_smoke,
            "rollback": {"kind": "none-first-promotion"} if prior_receipt is None else {
                "kind": "prior-accepted-immutable-release", "source_sha": prior_receipt["source_sha"],
                "release_run_id": prior_receipt["release_run_id"], "schema_compatible": True,
            },
            "database_access_performed": True, "database_writes_performed": False,
            "migrations_performed": False, "application_data_writes_performed": False,
            "image_pulls_performed": True, "service_changes_performed": True,
            "edge_recreated": False, "protected_resources_changed": False,
            "filesystem_writes_performed": True, "env_contents_recorded": False,
            "env_files_read": True,
            "private_keys_read": False,
        }
        if _CANCELLATION_CONTROLLER is not None:
            _CANCELLATION_CONTROLLER.mark_commit_started()
        persist_accepted(receipt_dir, receipt, candidate_bytes)
        return receipt
    except Exception as original:
        rollback = {"attempted": False, "status": "not-required"}
        if mutation_started:
            rollback = {"attempted": True, "status": "started"}
            try:
                base = compose_base(args.compose)
                candidate_env = compose_env(external, candidate, snapshot or Path(external["api_env_file"]), external["staging_origin_bind"], env)
                runner([*base, "stop", f"web-{target_slot}", f"api-{target_slot}"], env=candidate_env)
                runner([*base, "rm", "--force", f"web-{target_slot}", f"api-{target_slot}"], env=candidate_env)
                if cutover_started and args.mode == "bootstrap":
                    runner(["docker", "start", LEGACY_API], env=env)
                    runner(["docker", "start", LEGACY_ORIGIN], env=env)
                    wait_for_preserved_edge_route()
                    rollback = {"attempted": True, "status": "verified", "kind": "first-cutover-abort-to-preserved-origin", "accepted_release_rollback": False}
                elif cutover_started and prior_receipt is not None and prior_manifest is not None:
                    verify_live_schema(schema, env, runner)
                    rollback_tool = manifest_tool()
                    rollback_tool.validate_manifest(
                        prior_manifest,
                        purpose="rollback",
                        current_migration_set=schema["migration_set_identity"],
                    )
                    prior_slot = prior_receipt["active_slot"]
                    prior_env = compose_env(external, prior_manifest, snapshot or Path(external["api_env_file"]), external["active_origin_bind"], env)
                    runner([*base, "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never", f"api-{prior_slot}", f"web-{prior_slot}"], env=prior_env)
                    wait_ready("http://" + external["active_origin_bind"], prior_manifest["git_sha"])
                    smoke("http://" + external["active_origin_bind"], prior_manifest["git_sha"])
                    smoke(external["public_origin"], prior_manifest["git_sha"])
                    verify_snapshot(protected_before, env, runner)
                    rollback = {"attempted": True, "status": "verified", "kind": "prior-accepted-immutable-release", "source_sha": prior_manifest["git_sha"], "schema_compatible": True}
                else:
                    rollback = {"attempted": True, "status": "verified", "kind": "candidate-stage-removed"}
            except Exception as rollback_error:
                rollback = {"attempted": True, "status": "failed", "failure": type(rollback_error).__name__}
        failure = str(original) if isinstance(original, DeploymentError) else type(original).__name__
        resource_drift = failure in {
            "protected production container identity changed",
            "unrelated production container identity/state changed",
        }
        receipt = stopped_receipt(authority, [failure])
        receipt.update(
            status="failed", source_sha=candidate["git_sha"], release_run_id=args.candidate_run_id,
            manifest_sha256=candidate_sum, migration_set_identity=schema["migration_set_identity"],
            database_access_performed=True if database_verified else None,
            database_access_may_have_been_performed=not database_verified,
            image_pull_attempted=image_pull_attempted,
            image_pulls_performed=(
                True if pulled_images else None if image_pull_attempted else False
            ),
            pulled_images_verified=pulled_images,
            service_changes_performed=None if mutation_started else False,
            service_changes_may_have_been_performed=mutation_started,
            protected_resources_changed=True if resource_drift else None if mutation_started else False,
            protected_resources_may_have_changed=mutation_started and not resource_drift,
            filesystem_writes_performed=True,
            env_files_read=True,
            rollback=rollback,
        )
        try:
            receipt["durable_failure_receipt"] = persist_failure(
                receipt_dir, receipt
            )
        except (OSError, DeploymentError):
            receipt["durable_failure_receipt"] = None
            receipt["failure_receipt_persistence"] = "failed"
        raise OperationFailed(receipt) from original
    finally:
        if docker_config:
            try: runner(["docker", "logout", "ghcr.io"], env=env)
            except DeploymentError: pass
            shutil.rmtree(docker_config, ignore_errors=True)
        if snapshot is not None:
            try:
                size = snapshot.stat().st_size
                with snapshot.open("r+b", buffering=0) as handle:
                    handle.write(b"\0" * size)
                    handle.flush()
                    os.fsync(handle.fileno())
                snapshot.unlink()
            except OSError:
                pass
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    result.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    result.add_argument("--operation", choices=("authority-gate", "preflight", "promote"), default="authority-gate")
    result.add_argument("--mode", choices=("bootstrap", "upgrade"), default="bootstrap")
    result.add_argument("--candidate", type=Path)
    result.add_argument("--candidate-checksum", type=Path)
    result.add_argument("--candidate-run-id")
    result.add_argument("--registry-token-file", type=Path)
    result.add_argument("--registry-username")
    result.add_argument("--runtime-directory", type=Path)
    return result


def _main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    authority: dict[str, Any] = {}
    try:
        authority = load_json(args.authority, "production target authority")
        blockers = validate_authority(authority)
        if blockers:
            operation = {
                "preflight": "production-preflight",
                "promote": "production-promotion",
                "authority-gate": "production-authority-gate",
            }[args.operation]
            print(json.dumps(stopped_receipt(authority, blockers, operation=operation), sort_keys=True))
            return 78
        if args.operation == "authority-gate":
            receipt = stopped_receipt(
                authority, [], operation="production-authority-gate"
            )
            receipt["status"] = "authority-verified"
            print(json.dumps(receipt, sort_keys=True))
            return 0
        if args.candidate is None or args.candidate_checksum is None:
            raise DeploymentError("candidate manifest and checksum are required")
        receipt = promote(args, authority)
    except OperationFailed as exc:
        print(json.dumps(exc.receipt, sort_keys=True))
        return 78
    except DeploymentError as exc:
        operation = {
            "preflight": "production-preflight",
            "promote": "production-promotion",
            "authority-gate": "production-authority-gate",
        }[args.operation]
        receipt = stopped_receipt(authority, [str(exc)], operation=operation)
        if (
            isinstance(exc, OperationCancelled)
            and args.operation == "promote"
            and _PREMUTATION_FAILURE_RECEIPT_DIR is not None
        ):
            # A cancellation during the read-only pre-mutation gates occurs
            # before promote() creates any ephemeral credentials or services,
            # but it still needs durable host evidence.
            receipt.update(
                status="failed",
                source_sha="unknown",
                release_run_id=args.candidate_run_id or "unknown",
                database_access_performed=None,
                database_access_may_have_been_performed=True,
                service_changes_performed=False,
                service_changes_may_have_been_performed=False,
                filesystem_writes_performed=True,
                rollback={"attempted": False, "status": "not-required"},
            )
            try:
                receipt["durable_failure_receipt"] = persist_failure(
                    _PREMUTATION_FAILURE_RECEIPT_DIR, receipt
                )
            except (OSError, DeploymentError):
                receipt["durable_failure_receipt"] = None
                receipt["failure_receipt_persistence"] = "failed"
        print(json.dumps(receipt, sort_keys=True))
        return 78
    except Exception as exc:
        operation = {
            "preflight": "production-preflight",
            "promote": "production-promotion",
            "authority-gate": "production-authority-gate",
        }[args.operation]
        print(json.dumps(stopped_receipt(
            authority, [f"internal_failure:{type(exc).__name__}"], operation=operation,
        ), sort_keys=True))
        return 78
    print(json.dumps(receipt, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    with controlled_cancellation():
        return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
