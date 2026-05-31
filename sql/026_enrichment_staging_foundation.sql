-- =============================================================================
-- Stage 17N.3 — enrichment warehouse staging foundation
-- =============================================================================
-- Additive/idempotent migration. These tables store external source evidence
-- and derived dry-run intelligence only. They do not rewrite canonical ED-Finder
-- systems, stations, bodies, station_body_links, body_scan_facts, or body_rings.
--
-- Optional trigram/name-search indexes are deliberately left for a later
-- migration so this foundation does not require pg_trgm.

CREATE TABLE IF NOT EXISTS enrichment_source_runs (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_key      TEXT            NOT NULL UNIQUE,
    source              TEXT            NOT NULL,
    adapter_name        TEXT            NOT NULL,
    adapter_version     TEXT            NOT NULL,
    source_kind         TEXT            NOT NULL DEFAULT 'offline_snapshot',
    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    run_label           TEXT            DEFAULT NULL,
    dry_run             BOOLEAN         NOT NULL DEFAULT TRUE,
    source_started_at   TIMESTAMPTZ     DEFAULT NULL,
    source_completed_at TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    metadata            JSONB           NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE enrichment_source_runs
    IS 'Immutable registry of offline enrichment source imports/dry-runs. Source evidence, not canonical truth.';

CREATE TABLE IF NOT EXISTS enrichment_source_files (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_key     TEXT            NOT NULL,
    source_path         TEXT            DEFAULT NULL,
    source_file_name    TEXT            DEFAULT NULL,
    content_type        TEXT            NOT NULL DEFAULT 'application/json',
    compression         TEXT            DEFAULT NULL,
    file_size_bytes     BIGINT          DEFAULT NULL,
    file_sha256         TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    metadata            JSONB           NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE (source_run_id, source_file_key)
);

COMMENT ON TABLE enrichment_source_files
    IS 'Source files consumed by an enrichment run, keyed by deterministic file metadata/hash.';

CREATE TABLE IF NOT EXISTS enrichment_raw_records (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    record_index        BIGINT          DEFAULT NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    validation_status   TEXT            NOT NULL DEFAULT 'accepted' CHECK (validation_status IN (
        'accepted',
        'skipped',
        'conflict',
        'invalid'
    )),
    validation_warnings JSONB           NOT NULL DEFAULT '[]'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_enrichment_raw_records_run_file_hash
    ON enrichment_raw_records (source_run_id, source_file_id, source_record_hash);

CREATE UNIQUE INDEX IF NOT EXISTS idx_enrichment_raw_records_run_file_index
    ON enrichment_raw_records (source_run_id, source_file_id, record_index)
    WHERE record_index IS NOT NULL;

COMMENT ON TABLE enrichment_raw_records
    IS 'Immutable raw source payload archive for staging and dry-run comparison.';

CREATE TABLE IF NOT EXISTS staging_edsm_stations (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    market_id           BIGINT          DEFAULT NULL,
    edsm_station_id     BIGINT          DEFAULT NULL,
    station_name        TEXT            DEFAULT NULL,
    station_type        TEXT            DEFAULT NULL,
    distance_to_arrival DOUBLE PRECISION DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    services            JSONB           NOT NULL DEFAULT '[]'::jsonb,
    economies           JSONB           NOT NULL DEFAULT '[]'::jsonb,
    controlling_faction TEXT            DEFAULT NULL,
    allegiance          TEXT            DEFAULT NULL,
    government          TEXT            DEFAULT NULL,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_edsm_stations_run_hash
    ON staging_edsm_stations (source_run_id, source_record_hash);

COMMENT ON TABLE staging_edsm_stations
    IS 'Normalised EDSM station snapshot evidence. distance_to_arrival is volatile evidence, not canonical station distance.';

CREATE TABLE IF NOT EXISTS staging_edsm_bodies (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    source_body_id      BIGINT          DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    body_type           TEXT            DEFAULT NULL,
    subtype             TEXT            DEFAULT NULL,
    distance_to_arrival DOUBLE PRECISION DEFAULT NULL,
    is_main_star        BOOLEAN         DEFAULT NULL,
    is_landable         BOOLEAN         DEFAULT NULL,
    is_terraformable    BOOLEAN         DEFAULT NULL,
    estimated_scan_value INTEGER        DEFAULT NULL,
    estimated_mapping_value INTEGER     DEFAULT NULL,
    signals             JSONB           NOT NULL DEFAULT '{}'::jsonb,
    materials           JSONB           NOT NULL DEFAULT '{}'::jsonb,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_edsm_bodies_run_hash
    ON staging_edsm_bodies (source_run_id, source_record_hash);

COMMENT ON TABLE staging_edsm_bodies
    IS 'Normalised external body evidence. Source body identifiers are not ED-Finder bodies.id unless a later planner proves that association.';

CREATE TABLE IF NOT EXISTS staging_body_rings (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    source_body_id      BIGINT          DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    ring_name           TEXT            DEFAULT NULL,
    ring_type           TEXT            DEFAULT NULL,
    ring_class          TEXT            DEFAULT NULL,
    mass_mt             DOUBLE PRECISION DEFAULT NULL,
    inner_radius        DOUBLE PRECISION DEFAULT NULL,
    outer_radius        DOUBLE PRECISION DEFAULT NULL,
    association_status  TEXT            NOT NULL DEFAULT 'source_only' CHECK (association_status IN (
        'source_only',
        'local_matched',
        'unresolved_body_identity',
        'ambiguous_body_identity',
        'belt_source_evidence',
        'conflict'
    )),

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_body_rings_run_hash
    ON staging_body_rings (source_run_id, source_record_hash);

COMMENT ON TABLE staging_body_rings
    IS 'External ring evidence staged for later read-only comparison against trusted body_rings.';

CREATE TABLE IF NOT EXISTS staging_factions (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    faction_name        TEXT            NOT NULL,
    allegiance          TEXT            DEFAULT NULL,
    government          TEXT            DEFAULT NULL,
    influence           DOUBLE PRECISION DEFAULT NULL,
    happiness           TEXT            DEFAULT NULL,
    faction_state       TEXT            DEFAULT NULL,
    is_controlling_faction BOOLEAN      DEFAULT NULL,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_factions_run_hash
    ON staging_factions (source_run_id, source_record_hash);

CREATE TABLE IF NOT EXISTS staging_system_states (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    faction_name        TEXT            DEFAULT NULL,
    state_name          TEXT            NOT NULL,
    state_kind          TEXT            DEFAULT NULL,
    state_trend         TEXT            DEFAULT NULL,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_system_states_run_hash
    ON staging_system_states (source_run_id, source_record_hash);

CREATE TABLE IF NOT EXISTS staging_station_economies (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    market_id           BIGINT          DEFAULT NULL,
    station_name        TEXT            DEFAULT NULL,
    economy_name        TEXT            NOT NULL,
    proportion          DOUBLE PRECISION DEFAULT NULL,
    primary_rank        SMALLINT        DEFAULT NULL,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_station_economies_run_hash
    ON staging_station_economies (source_run_id, source_record_hash);

CREATE TABLE IF NOT EXISTS staging_station_services (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    market_id           BIGINT          DEFAULT NULL,
    station_name        TEXT            DEFAULT NULL,
    service_name        TEXT            NOT NULL,
    service_enabled     BOOLEAN         DEFAULT TRUE,
    service_payload     JSONB           NOT NULL DEFAULT '{}'::jsonb,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_station_services_run_hash
    ON staging_station_services (source_run_id, source_record_hash);

CREATE TABLE IF NOT EXISTS staging_market_commodities (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    market_id           BIGINT          DEFAULT NULL,
    station_name        TEXT            DEFAULT NULL,
    commodity_name      TEXT            NOT NULL,
    commodity_category  TEXT            DEFAULT NULL,
    buy_price           INTEGER         DEFAULT NULL,
    sell_price          INTEGER         DEFAULT NULL,
    demand              INTEGER         DEFAULT NULL,
    supply              INTEGER         DEFAULT NULL,
    mean_price          INTEGER         DEFAULT NULL,
    prohibited          BOOLEAN         DEFAULT NULL,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_market_commodities_run_hash
    ON staging_market_commodities (source_run_id, source_record_hash);

CREATE TABLE IF NOT EXISTS staging_body_signals (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    source_body_id      BIGINT          DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    signal_type         TEXT            NOT NULL,
    signal_name         TEXT            DEFAULT NULL,
    signal_count        INTEGER         DEFAULT NULL,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_body_signals_run_hash
    ON staging_body_signals (source_run_id, source_record_hash);

CREATE TABLE IF NOT EXISTS staging_codex_entries (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    source_file_id      BIGINT          DEFAULT NULL REFERENCES enrichment_source_files(id) ON DELETE SET NULL,
    raw_record_id       BIGINT          DEFAULT NULL REFERENCES enrichment_raw_records(id) ON DELETE SET NULL,
    source_record_key   TEXT            DEFAULT NULL,
    source_record_hash  TEXT            NOT NULL,

    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    entry_id            BIGINT          DEFAULT NULL,
    entry_name          TEXT            NOT NULL,
    category            TEXT            DEFAULT NULL,
    sub_category        TEXT            DEFAULT NULL,
    region_name         TEXT            DEFAULT NULL,

    source_class        TEXT            NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    raw_payload         JSONB           NOT NULL,
    provenance          JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_codex_entries_run_hash
    ON staging_codex_entries (source_run_id, source_record_hash);

CREATE TABLE IF NOT EXISTS derived_mission_intelligence (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    report_schema_version TEXT          NOT NULL DEFAULT 'mission_intelligence_dry_run/v1',
    planner_version     TEXT            NOT NULL,
    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    market_id           BIGINT          DEFAULT NULL,
    station_name        TEXT            DEFAULT NULL,
    faction_name        TEXT            DEFAULT NULL,
    mission_kind        TEXT            DEFAULT NULL,
    score               DOUBLE PRECISION DEFAULT NULL,
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    evidence            JSONB           NOT NULL DEFAULT '{}'::jsonb,
    derived_payload     JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS derived_exploration_intelligence (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    report_schema_version TEXT          NOT NULL DEFAULT 'exploration_intelligence_dry_run/v1',
    planner_version     TEXT            NOT NULL,
    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    source_body_id      BIGINT          DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    intelligence_kind   TEXT            DEFAULT NULL,
    score               DOUBLE PRECISION DEFAULT NULL,
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    evidence            JSONB           NOT NULL DEFAULT '{}'::jsonb,
    derived_payload     JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS derived_colonisation_economy_intelligence (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    report_schema_version TEXT          NOT NULL DEFAULT 'colonisation_economy_intelligence_dry_run/v1',
    planner_version     TEXT            NOT NULL,
    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    market_id           BIGINT          DEFAULT NULL,
    station_name        TEXT            DEFAULT NULL,
    economy_name        TEXT            DEFAULT NULL,
    intelligence_kind   TEXT            DEFAULT NULL,
    score               DOUBLE PRECISION DEFAULT NULL,
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    evidence            JSONB           NOT NULL DEFAULT '{}'::jsonb,
    derived_payload     JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS derived_alert_candidates (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_id       BIGINT          NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE,
    report_schema_version TEXT          NOT NULL DEFAULT 'alert_candidate_dry_run/v1',
    planner_version     TEXT            NOT NULL,
    alert_kind          TEXT            NOT NULL,
    alert_status        TEXT            NOT NULL DEFAULT 'candidate' CHECK (alert_status IN (
        'candidate',
        'suppressed',
        'conflict',
        'expired'
    )),
    severity            TEXT            DEFAULT NULL,
    system_id64         BIGINT          DEFAULT NULL,
    system_name         TEXT            DEFAULT NULL,
    market_id           BIGINT          DEFAULT NULL,
    station_name        TEXT            DEFAULT NULL,
    faction_name        TEXT            DEFAULT NULL,
    score               DOUBLE PRECISION DEFAULT NULL,
    confidence          TEXT            NOT NULL,
    freshness_class     TEXT            DEFAULT NULL,
    source_updated_at   TIMESTAMPTZ     DEFAULT NULL,
    imported_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    evidence            JSONB           NOT NULL DEFAULT '{}'::jsonb,
    derived_payload     JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_enrichment_source_runs_source
    ON enrichment_source_runs (source, adapter_name, imported_at);

CREATE INDEX IF NOT EXISTS idx_enrichment_source_runs_class
    ON enrichment_source_runs (source_class, source_kind);

CREATE INDEX IF NOT EXISTS idx_enrichment_source_files_run
    ON enrichment_source_files (source_run_id);

CREATE INDEX IF NOT EXISTS idx_enrichment_source_files_sha
    ON enrichment_source_files (file_sha256)
    WHERE file_sha256 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_enrichment_raw_records_run
    ON enrichment_raw_records (source_run_id);

CREATE INDEX IF NOT EXISTS idx_enrichment_raw_records_source_updated
    ON enrichment_raw_records (source_updated_at)
    WHERE source_updated_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_stations_run
    ON staging_edsm_stations (source_run_id);

CREATE INDEX IF NOT EXISTS idx_staging_edsm_stations_system_id64
    ON staging_edsm_stations (system_id64)
    WHERE system_id64 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_stations_system_name
    ON staging_edsm_stations (system_name)
    WHERE system_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_stations_market_id
    ON staging_edsm_stations (market_id)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_stations_station_name
    ON staging_edsm_stations (station_name)
    WHERE station_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_stations_source_updated
    ON staging_edsm_stations (source_updated_at)
    WHERE source_updated_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_bodies_run
    ON staging_edsm_bodies (source_run_id);

CREATE INDEX IF NOT EXISTS idx_staging_edsm_bodies_system_id64
    ON staging_edsm_bodies (system_id64)
    WHERE system_id64 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_bodies_system_name
    ON staging_edsm_bodies (system_name)
    WHERE system_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_edsm_bodies_body_identity
    ON staging_edsm_bodies (system_id64, source_body_id, body_name);

CREATE INDEX IF NOT EXISTS idx_staging_edsm_bodies_source_updated
    ON staging_edsm_bodies (source_updated_at)
    WHERE source_updated_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_body_rings_run
    ON staging_body_rings (source_run_id);

CREATE INDEX IF NOT EXISTS idx_staging_body_rings_identity
    ON staging_body_rings (system_id64, source_body_id, body_name, ring_name);

CREATE INDEX IF NOT EXISTS idx_staging_body_rings_source_updated
    ON staging_body_rings (source_updated_at)
    WHERE source_updated_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_factions_system
    ON staging_factions (system_id64, faction_name);

CREATE INDEX IF NOT EXISTS idx_staging_system_states_system
    ON staging_system_states (system_id64, state_name, state_kind);

CREATE INDEX IF NOT EXISTS idx_staging_station_economies_market
    ON staging_station_economies (market_id, economy_name)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_station_services_market
    ON staging_station_services (market_id, service_name)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_market_commodities_market
    ON staging_market_commodities (market_id, commodity_name)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_staging_body_signals_body
    ON staging_body_signals (system_id64, source_body_id, body_name, signal_type);

CREATE INDEX IF NOT EXISTS idx_staging_codex_entries_system
    ON staging_codex_entries (system_id64, entry_name, category);

CREATE INDEX IF NOT EXISTS idx_derived_mission_intelligence_system
    ON derived_mission_intelligence (system_id64, mission_kind, score);

CREATE INDEX IF NOT EXISTS idx_derived_exploration_intelligence_system
    ON derived_exploration_intelligence (system_id64, intelligence_kind, score);

CREATE INDEX IF NOT EXISTS idx_derived_colonisation_economy_system
    ON derived_colonisation_economy_intelligence (system_id64, economy_name, score);

CREATE INDEX IF NOT EXISTS idx_derived_alert_candidates_kind_status
    ON derived_alert_candidates (alert_kind, alert_status, severity);

CREATE INDEX IF NOT EXISTS idx_derived_alert_candidates_system
    ON derived_alert_candidates (system_id64, alert_kind, alert_status)
    WHERE system_id64 IS NOT NULL;
