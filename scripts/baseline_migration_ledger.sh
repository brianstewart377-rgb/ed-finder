#!/usr/bin/env bash
#
# Reviewed one-time helper for databases that predate schema_migrations.
# It records already-applied manifest entries into the migration ledger
# without replaying SQL, and can explicitly annotate the manual 019 state.
#
# Usage:
#   bash scripts/baseline_migration_ledger.sh \
#     --baseline-through 035_nullable_population.sql \
#     --manual-019-status applied \
#     --receipt-file artifacts/migration-baselines/prod.json
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
MANUAL_STATUS_TABLE="${MIGRATION_MANUAL_STATUS_TABLE:-schema_migration_manual_status}"
MIGRATION_DB_SERVICE="${MIGRATION_DB_SERVICE:-postgres}"
MIGRATION_DB_USER="${MIGRATION_DB_USER:-edfinder}"
MIGRATION_DB_NAME="${MIGRATION_DB_NAME:-edfinder}"
PGOPTIONS_VALUE="${PGOPTIONS_VALUE:--c statement_timeout=0 -c lock_timeout=0}"
COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"
COMPOSE_PROJECT_NAME_OVERRIDE="${EDFINDER_DOCKER_PROJECT_NAME:-}"
BASELINE_THROUGH=""
MANUAL_019_STATUS=""
RECEIPT_FILE=""
ALLOW_NONEMPTY_LEDGER=0
compose_args=()

say() { printf '\n[INFO] %s\n' "$*"; }
ok()  { printf '[OK]   %s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
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

ensure_tables() {
  cat <<SQL | run_sql_stdin 0 >/dev/null
CREATE TABLE IF NOT EXISTS ${LEDGER_TABLE} (
    filename TEXT PRIMARY KEY,
    checksum_sha256 TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    apply_mode TEXT NOT NULL DEFAULT 'auto',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS ${MANUAL_STATUS_TABLE} (
    filename TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    noted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);
SQL
}

record_baseline_migration() {
  local filename="$1"
  local checksum="$2"
  local notes="$3"
  local filename_sql checksum_sql notes_sql
  filename_sql="$(sql_escape "$filename")"
  checksum_sql="$(sql_escape "$checksum")"
  notes_sql="$(sql_escape "$notes")"
  run_sql_query "
INSERT INTO ${LEDGER_TABLE} (filename, checksum_sha256, apply_mode, notes)
VALUES ('${filename_sql}', '${checksum_sql}', 'baseline', '${notes_sql}')
ON CONFLICT (filename) DO NOTHING;
" >/dev/null
}

record_manual_status() {
  local filename="$1"
  local status="$2"
  local notes="$3"
  local filename_sql status_sql notes_sql
  filename_sql="$(sql_escape "$filename")"
  status_sql="$(sql_escape "$status")"
  notes_sql="$(sql_escape "$notes")"
  run_sql_query "
INSERT INTO ${MANUAL_STATUS_TABLE} (filename, status, notes)
VALUES ('${filename_sql}', '${status_sql}', '${notes_sql}')
ON CONFLICT (filename) DO UPDATE
SET status = EXCLUDED.status,
    noted_at = NOW(),
    notes = EXCLUDED.notes;
" >/dev/null
}

ledger_row_count() {
  run_sql_query "SELECT COUNT(*) FROM ${LEDGER_TABLE};"
}

usage() {
  sed -n '1,20p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --baseline-through)
      BASELINE_THROUGH="$2"
      shift 2
      ;;
    --manual-019-status)
      MANUAL_019_STATUS="$2"
      shift 2
      ;;
    --receipt-file)
      RECEIPT_FILE="$2"
      shift 2
      ;;
    --compose-file)
      COMPOSE_FILE_OVERRIDE="$2"
      shift 2
      ;;
    --project-name)
      COMPOSE_PROJECT_NAME_OVERRIDE="$2"
      shift 2
      ;;
    --allow-nonempty-ledger)
      ALLOW_NONEMPTY_LEDGER=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown flag: $1"
      ;;
  esac
