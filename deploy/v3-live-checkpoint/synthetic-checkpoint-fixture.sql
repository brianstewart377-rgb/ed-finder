-- Minimal repository-owned NON-PRODUCTION data for the first Finder/Inspect
-- checkpoint. Every identity and fact in this file is synthetic. This is not
-- a representative galaxy dataset and must never be merged with canonical or
-- production data.

BEGIN;

CREATE TABLE IF NOT EXISTS checkpoint_fixture_metadata (
    fixture_id TEXT PRIMARY KEY,
    classification TEXT NOT NULL CHECK (classification = 'synthetic_non_production'),
    source TEXT NOT NULL CHECK (source = 'repository_owned'),
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO checkpoint_fixture_metadata (fixture_id, classification, source)
VALUES ('checkpoint-synthetic-v1', 'synthetic_non_production', 'repository_owned')
ON CONFLICT (fixture_id) DO NOTHING;

INSERT INTO systems (
    id64, name, x, y, z, primary_economy, secondary_economy, population,
    is_colonised, controlling_faction, security, allegiance, government,
    main_star_type, main_star_subtype, main_star_is_scoopable,
    galaxy_region_id, has_body_data, body_count, data_quality,
    rating_dirty, cluster_dirty
) VALUES
    (7300000000001, 'Checkpoint Synthetic Alpha', 10, 5, -4,
     'HighTech', 'Industrial', 125000, TRUE, 'Synthetic Checkpoint Cooperative',
     'High', 'Independent', 'Cooperative', 'G', 'G2 V', TRUE,
     18, TRUE, 3, 100, FALSE, FALSE),
    (7300000000002, 'Checkpoint Synthetic Beta', 22, -8, 12,
     'Extraction', 'Refinery', 0, FALSE, NULL,
     'Unknown', 'None', 'None', 'K', 'K4 V', TRUE,
     18, TRUE, 2, 90, FALSE, FALSE),
    (7300000000003, 'Checkpoint Synthetic Gamma', -18, 14, 20,
     'Agriculture', 'Terraforming', 0, FALSE, NULL,
     'Unknown', 'None', 'None', 'F', 'F7 V', TRUE,
     18, TRUE, 2, 90, FALSE, FALSE),
    (7300000000004, 'Checkpoint Synthetic Delta', 35, 18, -25,
     'Tourism', 'None', 0, FALSE, NULL,
     'Unknown', 'None', 'None', 'A', 'A8 V', TRUE,
     18, TRUE, 2, 85, FALSE, FALSE)
ON CONFLICT (id64) DO NOTHING;

INSERT INTO bodies (
    id, system_id64, name, body_type, subtype, is_main_star,
    distance_from_star, is_landable, is_terraformable, is_water_world,
    bio_signal_count, geo_signal_count, spectral_class, is_scoopable,
    estimated_mapping_value, estimated_scan_value
) VALUES
    (7300000000101, 7300000000001, 'Checkpoint Synthetic Alpha A',
     'Star', 'G (White-Yellow) Star', TRUE, 0, FALSE, FALSE, FALSE,
     0, 0, 'G2 V', TRUE, 1200, 2400),
    (7300000000102, 7300000000001, 'Checkpoint Synthetic Alpha A 1',
     'Planet', 'Earth-like world', FALSE, 480, TRUE, TRUE, FALSE,
     3, 1, NULL, NULL, 650000, 320000),
    (7300000000103, 7300000000001, 'Checkpoint Synthetic Alpha A 2',
     'Planet', 'Water world', FALSE, 920, FALSE, TRUE, TRUE,
     1, 0, NULL, NULL, 420000, 210000),
    (7300000000201, 7300000000002, 'Checkpoint Synthetic Beta A',
     'Star', 'K (Yellow-Orange) Star', TRUE, 0, FALSE, FALSE, FALSE,
     0, 0, 'K4 V', TRUE, 1000, 2000),
    (7300000000202, 7300000000002, 'Checkpoint Synthetic Beta A 1',
     'Planet', 'High metal content world', FALSE, 350, TRUE, TRUE, FALSE,
     0, 2, NULL, NULL, 175000, 85000),
    (7300000000301, 7300000000003, 'Checkpoint Synthetic Gamma A',
     'Star', 'F (White) Star', TRUE, 0, FALSE, FALSE, FALSE,
     0, 0, 'F7 V', TRUE, 1100, 2200),
    (7300000000302, 7300000000003, 'Checkpoint Synthetic Gamma A 1',
     'Planet', 'Water world', FALSE, 610, FALSE, TRUE, TRUE,
     2, 0, NULL, NULL, 400000, 200000),
    (7300000000401, 7300000000004, 'Checkpoint Synthetic Delta A',
     'Star', 'A (Blue-White) Star', TRUE, 0, FALSE, FALSE, FALSE,
     0, 0, 'A8 V', TRUE, 1300, 2600),
    (7300000000402, 7300000000004, 'Checkpoint Synthetic Delta A 1',
     'Planet', 'Rocky body', FALSE, 760, TRUE, FALSE, FALSE,
     4, 3, NULL, NULL, 90000, 45000)
ON CONFLICT (id) DO NOTHING;

INSERT INTO stations (
    id, system_id64, name, station_type, distance_from_star, body_name,
    landing_pad_size, has_market, has_shipyard, has_outfitting,
    has_refuel, has_repair, has_rearm, has_universal_cartographics,
    primary_economy, secondary_economy, controlling_faction,
    allegiance, government
) VALUES (
    7300000001001, 7300000000001, 'Checkpoint Synthetic Hub', 'Coriolis',
    620, NULL, 'L', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE,
    'HighTech', 'Industrial', 'Synthetic Checkpoint Cooperative',
    'Independent', 'Cooperative'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ratings (
    system_id64, score, score_agriculture, score_refinery,
    score_industrial, score_hightech, score_military, score_tourism,
    score_extraction, economy_suggestion, elw_count, ww_count,
    landable_count, terraformable_count, walkable_count,
    bio_signal_total, geo_signal_total, other_star_count, slots,
    body_quality, compactness, signal_quality, orbital_safety, star_bonus,
    terraforming_potential, body_diversity, confidence, rationale,
    rating_version
) VALUES
    (7300000000001, 88, 74, 62, 78, 91, 54, 82, 58, 'HighTech',
     1, 1, 1, 2, 0, 4, 1, 1, 16, 92, 80, 76, 84, 8, 90, 24, 1.0,
     'Synthetic checkpoint fixture for Finder and Inspect.', 'checkpoint-synthetic-v1'),
    (7300000000002, 76, 35, 86, 73, 42, 58, 33, 94, 'Extraction',
     0, 0, 1, 1, 0, 0, 2, 1, 11, 78, 72, 50, 81, 5, 62, 12, 1.0,
     'Synthetic checkpoint fixture for Finder and Inspect.', 'checkpoint-synthetic-v1'),
    (7300000000003, 81, 93, 48, 52, 66, 40, 73, 38, 'Agriculture',
     0, 1, 0, 1, 0, 2, 0, 1, 13, 87, 70, 68, 85, 7, 95, 18, 1.0,
     'Synthetic checkpoint fixture for Finder and Inspect.', 'checkpoint-synthetic-v1'),
    (7300000000004, 69, 44, 39, 46, 70, 51, 92, 45, 'Tourism',
     0, 0, 1, 0, 0, 4, 3, 1, 9, 72, 67, 88, 76, 9, 35, 10, 1.0,
     'Synthetic checkpoint fixture for Finder and Inspect.', 'checkpoint-synthetic-v1')
ON CONFLICT (system_id64) DO NOTHING;

-- Body-insert integrity triggers correctly mark derived data dirty. These
-- explicit fixture ratings are the derived values for this bounded dataset.
UPDATE systems
SET rating_dirty = FALSE, cluster_dirty = FALSE
WHERE id64 BETWEEN 7300000000001 AND 7300000000004;

COMMIT;

-- The migration creates this materialized view WITH NO DATA. Finder joins it
-- even when the minimal fixture deliberately has no archetype-derived rows.
REFRESH MATERIALIZED VIEW mv_archetype_rankings;
