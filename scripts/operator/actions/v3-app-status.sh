#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-app-status","status":"stopped","failures":["python3_unavailable"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"oauth_login_started":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi

exec python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
ORIGIN = "http://127.0.0.1:58080"
PUBLIC = "https://ed-finder.app"
API_CONTAINER = "edfinder-v3-api"
HOST_FRONTEND_INDEX = Path("/opt/ed-finder/frontend/dist/index.html")
MAX_BODY = 65536


def run(argv, *, timeout=15):
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def get(url, *, body=True):
    argv = [
        "curl", "--silent", "--show-error", "--location", "--max-time", "10",
        "--output", "-" if body else "/dev/null", "--write-out", "\n%{http_code}", url,
    ]
    result = run(argv)
    if body:
        payload, sep, raw_code = result.stdout.rpartition("\n")
        encoded = payload.encode("utf-8")[:MAX_BODY]
        bounded = encoded.decode("utf-8", errors="replace")
    else:
        _, sep, raw_code = result.stdout.rpartition("\n")
        bounded = ""
    return {
        "inspection_succeeded": result.returncode == 0 and bool(sep),
        "status_code": int(raw_code) if sep and raw_code.isdigit() else None,
        "body_bytes": len(bounded.encode("utf-8")),
        "body_sha256": hashlib.sha256(bounded.encode()).hexdigest() if body and sep else None,
    }, bounded


def ok_http(item):
    code = item.get("status_code")
    return item.get("inspection_succeeded") and isinstance(code, int) and 200 <= code < 400


def classify_index_bytes(payload: bytes, *, full_size: int) -> dict[str, object]:
    prefix = payload[:MAX_BODY]
    return {
        "index_present": True,
        "index_bytes": full_size,
        "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
        "temporary_shell": b"replacement ED-Finder backend is online" in prefix,
        "vite_bundle_marker": b"/assets/" in prefix or b'type="module"' in prefix,
    }


receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-app-status",
    "status": "stopped",
    "read_only": True,
    "direct_db_access_performed": False,
    "application_health_may_read_db": True,
    "db_writes_performed": False,
    "oauth_login_started": False,
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
if host != EXPECTED_HOST or fqdn_result.returncode != 0 or fqdn != EXPECTED_FQDN:
    failures.append("unexpected_host_identity")
if run(["pwd", "-P"]).stdout.strip() != "/opt/ed-finder":
    failures.append("unexpected_working_directory")
if failures:
    receipt["failures"] = sorted(set(failures))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    sys.exit(1)

head_result = run(["git", "rev-parse", "HEAD"])
branch_result = run(["git", "branch", "--show-current"])
dirty_result = run(["git", "status", "--porcelain", "--untracked-files=no"])
receipt["repo"] = {
    "inspection_succeeded": head_result.returncode == branch_result.returncode == dirty_result.returncode == 0,
    "head": head_result.stdout.strip() if head_result.returncode == 0 else None,
    "branch": branch_result.stdout.strip() if branch_result.returncode == 0 else None,
    "tracked_changes_present": bool(dirty_result.stdout.strip()) if dirty_result.returncode == 0 else None,
}

listeners_result = run(["ss", "-H", "-lnt"])
listener_text = listeners_result.stdout
receipt["listeners"] = {
    "inspection_succeeded": listeners_result.returncode == 0,
    "80": ":80 " in listener_text or ":80\n" in listener_text,
    "58080": ":58080 " in listener_text or ":58080\n" in listener_text,
}
if listeners_result.returncode != 0:
    failures.append("listener_inspection_failed")
elif not receipt["listeners"]["58080"]:
    failures.append("v3_origin_listener_missing")

containers_result = run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
wanted = {
    "edfinder-v3-api",
    "edfinder-v3-proxy",
    "edfinder-v3-public-auth-edge",
    "edfinder-v3-support-redis",
    "edfinder-v3-support-nats",
    "edfinder-v3-phase4c-full-20260827_r5-postgres",
}
containers = []
if containers_result.returncode == 0:
    for line in containers_result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) == 3 and fields[0] in wanted:
            containers.append(dict(zip(("name", "image", "status"), fields)))
receipt["containers"] = {"inspection_succeeded": containers_result.returncode == 0, "items": containers}
present = {item["name"] for item in containers}
missing = sorted(wanted - present)
if containers_result.returncode != 0:
    failures.append("container_inspection_failed")
elif missing:
    failures.append("required_v3_container_missing")
receipt["containers"]["missing"] = missing

