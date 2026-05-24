-- =============================================================================
-- 020: Track rating algorithm version
--
-- Stage 17N.2c needs the UI/API to distinguish old saturated rating rows from
-- ratings rebuilt by the current scorer. Existing rows remain NULL until
-- build_ratings.py recalculates them.
-- =============================================================================

ALTER TABLE ratings
ADD COLUMN IF NOT EXISTS rating_version TEXT DEFAULT NULL;
