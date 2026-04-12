-- =============================================================================
-- ED Finder — SQL Functions & Views
-- Version: 1.0
--
-- Contains:
--   • Distance function (3D Euclidean)
--   • Bounding-box pre-filter helper
--   • Galaxy-wide economy search function
--   • Cluster search function (multi-economy, anchor-based)
--   • Cluster coverage score calculator
--   • Materialized view: best_uncolonised (top 10k uncolonised by score)
--   • Trigger: auto-set dirty flags on system/body update
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. 3D EUCLIDEAN DISTANCE  (LY between two points)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION distance_ly(
    x1 REAL, y1 REAL, z1 REAL,
    x2 REAL, y2 REAL, z2 REAL
) RETURNS REAL
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT sqrt(
        power(x1 - x2, 2) +
        power(y1 - y2, 2) +
        power(z1 - z2, 2)
    )::REAL;
$$;

-- ---------------------------------------------------------------------------
-- 2. BOUNDING BOX CHECK  (cheap pre-filter before exact distance)
--    Returns TRUE if point (px,py,pz) is within a cube of side 2r
--    centred on (cx,cy,cz). Use before calling distance_ly().
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION in_bounding_box(
    px REAL, py REAL, pz REAL,
    cx REAL, cy REAL, cz REAL,
    r  REAL
) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT
        abs(px - cx) <= r AND
        abs(py - cy) <= r AND
        abs(pz - cz) <= r;
$$;

