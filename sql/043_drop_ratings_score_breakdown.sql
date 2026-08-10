-- 043_drop_ratings_score_breakdown.sql
--
-- Retire the dead ratings.score_breakdown column (entirely NULL since the
-- 2026-07-15 storage-recovery repack; reconstructed at read time from the
-- score_<economy> columns by apps/api/src/ratings_breakdown.py, never read
-- from the column). See docs/superpowers/plans/2026-08-10-scoring-cleanup-migration.md.
--
-- Landmines handled here:
--   * system_detail view selects r.score_breakdown directly (HARD dependency --
--     blocks the column drop). CREATE OR REPLACE VIEW cannot remove a column,
--     so drop + recreate without it. The s.* / r.* column set below reproduces
--     the live view definition (verified 2026-08-10 via pg_get_viewdef) minus
--     the single r.score_breakdown line.
--   * search_galaxy_economy() / search_economy_near() reference the column via
--     dynamic EXECUTE (soft dependency; latent-broken after the drop). Both are
--     orphaned (no caller in apps/ or scripts/) -- dropped.
--   * The identically-named system_archetype_scores.score_breakdown column is
--     ALIVE and is deliberately NOT touched.
--
-- Every statement below is a metadata operation (the column is 100% NULL), so
-- this is effectively instant and holds ACCESS EXCLUSIVE on ratings only
-- momentarily.

BEGIN;

-- 1. Recreate system_detail without score_breakdown (hard blocker).
DROP VIEW IF EXISTS system_detail;
CREATE VIEW system_detail AS
SELECT
    s.*,
    gr.name AS galaxy_region,
    r.score,
    r.score_agriculture, r.score_refinery, r.score_industrial,
    r.score_hightech, r.score_military, r.score_tourism,
    r.economy_suggestion,
    r.elw_count, r.ww_count, r.ammonia_count,
    r.gas_giant_count, r.rocky_count, r.metal_rich_count,
    r.icy_count, r.rocky_ice_count, r.hmc_count,
    r.landable_count, r.terraformable_count,
    r.bio_signal_total, r.geo_signal_total,
    r.neutron_count, r.black_hole_count, r.white_dwarf_count,
    r.slots, r.body_quality, r.compactness,
    r.signal_quality, r.orbital_safety, r.star_bonus,
    r.computed_at AS score_computed_at
FROM systems s
LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
LEFT JOIN ratings r ON r.system_id64 = s.id64;

-- 2. Drop the two orphaned functions that reference the column via dynamic SQL.
--    (Confirmed unused: verify zero calls on production first -- see runbook.)
DROP FUNCTION IF EXISTS search_galaxy_economy(TEXT, SMALLINT, INTEGER, INTEGER, SMALLINT);
DROP FUNCTION IF EXISTS search_economy_near(TEXT, REAL, REAL, REAL, REAL, SMALLINT, INTEGER, INTEGER, SMALLINT);

-- 3. Drop the dead column (targets ratings only -- NOT system_archetype_scores).
ALTER TABLE ratings DROP COLUMN IF EXISTS score_breakdown;

COMMIT;
