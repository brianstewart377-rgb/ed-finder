-- ───────────────────────────────────────────────────────────────────────
-- 008_body_filter_aggregates.sql
-- ───────────────────────────────────────────────────────────────────────
-- Adds three precomputed body-count columns to the `ratings` table so
-- the v2 search form can offer "rings", "walkable", and "other star"
-- range sliders without expensive per-row joins on `bodies` at query
-- time.
--
-- Backfill is done HERE in pure SQL rather than via build_ratings.py
-- — keeps the rating math untouched (zero risk of regression) and runs
-- in a single statement against PG instead of millions of Python loops.
--
-- Caveat: the rings detection is a substring heuristic on bodies.subtype
-- ('ring' in lowercased subtype). The Spansh import currently does not
-- persist a structured rings field on bodies, so this is the best signal
-- we have. To get accurate ring data later, add `bodies.has_rings BOOLEAN`
-- + parse from the Spansh dump's `rings` array — see backlog.
--
-- ON-GOING REFRESH:
--   These 3 columns are static after import — they don't auto-refresh as
--   build_ratings.py touches a system. Re-run the backfill block at the
--   bottom of this file periodically (or after a fresh galaxy import).
-- ───────────────────────────────────────────────────────────────────────

ALTER TABLE ratings
  ADD COLUMN IF NOT EXISTS ring_count        SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS walkable_count    SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS other_star_count  SMALLINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN ratings.ring_count
  IS 'Number of bodies with rings (heuristic: subtype ILIKE %ring%). Backfilled by sql/008.';
COMMENT ON COLUMN ratings.walkable_count
  IS 'Landable bodies with no atmosphere (Odyssey on-foot). Backfilled by sql/008.';
COMMENT ON COLUMN ratings.other_star_count
  IS 'Stars NOT counted in neutron/black_hole/white_dwarf columns '
     '(main sequence, giants, brown dwarfs, etc.). Backfilled by sql/008.';

-- Optional: index the new columns if they get filtered heavily. Skip for
-- now; ratings is a smallish table and the existing covering index on
-- (system_id64, score) is more important.

-- ── Backfill aggregates from the bodies table ──────────────────────────
-- This is the slow part — full table scan on `bodies` (~1B rows on the
-- production galaxy). Expect 30–90 minutes depending on disk + cache.
-- Watch progress with:
--   SELECT count(*) FROM ratings WHERE ring_count > 0 OR walkable_count > 0;
--
-- Wrapped in a transaction so a partial run can be rolled back safely.
BEGIN;

WITH agg AS (
    SELECT b.system_id64,
           COUNT(*) FILTER (WHERE LOWER(b.subtype) LIKE '%ring%')      ::SMALLINT AS ring_count,
           COUNT(*) FILTER (WHERE b.is_landable = TRUE
                              AND (b.atmosphere_type IS NULL
                                   OR b.atmosphere_type = ''
                                   OR b.atmosphere_type ILIKE 'no atmosphere%'))
                                                                       ::SMALLINT AS walkable_count,
           COUNT(*) FILTER (WHERE b.body_type = 'Star'
                              AND LOWER(COALESCE(b.subtype, '')) NOT LIKE '%neutron%'
                              AND LOWER(COALESCE(b.subtype, '')) NOT LIKE '%black hole%'
                              AND LOWER(COALESCE(b.subtype, '')) NOT LIKE '%white dwarf%')
                                                                       ::SMALLINT AS other_star_count
    FROM   bodies b
    GROUP  BY b.system_id64
)
UPDATE ratings r
SET    ring_count       = LEAST(agg.ring_count,       32767),
       walkable_count   = LEAST(agg.walkable_count,   32767),
       other_star_count = LEAST(agg.other_star_count, 32767)
FROM   agg
WHERE  r.system_id64 = agg.system_id64;

COMMIT;

-- ── Verification ──────────────────────────────────────────────────────
-- Run after the backfill completes to spot-check:
--
--   SELECT
--     count(*)                        AS rated,
--     count(*) FILTER (WHERE ring_count       > 0) AS w_rings,
--     count(*) FILTER (WHERE walkable_count   > 0) AS w_walkable,
--     count(*) FILTER (WHERE other_star_count > 0) AS w_otherstar,
--     max(ring_count)                 AS max_rings,
--     max(walkable_count)             AS max_walkable,
--     max(other_star_count)           AS max_otherstar
--   FROM ratings;
