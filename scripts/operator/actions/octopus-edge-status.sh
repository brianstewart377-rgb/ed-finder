#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="ed-finder-prod"
EXPECTED_FQDN="nb79a3d.mevnode.com"
OCTOPUS_HOST="octopus.ed-finder.app"
OCTOPUS_UPSTREAM="127.0.0.1:43300"

stop() {
  python3 - "$1" <<'PY' >&2
import json, sys
print(json.dumps({
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "octopus-edge-status",
    "status": "stopped",
    "reason": sys.argv[1],
    "read_only": True,
    "db_access_performed": False,
}, separators=(",", ":")))
PY
  exit 1
}

[ "$(hostname -s)" = "$EXPECTED_HOST" ] || stop "unexpected_host"
[ "$(hostname -f 2>/dev/null)" = "$EXPECTED_FQDN" ] || stop "unexpected_fqdn"
[ "$(id -u)" -eq 0 ] || stop "root_required"
command -v python3 >/dev/null 2>&1 || stop "python3_missing"
command -v ss >/dev/null 2>&1 || stop "ss_missing"
command -v curl >/dev/null 2>&1 || stop "curl_missing"
command -v openssl >/dev/null 2>&1 || stop "openssl_missing"

tmp_dir="$(mktemp -d)" || stop "temporary_directory_failed"
trap 'rm -rf -- "$tmp_dir"' EXIT

# Collect only explicitly bounded, read-only inputs. Docker formatting avoids
# Config.Env, mounts, labels, and other fields that can contain secrets.
ss -H -ltnp > "$tmp_dir/listeners" || stop "listener_inspection_failed"
: > "$tmp_dir/containers"
: > "$tmp_dir/proxy-config"
if command -v docker >/dev/null 2>&1; then
  docker ps --no-trunc --format '{{json .}}' > "$tmp_dir/containers" \
    || stop "docker_listing_failed"
  while IFS=$'\t' read -r container image; do
    case "${container,,} ${image,,}" in
      *nginx*|*traefik*|*caddy*|*haproxy*)
        # nginx -T is captured, filtered, and sanitized before anything is emitted.
        case "${image,,}" in
          *nginx*) docker exec "$container" nginx -T > "$tmp_dir/proxy-raw" 2>&1 || true ;;
          *) continue ;;
        esac
        python3 - "$container" "$tmp_dir/proxy-raw" >> "$tmp_dir/proxy-config" <<'PY'
import re, sys
name, path = sys.argv[1:]
for raw in open(path, encoding="utf-8", errors="replace"):
    line = raw.strip()
    if not re.match(r"^(server_name|proxy_pass)\s+", line):
        continue
    if not any(x in line for x in ("ed-finder.app", "43300")):
        continue
    line = re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", line)
    line = re.sub(r"([?&][^=\s]+)=([^&;\s]+)", r"\1=[redacted]", line)
    print(f"container={name}\t{line[:500]}")
PY
        ;;
    esac
  done < <(docker ps --format '{{.Names}}\t{{.Image}}')
fi

# Host nginx output is likewise never emitted directly.
if command -v nginx >/dev/null 2>&1; then
  nginx -T > "$tmp_dir/proxy-raw" 2>&1 || true
  python3 - "$tmp_dir/proxy-raw" >> "$tmp_dir/proxy-config" <<'PY'
import re, sys
for raw in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = raw.strip()
    if not re.match(r"^(server_name|proxy_pass)\s+", line):
        continue
    if not any(x in line for x in ("ed-finder.app", "43300")):
        continue
    line = re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", line)
    line = re.sub(r"([?&][^=\s]+)=([^&;\s]+)", r"\1=[redacted]", line)
    print(f"host\t{line[:500]}")
PY
fi

getent ahosts "$OCTOPUS_HOST" > "$tmp_dir/dns" 2>/dev/null || :
curl -sS -o /dev/null --max-time 5 -w '%{http_code}' \
  -H "Host: $OCTOPUS_HOST" http://127.0.0.1/ > "$tmp_dir/http-status" 2>/dev/null || echo -n 000 > "$tmp_dir/http-status"
curl -sS -k -o /dev/null --max-time 5 -w '%{http_code}' \
  --resolve "$OCTOPUS_HOST:443:127.0.0.1" "https://$OCTOPUS_HOST/" \
  > "$tmp_dir/https-status" 2>/dev/null || echo -n 000 > "$tmp_dir/https-status"
