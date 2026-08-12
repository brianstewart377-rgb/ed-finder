-- =============================================================================
-- BigInt-safe, resumable Frontier journal provenance
-- =============================================================================
-- A source record is identified by its content hash within one anonymous
-- sync-key scope. Filename and byte offset remain provenance only: renaming or
-- copying a journal must not create a semantically new event.

ALTER TABLE journal_import_staging
    ADD COLUMN IF NOT EXISTS sync_key TEXT,
    ADD COLUMN IF NOT EXISTS source_offset BIGINT NOT NULL DEFAULT 0;

UPDATE journal_import_staging AS stage
   SET sync_key = COALESCE(
       runs.metadata->>'sync_key',
       runs.safety_boundary->>'sync_key',
       'legacy'
   )
  FROM source_runs AS runs
 WHERE runs.source_run_key = stage.source_run_key
   AND stage.sync_key IS NULL;

UPDATE journal_import_staging
   SET sync_key = 'legacy'
 WHERE sync_key IS NULL;

ALTER TABLE journal_import_staging
    ALTER COLUMN sync_key SET DEFAULT 'legacy',
    ALTER COLUMN sync_key SET NOT NULL,
    ALTER COLUMN system_id64 DROP NOT NULL;

ALTER TABLE journal_import_staging
    DROP CONSTRAINT IF EXISTS journal_import_staging_source_record_hash_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_import_sync_key_record_hash
    ON journal_import_staging (sync_key, source_record_hash);

CREATE INDEX IF NOT EXISTS idx_journal_import_source_position
    ON journal_import_staging (sync_key, source_file_name, source_offset);

COMMENT ON COLUMN journal_import_staging.source_offset
    IS 'UTF-8 byte offset of the source journal record; provenance only, never part of semantic identity.';

COMMENT ON COLUMN journal_import_staging.source_record_hash
    IS 'SHA-256 of source event content, independent of filename and byte offset; deduplicated within sync_key.';
