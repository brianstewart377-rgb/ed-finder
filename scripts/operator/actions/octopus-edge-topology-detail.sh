#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 0 ]; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"octopus-edge-topology-detail","status":"stopped","read_only":true,"db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false,"failures":["caller_parameters_not_allowed"]}'
    exit 64
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"octopus-edge-topology-detail","status":"stopped","read_only":true,"db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false,"failures":["python3_unavailable"]}'
    exit 1
fi

# All remote inputs are constants. The program requests only allowlisted Docker
# metadata and reduces nginx -T output to origin paths and safe directives.
exec python3 - <<'PY'
import hashlib
import json
import re
import socket
import subprocess
import sys

OPERATION = "octopus-edge-topology-detail"
EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
EXPECTED_WORKDIR = "/opt/ed-finder"
EXPECTED_VERSION = "1.0.122"
EXPECTED_IMAGE = "nginx:1.28-alpine"
CONTAINERS = ("edfinder-v3-public-auth-edge", "edfinder-v3-proxy")
MAX_RESPONSE = 4096
MAX_NGINX_OUTPUT = 1024 * 1024
MAX_NGINX_ORIGINS = 128
MAX_NGINX_DIRECTIVES = 512
MAX_NGINX_FIELD = 2048
INSPECT_FORMAT = json.dumps({
    "name": "{{.Name}}",
    "image": "{{.Config.Image}}",
    "state": "{{.State.Status}}",
    "network_mode": "{{.HostConfig.NetworkMode}}",
    "networks": "{{json .NetworkSettings.Networks}}",
    "ports": "{{json .NetworkSettings.Ports}}",
    "mounts": "{{json .Mounts}}",
}, separators=(",", ":"))


def run(argv, *, timeout=15):
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def stopped_receipt(failures, **fields):
    receipt = {
        "schema_version": "ed-finder/operator-operation-result/v1",
        "operation": OPERATION,
        "status": "stopped",
        "read_only": True,
        "db_access_performed": False,
        "db_writes_performed": False,
        "env_files_read": False,
        "private_keys_read": False,
        "service_changes_performed": False,
        "filesystem_writes_performed": False,
        **fields,
        "failures": sorted(set(failures)),
    }
    return receipt


def exact_version(body):
    if len(body.encode("utf-8")) > MAX_RESPONSE:
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("version") == EXPECTED_VERSION


def bounded_get(url):
    result = run(["curl", "--silent", "--show-error", "--max-time", "10",
                  "--max-filesize", str(MAX_RESPONSE), "--output", "-",
                  "--write-out", "\n%{http_code}", url])
    body, separator, code = result.stdout.rpartition("\n")
    body = body[:MAX_RESPONSE]
    return ({
        "inspection_succeeded": result.returncode == 0 and bool(separator),
        "status_code": int(code) if separator and code.isdigit() else None,
        "body_bytes": len(body.encode("utf-8")),
        "body_sha256": hashlib.sha256(body.encode()).hexdigest() if separator else None,
    }, body)


def sanitized_nginx_metadata(config):
    if len(config.encode("utf-8")) > MAX_NGINX_OUTPUT:
        raise ValueError("nginx output exceeded limit")
    origins = []
    directives = []
    current_origin = None
    origin_pattern = re.compile(r"^# configuration file ([^:\r\n]+):$")
    directive_pattern = re.compile(
        r"^(listen|server_name|proxy_pass|include)\s+([^;\r\n]+);$"
    )
    for raw_line in config.splitlines():
        line = raw_line.strip()
        origin = origin_pattern.fullmatch(line)
        if origin:
            current_origin = origin.group(1)
            if len(current_origin) > MAX_NGINX_FIELD:
                raise ValueError("nginx origin exceeded limit")
            if current_origin not in origins:
                origins.append(current_origin)
                if len(origins) > MAX_NGINX_ORIGINS:
                    raise ValueError("too many nginx origins")
            continue
        directive = directive_pattern.fullmatch(line)
        if directive:
            if len(directive.group(2)) > MAX_NGINX_FIELD:
                raise ValueError("nginx directive exceeded limit")
            directives.append({
                "origin": current_origin,
                "name": directive.group(1),
                "value": directive.group(2),
            })
            if len(directives) > MAX_NGINX_DIRECTIVES:
                raise ValueError("too many nginx directives")
    return {"configuration_file_origins": origins, "directives": directives}


