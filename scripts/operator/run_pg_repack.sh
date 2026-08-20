#!/usr/bin/env bash
# Explicit production pg_repack operator wrapper. Read-only check is the
# default; a rewrite requires --run, one --table, and --confirm.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="check"
TARGET_TABLE=""
CONFIRMED=0
ALLOW_LOW_DISK=0
WAIT_TIMEOUT="${PG_REPACK_WAIT_TIMEOUT:-60}"
JOBS="${PG_REPACK_JOBS:-1}"
FREE_SPACE_MULTIPLE="${PG_REPACK_FREE_SPACE_MULTIPLE:-2}"
DB_USER="${PG_REPACK_DB_USER:-edfinder}"
DB_NAME="${PG_REPACK_DB_NAME:-edfinder}"
LOG_FILE="${PG_REPACK_LOG_FILE:-/data/logs/pg_repack.log}"
LOCK_DIR="${PG_REPACK_LOCK_DIR:-/data/logs/pg_repack.lock}"

usage() {
    cat <<'EOF'
Usage:
  scripts/operator/run_pg_repack.sh
  scripts/operator/run_pg_repack.sh --run --table public.ratings --confirm

The default is a read-only dead-tuple pressure report. A rewrite is limited to
one explicitly named public table and fails closed on restore/import activity
or insufficient conservative disk headroom.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) MODE="check"; shift ;;
        --run) MODE="run"; shift ;;
        --table) TARGET_TABLE="${2:-}"; shift 2 ;;
        --confirm) CONFIRMED=1; shift ;;
        --allow-low-disk) ALLOW_LOW_DISK=1; shift ;;
        --wait-timeout) WAIT_TIMEOUT="${2:-}"; shift 2 ;;
        --jobs) JOBS="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[[ "$WAIT_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || die "--wait-timeout must be a positive integer"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "--jobs must be a positive integer"
[[ "$FREE_SPACE_MULTIPLE" =~ ^[1-9][0-9]*$ ]] || die "PG_REPACK_FREE_SPACE_MULTIPLE must be a positive integer"

cd "$ROOT_DIR"
# shellcheck source=scripts/operator/require_hetzner_operator_env.sh
source scripts/operator/require_hetzner_operator_env.sh

dc() {
    docker compose "$@"
}

psql_query() {
    dc exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -X -Atc "$1"
}

print_pressure_report() {
    dc exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -X -c "
WITH pressure AS (
    SELECT schemaname, relname, pg_total_relation_size(relid) AS total_bytes,
           n_live_tup, n_dead_tup,
           CASE WHEN n_live_tup + n_dead_tup = 0 THEN 0::numeric
                ELSE round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
           END AS dead_percent,
           last_autovacuum, last_autoanalyze
    FROM pg_stat_user_tables
    WHERE schemaname = 'public'
)
SELECT format('%I.%I', schemaname, relname) AS table_name,
       pg_size_pretty(total_bytes) AS total_size,
       n_live_tup, n_dead_tup, dead_percent,
       last_autovacuum, last_autoanalyze
FROM pressure
ORDER BY total_bytes DESC
LIMIT 30;"
    printf '%s\n' "NOTE: this is tuple pressure, not a physical-bloat measurement."
}

if [[ "$MODE" == "check" ]]; then
    [[ -z "$TARGET_TABLE" ]] || die "--table is only valid with --run"
    [[ "$CONFIRMED" -eq 0 ]] || die "--confirm is only valid with --run"
    print_pressure_report
    exit 0
fi

[[ "$TARGET_TABLE" =~ ^public[.][a-z_][a-z0-9_]*$ ]] || \
    die "--table must name exactly one unquoted public table (for example public.ratings)"
[[ "$CONFIRMED" -eq 1 ]] || \
    die "refusing table rewrite without --confirm; run the default read-only check first"

mkdir -p "$(dirname "$LOG_FILE")"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    die "another pg_repack operator run appears active: $LOCK_DIR"
fi
cleanup_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup_lock EXIT
exec > >(tee -a "$LOG_FILE") 2>&1

echo "===== pg_repack operator run starting $(date -u +'%Y-%m-%dT%H:%M:%SZ') ====="
echo "target table: $TARGET_TABLE"

if docker ps --format '{{.Names}}' | grep -Eq 'importer|build_(ratings|topology|clusters|regional|grid|archetype)'; then
    die "an importer or application rebuild container is active"
fi

active_restores="$(psql_query "SELECT count(*) FROM pg_stat_activity WHERE application_name = 'pg_restore';")"
[[ "$active_restores" == "0" ]] || die "pg_restore is active; repack must wait"

dc exec -T postgres pg_repack --version

extension_present="$(psql_query "SELECT count(*) FROM pg_extension WHERE extname = 'pg_repack';")"
[[ "$extension_present" == "0" || "$extension_present" == "1" ]] || \
    die "could not determine pg_repack extension state"

table_bytes="$(psql_query "SELECT pg_total_relation_size(to_regclass('$TARGET_TABLE'));")"
[[ "$table_bytes" =~ ^[1-9][0-9]*$ ]] || die "target table does not exist or has no measurable size"
free_bytes="$(dc exec -T postgres df -PB1 /var/lib/postgresql/data | awk 'NR == 2 {print $4}' | tr -d '[:space:]')"
[[ "$free_bytes" =~ ^[0-9]+$ ]] || die "could not determine PostgreSQL volume free space"
required_bytes=$((table_bytes * FREE_SPACE_MULTIPLE))

echo "table total bytes: $table_bytes"
echo "volume free bytes: $free_bytes"
echo "conservative required free bytes: $required_bytes (${FREE_SPACE_MULTIPLE}x table+indexes)"
if (( free_bytes < required_bytes )) && [[ "$ALLOW_LOW_DISK" -ne 1 ]]; then
    die "insufficient conservative disk headroom; investigate actual bloat or use --allow-low-disk only after an explicit operator review"
fi

if [[ "$extension_present" == "0" ]]; then
    echo "pg_repack extension is absent; installing it after successful read-only preflight"
    dc exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -X \
        -c "CREATE EXTENSION pg_repack;"
fi

echo "running pg_repack dry-run preflight"
dc exec -T postgres pg_repack \
    -U "$DB_USER" -d "$DB_NAME" \
    --table "$TARGET_TABLE" \
    --dry-run

echo "running pg_repack table rewrite"
dc exec -T postgres pg_repack \
    -U "$DB_USER" -d "$DB_NAME" \
    --table "$TARGET_TABLE" \
    --wait-timeout "$WAIT_TIMEOUT" \
    --jobs "$JOBS" \
    --no-kill-backend

post_bytes="$(psql_query "SELECT pg_total_relation_size(to_regclass('$TARGET_TABLE'));")"
echo "post-repack table total bytes: $post_bytes"
echo "===== pg_repack operator run complete $(date -u +'%Y-%m-%dT%H:%M:%SZ') ====="
