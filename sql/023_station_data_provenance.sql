-- Stage 17N.2d-L: station metadata provenance.
--
-- Existing station distance/body/type values are legacy local evidence. This
-- migration is additive and deliberately does not mark existing rows trusted.

ALTER TABLE stations
    ADD COLUMN IF NOT EXISTS distance_source TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS distance_confidence TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS distance_updated_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS station_type_source TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS station_type_confidence TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS station_type_updated_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS body_name_source TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS body_name_confidence TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS body_name_updated_at TIMESTAMPTZ DEFAULT NULL;

DO $$
BEGIN
    IF to_regclass('public.station_body_links') IS NOT NULL THEN
        ALTER TABLE station_body_links
            DROP CONSTRAINT IF EXISTS station_body_links_source_check;

        ALTER TABLE station_body_links
            ADD CONSTRAINT station_body_links_source_check
            CHECK (association_source IN (
                'import',
                'eddn',
                'manual',
                'resolver_body_id',
                'resolver_body_name',
                'resolver_distance',
                'edsm_body_name',
                'edsm_distance',
                'unknown'
            ));
    END IF;
END $$;
