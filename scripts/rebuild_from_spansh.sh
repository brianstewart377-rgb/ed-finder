#!/bin/bash
# =============================================================================
# ED Finder — Full Database Rebuild from Spansh Dumps
# =============================================================================
# Rebuilds ratings, topology, clusters, regional analysis, and archetype scores
# after Spansh import completes.
#
# Usage:
#   ./scripts/rebuild_from_spansh.sh
#
# Expected runtime: 5-9 hours
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR=/data/logs
LOG="${LOG_DIR}/rebuild.log"

log()     { echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO]  $*" | tee -a "$LOG"; }
success() { echo "$(date '+%Y-%m-%d %H:%M:%S') [OK]    $*" | tee -a "$LOG"; }
fatal()   { echo "$(date '+%Y-%m-%d %H:%M:%S') [FATAL] $*" | tee -a "$LOG"; exit 1; }

mkdir -p "$LOG_DIR"
cd "$COMPOSE_DIR"

log "=== Starting full database rebuild from Spansh imports ==="

# Wait for Spansh import to complete
log "Step 1: Waiting for Spansh import to complete..."
while true; do
    STATUS=$(docker exec ed-postgres psql -U edfinder -d edfinder \
        -tAc "SELECT COUNT(*) FROM import_meta WHERE status IN ('running', 'pending');" 2>&1 || echo "error")

    if [[ "$STATUS" == "0" ]]; then
        log "Spansh import complete"
        break
    elif [[ "$STATUS" == "error" ]]; then
        fatal "Could not check import status"
    else
        log "  Waiting for $STATUS import(s) to complete..."
        sleep 30
    fi
done

success "Step 1: Spansh import complete"

# Verify data loaded
SYSTEM_COUNT=$(docker exec ed-postgres psql -U edfinder -d edfinder \
    -tAc "SELECT COUNT(*) FROM systems;" 2>&1 || echo "0")
log "Systems loaded: $SYSTEM_COUNT"

if [[ "$SYSTEM_COUNT" -lt 100000 ]]; then
    fatal "Spansh import appears incomplete (only $SYSTEM_COUNT systems)"
fi

# Run rebuild jobs in sequence
JOBS=(
    "build_ratings.py:Build ratings"
    "build_topology.py:Build topology"
    "build_clusters.py:Build clusters"
    "build_regional_analysis.py:Build regional analysis"
    "build_grid.py:Build grid"
    "build_archetype_scores.py --limit 50000000:Build archetype scores"
)

STEP=2
for JOB in "${JOBS[@]}"; do
    IFS=: read -r SCRIPT LABEL <<< "$JOB"
    log "Step $STEP: $LABEL"

    JOB_LOG="${LOG_DIR}/$(echo "$SCRIPT" | sed 's/ .*//).log"

    if ! docker compose --profile import run --rm --entrypoint python3 importer \
        -u /app/$SCRIPT 2>&1 | tee -a "$JOB_LOG" | tee -a "$LOG"; then
        fatal "Step $STEP failed: $LABEL"
    fi

    success "Step $STEP: $LABEL complete"
    ((STEP++))
done

# Final VACUUM ANALYZE
log "Step $STEP: VACUUM ANALYZE"
docker compose exec -T postgres psql -U edfinder -d edfinder -c "VACUUM ANALYZE;" >> "$LOG" 2>&1
success "Step $STEP: VACUUM ANALYZE complete"

log "=== Full rebuild complete ==="
success "Database rebuild from Spansh complete. Total runtime: $(date '+%H:%M:%S')"
