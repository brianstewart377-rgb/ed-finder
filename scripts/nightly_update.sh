#!/bin/bash
# =============================================================================
# ED Finder — Nightly Update Script  (v1.2)
# Runs at 02:00 daily via cron.
#
# FIX in v1.2:
#   • Removed hardcoded /opt/ed-finder path. The script now auto-detects
#     the compose directory as the parent of the scripts/ folder. This means
#     the script works correctly regardless of where the repo is cloned,
#     and no longer fails if the old two-directory layout is not present.
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

# Created up front, not further down: both the docker-compose.yml check below
# and the overlap-guard check after it log a FATAL line via `tee -a "$LOG"`
# before doing anything else, and tee can't create a missing parent
# directory — on a host where /data/logs doesn't exist yet, a failure this
# early would silently not reach nightly.log at all, undermining the point
# of logging it.
mkdir -p "$LOG_DIR"

# Auto-detect the compose directory as the parent of this script's directory.
# This works whether the repo is at /opt/ed-finder or anywhere else.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -f "$COMPOSE/docker-compose.yml" ]]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [FATAL] Cannot find docker-compose.yml at $COMPOSE" | tee -a "$LOG"
    exit 1
fi

# Overlap guard. 2026-08-06 incident: a backlog-clearing regional-analysis
# backfill (Step 3.6, --limit 5000000) ran past 24h, cron fired the next
# night's run on top of it with nothing to stop it, and the two ran
# concurrently for two more days — contending on the same upserts, each
# roughly halving the other's throughput, and neither ever reaching the
# heartbeat ping at the bottom of this script (hence the "still down"
# dead-man's-switch alert: it wasn't broken, the run it was waiting on
# genuinely never finished). This is deliberately non-blocking (-n): if
# last night's run is still going, skip tonight's entirely rather than
# queue up a pileup, and let the still-running instance finish undisturbed.
#
# `flock -n 200` returning nonzero means "lock held" ONLY once we know
# flock itself ran; a missing binary would also return nonzero and get
# misread as contention, silently disabling every future nightly run with
# nothing but a misleading "still active" line in the log. Check for the
# binary explicitly first so that failure is loud instead.
command -v flock >/dev/null 2>&1 || {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [FATAL] flock is not available — cannot safely guard against overlapping nightly runs" | tee -a "$LOG"
    exit 1
}
NIGHTLY_LOCK_FILE="${NIGHTLY_LOCK_FILE:-/run/lock/ed-finder-nightly-update.lock}"
mkdir -p "$(dirname "$NIGHTLY_LOCK_FILE")"
exec 200>"$NIGHTLY_LOCK_FILE"
if ! flock -n 200; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN]  Previous nightly_update.sh run is still active ($NIGHTLY_LOCK_FILE held) — skipping tonight's run rather than stacking a duplicate" | tee -a "$LOG"
    exit 0
fi

# Host cron does not load the compose environment. Read only the heartbeat key
# rather than sourcing .env, because other values may contain shell syntax.
if [[ -z "${NIGHTLY_UPDATE_HEARTBEAT_URL+x}" ]] && [[ -r "$COMPOSE/.env" ]]; then
    while IFS= read -r env_line || [[ -n "$env_line" ]]; do
        env_line="${env_line%$'\r'}"
        case "$env_line" in
            NIGHTLY_UPDATE_HEARTBEAT_URL=*)
                NIGHTLY_UPDATE_HEARTBEAT_URL="${env_line#*=}"
                break
                ;;
        esac
    done < "$COMPOSE/.env"
fi
NIGHTLY_UPDATE_HEARTBEAT_URL="${NIGHTLY_UPDATE_HEARTBEAT_URL-}"