-- ---------------------------------------------------------------------------
-- 3. GALAXY-WIDE ECONOMY SEARCH
--    Returns top N uncolonised systems for a given economy type,
--    sorted by the economy-specific score descending.
--    Optional: filter by minimum score threshold.
--
--    Usage:
--      SELECT * FROM search_galaxy_economy('HighTech', 40, 100);
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION search_galaxy_economy(
    p_economy       TEXT,
    p_min_score     SMALLINT    DEFAULT 0,
    p_limit         INTEGER     DEFAULT 100,
    p_offset        INTEGER     DEFAULT 0
)
RETURNS TABLE (
    id64            BIGINT,
    name            TEXT,
    x               REAL,
    y               REAL,
    z               REAL,
    primary_economy economy_type,
    population      BIGINT,
    score           SMALLINT,
    economy_score   SMALLINT,
    elw_count       SMALLINT,
    ammonia_count   SMALLINT,
    gas_giant_count SMALLINT,
    bio_signal_total SMALLINT,
    score_breakdown JSONB
)
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_score_col TEXT;
BEGIN
    -- Map economy name to the correct score column
    v_score_col := CASE lower(p_economy)
        WHEN 'agriculture' THEN 'score_agriculture'
        WHEN 'refinery'    THEN 'score_refinery'
        WHEN 'industrial'  THEN 'score_industrial'
        WHEN 'hightech'    THEN 'score_hightech'
        WHEN 'high tech'   THEN 'score_hightech'
        WHEN 'military'    THEN 'score_military'
        WHEN 'tourism'     THEN 'score_tourism'
        ELSE 'score'  -- fallback to overall score
    END;

    RETURN QUERY EXECUTE format('
        SELECT
            s.id64, s.name, s.x, s.y, s.z,
            s.primary_economy, s.population,
            r.score,
            r.%I AS economy_score,
            r.elw_count, r.ammonia_count, r.gas_giant_count,
            r.bio_signal_total, r.score_breakdown
        FROM ratings r
        JOIN systems s ON s.id64 = r.system_id64
        WHERE s.population = 0
          AND r.%I IS NOT NULL
          AND r.%I >= $1
        ORDER BY r.%I DESC NULLS LAST
        LIMIT $2 OFFSET $3
    ', v_score_col, v_score_col, v_score_col, v_score_col)
    USING p_min_score, p_limit, p_offset;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. DISTANCE-LIMITED ECONOMY SEARCH
--    Same as above but within a radius of a reference point.
--    Used for standard searches (existing app behaviour).
--
--    Usage:
--      SELECT * FROM search_economy_near(
--          'HighTech', 0, 0, 0, 200, 40, 100, 0
--      );
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION search_economy_near(
    p_economy       TEXT,
    p_ref_x         REAL,
    p_ref_y         REAL,
    p_ref_z         REAL,
    p_radius        REAL        DEFAULT 200,
    p_min_score     SMALLINT    DEFAULT 0,
    p_limit         INTEGER     DEFAULT 100,
    p_offset        INTEGER     DEFAULT 0
)
RETURNS TABLE (
    id64            BIGINT,
    name            TEXT,
    x               REAL,
    y               REAL,
    z               REAL,
    distance        REAL,
    primary_economy economy_type,
    population      BIGINT,
    score           SMALLINT,
    economy_score   SMALLINT,
    elw_count       SMALLINT,
    ammonia_count   SMALLINT,
    gas_giant_count SMALLINT,
    bio_signal_total SMALLINT,
    score_breakdown JSONB
)
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_score_col TEXT;
BEGIN
    v_score_col := CASE lower(p_economy)
        WHEN 'agriculture' THEN 'score_agriculture'
        WHEN 'refinery'    THEN 'score_refinery'
        WHEN 'industrial'  THEN 'score_industrial'
        WHEN 'hightech'    THEN 'score_hightech'
        WHEN 'high tech'   THEN 'score_hightech'
        WHEN 'military'    THEN 'score_military'
        WHEN 'tourism'     THEN 'score_tourism'
        ELSE 'score'
    END;

    RETURN QUERY EXECUTE format('
        SELECT
            s.id64, s.name, s.x, s.y, s.z,
            distance_ly(s.x, s.y, s.z, $1, $2, $3) AS distance,
            s.primary_economy, s.population,
            r.score,
            r.%I AS economy_score,
            r.elw_count, r.ammonia_count, r.gas_giant_count,
            r.bio_signal_total, r.score_breakdown
        FROM systems s
        JOIN ratings r ON r.system_id64 = s.id64
        WHERE s.population = 0
          AND in_bounding_box(s.x, s.y, s.z, $1, $2, $3, $4)
          AND distance_ly(s.x, s.y, s.z, $1, $2, $3) <= $4
          AND r.%I IS NOT NULL
          AND r.%I >= $5
        ORDER BY r.%I DESC NULLS LAST
        LIMIT $6 OFFSET $7
    ', v_score_col, v_score_col, v_score_col, v_score_col)
    USING p_ref_x, p_ref_y, p_ref_z, p_radius, p_min_score, p_limit, p_offset;
END;
$$;

-- ---------------------------------------------------------------------------
-- 5. MULTI-ECONOMY CLUSTER SEARCH
--    Find the best anchor points where a 500ly bubble covers all
--    requested economy types with sufficient viable systems.
--
--    p_requirements: JSONB array of {economy, min_count, min_score}
--    Example:
--      SELECT * FROM search_cluster(
--          '[
--            {"economy": "HighTech",    "min_count": 1, "min_score": 40},
--            {"economy": "Agriculture", "min_count": 2, "min_score": 30},
--            {"economy": "Refinery",    "min_count": 2, "min_score": 30}
--          ]'::jsonb,
--          100,  -- max results
--          0     -- offset
--      );
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION search_cluster(
    p_requirements  JSONB,
    p_limit         INTEGER     DEFAULT 50,
    p_offset        INTEGER     DEFAULT 0
)
RETURNS TABLE (
    anchor_id64         BIGINT,
    anchor_name         TEXT,
    anchor_x            REAL,
    anchor_y            REAL,
    anchor_z            REAL,
    anchor_population   BIGINT,
    coverage_score      REAL,
    economy_diversity   SMALLINT,
    total_viable        SMALLINT,
    agriculture_count   SMALLINT,
    agriculture_best    SMALLINT,
    refinery_count      SMALLINT,
    refinery_best       SMALLINT,
    industrial_count    SMALLINT,
    industrial_best     SMALLINT,
    hightech_count      SMALLINT,
    hightech_best       SMALLINT,
    military_count      SMALLINT,
    military_best       SMALLINT,
    tourism_count       SMALLINT,
    tourism_best        SMALLINT
)
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_req           JSONB;
    v_where_parts   TEXT[]  := ARRAY[]::TEXT[];
    v_where_clause  TEXT;
BEGIN
    -- Build WHERE clause from requirements
    FOR v_req IN SELECT * FROM jsonb_array_elements(p_requirements)
    LOOP
        DECLARE
            v_eco       TEXT    := lower(v_req->>'economy');
            v_col       TEXT;
            v_min_count INTEGER := COALESCE((v_req->>'min_count')::INTEGER, 1);
        BEGIN
            v_col := CASE v_eco
                WHEN 'agriculture' THEN 'agriculture_count'
                WHEN 'refinery'    THEN 'refinery_count'
                WHEN 'industrial'  THEN 'industrial_count'
                WHEN 'hightech'    THEN 'hightech_count'
                WHEN 'high tech'   THEN 'hightech_count'
                WHEN 'military'    THEN 'military_count'
                WHEN 'tourism'     THEN 'tourism_count'
                ELSE NULL
            END;
            IF v_col IS NOT NULL THEN
                v_where_parts := v_where_parts || format('cs.%I >= %s', v_col, v_min_count);
            END IF;
        END;
    END LOOP;

    v_where_clause := CASE
        WHEN array_length(v_where_parts, 1) > 0
        THEN array_to_string(v_where_parts, ' AND ')
        ELSE 'TRUE'
    END;

    RETURN QUERY EXECUTE format('
        SELECT
            s.id64, s.name, s.x, s.y, s.z, s.population,
            cs.coverage_score, cs.economy_diversity, cs.total_viable,
            cs.agriculture_count, cs.agriculture_best,
            cs.refinery_count,   cs.refinery_best,
            cs.industrial_count, cs.industrial_best,
            cs.hightech_count,   cs.hightech_best,
            cs.military_count,   cs.military_best,
            cs.tourism_count,    cs.tourism_best
        FROM cluster_summary cs
        JOIN systems s ON s.id64 = cs.system_id64
        WHERE %s
          AND cs.coverage_score IS NOT NULL
        ORDER BY cs.coverage_score DESC NULLS LAST
        LIMIT $1 OFFSET $2
    ', v_where_clause)
    USING p_limit, p_offset;
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. COMPUTE CLUSTER COVERAGE SCORE
--    Weighted score 0-100 reflecting how self-sufficient an empire
--    centred on this anchor could be.
--    Called by build_clusters.py and incremental EDDN update.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION compute_coverage_score(
    p_agriculture_count SMALLINT,
    p_agriculture_best  SMALLINT,
    p_refinery_count    SMALLINT,
    p_refinery_best     SMALLINT,
    p_industrial_count  SMALLINT,
    p_industrial_best   SMALLINT,
    p_hightech_count    SMALLINT,
    p_hightech_best     SMALLINT,
    p_military_count    SMALLINT,
    p_military_best     SMALLINT,
    p_tourism_count     SMALLINT,
    p_tourism_best      SMALLINT
) RETURNS REAL
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    -- Economy weights (Agriculture + HighTech most valuable for colonisation)
    w_agriculture   CONSTANT REAL := 0.25;
    w_refinery      CONSTANT REAL := 0.20;
    w_industrial    CONSTANT REAL := 0.20;
    w_hightech      CONSTANT REAL := 0.20;
    w_military      CONSTANT REAL := 0.10;
    w_tourism       CONSTANT REAL := 0.05;

    v_score         REAL := 0;
    v_count_bonus   REAL;
BEGIN
    -- For each economy: (best_score/100 * weight) + count_bonus
    -- Count bonus: diminishing returns after 3 viable systems
    IF p_agriculture_best IS NOT NULL THEN
        v_count_bonus := LEAST(p_agriculture_count::REAL / 3.0, 1.0) * 0.1;
        v_score := v_score + (p_agriculture_best::REAL / 100.0 + v_count_bonus) * w_agriculture;
    END IF;

    IF p_refinery_best IS NOT NULL THEN
        v_count_bonus := LEAST(p_refinery_count::REAL / 3.0, 1.0) * 0.1;
        v_score := v_score + (p_refinery_best::REAL / 100.0 + v_count_bonus) * w_refinery;
    END IF;

    IF p_industrial_best IS NOT NULL THEN
        v_count_bonus := LEAST(p_industrial_count::REAL / 3.0, 1.0) * 0.1;
        v_score := v_score + (p_industrial_best::REAL / 100.0 + v_count_bonus) * w_industrial;
    END IF;

    IF p_hightech_best IS NOT NULL THEN
        v_count_bonus := LEAST(p_hightech_count::REAL / 3.0, 1.0) * 0.1;
        v_score := v_score + (p_hightech_best::REAL / 100.0 + v_count_bonus) * w_hightech;
    END IF;

    IF p_military_best IS NOT NULL THEN
        v_count_bonus := LEAST(p_military_count::REAL / 3.0, 1.0) * 0.1;
        v_score := v_score + (p_military_best::REAL / 100.0 + v_count_bonus) * w_military;
    END IF;

    IF p_tourism_best IS NOT NULL THEN
        v_count_bonus := LEAST(p_tourism_count::REAL / 3.0, 1.0) * 0.1;
        v_score := v_score + (p_tourism_best::REAL / 100.0 + v_count_bonus) * w_tourism;
    END IF;

    -- Normalise to 0-100
    RETURN LEAST(ROUND((v_score * 100)::NUMERIC, 1)::REAL, 100.0);
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. TRIGGER: Mark dirty flags when system or body is updated
--    Ensures incremental rebuild jobs pick up all EDDN changes.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_mark_system_dirty()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE systems
    SET rating_dirty  = TRUE,
        cluster_dirty = TRUE,
        updated_at    = NOW()
    WHERE id64 = NEW.id64;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_mark_body_system_dirty()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE systems
    SET rating_dirty  = TRUE,
        cluster_dirty = TRUE,
        has_body_data = TRUE,
        updated_at    = NOW()
    WHERE id64 = NEW.system_id64;
    RETURN NEW;
END;
$$;

-- Apply triggers (DROP first to allow re-running this file safely)
DROP TRIGGER IF EXISTS trg_system_dirty ON systems;
CREATE TRIGGER trg_system_dirty
    AFTER UPDATE OF primary_economy, secondary_economy, population,
                    is_colonised, is_being_colonised
    ON systems
    FOR EACH ROW
    EXECUTE FUNCTION fn_mark_system_dirty();

DROP TRIGGER IF EXISTS trg_body_dirty ON bodies;
CREATE TRIGGER trg_body_dirty
    AFTER INSERT OR UPDATE ON bodies
    FOR EACH ROW
    EXECUTE FUNCTION fn_mark_body_system_dirty();

-- ---------------------------------------------------------------------------
-- 8. USEFUL VIEWS
-- ---------------------------------------------------------------------------

-- High-value uncolonised systems (top candidates for colonisation)
CREATE OR REPLACE VIEW top_uncolonised AS
SELECT
    s.id64, s.name, s.x, s.y, s.z,
    s.primary_economy, s.secondary_economy,
    s.main_star_type,
    r.score, r.economy_suggestion,
    r.elw_count, r.ww_count, r.ammonia_count,
    r.gas_giant_count, r.bio_signal_total, r.geo_signal_total,
    r.terraformable_count, r.neutron_count, r.black_hole_count
FROM systems s
JOIN ratings r ON r.system_id64 = s.id64
WHERE s.population = 0
  AND r.score IS NOT NULL
  AND r.score >= 40
ORDER BY r.score DESC;

-- Best colonisation clusters (top empire-building locations)
CREATE OR REPLACE VIEW top_clusters AS
SELECT
    s.id64, s.name, s.x, s.y, s.z, s.population,
    cs.coverage_score, cs.economy_diversity, cs.total_viable,
    cs.agriculture_count, cs.agriculture_best,
    cs.refinery_count,   cs.refinery_best,
    cs.industrial_count, cs.industrial_best,
    cs.hightech_count,   cs.hightech_best,
    cs.military_count,   cs.military_best,
    cs.tourism_count,    cs.tourism_best
FROM cluster_summary cs
JOIN systems s ON s.id64 = cs.system_id64
WHERE cs.coverage_score IS NOT NULL
  AND cs.economy_diversity >= 3
ORDER BY cs.coverage_score DESC;

-- Import progress summary
CREATE OR REPLACE VIEW import_progress AS
SELECT
    dump_file,
    status,
    rows_processed,
    rows_total,
    CASE WHEN rows_total > 0
        THEN round((rows_processed::NUMERIC / rows_total * 100), 1)
        ELSE 0
    END AS pct_complete,
    CASE WHEN bytes_total > 0
        THEN round((bytes_processed::NUMERIC / bytes_total * 100), 1)
        ELSE 0
    END AS bytes_pct,
    started_at,
    completed_at,
    CASE WHEN started_at IS NOT NULL AND completed_at IS NULL
        THEN extract(epoch FROM (NOW() - started_at))::INTEGER
        ELSE NULL
    END AS elapsed_seconds
FROM import_meta
ORDER BY id;

-- System full detail (systems + ratings + body counts joined)
CREATE OR REPLACE VIEW system_detail AS
SELECT
    s.*,
    r.score,
    r.score_agriculture, r.score_refinery, r.score_industrial,
    r.score_hightech, r.score_military, r.score_tourism,
    r.economy_suggestion,
    r.elw_count, r.ww_count, r.ammonia_count,
    r.gas_giant_count, r.rocky_count, r.metal_rich_count,
    r.icy_count, r.rocky_ice_count, r.hmc_count,
    r.landable_count, r.terraformable_count,
    r.bio_signal_total, r.geo_signal_total,
    r.neutron_count, r.black_hole_count, r.white_dwarf_count,
    r.score_breakdown,
    r.computed_at AS score_computed_at
FROM systems s
LEFT JOIN ratings r ON r.system_id64 = s.id64;

DO $$ BEGIN RAISE NOTICE 'Functions and views created successfully.'; END $$;
