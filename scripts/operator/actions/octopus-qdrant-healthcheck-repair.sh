#!/usr/bin/env bash
set -euo pipefail

OCTOPUS_DIR="/opt/octopus"
COMPOSE_FILE="$OCTOPUS_DIR/docker-compose.selfhost.yml"
EXPECTED_HOST="ed-finder-prod"
EXPECTED_IMAGE="qdrant/qdrant:v1.17.0"
BACKUP=""
EDIT_COMMITTED=false
QDRANT_RECREATED=false
WEB_STARTED=false

receipt() {
  local status="$1" reason="$2"
  python3 - "$status" "$reason" "$BACKUP" "$QDRANT_RECREATED" "$WEB_STARTED" <<'PY'
import json
import sys

print(json.dumps({
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "octopus-qdrant-healthcheck-repair",
    "status": sys.argv[1],
    "reason": sys.argv[2],
    "compose_backup": sys.argv[3] or None,
    "qdrant_recreated": sys.argv[4] == "true",
    "web_started": sys.argv[5] == "true",
    "db_access_performed": False,
    "db_writes_performed": False,
    "volume_configuration_modified": False,
    "migrations_performed": False,
    "env_values_modified": False,
}, separators=(",", ":")))
PY
}

stop() {
  receipt "stopped" "$1" >&2
  exit 1
}

on_exit() {
  local rc=$?
  if [ "$rc" -ne 0 ] && [ "$EDIT_COMMITTED" = false ] && [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
    cp --preserve=mode,ownership,timestamps -- "$BACKUP" "$COMPOSE_FILE"
  fi
}
trap on_exit EXIT

[ "$(hostname -s)" = "$EXPECTED_HOST" ] || stop "unexpected_host"
[ "$(id -u)" -eq 0 ] || stop "root_required"
[ "$(pwd -P)" = "/opt/ed-finder" ] || stop "unexpected_working_directory"
[ -d "$OCTOPUS_DIR" ] || stop "octopus_directory_missing"
[ -f "$COMPOSE_FILE" ] || stop "compose_file_missing"
command -v docker >/dev/null 2>&1 || stop "docker_missing"
docker compose version >/dev/null 2>&1 || stop "docker_compose_missing"

# Validate the rendered service identity without displaying interpolated values.
read -r rendered_image rendered_web_image < <(docker compose --project-directory "$OCTOPUS_DIR" -f "$COMPOSE_FILE" config --format json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin).get("services",{}); print((d.get("qdrant",{}) or {}).get("image", ""), (d.get("web",{}) or {}).get("image", ""))') \
  || stop "compose_render_failed"
[ "$rendered_image" = "$EXPECTED_IMAGE" ] || stop "unexpected_qdrant_image"
case "$rendered_web_image" in
  ghcr.io/octopusreview/octopus-selfhost:1.0.122) ;;
  *) stop "unexpected_octopus_web_image" ;;
esac
current_qdrant_id="$(docker compose --project-directory "$OCTOPUS_DIR" -f "$COMPOSE_FILE" ps -q qdrant)"
[ -n "$current_qdrant_id" ] || stop "existing_qdrant_container_missing"
current_qdrant_image="$(docker inspect --format '{{.Config.Image}}' "$current_qdrant_id" 2>/dev/null)" \
  || stop "existing_qdrant_inspect_failed"
[ "$current_qdrant_image" = "$EXPECTED_IMAGE" ] || stop "unexpected_running_qdrant_image"

# The editor accepts exactly one qdrant healthcheck block and exactly the known
# wget /readyz failure mode. It changes only healthcheck.test, preserving timing.
replacement_file="$(mktemp "$OCTOPUS_DIR/.qdrant-healthcheck.XXXXXX")"
if ! python3 - "$COMPOSE_FILE" "$replacement_file" <<'PY'
from pathlib import Path
import re
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
lines = source.splitlines(keepends=True)

services_match = re.search(r"(?m)^services:\s*(?:#.*)?$", source)
if not services_match:
    raise SystemExit("top-level services mapping missing")
service_match = re.search(r"(?m)^  qdrant:\s*(?:#.*)?$", source[services_match.end():])
if not service_match:
    raise SystemExit("qdrant service missing")
service_offset = services_match.end()
indent = 2
start = source[:service_offset + service_match.start()].count("\n")
end = len(lines)
for index in range(start + 1, len(lines)):
    stripped = lines[index].lstrip(" ")
    if stripped.strip() and not stripped.startswith("#"):
        current_indent = len(lines[index]) - len(stripped)
        if current_indent <= indent:
            end = index
            break

