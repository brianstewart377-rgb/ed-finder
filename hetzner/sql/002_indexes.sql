-- =============================================================================
-- ED Finder — Indexes
-- Version: 1.0
--
-- RUN THIS AFTER BULK IMPORT IS COMPLETE — not before.
-- Building indexes on empty/partial tables wastes time and the indexes
-- get fragmented by bulk inserts anyway. Build once on the full dataset.
--
-- Estimated build time on 186M systems + 800M bodies (NVMe):
--   systems indexes:  ~20-40 minutes
--   bodies indexes:   ~2-4 hours
--   ratings indexes:  ~10-20 minutes
--   cluster indexes:  ~5-10 minutes
--   Total:            ~3-5 hours
--
-- Run with: psql -U edfinder -d edfinder -f 002_indexes.sql
-- Progress visible in pg_stat_progress_create_index
-- =============================================================================

-- Show progress helper
DO $$ BEGIN RAISE NOTICE 'Building indexes — this will take several hours. Monitor with:
SELECT phase, blocks_done, blocks_total, tuples_done, tuples_total
FROM pg_stat_progress_create_index;'; END $$;

-- =============================================================================
-- SYSTEMS TABLE INDEXES
-- =============================================================================

-- CRITICAL for build_grid.py v2.2 (ctid-range batching):
-- Allows _get_resume_page() to instantly find the first unassigned heap page
-- on restart without scanning the full 74GB table.
-- Without this index, resume detection does a full seq scan (~5 minutes).
-- With this index, resume detection takes < 1 second.
CREATE INDEX IF NOT EXISTS idx_sys_grid_null
    ON systems(id64)
    WHERE grid_cell_id IS NULL;

-- Primary spatial index — bounding box pre-filter (used by almost every query)
CREATE INDEX IF NOT EXISTS idx_sys_x ON systems(x);
CREATE INDEX IF NOT EXISTS idx_sys_y ON systems(y);
CREATE INDEX IF NOT EXISTS idx_sys_z ON systems(z);

-- Composite spatial index — covers the 3-axis bounding box check in one scan
CREATE INDEX IF NOT EXISTS idx_sys_coords ON systems(x, y, z);

-- Spatial grid cell — critical for cluster search (groups systems into 500ly cubes)
CREATE INDEX IF NOT EXISTS idx_sys_grid ON systems(grid_cell_id) WHERE grid_cell_id IS NOT NULL;

-- Economy searches (galaxy-wide economy search)
CREATE INDEX IF NOT EXISTS idx_sys_primary_economy ON systems(primary_economy);
CREATE INDEX IF NOT EXISTS idx_sys_secondary_economy ON systems(secondary_economy);

-- Colonisation state — almost every search filters on this
CREATE INDEX IF NOT EXISTS idx_sys_colonised ON systems(is_colonised);
CREATE INDEX IF NOT EXISTS idx_sys_population ON systems(population);

-- Compound: uncolonised + economy (most common galaxy-wide search pattern)
CREATE INDEX IF NOT EXISTS idx_sys_econ_pop
    ON systems(primary_economy, population)
    WHERE population = 0;

-- Compound: uncolonised within grid cell (cluster sub-query pattern)
CREATE INDEX IF NOT EXISTS idx_sys_grid_pop
    ON systems(grid_cell_id, population)
    WHERE population = 0 AND grid_cell_id IS NOT NULL;

-- Name search (autocomplete, exact lookup)
CREATE INDEX IF NOT EXISTS idx_sys_name ON systems(name);
CREATE INDEX IF NOT EXISTS idx_sys_name_trgm ON systems USING gin(name gin_trgm_ops);

-- Data quality / dirty flags
CREATE INDEX IF NOT EXISTS idx_sys_has_bodies ON systems(has_body_data) WHERE has_body_data = TRUE;
CREATE INDEX IF NOT EXISTS idx_sys_rating_dirty ON systems(rating_dirty) WHERE rating_dirty = TRUE;
CREATE INDEX IF NOT EXISTS idx_sys_cluster_dirty ON systems(cluster_dirty) WHERE cluster_dirty = TRUE;

-- EDDN update tracking
CREATE INDEX IF NOT EXISTS idx_sys_updated_at ON systems(updated_at);
CREATE INDEX IF NOT EXISTS idx_sys_eddn_updated ON systems(eddn_updated_at) WHERE eddn_updated_at IS NOT NULL;

