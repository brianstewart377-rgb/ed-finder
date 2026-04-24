#!/bin/bash
# =============================================================================
# ED Finder — Nightly Update Script
# Runs at 02:00 daily via cron.
#
# Strategy:
#   - Daily:   download systems_1day.json.gz (~3.7 MB) — fast system enrichment
#   - Weekly:  download systems_1week.json.gz (~27 MB) — catch any missed days
#   - Monthly: re-download galaxy_populated.json.gz (~3.6 GB) — full faction refresh
#   - galaxy.json.gz is NOT re-downloaded nightly (it's 102 GB — only for full
#     re-imports after a major Spansh schema change, done manually)
#
# EDDN listener handles real-time updates continuously (colonisation, new
# discoveries, body scans) — this script fills in bulk Spansh changes.
# =============================================================================
set -euo pipefail

LOG=/data/logs/nightly.log
DUMP_DIR=/data/dumps
COMPOSE=/opt/ed-finder

log()     { echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO]  $*" | tee -a "$LOG"; }
warn()    { echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN]  $*" | tee -a "$LOG"; }
success() { echo "$(date '+%Y-%m-%d %H:%M:%S') [OK]    $*" | tee -a "$LOG"; }

log "=== Nightly update started ==="
cd "$COMPOSE"

# Determine day of week (1=Mon … 7=Sun) and day of month
DOW=$(date +%u)
DOM=$(date +%d)

# ---------------------------------------------------------------------------
# 1. Download Spansh delta files
# ---------------------------------------------------------------------------
log "Downloading Spansh delta files ..."

download_if_stale() {
    local url="$1"
    local dest="$2"
    local max_age_hours="${3:-23}"
    local max_age_secs=$(( max_age_hours * 3600 ))

    if [[ -f "$dest" ]]; then
        local age=$(( $(date +%s) - $(stat -c %Y "$dest") ))
        if (( age < max_age_secs )); then
            log "$(basename $dest) is fresh (${age}s old) — skipping"
            return 0
        fi
    fi

    log "Downloading $(basename $dest) ..."
    wget -q --show-progress -O "${dest}.tmp" "$url" \
        && mv "${dest}.tmp" "$dest" \
        && success "Downloaded $(basename $dest) ($(du -sh $dest | cut -f1))" \
        || { warn "Download failed: $url"; rm -f "${dest}.tmp"; return 1; }
}

# Always: 1-day delta (~3.7 MB)
download_if_stale \
    "https://downloads.spansh.co.uk/systems_1day.json.gz" \
    "$DUMP_DIR/systems_1day.json.gz" \
    23

# Weekly (every Monday): 1-week delta (~27 MB) to catch any missed days
if [[ "$DOW" == "1" ]]; then
    download_if_stale \
        "https://downloads.spansh.co.uk/systems_1week.json.gz" \
        "$DUMP_DIR/systems_1week.json.gz" \
        167
fi

# Monthly (1st of month): re-download galaxy_populated for full faction refresh (~3.6 GB)
if [[ "$DOM" == "01" ]]; then
    log "Monthly refresh: downloading galaxy_populated.json.gz (~3.6 GB) ..."
    download_if_stale \
        "https://downloads.spansh.co.uk/galaxy_populated.json.gz" \
        "$DUMP_DIR/galaxy_populated.json.gz" \
        700
fi

# Always: galaxy_stations.json.gz is refreshed hourly by Spansh — keep it current
download_if_stale \
    "https://downloads.spansh.co.uk/galaxy_stations.json.gz" \
    "$DUMP_DIR/galaxy_stations.json.gz" \
    23

# ---------------------------------------------------------------------------
# 2. Import 1-day systems delta
# ---------------------------------------------------------------------------
log "Importing 1-day systems delta ..."
docker compose --profile import run --rm importer \
    python3 import_spansh.py --file systems_1day.json.gz \
    >> "$LOG" 2>&1 \
    && success "1-day delta imported" \
    || warn "1-day delta import had errors — check $LOG"

# Weekly: import 1-week delta (Mon only)
if [[ "$DOW" == "1" ]]; then
    log "Importing 1-week systems delta ..."
    docker compose --profile import run --rm importer \
        python3 import_spansh.py --file systems_1week.json.gz \
        >> "$LOG" 2>&1 \
        && success "1-week delta imported" \
        || warn "1-week delta import had errors"
