-- Supports build_clusters.py's macro-cell discovery query (Step 1), which
-- filters on ratings.score >= DEFAULT_SCORE (65). Without this index the
-- query forces a full scan of the ~189M-row ratings table. Partial index
-- keeps size proportional to qualifying rows, not table size.
--
-- CONCURRENTLY: do not wrap this file in a transaction when applying.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rat_score_viable
    ON ratings (score)
    WHERE score >= 65;
