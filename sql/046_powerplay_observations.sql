-- =============================================================================
-- Powerplay 2.0 personal observation model
-- =============================================================================
-- Additive/idempotent and deliberately isolated from colony/canonical state.
-- The only relationship to systems is the journal's numeric address; there is
-- no foreign key and no trigger or promotion path into canonical tables.

CREATE TABLE IF NOT EXISTS powerplay_observations (
    id                      BIGSERIAL       PRIMARY KEY,
    commander_key           TEXT            NOT NULL,
    source                  TEXT            NOT NULL,
    source_version          TEXT            NOT NULL,
    source_record_hash      TEXT            NOT NULL,
    source_event            TEXT            NOT NULL,
    system_address          BIGINT          NOT NULL,
    system_name             TEXT            DEFAULT NULL,
    controlling_power       JSONB           DEFAULT NULL,
    control_state           JSONB           DEFAULT NULL,
    control_progress        JSONB           DEFAULT NULL,
    reinforcement_points    JSONB           DEFAULT NULL,
    undermining_points      JSONB           DEFAULT NULL,
    powers                  JSONB           NOT NULL DEFAULT '[]'::jsonb,
    observed_at             TIMESTAMPTZ     NOT NULL,
    cycle_start             TIMESTAMPTZ     NOT NULL,
    game_build              TEXT            DEFAULT NULL,
    source_payload          JSONB           NOT NULL,
    confidence              NUMERIC         NOT NULL,
    value_provenance        JSONB           NOT NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_powerplay_observation_confidence
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT chk_powerplay_observation_powers_array
        CHECK (jsonb_typeof(powers) = 'array'),
    CONSTRAINT chk_powerplay_observation_payload_object
        CHECK (jsonb_typeof(source_payload) = 'object'),
    CONSTRAINT chk_powerplay_observation_provenance_object
        CHECK (jsonb_typeof(value_provenance) = 'object'),
    CONSTRAINT uq_powerplay_observation_source_hash
        UNIQUE (commander_key, source, source_record_hash)
);

CREATE INDEX IF NOT EXISTS idx_powerplay_observations_commander_system_time
    ON powerplay_observations (commander_key, system_address, observed_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_powerplay_observations_commander_cycle
    ON powerplay_observations (commander_key, cycle_start DESC, observed_at DESC);

CREATE TABLE IF NOT EXISTS commander_powerplay_events (
    id                      BIGSERIAL       PRIMARY KEY,
    commander_key           TEXT            NOT NULL,
    source                  TEXT            NOT NULL,
    source_version          TEXT            NOT NULL,
    source_record_hash      TEXT            NOT NULL,
    event_type              TEXT            NOT NULL,
    observed_at             TIMESTAMPTZ     NOT NULL,
    cycle_start             TIMESTAMPTZ     NOT NULL,
    game_build              TEXT            DEFAULT NULL,
    source_payload          JSONB           NOT NULL,
    confidence              NUMERIC         NOT NULL,
    value_provenance        JSONB           NOT NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_commander_powerplay_event_confidence
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT chk_commander_powerplay_event_payload_object
        CHECK (jsonb_typeof(source_payload) = 'object'),
    CONSTRAINT chk_commander_powerplay_event_provenance_object
        CHECK (jsonb_typeof(value_provenance) = 'object'),
    CONSTRAINT uq_commander_powerplay_event_source_hash
        UNIQUE (commander_key, source, source_record_hash)
);

CREATE INDEX IF NOT EXISTS idx_commander_powerplay_events_key_time
    ON commander_powerplay_events (commander_key, observed_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS commander_powerplay_state (
    commander_key           TEXT            PRIMARY KEY,
    pledge                  JSONB           DEFAULT NULL,
    rank                    JSONB           DEFAULT NULL,
    merits                  JSONB           DEFAULT NULL,
    last_updated            TIMESTAMPTZ     NOT NULL,
    source                  TEXT            NOT NULL,
    source_version          TEXT            NOT NULL,
    confidence              NUMERIC         NOT NULL,
    value_provenance        JSONB           NOT NULL,
    rebuilt_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_commander_powerplay_state_confidence
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT chk_commander_powerplay_state_provenance_object
        CHECK (jsonb_typeof(value_provenance) = 'object')
);

CREATE TABLE IF NOT EXISTS powerplay_cycles (
    id                      BIGSERIAL       PRIMARY KEY,
    commander_key           TEXT            NOT NULL,
    week                    DATE            NOT NULL,
    cycle_start             TIMESTAMPTZ     NOT NULL,
    captured_at             TIMESTAMPTZ     NOT NULL,
    control_snapshot        JSONB           NOT NULL,
    snapshot_hash           TEXT            NOT NULL,
    source                  TEXT            NOT NULL,
    source_version          TEXT            NOT NULL,
    confidence              NUMERIC         NOT NULL,
    value_provenance        JSONB           NOT NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_powerplay_cycle_snapshot_object
        CHECK (jsonb_typeof(control_snapshot) = 'object'),
    CONSTRAINT chk_powerplay_cycle_provenance_object
        CHECK (jsonb_typeof(value_provenance) = 'object'),
    CONSTRAINT chk_powerplay_cycle_confidence
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT uq_powerplay_cycle_snapshot
        UNIQUE (commander_key, cycle_start, snapshot_hash)
);

CREATE INDEX IF NOT EXISTS idx_powerplay_cycles_commander_week
    ON powerplay_cycles (commander_key, cycle_start DESC, captured_at DESC);

COMMENT ON TABLE powerplay_observations
    IS 'Append-only, source-labelled PP2 system observations. Personal data only; never promoted into colony or canonical state.';
COMMENT ON TABLE commander_powerplay_events
    IS 'Append-only personal PP2 journal events used to rebuild commander pledge, rank, merits, and contribution history.';
COMMENT ON TABLE commander_powerplay_state
    IS 'Rebuildable current personal PP2 state, scoped by anonymous commander_key.';
COMMENT ON TABLE powerplay_cycles
    IS 'Versioned weekly snapshots rebuilt solely from personal PP2 observations; multiple hashes preserve later reconstructions.';
COMMENT ON COLUMN powerplay_observations.source_payload
    IS 'Allowlisted journal values exactly as reported. Numeric PP2 anomalies are intentionally neither clamped nor corrected.';
