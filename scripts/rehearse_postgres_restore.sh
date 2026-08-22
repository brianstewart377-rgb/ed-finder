#!/usr/bin/env bash
#
# Run a full backup + restore rehearsal against the local docker-compose stack.
# This stays non-destructive by default: it restores into a disposable database
# and drops that database again unless --keep-db is supplied.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_FILE="${BACKUP_FILE:-/data/backups/postgres/latest.dump}"
TARGET_DB="${TARGET_DB:-edfinder_restore_rehearsal}"
SOURCE_DB="${SOURCE_DB:-edfinder}"
SKIP_BACKUP=0
KEEP_DB=0
RECEIPT_FILE="${RECEIPT_FILE:-}"
BACKUP_MODE="${EDFINDER_RESTORE_BACKUP_MODE:-auto}"
COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"
COMPOSE_PROJECT_NAME_OVERRIDE="${EDFINDER_DOCKER_PROJECT_NAME:-}"
BACKUP_FILE_EXPLICIT=0
MIN_SYSTEM_ROWS="${EDFINDER_RESTORE_MIN_SYSTEM_ROWS:-}"
MIN_BODIES_BYTES="${EDFINDER_RESTORE_MIN_BODIES_BYTES:-}"
MIN_RATINGS_BYTES="${EDFINDER_RESTORE_MIN_RATINGS_BYTES:-}"
MIN_SCHEMA_MIGRATIONS="${EDFINDER_RESTORE_MIN_SCHEMA_MIGRATIONS:-35}"
TARGET_MAY_EXIST=0

say() { printf "\n[INFO] %s\n" "$*"; }
ok()  { printf "[OK]   %s\n" "$*"; }
die() { printf "[ERROR] %s\n" "$*" >&2; exit 1; }

compose_args=()

usage() {
  sed -n '1,14p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-file)  BACKUP_FILE="$2"; BACKUP_FILE_EXPLICIT=1; shift 2 ;;
    --source-db)    SOURCE_DB="$2"; shift 2 ;;
    --target-db)    TARGET_DB="$2"; shift 2 ;;
    --receipt-file) RECEIPT_FILE="$2"; shift 2 ;;
    --backup-mode)  BACKUP_MODE="$2"; shift 2 ;;
    --compose-file) COMPOSE_FILE_OVERRIDE="$2"; shift 2 ;;
    --project-name) COMPOSE_PROJECT_NAME_OVERRIDE="$2"; shift 2 ;;
    --min-system-rows) MIN_SYSTEM_ROWS="$2"; shift 2 ;;
    --min-bodies-bytes) MIN_BODIES_BYTES="$2"; shift 2 ;;
    --min-ratings-bytes) MIN_RATINGS_BYTES="$2"; shift 2 ;;
    --min-schema-migrations) MIN_SCHEMA_MIGRATIONS="$2"; shift 2 ;;
    --skip-backup)  SKIP_BACKUP=1; shift ;;
    --keep-db)      KEEP_DB=1; shift ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown flag: $1"
      ;;
  esac
done

cd "$REPO_DIR"

command -v docker >/dev/null || die "docker not found"

if [[ -n "$COMPOSE_FILE_OVERRIDE" ]]; then
  [[ -f "$COMPOSE_FILE_OVERRIDE" ]] || die "compose file not found: $COMPOSE_FILE_OVERRIDE"
  compose_args+=(-f "$COMPOSE_FILE_OVERRIDE")
else
  [[ -f docker-compose.yml ]] || die "docker-compose.yml not found in $REPO_DIR"
fi

if [[ -n "$COMPOSE_PROJECT_NAME_OVERRIDE" ]]; then
  compose_args+=(-p "$COMPOSE_PROJECT_NAME_OVERRIDE")
fi

dc() {
  docker compose "${compose_args[@]}" "$@"
}

cleanup_target() {
  if [[ "$KEEP_DB" -ne 1 && "$TARGET_MAY_EXIST" -eq 1 ]]; then
    if [[ "$TARGET_DB" == "edfinder" ]]; then
      printf '[ERROR] refusing cleanup of live database edfinder\n' >&2
      return
    fi
    say "Cleanup disposable rehearsal database"
    dc exec -T postgres dropdb -U edfinder --if-exists "$TARGET_DB" || true
    TARGET_MAY_EXIST=0
  fi
}
trap cleanup_target EXIT

compose_has_service() {
  dc config --services | grep -Fxq "$1"
}

resolve_backup_mode() {
  case "$BACKUP_MODE" in
    auto)
      if compose_has_service maintenance; then
        BACKUP_MODE="maintenance"
      else
        BACKUP_MODE="postgres"
      fi
      ;;
    maintenance|postgres)
      ;;
    *)
      die "unsupported backup mode: $BACKUP_MODE"
      ;;
  esac
}

