-- =============================================================================
-- ED Finder — Hetzner PostgreSQL Schema
-- Version: 1.0
-- Target:  PostgreSQL 16
-- Server:  Hetzner AX41 (i7-8700, 128GB RAM, 2×1TB SSD)
--
-- Design principles:
--   • Indexes created SEPARATELY in 002_indexes.sql (after bulk import)
--   • All coords stored as REAL (4-byte float) — matches Elite's precision
--   • id64 is BIGINT throughout (Elite's 64-bit system addresses)
--   • NULL score = unvisited / insufficient data (never fabricated)
--   • cluster_summary pre-aggregated for sub-second multi-economy searches
--   • spatial_grid partitions galaxy into 500ly cubes for O(1) neighbour lookup
--   • All tables have updated_at for delta tracking
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fast ILIKE / trigram search on names
CREATE EXTENSION IF NOT EXISTS btree_gin; -- GIN indexes on scalar types

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
CREATE TYPE economy_type AS ENUM (
    'Agriculture', 'Refinery', 'Industrial', 'HighTech',
    'Military', 'Tourism', 'Extraction', 'Colony',
    'Terraforming', 'Prison', 'Damaged', 'Rescue',
    'Repair', 'Carrier', 'None', 'Unknown'
);

CREATE TYPE security_type AS ENUM (
    'High', 'Medium', 'Low', 'Anarchy', 'Lawless', 'Unknown'
);

CREATE TYPE allegiance_type AS ENUM (
    'Federation', 'Empire', 'Alliance', 'Independent',
    'Thargoid', 'Guardian', 'PilotsFederation', 'None', 'Unknown'
);

CREATE TYPE government_type AS ENUM (
    'Democracy', 'Dictatorship', 'Feudal', 'Patronage',
    'Corporate', 'Cooperative', 'Theocracy', 'Anarchy',
    'Communism', 'Confederacy', 'None', 'Unknown'
);

CREATE TYPE body_type AS ENUM (
    'Star', 'Planet', 'Moon', 'Barycentre', 'Unknown'
);

CREATE TYPE station_type AS ENUM (
    'Coriolis', 'Orbis', 'Ocellus', 'Outpost',
    'PlanetaryPort', 'PlanetaryOutpost', 'MegaShip',
    'AsteroidBase', 'FleetCarrier', 'Unknown'
);

CREATE TYPE import_status AS ENUM (
    'pending', 'running', 'complete', 'failed', 'partial'
);

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

    -- Primary star (from first body scan — quick filter without joining bodies)
    main_star_type      TEXT,
    main_star_subtype   TEXT,
    main_star_is_scoopable BOOLEAN      DEFAULT NULL,

    -- Spatial grid cell (set by build_grid.py, 500ly cubes)
    grid_cell_id        INTEGER         DEFAULT NULL,

    -- Data quality flags
    has_body_data       BOOLEAN         NOT NULL DEFAULT FALSE,  -- bodies table has rows for this system
    body_count          INTEGER         NOT NULL DEFAULT 0,
    data_quality        SMALLINT        NOT NULL DEFAULT 0,      -- 0=coords only, 1=star, 2=full bodies

    -- Timestamps
    first_discovered_at TIMESTAMPTZ     DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    eddn_updated_at     TIMESTAMPTZ     DEFAULT NULL,            -- last EDDN event for this system

    -- Dirty flags for incremental rebuild jobs
    rating_dirty        BOOLEAN         NOT NULL DEFAULT TRUE,
    cluster_dirty       BOOLEAN         NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------------
-- 2. BODIES  (~800M rows)
--    Every scanned body from bodies.json.gz
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bodies (
    id                  BIGINT          PRIMARY KEY,   -- Spansh body ID
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    name                TEXT            NOT NULL,

    -- Classification
    body_type           body_type       NOT NULL DEFAULT 'Unknown',
    subtype             TEXT,           -- e.g. 'Earth-like world', 'M (Red dwarf) Star'
    is_main_star        BOOLEAN         NOT NULL DEFAULT FALSE,

    -- Orbital properties
    distance_from_star  REAL            DEFAULT NULL,   -- light seconds
    orbital_period      REAL            DEFAULT NULL,   -- days
    semi_major_axis     REAL            DEFAULT NULL,   -- AU
    orbital_eccentricity REAL           DEFAULT NULL,
    orbital_inclination REAL            DEFAULT NULL,
    arg_of_periapsis    REAL            DEFAULT NULL,
    mean_anomaly        REAL            DEFAULT NULL,
    ascending_node      REAL            DEFAULT NULL,
    is_tidal_lock       BOOLEAN         DEFAULT NULL,

    -- Physical properties
    radius              REAL            DEFAULT NULL,   -- km
    mass                REAL            DEFAULT NULL,   -- Earth masses (planet) / Solar (star)
    gravity             REAL            DEFAULT NULL,   -- g
    surface_temp        REAL            DEFAULT NULL,   -- K
    surface_pressure    REAL            DEFAULT NULL,   -- atm

    -- Atmosphere
    atmosphere_type     TEXT            DEFAULT NULL,
    atmosphere_composition JSONB        DEFAULT NULL,   -- {N2: 0.7, O2: 0.2, ...}

    -- Surface
    volcanism           TEXT            DEFAULT NULL,
    solid_composition   JSONB           DEFAULT NULL,   -- {Rock: 0.7, Metal: 0.3}
    materials           JSONB           DEFAULT NULL,   -- {Iron: 19.8, Nickel: 14.9, ...}

    -- Terraforming & habitability
    terraforming_state  TEXT            DEFAULT NULL,
    is_terraformable    BOOLEAN         NOT NULL DEFAULT FALSE,
    is_landable         BOOLEAN         NOT NULL DEFAULT FALSE,
    is_water_world      BOOLEAN         NOT NULL DEFAULT FALSE,
    is_earth_like       BOOLEAN         NOT NULL DEFAULT FALSE,
    is_ammonia_world    BOOLEAN         NOT NULL DEFAULT FALSE,

    -- Biological / geological signals
    bio_signal_count    SMALLINT        NOT NULL DEFAULT 0,
    geo_signal_count    SMALLINT        NOT NULL DEFAULT 0,

    -- Star-specific fields
    spectral_class      TEXT            DEFAULT NULL,
    luminosity          TEXT            DEFAULT NULL,
    stellar_mass        REAL            DEFAULT NULL,
    absolute_magnitude  REAL            DEFAULT NULL,
    age_my              INTEGER         DEFAULT NULL,   -- million years
    is_scoopable        BOOLEAN         DEFAULT NULL,

    -- Mapped / scan values
    estimated_mapping_value  INTEGER    DEFAULT NULL,
    estimated_scan_value     INTEGER    DEFAULT NULL,

    -- Timestamps
    first_discovered_at TIMESTAMPTZ     DEFAULT NULL,
    first_mapped_at     TIMESTAMPTZ     DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 3. STATIONS  (~5M rows)
--    All stations, outposts, carriers from galaxy_stations.json.gz
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stations (
    id                  BIGINT          PRIMARY KEY,
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    name                TEXT            NOT NULL,
    station_type        station_type    NOT NULL DEFAULT 'Unknown',

    -- Location
    distance_from_star  REAL            DEFAULT NULL,   -- light seconds
    body_name           TEXT            DEFAULT NULL,   -- which body it orbits

    -- Capabilities
    landing_pad_size    TEXT            DEFAULT NULL,   -- 'S', 'M', 'L'
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

    -- Economy & market
    primary_economy     economy_type    DEFAULT NULL,
    secondary_economy   economy_type    DEFAULT NULL,
    prohibited_commodities JSONB        DEFAULT NULL,

    -- Controlling faction
    controlling_faction TEXT            DEFAULT NULL,
    allegiance          allegiance_type NOT NULL DEFAULT 'Unknown',
    government          government_type NOT NULL DEFAULT 'Unknown',

    -- Timestamps
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4. STATION_ECONOMIES  (many-to-many station↔economy with proportions)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS station_economies (
    station_id          BIGINT          NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    economy             economy_type    NOT NULL,
    proportion          REAL            NOT NULL DEFAULT 1.0,
    PRIMARY KEY (station_id, economy)
);

-- ---------------------------------------------------------------------------
-- 5. FACTIONS  (faction data from populated systems)
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
-- 6. SYSTEM_FACTIONS  (which factions are present in which systems)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_factions (
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    faction_id          INTEGER         NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
    influence           REAL            DEFAULT NULL,   -- 0.0 – 1.0
    state               TEXT            DEFAULT NULL,   -- 'CivilWar', 'Boom', etc.
    is_controlling      BOOLEAN         NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (system_id64, faction_id)
);

-- ---------------------------------------------------------------------------
-- 7. ATTRACTIONS  (~2M rows)
--    Biologicals, geology, Guardian/Thargoid sites, POIs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attractions (
    id                  BIGSERIAL       PRIMARY KEY,
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    body_id             BIGINT          DEFAULT NULL REFERENCES bodies(id) ON DELETE SET NULL,
    body_name           TEXT            DEFAULT NULL,

    -- Classification
    attraction_type     TEXT            NOT NULL,  -- 'Biology', 'Geology', 'Guardian', 'Thargoid', 'Other'
    subtype             TEXT            DEFAULT NULL,  -- 'Bacterium Nebulus', 'Fumarole', etc.
    genus               TEXT            DEFAULT NULL,  -- biological genus
    species             TEXT            DEFAULT NULL,  -- biological species
    variant             TEXT            DEFAULT NULL,  -- colour/variant

    -- Location on body
    latitude            REAL            DEFAULT NULL,
    longitude           REAL            DEFAULT NULL,

    -- Value
    estimated_value     BIGINT          DEFAULT NULL,  -- credits

    -- Timestamps
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 8. RATINGS  (pre-computed scores for all visited systems)
--    Mirrors the JavaScript rateSystem() function exactly.
--    NULL score = unvisited / insufficient body data.
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

    -- Score breakdown (mirrors frontend popover data)
    score_breakdown     JSONB           DEFAULT NULL,

    -- Timestamps
    computed_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 9. SPATIAL_GRID  (500ly cube partitioning for fast neighbour queries)
--    Built by build_grid.py after import.
--    Each system gets a grid_cell_id pointing to its 500ly cube.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spatial_grid (
    cell_id             INTEGER         PRIMARY KEY,

    -- Grid coordinates (cell_x = floor(x / 500), etc.)
    cell_x              SMALLINT        NOT NULL,
    cell_y              SMALLINT        NOT NULL,
    cell_z              SMALLINT        NOT NULL,

    -- Bounding box of this cell (actual LY coords)
    min_x               REAL            NOT NULL,
    max_x               REAL            NOT NULL,
    min_y               REAL            NOT NULL,
    max_y               REAL            NOT NULL,
    min_z               REAL            NOT NULL,
    max_z               REAL            NOT NULL,

    -- Stats (for query optimisation)
    system_count        INTEGER         NOT NULL DEFAULT 0,
    visited_count       INTEGER         NOT NULL DEFAULT 0,

    UNIQUE (cell_x, cell_y, cell_z)
);

-- ---------------------------------------------------------------------------
-- 10. CLUSTER_SUMMARY  (pre-aggregated multi-economy coverage per anchor)
--     Built by build_clusters.py after ratings + spatial_grid are ready.
--     One row per visited system = "if you colonise HERE, what can you build
--     within 500ly?"
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_summary (
    system_id64         BIGINT          PRIMARY KEY REFERENCES systems(id64) ON DELETE CASCADE,

    -- How many viable (score >= 40) uncolonised systems for each economy
    -- within 500ly of this anchor
    agriculture_count   SMALLINT        NOT NULL DEFAULT 0,
    agriculture_best    SMALLINT        DEFAULT NULL,   -- highest score
    agriculture_top_id  BIGINT          DEFAULT NULL,   -- id64 of best system

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

    -- Total viable systems across all economy types within 500ly
    total_viable        SMALLINT        NOT NULL DEFAULT 0,

    -- Weighted coverage score (0-100) — how well does this bubble cover
    -- all economy types? Higher = more self-sufficient empire possible
    coverage_score      REAL            DEFAULT NULL,

    -- How many distinct economy types have at least 1 viable system
    economy_diversity   SMALLINT        NOT NULL DEFAULT 0,

    -- Radius actually searched (almost always 500, but stored for flexibility)
    search_radius       SMALLINT        NOT NULL DEFAULT 500,

    -- Dirty flag — set TRUE by EDDN ingestion, cleared by rebuild job
    dirty               BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Timestamps
    computed_at         TIMESTAMPTZ     DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 11. WATCHLIST
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
-- 12. WATCHLIST_CHANGELOG
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS watchlist_changelog (
    id                  BIGSERIAL       PRIMARY KEY,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            NOT NULL,
    change_type         TEXT            NOT NULL,   -- 'colonised','population','economy','score'
    old_value           TEXT            DEFAULT NULL,
    new_value           TEXT            DEFAULT NULL,
    detected_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 13. SYSTEM_NOTES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_notes (
    system_id64         BIGINT          PRIMARY KEY REFERENCES systems(id64) ON DELETE CASCADE,
    note                TEXT            NOT NULL DEFAULT '',
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 14. API_CACHE  (Redis handles hot cache; this is the persistent layer)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key           TEXT            PRIMARY KEY,
    response_json       JSONB           NOT NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     NOT NULL,
    hit_count           INTEGER         NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 15. EDDN_LOG  (recent raw EDDN events — rolling 7-day window)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eddn_log (
    id                  BIGSERIAL       PRIMARY KEY,
    event_type          TEXT            NOT NULL,   -- 'FSSDiscoveryScan', 'Scan', 'NavBeaconScan', etc.
    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    raw_event           JSONB           NOT NULL,
    processed           BOOLEAN         NOT NULL DEFAULT FALSE,
    received_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 16. IMPORT_META  (track import progress — resumable checkpoints)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_meta (
    id                  SERIAL          PRIMARY KEY,
    dump_file           TEXT            NOT NULL UNIQUE,  -- 'galaxy.json.gz', etc.
    status              import_status   NOT NULL DEFAULT 'pending',
    rows_processed      BIGINT          NOT NULL DEFAULT 0,
    rows_total          BIGINT          DEFAULT NULL,
    bytes_processed     BIGINT          NOT NULL DEFAULT 0,
    bytes_total         BIGINT          DEFAULT NULL,
    last_checkpoint     BIGINT          NOT NULL DEFAULT 0, -- byte offset for resume
    started_at          TIMESTAMPTZ     DEFAULT NULL,
    completed_at        TIMESTAMPTZ     DEFAULT NULL,
    error_message       TEXT            DEFAULT NULL,
    checksum            TEXT            DEFAULT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Pre-populate known dump files
INSERT INTO import_meta (dump_file) VALUES
    ('galaxy.json.gz'),
    ('bodies.json.gz'),
    ('galaxy_stations.json.gz'),
    ('galaxy_populated.json.gz'),
    ('attractions.json.gz')
ON CONFLICT (dump_file) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 17. APP_META  (key-value store for app-level settings & state)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_meta (
    key                 TEXT            PRIMARY KEY,
    value               TEXT            NOT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

INSERT INTO app_meta (key, value) VALUES
    ('schema_version',      '1.0'),
    ('import_complete',     'false'),
    ('ratings_built',       'false'),
    ('grid_built',          'false'),
    ('clusters_built',      'false'),
    ('eddn_enabled',        'false'),
    ('last_nightly_update', 'never')
ON CONFLICT (key) DO NOTHING;