fi

# Monthly: re-import galaxy_populated (1st only)
if [[ "$DOM" == "01" ]]; then
    log "Monthly: re-importing galaxy_populated.json.gz ..."
    docker compose --profile import run --rm importer \
        python3 import_spansh.py --file galaxy_populated.json.gz \
        >> "$LOG" 2>&1 \
        && success "galaxy_populated imported" \
        || warn "galaxy_populated import had errors"
fi

# Always: refresh station data (Spansh updates this hourly)
log "Refreshing station data ..."
docker compose --profile import run --rm importer \
    python3 import_spansh.py --file galaxy_stations.json.gz \
    >> "$LOG" 2>&1 \
    && success "Station data refreshed" \
    || warn "Station refresh had errors"

# ---------------------------------------------------------------------------
# 3. Re-rate dirty systems (EDDN + delta updates set rating_dirty=TRUE)
# ---------------------------------------------------------------------------
DIRTY_COUNT=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc \
    "SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE" 2>/dev/null || echo "0")
log "Dirty systems to re-rate: $DIRTY_COUNT"

if (( DIRTY_COUNT > 0 )); then
    log "Re-rating dirty systems ..."
    docker compose --profile import run --rm importer \
        python3 build_ratings.py --dirty \
        >> "$LOG" 2>&1 \
        && success "Dirty ratings rebuilt ($DIRTY_COUNT systems)" \
        || warn "Rating rebuild had errors"
fi

# ---------------------------------------------------------------------------
# 4. Rebuild dirty clusters
# ---------------------------------------------------------------------------
DIRTY_CLUSTERS=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc \
    "SELECT COUNT(*) FROM systems WHERE cluster_dirty = TRUE" 2>/dev/null || echo "0")

if (( DIRTY_CLUSTERS > 0 )); then
    log "Rebuilding dirty clusters ($DIRTY_CLUSTERS systems) ..."
    docker compose --profile import run --rm importer \
        python3 build_clusters.py --dirty-only \
        >> "$LOG" 2>&1 \
        && success "Dirty clusters rebuilt" \
        || warn "Cluster rebuild had errors"
fi

# ---------------------------------------------------------------------------
# 5. Clear Redis cache (stale search results after data update)
# ---------------------------------------------------------------------------
log "Clearing Redis cache ..."
docker compose exec -T redis redis-cli FLUSHDB >> "$LOG" 2>&1 \
    && success "Redis cache cleared" \
    || warn "Redis flush failed"

# ---------------------------------------------------------------------------
# 6. Update last_nightly_update in app_meta
# ---------------------------------------------------------------------------
docker compose exec -T postgres psql -U edfinder -d edfinder -c \
    "INSERT INTO app_meta(key,value,updated_at)
     VALUES('last_nightly_update','$(date -u +%Y-%m-%dT%H:%M:%SZ)',NOW())
     ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()" \
    >> "$LOG" 2>&1

# ---------------------------------------------------------------------------
# 7. VACUUM ANALYZE (keep query planner stats current)
# ---------------------------------------------------------------------------
log "Running VACUUM ANALYZE ..."
docker compose exec -T postgres psql -U edfinder -d edfinder -c \
    "VACUUM ANALYZE systems; VACUUM ANALYZE ratings; VACUUM ANALYZE cluster_summary; VACUUM ANALYZE stations;" \
    >> "$LOG" 2>&1 \
    && success "VACUUM ANALYZE complete" \
    || warn "VACUUM failed"

# ---------------------------------------------------------------------------
# 8. Stats
# ---------------------------------------------------------------------------
DISK_USED=$(df -h /data | awk 'NR==2{print $3 "/" $2 " (" $5 ")"}')
PG_SIZE=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc \
    "SELECT pg_size_pretty(pg_database_size('edfinder'))" 2>/dev/null || echo "unknown")
SYS_COUNT=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc \
    "SELECT TO_CHAR(COUNT(*), '999,999,999') FROM systems" 2>/dev/null || echo "unknown")

log "Systems: $SYS_COUNT | Disk: $DISK_USED | PostgreSQL DB: $PG_SIZE"
log "=== Nightly update complete ==="
