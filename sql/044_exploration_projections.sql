-- =============================================================================
-- Personal exploration normalized projections
-- =============================================================================
-- Raw exploration_facts remains the replayable source of truth.  These tables
-- are sync-key-scoped read models rebuilt by rebuild_exploration_projections().
-- They deliberately have no foreign key to systems: personal journals may
-- contain systems which are not present in the shared catalogue yet.

CREATE TABLE IF NOT EXISTS exploration_visits (
    fact_id             BIGINT          PRIMARY KEY
                            REFERENCES exploration_facts(id) ON DELETE CASCADE,
    sync_key            TEXT            NOT NULL,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            DEFAULT NULL,
    visited_at          TIMESTAMPTZ     NOT NULL,
    source              TEXT            NOT NULL,
    x                   REAL            DEFAULT NULL,
    y                   REAL            DEFAULT NULL,
    z                   REAL            DEFAULT NULL,
    galaxy_region_id    SMALLINT        DEFAULT NULL,
    is_first_visit      BOOLEAN         NOT NULL DEFAULT FALSE,
    is_last_visit       BOOLEAN         NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_exploration_visits_sync_time
    ON exploration_visits (sync_key, visited_at DESC, fact_id DESC);
CREATE INDEX IF NOT EXISTS idx_exploration_visits_sync_system
    ON exploration_visits (sync_key, system_id64, visited_at);
CREATE INDEX IF NOT EXISTS idx_exploration_visits_sync_xyz
    ON exploration_visits (sync_key, x, y, z)
    WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL;

CREATE TABLE IF NOT EXISTS exploration_expedition_routes (
    visit_fact_id       BIGINT          PRIMARY KEY
                            REFERENCES exploration_visits(fact_id) ON DELETE CASCADE,
    sync_key            TEXT            NOT NULL,
    sequence_no         BIGINT          NOT NULL,
    departed_at         TIMESTAMPTZ     DEFAULT NULL,
    arrived_at          TIMESTAMPTZ     NOT NULL,
    from_system_id64    BIGINT          DEFAULT NULL,
    from_system_name    TEXT            DEFAULT NULL,
    from_x              REAL            DEFAULT NULL,
    from_y              REAL            DEFAULT NULL,
    from_z              REAL            DEFAULT NULL,
    to_system_id64      BIGINT          NOT NULL,
    to_system_name      TEXT            DEFAULT NULL,
    to_x                REAL            DEFAULT NULL,
    to_y                REAL            DEFAULT NULL,
    to_z                REAL            DEFAULT NULL,
    distance_ly         DOUBLE PRECISION DEFAULT NULL,
    CONSTRAINT uq_exploration_route_sequence UNIQUE (sync_key, sequence_no)
);

CREATE INDEX IF NOT EXISTS idx_exploration_routes_sync_arrived
    ON exploration_expedition_routes (sync_key, arrived_at DESC, sequence_no DESC);

CREATE TABLE IF NOT EXISTS exploration_body_completeness (
    sync_key            TEXT            NOT NULL,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            DEFAULT NULL,
    body_key            TEXT            NOT NULL,
    body_id             INTEGER         DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    first_observed_at   TIMESTAMPTZ     NOT NULL,
    last_observed_at    TIMESTAMPTZ     NOT NULL,
    fss_state           TEXT            NOT NULL DEFAULT 'discovered'
                            CHECK (fss_state IN ('discovered', 'scanned')),
    dss_state           TEXT            NOT NULL DEFAULT 'unmapped'
                            CHECK (dss_state IN ('unmapped', 'mapped')),
    map_progress        NUMERIC(5,2)    NOT NULL DEFAULT 0
                            CHECK (map_progress >= 0 AND map_progress <= 100),
    first_discovered    BOOLEAN         NOT NULL DEFAULT FALSE,
    first_mapped        BOOLEAN         NOT NULL DEFAULT FALSE,
    signal_count        INTEGER         NOT NULL DEFAULT 0,
    PRIMARY KEY (sync_key, system_id64, body_key)
);

CREATE INDEX IF NOT EXISTS idx_exploration_body_completeness_system
    ON exploration_body_completeness (sync_key, system_id64);

CREATE TABLE IF NOT EXISTS exobiology_sales (
    fact_id             BIGINT          NOT NULL
                            REFERENCES exploration_facts(id) ON DELETE CASCADE,
    line_no             INTEGER         NOT NULL,
    sync_key            TEXT            NOT NULL,
    batch_id            TEXT            NOT NULL,
    sold_at             TIMESTAMPTZ     NOT NULL,
    market_id           BIGINT          DEFAULT NULL,
    genus               TEXT            DEFAULT NULL,
    species             TEXT            DEFAULT NULL,
    value               BIGINT          NOT NULL DEFAULT 0,
    bonus               BIGINT          NOT NULL DEFAULT 0,
    total_value         BIGINT          NOT NULL DEFAULT 0,
    PRIMARY KEY (fact_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_exobiology_sales_sync_time
    ON exobiology_sales (sync_key, sold_at DESC);
CREATE INDEX IF NOT EXISTS idx_exobiology_sales_sync_taxon
    ON exobiology_sales (sync_key, genus, species);

CREATE TABLE IF NOT EXISTS exobiology_organisms (
    sync_key            TEXT            NOT NULL,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            DEFAULT NULL,
    body_key            TEXT            NOT NULL,
    body_id             INTEGER         DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    genus               TEXT            NOT NULL,
    species             TEXT            DEFAULT NULL,
    variant             TEXT            DEFAULT NULL,
    sample_stage        SMALLINT        NOT NULL DEFAULT 0
                            CHECK (sample_stage BETWEEN 0 AND 3),
    first_sampled_at    TIMESTAMPTZ     NOT NULL,
    analysed_at         TIMESTAMPTZ     DEFAULT NULL,
    sold_at             TIMESTAMPTZ     DEFAULT NULL,
    analysed            BOOLEAN         NOT NULL DEFAULT FALSE,
    sold                BOOLEAN         NOT NULL DEFAULT FALSE,
    PRIMARY KEY (sync_key, system_id64, body_key, genus)
);

CREATE INDEX IF NOT EXISTS idx_exobiology_organisms_system
    ON exobiology_organisms (sync_key, system_id64);

CREATE TABLE IF NOT EXISTS codex_observations (
    sync_key            TEXT            NOT NULL,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            DEFAULT NULL,
    entry_id            BIGINT          NOT NULL,
    category            TEXT            DEFAULT NULL,
    sub_category        TEXT            DEFAULT NULL,
    entry_name          TEXT            DEFAULT NULL,
    region_id           SMALLINT        DEFAULT NULL,
    region              TEXT            NOT NULL DEFAULT 'Unknown',
    first_observed_at   TIMESTAMPTZ     NOT NULL,
    last_observed_at    TIMESTAMPTZ     NOT NULL,
    observation_count   INTEGER         NOT NULL DEFAULT 1,
    sold_status         TEXT            NOT NULL DEFAULT 'pending'
                            CHECK (sold_status IN ('pending', 'sold')),
    sold_at             TIMESTAMPTZ     DEFAULT NULL,
    PRIMARY KEY (sync_key, system_id64, entry_id, region)
);

CREATE INDEX IF NOT EXISTS idx_codex_observations_sync_region
    ON codex_observations (sync_key, region, category);

CREATE OR REPLACE FUNCTION exploration_jsonb_number(payload JSONB, field_name TEXT)
RETURNS DOUBLE PRECISION
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN payload ->> field_name ~ '^[-+]?[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?$'
    THEN (payload ->> field_name)::DOUBLE PRECISION
    ELSE NULL
END;

CREATE OR REPLACE FUNCTION exploration_jsonb_bigint(payload JSONB, field_name TEXT)
RETURNS BIGINT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN payload ->> field_name ~ '^[0-9]{1,18}$'
    THEN (payload ->> field_name)::BIGINT
    ELSE NULL
END;

CREATE OR REPLACE FUNCTION exploration_jsonb_boolean(payload JSONB, field_name TEXT)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE LOWER(payload ->> field_name)
    WHEN 'true' THEN TRUE
    WHEN 'false' THEN FALSE
    ELSE NULL
END;

CREATE OR REPLACE FUNCTION rebuild_exploration_projections(p_sync_key TEXT)
RETURNS TABLE (
    visits BIGINT,
    bodies BIGINT,
    organisms BIGINT,
    sales BIGINT,
    codex BIGINT,
    route_legs BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_visits BIGINT := 0;
    v_bodies BIGINT := 0;
    v_organisms BIGINT := 0;
    v_sales BIGINT := 0;
    v_codex BIGINT := 0;
    v_routes BIGINT := 0;
BEGIN
    DELETE FROM exploration_expedition_routes WHERE sync_key = p_sync_key;
    DELETE FROM exploration_visits WHERE sync_key = p_sync_key;
    DELETE FROM exploration_body_completeness WHERE sync_key = p_sync_key;
    DELETE FROM exobiology_organisms WHERE sync_key = p_sync_key;
    DELETE FROM exobiology_sales WHERE sync_key = p_sync_key;
    DELETE FROM codex_observations WHERE sync_key = p_sync_key;

    INSERT INTO exploration_visits (
        fact_id, sync_key, system_id64, system_name, visited_at, source,
        x, y, z, galaxy_region_id, is_first_visit, is_last_visit
    )
    SELECT
        f.id, f.sync_key, f.system_id64, COALESCE(f.system_name, s.name),
        f.observed_at, f.source,
        COALESCE(s.x, exploration_jsonb_number(f.payload_json -> 'StarPos', '0')::REAL,
                 CASE WHEN jsonb_typeof(f.payload_json -> 'StarPos') = 'array'
                      THEN exploration_jsonb_number(jsonb_build_object('v', f.payload_json -> 'StarPos' -> 0), 'v')::REAL END),
        COALESCE(s.y, CASE WHEN jsonb_typeof(f.payload_json -> 'StarPos') = 'array'
                      THEN exploration_jsonb_number(jsonb_build_object('v', f.payload_json -> 'StarPos' -> 1), 'v')::REAL END),
        COALESCE(s.z, CASE WHEN jsonb_typeof(f.payload_json -> 'StarPos') = 'array'
                      THEN exploration_jsonb_number(jsonb_build_object('v', f.payload_json -> 'StarPos' -> 2), 'v')::REAL END),
        s.galaxy_region_id,
        ROW_NUMBER() OVER (PARTITION BY f.system_id64 ORDER BY f.observed_at, f.id) = 1,
        ROW_NUMBER() OVER (PARTITION BY f.system_id64 ORDER BY f.observed_at DESC, f.id DESC) = 1
    FROM exploration_facts f
    LEFT JOIN systems s ON s.id64 = f.system_id64
    WHERE f.sync_key = p_sync_key
      AND f.event_type IN ('FSDJump', 'Location', 'CarrierJump');
    GET DIAGNOSTICS v_visits = ROW_COUNT;

    INSERT INTO exploration_expedition_routes (
        visit_fact_id, sync_key, sequence_no, departed_at, arrived_at,
        from_system_id64, from_system_name, from_x, from_y, from_z,
        to_system_id64, to_system_name, to_x, to_y, to_z, distance_ly
    )
    WITH ordered AS (
        SELECT v.*,
               ROW_NUMBER() OVER (ORDER BY visited_at, fact_id) AS seq,
               LAG(visited_at) OVER (ORDER BY visited_at, fact_id) AS prev_at,
               LAG(system_id64) OVER (ORDER BY visited_at, fact_id) AS prev_id,
               LAG(system_name) OVER (ORDER BY visited_at, fact_id) AS prev_name,
               LAG(x) OVER (ORDER BY visited_at, fact_id) AS prev_x,
               LAG(y) OVER (ORDER BY visited_at, fact_id) AS prev_y,
               LAG(z) OVER (ORDER BY visited_at, fact_id) AS prev_z
        FROM exploration_visits v
        WHERE sync_key = p_sync_key
    )
    SELECT fact_id, sync_key, seq, prev_at, visited_at,
           prev_id, prev_name, prev_x, prev_y, prev_z,
           system_id64, system_name, x, y, z,
           CASE WHEN prev_x IS NOT NULL AND prev_y IS NOT NULL AND prev_z IS NOT NULL
                     AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL
                THEN SQRT(POWER(x - prev_x, 2) + POWER(y - prev_y, 2) + POWER(z - prev_z, 2))
                ELSE NULL END
    FROM ordered;
    GET DIAGNOSTICS v_routes = ROW_COUNT;

    INSERT INTO exploration_body_completeness (
        sync_key, system_id64, system_name, body_key, body_id, body_name,
        first_observed_at, last_observed_at, fss_state, dss_state,
        map_progress, first_discovered, first_mapped, signal_count
    )
    SELECT
        f.sync_key, f.system_id64, MAX(f.system_name),
        COALESCE(f.body_id::TEXT, LOWER(f.body_name)),
        MAX(f.body_id), MAX(f.body_name), MIN(f.observed_at), MAX(f.observed_at),
        CASE WHEN BOOL_OR(f.event_type = 'Scan') THEN 'scanned' ELSE 'discovered' END,
        CASE WHEN BOOL_OR(f.event_type = 'SAAScanComplete') THEN 'mapped' ELSE 'unmapped' END,
        LEAST(100, GREATEST(0, COALESCE(
            MAX(CASE WHEN f.event_type = 'SAAScanComplete' THEN 100.0 END),
            MAX(exploration_jsonb_number(f.payload_json, 'MapProgress')),
            MAX(exploration_jsonb_number(f.payload_json, 'MappingProgress')),
            0
        )))::NUMERIC(5,2),
        BOOL_OR(
            exploration_jsonb_boolean(f.payload_json, 'FirstDiscovery') IS TRUE
            OR (f.event_type = 'Scan' AND exploration_jsonb_boolean(f.payload_json, 'WasDiscovered') IS FALSE)
        ),
        BOOL_OR(
            exploration_jsonb_boolean(f.payload_json, 'FirstMapped') IS TRUE
            OR (f.event_type = 'SAAScanComplete' AND exploration_jsonb_boolean(f.payload_json, 'WasMapped') IS FALSE)
        ),
        COUNT(*) FILTER (WHERE f.event_type IN ('FSSBodySignals', 'SAASignalsFound'))
    FROM exploration_facts f
    WHERE f.sync_key = p_sync_key
      AND f.event_type IN ('Scan', 'FSSBodySignals', 'SAASignalsFound', 'SAAScanComplete', 'ScanOrganic')
      AND (f.body_id IS NOT NULL OR f.body_name IS NOT NULL)
    GROUP BY f.sync_key, f.system_id64, COALESCE(f.body_id::TEXT, LOWER(f.body_name));
    GET DIAGNOSTICS v_bodies = ROW_COUNT;

    INSERT INTO exobiology_sales (
        fact_id, line_no, sync_key, batch_id, sold_at, market_id,
        genus, species, value, bonus, total_value
    )
    SELECT
        f.id, item.ordinality::INTEGER, f.sync_key,
        COALESCE(f.payload_json ->> 'SaleID', f.payload_json ->> 'MarketID', f.id::TEXT),
        f.observed_at, exploration_jsonb_bigint(f.payload_json, 'MarketID'),
        COALESCE(item.value ->> 'Genus', item.value ->> 'Genus_Localised'),
        COALESCE(item.value ->> 'Species', item.value ->> 'Species_Localised'),
        COALESCE(exploration_jsonb_bigint(item.value, 'Value'), 0),
        COALESCE(exploration_jsonb_bigint(item.value, 'Bonus'), 0),
        COALESCE(
            exploration_jsonb_bigint(item.value, 'TotalValue'),
            exploration_jsonb_bigint(item.value, 'Value'), 0
        ) + COALESCE(exploration_jsonb_bigint(item.value, 'Bonus'), 0)
    FROM exploration_facts f
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(f.payload_json -> 'BioData') = 'array'
             THEN f.payload_json -> 'BioData'
             ELSE jsonb_build_array(f.payload_json) END
    ) WITH ORDINALITY AS item(value, ordinality)
    WHERE f.sync_key = p_sync_key
      AND f.event_type = 'SellOrganicData';
    GET DIAGNOSTICS v_sales = ROW_COUNT;

    INSERT INTO exobiology_organisms (
        sync_key, system_id64, system_name, body_key, body_id, body_name,
        genus, species, variant, sample_stage, first_sampled_at, analysed_at,
        sold_at, analysed, sold
    )
    WITH samples AS (
        SELECT f.*,
               COALESCE(f.body_id::TEXT, LOWER(f.body_name)) AS resolved_body_key,
               COALESCE(f.payload_json ->> 'Genus', f.payload_json ->> 'Genus_Localised',
                        f.payload_json ->> 'Species', f.payload_json ->> 'Species_Localised') AS resolved_genus,
               COALESCE(f.payload_json ->> 'Species', f.payload_json ->> 'Species_Localised') AS resolved_species,
               COALESCE(f.payload_json ->> 'Variant', f.payload_json ->> 'Variant_Localised') AS resolved_variant,
               CASE LOWER(COALESCE(f.payload_json ->> 'ScanType', f.payload_json ->> 'SampleStage', ''))
                   WHEN 'analyse' THEN 3 WHEN 'analyze' THEN 3
                   WHEN 'sample' THEN 2 WHEN 'log' THEN 1
                   ELSE COALESCE(exploration_jsonb_number(f.payload_json, 'SampleStage')::INTEGER, 1)
               END AS resolved_stage
        FROM exploration_facts f
        WHERE f.sync_key = p_sync_key
          AND f.event_type = 'ScanOrganic'
          AND (f.body_id IS NOT NULL OR f.body_name IS NOT NULL)
    ), grouped AS (
        SELECT sync_key, system_id64, MAX(system_name) AS system_name,
               resolved_body_key, MAX(body_id) AS body_id, MAX(body_name) AS body_name,
               resolved_genus, MAX(resolved_species) AS species, MAX(resolved_variant) AS variant,
               LEAST(3, GREATEST(0, MAX(resolved_stage)))::SMALLINT AS sample_stage,
               MIN(observed_at) AS first_sampled_at,
               MIN(observed_at) FILTER (WHERE resolved_stage >= 3) AS analysed_at
        FROM samples
        WHERE resolved_body_key IS NOT NULL AND resolved_genus IS NOT NULL
        GROUP BY sync_key, system_id64, resolved_body_key, resolved_genus
    )
    SELECT g.*,
           sale.sold_at,
           g.sample_stage >= 3,
           sale.sold_at IS NOT NULL
    FROM grouped g
    LEFT JOIN LATERAL (
        SELECT MIN(s.sold_at) AS sold_at
        FROM exobiology_sales s
        WHERE s.sync_key = g.sync_key
          AND (s.genus = g.resolved_genus OR (s.species IS NOT NULL AND s.species = g.species))
          AND s.sold_at >= g.first_sampled_at
    ) sale ON TRUE;
    GET DIAGNOSTICS v_organisms = ROW_COUNT;

    INSERT INTO codex_observations (
        sync_key, system_id64, system_name, entry_id, category, sub_category, entry_name,
        region_id, region, first_observed_at, last_observed_at,
        observation_count, sold_status, sold_at
    )
    WITH entries AS (
        SELECT f.*,
               exploration_jsonb_bigint(f.payload_json, 'EntryID') AS resolved_entry_id,
               COALESCE(f.payload_json ->> 'Category_Localised', f.payload_json ->> 'Category') AS resolved_category,
               COALESCE(f.payload_json ->> 'SubCategory_Localised', f.payload_json ->> 'SubCategory') AS resolved_sub_category,
               COALESCE(f.payload_json ->> 'Name_Localised', f.payload_json ->> 'Name') AS resolved_name,
               s.galaxy_region_id AS resolved_region_id,
               COALESCE(gr.name, f.payload_json ->> 'Region_Localised', f.payload_json ->> 'Region', 'Unknown') AS resolved_region
        FROM exploration_facts f
        LEFT JOIN systems s ON s.id64 = f.system_id64
        LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
        WHERE f.sync_key = p_sync_key AND f.event_type = 'CodexEntry'
    ), grouped AS (
        SELECT sync_key, system_id64, MAX(system_name) AS system_name,
               resolved_entry_id, MAX(resolved_category) AS category,
               MAX(resolved_sub_category) AS sub_category, MAX(resolved_name) AS entry_name,
               MAX(resolved_region_id) AS region_id, resolved_region,
               MIN(observed_at) AS first_observed_at, MAX(observed_at) AS last_observed_at,
               COUNT(*)::INTEGER AS observation_count,
               BOOL_OR(exploration_jsonb_boolean(payload_json, 'Sold') IS TRUE) AS explicitly_sold
        FROM entries
        WHERE resolved_entry_id IS NOT NULL
        GROUP BY sync_key, system_id64, resolved_entry_id, resolved_region
    )
    SELECT g.sync_key, g.system_id64, g.system_name, g.resolved_entry_id,
           g.category, g.sub_category, g.entry_name,
           g.region_id, g.resolved_region, g.first_observed_at, g.last_observed_at,
           g.observation_count,
           CASE WHEN g.explicitly_sold OR sale.sold_at IS NOT NULL THEN 'sold' ELSE 'pending' END,
           sale.sold_at
    FROM grouped g
    LEFT JOIN LATERAL (
        SELECT MIN(f.observed_at) AS sold_at
        FROM exploration_facts f
        WHERE f.sync_key = g.sync_key
          AND f.event_type IN ('SellExplorationData', 'MultiSellExplorationData', 'RedeemVoucher')
          AND f.observed_at >= g.first_observed_at
    ) sale ON TRUE;
    GET DIAGNOSTICS v_codex = ROW_COUNT;

    RETURN QUERY SELECT v_visits, v_bodies, v_organisms, v_sales, v_codex, v_routes;
END;
$$;

COMMENT ON FUNCTION rebuild_exploration_projections(TEXT)
    IS 'Idempotently rebuilds all normalized personal exploration projections for one sync key from exploration_facts.';