host_frontend = {
    "inspection_succeeded": True,
    "index_present": HOST_FRONTEND_INDEX.is_file(),
    "index_bytes": None,
    "prefix_sha256": None,
    "temporary_shell": None,
    "vite_bundle_marker": None,
}
if HOST_FRONTEND_INDEX.is_file():
    try:
        host_payload = HOST_FRONTEND_INDEX.read_bytes()
        host_frontend.update(classify_index_bytes(host_payload, full_size=len(host_payload)))
    except OSError:
        host_frontend["inspection_succeeded"] = False
receipt["host_frontend"] = host_frontend

index_result = run([
    "docker", "exec", API_CONTAINER, "python", "-c",
    "from pathlib import Path; p=Path('/app/frontend/index.html'); "
    "b=p.read_bytes() if p.is_file() else b''; "
    "print(len(b) if p.is_file() else -1); "
    "print(__import__('hashlib').sha256(b[:65536]).hexdigest() if b else ''); "
    "print('temporary_shell=' + str(b'replacement ED-Finder backend is online' in b[:65536]).lower()); "
    "print('vite_bundle=' + str(b'/assets/' in b[:65536] or b'type=\"module\"' in b[:65536]).lower())"
])
frontend = {
    "inspection_succeeded": index_result.returncode == 0,
    "index_present": False,
    "index_bytes": None,
    "prefix_sha256": None,
    "temporary_shell": None,
    "vite_bundle_marker": None,
}
if index_result.returncode == 0:
    lines = index_result.stdout.splitlines()
    if len(lines) >= 4:
        try:
            size = int(lines[0])
        except ValueError:
            size = -1
        frontend.update({
            "index_present": size >= 0,
            "index_bytes": size if size >= 0 else None,
            "prefix_sha256": lines[1] or None,
            "temporary_shell": lines[2].strip() == "temporary_shell=true",
            "vite_bundle_marker": lines[3].strip() == "vite_bundle=true",
        })
receipt["frontend"] = frontend
if not frontend["inspection_succeeded"] or not frontend["index_present"]:
    failures.append("frontend_index_inspection_failed")
receipt["frontend_comparison"] = {
    "host_bundle_available": bool(host_frontend["index_present"]),
    "host_matches_running": bool(
        host_frontend["prefix_sha256"]
        and frontend["prefix_sha256"]
        and host_frontend["prefix_sha256"] == frontend["prefix_sha256"]
    ),
}

origin_root, _ = get(ORIGIN + "/", body=False)
origin_health, health_body = get(ORIGIN + "/api/health")
origin_session, session_body = get(ORIGIN + "/api/auth/session")
origin_openapi, openapi_body = get(ORIGIN + "/openapi.json")

health_shape = None
try:
    health_shape = json.loads(health_body)
except json.JSONDecodeError:
    pass
session_shape = None
try:
    parsed_session = json.loads(session_body)
    if isinstance(parsed_session, dict):
        session_shape = {
            "authenticated": bool(parsed_session.get("authenticated")),
            "owner_claim_available": bool(parsed_session.get("owner_claim_available")),
            "has_user": parsed_session.get("user") is not None,
        }
except json.JSONDecodeError:
    pass
required_oauth_paths = {
    "/api/auth/frontier/login",
    "/api/auth/frontier/callback",
    "/api/auth/session",
    "/api/auth/logout",
    "/api/auth/owner/claim",
}
openapi_paths = set()
try:
    parsed_openapi = json.loads(openapi_body)
    if isinstance(parsed_openapi, dict) and isinstance(parsed_openapi.get("paths"), dict):
        openapi_paths = set(parsed_openapi["paths"])
except json.JSONDecodeError:
    pass

receipt["origin"] = {
    "root": origin_root,
    "health": origin_health,
    "health_response": health_shape if isinstance(health_shape, dict) else None,
    "session": origin_session,
    "session_response": session_shape,
    "openapi": origin_openapi,
    "oauth_paths_present": sorted(required_oauth_paths & openapi_paths),
    "oauth_paths_missing": sorted(required_oauth_paths - openapi_paths),
}
for label, item in (("root", origin_root), ("health", origin_health), ("session", origin_session), ("openapi", origin_openapi)):
    if not ok_http(item):
        failures.append(f"origin_{label}_failed")
if required_oauth_paths - openapi_paths:
    failures.append("oauth_routes_missing")

public_root, _ = get(PUBLIC + "/", body=False)
public_health, _ = get(PUBLIC + "/api/health", body=False)
public_session, _ = get(PUBLIC + "/api/auth/session", body=False)
receipt["public"] = {"root": public_root, "health": public_health, "session": public_session}
for label, item in (("root", public_root), ("health", public_health), ("session", public_session)):
    if not ok_http(item):
        failures.append(f"public_{label}_failed")

receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
sys.exit(0 if not failures else 1)
PY
