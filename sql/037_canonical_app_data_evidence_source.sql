-- =============================================================================
-- Stage 26B - canonical app data evidence source
-- =============================================================================
-- Allow lifecycle-managed evidence records and source-run ledger entries to
-- identify canonical app-data promotions explicitly instead of overloading a
-- manual/operator source label.

ALTER TABLE source_runs
    DROP CONSTRAINT IF EXISTS chk_source_runs_source_name;

ALTER TABLE source_runs
    ADD CONSTRAINT chk_source_runs_source_name
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
        'planner_reference_archive',
        'canonical_app_data'
    ));

ALTER TABLE evidence_records
    DROP CONSTRAINT IF EXISTS chk_evidence_records_source_name;

ALTER TABLE evidence_records
    ADD CONSTRAINT chk_evidence_records_source_name
    CHECK (source_name IN (
        'spansh',
        'eddn',
        'edsm',
        'inara',
        'daftmav',
        'mega_guide',
        'operator_artifact',
        'local_generated_artifact',
        'mission_observation',
        'frontier_journal',
        'edcd',
        'canonn',
        'planner_reference_archive',
        'manual_operator_source',
        'canonical_app_data'
    ));
