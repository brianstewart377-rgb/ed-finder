-- =============================================================================
-- 019: Make coordinates nullable
--
-- PROBLEM: systems.x/y/z are REAL NOT NULL DEFAULT 0. Systems imported without
-- coordinates silently get (0, 0, 0), which is indistinguishable from Sol. This
-- causes:
--   - All such systems to show "0.00 LY" from Sol in search results
--   - Autocomplete to return (0, 0, 0) as their coordinates
--   - Distance calculations to be meaningless
--
-- FIX: Allow NULL coordinates. NULL means "unknown location". Only Sol (id64
-- 10477373803) is legitimately at (0, 0, 0).
--
-- MIGRATION STEPS:
--   1. Drop NOT NULL constraint on x, y, z
--   2. Remove DEFAULT 0 (new inserts must explicitly provide coords or NULL)
--   3. Set existing (0,0,0) rows to NULL where id64 != Sol
-- =============================================================================

-- Step 1+2: Allow NULL, remove default
ALTER TABLE systems ALTER COLUMN x DROP NOT NULL;
ALTER TABLE systems ALTER COLUMN x DROP DEFAULT;
ALTER TABLE systems ALTER COLUMN y DROP NOT NULL;
ALTER TABLE systems ALTER COLUMN y DROP DEFAULT;
ALTER TABLE systems ALTER COLUMN z DROP NOT NULL;
ALTER TABLE systems ALTER COLUMN z DROP DEFAULT;

-- Step 3: Convert fake (0,0,0) to NULL (except Sol)
-- This may take a few minutes on 186M rows — run during maintenance window.
-- Only affects rows where ALL THREE coords are exactly 0.
UPDATE systems
SET x = NULL, y = NULL, z = NULL
WHERE x = 0 AND y = 0 AND z = 0
  AND id64 != 10477373803;  -- Sol is genuinely at origin
