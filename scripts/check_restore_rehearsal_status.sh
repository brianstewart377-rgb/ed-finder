#!/usr/bin/env bash
#
# Inspect a restore rehearsal without mutating the target database.
# Useful both for light progress checks and for the final finish-state probe.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DB="${TARGET_DB:-edfinder_restore_rehearsal}"
RECEIPT_FILE="${RECEIPT_FILE:-}"
WAIT_FOR_FINISH=0
POLL_SECONDS="${POLL_SECONDS:-30}"
COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"
COMPOSE_PROJECT_NAME_OVERRIDE="${EDFINDER_DOCKER_PROJECT_NAME:-}"

say() { printf "\n[INFO] %s\n" "$*"; }
ok() { printf "[OK]   %s\n" "$*"; }
warn() { printf "[WARN] %s\n" "$*" >&2; }
die() { printf "[ERROR] %s\n" "$*" >&2; exit 1; }

compose_args=()

usage() {
  sed -n '1,14p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-db) TARGET_DB="$2"; shift 2 ;;
    --receipt-file) RECEIPT_FILE="$2"; shift 2 ;;
    --compose-file) COMPOSE_FILE_OVERRIDE="$2"; shift 2 ;;
    --project-name) COMPOSE_PROJECT_NAME_OVERRIDE="$2"; shift 2 ;;
    --poll-seconds) POLL_SECONDS="$2"; shift 2 ;;
    --wait) WAIT_FOR_FINISH=1; shift ;;
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
command -v ps >/dev/null || die "ps not found"

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

restore_process_lines() {
  ps -eo pid=,etimes=,args= | grep '[p]g_restore' | grep -F " -d $TARGET_DB" || true
}

database_exists() {
  dc exec -T postgres psql -U edfinder -lqt | cut -d '|' -f 1 | sed 's/[[:space:]]*$//' | grep -Fxq "$TARGET_DB"
}

receipt_exists() {
  [[ -n "$RECEIPT_FILE" && -f "$RECEIPT_FILE" ]]
}

show_receipt() {
  [[ -n "$RECEIPT_FILE" ]] || return 0
  if [[ -f "$RECEIPT_FILE" ]]; then
    ok "receipt present: $RECEIPT_FILE"
    cat "$RECEIPT_FILE"
  else
    warn "receipt not present yet: $RECEIPT_FILE"
  fi
}

show_database_smoke() {
  local public_tables schema_migrations
  public_tables="$(
    dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
      -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
  )"
  schema_migrations="$(
    dc exec -T postgres psql -U edfinder -d "$TARGET_DB" -At \
      -c "SELECT COUNT(*) FROM schema_migrations;"
  )"
  ok "public tables visible: $public_tables"
  ok "schema migrations visible: $schema_migrations"
}

wait_for_finish() {
  local process_lines
  while true; do
    process_lines="$(restore_process_lines)"
    if [[ -z "$process_lines" ]]; then
      return 0
    fi
    say "restore still running for $TARGET_DB"
    printf '%s\n' "$process_lines"
    sleep "$POLL_SECONDS"
  done
}

dc ps postgres >/dev/null
ok "compose can see postgres"

if [[ "$WAIT_FOR_FINISH" -eq 1 ]]; then
  wait_for_finish
  ok "restore process no longer running for $TARGET_DB"
fi

process_lines="$(restore_process_lines)"
if [[ -n "$process_lines" ]]; then
  say "restore is still running for $TARGET_DB"
  printf '%s\n' "$process_lines"
else
  ok "no active pg_restore found for $TARGET_DB"
fi

if database_exists; then
  ok "target database exists: $TARGET_DB"
  if [[ -z "$process_lines" ]]; then
    show_database_smoke
  fi
else
  warn "target database not present: $TARGET_DB"
fi

show_receipt
