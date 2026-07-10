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
bash scripts/restore_postgres_backup.sh "${restore_args[@]}"
ok "restore helper completed"

say "Collect readiness markers"
PUBLIC_TABLES="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
)"
SCHEMA_MIGRATIONS="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM schema_migrations;"
)"
ok "public tables visible: $PUBLIC_TABLES"
ok "schema migrations visible: $SCHEMA_MIGRATIONS"

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
  "keep_db": $([[ "$KEEP_DB" -eq 1 ]] && echo true || echo false)
}
EOF
  ok "wrote rehearsal receipt: $RECEIPT_FILE"
fi

if [[ "$KEEP_DB" -ne 1 ]]; then
  say "Drop disposable rehearsal database"
  dc exec -T postgres dropdb -U edfinder --if-exists "$TARGET_DB"
  ok "dropped rehearsal database: $TARGET_DB"
fi

echo
echo "Restore rehearsal complete."
echo "  Backup file:        $BACKUP_FILE"
echo "  Target DB:          $TARGET_DB"
echo "  Public tables:      $PUBLIC_TABLES"
echo "  Schema migrations:  $SCHEMA_MIGRATIONS"
