-- Stage 6A: Observed Facts Backend Foundation
-- ---------------------------------------------------------------------
-- This migration extends the Stage 4D observed_facts shelf
-- (sql/017_observed_facts.sql) into a CRUD-ready API table for the
-- Stage 6A passive evidence-shelf API. It is **strictly additive**:
--
--   * No existing rows are dropped or rewritten with non-deterministic
--     values; the UPDATE block only fills NULL columns with
--     deterministic legacy-derived values.
--   * New columns are added with safe defaults so older Stage 4D writers
--     can keep working until they are migrated.
--   * subject_id is relaxed from NOT NULL (Stage 4D) to nullable
--     (Stage 6A) so system/build-level notes that have no specific
--     subject can be recorded.
--
-- Legacy / new column compatibility mapping (kept populated by the
-- Stage 6A store on every write so Stage 4D comparison/trace code can
-- continue reading observed_facts until a later normalisation
-- migration drops the legacy columns):
--
--     legacy column          new Stage 6A column
--     -------------          --------------------
--     area                =  fact_type
--     source_type         =  source
--     observed_value      =  observed_value_json
--     facility_id         =  facility_template_id
--     body_id             =  local_body_id
--
-- This migration depends on sql/017_observed_facts.sql having created
-- the base observed_facts table. Fresh environments must apply 017
-- before 018; we deliberately do NOT add a CREATE TABLE IF NOT EXISTS
-- fallback here because doing so would silently mask a missing prior
-- migration and could produce a different default column set.

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

-- Backfill existing Stage 4D rows into the new Stage 6A columns using the
-- legacy compatibility mapping documented above. Each COALESCE preserves
-- any value already present so re-running this migration is idempotent.
-- The observation_id backfill uses the row's BIGSERIAL id, which is
-- stable and deterministic.
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

-- Stage 6A allows subject_id to be NULL for system/build-level notes
-- (e.g. a free-form NOTE about a system that does not target a specific
-- service/economy/facility). Stage 4D had this column NOT NULL because
-- legacy comparison fact_types always carried a subject identifier.
ALTER TABLE observed_facts ALTER COLUMN subject_id DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_observed_facts_observation_id ON observed_facts(observation_id);
CREATE INDEX IF NOT EXISTS idx_observed_facts_fact_type ON observed_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_observed_facts_subject_type ON observed_facts(subject_type);
CREATE INDEX IF NOT EXISTS idx_observed_facts_status ON observed_facts(status);
CREATE INDEX IF NOT EXISTS idx_observed_facts_target_archetype ON observed_facts(target_archetype);
CREATE INDEX IF NOT EXISTS idx_observed_facts_build_fingerprint ON observed_facts(build_fingerprint);
CREATE INDEX IF NOT EXISTS idx_observed_facts_simulation_fingerprint ON observed_facts(simulation_fingerprint);