log()     { echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO]  $*" | tee -a "$LOG"; }
warn()    { echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN]  $*" | tee -a "$LOG"; ERRORS="${ERRORS} | $*"; }
success() { echo "$(date '+%Y-%m-%d %H:%M:%S') [OK]    $*" | tee -a "$LOG"; }
fatal()   { echo "$(date '+%Y-%m-%d %H:%M:%S') [FATAL] $*" | tee -a "$LOG"; exit 1; }

# Accumulate non-fatal warnings for end-of-run summary
ERRORS=""

log "=== Nightly update started (compose dir: $COMPOSE) ==="
cd "$COMPOSE" || fatal "compose directory missing: $COMPOSE"

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
    # --entrypoint override is required: the image's ENTRYPOINT is already
    # ["python3"], and `docker compose run <service> <cmd>` appends the given
    # command on top of the entrypoint rather than replacing it. Without this
    # override the container tried to execute a literal file named "python3"
    # as its script argument and failed on every invocation (see
    # run_dirty_ratings_if_needed.sh, which already uses this same override
    # and works correctly).
    docker compose --profile import run --rm --entrypoint python3 importer \
        "$@" \
        2>&1 | tee -a "$job_log" | tee -a "$LOG"
    return "${PIPESTATUS[0]}"
}

# Bound every direct psql call to 30 minutes so a stuck statement cannot run all
# night. Anything longer belongs in the maintenance container's weekly path.
# Passing PGOPTIONS through docker compose exec also works for VACUUM, which
# cannot share a transaction with an inline SET statement.
NIGHTLY_PGOPTIONS="-c statement_timeout=1800000"

run_psql() {
    docker compose exec -T -e "PGOPTIONS=$NIGHTLY_PGOPTIONS" \
        postgres psql -U edfinder -d edfinder "$@"
}

# Query postgres without letting an unverifiable state masquerade as zero.
# The output variable is assigned in the current shell so warn() can update
# ERRORS and force the final heartbeat onto the /fail path.
pg_count_into() {
    local output_var="$1"
    local sql="$2"
    local value
    if value=$(run_psql -tAc "$sql" 2>> "$LOG"); then
        printf -v "$output_var" '%s' "$value"
    else
        local psql_exit=$?
        printf -v "$output_var" '%s' '0'
        warn "Database measurement failed for $output_var (psql exit $psql_exit); using 0 only to continue"
        return "$psql_exit"
    fi
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
pg_count_into DIRTY_COUNT "SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE"
log "Dirty systems to re-rate: $DIRTY_COUNT"

if (( DIRTY_COUNT > 0 )); then
    log "Running build_ratings.py --dirty ..."
    run_importer "build_ratings" build_ratings.py --dirty \
        && success "Dirty ratings rebuilt" \
        || warn "Rating rebuild had errors (check ${LOG_DIR}/build_ratings.log)"

    # Post-rebuild verification: how many are still dirty?
    pg_count_into STILL_DIRTY "SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE"
    if (( STILL_DIRTY > 0 )); then
        warn "Rating rebuild incomplete: $STILL_DIRTY systems still have rating_dirty=TRUE"
    else
        success "All rating_dirty flags cleared"
    fi
fi

# ---------------------------------------------------------------------------
# 3.5. Build archetype topology + scores for dirty systems
#
# Dirty detection:
#   build_topology.py --dirty  → ratings.rating_dirty = TRUE (or topology missing)
#   build_archetype_scores.py --dirty → system_archetype_scores.dirty = TRUE
# ---------------------------------------------------------------------------
log "--- Step 3.5: Build archetype topology + scores ---"

# Use the same dirty signal as build_topology.py's --dirty mode
# (_fetch_system_ids in apps/importer/src/build_topology.py): ratings rows
# whose owning system is rating_dirty, or systems with a rating but no
# topology row yet. rating_dirty lives on systems, not ratings — the prior
# "FROM ratings WHERE rating_dirty" errored every night (column does not
# exist on ratings) and silently degraded to 0, which skipped
# build_topology.py --dirty entirely regardless of the real backlog size.
pg_count_into TOPO_DIRTY "SELECT COUNT(*) FROM (
    SELECT r.system_id64
    FROM ratings r
    JOIN systems s ON s.id64 = r.system_id64
    LEFT JOIN system_slot_topology t ON t.system_id64 = r.system_id64
    WHERE s.rating_dirty = TRUE
       OR t.system_id64 IS NULL
) topo_dirty"
pg_count_into ARCH_SCORE_DIRTY "SELECT COUNT(*) FROM system_archetype_scores WHERE dirty = TRUE"
log "Topology dirty (rating_dirty): $TOPO_DIRTY | Archetype scores dirty: $ARCH_SCORE_DIRTY"