run_postgres_direct_backup() {
  mkdir -p "$(dirname "$BACKUP_FILE")"
  local tmp_backup="${BACKUP_FILE}.tmp"

  say "Run direct backup via postgres service"
  dc exec -T postgres pg_dump -U edfinder -d "$SOURCE_DB" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-privileges > "$tmp_backup"
  cat "$tmp_backup" | dc exec -T postgres pg_restore --list >/dev/null
  mv "$tmp_backup" "$BACKUP_FILE"
  ok "direct postgres backup completed"
}

resolve_backup_mode

[[ "$TARGET_DB" != "edfinder" ]] || \
  die "restore rehearsals must use a disposable target database, never edfinder"

# ED-Finder's production backup is expected to contain the full galaxy. Local
# disposable rehearsals intentionally use tiny fixtures, so their default
# thresholds stay minimal when docker-compose.local.yml is selected.
if [[ -z "$MIN_SYSTEM_ROWS" ]]; then
  if [[ "$COMPOSE_FILE_OVERRIDE" == *"docker-compose.local.yml" ]]; then
    MIN_SYSTEM_ROWS=1
  else
    MIN_SYSTEM_ROWS=180000000
  fi
fi
if [[ -z "$MIN_BODIES_BYTES" ]]; then
  if [[ "$COMPOSE_FILE_OVERRIDE" == *"docker-compose.local.yml" ]]; then
    MIN_BODIES_BYTES=1
  else
    MIN_BODIES_BYTES=107374182400
  fi
fi
if [[ -z "$MIN_RATINGS_BYTES" ]]; then
  if [[ "$COMPOSE_FILE_OVERRIDE" == *"docker-compose.local.yml" ]]; then
    MIN_RATINGS_BYTES=1
  else
    MIN_RATINGS_BYTES=1073741824
  fi
fi
for numeric_setting in \
  "$MIN_SYSTEM_ROWS" \
  "$MIN_BODIES_BYTES" \
  "$MIN_RATINGS_BYTES" \
  "$MIN_SCHEMA_MIGRATIONS"; do
  [[ "$numeric_setting" =~ ^[0-9]+$ ]] || die "restore thresholds must be non-negative integers"
done

if [[ "$BACKUP_MODE" == "postgres" && "$BACKUP_FILE_EXPLICIT" -ne 1 ]]; then
  BACKUP_FILE="$REPO_DIR/artifacts/restore-rehearsals/latest.dump"
fi

STARTED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

if [[ "$SKIP_BACKUP" -ne 1 ]]; then
  if [[ "$BACKUP_MODE" == "maintenance" ]]; then
    say "Run manual backup through maintenance sidecar"
    dc exec maintenance /usr/local/bin/run_backup.sh manual
    ok "manual backup completed"
  else
    run_postgres_direct_backup
  fi
fi

[[ -f "$BACKUP_FILE" ]] || die "backup file not found: $BACKUP_FILE"

restore_args=(
  --backup-file "$BACKUP_FILE"
  --target-db "$TARGET_DB"
)
if [[ -n "$COMPOSE_FILE_OVERRIDE" ]]; then
  restore_args+=(--compose-file "$COMPOSE_FILE_OVERRIDE")
fi
if [[ -n "$COMPOSE_PROJECT_NAME_OVERRIDE" ]]; then
  restore_args+=(--project-name "$COMPOSE_PROJECT_NAME_OVERRIDE")
fi

say "Restore archive into disposable rehearsal database"
TARGET_MAY_EXIST=1
bash scripts/restore_postgres_backup.sh "${restore_args[@]}"
ok "restore helper completed"

say "Collect production-readiness markers"
PUBLIC_TABLES="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
)"
SCHEMA_MIGRATIONS="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM schema_migrations;"
)"
SYSTEM_ROWS="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM systems;"
)"
KNOWN_SYSTEMS="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(DISTINCT lower(name)) FROM systems WHERE lower(name) IN ('sol', 'colonia');"
)"
BODIES_BYTES="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT pg_total_relation_size('public.bodies');"
)"
RATINGS_BYTES="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT pg_total_relation_size('public.ratings');"
)"
STATION_ROWS="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM stations;"
)"
UNVALIDATED_CONSTRAINTS="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM pg_constraint WHERE NOT convalidated;"
)"
INVALID_INDEXES="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM pg_index WHERE NOT indisvalid OR NOT indisready;"
)"
UNPOPULATED_MATERIALIZED_VIEWS="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'm' AND NOT c.relispopulated;"
)"

[[ "$PUBLIC_TABLES" -ge 1 ]] || die "rehearsal restored no public tables"
[[ "$SCHEMA_MIGRATIONS" -ge "$MIN_SCHEMA_MIGRATIONS" ]] || \
  die "schema migration count $SCHEMA_MIGRATIONS is below required $MIN_SCHEMA_MIGRATIONS"
