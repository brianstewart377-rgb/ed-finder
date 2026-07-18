#!/usr/bin/env bash
#
# Apply ED-Finder SQL migrations via an explicit manifest and a lightweight
# database ledger. This replaces "replay every sql/*.sql on every deploy".
#
# Usage:
#   bash scripts/apply_migrations.sh
#   bash scripts/apply_migrations.sh --include-manual
#
# Connection modes:
#   1. DATABASE_URL set            -> use local/direct psql
#   2. default (no DATABASE_URL)   -> use docker compose exec postgres
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi
DATABASE_URL="${DATABASE_MIGRATION_URL:-${DATABASE_URL:-}}"
SQL_DIR="${SQL_DIR:-$ROOT_DIR/sql}"
MANIFEST_FILE="${MIGRATION_MANIFEST:-$SQL_DIR/migration-manifest.txt}"
LEDGER_TABLE="${MIGRATION_LEDGER_TABLE:-schema_migrations}"
INCLUDE_MANUAL=0

MIGRATION_DB_SERVICE="${MIGRATION_DB_SERVICE:-postgres}"
MIGRATION_DB_USER="${MIGRATION_DB_USER:-edfinder}"
MIGRATION_DB_NAME="${MIGRATION_DB_NAME:-edfinder}"
PGOPTIONS_VALUE="${PGOPTIONS_VALUE:--c statement_timeout=0 -c lock_timeout=0}"
COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"
COMPOSE_PROJECT_NAME_OVERRIDE="${EDFINDER_DOCKER_PROJECT_NAME:-}"
compose_args=()

say() { printf '\n[INFO] %s\n' "$*"; }
ok()  { printf '[OK]   %s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-manual)
      INCLUDE_MANUAL=1
      shift
      ;;
    --compose-file)
      COMPOSE_FILE_OVERRIDE="$2"
      shift 2
      ;;
    --project-name)
      COMPOSE_PROJECT_NAME_OVERRIDE="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '1,30p' "$0"
      exit 0
      ;;
    *)
      die "Unknown flag: $1"
      ;;
  esac
done

[[ -d "$SQL_DIR" ]] || die "SQL directory not found: $SQL_DIR"
[[ -f "$MANIFEST_FILE" ]] || die "Migration manifest not found: $MANIFEST_FILE"
cd "$ROOT_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

if [[ -n "$COMPOSE_FILE_OVERRIDE" ]]; then
  [[ -f "$COMPOSE_FILE_OVERRIDE" ]] || die "compose file not found: $COMPOSE_FILE_OVERRIDE"
  compose_args+=(-f "$COMPOSE_FILE_OVERRIDE")
elif [[ -z "${DATABASE_URL:-}" ]]; then
  [[ -f docker-compose.yml ]] || die "docker-compose.yml not found in $ROOT_DIR"
fi

if [[ -n "$COMPOSE_PROJECT_NAME_OVERRIDE" ]]; then
  compose_args+=(-p "$COMPOSE_PROJECT_NAME_OVERRIDE")
fi

dc() {
  docker compose "${compose_args[@]}" "$@"
}

sql_escape() {
  printf '%s' "$1" | sed "s/'/''/g"
}

hash_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "$file" <<'PY'
import hashlib
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
  elif command -v python >/dev/null 2>&1; then
    python - "$file" <<'PY'
import hashlib
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
  else
    die "missing sha256sum/shasum/python to hash migration files"
  fi
}

run_sql_stdin() {
  local at_mode="${1:-0}"
  if [[ -n "${DATABASE_URL:-}" ]]; then
    local args=(-v ON_ERROR_STOP=1)
    if [[ "$at_mode" == "1" ]]; then
      args+=(-At)
    fi
    args+=("$DATABASE_URL")
    PGOPTIONS="$PGOPTIONS_VALUE" psql "${args[@]}"
  else
    local extra_flags="-v ON_ERROR_STOP=1"
    if [[ "$at_mode" == "1" ]]; then
      extra_flags="$extra_flags -At"
    fi
    dc exec -T "$MIGRATION_DB_SERVICE" sh -lc \
      "PGOPTIONS='$PGOPTIONS_VALUE' exec psql -U '$MIGRATION_DB_USER' -d '$MIGRATION_DB_NAME' $extra_flags"
  fi
}