ARCH_BUILD_RAN=0

if (( TOPO_DIRTY > 0 )); then
    log "Running build_topology.py --dirty ..."
    run_importer "build_topology" build_topology.py --dirty \
        && success "Topology rebuilt" \
        || warn "Topology rebuild had errors (check ${LOG_DIR}/build_topology.log)"
fi

# Re-check arch score dirty count after topology run (topology write sets dirty=TRUE
# on system_archetype_scores for any system it touches)
pg_count_into ARCH_SCORE_DIRTY "SELECT COUNT(*) FROM system_archetype_scores WHERE dirty = TRUE"
log "Archetype scores dirty after topology pass: $ARCH_SCORE_DIRTY"

if (( ARCH_SCORE_DIRTY > 0 )); then
    log "Running build_archetype_scores.py --dirty ..."
    run_importer "build_archetype_scores" build_archetype_scores.py --dirty \
        && { success "Archetype scores rebuilt"; ARCH_BUILD_RAN=1; } \
        || warn "Archetype score rebuild had errors (check ${LOG_DIR}/build_archetype_scores.log)"

    log "Refreshing mv_archetype_rankings ..."
    run_psql \
        -c "SET statement_timeout = '10min'; REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;" \
        >> "$LOG" 2>&1 \
        && success "mv_archetype_rankings refreshed" \
        || warn "MV refresh failed"

    # Post-rebuild verification
    pg_count_into STILL_DIRTY_A "SELECT COUNT(*) FROM system_archetype_scores WHERE dirty = TRUE"
    if (( STILL_DIRTY_A > 0 )); then
        warn "Archetype rebuild incomplete: $STILL_DIRTY_A rows still have dirty=TRUE in system_archetype_scores"
    else
        success "All system_archetype_scores.dirty flags cleared"
    fi
fi

# Re-check for systems with a ratings row but no archetype row at all —
# --dirty only rescores existing rows, it never inserts new ones. Note:
# the `limit or 10_000_000` fallback in build_archetype_scores.py silently
# caps at 10M rows — always pass --limit explicitly.
pg_count_into ARCH_SCORE_MISSING "
    SELECT COUNT(*) FROM ratings r
    LEFT JOIN system_archetype_scores a ON a.system_id64 = r.system_id64
    WHERE a.system_id64 IS NULL
"
log "Systems missing archetype rows entirely: $ARCH_SCORE_MISSING"

if (( ARCH_SCORE_MISSING > 0 )); then
    log "Running build_archetype_scores.py (new-system mode) ..."
    # Cap per-run at 5M rows to avoid unattended multi-day runs.
    # At this rate the current ~177M backlog clears in ~36 nights.
    # Remove the cap once the backlog is cleared and replace with
    # a smaller maintenance cap (e.g. --limit 500000).
    run_importer "build_archetype_scores_new" build_archetype_scores.py --limit 5000000 \
        && { success "New archetype scores backfilled"; ARCH_BUILD_RAN=1; } \
        || warn "New archetype score backfill had errors (check ${LOG_DIR}/build_archetype_scores_new.log)"

    log "Refreshing mv_archetype_rankings ..."
    run_psql \
        -c "SET statement_timeout = '10min'; REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;" \
        >> "$LOG" 2>&1 \
        && success "mv_archetype_rankings refreshed" \
        || warn "MV refresh failed"
