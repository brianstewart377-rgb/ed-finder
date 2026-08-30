#!/usr/bin/env bash
# Validate the explicit external PostgreSQL production mode without printing DSNs.
set -euo pipefail

CONFIG_ONLY=0
[[ "${1:-}" == "--config-only" ]] && CONFIG_ONLY=1

die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

required_urls=(
  DATABASE_APP_URL
  DATABASE_READONLY_URL
  DATABASE_IMPORT_URL
  DATABASE_MAINTENANCE_URL
  DATABASE_MIGRATION_URL
)

for name in "${required_urls[@]}"; do
  value="${!name:-}"
  [[ -n "$value" ]] || die "$name is required in external database mode"
  case "$value" in
    postgres://*|postgresql://*) ;;
    *) die "$name must be a PostgreSQL URL" ;;
  esac
done

# A URL naming the Compose service would make --external-db appear configured
# while still depending on the bundled database that this mode must bypass.
python3 - <<'PY'
import os
from urllib.parse import urlsplit

names = (
    "DATABASE_APP_URL", "DATABASE_READONLY_URL", "DATABASE_IMPORT_URL",
    "DATABASE_MAINTENANCE_URL", "DATABASE_MIGRATION_URL",
)
for name in names:
    hostname = (urlsplit(os.environ[name]).hostname or "").lower()
    if not hostname:
        raise SystemExit(f"[ERROR] {name} must include a database host")
    if hostname == "postgres":
        raise SystemExit(f"[ERROR] {name} must not target the bundled Compose postgres service")
PY

if [[ "$CONFIG_ONLY" -eq 1 ]]; then
  printf '[OK] external database configuration is complete\n'
  exit 0
fi

command -v psql >/dev/null 2>&1 || die "psql is required for external database preflight"
version_num="$(PGCONNECT_TIMEOUT=10 PGOPTIONS='-c default_transaction_read_only=on' \
  psql --no-psqlrc --dbname="$DATABASE_READONLY_URL" -AtX \
    -c "SELECT current_setting('server_version_num')")" || die "external database preflight connection failed"
[[ "$version_num" =~ ^18[0-9]{4}$ ]] || die "external database must be PostgreSQL 18 (server reported a different major version)"
printf '[OK] external PostgreSQL 18 read-only preflight passed\n'
