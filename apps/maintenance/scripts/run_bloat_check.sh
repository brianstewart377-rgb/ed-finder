#!/bin/bash
# Read-only weekly dead-tuple pressure report. This intentionally does not run
# pg_repack: physical rewrites require an explicit operator decision per table.
set -euo pipefail

DB_URL="${DATABASE_URL:?DATABASE_URL must be set}"
LOG_FILE="${BLOAT_CHECK_LOG_FILE:-/data/logs/bloat-check.log}"
MIN_TABLE_BYTES="${BLOAT_CHECK_MIN_TABLE_BYTES:-10737418240}"
MIN_DEAD_PERCENT="${BLOAT_CHECK_MIN_DEAD_PERCENT:-20}"

[[ "$MIN_TABLE_BYTES" =~ ^[0-9]+$ ]] || {
    echo "BLOAT_CHECK_MIN_TABLE_BYTES must be a non-negative integer" >&2
    exit 2
}
[[ "$MIN_DEAD_PERCENT" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo "BLOAT_CHECK_MIN_DEAD_PERCENT must be numeric" >&2
    exit 2
}

mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "===== Dead-tuple pressure check starting $(date -u +'%Y-%m-%dT%H:%M:%SZ') ====="
psql "$DB_URL" -v ON_ERROR_STOP=1 -X \
    -v min_table_bytes="$MIN_TABLE_BYTES" \
    -v min_dead_percent="$MIN_DEAD_PERCENT" <<'SQL'
WITH table_pressure AS (
    SELECT
        schemaname,
        relname,
        pg_total_relation_size(relid) AS total_bytes,
        n_live_tup,
        n_dead_tup,
        CASE
            WHEN n_live_tup + n_dead_tup = 0 THEN 0::numeric
            ELSE round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
        END AS dead_percent,
        last_autovacuum,
        last_autoanalyze
    FROM pg_stat_user_tables
    WHERE schemaname = 'public'
)
SELECT
    format('%I.%I', schemaname, relname) AS table_name,
    pg_size_pretty(total_bytes) AS total_size,
    n_live_tup,
    n_dead_tup,
    dead_percent,
    CASE
        WHEN total_bytes >= :'min_table_bytes'::bigint
         AND dead_percent >= :'min_dead_percent'::numeric
        THEN 'review_for_repack'
        ELSE 'autovacuum_monitor'
    END AS disposition,
    last_autovacuum,
    last_autoanalyze
FROM table_pressure
ORDER BY total_bytes DESC
LIMIT 30;
SQL
echo "NOTE: pg_stat_user_tables reports tuple pressure, not a physical-bloat measurement."
echo "===== Dead-tuple pressure check complete ====="
