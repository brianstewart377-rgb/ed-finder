#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"octopus-edge-topology","status":"stopped","read_only":true,"db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false,"failures":["python3_unavailable"]}'
    exit 1
fi

exec python3 - <<'PY'
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
PUBLIC_NAME = "octopus.ed-finder.app"
CONTAINERS = (
    "edfinder-v3-public-auth-edge",
    "edfinder-v3-proxy",
    "octopus-web-1",
)
EDGE_CONTAINERS = CONTAINERS[:2]
MAX_RESPONSE = 4096


def run(argv, *, timeout=15):
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def docker_format(name, template):
    result = run(["docker", "inspect", "--format", template, name])
    return result.returncode == 0, result.stdout.strip()


def json_value(name, template, default):
    ok, text = docker_format(name, template)
    if not ok:
        return False, default
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        return False, default


def safe_labels(name):
    keys = (
        "com.docker.compose.project",
        "com.docker.compose.service",
        "com.docker.compose.project.working_dir",
        "com.docker.compose.project.config_files",
    )
    labels = {}
    all_ok = True
    for key in keys:
        ok, value = docker_format(name, '{{index .Config.Labels "' + key + '"}}')
        all_ok = all_ok and ok
        labels[key] = value if ok and value != "<no value>" else None
    return all_ok, labels


def sanitize_mounts(mounts):
    return [
        {
            "type": item.get("Type"),
            "source": item.get("Source"),
            "destination": item.get("Destination"),
            "rw": bool(item.get("RW")),
        }
        for item in mounts
        if isinstance(item, dict)
    ]


def sanitize_networks(networks):
    if not isinstance(networks, dict):
        return {}
    result = {}
    for name, item in networks.items():
        if not isinstance(item, dict):
            continue
        result[name] = {
            "ip_address": item.get("IPAddress"),
            "gateway": item.get("Gateway"),
            "aliases": sorted(str(value) for value in (item.get("Aliases") or []) if value),
        }
    return result


def nginx_inventory(name):
    result = run(["docker", "exec", name, "nginx", "-T"])
    item = {"inspection_succeeded": result.returncode == 0, "directives": []}
    if result.returncode:
        return item
    directives = []
    allowed_semicolon = re.compile(
        r"^(listen|server_name|set|resolver|proxy_pass|proxy_set_header|auth_request|auth_basic|auth_basic_user_file|error_page|return)\b"
    )
    allowed_block = re.compile(r"^(server|location)\b.*\{")
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if allowed_block.match(line) or (line.endswith(";") and allowed_semicolon.match(line)):
            # Do not emit cookie/header values that could contain credentials. Only configuration text is kept.
            if re.search(r"(?i)(password|secret|token|private[_-]?key)\s+[^$]", line):
                continue
            directives.append(line[:500])
    item["directives"] = directives[:250]
    item["truncated"] = len(directives) > 250
    return item


def curl_summary(url, *, host_header=None):
    argv = [
        "curl", "--silent", "--show-error", "--max-time", "10", "--max-filesize", str(MAX_RESPONSE),
        "--dump-header", "-", "--output", "-",
    ]
    if host_header:
        argv += ["--header", "Host: " + host_header]
    result = run(argv + [url], timeout=12)
    raw = result.stdout[: MAX_RESPONSE * 2]
    # curl with --dump-header - and --output - emits headers followed by body.
    parts = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    header_text = parts[0] if parts else ""
    body = parts[1] if len(parts) > 1 else ""
    status_match = re.search(r"^HTTP/\S+\s+(\d{3})", header_text, re.M)
    headers = {}
    for line in header_text.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in {"server", "content-type", "location", "www-authenticate", "cf-cache-status"}:
            headers[key] = value[:300]
    title = None
    match = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    if match:
        title = re.sub(r"\s+", " ", match.group(1)).strip()[:200]
    return {
        "inspection_succeeded": result.returncode == 0,
        "status_code": int(status_match.group(1)) if status_match else None,
        "headers": headers,
        "body_bytes": len(body.encode("utf-8")),
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else None,
        "title": title,
    }


