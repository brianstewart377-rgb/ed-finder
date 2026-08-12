-- =============================================================================
-- Personal route layer
-- =============================================================================
-- Routes are private, commander-scoped planning/history records.  commander_id
-- deliberately uses the application's existing anonymous sync key; no Frontier
-- identity or shared/canonical-data write path is introduced here.

CREATE TABLE IF NOT EXISTS routes (
    route_id        UUID            PRIMARY KEY,
    name            TEXT            NOT NULL,
    source          TEXT            NOT NULL,
    waypoints       JSONB           NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    commander_id    TEXT            NOT NULL,
    type            TEXT            NOT NULL,
    external_id     TEXT            DEFAULT NULL,
    metadata        JSONB           NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT chk_routes_type
        CHECK (type IN ('personal', 'journal', 'spansh', 'expedition')),
    CONSTRAINT chk_routes_waypoints_array
        CHECK (jsonb_typeof(waypoints) = 'array'),
    CONSTRAINT chk_routes_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_routes_commander_source_external
    ON routes (commander_id, source, external_id)
    WHERE external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_routes_personal_history
    ON routes (commander_id, type)
    WHERE type = 'personal';

CREATE INDEX IF NOT EXISTS idx_routes_commander_created
    ON routes (commander_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_routes_commander_type
    ON routes (commander_id, type, updated_at DESC);

CREATE TABLE IF NOT EXISTS route_events (
    route_event_id          BIGSERIAL       PRIMARY KEY,
    route_id                UUID            NOT NULL
        REFERENCES routes(route_id) ON DELETE CASCADE,
    system_id64             BIGINT          DEFAULT NULL,
    system_name             TEXT            NOT NULL,
    x                       REAL            DEFAULT NULL,
    y                       REAL            DEFAULT NULL,
    z                       REAL            DEFAULT NULL,
    visited_at              TIMESTAMPTZ     NOT NULL,
    distance_from_planned   REAL            DEFAULT NULL,
    event_order             INTEGER         NOT NULL,
    source_event_key        TEXT            DEFAULT NULL,
    context                 JSONB           NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT chk_route_events_order CHECK (event_order >= 0),
    CONSTRAINT chk_route_events_context_object
        CHECK (jsonb_typeof(context) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_route_events_source_event
    ON route_events (route_id, source_event_key)
    WHERE source_event_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_route_events_order
    ON route_events (route_id, event_order);

CREATE INDEX IF NOT EXISTS idx_route_events_route_visited
    ON route_events (route_id, visited_at, event_order);

CREATE INDEX IF NOT EXISTS idx_route_events_system_visited
    ON route_events (system_id64, visited_at DESC)
    WHERE system_id64 IS NOT NULL;

-- NavRouteClear has no current system.  The staging model originally required
-- every allowlisted event to carry SystemAddress, so relax only that column.
ALTER TABLE journal_import_staging
    ALTER COLUMN system_id64 DROP NOT NULL;

ALTER TABLE journal_import_staging
    DROP CONSTRAINT IF EXISTS chk_journal_import_subject_type;

ALTER TABLE journal_import_staging
    ADD CONSTRAINT chk_journal_import_subject_type
        CHECK (subject_type IN ('system', 'body', 'route'));

COMMENT ON TABLE routes
    IS 'Commander-scoped planned, journal, Spansh, expedition, and personal-history routes.';

COMMENT ON TABLE route_events
    IS 'Chronological actual system visits aligned with a planned route when one exists.';