def decode_inspect(stdout, expected_name):
    raw = json.loads(stdout)
    networks = json.loads(raw["networks"] or "{}")
    ports = json.loads(raw["ports"] or "{}")
    mounts = json.loads(raw["mounts"] or "[]")
    if (raw["name"] != "/" + expected_name or raw["state"] != "running"
            or raw["image"] != EXPECTED_IMAGE):
        raise ValueError("unexpected container identity, state, or image")
    published_ports = {}
    for container_port, bindings in ports.items():
        if not isinstance(bindings, list):
            continue
        real_bindings = [
            {"HostIp": binding["HostIp"], "HostPort": binding["HostPort"]}
            for binding in bindings
            if (isinstance(binding, dict)
                and isinstance(binding.get("HostIp"), str)
                and isinstance(binding.get("HostPort"), str)
                and bool(binding["HostPort"]))
        ]
        if real_bindings:
            published_ports[container_port] = real_bindings
    return {
        "name": expected_name,
        "image": raw["image"],
        "network_mode": raw["network_mode"],
        "network_names": sorted(networks),
        "published_ports": published_ports,
        "mounts": [
            {"source": item.get("Source"), "destination": item.get("Destination"),
             "type": item.get("Type"), "rw": bool(item.get("RW"))}
            for item in mounts if item.get("Type") in {"bind", "volume"}
        ],
    }


def inspect_containers(names, runner=run):
    items = []
    failures = []
    for name in names:
        inspected = runner([
            "docker", "inspect", "--type", "container", "--format", INSPECT_FORMAT, name
        ])
        if inspected.returncode != 0:
            failures.append(f"container_missing:{name}")
            continue
        try:
            items.append(decode_inspect(inspected.stdout, name))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            failures.append(f"container_unexpected:{name}")
    return items, failures


def inspect_nginx(items, runner=run):
    failures = []
    for item in items:
        name = item["name"]
        nginx = runner(["docker", "exec", name, "nginx", "-T"])
        if nginx.returncode != 0:
            failures.append(f"nginx_inspection_failed:{name}")
            continue
        try:
            item["nginx"] = sanitized_nginx_metadata(nginx.stdout)
        except ValueError:
            failures.append(f"nginx_inspection_unbounded:{name}")
    return failures


def inspect_topology(names, runner=run):
    items, failures = inspect_containers(names, runner)
    if failures:
        return items, failures
    failures.extend(inspect_nginx(items, runner))
    return items, failures


failures = []
short_host = socket.gethostname().split(".")[0]
fqdn_result = run(["hostname", "-f"])
fqdn = fqdn_result.stdout.strip()
pwd_result = run(["pwd", "-P"])
workdir = pwd_result.stdout.strip()
identity = {"short": short_host, "fqdn": fqdn, "working_directory": workdir}
if short_host != EXPECTED_HOST or fqdn_result.returncode != 0 or fqdn != EXPECTED_FQDN:
    failures.append("unexpected_host_identity")
if pwd_result.returncode != 0 or workdir != EXPECTED_WORKDIR:
    failures.append("unexpected_working_directory")
if failures:
    print(json.dumps(stopped_receipt(failures, host=identity), separators=(",", ":"), sort_keys=True))
    sys.exit(1)

container_receipts, container_failures = inspect_topology(CONTAINERS)
failures.extend(container_failures)

health, _ = bounded_get("http://127.0.0.1:43300/api/health")
version, version_body = bounded_get("http://127.0.0.1:43300/api/version")
version["expected_version"] = EXPECTED_VERSION
version["exact_version_match"] = version["inspection_succeeded"] and exact_version(version_body)
if health["status_code"] not in range(200, 300):
    failures.append("octopus_health_failed")
if version["status_code"] not in range(200, 300):
    failures.append("octopus_version_http_failed")
if not version["exact_version_match"]:
    failures.append("unexpected_octopus_version")

receipt = stopped_receipt(
    failures,
    host=identity,
    expected_containers=list(CONTAINERS),
    containers=container_receipts,
    octopus_internal={"health": health, "version": version},
)
if not failures and [item["name"] for item in container_receipts] == list(CONTAINERS):
    receipt["status"] = "completed"
    receipt.pop("failures")
print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
sys.exit(0 if receipt["status"] == "completed" else 1)
PY
