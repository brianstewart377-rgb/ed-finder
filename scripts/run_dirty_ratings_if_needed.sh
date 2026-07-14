#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DIRTY_RATING_THRESHOLD="${DIRTY_RATING_THRESHOLD:-250}"
DIRTY_RATING_WORKERS="${DIRTY_RATING_WORKERS:-2}"
DIRTY_RATING_CHUNK="${DIRTY_RATING_CHUNK:-1000}"
DIRTY_RATING_LOCK_FILE="${DIRTY_RATING_LOCK_FILE:-/tmp/ed-finder-dirty-ratings.lock}"

log() {
    printf '%s [dirty-ratings] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

require_positive_int() {
    local name="$1"
    local value="$2"
    [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "$name must be a positive integer, got '$value'"
}

require_non_negative_int() {
    local name="$1"
    local value="$2"
    [[ "$value" =~ ^[0-9]+$ ]] || die "$name must be a non-negative integer, got '$value'"
}

format_command() {
    printf '%q ' "$@"
}

command -v docker >/dev/null 2>&1 || die "docker is not available"
command -v flock >/dev/null 2>&1 || die "flock is not available"

require_non_negative_int "DIRTY_RATING_THRESHOLD" "$DIRTY_RATING_THRESHOLD"
require_positive_int "DIRTY_RATING_WORKERS" "$DIRTY_RATING_WORKERS"
require_positive_int "DIRTY_RATING_CHUNK" "$DIRTY_RATING_CHUNK"

cd "$REPO_ROOT"
[[ -f docker-compose.yml ]] || die "docker-compose.yml not found in $REPO_ROOT"

mkdir -p "$(dirname "$DIRTY_RATING_LOCK_FILE")"
exec 9>"$DIRTY_RATING_LOCK_FILE"

if ! flock -n 9; then
    log "another dirty ratings maintenance run is active; exiting"
    exit 0
fi

started_epoch="$(date +%s)"
started_iso="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
log "start time=$started_iso threshold=$DIRTY_RATING_THRESHOLD workers=$DIRTY_RATING_WORKERS chunk=$DIRTY_RATING_CHUNK lock=$DIRTY_RATING_LOCK_FILE"

count_cmd=(
    docker compose exec -T postgres
    psql -U edfinder -d edfinder -Atq -v ON_ERROR_STOP=1
    -c "SET statement_timeout = '30s'"
    -c "SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE;"
)
log "dirty count command: $(format_command "${count_cmd[@]}")"

if dirty_count="$("${count_cmd[@]}")"; then
    dirty_count="$(printf '%s' "$dirty_count" | tr -d '[:space:]')"
else
    status=$?
    duration=$(( "$(date +%s)" - started_epoch ))
    log "dirty count query failed exit_status=$status duration_seconds=$duration"
    exit "$status"
fi

[[ "$dirty_count" =~ ^[0-9]+$ ]] || die "dirty count query returned non-numeric output: '$dirty_count'"
log "dirty_count=$dirty_count"

if (( dirty_count < DIRTY_RATING_THRESHOLD )); then
    duration=$(( "$(date +%s)" - started_epoch ))
    log "below threshold; skipping dirty ratings rebuild exit_status=0 duration_seconds=$duration"
    exit 0
fi

run_cmd=(
    docker compose --profile import run --rm
    --entrypoint python3
    importer
    /app/build_ratings.py
    --dirty
    --workers "$DIRTY_RATING_WORKERS"
    --chunk "$DIRTY_RATING_CHUNK"
)
log "dirty ratings rebuild command: $(format_command "${run_cmd[@]}")"

set +e
"${run_cmd[@]}"
status=$?
set -e

duration=$(( "$(date +%s)" - started_epoch ))
log "dirty ratings rebuild finished exit_status=$status duration_seconds=$duration dirty_count=$dirty_count"

exit "$status"