done

[[ -d "$SQL_DIR" ]] || die "SQL directory not found: $SQL_DIR"
[[ -f "$MANIFEST_FILE" ]] || die "Migration manifest not found: $MANIFEST_FILE"
[[ -n "$BASELINE_THROUGH" ]] || die "--baseline-through is required"
cd "$ROOT_DIR"

if [[ -n "${DATABASE_URL:-}" ]]; then
  need_cmd psql
else
  need_cmd docker
fi

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

say "Ensure migration baseline tables exist"
ensure_tables
ok "baseline tables ready"

existing_rows="$(ledger_row_count)"
if [[ "$existing_rows" != "0" && "$ALLOW_NONEMPTY_LEDGER" -ne 1 ]]; then
  die "ledger already contains ${existing_rows} rows; refusing baseline without --allow-nonempty-ledger"
fi

baseline_found=0
baseline_count=0
manual_recorded='false'
manual_status_value='not-reviewed'
manual_seen=0

while IFS='|' read -r raw_filename raw_mode; do
  filename="$(printf '%s' "${raw_filename:-}" | xargs)"
  mode="$(printf '%s' "${raw_mode:-auto}" | xargs)"

  [[ -n "$filename" ]] || continue
  [[ "${filename:0:1}" == "#" ]] && continue

  case "$mode" in
    ''|auto) mode='auto' ;;
    manual) ;;
    *) die "Unsupported migration mode '$mode' for entry '$filename'" ;;
  esac

  file_path="$SQL_DIR/$filename"
  [[ -f "$file_path" ]] || die "Manifest entry missing file: $file_path"

  if [[ "$mode" == 'manual' ]]; then
    manual_seen=1
    if [[ "$filename" == '019_nullable_coords.sql' ]]; then
      case "$MANUAL_019_STATUS" in
        applied)
          checksum="$(hash_file "$file_path")"
          record_baseline_migration \
            "$filename" \
            "$checksum" \
            'manual migration confirmed complete during ledger baseline'
          record_manual_status \
            "$filename" \
            'applied' \
            'reviewed during ledger baseline'
          baseline_count=$((baseline_count + 1))
          manual_recorded='true'
          manual_status_value='applied'
          ;;
        pending)
          if [[ "$BASELINE_THROUGH" != "$filename" ]]; then
            die "manual 019 cannot stay pending when baseline continues past 019"
          fi
          record_manual_status \
            "$filename" \
            'pending' \
            'reviewed during ledger baseline; SQL not recorded as applied'
          manual_status_value='pending'
          ;;
        '')
          die "baseline crosses manual migration 019; provide --manual-019-status applied|pending"
          ;;
        *)
          die "unsupported --manual-019-status: $MANUAL_019_STATUS"
          ;;
      esac
    else
      die "manual migration encountered without explicit handling: $filename"
    fi
  else
    checksum="$(hash_file "$file_path")"
    record_baseline_migration "$filename" "$checksum" 'reviewed baseline row'
    baseline_count=$((baseline_count + 1))
  fi

  if [[ "$filename" == "$BASELINE_THROUGH" ]]; then
    baseline_found=1
    break
  fi
done < "$MANIFEST_FILE"

[[ "$baseline_found" -eq 1 ]] || die "baseline-through entry not found in manifest: $BASELINE_THROUGH"

if [[ -n "$RECEIPT_FILE" ]]; then
  mkdir -p "$(dirname "$RECEIPT_FILE")"
  cat > "$RECEIPT_FILE" <<EOF
{
  "completed_at_utc": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "baseline_through": "$BASELINE_THROUGH",
  "ledger_rows_recorded": $baseline_count,
  "manual_019_seen": $([[ "$manual_seen" -eq 1 ]] && echo true || echo false),
  "manual_019_recorded_in_ledger": $manual_recorded,
  "manual_019_status": "$manual_status_value"
}
EOF
fi

ok "baseline complete through ${BASELINE_THROUGH} (ledger rows recorded=${baseline_count}, manual_019_status=${manual_status_value})"
