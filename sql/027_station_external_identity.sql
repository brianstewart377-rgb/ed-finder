-- =============================================================================
-- Stage 18J-P5 - external station identity migration draft
-- =============================================================================
-- Additive/idempotent migration. This table stores provenance-backed external
-- station identity evidence for canonical stations. It does not modify canonical
-- station rows, backfill evidence, approve station-type writes, or create an
-- apply path.

CREATE TABLE IF NOT EXISTS station_external_identity (
    id                          BIGSERIAL       PRIMARY KEY,
    canonical_station_id        BIGINT          NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    system_id64                 BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    station_name                TEXT            NOT NULL,
    source                      TEXT            NOT NULL,
    market_id                   BIGINT          DEFAULT NULL,
    edsm_station_id             BIGINT          DEFAULT NULL,
    source_run_key              TEXT            NOT NULL,
    source_file_key             TEXT            NOT NULL,
    source_record_hash          TEXT            NOT NULL,
    source_updated_at           TIMESTAMPTZ     DEFAULT NULL,
    evidence_first_seen_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    evidence_last_seen_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    confidence                  TEXT            NOT NULL,
    freshness_class             TEXT            NOT NULL,
    identity_status             TEXT            NOT NULL DEFAULT 'proposed',
    conflict_reason             TEXT            DEFAULT NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_station_external_identity_external_id
        CHECK (market_id IS NOT NULL OR edsm_station_id IS NOT NULL),
    CONSTRAINT chk_station_external_identity_status
        CHECK (identity_status IN (
            'proposed',
            'confirmed',
            'conflicting',
            'rejected',
            'superseded'
        )),
    CONSTRAINT chk_station_external_identity_confidence
        CHECK (confidence IN (
            'exact_station_identity',
            'source_station_snapshot',
            'high',
            'medium',
            'low',
            'unresolved'
        )),
    CONSTRAINT chk_station_external_identity_freshness
        CHECK (freshness_class IN (
            'source_updated_at',
            'file_snapshot',
            'current',
            'recent',
            'stale',
            'undated',
            'unknown'
        )),
    CONSTRAINT chk_station_external_identity_conflict_reason
        CHECK (identity_status <> 'conflicting' OR conflict_reason IS NOT NULL),
    CONSTRAINT chk_station_external_identity_seen_window
        CHECK (evidence_last_seen_at >= evidence_first_seen_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_station_external_identity_confirmed_source_market
    ON station_external_identity (source, market_id)
    WHERE market_id IS NOT NULL AND identity_status = 'confirmed';

CREATE UNIQUE INDEX IF NOT EXISTS idx_station_external_identity_confirmed_source_edsm
    ON station_external_identity (source, edsm_station_id)
    WHERE edsm_station_id IS NOT NULL AND identity_status = 'confirmed';

CREATE UNIQUE INDEX IF NOT EXISTS idx_station_external_identity_confirmed_station_source_market
    ON station_external_identity (canonical_station_id, source, market_id)
    WHERE market_id IS NOT NULL AND identity_status = 'confirmed';

CREATE UNIQUE INDEX IF NOT EXISTS idx_station_external_identity_confirmed_station_source_edsm
    ON station_external_identity (canonical_station_id, source, edsm_station_id)
    WHERE edsm_station_id IS NOT NULL AND identity_status = 'confirmed';

CREATE INDEX IF NOT EXISTS idx_station_external_identity_station
    ON station_external_identity (canonical_station_id);

CREATE INDEX IF NOT EXISTS idx_station_external_identity_system
    ON station_external_identity (system_id64);

CREATE INDEX IF NOT EXISTS idx_station_external_identity_market_id
    ON station_external_identity (market_id)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_station_external_identity_edsm_station_id
    ON station_external_identity (edsm_station_id)
    WHERE edsm_station_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_station_external_identity_source_run_file
    ON station_external_identity (source_run_key, source_file_key);

CREATE INDEX IF NOT EXISTS idx_station_external_identity_status
    ON station_external_identity (identity_status);

COMMENT ON TABLE station_external_identity
    IS 'Provenance-backed external station identity evidence. Only confirmed rows may later be used by read-only reconciliation as canonical external identity proof.';

COMMENT ON COLUMN station_external_identity.canonical_station_id
    IS 'ED-Finder canonical stations.id update target; not an external market identifier.';

COMMENT ON COLUMN station_external_identity.market_id
    IS 'Nullable external market identifier observed from source evidence.';

COMMENT ON COLUMN station_external_identity.edsm_station_id
    IS 'Nullable external EDSM station identifier observed from source evidence.';

COMMENT ON COLUMN station_external_identity.source_run_key
    IS 'Warehouse source run key that produced this identity evidence.';

COMMENT ON COLUMN station_external_identity.source_file_key
    IS 'Warehouse source file key that produced this identity evidence.';

COMMENT ON COLUMN station_external_identity.source_record_hash
    IS 'Deterministic hash of the source station record backing this identity evidence.';

COMMENT ON COLUMN station_external_identity.identity_status
    IS 'Identity review status. Only confirmed rows can serve as canonical external identity proof.';

COMMENT ON COLUMN station_external_identity.conflict_reason
    IS 'Required explanation for conflicting rows; conflicting evidence is visible but blocked from proof use.';