fi

# Catch-up: if any archetype build ran in this invocation, ensure the
# MV reflects the new data. The inline refreshes inside each block may
# have failed or been skipped (the build clears dirty flags, so the
# post-build count can be zero even though data changed).
if (( ARCH_BUILD_RAN == 1 )); then
    pg_count_into MV_ROWS "SELECT COUNT(*) FROM mv_archetype_rankings"
    log "Archetype build ran this cycle — verifying MV is current ($MV_ROWS rows) ..."
    run_psql \
        -c "SET statement_timeout = '10min'; REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;" \
        >> "$LOG" 2>&1 \
        && success "mv_archetype_rankings refreshed (catch-up)" \
        || warn "MV catch-up refresh failed"
fi

# Re-check for systems with body data but no regional analysis row at all —
# build_regional_analysis.py's default mode only covers systems missing a
# row, same shape as the archetype new-system step above.
pg_count_into REGIONAL_MISSING "
    SELECT COUNT(*) FROM systems s
    LEFT JOIN system_regional_analysis r ON r.system_id64 = s.id64
    WHERE r.system_id64 IS NULL
      AND s.has_body_data = TRUE
"
log "Systems missing regional analysis rows: $REGIONAL_MISSING"

if (( REGIONAL_MISSING > 0 )); then
    log "Running build_regional_analysis.py (new-system mode) ..."
    # Cap at 5M/night — same pattern as archetype scoring.
    # Remove cap once backlog is cleared.
    run_importer "build_regional_analysis_new" build_regional_analysis.py --limit 5000000 \
        && success "New regional analysis rows backfilled" \
        || warn "Regional analysis backfill had errors (check ${LOG_DIR}/build_regional_analysis_new.log)"
fi

# ---------------------------------------------------------------------------
# 4. Rebuild clusters
# ---------------------------------------------------------------------------
# 2026-07-15: cluster rebuild re-enabled (daily dirty-only).
# Discovery query fix (cf993d1) + idx_rat_score_viable (039) reduced
# discovery time from timeout to 192s. Sunday full rebuild remains
# disabled pending separate evaluation at scale.
#
log "--- Step 4: Rebuild clusters ---"

# Strategy:
# - Sunday (DOW=7): Full rebuild (ensures everything is in sync)
# - Other days:     Incremental rebuild (dirty anchors only)
ELIGIBLE_CLUSTER_DIRTY_SQL="cluster_dirty = TRUE AND has_body_data = TRUE AND macro_grid_id IS NOT NULL"

if [[ "$DOW" == "7" ]]; then
    log "Weekly full cluster rebuild (Sunday) ..."
    # DISABLED: see TODO above
    # run_importer "build_clusters_full" build_clusters.py --workers 6 \
    #     && success "Full cluster rebuild complete" \
    #     || warn "Full cluster rebuild had errors (check ${LOG_DIR}/build_clusters_full.log)"
else
    pg_count_into DIRTY_CLUSTERS "SELECT COUNT(*) FROM systems WHERE ${ELIGIBLE_CLUSTER_DIRTY_SQL}"
    log "Eligible dirty cluster anchors: $DIRTY_CLUSTERS"

    if (( DIRTY_CLUSTERS > 0 )); then
        log "Running build_clusters.py --dirty-only ..."
        run_importer "build_clusters" build_clusters.py --dirty-only --workers 6 \
            && success "Dirty clusters rebuilt" \
            || warn "Cluster rebuild had errors (check ${LOG_DIR}/build_clusters.log)"

        # Post-rebuild verification
        pg_count_into STILL_DIRTY_C "SELECT COUNT(*) FROM systems WHERE ${ELIGIBLE_CLUSTER_DIRTY_SQL}"
        if (( STILL_DIRTY_C > 0 )); then
            warn "Cluster rebuild incomplete: $STILL_DIRTY_C eligible systems remain dirty"
        else
            success "All eligible cluster_dirty flags cleared"
        fi
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
# 6. VACUUM ANALYZE
# ---------------------------------------------------------------------------
log "--- Step 6: VACUUM ANALYZE ---"
# systems and ratings are deliberately excluded: the maintenance container
# ANALYZEs them daily at 03:15 and VACUUMs them in the Sunday weekly task.
# VACUUMing these 200GB+ tables here would overlap the 02:10 pg_dump.
VACUUM_TABLES=(
    cluster_summary
    stations
    system_archetype_scores
    system_archetype_traits
)

