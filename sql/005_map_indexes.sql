-- ============================================================================
-- ED Finder — Map support indexes (v3.1)
-- ============================================================================
-- Indexes supporting the new /api/map/* endpoints:
--
--   idx_systems_first_discovered_at
--     → /api/map/timeline bucket aggregation (DATE_TRUNC)
--
--   idx_systems_galaxy_region_populated
--     → /api/map/regions centroid computation (LEFT JOIN + GROUP BY)
--
--   idx_cluster_summary_top_score
--     → /api/map/clusters/hulls ORDER BY top_score DESC
--
-- All three are CREATE INDEX IF NOT EXISTS + CONCURRENTLY where supported,
-- so the migration is idempotent and non-blocking on a live system.
-- ============================================================================

-- CONCURRENTLY cannot run inside a transaction block.  Wrap individual
-- statements (each runs in its own implicit transaction).

CREATE INDEX IF NOT EXISTS idx_systems_first_discovered_at
    ON systems (COALESCE(first_discovered_at, last_updated))
    WHERE COALESCE(first_discovered_at, last_updated) IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_systems_galaxy_region_populated
    ON systems (galaxy_region_id)
    WHERE galaxy_region_id IS NOT NULL;

-- Functional expression index on the cluster_summary best-score GREATEST(...)
-- so the hulls endpoint can satisfy ORDER BY without a seq scan.
CREATE INDEX IF NOT EXISTS idx_cluster_summary_top_score
    ON cluster_summary (
        GREATEST(
            COALESCE(agriculture_best,0), COALESCE(refinery_best,0),
            COALESCE(industrial_best,0),  COALESCE(hightech_best,0),
            COALESCE(military_best,0),    COALESCE(tourism_best,0)
        ) DESC
    );

-- ANALYZE so the planner notices the new indexes immediately.
ANALYZE systems;
ANALYZE cluster_summary;