-- Star type quick filter (without joining bodies)
CREATE INDEX IF NOT EXISTS idx_sys_main_star ON systems(main_star_type) WHERE main_star_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sys_scoopable ON systems(main_star_is_scoopable) WHERE main_star_is_scoopable = TRUE;

-- =============================================================================
-- BODIES TABLE INDEXES
-- =============================================================================

-- Foreign key (cascade deletes, joins)
CREATE INDEX IF NOT EXISTS idx_body_system ON bodies(system_id64);

-- Body type filters
CREATE INDEX IF NOT EXISTS idx_body_subtype ON bodies(subtype) WHERE subtype IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_body_type ON bodies(body_type);

-- Key boolean filters (partial indexes — only index TRUE rows, much smaller)
CREATE INDEX IF NOT EXISTS idx_body_elw
    ON bodies(system_id64)
    WHERE is_earth_like = TRUE;

CREATE INDEX IF NOT EXISTS idx_body_ww
    ON bodies(system_id64)
    WHERE is_water_world = TRUE;

CREATE INDEX IF NOT EXISTS idx_body_ammonia
    ON bodies(system_id64)
    WHERE is_ammonia_world = TRUE;

CREATE INDEX IF NOT EXISTS idx_body_terraformable
    ON bodies(system_id64)
    WHERE is_terraformable = TRUE;

CREATE INDEX IF NOT EXISTS idx_body_landable
    ON bodies(system_id64)
    WHERE is_landable = TRUE;

CREATE INDEX IF NOT EXISTS idx_body_main_star
    ON bodies(system_id64)
    WHERE is_main_star = TRUE;

-- Signal counts (for biological / geological hotspot searches)
CREATE INDEX IF NOT EXISTS idx_body_bio_signals
    ON bodies(system_id64, bio_signal_count)
    WHERE bio_signal_count > 0;

CREATE INDEX IF NOT EXISTS idx_body_geo_signals
    ON bodies(system_id64, geo_signal_count)
    WHERE geo_signal_count > 0;

-- Scan/mapping value (for high-value system searches)
CREATE INDEX IF NOT EXISTS idx_body_scan_value
    ON bodies(estimated_scan_value DESC NULLS LAST)
    WHERE estimated_scan_value IS NOT NULL;

-- =============================================================================
-- STATIONS TABLE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_sta_system ON stations(system_id64);
CREATE INDEX IF NOT EXISTS idx_sta_type ON stations(station_type);
CREATE INDEX IF NOT EXISTS idx_sta_economy ON stations(primary_economy);
CREATE INDEX IF NOT EXISTS idx_sta_name ON stations(name);
CREATE INDEX IF NOT EXISTS idx_sta_name_trgm ON stations USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_sta_large_pad ON stations(system_id64) WHERE landing_pad_size = 'L';
CREATE INDEX IF NOT EXISTS idx_sta_shipyard ON stations(system_id64) WHERE has_shipyard = TRUE;
CREATE INDEX IF NOT EXISTS idx_sta_outfitting ON stations(system_id64) WHERE has_outfitting = TRUE;

-- =============================================================================
-- ATTRACTIONS TABLE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_attr_system ON attractions(system_id64);
CREATE INDEX IF NOT EXISTS idx_attr_body ON attractions(body_id) WHERE body_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_attr_type ON attractions(attraction_type);
CREATE INDEX IF NOT EXISTS idx_attr_subtype ON attractions(subtype) WHERE subtype IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_attr_genus ON attractions(genus) WHERE genus IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_attr_species ON attractions(species) WHERE species IS NOT NULL;

-- =============================================================================
-- RATINGS TABLE INDEXES
-- =============================================================================

-- The most important index — covers every galaxy-wide score search
CREATE INDEX IF NOT EXISTS idx_rat_score ON ratings(score DESC NULLS LAST)
    WHERE score IS NOT NULL;

-- Per-economy score indexes (galaxy-wide "best for X economy" searches)
CREATE INDEX IF NOT EXISTS idx_rat_agriculture ON ratings(score_agriculture DESC NULLS LAST)
    WHERE score_agriculture IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rat_refinery ON ratings(score_refinery DESC NULLS LAST)
    WHERE score_refinery IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rat_industrial ON ratings(score_industrial DESC NULLS LAST)
    WHERE score_industrial IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rat_hightech ON ratings(score_hightech DESC NULLS LAST)
    WHERE score_hightech IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rat_military ON ratings(score_military DESC NULLS LAST)
    WHERE score_military IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rat_tourism ON ratings(score_tourism DESC NULLS LAST)
    WHERE score_tourism IS NOT NULL;

