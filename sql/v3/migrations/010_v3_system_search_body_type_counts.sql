-- sql/v3/migrations/010_v3_system_search_body_type_counts.sql
-- Adds per-body-type COUNT columns to v3_derived.system_search for Finder
-- body-composition sliders. Additive only; does not touch canonical relations.
BEGIN;

ALTER TABLE v3_derived.system_search
    ADD COLUMN elw_count            integer NOT NULL DEFAULT 0 CHECK(elw_count >= 0),
    ADD COLUMN ww_count             integer NOT NULL DEFAULT 0 CHECK(ww_count >= 0),
    ADD COLUMN ammonia_count        integer NOT NULL DEFAULT 0 CHECK(ammonia_count >= 0),
    ADD COLUMN terraformable_count  integer NOT NULL DEFAULT 0 CHECK(terraformable_count >= 0),
    ADD COLUMN gas_giant_count      integer NOT NULL DEFAULT 0 CHECK(gas_giant_count >= 0),
    ADD COLUMN hmc_count            integer NOT NULL DEFAULT 0 CHECK(hmc_count >= 0),
    ADD COLUMN metal_rich_count     integer NOT NULL DEFAULT 0 CHECK(metal_rich_count >= 0),
    ADD COLUMN rocky_count          integer NOT NULL DEFAULT 0 CHECK(rocky_count >= 0),
    ADD COLUMN rocky_ice_count      integer NOT NULL DEFAULT 0 CHECK(rocky_ice_count >= 0),
    ADD COLUMN icy_count            integer NOT NULL DEFAULT 0 CHECK(icy_count >= 0),
    ADD COLUMN black_hole_count     integer NOT NULL DEFAULT 0 CHECK(black_hole_count >= 0),
    ADD COLUMN neutron_count        integer NOT NULL DEFAULT 0 CHECK(neutron_count >= 0),
    ADD COLUMN white_dwarf_count    integer NOT NULL DEFAULT 0 CHECK(white_dwarf_count >= 0),
    ADD COLUMN other_star_count     integer NOT NULL DEFAULT 0 CHECK(other_star_count >= 0),
    ADD COLUMN ring_count           integer NOT NULL DEFAULT 0 CHECK(ring_count >= 0),
    ADD COLUMN walkable_count       integer NOT NULL DEFAULT 0
        CHECK(walkable_count BETWEEN 0 AND landable_count),
    ADD COLUMN bio_signal_total     integer NOT NULL DEFAULT 0 CHECK(bio_signal_total >= 0),
    ADD COLUMN geo_signal_total     integer NOT NULL DEFAULT 0 CHECK(geo_signal_total >= 0);

-- v3_app.system_search is SELECT s.*; recreate so new columns are exposed.
CREATE OR REPLACE VIEW v3_app.system_search AS
SELECT s.* FROM v3_meta.current_derived_generation c
JOIN v3_derived.system_search s USING(derived_generation_id);

COMMIT;
