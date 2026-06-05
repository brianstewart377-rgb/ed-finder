-- =============================================================================
-- Stage 19F - source_runs ledger schema
-- =============================================================================
-- Additive/idempotent migration. Creates the durable Data Warehouse Utopia
-- source-run ledger for future import provenance. This migration creates only
-- the ledger table and lookup/safety indexes.

CREATE TABLE IF NOT EXISTS source_runs (
    id                          BIGSERIAL       PRIMARY KEY,
    source_run_key              TEXT            NOT NULL UNIQUE,
    source_name                 TEXT            NOT NULL,
    source_category             TEXT            NOT NULL,
    domain                      TEXT            NOT NULL,
    import_scope                TEXT            NOT NULL,
    status                      TEXT            NOT NULL,
    source_uri                  TEXT            DEFAULT NULL,
    source_input_sha256         TEXT            DEFAULT NULL,
    source_manifest_sha256      TEXT            DEFAULT NULL,
    started_at                  TIMESTAMPTZ     NOT NULL,
    finished_at                 TIMESTAMPTZ     DEFAULT NULL,
    duration_ms                 BIGINT          DEFAULT NULL,
    git_commit_sha              TEXT            NOT NULL,
    importer_name               TEXT            NOT NULL,
    importer_version            TEXT            NOT NULL,
    trigger_context             TEXT            NOT NULL,
    artifact_path               TEXT            DEFAULT NULL,
    artifact_sha256             TEXT            DEFAULT NULL,
    artifact_integrity_sha256   TEXT            DEFAULT NULL,
    rows_read                   BIGINT          NOT NULL DEFAULT 0,
    rows_staged                 BIGINT          NOT NULL DEFAULT 0,
    rows_rejected               BIGINT          NOT NULL DEFAULT 0,
    rows_skipped                BIGINT          NOT NULL DEFAULT 0,
    error_code                  TEXT            DEFAULT NULL,
    error_summary               TEXT            DEFAULT NULL,
    safety_boundary             JSONB           NOT NULL DEFAULT '{}'::jsonb,
    metadata                    JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_source_runs_source_name
        CHECK (source_name IN (
            'edsm',
            'spansh',
            'inara',
            'daftmav',
            'mega_guide',
            'operator_artifact',
            'local_generated_artifact',
            'mission_observation',
            'frontier_journal',
            'edcd',
            'canonn',
            'ravencolonial'
        )),
    CONSTRAINT chk_source_runs_source_category
        CHECK (source_category IN (
            'source_of_truth',
            'source_of_evidence',
            'source_of_inspiration',
            'manual_operator_source',
            'derived_source'
        )),
    CONSTRAINT chk_source_runs_domain
        CHECK (domain IN (
            'systems',
            'stars',
            'bodies',
            'rings',
            'belt_clusters',
            'stations',
            'settlements',
            'station_services',
            'markets',
            'shipyard_outfitting',
            'factions_bgs',
            'economies_security',
            'construction_sites',
            'fleet_carriers_transient',
            'materials_resources',
            'facility_templates',
            'rules_reference',
            'mission_intelligence',
            'operator_artifacts'
        )),
    CONSTRAINT chk_source_runs_import_scope
        CHECK (import_scope IN (
            'raw_capture_only',
            'staging_only',
            'warehouse_fact_refresh',
            'reconciliation_candidate',
            'review_packet',
            'approval_allowlist',
            'bounded_write_reviewed',
            'canonical_apply'
        )),
    CONSTRAINT chk_source_runs_status
        CHECK (status IN (
            'planned',
            'running',
            'succeeded',
            'failed',
            'rejected',
            'superseded',
            'cancelled'
        )),
    CONSTRAINT chk_source_runs_duration_non_negative
        CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT chk_source_runs_rows_read_non_negative
        CHECK (rows_read >= 0),
    CONSTRAINT chk_source_runs_rows_staged_non_negative
        CHECK (rows_staged >= 0),
    CONSTRAINT chk_source_runs_rows_rejected_non_negative
        CHECK (rows_rejected >= 0),
    CONSTRAINT chk_source_runs_rows_skipped_non_negative
        CHECK (rows_skipped >= 0),
    CONSTRAINT chk_source_runs_finished_window
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_source_runs_source_domain_started
    ON source_runs (source_name, domain, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_runs_status_started
    ON source_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_runs_source_status
    ON source_runs (source_name, status);

CREATE INDEX IF NOT EXISTS idx_source_runs_artifact_sha256
    ON source_runs (artifact_sha256)
    WHERE artifact_sha256 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_source_runs_source_input_sha256
    ON source_runs (source_input_sha256)
    WHERE source_input_sha256 IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_runs_one_running_per_source_domain_scope
    ON source_runs (source_name, domain, import_scope)
    WHERE status = 'running';

COMMENT ON TABLE source_runs
    IS 'Durable import/source capture ledger for Data Warehouse Utopia provenance and artifacts.';

COMMENT ON COLUMN source_runs.source_run_key
    IS 'Stable external key used by artifacts, staging rows, and warehouse facts.';

COMMENT ON COLUMN source_runs.safety_boundary
    IS 'Structured safety flags and boundary confirmations for the run.';

COMMENT ON COLUMN source_runs.artifact_integrity_sha256
    IS 'Integrity hash for canonical JSON artifacts when applicable.';
