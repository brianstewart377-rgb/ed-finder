-- Stage 4D: Observed vs Predicted Data Foundation
-- Generic observed facts table for future journal/manual/API/EDMC ingestion.

CREATE TABLE IF NOT EXISTS observed_facts (
    id BIGSERIAL PRIMARY KEY,

    system_id64 BIGINT,
    body_id TEXT,
    facility_id TEXT,

    area TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,

    observed_value JSONB NOT NULL,

    source_type TEXT NOT NULL DEFAULT 'unknown',
    source_commander TEXT,
    observed_at TIMESTAMPTZ,
    raw_event_ref TEXT,

    confidence TEXT NOT NULL DEFAULT 'observed',
    notes JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_observed_facts_system ON observed_facts(system_id64);
CREATE INDEX IF NOT EXISTS idx_observed_facts_area_subject ON observed_facts(area, subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_observed_facts_body ON observed_facts(system_id64, body_id);
CREATE INDEX IF NOT EXISTS idx_observed_facts_facility ON observed_facts(system_id64, facility_id);
