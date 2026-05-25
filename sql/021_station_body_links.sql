-- Stage 17N.2d-H: normalized station/body occupied-slot association.
--
-- This table is deliberately separate from stations. A station can exist even
-- when ED-Finder cannot prove which body/lane it belongs to. Unknown values
-- must stay nullable/explicit instead of being forced into fake occupancy.

CREATE TABLE IF NOT EXISTS station_body_links (
    station_id              BIGINT      PRIMARY KEY REFERENCES stations(id) ON DELETE CASCADE,
    market_id               BIGINT      DEFAULT NULL,
    system_id64             BIGINT      NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    body_id                 BIGINT      DEFAULT NULL REFERENCES bodies(id) ON DELETE SET NULL,
    body_name               TEXT        DEFAULT NULL,
    lane                    TEXT        NOT NULL DEFAULT 'unknown',
    association_status      TEXT        NOT NULL DEFAULT 'unresolved',
    association_confidence  TEXT        NOT NULL DEFAULT 'unresolved',
    association_source      TEXT        NOT NULL DEFAULT 'unknown',
    resolver_notes          TEXT        DEFAULT NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT station_body_links_lane_check
        CHECK (lane IN ('orbital', 'surface', 'unknown')),
    CONSTRAINT station_body_links_status_check
        CHECK (association_status IN ('confirmed', 'inferred', 'unresolved')),
    CONSTRAINT station_body_links_confidence_check
        CHECK (association_confidence IN ('exact', 'strong_inference', 'weak_inference', 'unresolved')),
    CONSTRAINT station_body_links_source_check
        CHECK (association_source IN (
            'import',
            'eddn',
            'manual',
            'resolver_body_id',
            'resolver_body_name',
            'resolver_distance',
            'unknown'
        ))
);

CREATE INDEX IF NOT EXISTS idx_station_body_links_system_status
    ON station_body_links(system_id64, association_status);

CREATE INDEX IF NOT EXISTS idx_station_body_links_body_lane
    ON station_body_links(system_id64, body_id, lane)
    WHERE body_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_station_body_links_unresolved_type
    ON station_body_links(system_id64, lane, association_confidence);
