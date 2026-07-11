-- =============================================================================
-- Stage 26b - Evidence record lifecycle hardening
-- =============================================================================
-- Makes lifecycle states structural:
--   * adds quarantined as a first-class record_status
--   * enforces one active record per evidence subject/fact-kind
--   * adds lifecycle-oriented indexes for freshness sweeps and lookups

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_evidence_records_record_status'
          AND conrelid = 'evidence_records'::regclass
    ) THEN
        ALTER TABLE evidence_records
            DROP CONSTRAINT chk_evidence_records_record_status;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_evidence_records_record_status'
          AND conrelid = 'evidence_records'::regclass
    ) THEN
        ALTER TABLE evidence_records
            ADD CONSTRAINT chk_evidence_records_record_status
            CHECK (record_status IN ('active', 'superseded', 'rejected', 'archived', 'quarantined'));
    END IF;
END $$;

WITH ranked_active AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY system_id64, subject_type, COALESCE(subject_id, ''), evidence_type
               ORDER BY COALESCE(observed_at, collected_at, created_at) DESC, id DESC
           ) AS active_rank
    FROM evidence_records
    WHERE record_status = 'active'
),
superseded_duplicates AS (
    UPDATE evidence_records er
       SET record_status = 'superseded',
           freshness_status = 'superseded',
           updated_at = now(),
           metadata_json = COALESCE(er.metadata_json, '{}'::jsonb) || jsonb_build_object(
               'superseded_by_migration',
               '036_evidence_record_lifecycle',
               'superseded_at',
               to_jsonb(now())
           )
      FROM ranked_active ranked
     WHERE er.id = ranked.id
       AND ranked.active_rank > 1
    RETURNING er.id
)
SELECT COUNT(*) FROM superseded_duplicates;

CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_records_active_subject_fact
    ON evidence_records (system_id64, subject_type, COALESCE(subject_id, ''), evidence_type)
    WHERE record_status = 'active';

CREATE INDEX IF NOT EXISTS idx_evidence_records_lifecycle_freshness
    ON evidence_records (
        record_status,
        freshness_status,
        COALESCE(observed_at, collected_at, created_at) DESC
    );
