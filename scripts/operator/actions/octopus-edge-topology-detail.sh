#!/usr/bin/env bash
set -euo pipefail

operation="octopus-edge-topology-detail"
stopped='{"schema_version":"ed-finder/operator-operation-result/v1","operation":"octopus-edge-topology-detail","status":"stopped","read_only":true,"db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'

if [ "$#" -ne 0 ]; then
    printf '%s\n' "${stopped%\}},\"failures\":[\"caller_parameters_forbidden\"]}"
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "${stopped%\}},\"failures\":[\"python3_unavailable\"]}"
    exit 1
fi

# Fixed program and targets only. In particular, never request the complete
# docker-inspect object: it includes container environment values.
exec python3 - <<'PY'
import json
import re
import socket
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
EXPECTED_DIRECTORY = "/opt/ed-finder"
EXPECTED_CONTAINERS = ("edfinder-v3-public-auth-edge", "edfinder-v3-proxy")
EXPECTED_VERSION = "1.0.122"
MAX_RESPONSE = 4096
MAX_DIRECTIVES = 200
MAX_NGINX_OUTPUT = 1024 * 1024


def run(argv, *, timeout=15):
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def docker_field(container, template):
    result = run(["docker", "inspect", "--type", "container", "--format", template, container])
    if result.returncode:
        raise RuntimeError("container_inspection_failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("container_inspection_invalid") from exc


def safe_path(value):
    return bool(re.fullmatch(r"/[A-Za-z0-9_./*?${}-]+", value)) and ".." not in value.split("/")


def sanitize_proxy_target(value):
    value = re.sub(r"(https?://)[^/@\s]+@", r"\1redacted@", value)
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[redacted-invalid-target]"
    if parsed.scheme in ("http", "https"):
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    if value.startswith("$") and re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", value):
        return value
    return "[redacted-unsupported-target]"


def parse_nginx_config(output):
    origin = None
    origins = []
    directives = []
    for raw in output.splitlines():
        marker = re.fullmatch(r"# configuration file (/.+):", raw.strip())
        if marker:
            candidate = marker.group(1)
            if not safe_path(candidate):
                raise ValueError("unsafe_nginx_origin")
            origin = candidate
            if candidate not in origins:
                origins.append(candidate)
            continue
        line = raw.strip()
        match = re.fullmatch(r"(server_name|proxy_pass|listen|include)\s+(.+?)\s*;", line)
        if not match:
            continue
        if origin is None:
            raise ValueError("directive_without_nginx_origin")
        name, value = match.groups()
        if name == "proxy_pass":
            value = sanitize_proxy_target(value)
        elif name == "include":
            if not safe_path(value):
                value = "[redacted-unsafe-path]"
        else:
            value = re.sub(r"[^A-Za-z0-9_.: *$\[\]=-]", "?", value)[:512]
        directives.append({"origin": origin, "directive": name, "value": value})
        if len(directives) > MAX_DIRECTIVES:
            raise ValueError("too_many_nginx_directives")
    if not origins:
        raise ValueError("nginx_origins_missing")
    return origins, directives


def bounded_get(path):
    result = run([
        "curl", "--silent", "--show-error", "--max-time", "10",
        "--max-filesize", str(MAX_RESPONSE), "--output", "-",
        "--write-out", "\n%{http_code}", "http://127.0.0.1:43300" + path,
    ])
    body, separator, code = result.stdout.rpartition("\n")
    return result.returncode == 0 and bool(separator), int(code) if separator and code.isdigit() else None, body


def exact_version(body):
    if len(body.encode("utf-8")) > MAX_RESPONSE:
        return False
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        value = body.strip()
    candidates = [value] if isinstance(value, str) else []
    if isinstance(value, dict):
        candidates.extend(value.get(key) for key in ("version", "release", "tag"))
    return any(isinstance(item, str) and item.removeprefix("v") == EXPECTED_VERSION for item in candidates)


receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "octopus-edge-topology-detail",
    "status": "stopped",
    "read_only": True,
    "db_access_performed": False,
    "db_writes_performed": False,
    "env_files_read": False,
    "private_keys_read": False,
    "service_changes_performed": False,
    "filesystem_writes_performed": False,
}
failures = []
host = socket.gethostname().split(".")[0]
fqdn_result = run(["hostname", "-f"])
directory_result = run(["pwd", "-P"])
receipt["host"] = {"short": host, "fqdn": fqdn_result.stdout.strip()}
if host != EXPECTED_HOST or fqdn_result.returncode or fqdn_result.stdout.strip() != EXPECTED_FQDN:
    failures.append("unexpected_host_identity")
if directory_result.returncode or directory_result.stdout.strip() != EXPECTED_DIRECTORY:
    failures.append("unexpected_working_directory")
if failures:
    receipt["failures"] = sorted(set(failures))
    print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
    sys.exit(1)

containers = []
for name in EXPECTED_CONTAINERS:
    running = run(["docker", "ps", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"])
    if running.returncode or running.stdout.splitlines() != [name]:
        failures.append("missing_or_unexpected_container:" + name)
        continue
    try:
        image = docker_field(name, "{{json .Config.Image}}")
        network_mode = docker_field(name, "{{json .HostConfig.NetworkMode}}")
        networks = docker_field(name, "{{json .NetworkSettings.Networks}}")
        network_names = list(networks)
        ports_raw = docker_field(name, "{{json .NetworkSettings.Ports}}") or {}
        published_ports = []
        for container_port, bindings in sorted(ports_raw.items()):
            for binding in bindings or []:
                published_ports.append({"container_port": container_port,
                                        "host_ip": binding.get("HostIp"),
                                        "host_port": binding.get("HostPort")})
        mounts_raw = docker_field(name, "{{json .Mounts}}")
        mounts = [{"source": item.get("Source"), "destination": item.get("Destination"),
                   "type": item.get("Type"), "rw": bool(item.get("RW"))} for item in mounts_raw]
        nginx = run(["docker", "exec", name, "nginx", "-T"])
        if nginx.returncode:
            raise RuntimeError("nginx_inspection_failed")
        if len(nginx.stdout.encode("utf-8")) > MAX_NGINX_OUTPUT:
            raise RuntimeError("nginx_inspection_too_large")
        origins, directives = parse_nginx_config(nginx.stdout)
        containers.append({"name": name, "image": image, "network_mode": network_mode,
                           "network_names": sorted(network_names), "published_ports": published_ports,
                           "mounts": mounts, "nginx_config_origins": origins,
                           "nginx_directives": directives})
    except (RuntimeError, TypeError, ValueError) as exc:
        failures.append(str(exc) + ":" + name)

receipt["containers"] = containers
health_inspected, health_code, _ = bounded_get("/api/health")
version_inspected, version_code, version_body = bounded_get("/api/version")
health_success = health_inspected and health_code is not None and 200 <= health_code < 300
version_success = version_inspected and version_code is not None and 200 <= version_code < 300
version_exact = exact_version(version_body)
receipt["octopus_internal"] = {
    "health": {"inspection_succeeded": health_inspected, "status_code": health_code,
               "success": health_success},
    "version": {"inspection_succeeded": version_inspected, "status_code": version_code,
                "success": version_success, "expected_version": EXPECTED_VERSION,
                "exact_version_match": version_exact},
}
if not health_success or not version_success:
    failures.append("octopus_internal_http_failed")
if not version_exact:
    failures.append("unexpected_octopus_version")
if len(containers) != len(EXPECTED_CONTAINERS):
    failures.append("topology_inspection_incomplete")

receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
sys.exit(0 if not failures else 1)
PY
