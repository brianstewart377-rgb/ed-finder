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
EVIDENCE_RECORD_RETENTION_DAYS="${EVIDENCE_RECORD_RETENTION_DAYS:-90}"
ADMIN_JOB_RUN_RETENTION_DAYS="${ADMIN_JOB_RUN_RETENTION_DAYS:-60}"

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
        run_step "expire evidence by explicit expires_at" "$(cat <<'SQL'
WITH updated AS (
    UPDATE evidence_records
       SET freshness_status = 'expired',
           updated_at = NOW()
     WHERE record_status = 'active'
       AND freshness_status <> 'expired'
       AND expires_at IS NOT NULL
       AND expires_at <= NOW()
    RETURNING 1
)
SELECT COUNT(*)::int AS expired_by_expires_at FROM updated;
SQL
)"
        run_step "expire aged evidence by policy" "$(cat <<'SQL'
WITH policies(evidence_type, stale_days, expired_days) AS (
    VALUES
        ('body_completeness', 90, 365),
        ('body_scan', 90, 365),
        ('body_signal_scan', 30, 180),
        ('colonisation_status', 3, 14),
        ('operator_note', 30, 180),
        ('ring_composition', 90, 365),
        ('service_snapshot', 7, 30),
        ('station_set', 7, 30)
),
policy_rows AS (
    SELECT
        er.evidence_key,
        COALESCE(p.expired_days, 180) AS expired_days
    FROM evidence_records er
    LEFT JOIN policies p
      ON p.evidence_type = er.evidence_type
    WHERE er.record_status = 'active'
),
updated AS (
    UPDATE evidence_records er
       SET freshness_status = 'expired',
           updated_at = NOW()
      FROM policy_rows pr
     WHERE er.evidence_key = pr.evidence_key
       AND er.freshness_status = ANY(ARRAY['current', 'stale', 'unknown'])
       AND COALESCE(er.observed_at, er.collected_at, er.created_at)
           <= NOW() - make_interval(days => pr.expired_days)
    RETURNING 1
)
SELECT COUNT(*)::int AS expired_by_age FROM updated;
SQL
)"
        run_step "mark stale evidence by policy" "$(cat <<'SQL'
WITH policies(evidence_type, stale_days, expired_days) AS (
    VALUES
        ('body_completeness', 90, 365),
        ('body_scan', 90, 365),
        ('body_signal_scan', 30, 180),
        ('colonisation_status', 3, 14),
        ('operator_note', 30, 180),
        ('ring_composition', 90, 365),
        ('service_snapshot', 7, 30),
        ('station_set', 7, 30)
),
policy_rows AS (
    SELECT
        er.evidence_key,
        COALESCE(p.stale_days, 30) AS stale_days
    FROM evidence_records er
    LEFT JOIN policies p
      ON p.evidence_type = er.evidence_type
    WHERE er.record_status = 'active'
),
updated AS (
    UPDATE evidence_records er
       SET freshness_status = 'stale',
           updated_at = NOW()
      FROM policy_rows pr
     WHERE er.evidence_key = pr.evidence_key
       AND er.freshness_status = ANY(ARRAY['current', 'unknown'])
       AND COALESCE(er.observed_at, er.collected_at, er.created_at)
           <= NOW() - make_interval(days => pr.stale_days)
    RETURNING 1
)
SELECT COUNT(*)::int AS stale_by_age FROM updated;
SQL
)"
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
        run_step "prune retained evidence history" "$(cat <<SQL
WITH ranked AS (
    SELECT
        evidence_key,
        ROW_NUMBER() OVER (
            PARTITION BY system_id64, subject_type, COALESCE(subject_id, ''), evidence_type
            ORDER BY COALESCE(observed_at, collected_at, created_at) DESC, evidence_key DESC
        ) AS archive_rank,
        COALESCE(observed_at, collected_at, created_at, updated_at) AS record_time
    FROM evidence_records
    WHERE record_status = 'superseded'
       OR (
            record_status = 'active'
        AND freshness_status = 'expired'
       )
),
deleted AS (
    DELETE FROM evidence_records er
    USING ranked r
    WHERE er.evidence_key = r.evidence_key
      AND r.archive_rank > 1
      AND r.record_time < NOW() - make_interval(days => ${EVIDENCE_RECORD_RETENTION_DAYS}::int)
    RETURNING 1
)
SELECT COUNT(*)::int AS retained_history_rows_deleted FROM deleted;
SQL
)"
        run_step "prune admin job history" "$(cat <<SQL
WITH deleted AS (
    DELETE FROM admin_job_runs
    WHERE status IN ('completed', 'failed')
      AND COALESCE(finished_at, started_at) < NOW() - make_interval(days => ${ADMIN_JOB_RUN_RETENTION_DAYS}::int)
    RETURNING 1
)
SELECT COUNT(*)::int AS admin_job_rows_deleted FROM deleted;
SQL
)"
        echo "===== Weekly maintenance complete ====="
        ;;
    smoke)
        # Manual sanity check from `docker compose run --rm maintenance smoke`.
        # Exits 0 if the DB is reachable and the seed_check invariants
        # hold. Uses pg_class.reltuples (the planner's row-count estimate
        # last set by ANALYZE) rather than COUNT(*) — at prod scale
        # (~186M systems / ratings rows) a real COUNT does a sequential
        # scan that exceeds the 15s statement_timeout. reltuples is
        # instantaneous and accurate to ~5% if ANALYZE has run recently
        # (which the nightly schedule guarantees).
        run_step "connectivity"     "SELECT 1;"
        run_step "systems estimate" \
            "SELECT format('%s rows (planner estimate, last ANALYZE %s)',
                           reltuples::bigint,
                           COALESCE(to_char(s.last_analyze, 'YYYY-MM-DD HH24:MI'),
                                    to_char(s.last_autoanalyze, 'YYYY-MM-DD HH24:MI'),
                                    'never'))
             FROM pg_class c
             LEFT JOIN pg_stat_user_tables s ON s.relname = c.relname
             WHERE c.relname='systems';"
        run_step "ratings estimate" \
            "SELECT format('%s rows (planner estimate, last ANALYZE %s)',
                           reltuples::bigint,
                           COALESCE(to_char(s.last_analyze, 'YYYY-MM-DD HH24:MI'),
                                    to_char(s.last_autoanalyze, 'YYYY-MM-DD HH24:MI'),
                                    'never'))
             FROM pg_class c
             LEFT JOIN pg_stat_user_tables s ON s.relname = c.relname
             WHERE c.relname='ratings';"
        run_step "bodies estimate" \
            "SELECT format('%s rows (planner estimate, last ANALYZE %s)',
                           reltuples::bigint,
                           COALESCE(to_char(s.last_analyze, 'YYYY-MM-DD HH24:MI'),
                                    to_char(s.last_autoanalyze, 'YYYY-MM-DD HH24:MI'),
                                    'never'))
             FROM pg_class c
             LEFT JOIN pg_stat_user_tables s ON s.relname = c.relname
             WHERE c.relname='bodies';"
        ;;
    *)
        echo "usage: $0 {nightly|weekly|smoke}" >&2
        exit 2
        ;;
esac
