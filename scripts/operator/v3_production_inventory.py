#!/usr/bin/env python3
"""Read-only, secret-safe inventory for the exact V3 production host.

The helper accepts no target or command input. It intentionally runs on the
already-present host Python because installing a new host runtime is outside a
read-only inventory. Application and release runtimes remain CPython 3.14.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
DB_USER = "edfinder"
DB_NAME = "edfinder"
ORIGIN = "http://127.0.0.1:58080"
PUBLIC = "https://ed-finder.app"
MAX_CONTAINERS = 256
MAX_LISTENERS = 128
MAX_BODY = 65536
TIMEOUT_SECONDS = 15
SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
MAX_RUNTIME_VERSION = 64
MAX_DOCKER_ENDPOINT = 256
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


def bounded_executable(value: str | None) -> str | None:
    if (
        isinstance(value, str)
        and len(value) <= 256
        and re.fullmatch(r"/[A-Za-z0-9_./+-]+", value)
        and ".." not in value.split("/")
    ):
        return value
    return None


def bounded_docker_endpoint(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not 0 < len(value) <= MAX_DOCKER_ENDPOINT
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.query or parsed.fragment:
        return None
    if parsed.scheme == "unix":
        if (
            parsed.netloc
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", parsed.path)
            or ".." in parsed.path.split("/")
        ):
            return None
        return value
    if parsed.scheme == "tcp":
        if (
            parsed.hostname is None
            or port is None
            or parsed.path not in {"", "/"}
            or not re.fullmatch(r"[A-Za-z0-9_.:-]+", parsed.hostname)
        ):
            return None
        return value
    return None


def run(argv: list[str], *, timeout: int = TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, text=True, capture_output=True, timeout=timeout, check=False,
            env={"PATH": SAFE_PATH, "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def docker_json_lines(argv: list[str]) -> tuple[bool, list[dict[str, Any]]]:
    result = run(argv)
    items: list[dict[str, Any]] = []
    if result.returncode == 0:
        try:
            for line in result.stdout.splitlines():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError
                items.append(value)
        except (json.JSONDecodeError, ValueError):
            return False, []
    return result.returncode == 0, items


def sanitize_container(item: dict[str, Any]) -> dict[str, Any]:
    allowed = ("Names", "Image", "ID", "State", "Status", "Ports", "Networks")
    return {key: item.get(key) for key in allowed}


def sanitize_network(item: dict[str, Any]) -> dict[str, Any]:
    allowed = ("Name", "ID", "Driver", "Scope", "Internal", "IPv6")
    return {key: item.get(key) for key in allowed}


def inventory_runtime() -> dict[str, Any]:
    """Describe the interpreter already selected by the read-only launcher."""
    implementation = platform.python_implementation()
    version = platform.python_version()
    executable = bounded_executable(sys.executable)
    return {
        "inspection_succeeded": (
            0 < len(implementation) <= MAX_RUNTIME_VERSION
            and 0 < len(version) <= MAX_RUNTIME_VERSION
            and executable is not None
        ),
        "command": "python3",
        "used_for_inventory": True,
        "executable": executable,
        "implementation": implementation[:MAX_RUNTIME_VERSION],
        "version": version[:MAX_RUNTIME_VERSION],
        "version_info": [
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        ],
        "is_exact_cpython_3_14": (
            implementation == "CPython"
            and sys.version_info[:2] == (3, 14)
        ),
    }


def inspect_python314_runtime() -> dict[str, Any]:
    """Inspect, but never install, the mutation runtime required by authority."""
    executable = shutil.which("python3.14", path=SAFE_PATH)
    unavailable: dict[str, Any] = {
        "inspection_succeeded": True,
        "command": "python3.14",
        "exists": False,
        "executable": None,
        "implementation": None,
        "version": None,
        "version_info": None,
        "is_exact_cpython_3_14": False,
    }
    if executable is None:
        return unavailable
    bounded_path = bounded_executable(executable)
    if bounded_path is None:
        return {**unavailable, "inspection_succeeded": False, "exists": True}
    probe = run(
        [
            bounded_path,
            "-I",
            "-S",
            "-c",
            (
                "import json,platform,sys;"
                "print(json.dumps({'implementation':platform.python_implementation(),"
                "'version':platform.python_version(),"
                "'version_info':list(sys.version_info[:3])},separators=(',',':')))"
            ),
        ]
    )
    failed = {
        **unavailable,
        "inspection_succeeded": False,
        "exists": True,
        "executable": bounded_path,
    }
    if probe.returncode != 0 or len(probe.stdout) > 512:
        return failed
    try:
        observed = json.loads(probe.stdout.strip())
    except json.JSONDecodeError:
        return failed
    if not isinstance(observed, dict) or set(observed) != {
        "implementation", "version", "version_info",
    }:
        return failed
    implementation = observed["implementation"]
    version = observed["version"]
    version_info = observed["version_info"]
    if (
        not isinstance(implementation, str)
        or not 0 < len(implementation) <= MAX_RUNTIME_VERSION
        or not isinstance(version, str)
        or not re.fullmatch(r"[0-9A-Za-z.+-]{1,64}", version)
        or not isinstance(version_info, list)
        or len(version_info) != 3
        or any(
            not isinstance(item, int) or isinstance(item, bool)
            for item in version_info
        )
    ):
        return failed
    return {
        "inspection_succeeded": True,
        "exists": True,
        "executable": bounded_path,
        "implementation": implementation,
        "version": version,
        "version_info": version_info,
        "is_exact_cpython_3_14": (
            implementation == "CPython" and version_info[:2] == [3, 14]
        ),
    }


def inspect_default_docker_context() -> dict[str, Any]:
    """Return only the bounded name and endpoint, never context config data."""
    result = run(
        [
            "docker", "context", "inspect", "default", "--format",
            "{{json .Name}}\t{{json .Endpoints.docker.Host}}",
        ]
    )
    failed = {
        "inspection_succeeded": False,
        "name": None,
        "docker_endpoint": None,
    }
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 1:
        return failed
    raw_name, separator, raw_endpoint = lines[0].partition("\t")
    if not separator:
        return failed
    try:
        name = json.loads(raw_name)
        endpoint = json.loads(raw_endpoint)
    except json.JSONDecodeError:
        return failed
    endpoint = bounded_docker_endpoint(endpoint)
    if name != "default" or endpoint is None:
        return failed
    return {
        "inspection_succeeded": True,
        "name": name,
        "docker_endpoint": endpoint,
    }


def loopback_origin_ownership(
    containers: list[dict[str, Any]], *, inspection_succeeded: bool,
) -> dict[str, Any]:
    """Derive bounded exact-loopback bindings from sanitized Docker port data."""
    ports = {
        "58080": {"bind_address": "127.0.0.1", "owners": [], "bindings": []},
        "58081": {"bind_address": "127.0.0.1", "owners": [], "bindings": []},
    }
    complete = inspection_succeeded
    pattern = re.compile(
        r"(?:^|,\s*)127\.0\.0\.1:(58080|58081)->([0-9]{1,5})/(tcp|udp)(?=,|$)"
    )
    for item in containers:
        name = item.get("Names")
        published = item.get("Ports")
        state = item.get("State")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name)
            or not isinstance(state, str)
        ):
            complete = False
            continue
        if state.lower() != "running":
            continue
        if published is None:
            published = ""
        if not isinstance(published, str) or len(published) > 4096:
            complete = False
            continue
        for match in pattern.finditer(published):
            host_port, container_port, protocol = match.groups()
            target_port = int(container_port)
            if not 1 <= target_port <= 65535:
                complete = False
                continue
            binding = {
                "container": name,
                "container_port": target_port,
                "protocol": protocol,
            }
            if binding not in ports[host_port]["bindings"]:
                ports[host_port]["bindings"].append(binding)
    for value in ports.values():
        value["bindings"].sort(
            key=lambda item: (
                item["container"], item["container_port"], item["protocol"]
            )
        )
        value["owners"] = sorted(
            {item["container"] for item in value["bindings"]}
        )
    return {
        "inspection_succeeded": complete,
        "source": "docker_ps_ports",
        "ports": ports,
    }


def host_capacity() -> dict[str, Any]:
    memory: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as memory_file:
            for line in memory_file:
                key, separator, value = line.partition(":")
                if separator and key in {"MemTotal", "MemAvailable", "SwapTotal"}:
                    fields = value.split()
                    if fields and fields[0].isdigit():
                        memory[key] = int(fields[0])
    except OSError:
        pass
    try:
        filesystem = os.statvfs("/")
        root_available = filesystem.f_bavail * filesystem.f_frsize
    except OSError:
        root_available = None
    return {
        "logical_cpus": os.cpu_count(),
        "memory_total_kib": memory.get("MemTotal"),
        "memory_available_kib": memory.get("MemAvailable"),
        "swap_total_kib": memory.get("SwapTotal"),
        "root_available_bytes": root_available,
    }


def inspect_container_networks(name: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
        return None
    result = run(
        [
            "docker", "inspect", "--format",
            "{{json .NetworkSettings.Networks}}", name,
        ]
    )
    try:
        value = json.loads(result.stdout) if result.returncode == 0 else None
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    # Docker's network attachment object contains no container environment.
    return {
        network: {
            "aliases": sorted(
                alias for alias in (detail.get("Aliases") or [])
                if isinstance(alias, str) and len(alias) <= 128
            ),
            "ip_address": detail.get("IPAddress") if isinstance(detail.get("IPAddress"), str) else None,
        }
        for network, detail in sorted(value.items())
        if isinstance(network, str) and isinstance(detail, dict)
    }


def parse_ledger(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "inspection_succeeded": False,
        "query_read_only": False,
        "database_identity": None,
        "entries": [],
        "ledger_rows_sha256": None,
    }
    if result.returncode != 0:
        return value
    try:
        observed = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return value
    if not isinstance(observed, dict) or set(observed) != {
        "database_name", "server_address", "server_port",
        "transaction_read_only", "migrations",
    }:
        return value
    entries = observed["migrations"]
    if (
        not isinstance(entries, list)
        or not entries
        or any(
            not isinstance(item, dict)
            or set(item) != {"filename", "checksum_sha256"}
            or not re.fullmatch(r"[0-9]{3}_[a-z0-9_]+\.sql", str(item["filename"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["checksum_sha256"]))
            for item in entries
        )
    ):
        return value
    identity = {
        "database_name": observed["database_name"],
        "server_address": observed["server_address"],
        "server_port": observed["server_port"],
    }
    value["query_read_only"] = observed["transaction_read_only"] == "on"
    if not value["query_read_only"]:
        return value
    if entries != sorted(entries, key=lambda item: item["filename"]):
        return value
    if len({item["filename"] for item in entries}) != len(entries):
        return value
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    value.update(
        inspection_succeeded=True,
        database_identity=identity,
        entries=entries,
        ledger_rows_sha256="sha256:" + hashlib.sha256(canonical).hexdigest(),
    )
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def get(url: str) -> tuple[dict[str, Any], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "edfinder-v3-production-inventory/1"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read(MAX_BODY + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BODY + 1)
        status = exc.code
    except (OSError, urllib.error.URLError, TimeoutError):
        return {
            "inspection_succeeded": False,
            "status_code": None,
            "body_bytes": 0,
            "body_sha256": None,
        }, b""
    bounded = len(body) <= MAX_BODY
    return {
        "inspection_succeeded": bounded,
        "status_code": status,
        "body_bytes": len(body[:MAX_BODY]),
        "body_sha256": hashlib.sha256(body[:MAX_BODY]).hexdigest(),
        "redirects_followed": False,
    }, body[:MAX_BODY]


def health_shape(body: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    allowed: dict[str, Any] = {}
    for key in ("status", "database", "version", "build_sha"):
        item = value.get(key)
        if isinstance(item, str) and len(item) <= 128:
            allowed[key] = item
    return allowed if set(allowed) == {"status", "database", "version", "build_sha"} else None


def main() -> int:
    receipt: dict[str, Any] = {
        "schema_version": "ed-finder/v3-production-inventory/v1",
        "operation": "v3-production-inventory",
        "status": "stopped",
        "target": {"production": True, "hostname": EXPECTED_HOST, "fqdn": EXPECTED_FQDN},
        "read_only": True,
        "direct_db_access_performed": False,
        "db_writes_performed": False,
        "migrations_performed": False,
        "application_data_writes_performed": False,
        "env_files_read": False,
        "container_environment_read": False,
        "private_keys_read": False,
        "service_changes_performed": False,
        "filesystem_writes_performed": False,
    }
    failures: list[str] = []
    host = socket.gethostname().split(".")[0]
    fqdn_result = run(["hostname", "-f"])
    fqdn = fqdn_result.stdout.strip()
    receipt["observed_host"] = {"hostname": host, "fqdn": fqdn}
    if host != EXPECTED_HOST or fqdn_result.returncode != 0 or fqdn != EXPECTED_FQDN:
        receipt["failures"] = ["unexpected_production_host_identity"]
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 78
    receipt["host_runtime"] = {
        "inventory_python": inventory_runtime(),
        "python3_14": inspect_python314_runtime(),
    }
    if not receipt["host_runtime"]["inventory_python"]["inspection_succeeded"]:
        failures.append("inventory_python_runtime_inspection_failed")
    if not receipt["host_runtime"]["python3_14"]["inspection_succeeded"]:
        failures.append("python314_runtime_inspection_failed")
    receipt["capacity"] = host_capacity()
    receipt["docker_context"] = inspect_default_docker_context()
    if not receipt["docker_context"]["inspection_succeeded"]:
        failures.append("default_docker_context_inventory_failed")

    docker_ok, containers = docker_json_lines(
        ["docker", "ps", "--all", "--no-trunc", "--format", "{{json .}}"]
    )
    containers_complete = docker_ok
    if len(containers) > MAX_CONTAINERS:
        containers = containers[:MAX_CONTAINERS]
        containers_complete = False
        failures.append("container_inventory_truncated")
    if not docker_ok:
        failures.append("container_inventory_failed")
    containers = [sanitize_container(item) for item in containers]
    for item in containers:
        name = item.get("Names")
        item["NetworksDetail"] = inspect_container_networks(name) if isinstance(name, str) else None
    receipt["containers"] = {"inspection_succeeded": docker_ok, "items": containers, "limit": MAX_CONTAINERS}
    receipt["loopback_origin_port_ownership"] = loopback_origin_ownership(
        containers, inspection_succeeded=containers_complete
    )
    if not receipt["loopback_origin_port_ownership"]["inspection_succeeded"]:
        failures.append("loopback_origin_ownership_derivation_failed")
    required_containers = {
        "edfinder-v3-api", "edfinder-v3-proxy", "edfinder-v3-public-auth-edge",
        POSTGRES_CONTAINER, "edfinder-v3-support-redis", "edfinder-v3-support-nats",
    }
    present_names = {str(item.get("Names")) for item in containers}
    missing_required = sorted(required_containers - present_names)
    receipt["containers"]["missing_required"] = missing_required
    if missing_required:
        failures.append("required_production_container_missing")
    if not any(name.startswith("octopus-") for name in present_names):
        failures.append("octopus_container_inventory_missing")

    network_ok, networks = docker_json_lines(
        ["docker", "network", "ls", "--no-trunc", "--format", "{{json .}}"]
    )
    if len(networks) > MAX_CONTAINERS:
        failures.append("network_inventory_truncated")
    receipt["networks"] = {
        "inspection_succeeded": network_ok,
        "items": [sanitize_network(item) for item in networks[:MAX_CONTAINERS]],
        "limit": MAX_CONTAINERS,
    }
    if not network_ok:
        failures.append("network_inventory_failed")

    listeners_result = run(["ss", "-H", "-lnt"])
    listeners = []
    if listeners_result.returncode == 0:
        for line in listeners_result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 4:
                listeners.append(fields[3][:256])
    if len(listeners) > MAX_LISTENERS:
        listeners = listeners[:MAX_LISTENERS]
        failures.append("listener_inventory_truncated")
    receipt["listeners"] = {"inspection_succeeded": listeners_result.returncode == 0, "items": listeners}
    if listeners_result.returncode != 0:
        failures.append("listener_inventory_failed")

    postgres = next((item for item in containers if item.get("Names") == POSTGRES_CONTAINER), None)
    if postgres is None or not str(postgres.get("State", "")).lower().startswith("running"):
        failures.append("retained_postgres_container_unavailable")
        receipt["database"] = {"inspection_succeeded": False, "entries": []}
    else:
        receipt["direct_db_access_performed"] = True
        ledger_result = run(
            [
                "docker", "exec", POSTGRES_CONTAINER,
                "psql", "-X", "--no-password", "--tuples-only", "--no-align", "--quiet",
                "--field-separator", "\t", "--set", "ON_ERROR_STOP=1",
                "--username", DB_USER, "--dbname", DB_NAME, "--command", LEDGER_SQL,
            ],
            timeout=20,
        )
        receipt["database"] = parse_ledger(ledger_result)
        if not receipt["database"]["inspection_succeeded"]:
            failures.append("production_migration_ledger_unavailable_or_invalid")

    origin_root, origin_root_body = get(ORIGIN + "/")
    origin_health, origin_health_body = get(ORIGIN + "/api/health")
    public_root, public_root_body = get(PUBLIC + "/")
    public_health, public_health_body = get(PUBLIC + "/api/health")
    receipt["http"] = {
        "origin_root": origin_root,
        "origin_health": origin_health,
        "public_root": public_root,
        "public_health": public_health,
    }
    api_container = next(
        (item for item in containers if item.get("Names") == "edfinder-v3-api"),
        None,
    )
    receipt["current_release"] = {
        "api_container": api_container,
        "origin_health": health_shape(origin_health_body),
        "public_health": health_shape(public_health_body),
        "origin_temporary_shell": b"replacement ED-Finder backend is online" in origin_root_body,
        "public_temporary_shell": b"replacement ED-Finder backend is online" in public_root_body,
    }
    for label, item, shape in (
        ("origin_root", origin_root, True),
        ("origin_health", origin_health, health_shape(origin_health_body) is not None),
        ("public_root", public_root, True),
        ("public_health", public_health, health_shape(public_health_body) is not None),
    ):
        status_code = item.get("status_code")
        if (
            not item.get("inspection_succeeded")
            or not isinstance(status_code, int)
            or not 200 <= status_code < 300
            or not shape
        ):
            failures.append(f"{label}_inventory_failed")
    receipt["failures"] = sorted(set(failures))
    receipt["status"] = "success" if not failures else "stopped"
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if not failures else 78


if __name__ == "__main__":
    raise SystemExit(main())