run_sql_query() {
  local sql="$1"
  printf '%s\n' "$sql" | run_sql_stdin 1
}

apply_sql_file() {
  local file="$1"
  if [[ -n "${DATABASE_URL:-}" ]]; then
    PGOPTIONS="$PGOPTIONS_VALUE" psql -v ON_ERROR_STOP=1 -f "$file" "$DATABASE_URL" >/dev/null
  else
    cat "$file" | run_sql_stdin 0 >/dev/null
  fi
}

ensure_ledger_table() {
  cat <<SQL | run_sql_stdin 0 >/dev/null
CREATE TABLE IF NOT EXISTS ${LEDGER_TABLE} (
    filename TEXT PRIMARY KEY,
    checksum_sha256 TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    apply_mode TEXT NOT NULL DEFAULT 'auto',
    notes TEXT
);
SQL
}

record_migration() {
  local filename="$1"
  local checksum="$2"
  local apply_mode="$3"
  local filename_sql checksum_sql mode_sql
  filename_sql="$(sql_escape "$filename")"
  checksum_sql="$(sql_escape "$checksum")"
  mode_sql="$(sql_escape "$apply_mode")"
  run_sql_query "
INSERT INTO ${LEDGER_TABLE} (filename, checksum_sha256, apply_mode)
VALUES ('${filename_sql}', '${checksum_sql}', '${mode_sql}')
ON CONFLICT (filename) DO NOTHING;
" >/dev/null
}

fetch_recorded_checksum() {
  local filename="$1"
  local filename_sql
  filename_sql="$(sql_escape "$filename")"
  run_sql_query "
SELECT checksum_sha256
FROM ${LEDGER_TABLE}
WHERE filename = '${filename_sql}';
"
}

if [[ -n "${DATABASE_URL:-}" ]]; then
  need_cmd psql
else
  need_cmd docker
fi

say "Ensure migration ledger exists"
ensure_ledger_table
ok "ledger table ready: ${LEDGER_TABLE}"

applied_count=0
skipped_count=0

while IFS='|' read -r raw_filename raw_mode; do
  filename="$(printf '%s' "${raw_filename:-}" | xargs)"
  mode="$(printf '%s' "${raw_mode:-auto}" | xargs)"

  [[ -n "$filename" ]] || continue
  [[ "${filename:0:1}" == "#" ]] && continue

  case "$mode" in
    ''|auto) mode='auto' ;;
    manual) ;;
    *)
      die "Unsupported migration mode '$mode' for entry '$filename'"
      ;;
  esac

  if [[ "$mode" == "manual" && "$INCLUDE_MANUAL" -ne 1 ]]; then
    printf '[INFO] skipping manual migration %s\n' "$filename"
    skipped_count=$((skipped_count + 1))
    continue
  fi

  file_path="$SQL_DIR/$filename"
  [[ -f "$file_path" ]] || die "Manifest entry missing file: $file_path"

  checksum="$(hash_file "$file_path")"
  recorded_checksum="$(fetch_recorded_checksum "$filename")"

  if [[ -n "$recorded_checksum" ]]; then
    if [[ "$recorded_checksum" != "$checksum" ]]; then
      die "Checksum mismatch for already-recorded migration $filename"
    fi
    printf '[INFO] already applied %s\n' "$filename"
    skipped_count=$((skipped_count + 1))
    continue
  fi

  printf '[INFO] applying %s\n' "$filename"
  apply_sql_file "$file_path"
  record_migration "$filename" "$checksum" "$mode"
  applied_count=$((applied_count + 1))
done < "$MANIFEST_FILE"

ok "migration apply complete (applied=${applied_count}, skipped=${skipped_count})"
