#!/usr/bin/env bash
set -euo pipefail

# Keep the operation contract machine-readable even if the Python runtime is absent.
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"octopus-edge-status","status":"stopped","read_only":true,"db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false,"failures":["python3_unavailable"]}'
    exit 1
fi

# This action deliberately delegates all inspection to a fixed Python program:
# no caller-controlled command, path, hostname, or container name is accepted.
exec python3 - <<'PY'
import hashlib
import ipaddress
import json
import re
import socket
import subprocess
import sys

EXPECTED_HOST = "ed-finder"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
PUBLIC_NAME = "octopus.ed-finder.app"
EXPECTED_VERSION = "1.0.122"
MAX_RESPONSE = 4096


def run(argv, *, stdin=None, timeout=15):
    try:
        return subprocess.run(argv, input=stdin, text=True, capture_output=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def bounded_get(url, *, insecure=False):
    argv = ["curl", "--silent", "--show-error", "--location", "--max-time", "10",
            "--max-filesize", str(MAX_RESPONSE), "--output", "-",
            "--write-out", "\n%{http_code}"]
    if insecure:
        argv.append("--insecure")
    result = run(argv + [url])
    body, sep, code = result.stdout.rpartition("\n")
    bounded = body[:MAX_RESPONSE]
    return {
        "inspection_succeeded": result.returncode == 0 and bool(sep),
        "status_code": int(code) if sep and code.isdigit() else None,
        "body_bytes": len(bounded.encode("utf-8")),
        "body_sha256": hashlib.sha256(bounded.encode()).hexdigest() if sep else None,
    }, bounded


def version_matches(body):
    if len(body.encode("utf-8")) > MAX_RESPONSE:
        return False
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        value = body.strip()
    candidates = []
    if isinstance(value, str):
        candidates.append(value)
    elif isinstance(value, dict):
        candidates.extend(str(value.get(key, "")) for key in ("version", "release", "tag"))
    return any(re.search(r"(?:^|[^0-9])v?" + re.escape(EXPECTED_VERSION) + r"(?:$|[^0-9])", item)
               for item in candidates)


def host_identity_matches(short_host, fqdn, fqdn_returncode):
    return (short_host == EXPECTED_HOST and fqdn_returncode == 0 and
            fqdn == EXPECTED_FQDN)


def parse_proxy_servers(config):
    servers = []
    current = None
    depth = 0
    for raw in config.splitlines():
        line = raw.strip()
        if re.fullmatch(r"server\s*\{", line):
            if current is not None:
                return []  # ambiguous nested server block
            current = []
            depth = 1
            continue
        if current is None:
            continue
        depth += line.count("{") - line.count("}")
        match = re.fullmatch(r"(set\s+\$[A-Za-z_][A-Za-z0-9_]*\s+[^;\s]+|server_name\s+[^;]+|proxy_pass\s+[^;\s]+)\s*;", line)
        if match:
            current.append(match.group(1) + ";")
        if depth == 0:
            servers.append(current)
            current = None
    return servers if current is None else []


def route_present(servers):
    all_directives = []
    all_resolved = []
    found = False
    for directives in servers:
        all_directives.extend(directives)
        present, resolved = route_present_in_server(directives)
        all_resolved.extend(resolved)
        found = found or present
    return found, all_resolved[:20], all_directives[:100]


def route_present_in_server(directives):
    variables = {}
    proxy_targets = []
    names = []
    for directive in directives:
        if directive.startswith("set "):
            _, variable, value = directive[:-1].split(None, 2)
            variables[variable] = value
        elif directive.startswith("proxy_pass "):
            proxy_targets.append(directive[len("proxy_pass "):-1])
        elif directive.startswith("server_name "):
            names.extend(directive[len("server_name "):-1].split())
    resolved = [variables.get(target, target) for target in proxy_targets]
    target_ok = any(re.fullmatch(r"https?://octopus-web(?::3000)?(?:/.*)?", target) or
                    re.fullmatch(r"https?://(?:127\.0\.0\.1|localhost):43300(?:/.*)?", target)
                    for target in resolved)
    return PUBLIC_NAME in names and target_ok, resolved[:20]


receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "octopus-edge-status",
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
if not host_identity_matches(host, fqdn, fqdn_result.returncode):
    failures.append("unexpected_host_identity")
if run(["pwd", "-P"]).stdout.strip() != "/opt/ed-finder":
    failures.append("unexpected_working_directory")
if failures:
    receipt["failures"] = sorted(set(failures))
    print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
    sys.exit(1)

listeners_result = run(["ss", "-H", "-lnt"])
ports = set()
if listeners_result.returncode == 0:
    for line in listeners_result.stdout.splitlines():
        match = re.search(r"\s(?:\[[^]]+\]|[^\s]+):(\d+)\s", line + " ")
        if match:
            ports.add(int(match.group(1)))
receipt["listeners"] = {str(port): port in ports for port in (80, 443, 43300)}
receipt["listeners"].update({
    "inspection_succeeded": listeners_result.returncode == 0,
    "required_origin_ports": [80, 43300],
    "host_tls_listener_required": False,
    "tls_termination": "host" if 443 in ports else "external_or_container_edge",
})
if listeners_result.returncode:
    failures.append("listener_inspection_failed")
elif not all(port in ports for port in (80, 43300)):
    failures.append("required_listener_missing")

docker_result = run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
containers = []
if docker_result.returncode == 0:
    for line in docker_result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) == 3 and re.search(r"octopus|nginx|proxy", fields[0] + " " + fields[1], re.I):
            containers.append(dict(zip(("name", "image", "status"), fields)))
