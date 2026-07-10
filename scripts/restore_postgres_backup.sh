#!/usr/bin/env bash
#
# Restore a custom-format Postgres backup into the local docker-compose postgres
# service. Defaults to a disposable database so the normal path is non-destructive.
#
# Usage examples:
#   bash scripts/restore_postgres_backup.sh
#   bash scripts/restore_postgres_backup.sh --backup-file /data/backups/postgres/latest.dump
#   bash scripts/restore_postgres_backup.sh --target-db edfinder_restore_20260708
#   bash scripts/restore_postgres_backup.sh --target-db edfinder --allow-live-db
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_FILE="${BACKUP_FILE:-/data/backups/postgres/latest.dump}"
TARGET_DB="${TARGET_DB:-edfinder_restore}"
ALLOW_LIVE_DB=0
COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"
COMPOSE_PROJECT_NAME_OVERRIDE="${EDFINDER_DOCKER_PROJECT_NAME:-}"

say() { printf "\n[INFO] %s\n" "$*"; }
ok()  { printf "[OK]   %s\n" "$*"; }
die() { printf "[ERROR] %s\n" "$*" >&2; exit 1; }

compose_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-file)   BACKUP_FILE="$2"; shift 2 ;;
    --target-db)     TARGET_DB="$2"; shift 2 ;;
    --allow-live-db) ALLOW_LIVE_DB=1; shift ;;
    --compose-file)  COMPOSE_FILE_OVERRIDE="$2"; shift 2 ;;
    --project-name)  COMPOSE_PROJECT_NAME_OVERRIDE="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *)
      die "unknown flag: $1"
      ;;
  esac
done

cd "$REPO_DIR"

[[ -f "$BACKUP_FILE" ]] || die "backup file not found: $BACKUP_FILE"
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

if [[ "$TARGET_DB" == "edfinder" && "$ALLOW_LIVE_DB" -ne 1 ]]; then
  die "refusing to restore over live database 'edfinder' without --allow-live-db"
fi

say "Check postgres container"
dc ps postgres >/dev/null
ok "compose can see postgres"

say "Drop and recreate target database"
dc exec -T postgres dropdb -U edfinder --if-exists "$TARGET_DB"
dc exec -T postgres createdb -U edfinder "$TARGET_DB"
ok "database ready: $TARGET_DB"

say "Restore archive into $TARGET_DB"
cat "$BACKUP_FILE" | dc exec -T postgres \
  pg_restore \
    -U edfinder \
    -d "$TARGET_DB" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges
ok "archive restored"

say "Smoke-check restored database"
restored_tables="$(
  dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
    -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
)"
[[ "$restored_tables" -ge 1 ]] || die "restored database has no public tables"
ok "public tables visible: $restored_tables"

echo
echo "Restore complete."
echo "  Backup file: $BACKUP_FILE"
echo "  Target DB:   $TARGET_DB"
