-- =============================================================================
-- Stage 17N.2d-P follow-up — EDDN ring identity repair support
-- =============================================================================
-- body_rings.body_id is the ED-Finder local bodies.id foreign key. EDDN
-- Journal BodyID is source identity and belongs in source_body_id.

ALTER TABLE body_rings
    ADD COLUMN IF NOT EXISTS source_body_id BIGINT DEFAULT NULL;

COMMENT ON COLUMN body_rings.body_id
    IS 'ED-Finder local bodies.id. Source-specific body identifiers must be stored in source_body_id.';

COMMENT ON COLUMN body_rings.source_body_id
    IS 'Nullable source/journal body identifier such as EDDN Journal BodyID; not a local body foreign key.';

CREATE INDEX IF NOT EXISTS idx_body_rings_source_body_id
    ON body_rings (source, system_id64, source_body_id)
    WHERE source_body_id IS NOT NULL;
