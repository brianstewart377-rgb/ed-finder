-- =============================================================================
-- Personal exploration layer - staging table
-- =============================================================================
-- Additive/idempotent migration. Creates the table backing personal exploration
-- data (systems visited, bodies scanned/mapped, discoveries, exobiology, Codex
-- entries), scoped by the existing anonymous sync_key mechanism. This table is
-- never merged into body_scan_facts, body_rings, or any other canonical table -
-- see docs/superpowers/specs/2026-08-08-map-exploration-layer-design.md.

CREATE TABLE IF NOT EXISTS exploration_facts (
    id                  BIGSERIAL       PRIMARY KEY,
    sync_key            TEXT            NOT NULL,
    source              TEXT            NOT NULL DEFAULT 'journal',
    source_record_hash  TEXT            NOT NULL UNIQUE,
    event_type          TEXT            NOT NULL,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            DEFAULT NULL,
    body_id             INTEGER         DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    observed_at         TIMESTAMPTZ     NOT NULL,
    payload_json        JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_exploration_facts_source
        CHECK (source IN ('journal', 'edsm'))
);

CREATE INDEX IF NOT EXISTS idx_exploration_facts_sync_key_observed
    ON exploration_facts (sync_key, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_exploration_facts_sync_key_event_type
    ON exploration_facts (sync_key, event_type);

COMMENT ON TABLE exploration_facts
    IS 'Personal exploration data (visits, scans, mapping, discoveries, exobiology, Codex), scoped by sync_key. Never promoted to canonical/shared tables.';

COMMENT ON COLUMN exploration_facts.source_record_hash
    IS 'Stable client-computed dedupe key for one observation. Re-importing the same journal/EDSM data is a no-op at this layer.';

COMMENT ON COLUMN exploration_facts.source
    IS 'journal = parsed from the player''s own Elite Dangerous journal files. edsm = backfilled from the player''s own EDSM flight log via their personal API key.';
