-- =============================================================================
-- Stage 25D A-1 - Frontier Journal import staging
-- =============================================================================
-- Additive/idempotent migration. Creates the bounded staging table used by the
-- journal import API so journal uploads can land in source_runs +
-- journal_import_staging + evidence shelf without mutating canonical tables.

CREATE TABLE IF NOT EXISTS journal_import_staging (
    id                  BIGSERIAL       PRIMARY KEY,
    source_run_key      TEXT            NOT NULL
        REFERENCES source_runs(source_run_key) ON DELETE CASCADE,
    source_file_name    TEXT            NOT NULL,
    source_record_hash  TEXT            NOT NULL UNIQUE,
    event_type          TEXT            NOT NULL,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            DEFAULT NULL,
    subject_type        TEXT            NOT NULL,
    subject_id          TEXT            DEFAULT NULL,
    observed_at         TIMESTAMPTZ     DEFAULT NULL,
    summary             TEXT            DEFAULT NULL,
    payload_json        JSONB           NOT NULL DEFAULT '{}'::jsonb,
    privacy_boundary    JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_journal_import_subject_type
        CHECK (subject_type IN ('system', 'body'))
);

CREATE INDEX IF NOT EXISTS idx_journal_import_staging_run_created
    ON journal_import_staging (source_run_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_journal_import_staging_system_observed
    ON journal_import_staging (system_id64, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_journal_import_staging_event_type
    ON journal_import_staging (event_type, observed_at DESC);

COMMENT ON TABLE journal_import_staging
    IS 'Bounded staging rows for client-parsed Frontier Journal imports. A-1 writes evidence shelf records only; canonical tables stay untouched.';

COMMENT ON COLUMN journal_import_staging.source_record_hash
    IS 'Stable dedupe key for a normalised journal observation. Global uniqueness makes whole-folder re-imports a no-op at the staging layer.';

COMMENT ON COLUMN journal_import_staging.privacy_boundary
    IS 'Client-declared privacy stripping / allowlist boundary used before the upload crossed the network.';