-- Economy suggestion + score (standard search pattern)
CREATE INDEX IF NOT EXISTS idx_rat_econ_score
    ON ratings(economy_suggestion, score DESC NULLS LAST)
    WHERE score IS NOT NULL;

-- Body count filters (frontend slider filters)
CREATE INDEX IF NOT EXISTS idx_rat_elw ON ratings(elw_count) WHERE elw_count > 0;
CREATE INDEX IF NOT EXISTS idx_rat_ammonia ON ratings(ammonia_count) WHERE ammonia_count > 0;
CREATE INDEX IF NOT EXISTS idx_rat_gas_giant ON ratings(gas_giant_count) WHERE gas_giant_count > 0;
CREATE INDEX IF NOT EXISTS idx_rat_bio ON ratings(bio_signal_total) WHERE bio_signal_total > 0;
CREATE INDEX IF NOT EXISTS idx_rat_geo ON ratings(geo_signal_total) WHERE geo_signal_total > 0;
CREATE INDEX IF NOT EXISTS idx_rat_terraformable ON ratings(terraformable_count) WHERE terraformable_count > 0;
CREATE INDEX IF NOT EXISTS idx_rat_neutron ON ratings(neutron_count) WHERE neutron_count > 0;

-- Dirty flag (incremental rebuild) — index on system_id64 for join performance
-- NOTE: cannot use NOW() in partial index predicate (not immutable), so index all rows
CREATE INDEX IF NOT EXISTS idx_rat_dirty ON ratings(system_id64);

-- =============================================================================
-- SPATIAL_GRID TABLE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_grid_coords ON spatial_grid(cell_x, cell_y, cell_z);

-- =============================================================================
-- CLUSTER_SUMMARY TABLE INDEXES
-- =============================================================================

-- Coverage score — the primary sort for cluster search results
CREATE INDEX IF NOT EXISTS idx_clu_coverage ON cluster_summary(coverage_score DESC NULLS LAST)
    WHERE coverage_score IS NOT NULL;

-- Economy diversity — "find regions covering N economy types"
CREATE INDEX IF NOT EXISTS idx_clu_diversity ON cluster_summary(economy_diversity DESC);

-- Per-economy count indexes (for "must have at least N viable X systems")
CREATE INDEX IF NOT EXISTS idx_clu_agriculture ON cluster_summary(agriculture_count DESC) WHERE agriculture_count > 0;
CREATE INDEX IF NOT EXISTS idx_clu_refinery    ON cluster_summary(refinery_count DESC)    WHERE refinery_count > 0;
CREATE INDEX IF NOT EXISTS idx_clu_industrial  ON cluster_summary(industrial_count DESC)  WHERE industrial_count > 0;
CREATE INDEX IF NOT EXISTS idx_clu_hightech    ON cluster_summary(hightech_count DESC)    WHERE hightech_count > 0;
CREATE INDEX IF NOT EXISTS idx_clu_military    ON cluster_summary(military_count DESC)    WHERE military_count > 0;
CREATE INDEX IF NOT EXISTS idx_clu_tourism     ON cluster_summary(tourism_count DESC)     WHERE tourism_count > 0;

-- Dirty flag (5-minute incremental rebuild)
CREATE INDEX IF NOT EXISTS idx_clu_dirty ON cluster_summary(system_id64) WHERE dirty = TRUE;

-- =============================================================================
-- WATCHLIST / NOTES / CACHE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_wl_system    ON watchlist(system_id64);
CREATE INDEX IF NOT EXISTS idx_wl_added     ON watchlist(added_at DESC);
CREATE INDEX IF NOT EXISTS idx_wllog_system ON watchlist_changelog(system_id64);
CREATE INDEX IF NOT EXISTS idx_wllog_det    ON watchlist_changelog(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_cache_exp    ON api_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_eddn_recv    ON eddn_log(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_eddn_proc    ON eddn_log(processed) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_eddn_system  ON eddn_log(system_id64) WHERE system_id64 IS NOT NULL;

-- =============================================================================
-- POST-INDEX STATISTICS UPDATE
-- =============================================================================
-- Force planner to use fresh statistics after index build
ANALYZE systems;
ANALYZE bodies;
ANALYZE ratings;
ANALYZE cluster_summary;
ANALYZE spatial_grid;
ANALYZE stations;
ANALYZE attractions;

DO $$ BEGIN RAISE NOTICE 'All indexes built successfully.'; END $$;
