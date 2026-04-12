#!/bin/bash
# =============================================================================
# ED Finder — Nightly Update Script
# Runs at 02:00 daily via cron.
# Downloads latest Spansh delta dump and applies changes.
# =============================================================================
set -euo pipefail

LOG=/data/logs/nightly.log
DUMP_DIR=/data/dumps
COMPOSE=/opt/ed-finder

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

log "=== Nightly update started ==="

cd "$COMPOSE"

# 1. Download latest galaxy.json.gz delta from Spansh
# Spansh updates nightly — we check if the file is newer than 23h
log "Checking for Spansh updates ..."
GALAXY_DUMP="$DUMP_DIR/galaxy.json.gz"
GALAXY_YESTERDAY="$DUMP_DIR/galaxy_yesterday.json.gz"

if [[ -f "$GALAXY_DUMP" ]]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$GALAXY_DUMP") ))
    if (( AGE > 82800 )); then  # 23 hours
        log "galaxy.json.gz is ${AGE}s old — downloading fresh copy ..."
        [[ -f "$GALAXY_DUMP" ]] && mv "$GALAXY_DUMP" "$GALAXY_YESTERDAY"
        wget -q -O "$GALAXY_DUMP.tmp" "https://downloads.spansh.co.uk/galaxy.json.gz" \
            && mv "$GALAXY_DUMP.tmp" "$GALAXY_DUMP" \
            && log "Downloaded new galaxy.json.gz" \
            || { log "Download failed — keeping yesterday's file"; [[ -f "$GALAXY_YESTERDAY" ]] && mv "$GALAXY_YESTERDAY" "$GALAXY_DUMP"; }
    else
        log "galaxy.json.gz is fresh (${AGE}s old) — skipping download"
    fi
else
    log "galaxy.json.gz not found — run full import first"
    exit 0
fi

# 2. Run incremental import (upserts only changed systems)
log "Running incremental systems import ..."
docker compose --profile import run --rm importer \
    python3 import_spansh.py --file galaxy.json.gz --resume \
    >> "$LOG" 2>&1 \
    && log "Incremental import complete" \
    || log "WARNING: Incremental import had errors — check $LOG"

# 3. Re-rate dirty systems
log "Re-rating dirty systems ..."
docker compose --profile import run --rm importer \
    python3 build_ratings.py --dirty \
    >> "$LOG" 2>&1 \
    && log "Dirty ratings rebuilt" \
    || log "WARNING: Rating rebuild had errors"

# 4. Rebuild dirty clusters (only anchors near changed systems)
log "Rebuilding dirty clusters ..."
docker compose --profile import run --rm importer \
    python3 build_clusters.py --dirty-only \
    >> "$LOG" 2>&1 \
    && log "Dirty clusters rebuilt" \
    || log "WARNING: Cluster rebuild had errors"

# 5. Clear Redis cache (stale search results after data update)
log "Clearing Redis cache ..."
docker compose exec -T redis redis-cli FLUSHDB >> "$LOG" 2>&1 \
    && log "Redis cache cleared" \
    || log "WARNING: Redis flush failed"

# 6. Update last_nightly_update in app_meta
docker compose exec -T postgres psql -U edfinder -d edfinder -c \
    "INSERT INTO app_meta(key,value,updated_at) VALUES('last_nightly_update','$(date -u +%Y-%m-%dT%H:%M:%SZ)',NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()" \
    >> "$LOG" 2>&1

# 7. Vacuum analyze (keep query planner stats current)
log "Running VACUUM ANALYZE ..."
docker compose exec -T postgres psql -U edfinder -d edfinder -c \
    "VACUUM ANALYZE systems; VACUUM ANALYZE ratings; VACUUM ANALYZE cluster_summary;" \
    >> "$LOG" 2>&1 \
    && log "VACUUM ANALYZE complete" \
    || log "WARNING: VACUUM failed"

# 8. Disk usage report
DISK_USED=$(df -h /data | awk 'NR==2{print $3 "/" $2 " (" $5 ")"}')
PG_SIZE=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc \
    "SELECT pg_size_pretty(pg_database_size('edfinder'))" 2>/dev/null || echo "unknown")
log "Disk: $DISK_USED | PostgreSQL: $PG_SIZE"

log "=== Nightly update complete ==="