health = [i for i in range(start + 1, end) if re.match(r"^ {%d}healthcheck:\s*(?:#.*)?$" % (indent + 2), lines[i].rstrip("\n"))]
if len(health) != 1:
    raise SystemExit("expected exactly one qdrant healthcheck")
hstart = health[0]
hend = end
for index in range(hstart + 1, end):
    stripped = lines[index].lstrip(" ")
    if stripped.strip() and not stripped.startswith("#"):
        current_indent = len(lines[index]) - len(stripped)
        if current_indent <= indent + 2:
            hend = index
            break

tests = [i for i in range(hstart + 1, hend) if re.match(r"^ {%d}test:" % (indent + 4), lines[i])]
if len(tests) != 1:
    raise SystemExit("expected exactly one qdrant healthcheck test")
test_index = tests[0]
test_line = lines[test_index]
expected = ('test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", '
            '"http://localhost:6333/readyz"]')
if test_line.strip() != expected:
    raise SystemExit("qdrant healthcheck is not the expected broken wget readiness check")
if any("wget" in line for i, line in enumerate(lines) if i != test_index and start <= i < hend):
    raise SystemExit("unexpected additional wget content in qdrant healthcheck")

prefix = " " * (indent + 4)
command = ('test: ["CMD-SHELL", "while read -r _ local _ state _; do if [ $$state = 0A ]; '
           'then case $$local in *:18BD) exit 0;; esac; fi; done < /proc/net/tcp; '
           'while read -r _ local _ state _; do if [ $$state = 0A ]; then case $$local '
           'in *:18BD) exit 0;; esac; fi; done < /proc/net/tcp6; exit 1"]\n')
lines[test_index] = prefix + command
Path(sys.argv[2]).write_text("".join(lines), encoding="utf-8")
PY
then
  rm -f -- "$replacement_file"
  stop "expected_broken_healthcheck_not_found"
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$COMPOSE_FILE.before-qdrant-healthcheck-repair.$timestamp"
[ ! -e "$BACKUP" ] || { rm -f -- "$replacement_file"; stop "backup_already_exists"; }
cp --preserve=mode,ownership,timestamps -- "$COMPOSE_FILE" "$BACKUP"
chown --reference="$COMPOSE_FILE" "$replacement_file"
chmod --reference="$COMPOSE_FILE" "$replacement_file"
mv -- "$replacement_file" "$COMPOSE_FILE"

docker compose --project-directory "$OCTOPUS_DIR" -f "$COMPOSE_FILE" config --quiet \
  || stop "edited_compose_validation_failed"
EDIT_COMMITTED=true

docker compose --project-directory "$OCTOPUS_DIR" -f "$COMPOSE_FILE" up -d --no-deps --force-recreate qdrant \
  >/dev/null || stop "qdrant_recreate_failed"
QDRANT_RECREATED=true

qdrant_id="$(docker compose --project-directory "$OCTOPUS_DIR" -f "$COMPOSE_FILE" ps -q qdrant)"
[ -n "$qdrant_id" ] || stop "qdrant_container_missing"
healthy=false
for _ in $(seq 1 60); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$qdrant_id" 2>/dev/null || true)"
  if [ "$health" = healthy ]; then healthy=true; break; fi
  [ "$health" != unhealthy ] || stop "qdrant_became_unhealthy"
  sleep 2
done
[ "$healthy" = true ] || stop "qdrant_health_timeout"

python3 - <<'PY' || stop "host_qdrant_readyz_failed"
from urllib.request import urlopen
with urlopen("http://127.0.0.1:43333/readyz", timeout=5) as response:
    body = response.read(1024).decode("utf-8", "replace").strip()
    if response.status != 200 or body != "all shards are ready":
        raise SystemExit(1)
PY

docker compose --project-directory "$OCTOPUS_DIR" -f "$COMPOSE_FILE" up -d web >/dev/null \
  || stop "web_start_failed"
WEB_STARTED=true

web_ready=false
for _ in $(seq 1 60); do
  if python3 - <<'PY'
from urllib.request import urlopen
for path in ("/", "/api/health", "/api/version"):
    with urlopen("http://127.0.0.1:43300" + path, timeout=5) as response:
        if not 200 <= response.status < 400:
            raise SystemExit(1)
PY
  then web_ready=true; break; fi
  sleep 2
done
[ "$web_ready" = true ] || stop "web_health_timeout"

receipt "success" "repair_complete"
