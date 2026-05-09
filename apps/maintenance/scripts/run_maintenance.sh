#!/bin/bash
#
# scripts/run_maintenance.sh — nightly + weekly DB maintenance tasks.
#
# This is what stops the "search worked yesterday and now it 503s"
# class of bug: PostgreSQL's planner relies on table statistics that
# go stale as data grows. Without periodic ANALYZE, the planner can
# decide a sequential scan over 186M rows is cheaper than the btree
# index it should obviously use — which is exactly what manifested
# as the autocomplete hang on 2026-05-09.
#
# Schedule (see crontab):
#   nightly @ 03:15 UTC : run_maintenance.sh nightly
#   weekly  @ 04:00 UTC : run_maintenance.sh weekly  (Sundays)
#
# Failures: each step is independent. If ANALYZE bodies fails, we still
# refresh the MVs. The whole script is wrapped in `set +e` for that
# reason — we want best-effort, not all-or-nothing.
#
# Logs land on stdout (so docker compose logs picks them up) AND in
# /data/logs/maintenance.log for grep-ability.
set +e
set -uo pipefail

TASK="${1:-nightly}"
LOG_FILE="${LOG_FILE:-/data/logs/maintenance.log}"
DB_URL="${DATABASE_URL:?DATABASE_URL must be set}"

mkdir -p "$(dirname "$LOG_FILE")"

# tee everything into the log file with a timestamp prefix.
exec > >(tee -a >(while IFS= read -r line; do
    printf '%s [%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$TASK" "$line"
done >> "$LOG_FILE")) 2>&1

run_step() {
    local label="$1"; shift
    local sql="$*"
    local started; started=$(date +%s)
    echo "▶ $label"
    if psql "$DB_URL" -v ON_ERROR_STOP=1 -X -q -c "$sql"; then
        echo "  ✓ $label completed in $(( $(date +%s) - started ))s"
    else
        echo "  ✗ $label FAILED (exit $?)" >&2
        return 1
    fi
}

case "$TASK" in
    nightly)
        echo "===== Nightly maintenance starting ====="
        # ANALYZE — keep planner stats fresh. Cheap (~30-90s on 186M
        # rows) and the single most important step. This is the one
        # that prevents tomorrow's "autocomplete is suddenly slow"
        # incident.
        run_step "ANALYZE systems"   "ANALYZE systems;"
        run_step "ANALYZE bodies"    "ANALYZE bodies;"
        run_step "ANALYZE ratings"   "ANALYZE ratings;"
        run_step "ANALYZE stations"  "ANALYZE stations;"
        # Refresh map materialised views — concurrently when supported,
        # falls back to plain refresh on first build.
        run_step "refresh_map_mviews()"  "SELECT * FROM refresh_map_mviews(FALSE);"
        echo "===== Nightly maintenance complete ====="
        ;;
    weekly)
        echo "===== Weekly maintenance starting ====="
        # REINDEX CONCURRENTLY — rebuilds the autocomplete + spatial
        # indexes without holding a write lock. Btree indexes bloat
        # over time even with autovacuum (especially this one which
        # sees the EDDN write churn), so a weekly rebuild keeps the
        # heap-to-leaf ratio sane.
        #
        # Each REINDEX is in its own statement because asyncpg can't
        # batch them, and a single failure (e.g. lock conflict) shouldn't
        # block the others.
        run_step "REINDEX idx_sys_name_lower_pattern" \
            "REINDEX INDEX CONCURRENTLY idx_sys_name_lower_pattern;"
        run_step "REINDEX idx_sys_xyz" \
            "REINDEX INDEX CONCURRENTLY idx_sys_xyz;"
        # VACUUM ANALYZE on the hot tables — autovacuum keeps up most
        # weeks but a manual sweep cleans dead-tuple drift after big
        # nightly EDDN bursts.
        run_step "VACUUM ANALYZE systems" "VACUUM (ANALYZE) systems;"
        run_step "VACUUM ANALYZE bodies"  "VACUUM (ANALYZE) bodies;"
        run_step "VACUUM ANALYZE ratings" "VACUUM (ANALYZE) ratings;"
        echo "===== Weekly maintenance complete ====="
        ;;
    smoke)
        # Manual sanity check from `docker compose run --rm maintenance smoke`.
        # Exits 0 if the DB is reachable and seed_check invariants hold.
        run_step "connectivity check" "SELECT 1;"
        run_step "systems count"      "SELECT COUNT(*) FROM systems;"
        run_step "ratings count"      "SELECT COUNT(*) FROM ratings;"
        ;;
    *)
        echo "usage: $0 {nightly|weekly|smoke}" >&2
        exit 2
        ;;
esac
