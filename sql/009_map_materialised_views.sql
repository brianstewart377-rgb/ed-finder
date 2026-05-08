-- ============================================================================
-- ED Finder — Map aggregation materialised views
-- ============================================================================
-- Audit fix (2026-05-08, AUDIT_REPORT.md §C4 / Phase 5):
--
-- Before this migration, /api/map/regions, /api/map/heatmap, and
-- /api/map/timeline issued a fresh AVG / GROUP-BY / DATE_TRUNC + COUNT(*)
-- across the 186 M-row systems table on every cache miss. With cache TTL
-- of 24 h, a thundering-herd burst at expiry could deadlock the entire
-- 20-conn asyncpg pool while a single query held a slot for up to 300 s.
--
-- This migration pre-aggregates the same data into materialised views
-- refreshed nightly by scripts/refresh_map_mviews.sh. Cache-miss latency
-- drops from "5-300 s" to "<50 ms" because the views are key-value
-- lookups against a few thousand pre-computed rows.
--
-- Contract:
--   * mv_map_regions          — one row per galaxy region (≤ 42 rows)
--   * mv_map_heatmap_200ly    — voxel cells at 200 LY resolution
--   * mv_map_heatmap_500ly    — voxel cells at 500 LY resolution
--   * mv_map_heatmap_1000ly   — voxel cells at 1000 LY resolution
--   * mv_map_timeline_month   — month-bucketed discovery counts
--
-- Refresh strategy:
--   * REFRESH MATERIALIZED VIEW CONCURRENTLY  ← needs UNIQUE indexes
--   * Triggered nightly + after each completed `build_ratings.py` run
--   * Concurrent refresh = no read lock; live queries see old rows
--     until refresh completes, never blocked.
-- ============================================================================

\echo === Building map aggregation materialised views ===

-- ── Regions ────────────────────────────────────────────────────────────────
DROP MATERIALIZED VIEW IF EXISTS mv_map_regions CASCADE;
CREATE MATERIALIZED VIEW mv_map_regions AS
SELECT
    r.id,
    r.name,
    AVG(s.x)::real AS x,
    AVG(s.y)::real AS y,
    AVG(s.z)::real AS z,
    COUNT(s.id64)  AS system_count
FROM   galaxy_regions r
LEFT JOIN systems s ON s.galaxy_region_id = r.id
GROUP BY r.id, r.name
ORDER BY r.id;

-- Required for REFRESH ... CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS mv_map_regions_pk ON mv_map_regions(id);

-- ── Heatmap (3 voxel resolutions) ──────────────────────────────────────────
-- The API picks a resolution by the request's voxel_size; cells smaller
-- than 200 LY are not pre-aggregated (the viewport scale doesn't justify
-- the row explosion). All three views carry per-economy max scores so
-- the API can render per-economy heatmaps without re-scanning ratings.

CREATE OR REPLACE FUNCTION _build_heatmap_mv(_voxel int, _name text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    sql text;
BEGIN
    EXECUTE format('DROP MATERIALIZED VIEW IF EXISTS %I CASCADE', _name);
    sql := format($mv$
        CREATE MATERIALIZED VIEW %I AS
        SELECT
            FLOOR(s.x / %s)::int * %s + %s/2 AS cx,
            FLOOR(s.y / %s)::int * %s + %s/2 AS cy,
            FLOOR(s.z / %s)::int * %s + %s/2 AS cz,
            COUNT(*)                          AS n,
            AVG(r.score)::int                 AS avg_score,
            MAX(r.score)                      AS max_score,
            MAX(r.score_agriculture) AS max_agriculture,
            MAX(r.score_refinery)    AS max_refinery,
            MAX(r.score_industrial)  AS max_industrial,
            MAX(r.score_hightech)    AS max_hightech,
            MAX(r.score_military)    AS max_military,
            MAX(r.score_tourism)     AS max_tourism,
            MAX(r.score_extraction)  AS max_extraction
        FROM   systems s
        JOIN   ratings r ON r.system_id64 = s.id64
        WHERE  r.score IS NOT NULL
        GROUP BY cx, cy, cz
    $mv$, _name, _voxel, _voxel, _voxel, _voxel, _voxel, _voxel, _voxel, _voxel, _voxel);
    EXECUTE sql;
    EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON %I(cx, cy, cz)',
                   _name || '_pk', _name);
END;
$$;

SELECT _build_heatmap_mv(200,  'mv_map_heatmap_200ly');
SELECT _build_heatmap_mv(500,  'mv_map_heatmap_500ly');
SELECT _build_heatmap_mv(1000, 'mv_map_heatmap_1000ly');
DROP FUNCTION _build_heatmap_mv(int, text);

-- ── Timeline (month buckets — by far the most-used) ────────────────────────
DROP MATERIALIZED VIEW IF EXISTS mv_map_timeline_month CASCADE;
CREATE MATERIALIZED VIEW mv_map_timeline_month AS
SELECT
    DATE_TRUNC('month', COALESCE(first_discovered_at, updated_at))::date AS bucket,
    COUNT(*) AS systems_discovered
FROM   systems
WHERE  COALESCE(first_discovered_at, updated_at) IS NOT NULL
GROUP BY bucket
ORDER BY bucket;

CREATE UNIQUE INDEX IF NOT EXISTS mv_map_timeline_month_pk
    ON mv_map_timeline_month(bucket);

-- ── Refresh helper (call from nightly cron) ────────────────────────────────
CREATE OR REPLACE FUNCTION refresh_map_mviews(_concurrent boolean DEFAULT TRUE)
RETURNS TABLE(name text, refresh_ms numeric)
LANGUAGE plpgsql AS $$
DECLARE
    _t0 timestamptz;
    _mv text;
BEGIN
    FOR _mv IN
        SELECT unnest(ARRAY[
            'mv_map_regions',
            'mv_map_heatmap_200ly',
            'mv_map_heatmap_500ly',
            'mv_map_heatmap_1000ly',
            'mv_map_timeline_month'
        ])
    LOOP
        _t0 := clock_timestamp();
        IF _concurrent THEN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', _mv);
        ELSE
            EXECUTE format('REFRESH MATERIALIZED VIEW %I', _mv);
        END IF;
        name        := _mv;
        refresh_ms  := EXTRACT(EPOCH FROM (clock_timestamp() - _t0)) * 1000;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION refresh_map_mviews(boolean) IS
'Refresh every map aggregation MV. Pass FALSE on a fresh DB (CONCURRENT '
'requires a non-empty MV — first refresh after CREATE must be non-concurrent).';

\echo === Map MVs created. First refresh below (non-concurrent because MVs are empty) ===
SELECT * FROM refresh_map_mviews(FALSE);

\echo === Done ===