[[ "$SYSTEM_ROWS" -ge "$MIN_SYSTEM_ROWS" ]] || \
  die "systems count $SYSTEM_ROWS is below required $MIN_SYSTEM_ROWS"
[[ "$KNOWN_SYSTEMS" -eq 2 ]] || die "Sol and Colonia were not both restored"
[[ "$BODIES_BYTES" -ge "$MIN_BODIES_BYTES" ]] || \
  die "bodies relation bytes $BODIES_BYTES is below required $MIN_BODIES_BYTES"
[[ "$RATINGS_BYTES" -ge "$MIN_RATINGS_BYTES" ]] || \
  die "ratings relation bytes $RATINGS_BYTES is below required $MIN_RATINGS_BYTES"
[[ "$STATION_ROWS" -ge 1 ]] || die "stations table is empty"
[[ "$UNVALIDATED_CONSTRAINTS" -eq 0 ]] || \
  die "$UNVALIDATED_CONSTRAINTS constraints are not validated"
[[ "$INVALID_INDEXES" -eq 0 ]] || \
  die "$INVALID_INDEXES indexes are invalid or not ready"
[[ "$UNPOPULATED_MATERIALIZED_VIEWS" -eq 0 ]] || \
  die "$UNPOPULATED_MATERIALIZED_VIEWS public materialized views are not populated"

ok "public tables visible: $PUBLIC_TABLES"
ok "schema migrations visible: $SCHEMA_MIGRATIONS"
ok "systems rows: $SYSTEM_ROWS"
ok "known systems restored: Sol and Colonia"
ok "bodies relation bytes: $BODIES_BYTES"
ok "ratings relation bytes: $RATINGS_BYTES"
ok "stations rows: $STATION_ROWS"
ok "unvalidated constraints: $UNVALIDATED_CONSTRAINTS"
ok "invalid/not-ready indexes: $INVALID_INDEXES"
ok "unpopulated materialized views: $UNPOPULATED_MATERIALIZED_VIEWS"

if [[ -n "$RECEIPT_FILE" ]]; then
  mkdir -p "$(dirname "$RECEIPT_FILE")"
  cat > "$RECEIPT_FILE" <<EOF
{
  "started_at_utc": "$STARTED_AT",
  "completed_at_utc": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "backup_file": "$BACKUP_FILE",
  "backup_mode": "$BACKUP_MODE",
  "source_db": "$SOURCE_DB",
  "target_db": "$TARGET_DB",
  "public_tables": $PUBLIC_TABLES,
  "schema_migrations": $SCHEMA_MIGRATIONS,
  "systems_rows": $SYSTEM_ROWS,
  "minimum_systems_rows": $MIN_SYSTEM_ROWS,
  "known_systems_sol_colonia": $KNOWN_SYSTEMS,
  "bodies_relation_bytes": $BODIES_BYTES,
  "minimum_bodies_relation_bytes": $MIN_BODIES_BYTES,
  "ratings_relation_bytes": $RATINGS_BYTES,
  "minimum_ratings_relation_bytes": $MIN_RATINGS_BYTES,
  "stations_rows": $STATION_ROWS,
  "unvalidated_constraints": $UNVALIDATED_CONSTRAINTS,
  "invalid_or_not_ready_indexes": $INVALID_INDEXES,
  "unpopulated_materialized_views": $UNPOPULATED_MATERIALIZED_VIEWS,
  "keep_db": $([[ "$KEEP_DB" -eq 1 ]] && echo true || echo false)
}
EOF
  ok "wrote rehearsal receipt: $RECEIPT_FILE"
fi

if [[ "$KEEP_DB" -ne 1 ]]; then
  say "Drop disposable rehearsal database"
  dc exec -T postgres dropdb -U edfinder --if-exists "$TARGET_DB"
  TARGET_MAY_EXIST=0
  ok "dropped rehearsal database: $TARGET_DB"
fi

echo
echo "Restore rehearsal complete."
echo "  Backup file:        $BACKUP_FILE"
echo "  Target DB:          $TARGET_DB"
echo "  Public tables:      $PUBLIC_TABLES"
echo "  Schema migrations:  $SCHEMA_MIGRATIONS"
echo "  Systems rows:       $SYSTEM_ROWS"
echo "  Sol + Colonia:      $KNOWN_SYSTEMS/2"
echo "  Bodies bytes:       $BODIES_BYTES"
echo "  Ratings bytes:      $RATINGS_BYTES"
echo "  Stations rows:      $STATION_ROWS"
echo "  Invalid indexes:    $INVALID_INDEXES"
echo "  Unpopulated MVs:    $UNPOPULATED_MATERIALIZED_VIEWS"
