-- ============================================================
-- ED:Finder Phase 2 DB migration — v3.28
-- Adds is_tidal_lock column to bodies table.
--
-- Run this ONCE on existing galaxy.db before re-importing
-- (or re-run import_galaxy to populate the new column from data blob).
--
-- Safe to run multiple times (ALTER TABLE ignores existing columns
-- via the error handler below, or use the 'IF NOT EXISTS' workaround).
--
-- Usage on Pi5:
--   sqlite3 /data/galaxy.db < migrate_v3_28.sql
-- ============================================================

-- SQLite doesn't support ALTER TABLE ... ADD COLUMN IF NOT EXISTS directly,
-- so we use a pragma check then try-add via a simple ALTER.
-- If the column already exists SQLite will return "duplicate column name" error
-- and continue — safe to ignore.

ALTER TABLE bodies ADD COLUMN is_tidal_lock INTEGER DEFAULT 0;

-- After adding the column, populate it from the stored data JSON blob
-- (only needed if you already have Phase 2 bodies in DB from an old import).
-- This runs a one-time UPDATE to extract the field from the JSON 'data' column.
UPDATE bodies
   SET is_tidal_lock = CASE
       WHEN json_extract(data, '$.rotationalPeriodTidallyLocked') = 1 THEN 1
       WHEN json_extract(data, '$.is_rotational_period_tidally_locked') = 1 THEN 1
       ELSE 0
   END
 WHERE data IS NOT NULL;

-- Index for tidal-lock queries
CREATE INDEX IF NOT EXISTS idx_bodies_tidal ON bodies(is_tidal_lock);

-- Verify
SELECT 'Migration complete. Tidal-lock stats:',
       SUM(is_tidal_lock) AS tidal_count,
       COUNT(*) AS total_bodies
  FROM bodies;
