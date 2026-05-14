-- Stage 6A: Observed Facts Backend Foundation
-- Extend the Stage 4D observed_facts shelf into a CRUD-ready API table.

ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS observation_id TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS fact_type TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'unverified';
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS observed_value_json JSONB;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS expected_value_json JSONB;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS build_fingerprint TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS simulation_fingerprint TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS target_archetype TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS facility_template_id TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS local_body_id TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS service_id TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS economy TEXT;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE observed_facts ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE observed_facts
   SET observation_id = COALESCE(observation_id, 'obs_legacy_' || id::text),
       source = COALESCE(source, source_type, 'manual'),
       fact_type = COALESCE(fact_type, area),
       status = COALESCE(status, 'unverified'),
       observed_value_json = COALESCE(observed_value_json, observed_value),
       facility_template_id = COALESCE(facility_template_id, facility_id),
       local_body_id = COALESCE(local_body_id, body_id),
       tags_json = COALESCE(tags_json, '[]'::jsonb),
       metadata_json = COALESCE(metadata_json, '{}'::jsonb)
 WHERE observation_id IS NULL
    OR fact_type IS NULL
    OR observed_value_json IS NULL;

ALTER TABLE observed_facts ALTER COLUMN observation_id SET NOT NULL;
ALTER TABLE observed_facts ALTER COLUMN fact_type SET NOT NULL;
ALTER TABLE observed_facts ALTER COLUMN observed_value_json SET DEFAULT 'null'::jsonb;
ALTER TABLE observed_facts ALTER COLUMN tags_json SET DEFAULT '[]'::jsonb;
ALTER TABLE observed_facts ALTER COLUMN metadata_json SET DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS idx_observed_facts_observation_id ON observed_facts(observation_id);
CREATE INDEX IF NOT EXISTS idx_observed_facts_fact_type ON observed_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_observed_facts_subject_type ON observed_facts(subject_type);
CREATE INDEX IF NOT EXISTS idx_observed_facts_status ON observed_facts(status);
CREATE INDEX IF NOT EXISTS idx_observed_facts_target_archetype ON observed_facts(target_archetype);
CREATE INDEX IF NOT EXISTS idx_observed_facts_build_fingerprint ON observed_facts(build_fingerprint);
CREATE INDEX IF NOT EXISTS idx_observed_facts_simulation_fingerprint ON observed_facts(simulation_fingerprint);
