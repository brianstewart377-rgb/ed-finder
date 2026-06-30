-- ---------------------------------------------------------------------------
-- 30. R1 canonical body evidence foundation
-- ---------------------------------------------------------------------------
-- Additive R1-only schema.
-- No legacy ratings rows are changed.
-- No v4 archetype rows are changed.
--
-- Manual rollback:
--   DROP TABLE IF EXISTS r1_body_classification_trace;
--   DROP TABLE IF EXISTS r1_system_body_aggregates;
--   DROP TABLE IF EXISTS r1_aggregate_runs;

CREATE TABLE IF NOT EXISTS r1_aggregate_runs (
    run_id BIGSERIAL PRIMARY KEY,
    contract_version TEXT NOT NULL,
    source_snapshot_identifier TEXT NOT NULL,
    scorer_revision TEXT DEFAULT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scope TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned', 'dry_run', 'completed', 'partial', 'failed')),
    source_row_count BIGINT NOT NULL DEFAULT 0,
    source_data_sha256 TEXT DEFAULT NULL,
    notes TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_r1_aggregate_runs_generated_at
    ON r1_aggregate_runs (generated_at DESC);

CREATE TABLE IF NOT EXISTS r1_system_body_aggregates (
    run_id BIGINT NOT NULL REFERENCES r1_aggregate_runs(run_id) ON DELETE CASCADE,
    system_id64 BIGINT NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    total_body_rows_seen INTEGER NOT NULL DEFAULT 0,
    total_body_rows_classified INTEGER NOT NULL DEFAULT 0,
    unknown_body_count INTEGER NOT NULL DEFAULT 0,
    true_earth_like_world_count INTEGER NOT NULL DEFAULT 0,
    true_water_world_count INTEGER NOT NULL DEFAULT 0,
    true_ammonia_world_count INTEGER NOT NULL DEFAULT 0,
    gas_giant_ammonia_life_count INTEGER NOT NULL DEFAULT 0,
    gas_giant_water_life_count INTEGER NOT NULL DEFAULT 0,
    black_hole_count INTEGER NOT NULL DEFAULT 0,
    neutron_star_count INTEGER NOT NULL DEFAULT 0,
    white_dwarf_count INTEGER NOT NULL DEFAULT 0,
    gas_giant_count INTEGER NOT NULL DEFAULT 0,
    rocky_count INTEGER NOT NULL DEFAULT 0,
    rocky_ice_count INTEGER NOT NULL DEFAULT 0,
    icy_count INTEGER NOT NULL DEFAULT 0,
    high_metal_content_count INTEGER NOT NULL DEFAULT 0,
    metal_rich_count INTEGER NOT NULL DEFAULT 0,
    landable_count INTEGER NOT NULL DEFAULT 0,
    terraformable_count INTEGER NOT NULL DEFAULT 0,
    ringed_body_count INTEGER NOT NULL DEFAULT 0,
    biological_signal_body_count INTEGER NOT NULL DEFAULT 0,
    geological_signal_body_count INTEGER NOT NULL DEFAULT 0,
    biological_signal_total INTEGER NOT NULL DEFAULT 0,
    geological_signal_total INTEGER NOT NULL DEFAULT 0,
    body_data_completeness_state TEXT NOT NULL DEFAULT 'unknown'
        CHECK (body_data_completeness_state IN ('complete', 'partial', 'unknown')),
    min_distance_from_arrival_star_ls REAL DEFAULT NULL,
    max_distance_from_arrival_star_ls REAL DEFAULT NULL,
    distance_known_body_count INTEGER NOT NULL DEFAULT 0,
    distance_unknown_body_count INTEGER NOT NULL DEFAULT 0,
    identity_fields_complete BOOLEAN NOT NULL DEFAULT FALSE,
    distance_fields_complete BOOLEAN NOT NULL DEFAULT FALSE,
    ring_fields_complete BOOLEAN NOT NULL DEFAULT FALSE,
    signal_fields_complete BOOLEAN NOT NULL DEFAULT FALSE,
    atmosphere_fields_complete BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, system_id64)
);

CREATE TABLE IF NOT EXISTS r1_body_classification_trace (
    run_id BIGINT NOT NULL,
    system_id64 BIGINT NOT NULL,
    body_id BIGINT NOT NULL REFERENCES bodies(id) ON DELETE CASCADE,
    body_name TEXT NOT NULL,
    canonical_facts JSONB NOT NULL DEFAULT '{}'::jsonb,
    true_earth_like_world BOOLEAN DEFAULT NULL,
    true_water_world BOOLEAN DEFAULT NULL,
    true_ammonia_world BOOLEAN DEFAULT NULL,
    gas_giant_ammonia_life BOOLEAN DEFAULT NULL,
    gas_giant_water_life BOOLEAN DEFAULT NULL,
    black_hole BOOLEAN DEFAULT NULL,
    neutron_star BOOLEAN DEFAULT NULL,
    white_dwarf BOOLEAN DEFAULT NULL,
    gas_giant BOOLEAN DEFAULT NULL,
    rocky BOOLEAN DEFAULT NULL,
    rocky_ice BOOLEAN DEFAULT NULL,
    icy BOOLEAN DEFAULT NULL,
    high_metal_content BOOLEAN DEFAULT NULL,
    metal_rich BOOLEAN DEFAULT NULL,
    landable BOOLEAN DEFAULT NULL,
    terraformable BOOLEAN DEFAULT NULL,
    rings BOOLEAN DEFAULT NULL,
    biological_signals BOOLEAN DEFAULT NULL,
    geological_signals BOOLEAN DEFAULT NULL,
    distance_from_arrival_star_ls REAL DEFAULT NULL,
    distance_source_status TEXT NOT NULL DEFAULT 'unknown',
    ring_source_status TEXT NOT NULL DEFAULT 'unknown',
    raw_subtype TEXT DEFAULT NULL,
    normalised_subtype TEXT DEFAULT NULL,
    raw_is_earth_like BOOLEAN DEFAULT NULL,
    raw_is_water_world BOOLEAN DEFAULT NULL,
    raw_is_ammonia_world BOOLEAN DEFAULT NULL,
    raw_is_landable BOOLEAN DEFAULT NULL,
    raw_is_terraformable BOOLEAN DEFAULT NULL,
    raw_terraforming_state TEXT DEFAULT NULL,
    raw_bio_signal_count INTEGER DEFAULT NULL,
    raw_geo_signal_count INTEGER DEFAULT NULL,
    raw_atmosphere_type TEXT DEFAULT NULL,
    raw_atmosphere_composition JSONB DEFAULT NULL,
    applied_rule_ids TEXT[] NOT NULL DEFAULT '{}',
    unknown_flags TEXT[] NOT NULL DEFAULT '{}',
    ambiguous_flags TEXT[] NOT NULL DEFAULT '{}',
    completeness_state TEXT NOT NULL DEFAULT 'unknown'
        CHECK (completeness_state IN ('complete', 'partial', 'unknown')),
    raw_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, system_id64, body_id),
    FOREIGN KEY (run_id, system_id64)
        REFERENCES r1_system_body_aggregates(run_id, system_id64)
        ON DELETE CASCADE
);
