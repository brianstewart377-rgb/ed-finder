-- =============================================================================
-- Stage 17N.2d-N — provenance-backed body ring facts
-- =============================================================================
-- Additive/idempotent migration. Missing body_rings rows mean ring state is
-- unknown. Explicit no-ring evidence belongs in body_scan_facts.is_ringed =
-- FALSE from trusted full scans only.

CREATE TABLE IF NOT EXISTS body_rings (
    id                  BIGSERIAL       PRIMARY KEY,
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    body_id             BIGINT          DEFAULT NULL REFERENCES bodies(id) ON DELETE SET NULL,
    source_body_id      BIGINT          DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,

    ring_name           TEXT            DEFAULT NULL,
    ring_type           TEXT            DEFAULT NULL,
    ring_class          TEXT            DEFAULT NULL,
    mass_mt             DOUBLE PRECISION DEFAULT NULL,
    inner_radius        DOUBLE PRECISION DEFAULT NULL,
    outer_radius        DOUBLE PRECISION DEFAULT NULL,

    source              TEXT            NOT NULL,
    confidence          TEXT            NOT NULL,
    association_status  TEXT            NOT NULL DEFAULT 'local_matched'
        CHECK (association_status IN (
            'local_matched',
            'unresolved_body_identity',
            'ambiguous_body_identity',
            'belt_source_evidence',
            'conflict'
        )),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    UNIQUE (system_id64, body_id, ring_name, source)
);

ALTER TABLE body_rings
    ADD COLUMN IF NOT EXISTS association_status TEXT NOT NULL DEFAULT 'local_matched';

CREATE INDEX IF NOT EXISTS idx_body_rings_system_id64
    ON body_rings (system_id64);

CREATE INDEX IF NOT EXISTS idx_body_rings_body_id
    ON body_rings (body_id);

CREATE INDEX IF NOT EXISTS idx_body_rings_local_matched
    ON body_rings (system_id64, body_id)
    WHERE body_id IS NOT NULL AND association_status = 'local_matched';

CREATE INDEX IF NOT EXISTS idx_body_rings_source_body_id
    ON body_rings (source, system_id64, source_body_id)
    WHERE source_body_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_body_rings_body_name
    ON body_rings (system_id64, body_name)
    WHERE body_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_body_rings_type_class
    ON body_rings (ring_type, ring_class);

COMMENT ON TABLE body_rings
    IS 'Provenance-backed per-ring source facts. Missing rows mean unknown ring state, not no rings.';

COMMENT ON COLUMN body_rings.body_id
    IS 'ED-Finder local bodies.id. Source-specific body identifiers must be stored in source_body_id.';

COMMENT ON COLUMN body_rings.source_body_id
    IS 'Nullable source/journal body identifier such as EDDN Journal BodyID; not a local body foreign key.';

COMMENT ON COLUMN body_rings.source
    IS 'Source that supplied the ring row, for example spansh_dump or eddn_scan.';

COMMENT ON COLUMN body_rings.confidence
    IS 'Evidence quality label such as source_ring_payload or partial_source_ring_payload.';

COMMENT ON COLUMN body_rings.association_status
    IS 'Whether body_id is a trusted local bodies.id association. Consumers count only local_matched rows.';

ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS ring_count SMALLINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN ratings.ring_count
    IS 'Number of bodies with trusted ring rows in body_rings. Missing ring facts are unknown, not no-rings.';

ALTER TABLE body_scan_facts
    ALTER COLUMN is_ringed DROP DEFAULT;

COMMENT ON COLUMN body_scan_facts.is_ringed
    IS 'Tri-state scan-derived ring evidence: true ringed, false trusted full-scan no-rings, null unknown.';
