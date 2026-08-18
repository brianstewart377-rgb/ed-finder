-- Seed test galaxy with 5,000+ realistic systems distributed across the galaxy
-- This gives us enough data to test the map at all zoom levels

-- Bulk insert synthetic systems with proper distribution
WITH generated_systems AS (
  SELECT
    1000000 + i AS id64,
    'Synthetic_' || i::text AS name,
    (random() * 60000 - 30000)::real AS x,
    (random() * 1000 - 500)::real AS y,
    (random() * 60000 - 30000)::real AS z,
    (ARRAY['O','B','A','F','G','K','M','L','T','Y'])[((i % 10) + 1)] AS main_star_type
  FROM generate_series(1, 5000) i
)
INSERT INTO systems (
  id64, name, x, y, z, main_star_type, primary_economy,
  secondary_economy, population, is_colonised, security,
  allegiance, government, updated_at, first_discovered_at
)
SELECT
  id64, name, x, y, z, main_star_type, 'Unknown'::economy_type,
  'None'::economy_type, (random() * 10000000)::bigint, false,
  'Unknown'::security_type, 'Unknown'::allegiance_type,
  'Unknown'::government_type, now(), now()
FROM generated_systems
ON CONFLICT (id64) DO NOTHING;

-- Create ratings for all systems
INSERT INTO ratings (system_id64, score, rating_version, confidence)
SELECT DISTINCT s.id64, (((s.id64 % 100) + 1) * 10)::int, '3.4', 0.85
FROM systems s
LEFT JOIN ratings r ON s.id64 = r.system_id64
WHERE r.system_id64 IS NULL
ON CONFLICT (system_id64, rating_version) DO NOTHING;

-- Refresh materialized views
SELECT refresh_map_mviews(false);

-- Verify
SELECT COUNT(*) as total_systems FROM systems;
SELECT COUNT(*) as heatmap_cells FROM mv_map_heatmap_200ly;
