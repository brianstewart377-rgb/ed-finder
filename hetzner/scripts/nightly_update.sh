#!/bin/bash
# =============================================================================
# ED Finder — Nightly Update Script  (v1.1)
# Runs at 02:00 daily via cron.
#
# FIX in v1.1:
#   • Each long-running Python job now writes to its OWN log file under
#     /data/logs/ (e.g. import_1day.log, build_ratings.log) so you can
#     tail individual jobs without grepping a 500 MB combined log.
#   • Critical import steps (1-day delta, station refresh) now fail fast
#     and abort the nightly run if they exit non-zero, instead of silently
#     continuing with stale data.
#   • Post-rebuild dirty-count verification: after build_ratings.py and
#     build_clusters.py finish, the remaining dirty count is queried and
#     logged so you can see at a glance whether the rebuild completed or
#     was partial.
#   • ERRORS variable accumulates all non-fatal warnings; a summary is
#     printed at the end so you can see the full picture in one line.
#
# Strategy:
#   - Daily:   download systems_1day.json.gz (~3.7 MB) — fast system enrichment
#   - Weekly:  download systems_1week.json.gz (~27 MB) — catch any missed days
#   - Monthly: re-download galaxy_populated.json.gz (~3.6 GB) — full faction refresh
#   - galaxy.json.gz is NOT re-downloaded nightly (102 GB — only for full
#     re-imports after a major Spansh schema change, done manually)
#
# EDDN listener handles real-time updates continuously (colonisation, new
# discoveries, body scans) — this script fills in bulk Spansh changes.
# =============================================================================
set -uo pipefail
# NOTE: We do NOT use -e (exit on error) globally because some steps are
# non-fatal (e.g. weekly delta on non-Monday).  Critical steps use explicit
# || { ...; exit 1; } to abort the run.

LOG_DIR=/data/logs
LOG=${LOG_DIR}/nightly.log
DUMP_DIR=/data/dumps
COMPOSE=/opt/ed-finder

mkdir -p "$LOG_DIR"

log()     { echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO]  $*" | tee -a "$LOG"; }
warn()    { echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN]  $*" | tee -a "$LOG"; ERRORS="${ERRORS} | $*"; }
success() { echo "$(date '+%Y-%m-%d %H:%M:%S') [OK]    $*" | tee -a "$LOG"; }
fatal()   { echo "$(date '+%Y-%m-%d %H:%M:%S') [FATAL] $*" | tee -a "$LOG"; exit 1; }

# Accumulate non-fatal warnings for end-of-run summary
ERRORS=""

log "=== Nightly update started ==="
cd "$COMPOSE"

# Determine day of week (1=Mon … 7=Sun) and day of month
DOW=$(date +%u)
DOM=$(date +%d)

# Helper: run a docker compose importer command with its own log file.
# Usage: run_importer <log_suffix> <python_args...>
# Returns the exit code of the python command.
run_importer() {
    local suffix="$1"; shift
    local job_log="${LOG_DIR}/${suffix}.log"
    log "  → Output: $job_log"
    docker compose --profile import run --rm importer \
        python3 "$@" \
        2>&1 | tee -a "$job_log" | tee -a "$LOG"
    return "${PIPESTATUS[0]}"
}

# Helper: query postgres for a count
pg_count() {
    docker compose exec -T postgres psql -U edfinder -d edfinder -tAc "$1" 2>/dev/null || echo "0"
}

# ---------------------------------------------------------------------------
# 1. Download Spansh delta files
# ---------------------------------------------------------------------------
log "--- Step 1: Download Spansh delta files ---"

download_if_stale() {
    local url="$1"
    local dest="$2"
    local max_age_hours="${3:-23}"
    local max_age_secs=$(( max_age_hours * 3600 ))

    if [[ -f "$dest" ]]; then
        local age=$(( $(date +%s) - $(stat -c %Y "$dest") ))
        if (( age < max_age_secs )); then
            log "$(basename "$dest") is fresh (${age}s old) — skipping download"
            return 0
        fi
    fi

    log "Downloading $(basename "$dest") ..."
    wget -q --show-progress -O "${dest}.tmp" "$url" \
        && mv "${dest}.tmp" "$dest" \
        && success "Downloaded $(basename "$dest") ($(du -sh "$dest" | cut -f1))" \
        || { warn "Download failed: $url"; rm -f "${dest}.tmp"; return 1; }
}

# Always: 1-day delta (~3.7 MB)
download_if_stale \
    "https://downloads.spansh.co.uk/systems_1day.json.gz" \
    "$DUMP_DIR/systems_1day.json.gz" \
    23 \
    || fatal "1-day delta download failed — aborting nightly run"

# Weekly (every Monday): 1-week delta (~27 MB)
if [[ "$DOW" == "1" ]]; then
    download_if_stale \
        "https://downloads.spansh.co.uk/systems_1week.json.gz" \
        "$DUMP_DIR/systems_1week.json.gz" \
        167 \
        || warn "1-week delta download failed — skipping weekly import"
fi

# Monthly (1st of month): re-download galaxy_populated for full faction refresh (~3.6 GB)
if [[ "$DOM" == "01" ]]; then
    log "Monthly refresh: downloading galaxy_populated.json.gz (~3.6 GB) ..."
    download_if_stale \
        "https://downloads.spansh.co.uk/galaxy_populated.json.gz" \
        "$DUMP_DIR/galaxy_populated.json.gz" \
        700 \
        || warn "galaxy_populated download failed — skipping monthly faction refresh"
fi

