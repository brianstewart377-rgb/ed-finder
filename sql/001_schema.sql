-- =============================================================================
-- ED Finder — Hetzner PostgreSQL Schema
-- Version: 2.0
-- Target:  PostgreSQL 16
-- Server:  Hetzner AX41 (i7-8700, 128GB RAM, 2×1TB SSD)
--
-- Changes in v2.0:
--   • Added galaxy_regions table (42 named ED codex regions)
--   • Added galaxy_region_id to systems (populated during import)
--   • Added needs_permit to systems (fixes API/schema disconnect)
--   • Added main_star_class to systems (alias for main_star_type, fixes API)
--   • Added macro_grid_id to systems (2000 LY cube for cluster builder)
--   • Added macro_grid table (2000 LY cubes, unit of work for clusters)
--   • Added slots, body_quality, compactness, signal_quality,
--     orbital_safety, star_bonus to ratings (fixes API/schema disconnect)
--   • Added import_errors table (structured error logging)
--   • Replaced cluster_summary with region_clusters (macro-grid approach)
--   • Kept cluster_summary for incremental EDDN dirty-rebuild path
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fast ILIKE / trigram search on names
CREATE EXTENSION IF NOT EXISTS btree_gin; -- GIN indexes on scalar types

-- ---------------------------------------------------------------------------
-- Enums
--
-- PostgreSQL does not support "CREATE TYPE ... IF NOT EXISTS", so re-running
-- this script against an existing database (e.g. after a schema edit) would
-- crash with "type already exists". Wrapping each CREATE TYPE in a DO block
-- lets the script be idempotent.
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE economy_type AS ENUM (
        'Agriculture', 'Refinery', 'Industrial', 'HighTech',
        'Military', 'Tourism', 'Extraction', 'Colony',
        'Terraforming', 'Prison', 'Damaged', 'Rescue',
        'Repair', 'Carrier', 'None', 'Unknown'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE security_type AS ENUM (
        'High', 'Medium', 'Low', 'Anarchy', 'Lawless', 'Unknown'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE allegiance_type AS ENUM (
        'Federation', 'Empire', 'Alliance', 'Independent',
        'Thargoid', 'Guardian', 'PilotsFederation', 'None', 'Unknown'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE government_type AS ENUM (
        'Democracy', 'Dictatorship', 'Feudal', 'Patronage',
        'Corporate', 'Cooperative', 'Theocracy', 'Anarchy',
        'Communism', 'Confederacy', 'None', 'Unknown'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE body_type AS ENUM (
        'Star', 'Planet', 'Moon', 'Barycentre', 'Unknown'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE station_type AS ENUM (
        'Coriolis', 'Orbis', 'Ocellus', 'Outpost',
        'PlanetaryPort', 'PlanetaryOutpost', 'MegaShip',
        'AsteroidBase', 'FleetCarrier', 'Unknown'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE import_status AS ENUM (
        'pending', 'running', 'complete', 'failed', 'partial'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
-- 0. GALAXY_REGIONS  (42 named Elite Dangerous codex regions)
--    Populated once at startup from the static RegionMapData.
--    id matches the region index from klightspeed/EliteDangerousRegionMap.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS galaxy_regions (
    id          SMALLINT    PRIMARY KEY,   -- 1–42, matches RegionMapData index
    name        TEXT        NOT NULL UNIQUE
);

-- Pre-populate all 42 named regions
INSERT INTO galaxy_regions (id, name) VALUES
    (1,  'Galactic Centre'),
    (2,  'Empyrean Straits'),
    (3,  'Ryker''s Hope'),
    (4,  'Odin''s Hold'),
    (5,  'Norma Arm'),
    (6,  'Arcadian Stream'),
    (7,  'Izanami'),
    (8,  'Inner Orion-Perseus Conflux'),
    (9,  'Inner Scutum-Centaurus Arm'),
    (10, 'Norma Expanse'),
    (11, 'Trojan Belt'),
    (12, 'The Veils'),
    (13, 'Newton''s Vault'),
    (14, 'The Conduit'),
    (15, 'Outer Orion-Perseus Conflux'),
    (16, 'Orion-Cygnus Arm'),
    (17, 'Temple'),
    (18, 'Inner Orion Spur'),
    (19, 'Hawking''s Gap'),
    (20, 'Dryman''s Point'),
    (21, 'Sagittarius-Carina Arm'),
    (22, 'Mare Somnia'),
    (23, 'Acheron'),
    (24, 'Formorian Frontier'),
    (25, 'Hieronymus Delta'),
    (26, 'Outer Scutum-Centaurus Arm'),
    (27, 'Outer Arm'),
    (28, 'Aquila''s Halo'),
    (29, 'Errant Marches'),
    (30, 'Perseus Arm'),
    (31, 'Formidine Rift'),
    (32, 'Vulcan Gate'),
    (33, 'Elysian Shore'),
    (34, 'Sanguineous Rim'),
    (35, 'Outer Orion Spur'),
    (36, 'Achilles''s Altar'),
    (37, 'Xibalba'),
    (38, 'Lyra''s Song'),
    (39, 'Tenebrae'),
    (40, 'The Abyss'),
    (41, 'Kepler''s Crest'),
    (42, 'The Void')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 1. SYSTEMS  (186M rows)
--    Core system data from galaxy.json.gz + galaxy_populated.json.gz
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS systems (
    id64                BIGINT          PRIMARY KEY,
    name                TEXT            NOT NULL,

    -- Coordinates (Elite internal units, 1:1 with light years from Sol)
    x                   REAL            NOT NULL DEFAULT 0,
    y                   REAL            NOT NULL DEFAULT 0,
    z                   REAL            NOT NULL DEFAULT 0,

    -- Economy
    primary_economy     economy_type    NOT NULL DEFAULT 'Unknown',
    secondary_economy   economy_type    NOT NULL DEFAULT 'None',

    -- Population & colonisation
    population          BIGINT          NOT NULL DEFAULT 0,
    is_colonised        BOOLEAN         NOT NULL DEFAULT FALSE,
    is_being_colonised  BOOLEAN         NOT NULL DEFAULT FALSE,
    controlling_faction TEXT,

    -- Politics
    security            security_type   NOT NULL DEFAULT 'Unknown',
    allegiance          allegiance_type NOT NULL DEFAULT 'Unknown',
    government          government_type NOT NULL DEFAULT 'Unknown',

    -- Permit requirement (some systems require a permit to enter)
    needs_permit        BOOLEAN         NOT NULL DEFAULT FALSE,

    -- Primary star
    main_star_type      TEXT,           -- single letter: O, B, A, F, G, K, M, etc.
    main_star_subtype   TEXT,           -- remainder of spectral class
    main_star_is_scoopable BOOLEAN      DEFAULT NULL,
    -- Alias used by the API layer (same as main_star_type, kept for compatibility)
    main_star_class     TEXT
        GENERATED ALWAYS AS (main_star_type) STORED,

    -- Spatial grid cell (set by build_grid.py, 500ly cubes)
    grid_cell_id        BIGINT          DEFAULT NULL,

    -- Macro-grid cell (set by build_grid.py, 2000ly cubes — cluster builder unit)
    macro_grid_id       BIGINT          DEFAULT NULL,

    -- Named galactic region (1–42, set during import via findRegion())
    galaxy_region_id    SMALLINT        DEFAULT NULL
                            REFERENCES galaxy_regions(id) ON DELETE SET NULL,

    -- Data quality flags
    has_body_data       BOOLEAN         NOT NULL DEFAULT FALSE,
    body_count          INTEGER         NOT NULL DEFAULT 0,
    data_quality        SMALLINT        NOT NULL DEFAULT 0,

    -- Timestamps
    first_discovered_at TIMESTAMPTZ     DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    eddn_updated_at     TIMESTAMPTZ     DEFAULT NULL,

    -- Dirty flags for incremental rebuild jobs
    rating_dirty        BOOLEAN         NOT NULL DEFAULT TRUE,
    cluster_dirty       BOOLEAN         NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------------
-- 2. BODIES  (~800M rows)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bodies (
    id                  BIGINT          PRIMARY KEY,
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    name                TEXT            NOT NULL,

    body_type           body_type       NOT NULL DEFAULT 'Unknown',
    subtype             TEXT,
    is_main_star        BOOLEAN         NOT NULL DEFAULT FALSE,

    distance_from_star  REAL            DEFAULT NULL,
    orbital_period      REAL            DEFAULT NULL,
    semi_major_axis     REAL            DEFAULT NULL,
    orbital_eccentricity REAL           DEFAULT NULL,
    orbital_inclination REAL            DEFAULT NULL,
    arg_of_periapsis    REAL            DEFAULT NULL,
    mean_anomaly        REAL            DEFAULT NULL,
    ascending_node      REAL            DEFAULT NULL,
    is_tidal_lock       BOOLEAN         DEFAULT NULL,

    radius              REAL            DEFAULT NULL,
    mass                REAL            DEFAULT NULL,
    gravity             REAL            DEFAULT NULL,
    surface_temp        REAL            DEFAULT NULL,
    surface_pressure    REAL            DEFAULT NULL,

    atmosphere_type     TEXT            DEFAULT NULL,
    atmosphere_composition JSONB        DEFAULT NULL,

    volcanism           TEXT            DEFAULT NULL,
    solid_composition   JSONB           DEFAULT NULL,
    materials           JSONB           DEFAULT NULL,

    terraforming_state  TEXT            DEFAULT NULL,
    is_terraformable    BOOLEAN         NOT NULL DEFAULT FALSE,
    is_landable         BOOLEAN         NOT NULL DEFAULT FALSE,
    is_water_world      BOOLEAN         NOT NULL DEFAULT FALSE,
    is_earth_like       BOOLEAN         NOT NULL DEFAULT FALSE,
    is_ammonia_world    BOOLEAN         NOT NULL DEFAULT FALSE,

    bio_signal_count    SMALLINT        NOT NULL DEFAULT 0,
    geo_signal_count    SMALLINT        NOT NULL DEFAULT 0,

    spectral_class      TEXT            DEFAULT NULL,
    luminosity          TEXT            DEFAULT NULL,
    stellar_mass        REAL            DEFAULT NULL,
    absolute_magnitude  REAL            DEFAULT NULL,
    age_my              INTEGER         DEFAULT NULL,
    is_scoopable        BOOLEAN         DEFAULT NULL,

    estimated_mapping_value  INTEGER    DEFAULT NULL,
    estimated_scan_value     INTEGER    DEFAULT NULL,

    first_discovered_at TIMESTAMPTZ     DEFAULT NULL,
    first_mapped_at     TIMESTAMPTZ     DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 3. STATIONS  (~5M rows)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stations (
    id                  BIGINT          PRIMARY KEY,
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    name                TEXT            NOT NULL,
    station_type        station_type    NOT NULL DEFAULT 'Unknown',

    distance_from_star  REAL            DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,

    landing_pad_size    TEXT            DEFAULT NULL,
    has_market          BOOLEAN         NOT NULL DEFAULT FALSE,
    has_shipyard        BOOLEAN         NOT NULL DEFAULT FALSE,
    has_outfitting      BOOLEAN         NOT NULL DEFAULT FALSE,
    has_refuel          BOOLEAN         NOT NULL DEFAULT FALSE,
    has_repair          BOOLEAN         NOT NULL DEFAULT FALSE,
    has_rearm           BOOLEAN         NOT NULL DEFAULT FALSE,
    has_black_market    BOOLEAN         NOT NULL DEFAULT FALSE,
    has_material_trader BOOLEAN         NOT NULL DEFAULT FALSE,
    has_technology_broker BOOLEAN       NOT NULL DEFAULT FALSE,
    has_interstellar_factors BOOLEAN    NOT NULL DEFAULT FALSE,
    has_universal_cartographics BOOLEAN NOT NULL DEFAULT FALSE,
    has_search_rescue   BOOLEAN         NOT NULL DEFAULT FALSE,

    primary_economy     economy_type    DEFAULT NULL,
    secondary_economy   economy_type    DEFAULT NULL,
    prohibited_commodities JSONB        DEFAULT NULL,

    controlling_faction TEXT            DEFAULT NULL,
    allegiance          allegiance_type NOT NULL DEFAULT 'Unknown',
    government          government_type NOT NULL DEFAULT 'Unknown',

    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4. STATION_ECONOMIES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS station_economies (
    station_id          BIGINT          NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    economy             economy_type    NOT NULL,
    proportion          REAL            NOT NULL DEFAULT 1.0,
    PRIMARY KEY (station_id, economy)
);

-- ---------------------------------------------------------------------------
-- 5. FACTIONS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS factions (
    id                  SERIAL          PRIMARY KEY,
    name                TEXT            UNIQUE NOT NULL,
    allegiance          allegiance_type NOT NULL DEFAULT 'Unknown',
    government          government_type NOT NULL DEFAULT 'Unknown',
    is_player_faction   BOOLEAN         NOT NULL DEFAULT FALSE,
    home_system_id64    BIGINT          DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 6. SYSTEM_FACTIONS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_factions (
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    faction_id          INTEGER         NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
    influence           REAL            DEFAULT NULL,
    state               TEXT            DEFAULT NULL,
    is_controlling      BOOLEAN         NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (system_id64, faction_id)
);

-- ---------------------------------------------------------------------------
-- 7. ATTRACTIONS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attractions (
    id                  BIGSERIAL       PRIMARY KEY,
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    body_id             BIGINT          DEFAULT NULL REFERENCES bodies(id) ON DELETE SET NULL,
    body_name           TEXT            DEFAULT NULL,

    attraction_type     TEXT            NOT NULL,
    subtype             TEXT            DEFAULT NULL,
    genus               TEXT            DEFAULT NULL,
    species             TEXT            DEFAULT NULL,
    variant             TEXT            DEFAULT NULL,

    latitude            REAL            DEFAULT NULL,
    longitude           REAL            DEFAULT NULL,

    estimated_value     BIGINT          DEFAULT NULL,

    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 8. RATINGS  (pre-computed scores for all visited systems)
--    v2.0: Added detailed score components to match what the API expects.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ratings (
    system_id64         BIGINT          PRIMARY KEY REFERENCES systems(id64) ON DELETE CASCADE,

    -- Overall score (0-100)
    score               SMALLINT        DEFAULT NULL,

    -- Economy suitability scores (0-100 each)
    score_agriculture   SMALLINT        DEFAULT NULL,
    score_refinery      SMALLINT        DEFAULT NULL,
    score_industrial    SMALLINT        DEFAULT NULL,
    score_hightech      SMALLINT        DEFAULT NULL,
    score_military      SMALLINT        DEFAULT NULL,
    score_tourism       SMALLINT        DEFAULT NULL,

    -- Suggested primary economy
    economy_suggestion  economy_type    DEFAULT NULL,

    -- Body counts (used by frontend filters)
    elw_count           SMALLINT        NOT NULL DEFAULT 0,
    ww_count            SMALLINT        NOT NULL DEFAULT 0,
    ammonia_count       SMALLINT        NOT NULL DEFAULT 0,
    gas_giant_count     SMALLINT        NOT NULL DEFAULT 0,
    rocky_count         SMALLINT        NOT NULL DEFAULT 0,
    metal_rich_count    SMALLINT        NOT NULL DEFAULT 0,
    icy_count           SMALLINT        NOT NULL DEFAULT 0,
    rocky_ice_count     SMALLINT        NOT NULL DEFAULT 0,
    hmc_count           SMALLINT        NOT NULL DEFAULT 0,
    landable_count      SMALLINT        NOT NULL DEFAULT 0,
    terraformable_count SMALLINT        NOT NULL DEFAULT 0,
    bio_signal_total    SMALLINT        NOT NULL DEFAULT 0,
    geo_signal_total    SMALLINT        NOT NULL DEFAULT 0,
    neutron_count       SMALLINT        NOT NULL DEFAULT 0,
    black_hole_count    SMALLINT        NOT NULL DEFAULT 0,
    white_dwarf_count   SMALLINT        NOT NULL DEFAULT 0,

    -- Detailed score components (v2.0 — matches API score_components field)
    slots               SMALLINT        DEFAULT NULL,  -- available build slots (0-20)
    body_quality        SMALLINT        DEFAULT NULL,  -- body quality score (0-100)
    compactness         SMALLINT        DEFAULT NULL,  -- orbital compactness (0-100)
    signal_quality      SMALLINT        DEFAULT NULL,  -- bio/geo signal quality (0-100)
    orbital_safety      SMALLINT        DEFAULT NULL,  -- orbital safety score (0-100)
    star_bonus          SMALLINT        DEFAULT NULL,  -- star type bonus (0-10)

    -- Full score breakdown JSON (for popover display)
    score_breakdown     JSONB           DEFAULT NULL,

    -- Timestamps
    computed_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 9. SPATIAL_GRID  (500ly cube partitioning)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spatial_grid (
    cell_id             BIGINT          PRIMARY KEY,

    cell_x              SMALLINT        NOT NULL,
    cell_y              SMALLINT        NOT NULL,
    cell_z              SMALLINT        NOT NULL,

    min_x               REAL            NOT NULL,
    max_x               REAL            NOT NULL,
    min_y               REAL            NOT NULL,
    max_y               REAL            NOT NULL,
    min_z               REAL            NOT NULL,
    max_z               REAL            NOT NULL,

    system_count        INTEGER         NOT NULL DEFAULT 0,
    visited_count       INTEGER         NOT NULL DEFAULT 0,

    UNIQUE (cell_x, cell_y, cell_z)
);

-- ---------------------------------------------------------------------------
-- 10. MACRO_GRID  (2000ly cube partitioning — unit of work for cluster builder)
--     Each cell covers a 2000 LY cube. There are roughly 500–1000 populated
--     macro-cells across the inhabited galaxy vs 125,000 500 LY cells.
--     The cluster builder processes one macro-cell at a time, finding the
--     top 50 anchors within it and computing their 500 LY bubble stats.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS macro_grid (
    cell_id             BIGINT          PRIMARY KEY,

    cell_x              SMALLINT        NOT NULL,
    cell_y              SMALLINT        NOT NULL,
    cell_z              SMALLINT        NOT NULL,

    min_x               REAL            NOT NULL,
    max_x               REAL            NOT NULL,
    min_y               REAL            NOT NULL,
    max_y               REAL            NOT NULL,
    min_z               REAL            NOT NULL,
    max_z               REAL            NOT NULL,

    system_count        INTEGER         NOT NULL DEFAULT 0,
    anchor_count        INTEGER         NOT NULL DEFAULT 0,  -- systems with body data

    UNIQUE (cell_x, cell_y, cell_z)
);

-- ---------------------------------------------------------------------------
-- 11. CLUSTER_SUMMARY  (pre-aggregated per-anchor bubble stats)
--     Built by build_clusters.py. One row per anchor system.
--     The macro-grid approach means we only compute this for the top-50
--     anchors per macro-cell, not every system in the galaxy.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_summary (
    system_id64         BIGINT          PRIMARY KEY REFERENCES systems(id64) ON DELETE CASCADE,

    agriculture_count   SMALLINT        NOT NULL DEFAULT 0,
    agriculture_best    SMALLINT        DEFAULT NULL,
    agriculture_top_id  BIGINT          DEFAULT NULL,

    refinery_count      SMALLINT        NOT NULL DEFAULT 0,
    refinery_best       SMALLINT        DEFAULT NULL,
    refinery_top_id     BIGINT          DEFAULT NULL,

    industrial_count    SMALLINT        NOT NULL DEFAULT 0,
    industrial_best     SMALLINT        DEFAULT NULL,
    industrial_top_id   BIGINT          DEFAULT NULL,

    hightech_count      SMALLINT        NOT NULL DEFAULT 0,
    hightech_best       SMALLINT        DEFAULT NULL,
    hightech_top_id     BIGINT          DEFAULT NULL,

    military_count      SMALLINT        NOT NULL DEFAULT 0,
    military_best       SMALLINT        DEFAULT NULL,
    military_top_id     BIGINT          DEFAULT NULL,

    tourism_count       SMALLINT        NOT NULL DEFAULT 0,
    tourism_best        SMALLINT        DEFAULT NULL,
    tourism_top_id      BIGINT          DEFAULT NULL,

    total_viable        SMALLINT        NOT NULL DEFAULT 0,
    coverage_score      REAL            DEFAULT NULL,
    economy_diversity   SMALLINT        NOT NULL DEFAULT 0,
    search_radius       SMALLINT        NOT NULL DEFAULT 500,

    -- Which macro-cell this anchor belongs to (for region-aware queries)
    macro_grid_id       BIGINT          DEFAULT NULL REFERENCES macro_grid(cell_id) ON DELETE SET NULL,

    dirty               BOOLEAN         NOT NULL DEFAULT TRUE,

    computed_at         TIMESTAMPTZ     DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 12. WATCHLIST
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS watchlist (
    id                  SERIAL          PRIMARY KEY,
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    name                TEXT            NOT NULL,
    x                   REAL            DEFAULT NULL,
    y                   REAL            DEFAULT NULL,
    z                   REAL            DEFAULT NULL,
    population          BIGINT          DEFAULT NULL,
    is_colonised        BOOLEAN         DEFAULT FALSE,
    alert_min_score     SMALLINT        DEFAULT NULL,
    alert_economy       TEXT            DEFAULT NULL,
    added_at            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_checked_at     TIMESTAMPTZ     DEFAULT NULL,
    last_status         TEXT            DEFAULT NULL,
    UNIQUE (system_id64)
);

-- ---------------------------------------------------------------------------
-- 13. WATCHLIST_CHANGELOG
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS watchlist_changelog (
    id                  BIGSERIAL       PRIMARY KEY,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            NOT NULL,
    change_type         TEXT            NOT NULL,
    old_value           TEXT            DEFAULT NULL,
    new_value           TEXT            DEFAULT NULL,
    detected_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 14. SYSTEM_NOTES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_notes (
    system_id64         BIGINT          PRIMARY KEY REFERENCES systems(id64) ON DELETE CASCADE,
    note                TEXT            NOT NULL DEFAULT '',
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 15. API_CACHE
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key           TEXT            PRIMARY KEY,
    response_json       JSONB           NOT NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     NOT NULL,
    hit_count           INTEGER         NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 16. EDDN_LOG  (rolling 7-day window)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eddn_log (
    id                  BIGSERIAL       PRIMARY KEY,
    event_type          TEXT            NOT NULL,
    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    raw_event           JSONB           DEFAULT NULL,
    processed           BOOLEAN         NOT NULL DEFAULT FALSE,
    received_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 17. IMPORT_META  (resumable import checkpoints)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_meta (
    id                  SERIAL          PRIMARY KEY,
    dump_file           TEXT            NOT NULL UNIQUE,
    status              import_status   NOT NULL DEFAULT 'pending',
    rows_processed      BIGINT          NOT NULL DEFAULT 0,
    rows_total          BIGINT          DEFAULT NULL,
    bytes_processed     BIGINT          NOT NULL DEFAULT 0,
    bytes_total         BIGINT          DEFAULT NULL,
    errors_encountered  INTEGER         NOT NULL DEFAULT 0,  -- v2.0: track error count
    last_checkpoint     BIGINT          NOT NULL DEFAULT 0,
    started_at          TIMESTAMPTZ     DEFAULT NULL,
    completed_at        TIMESTAMPTZ     DEFAULT NULL,
    error_message       TEXT            DEFAULT NULL,
    checksum            TEXT            DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

INSERT INTO import_meta (dump_file) VALUES
    ('galaxy.json.gz'),
    ('galaxy_populated.json.gz'),
    ('galaxy_stations.json.gz')
ON CONFLICT (dump_file) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 18. IMPORT_ERRORS  (structured per-record error log — v2.0)
--     Replaces grepping 500MB log files. Query directly to see exactly
--     which systems/bodies failed and why.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_errors (
    id                  BIGSERIAL       PRIMARY KEY,
    dump_file           TEXT            NOT NULL,
    record_id           BIGINT          DEFAULT NULL,   -- id64 or body id
    record_type         TEXT            NOT NULL,       -- 'system', 'body', 'station'
    error_class         TEXT            NOT NULL,       -- exception class name
    error_message       TEXT            NOT NULL,
    raw_snippet         TEXT            DEFAULT NULL,   -- first 500 chars of the raw record
    occurred_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 19. APP_META  (key-value store for app-level settings & state)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_meta (
    key                 TEXT            PRIMARY KEY,
    value               TEXT            NOT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

INSERT INTO app_meta (key, value) VALUES
    ('schema_version',      '2.0'),
    ('import_complete',     'false'),
    ('ratings_built',       'false'),
    ('grid_built',          'false'),
    ('macro_grid_built',    'false'),
    ('clusters_built',      'false'),
    ('eddn_enabled',        'false'),
    ('last_nightly_update', 'never')
ON CONFLICT (key) DO NOTHING;
