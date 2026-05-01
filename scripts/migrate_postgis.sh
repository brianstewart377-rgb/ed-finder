#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# migrate_postgis.sh  v1.0
# Run AFTER the full Spansh import has completed.
# Adds PostGIS geometry column to the systems table and builds a spatial index.
# This enables fast radius searches and replaces the Python-side grid-cell math.
#
# Runtime: ~45-90 minutes on 41M rows (Hetzner AX41-SSD)
# Disk:    ~12 GB additional (geometry column + GIST index)
#
# Usage:
#   cd /opt/ed-finder
#   bash scripts/migrate_postgis.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$(cd "$SCRIPT_DIR/.." && pwd)/docker-compose.yml"
LOG_FILE="/data/logs/migrate_postgis_$(date +%Y%m%d_%H%M%S).log"

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
fatal(){ log "[FATAL] $*"; exit 1; }

log "═══════════════════════════════════════════════════════"
log " PostGIS Migration v1.0"
log " Log: $LOG_FILE"
log "═══════════════════════════════════════════════════════"

# ── Verify postgres is running ────────────────────────────────────────────────
docker compose -f "$COMPOSE_FILE" ps postgres | grep -q "running" \
  || fatal "ed-postgres is not running. Start the stack first."

# ── Helper to run SQL ─────────────────────────────────────────────────────────
run_sql() {
  docker exec -i ed-postgres psql -U edfinder -d edfinder -v ON_ERROR_STOP=1 "$@"
}

# ── Step 1: Install PostGIS extension ────────────────────────────────────────
log "[1/6] Installing PostGIS extension..."
run_sql -c "CREATE EXTENSION IF NOT EXISTS postgis;" \
  && log "      PostGIS installed." \
  || fatal "Failed to install PostGIS. Is postgis available in the postgres image?"

# ── Step 2: Add geometry column ───────────────────────────────────────────────
log "[2/6] Adding geometry column to systems table (may take a few minutes)..."
run_sql <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'systems' AND column_name = 'geom'
  ) THEN
    ALTER TABLE systems ADD COLUMN geom geometry(PointZ, 4326);
    RAISE NOTICE 'Column geom added.';
  ELSE
    RAISE NOTICE 'Column geom already exists — skipping.';
  END IF;
END $$;
SQL
log "      Column added."

# ── Step 3: Populate geometry from x/y/z ─────────────────────────────────────
log "[3/6] Populating geometry column from x/y/z coordinates (~30-60 min)..."
run_sql -c "
  UPDATE systems
  SET geom = ST_SetSRID(ST_MakePoint(x, z, y), 4326)
  WHERE geom IS NULL AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL;
" 2>&1 | tee -a "$LOG_FILE"
log "      Geometry populated."

# ── Step 4: Build GIST spatial index ─────────────────────────────────────────
log "[4/6] Building GIST spatial index (idx_systems_geom) — ~20-40 min..."
run_sql -c "
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_systems_geom
  ON systems USING GIST (geom);
" 2>&1 | tee -a "$LOG_FILE"
log "      Spatial index built."

# ── Step 5: Add NOT NULL constraint ──────────────────────────────────────────
log "[5/6] Verifying coverage..."
run_sql -c "
  SELECT
    COUNT(*) FILTER (WHERE geom IS NULL AND x IS NOT NULL) AS missing_geom,
    COUNT(*) AS total
  FROM systems;
" 2>&1 | tee -a "$LOG_FILE"

# ── Step 6: ANALYZE ───────────────────────────────────────────────────────────
log "[6/6] Running ANALYZE on systems table..."
run_sql -c "ANALYZE systems;" 2>&1 | tee -a "$LOG_FILE"
log "      ANALYZE complete."

log "═══════════════════════════════════════════════════════"
log " PostGIS migration complete!"
log " You can now use ST_DWithin() for fast radius searches."
log " Restart the API container to pick up the new index:"
log "   docker compose -f $COMPOSE_FILE restart api"
log "═══════════════════════════════════════════════════════"
