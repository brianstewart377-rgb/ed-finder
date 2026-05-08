#!/usr/bin/env bash
# scripts/refresh_map_mviews.sh
# ─────────────────────────────────────────────────────────────────────────────
# Refresh ED Finder's map aggregation materialised views.
#
# Audit fix (2026-05-08, AUDIT_REPORT.md §C4 / Phase 5): /api/map/regions,
# /api/map/heatmap, and /api/map/timeline now read from materialised views
# refreshed by this script. Run nightly + after each completed
# build_ratings.py / cluster rebuild.
#
# Usage:
#   ./scripts/refresh_map_mviews.sh            # CONCURRENT refresh (no read lock)
#   ./scripts/refresh_map_mviews.sh --first    # non-concurrent (first run after CREATE)
#
# Schedule (add to crontab via setup.sh):
#   30 03 * * * /opt/ed-finder/scripts/refresh_map_mviews.sh >> /var/log/ed-finder/mv_refresh.log 2>&1
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

CONCURRENT="TRUE"
if [[ "${1:-}" == "--first" ]]; then
    CONCURRENT="FALSE"
fi

# Use the importer container's direct-PG path (bypasses pgBouncer because
# REFRESH MATERIALIZED VIEW CONCURRENTLY needs a session-mode connection).
DSN="${DATABASE_URL_DIRECT:-postgresql://edfinder:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}@postgres:5432/edfinder}"

echo "[$(date -Iseconds)] refresh_map_mviews — CONCURRENT=$CONCURRENT"
psql "$DSN" -X --tuples-only --no-align <<SQL
SELECT format('  %-32s  %8.1f ms', name, refresh_ms)
FROM refresh_map_mviews($CONCURRENT);
SQL
echo "[$(date -Iseconds)] done"