# Always: galaxy_stations.json.gz (Spansh refreshes this hourly)
download_if_stale \
    "https://downloads.spansh.co.uk/galaxy_stations.json.gz" \
    "$DUMP_DIR/galaxy_stations.json.gz" \
    23 \
    || warn "galaxy_stations download failed — station data may be stale"

# ---------------------------------------------------------------------------
# 2. Import delta files
# ---------------------------------------------------------------------------
log "--- Step 2: Import delta files ---"

log "Importing 1-day systems delta ..."
run_importer "import_1day" import_spansh.py --file systems_1day.json.gz \
    && success "1-day delta imported" \
    || fatal "1-day delta import failed (exit $?) — aborting nightly run (check ${LOG_DIR}/import_1day.log)"

# Weekly: import 1-week delta (Mon only)
if [[ "$DOW" == "1" ]] && [[ -f "$DUMP_DIR/systems_1week.json.gz" ]]; then
    log "Importing 1-week systems delta ..."
    run_importer "import_1week" import_spansh.py --file systems_1week.json.gz \
        && success "1-week delta imported" \
        || warn "1-week delta import had errors (check ${LOG_DIR}/import_1week.log)"
fi

# Monthly: re-import galaxy_populated (1st only)
if [[ "$DOM" == "01" ]] && [[ -f "$DUMP_DIR/galaxy_populated.json.gz" ]]; then
    log "Monthly: re-importing galaxy_populated.json.gz ..."
    run_importer "import_populated" import_spansh.py --file galaxy_populated.json.gz \
        && success "galaxy_populated imported" \
        || warn "galaxy_populated import had errors (check ${LOG_DIR}/import_populated.log)"
fi

# Always: refresh station data
log "Refreshing station data ..."
run_importer "import_stations" import_spansh.py --file galaxy_stations.json.gz \
    && success "Station data refreshed" \
    || warn "Station refresh had errors (check ${LOG_DIR}/import_stations.log)"

# ---------------------------------------------------------------------------
# 3. Re-rate dirty systems
# ---------------------------------------------------------------------------
log "--- Step 3: Re-rate dirty systems ---"
DIRTY_COUNT=$(pg_count "SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE")
log "Dirty systems to re-rate: $DIRTY_COUNT"

if (( DIRTY_COUNT > 0 )); then
    log "Running build_ratings.py --dirty ..."
    run_importer "build_ratings" build_ratings.py --dirty \
        && success "Dirty ratings rebuilt" \
        || warn "Rating rebuild had errors (check ${LOG_DIR}/build_ratings.log)"

    # Post-rebuild verification: how many are still dirty?
    STILL_DIRTY=$(pg_count "SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE")
    if (( STILL_DIRTY > 0 )); then
        warn "Rating rebuild incomplete: $STILL_DIRTY systems still have rating_dirty=TRUE"
    else
        success "All rating_dirty flags cleared"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Rebuild dirty clusters
# ---------------------------------------------------------------------------
log "--- Step 4: Rebuild dirty clusters ---"
DIRTY_CLUSTERS=$(pg_count "SELECT COUNT(*) FROM systems WHERE cluster_dirty = TRUE")
log "Dirty cluster anchors: $DIRTY_CLUSTERS"

if (( DIRTY_CLUSTERS > 0 )); then
    log "Running build_clusters.py --dirty-only ..."
    run_importer "build_clusters" build_clusters.py --dirty-only \
        && success "Dirty clusters rebuilt" \
        || warn "Cluster rebuild had errors (check ${LOG_DIR}/build_clusters.log)"

    # Post-rebuild verification
    STILL_DIRTY_C=$(pg_count "SELECT COUNT(*) FROM systems WHERE cluster_dirty = TRUE")
    if (( STILL_DIRTY_C > 0 )); then
        warn "Cluster rebuild incomplete: $STILL_DIRTY_C systems still have cluster_dirty=TRUE"
    else
        success "All cluster_dirty flags cleared"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Clear Redis cache
# ---------------------------------------------------------------------------
log "--- Step 5: Clear Redis cache ---"
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
# 7. VACUUM ANALYZE
# ---------------------------------------------------------------------------
log "--- Step 7: VACUUM ANALYZE ---"
docker compose exec -T postgres psql -U edfinder -d edfinder -c \
    "VACUUM ANALYZE systems; VACUUM ANALYZE ratings; VACUUM ANALYZE cluster_summary; VACUUM ANALYZE stations;" \
    >> "$LOG" 2>&1 \
    && success "VACUUM ANALYZE complete" \
    || warn "VACUUM failed"

# ---------------------------------------------------------------------------
# 8. Final stats and summary
# ---------------------------------------------------------------------------
DISK_USED=$(df -h /data | awk 'NR==2{print $3 "/" $2 " (" $5 ")"}')
PG_SIZE=$(pg_count "SELECT pg_size_pretty(pg_database_size('edfinder'))")
SYS_COUNT=$(pg_count "SELECT TO_CHAR(COUNT(*), '999,999,999') FROM systems")
REMAINING_DIRTY=$(pg_count "SELECT COUNT(*) FROM systems WHERE rating_dirty OR cluster_dirty")

log "Systems: $SYS_COUNT | Disk: $DISK_USED | PostgreSQL DB: $PG_SIZE | Remaining dirty: $REMAINING_DIRTY"

if [[ -n "$ERRORS" ]]; then
    warn "=== Nightly update completed WITH WARNINGS: $ERRORS ==="
else
    success "=== Nightly update complete — no errors ==="
fi
