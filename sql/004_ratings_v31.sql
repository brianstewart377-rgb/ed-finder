-- ============================================================================
-- ED Finder — Ratings v3.1 schema migration
-- ============================================================================
-- Adds five new columns to the `ratings` table to support the v3.1 scoring
-- engine (see backend/build_ratings.py rate_system() docstring):
--
--   score_extraction        smallint   — explicit Extraction-economy score
--                                         (v3.0 stored it only inside
--                                         score_breakdown JSONB; exposing it
--                                         as a column lets the rerank
--                                         endpoint weight it efficiently).
--
--   terraforming_potential  smallint   — 0-100 quality-weighted terraforming
--                                         score (distinct from raw count).
--
--   body_diversity          smallint   — 0-30 Shannon-diversity bonus.
--
--   confidence              real       — 0.70-1.00 data-freshness factor,
--                                         derived from systems.updated_at.
--
--   rationale               text       — one-line natural-language explainer
--                                         for surfacing in the UI popover.
--
-- Safe to run multiple times (all ADDs are IF NOT EXISTS).  Does not touch
-- existing rows; a `build_ratings.py --rebuild` run is required to populate
-- the new columns — until then NULLs are returned and the rerank endpoint
-- falls back to the stored dimensional scores.
-- ============================================================================

ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS score_extraction       smallint,
    ADD COLUMN IF NOT EXISTS terraforming_potential  smallint,
    ADD COLUMN IF NOT EXISTS body_diversity          smallint,
    ADD COLUMN IF NOT EXISTS confidence              real,
    ADD COLUMN IF NOT EXISTS rationale               text;

-- Range checks (runtime clamps in Python already enforce these, but the DB
-- constraints make any future manual UPDATE safe too).
ALTER TABLE ratings
    DROP CONSTRAINT IF EXISTS ratings_score_extraction_range,
    DROP CONSTRAINT IF EXISTS ratings_terraforming_potential_range,
    DROP CONSTRAINT IF EXISTS ratings_body_diversity_range,
    DROP CONSTRAINT IF EXISTS ratings_confidence_range;

ALTER TABLE ratings
    ADD CONSTRAINT ratings_score_extraction_range
        CHECK (score_extraction       IS NULL OR score_extraction       BETWEEN 0 AND 100),
    ADD CONSTRAINT ratings_terraforming_potential_range
        CHECK (terraforming_potential IS NULL OR terraforming_potential BETWEEN 0 AND 100),
    ADD CONSTRAINT ratings_body_diversity_range
        CHECK (body_diversity         IS NULL OR body_diversity         BETWEEN 0 AND 30),
    ADD CONSTRAINT ratings_confidence_range
        CHECK (confidence             IS NULL OR confidence             BETWEEN 0.0 AND 1.0);

-- Partial index: accelerates the "recently updated / high confidence" sort
-- used by the shipping/fresh filters on the search endpoint.
CREATE INDEX IF NOT EXISTS idx_ratings_confidence_high
    ON ratings (confidence DESC NULLS LAST, score DESC)
    WHERE confidence IS NOT NULL AND confidence >= 0.85;

COMMENT ON COLUMN ratings.score_extraction       IS 'Explicit Extraction economy score 0-100 (v3.1).';
COMMENT ON COLUMN ratings.terraforming_potential IS 'Quality-weighted terraforming score 0-100 (v3.1).';
COMMENT ON COLUMN ratings.body_diversity         IS 'Shannon-diversity bonus 0-30 (v3.1).';
COMMENT ON COLUMN ratings.confidence             IS 'Data freshness factor 0.70-1.00 (v3.1).';
COMMENT ON COLUMN ratings.rationale              IS 'One-line natural-language explainer (v3.1).';
