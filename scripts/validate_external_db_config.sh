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
    value = os.environ[name]
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise SystemExit(f"[ERROR] {name} must percent-encode whitespace and control characters")
    hostname = (urlsplit(value).hostname or "").lower()
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

# Keep credentials out of argv (and therefore /proc/<pid>/cmdline). libpq reads
# the URI from this owner-only service file while psql receives only a constant
# service name. The file is replaced for each role and removed on every exit.
service_file="$(mktemp)"
chmod 600 "$service_file"
cleanup() { rm -f "$service_file"; }
trap cleanup EXIT

# Connect through every credential, not just the read-only role. In addition to
# proving each URL works, pg_control_system() gives us the cluster identity; the
# database name distinguishes databases within that cluster. Hostnames alone
# are insufficient because aliases/load balancers can legitimately differ.
expected_identity=""
declare -A observed_roles=()
for name in "${required_urls[@]}"; do
  value="${!name}"
  printf '[external_preflight]\ndbname=%s\n' "$value" >"$service_file"
  identity="$(PGCONNECT_TIMEOUT=10 PGOPTIONS='-c default_transaction_read_only=on' \
    PGSERVICEFILE="$service_file" EDFINDER_VALIDATING_URL_NAME="$name" \
    psql --no-psqlrc --dbname='service=external_preflight' -AtX --field-separator='|' \
      -c "SELECT current_setting('server_version_num'), system_identifier, current_database(), encode(convert_to(current_user, 'UTF8'), 'hex'), has_table_privilege(current_user, 'public.systems', 'SELECT'), has_table_privilege(current_user, 'public.systems', 'INSERT'), has_table_privilege(current_user, 'public.systems', 'UPDATE'), has_table_privilege(current_user, 'public.systems', 'DELETE'), has_table_privilege(current_user, 'public.systems', 'MAINTAIN'), has_schema_privilege(current_user, 'public', 'CREATE') FROM pg_control_system()")" \
    || die "$name external database preflight connection/identity check failed"

  IFS='|' read -r version_num system_identifier database_name role_id can_select can_insert can_update can_delete can_maintain can_ddl extra <<<"$identity"
  [[ -z "${extra:-}" && -n "$system_identifier" && -n "$database_name" && "$role_id" =~ ^[0-9a-f]+$ ]] \
    || die "$name returned an invalid database identity"
  [[ "$version_num" =~ ^18[0-9]{4}$ ]] \
    || die "$name must target PostgreSQL 18 (server reported a different major version)"
  role_identity="${system_identifier}|${database_name}"
  if [[ -z "$expected_identity" ]]; then
    expected_identity="$role_identity"
  elif [[ "$role_identity" != "$expected_identity" ]]; then
    die "$name does not target the same PostgreSQL cluster and database as the other external role URLs"
  fi
  [[ -z "${observed_roles[$role_id]:-}" ]] \
    || die "$name resolves to the same database role as ${observed_roles[$role_id]}; external roles must be separated"
  observed_roles[$role_id]="$name"

  case "$name" in
    DATABASE_READONLY_URL)
      [[ "$can_select" == "t" && "$can_insert" == "f" && "$can_update" == "f" \
        && "$can_delete" == "f" && "$can_maintain" == "f" && "$can_ddl" == "f" ]] \
        || die "$name role is not strictly read-only"
      ;;
    DATABASE_APP_URL|DATABASE_IMPORT_URL)
      [[ "$can_select" == "t" && "$can_insert" == "t" && "$can_update" == "t" \
        && "$can_delete" == "t" && "$can_ddl" == "f" ]] \
        || die "$name role lacks required DML or is overprivileged for schema DDL"
      ;;
    DATABASE_MAINTENANCE_URL)
      [[ "$can_select" == "t" && "$can_delete" == "t" && "$can_maintain" == "t" \
        && "$can_ddl" == "f" ]] \
        || die "$name role lacks required maintenance privileges or is overprivileged for schema DDL"
      ;;
    DATABASE_MIGRATION_URL)
      [[ "$can_ddl" == "t" ]] || die "$name role lacks required schema DDL capability"
      ;;
  esac
done
printf '[OK] separated external roles have suitable privileges on one PostgreSQL 18 cluster and database\n'