def auth_file_metadata():
    path = Path("/opt/octopus/ui.htpasswd")
    try:
        info = path.stat()
    except OSError:
        return {"exists": False, "is_regular": False, "nonempty": False, "size_bytes": None, "mode": None}
    return {
        "exists": True,
        "is_regular": stat.S_ISREG(info.st_mode),
        "nonempty": info.st_size > 0,
        "size_bytes": info.st_size,
        "mode": oct(stat.S_IMODE(info.st_mode)),
    }


receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "octopus-edge-topology",
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
fqdn = fqdn_result.stdout.strip()
receipt["host"] = {"short": host, "fqdn": fqdn}
if host != EXPECTED_HOST or fqdn_result.returncode or fqdn != EXPECTED_FQDN:
    failures.append("unexpected_host_identity")
if run(["pwd", "-P"]).stdout.strip() != "/opt/ed-finder":
    failures.append("unexpected_working_directory")
if failures:
    receipt["failures"] = failures
    print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
    sys.exit(1)

containers = {}
for name in CONTAINERS:
    ok_mode, network_mode = docker_format(name, "{{.HostConfig.NetworkMode}}")
    ok_networks, networks = json_value(name, "{{json .NetworkSettings.Networks}}", {})
    ok_ports, ports = json_value(name, "{{json .NetworkSettings.Ports}}", {})
    ok_mounts, mounts = json_value(name, "{{json .Mounts}}", [])
    ok_labels, labels = safe_labels(name)
    exists = all((ok_mode, ok_networks, ok_ports, ok_mounts, ok_labels))
    containers[name] = {
        "inspection_succeeded": exists,
        "network_mode": network_mode if ok_mode else None,
        "networks": sanitize_networks(networks),
        "ports": ports if isinstance(ports, dict) else {},
        "mounts": sanitize_mounts(mounts),
        "compose": labels,
    }
    if not exists:
        failures.append("container_topology_inspection_failed:" + name)
receipt["containers"] = containers

edge_networks = set()
for name in EDGE_CONTAINERS:
    edge_networks.update(containers.get(name, {}).get("networks", {}).keys())
octopus_networks = set(containers.get("octopus-web-1", {}).get("networks", {}).keys())
receipt["network_relationships"] = {
    "edge_networks": sorted(edge_networks),
    "octopus_web_networks": sorted(octopus_networks),
    "shared_networks": sorted(edge_networks & octopus_networks),
    "host_network_edges": sorted(
        name for name in EDGE_CONTAINERS if containers.get(name, {}).get("network_mode") == "host"
    ),
}

nginx = {name: nginx_inventory(name) for name in EDGE_CONTAINERS}
receipt["nginx"] = nginx
for name, item in nginx.items():
    if not item["inspection_succeeded"]:
        failures.append("nginx_inventory_failed:" + name)

listeners = run(["ss", "-H", "-lnt"])
listener_ports = set()
if listeners.returncode == 0:
    for line in listeners.stdout.splitlines():
        match = re.search(r"\s(?:\[[^]]+\]|[^\s]+):(\d+)\s", line + " ")
        if match:
            listener_ports.add(int(match.group(1)))
receipt["listeners"] = {
    "inspection_succeeded": listeners.returncode == 0,
    "ports": {str(port): port in listener_ports for port in (80, 443, 43300, 58080)},
}
if listeners.returncode:
    failures.append("listener_inventory_failed")

receipt["octopus_auth_file"] = auth_file_metadata()
receipt["http_paths"] = {
    "public_cloudflare": curl_summary("https://" + PUBLIC_NAME + "/"),
    "host_port_80_with_octopus_host": curl_summary("http://127.0.0.1/", host_header=PUBLIC_NAME),
    "host_port_58080_with_octopus_host": curl_summary("http://127.0.0.1:58080/", host_header=PUBLIC_NAME),
    "octopus_loopback": curl_summary("http://127.0.0.1:43300/"),
}

receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
sys.exit(0 if not failures else 1)
PY
