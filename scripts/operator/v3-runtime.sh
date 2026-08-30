#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT/deploy/v3/compose.yml"
ENV_FILE="${V3_ENV_FILE:-$ROOT/deploy/v3/.env}"

die() { printf 'v3-runtime: %s\n' "$*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || die 'docker is required'
[[ -f "$ENV_FILE" ]] || die "environment file missing: $ENV_FILE"
[[ ! -L "$ENV_FILE" ]] || die 'environment file must not be a symlink'
mode="$(stat -c '%a' "$ENV_FILE")"
(( (8#$mode & 8#077) == 0 )) || die 'environment file must not be group/world accessible (use chmod 600)'

readarray -t safe_runtime_values < <(python3 - "$ENV_FILE" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

values = {}
for number, raw in enumerate(Path(sys.argv[1]).read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"v3-runtime: invalid environment line {number}")
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()
required = ("V3_DATABASE_APP_URL", "V3_DATABASE_READONLY_URL", "V3_DATABASE_EDDN_URL", "V3_CORS_ORIGINS")
for key in required:
    if not values.get(key) or values[key] == "REPLACE_ME":
        raise SystemExit(f"v3-runtime: {key} is required")
for key in required[:3]:
    parsed = urlsplit(values[key])
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise SystemExit(f"v3-runtime: {key} must be a PostgreSQL URL with a host")
    if parsed.hostname in {"postgres", "ed-postgres", "localhost", "127.0.0.1", "::1"}:
        raise SystemExit(f"v3-runtime: {key} must target external PostgreSQL")
bind = values.get("V3_BIND_ADDRESS", "127.0.0.1")
allow_public = values.get("V3_ALLOW_PUBLIC_BIND", os.environ.get("V3_ALLOW_PUBLIC_BIND", "no"))
if bind not in {"127.0.0.1", "::1"} and allow_public != "yes":
    raise SystemExit("v3-runtime: non-loopback bind requires V3_ALLOW_PUBLIC_BIND=yes")
print(bind)
print(values.get("V3_HTTP_PORT", "8080"))
PY
)
V3_BIND_ADDRESS="${safe_runtime_values[0]}"
V3_HTTP_PORT="${safe_runtime_values[1]}"

dc() { docker compose --project-name edfinder-v3 --env-file "$ENV_FILE" -f "$COMPOSE" "$@"; }
case "${1:-}" in
  validate) dc config --quiet ;;
  start) dc config --quiet; dc up -d --build redis api eddn proxy ;;
  status) dc ps ;;
  stop) dc down --remove-orphans ;;
  smoke)
    [[ "$V3_BIND_ADDRESS" == 127.0.0.1 ]] || die 'smoke is private-only; validate a public cutover separately'
    curl --fail --silent --show-error "http://127.0.0.1:${V3_HTTP_PORT}/nginx-healthz"
    curl --fail --silent --show-error "http://127.0.0.1:${V3_HTTP_PORT}/api/health"
    ;;
  *) die 'usage: v3-runtime.sh {validate|start|status|stop|smoke}' ;;
esac