receipt["containers"] = {"inspection_succeeded": docker_result.returncode == 0,
                         "items": containers[:20], "truncated": len(containers) > 20}
if docker_result.returncode:
    failures.append("container_inspection_failed")

nginx_candidates = [item["name"] for item in containers
                    if re.search(r"nginx|proxy", item["name"] + " " + item["image"], re.I)]
proxy_items = []
route_found = False
all_inspected = bool(nginx_candidates)
for candidate in nginx_candidates:
    nginx_result = run(["docker", "exec", candidate, "nginx", "-T"])
    item = {
        "name": candidate,
        "inspection_succeeded": nginx_result.returncode == 0,
        "route_present": False,
        "directives": [],
        "resolved_proxy_targets": [],
    }
    if nginx_result.returncode:
        all_inspected = False
    else:
        servers = parse_proxy_servers(nginx_result.stdout)
        item["route_present"], item["resolved_proxy_targets"], item["directives"] = route_present(servers)
        route_found = route_found or item["route_present"]
    proxy_items.append(item)
proxy = {
    "inspection_succeeded": all_inspected,
    "candidate_count": len(nginx_candidates),
    "inspected_count": len(proxy_items),
    "route_present": route_found,
    "items": proxy_items,
    "multi_proxy_topology_supported": True,
}
if not nginx_candidates:
    failures.append("proxy_container_missing")
elif not all_inspected:
    failures.append("proxy_inspection_failed")
if nginx_candidates and all_inspected and not route_found:
    failures.append("octopus_route_missing")
receipt["proxy"] = proxy

health, _ = bounded_get("http://127.0.0.1:43300/api/health")
version, version_body = bounded_get("http://127.0.0.1:43300/api/version")
version["expected_release"] = EXPECTED_VERSION
version["expected_release_present"] = version_matches(version_body)
version["bounded_response"] = version_body[:MAX_RESPONSE]
receipt["octopus_internal"] = {"health": health, "version": version}
if health["status_code"] not in range(200, 400) or version["status_code"] not in range(200, 400):
    failures.append("octopus_internal_http_failed")
if not version["expected_release_present"]:
    failures.append("unexpected_octopus_version")

try:
    dns_values = sorted({str(ipaddress.ip_address(item[4][0])) for item in
                         socket.getaddrinfo(PUBLIC_NAME, 443, type=socket.SOCK_STREAM)})
    dns_ok = bool(dns_values)
except (OSError, ValueError):
    dns_values, dns_ok = [], False
receipt["dns"] = {"inspection_succeeded": dns_ok, "addresses": dns_values[:16]}
if not dns_ok:
    failures.append("dns_resolution_failed")

http, _ = bounded_get("http://" + PUBLIC_NAME + "/")
https, _ = bounded_get("https://" + PUBLIC_NAME + "/", insecure=True)
https["tls_verification_bypassed_for_response_only"] = True
receipt["public_http"] = {"http": http, "https": https}
if not http["inspection_succeeded"] or not https["inspection_succeeded"]:
    failures.append("public_http_inspection_failed")
elif http["status_code"] not in range(200, 400) or https["status_code"] not in range(200, 400):
    failures.append("public_http_status_failed")

served = {"inspection_succeeded": False, "certificate_present": False, "hostname_valid": False,
          "currently_valid": False, "served_certificate_valid": False, "names": [],
          "installed_certificate_availability": "not_inspected"}
handshake = run(["openssl", "s_client", "-connect", PUBLIC_NAME + ":443", "-servername", PUBLIC_NAME,
                 "-verify_hostname", PUBLIC_NAME, "-verify_return_error", "-showcerts"], stdin="", timeout=15)
cert_match = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", handshake.stdout, re.S)
if handshake.returncode != 0 or not cert_match:
    failures.append("served_certificate_fetch_failed")
else:
    cert = cert_match.group(0) + "\n"
    metadata = run(["openssl", "x509", "-noout", "-subject", "-issuer", "-dates", "-ext", "subjectAltName"], stdin=cert)
    hostname_check = run(["openssl", "x509", "-noout", "-checkhost", PUBLIC_NAME], stdin=cert)
    validity_check = run(["openssl", "x509", "-noout", "-checkend", "0"], stdin=cert)
    served["inspection_succeeded"] = metadata.returncode == 0
    served["certificate_present"] = metadata.returncode == 0
    served["hostname_valid"] = hostname_check.returncode == 0
    served["currently_valid"] = validity_check.returncode == 0
    served["served_certificate_valid"] = (
        handshake.returncode == 0 and served["certificate_present"] and
        served["hostname_valid"] and served["currently_valid"]
    )
    served["names"] = sorted(set(re.findall(r"DNS:([^,\s]+)", metadata.stdout)))[:50]
    dates = dict(re.findall(r"^(notBefore|notAfter)=(.*)$", metadata.stdout, re.M))
    served.update(dates)
    if not served["served_certificate_valid"]:
        failures.append("served_certificate_invalid")
receipt["served_certificate"] = served

receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
sys.exit(0 if not failures else 1)
PY