for endpoint in health version; do
  curl -sS -o /dev/null --max-time 5 -w '%{http_code}' \
    "http://$OCTOPUS_UPSTREAM/api/$endpoint" > "$tmp_dir/$endpoint-status" 2>/dev/null \
    || echo -n 000 > "$tmp_dir/$endpoint-status"
done
: > "$tmp_dir/certificate"
if grep -Eq '(^|[[:space:]])[^[:space:]]*:443[[:space:]]' "$tmp_dir/listeners"; then
  openssl s_client -connect 127.0.0.1:443 -servername "$OCTOPUS_HOST" </dev/null 2>/dev/null \
    | openssl x509 -noout -subject -ext subjectAltName > "$tmp_dir/certificate" 2>/dev/null || :
fi
# Inspect public certificate metadata only. Never enumerate or open privkey.pem.
if [ -d /etc/letsencrypt/live ]; then
  while IFS= read -r -d '' certificate; do
    openssl x509 -in "$certificate" -noout -subject -ext subjectAltName \
      >> "$tmp_dir/certificate" 2>/dev/null || :
  done < <(find /etc/letsencrypt/live -maxdepth 3 \( -type f -o -type l \) \
    \( -name fullchain.pem -o -name cert.pem \) -print0 2>/dev/null)
fi

python3 - "$tmp_dir" "$EXPECTED_HOST" "$EXPECTED_FQDN" "$OCTOPUS_HOST" <<'PY'
import json, pathlib, re, sys

root = pathlib.Path(sys.argv[1])
hostname, fqdn, octopus_host = sys.argv[2:]
listeners_raw = (root / "listeners").read_text(errors="replace").splitlines()

def listeners(port):
    found = []
    for line in listeners_raw:
        if re.search(rf"(?:^|\s)(?:\[[^]]+\]|[^\s]+):{port}\s", line):
            # ss process metadata is useful ownership evidence; cap every line.
            found.append(line[:500])
    return found

container_rows = []
for line in (root / "containers").read_text(errors="replace").splitlines():
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    haystack = " ".join(str(row.get(k, "")) for k in ("Names", "Image", "Ports"))
    if any(term in haystack.lower() for term in ("octopus", "nginx", "traefik", "caddy", "haproxy", "43300", ":80->", ":443->")):
        container_rows.append({k: row.get(k, "") for k in ("Names", "Image", "Ports", "Status")})

routes = (root / "proxy-config").read_text(errors="replace").splitlines()
dns_addresses = sorted({line.split()[0] for line in (root / "dns").read_text().splitlines() if line.split()})
certificate_names = sorted(set(re.findall(r"DNS:([^,\s]+)", (root / "certificate").read_text(errors="replace"))))
code = lambda name: (root / name).read_text().strip()[-3:] or "000"
l80, l443, l43300 = listeners(80), listeners(443), listeners(43300)
health_code, version_code = code("health-status"), code("version-status")
route_present = any(octopus_host in line for line in routes) and any("43300" in line for line in routes)
certificate_present = octopus_host in certificate_names or any(
    name.startswith("*.") and octopus_host.endswith(name[1:]) and octopus_host.count(".") == name.count(".")
    for name in certificate_names
)
needed = []
if not dns_addresses:
    needed.append("create_dns_record")
if not l80:
    needed.append("provide_port_80_listener")
if not l443:
    needed.append("provide_port_443_listener")
if not route_present:
    needed.append("configure_reverse_proxy_to_127.0.0.1_43300")
if not certificate_present:
    needed.append("issue_certificate_for_octopus_ed_finder_app")
receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "octopus-edge-status",
    "status": "success",
    "hostname": hostname,
    "fqdn": fqdn,
    "target": {"hostname": octopus_host, "upstream": "127.0.0.1:43300", "expected_version": "1.0.122"},
    "listeners": {"80": l80, "443": l443, "43300": l43300},
    "containers": container_rows,
    "proxy_directives": routes,
    "dns_addresses": dns_addresses,
    "http_status": code("http-status"),
    "https_status": code("https-status"),
    "octopus_api": {"health_status": health_code, "version_status": version_code},
    "certificate_names": certificate_names,
    "needed": needed,
    "conclusions": {
        "dns_present": bool(dns_addresses),
        "listener_80": bool(l80),
        "listener_443": bool(l443),
        "listener_43300": bool(l43300),
        "octopus_internal_healthy": health_code.startswith("2") and version_code.startswith("2"),
        "route_present": route_present,
        "certificate_present": certificate_present,
    },
    "read_only": True,
    "db_access_performed": False,
    "writes_performed": False,
    "service_restarts_performed": False,
}
print(json.dumps(receipt, separators=(",", ":")))
PY
