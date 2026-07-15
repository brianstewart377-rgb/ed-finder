-- Widen count and total columns from smallint to integer.
-- The _best columns also widened for consistency (scores are small
-- today, but the type should not be the constraint).
-- economy_diversity (0-6) and search_radius (always 500) stay smallint.
-- ALTER TYPE on a 142K-row table is fast; no CONCURRENTLY needed.

-- top_clusters view depends on these columns; drop and recreate.
DROP VIEW IF EXISTS top_clusters;

ALTER TABLE cluster_summary
    ALTER COLUMN agriculture_count TYPE integer,
    ALTER COLUMN agriculture_best  TYPE integer,
    ALTER COLUMN refinery_count    TYPE integer,
    ALTER COLUMN refinery_best     TYPE integer,
    ALTER COLUMN industrial_count  TYPE integer,
    ALTER COLUMN industrial_best   TYPE integer,
    ALTER COLUMN hightech_count    TYPE integer,
    ALTER COLUMN hightech_best     TYPE integer,
    ALTER COLUMN military_count    TYPE integer,
    ALTER COLUMN military_best     TYPE integer,
    ALTER COLUMN tourism_count     TYPE integer,
    ALTER COLUMN tourism_best      TYPE integer,
    ALTER COLUMN total_viable      TYPE integer;

CREATE OR REPLACE VIEW top_clusters AS
SELECT
    s.id64, s.name, s.x, s.y, s.z, s.population,
    s.galaxy_region_id,
    gr.name AS galaxy_region,
    cs.coverage_score, cs.economy_diversity, cs.total_viable,
    cs.agriculture_count, cs.agriculture_best,
    cs.refinery_count,   cs.refinery_best,
    cs.industrial_count, cs.industrial_best,
    cs.hightech_count,   cs.hightech_best,
    cs.military_count,   cs.military_best,
    cs.tourism_count,    cs.tourism_best
FROM cluster_summary cs
JOIN systems s ON s.id64 = cs.system_id64
LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
WHERE cs.coverage_score IS NOT NULL
  AND cs.economy_diversity >= 3
ORDER BY cs.coverage_score DESC;
