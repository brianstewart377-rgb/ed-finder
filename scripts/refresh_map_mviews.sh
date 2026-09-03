#!/usr/bin/env bash
# scripts/refresh_map_mviews.sh
# ─────────────────────────────────────────────────────────────────────────────
# Refresh ED Finder's map aggregation materialised views.
#
# Repository helper only. This file does not authorize production scheduling or
# identify a V3 production database target. The former Hetzner `/opt/ed-finder`
# cron/setup path is retired. A current V3 workflow/runbook must explicitly
# authorize and supply any production execution context.
#
# Usage in an already appropriate environment:
#   ./scripts/refresh_map_mviews.sh            # CONCURRENT refresh (no read lock)
#   ./scripts/refresh_map_mviews.sh --first    # non-concurrent (first run after CREATE)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

CONCURRENT="TRUE"
if [[ "${1:-}" == "--first" ]]; then
    CONCURRENT="FALSE"
fi

# Repository/Compose helper default. A production V3 target must be supplied by
# an explicitly current operator path; do not infer it from this fallback.
DSN="${DATABASE_URL_DIRECT:-postgresql://edfinder:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}@postgres:5432/edfinder}"

echo "[$(date -Iseconds)] refresh_map_mviews — CONCURRENT=$CONCURRENT"
psql "$DSN" -X --tuples-only --no-align <<SQL
SELECT format('  %-32s  %8.1f ms', name, refresh_ms)
FROM refresh_map_mviews($CONCURRENT);
SQL
echo "[$(date -Iseconds)] done"
