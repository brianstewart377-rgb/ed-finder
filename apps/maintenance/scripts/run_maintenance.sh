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
# refresh the MVs. The script records every failed step and exits non-zero
# after the remaining best-effort work has completed.
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
MAINTENANCE_PGOPTIONS="${PGOPTIONS:+${PGOPTIONS} }-c statement_timeout=0"
FAILED_STEPS=0
FAILED_LABELS=()

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
    if PGOPTIONS="$MAINTENANCE_PGOPTIONS" psql "$DB_URL" -v ON_ERROR_STOP=1 -X -q -c "$sql"; then
        echo "  ✓ $label completed in $(( $(date +%s) - started ))s"
    else
        local psql_exit=$?
        FAILED_STEPS=$((FAILED_STEPS + 1))
        FAILED_LABELS+=("$label")
        echo "  ✗ $label FAILED (exit $psql_exit)" >&2
        return "$psql_exit"
    fi
}

finish_task() {
    local label="$1"
    if (( FAILED_STEPS > 0 )); then
        echo "===== $label maintenance FAILED: $FAILED_STEPS step(s): ${FAILED_LABELS[*]} =====" >&2
        if [[ "$label" == "Nightly" || "$label" == "Weekly" ]]; then
            _maintenance_heartbeat fail
        fi
        return 1
    fi
    echo "===== $label maintenance complete ====="
    if [[ "$label" == "Nightly" || "$label" == "Weekly" ]]; then
        _maintenance_heartbeat success
    fi
}

_maintenance_heartbeat() {
    # $1 = "success" | "fail". Pings the healthchecks check so a failed
    # maintenance run is not silent. Ping delivery never changes exit status.
    local outcome="$1"
    local url="${MAINTENANCE_HEARTBEAT_URL:-}"
    if [[ -z "$url" ]]; then
        return 0
    fi
    if [[ "$outcome" == "fail" ]]; then
        url="${url%/}/fail"
    fi
    if curl -fsS -m 10 --retry 3 "$url" >/dev/null 2>&1; then
        echo "maintenance heartbeat: sent ($outcome)"
    else
        echo "maintenance heartbeat: delivery failed (curl); outcome was $outcome" >&2
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
        # Refresh populated map materialised views concurrently so readers
        # remain available throughout the maintenance run.
        run_step "refresh_map_mviews()"  \
            "SET statement_timeout = '60min'; SELECT * FROM refresh_map_mviews(TRUE);"
        # mv_archetype_rankings refresh (moved here 2026-08-08 from
        # scripts/nightly_update.sh — see that script's comment above
        # NIGHTLY_PGOPTIONS). It used to need its own fixed nightly
        # statement_timeout, and kept outgrowing it as the view grew
        # (6m30s at 10M rows on 2026-07-15, per known-issues.md, up to
        # 52m33s at 20M rows by this move) — worse than linear growth, so
        # picking a bigger fixed number here would just repeat the same
        # bug. No inline SET: this inherits MAINTENANCE_PGOPTIONS'
        # genuinely unbounded statement_timeout=0, the budget this kind of
        # long-running, independent, best-effort step is meant to have.
        # nightly_update.sh (02:00 UTC) rebuilds the underlying
        # system_archetype_scores rows on its own schedule before this
        # task runs (03:15 UTC) — a 75-minute assumption, not a guarantee.
        # If that rebuild (e.g. the --limit 5000000 new-system backfill)
        # is still running past 03:15, this refresh reflects the
        # scores as of 03:15, not that night's finished rebuild. Low
        # impact and self-healing (this step is unconditional and runs
        # again every night regardless), but a real gap: there is
        # currently no explicit ordering/wait between the two schedules.
        run_step "refresh mv_archetype_rankings" \
            "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;"
        finish_task "Nightly"
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
        run_step "REINDEX idx_sys_coords" \
            "REINDEX INDEX CONCURRENTLY idx_sys_coords;"
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
       OR record_status = 'archived'
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
        finish_task "Weekly"
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
        finish_task "Smoke"
        ;;
    *)
        echo "usage: $0 {nightly|weekly|smoke}" >&2
        exit 2
        ;;
esac