for table in "${VACUUM_TABLES[@]}"; do
    run_psql \
        -c "VACUUM ANALYZE ${table}" >> "$LOG" 2>&1 \
        && success "VACUUM ANALYZE ${table} complete" \
        || warn "VACUUM ANALYZE ${table} failed"
done

# ---------------------------------------------------------------------------
# 7. Final stats
# ---------------------------------------------------------------------------
DISK_USED=$(df -h /data | awk 'NR==2{print $3 "/" $2 " (" $5 ")"}')
pg_count_into PG_SIZE "SELECT pg_size_pretty(pg_database_size('edfinder'))"
pg_count_into SYS_COUNT "SELECT TO_CHAR(COUNT(*), '999,999,999') FROM systems"
pg_count_into REMAINING_DIRTY "SELECT COUNT(*) FROM systems WHERE rating_dirty OR (${ELIGIBLE_CLUSTER_DIRTY_SQL})"

log "Systems: $SYS_COUNT | Disk: $DISK_USED | PostgreSQL DB: $PG_SIZE | Remaining dirty: $REMAINING_DIRTY"

# ---------------------------------------------------------------------------
# 8. Record completion only after every work and verification step is clean
# ---------------------------------------------------------------------------
if [[ -z "$ERRORS" ]]; then
    run_psql -c \
        "INSERT INTO app_meta(key,value,updated_at)
         VALUES('last_nightly_update','$(date -u +%Y-%m-%dT%H:%M:%SZ)',NOW())
         ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()" \
        >> "$LOG" 2>&1 \
        && success "last_nightly_update recorded" \
        || warn "last_nightly_update update failed"
else
    log "last_nightly_update: skipped (run already degraded)"
fi

if [[ -n "$ERRORS" ]]; then
    warn "=== Nightly update completed WITH WARNINGS: $ERRORS ==="
    if [[ -z "$NIGHTLY_UPDATE_HEARTBEAT_URL" ]]; then
        log "Nightly update heartbeat: skipped (URL unconfigured)"
    else
        HEARTBEAT_CURL_STATUS=0
        curl -fsS -m 10 --retry 3 "$NIGHTLY_UPDATE_HEARTBEAT_URL/fail" \
            || HEARTBEAT_CURL_STATUS=$?
        if (( HEARTBEAT_CURL_STATUS == 0 )); then
            log "Nightly update heartbeat: sent-fail"
        else
            log "Nightly update heartbeat: ping-failed (fail signal)"
        fi
    fi
else
    success "=== Nightly update complete — no errors ==="
    if [[ -z "$NIGHTLY_UPDATE_HEARTBEAT_URL" ]]; then
        log "Nightly update heartbeat: skipped (URL unconfigured)"
    else
        HEARTBEAT_CURL_STATUS=0
        curl -fsS -m 10 --retry 3 "$NIGHTLY_UPDATE_HEARTBEAT_URL" \
            || HEARTBEAT_CURL_STATUS=$?
        if (( HEARTBEAT_CURL_STATUS == 0 )); then
            log "Nightly update heartbeat: sent-clean"
        else
            log "Nightly update heartbeat: ping-failed (clean signal)"
        fi
    fi
fi
