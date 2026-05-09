-- ─────────────────────────────────────────────────────────────────────────
-- ED Finder — Preview/dev seed data
--
-- Populates a tiny sample of well-known Elite Dangerous systems so the
-- preview environment has something to render. Real production has 186M+
-- rows; here we ship ~40 hand-picked systems (plus a few bodies & stations)
-- so the search / detail / map endpoints all return non-empty results.
-- Idempotent: ON CONFLICT DO NOTHING everywhere.
-- ─────────────────────────────────────────────────────────────────────────

INSERT INTO systems (id64, name, x, y, z, primary_economy, secondary_economy, population, is_colonised, security, allegiance, government, main_star_type, main_star_subtype, has_body_data, body_count, data_quality, galaxy_region_id) VALUES
  (10477373803,        'Sol',                 0,         0,         0,         'Refinery',     'HighTech',     22780871769, true, 'High',   'Federation', 'Democracy',    'G',  '2 V',  true, 41, 5, 18),
  (1109989017963,      'Alpha Centauri',     3.03,    -0.09,    3.16,         'Extraction',   'Refinery',     0,            false,'Low',    'Independent','None',         'G',  '2 V',  true, 11, 5, 18),
  (908486931187,       'Sirius',            -6.34,    -1.90,   -5.84,         'HighTech',     'Industrial',   25000,        true, 'Medium', 'Independent','Corporate',    'A',  '0 V',  true, 13, 5, 18),
  (76051116745449,     'Lave',              -78.59,  -149.62,  -340.34,       'Agriculture',  'Tourism',      14573872,     true, 'High',   'Alliance',   'Democracy',    'G',  '5 V',  true, 8,  5, 18),
  (5031654888146,      'Diaguandri',         -41.06,  -62.16,  -103.25,       'Refinery',     'HighTech',     11313056,     true, 'High',   'Independent','Democracy',    'K',  '5 V',  true, 9,  5, 18),
  (10477373803000,     'Achenar',             67.50,  -119.47,  24.84,        'Industrial',   'HighTech',     6700000000,   true, 'High',   'Empire',     'Patronage',    'A',  '0 V',  true, 14, 5, 18),
  (3032276286120,      'Beta Hydri',         33.87,  -38.59,    32.31,        'HighTech',     'Industrial',   5121480768,   true, 'High',   'Federation', 'Democracy',    'G',  '2 IV', true, 12, 5, 18),
  (3107332155339,      'Procyon',            -10.43, -3.15,    -11.84,        'HighTech',     'Refinery',     0,            false,'Low',    'Independent','None',         'F',  '5 IV-V',true, 5, 5, 18),
  (5031654888100,      'Barnard''s Star',     -3.03,  1.37,     1.69,         'Industrial',   'Refinery',     0,            false,'Low',    'Federation', 'None',         'M',  '4 V',  true, 4,  5, 18),
  (12081669496681,     'Wolf 359',           4.06,    7.28,     -3.06,        'HighTech',     'Industrial',   1370000,      true, 'Medium', 'Independent','Cooperative',  'M',  '6 V',  true, 4,  5, 18),
  (2106438391457,      'Eravate',           -42.43,   -3.15,    59.81,        'Industrial',   'Refinery',     14906000,     true, 'High',   'Federation', 'Democracy',    'K',  '0 V',  true, 9,  5, 18),
  (5378341272451,      'Shinrarta Dezhra',   55.71,    17.59,    27.15,        'HighTech',     'Industrial',   85206935,     true, 'High',   'PilotsFederation','Democracy','M','8 V', true, 6,  5, 18),
  (40028348107985,     'Jacques Station (Eol Prou RS-T d3-94)', -9529.625, -910.31, 19808.78, 'Tourism','HighTech',     0, false, 'Low', 'Independent','None','K','3 V', true, 7, 4, 1),
  (1733180283851,      'LHS 3447',          -42.91,    -1.87,   60.63,         'Refinery',     'Industrial',   1064310,      true, 'Medium', 'Federation', 'Democracy',    'M',  '1 V',  true, 6,  4, 18),
  (5856288576642,      'Maia',              -81.78,  -149.40,  -343.37,        'Tourism',      'HighTech',     0,            false,'Low',    'Independent','None',         'B',  '7 V',  true, 9,  4, 18),
  (1109989017900,      'Colonia',            -9530.50, -910.28, 19808.13,      'HighTech',     'Industrial',   356800,       true, 'High',   'Independent','Cooperative',  'A',  '5 V',  true, 7,  4, 1 ),
  (40554234393,        'Asellus Primus',    -23.93,    -6.34,   18.84,         'Refinery',     'Industrial',   2150000,      true, 'High',   'Alliance',   'Democracy',    'F',  '5 V',  true, 9,  4, 18),
  (672296468643,       'Ross 154',           4.50,     5.00,     -7.93,        'Refinery',     'Industrial',   8300,         true, 'Low',    'Independent','None',         'M',  '3.5 V',true, 4,  4, 18),
  (10477373850,        'Wolf 1301',          53.87,    7.20,     32.50,        'Industrial',   'Refinery',     6500000,      true, 'High',   'Federation', 'Democracy',    'M',  '4 V',  true, 5,  4, 18),
  (16064215129,        'Robigo',             -9529.62, -912.44,  19799.29,     'Tourism',      'HighTech',     0,            false,'Low',    'Independent','None',         'M',  '1 V',  true, 7,  4, 1),
  (560001019643,       'Sothis',              80.16,   -33.97,   -71.40,       'Tourism',      'Industrial',   33800,        true, 'Medium', 'Federation', 'Corporate',    'K',  '4 V',  true, 8,  4, 18),
  (671989141425,       'Hutton Orbital (Alpha Centauri 1)', 3.03, -0.09, 3.16, 'Refinery',     'HighTech',     0,            false,'Low',    'Independent','None',         'G',  '2 V',  true, 11, 4, 18),
  (5856288576500,      'Tau Ceti',           -13.84,   -7.84,   -10.59,        'Agriculture',  'Tourism',      8300000,      true, 'Medium', 'Federation', 'Democracy',    'G',  '8.5 V',true, 7,  4, 18),
  (3107332155000,      'Pleiades Sector HR-W d1-79', -77.06, -147.06, -340.16, 'Extraction',   'Industrial',   0,            false,'Low',    'Independent','None',         'A',  '3 V',  true, 5,  4, 18),
  (12081669496500,     'Synuefe EU-Q c21-15', -2920.40, -90.71,  3380.34,      'Extraction',   'Refinery',     0,            false,'Low',    'Independent','None',         'M',  '5 V',  true, 6,  3, 1),
  (16064215100,        'HIP 22460',          -101.50,  -78.84,  -47.84,        'Tourism',      'Refinery',     0,            false,'Low',    'Independent','None',         'A',  '0 V',  true, 7,  3, 18),
  (672296468700,       'HIP 17692',          -84.62,  -149.46, -343.40,        'Refinery',     'Tourism',      0,            false,'Low',    'Independent','None',         'F',  '8 V',  true, 6,  3, 18),
  (40028348107000,     'Merope',              -78.59,  -149.62, -340.34,       'Tourism',      'HighTech',     0,            false,'Low',    'Independent','None',         'B',  '6 V',  true, 8,  4, 18),
  (40554234300,        'Witch Head Sector IR-W d1-105',  -347.31,-49.78, -710.43, 'Extraction','Industrial', 0, false,'Low','Independent','None','A','3 V',true, 5, 3, 18),
  (560001019700,       'Pleione',             -82.84,  -149.78, -344.84,       'Refinery',     'Tourism',      0,            false,'Low',    'Independent','None',         'B',  '8 V',  true, 6,  4, 18),
  (671989141500,       'HIP 21991',           -88.62,  -147.46, -348.59,       'Industrial',   'Refinery',     0,            false,'Low',    'Independent','None',         'F',  '4 V',  true, 5,  3, 18),
  (1733180283900,      'Atlas',               -82.93,  -148.71, -344.59,       'Tourism',      'HighTech',     0,            false,'Low',    'Independent','None',         'B',  '8 III',true, 6,  4, 18),
  (2106438391500,      'Electra',             -83.59,  -149.40, -342.84,       'Tourism',      'HighTech',     0,            false,'Low',    'Independent','None',         'B',  '6 IV', true, 7,  4, 18),
  (5378341272500,      'Taygeta',             -82.71,  -148.06, -344.84,       'Tourism',      'HighTech',     0,            false,'Low',    'Independent','None',         'B',  '6 V',  true, 6,  4, 18),
  (3032276286200,      'Celaeno',             -78.78,  -150.21, -343.46,       'Tourism',      'HighTech',     0,            false,'Low',    'Independent','None',         'B',  '7 IV', true, 5,  4, 18),
  (1109989017990,      'Witch Head Nebula HIP 17125',-352.71,-49.93,-705.62,   'Extraction',   'Industrial',   0,            false,'Low',    'Independent','None',         'M',  '2 V',  true, 4,  3, 18),
  (908486931200,       'IC 2391 Sector YZ-O b6-7', 466.81,    -57.62,  -110.06, 'Tourism',     'Refinery',     0,            false,'Low',    'Independent','None',         'F',  '6 V',  true, 5,  3, 18),
  (76051116745500,     'Coalsack Sector EQ-Y b13', -1207.34, -47.06,  504.81,  'Extraction', 'Industrial',     0,            false,'Low',    'Independent','None',         'A',  '5 V',  true, 4,  3, 18),
  (5031654888200,      'Bovomit',              -39.06,    33.78,  -7.62,       'Agriculture',  'Tourism',      980000,       true, 'Medium', 'Independent','Democracy',    'K',  '5 V',  true, 6,  4, 18),
  (10477373900,        'Ngalinn',             -54.59,    77.62,   60.78,       'HighTech',     'Industrial',   2700000,      true, 'High',   'Independent','Democracy',    'G',  '2 V',  true, 7,  4, 18)
ON CONFLICT (id64) DO NOTHING;

-- Sample bodies (a star + a few planets per system, just for the first dozen systems)
INSERT INTO bodies (id, system_id64, name, body_type, subtype, is_main_star, distance_from_star, radius, mass, gravity, surface_temp, is_terraformable, is_landable, is_water_world, is_earth_like, is_ammonia_world, bio_signal_count, geo_signal_count) VALUES
  (1,  10477373803, 'Sol',           'Star',  'G2 V',          true,  0,    695700,  1.0,    NULL,   5778, false, false, false, false, false, 0, 0),
  (2,  10477373803, 'Mercury',       'Planet','High metal content body', false, 57909, 2440, 0.055, 3.7,    440, false, true,  false, false, false, 0, 12),
  (3,  10477373803, 'Venus',         'Planet','High metal content body', false, 108200,6052, 0.815, 8.87,   737, false, false, false, false, false, 0, 0),
  (4,  10477373803, 'Earth',         'Planet','Earth-like world',       false, 149600,6371, 1.0,   9.81,   288, false, false, false, true,  false, 5, 0),
  (5,  10477373803, 'Mars',          'Planet','Rocky body',              false, 227940,3389, 0.107, 3.71,   210, true,  true,  false, false, false, 1, 8),
  (6,  10477373803, 'Jupiter',       'Planet','Gas giant',                false, 778500,69911,317.8, 24.79, 165, false, false, false, false, false, 0, 0),
  (7,  10477373803, 'Saturn',        'Planet','Gas giant',                false, 1429400,58232,95.16,10.44, 134, false, false, false, false, false, 0, 0),
  (8,  10477373803, 'Uranus',        'Planet','Ice giant',                false, 2870972,25362,14.54,8.69,  76,  false, false, false, false, false, 0, 0),
  (9,  10477373803, 'Neptune',       'Planet','Ice giant',                false, 4498252,24622,17.15,11.15, 72,  false, false, false, false, false, 0, 0),
  (10, 1109989017963,'Alpha Centauri A','Star','G2 V',                    true,  0, 696500, 1.1, NULL, 5790, false, false, false, false, false, 0, 0),
  (11, 1109989017963,'Alpha Centauri B','Star','K1 V',                    false, 0, 600000, 0.907,NULL,5260, false, false, false, false, false, 0, 0),
  (12, 1109989017963,'Proxima Centauri b','Planet','Rocky body',          false, 7500,6800, 1.27,9.84, 234, true,  true, false, false, false, 2, 5),
  (13, 908486931187, 'Sirius A',     'Star','A0 V',                      true,  0, 1700000,2.02,NULL, 9940, false, false, false, false, false, 0, 0),
  (14, 908486931187, 'Sirius Atmospherics','Planet','High metal content body',false,180,5800,0.7,7.5,520, false, true, false, false, false, 0, 4),
  (15, 76051116745449,'Lave',        'Planet','Earth-like world',         false, 100000,6500,1.05,9.85,290, false, false, false, true, false, 6, 0),
  (16, 5031654888146,'Diaguandri 1', 'Planet','High metal content body', false, 50000, 4500, 0.8, 7.2,  450, false, true, false, false, false, 0, 6),
  (17, 5378341272451,'Shinrarta Dezhra A','Star','M8 V',                  true,  0, 380000, 0.18,NULL, 2900, false, false, false, false, false, 0, 0),
  (18, 5378341272451,'Founders World','Planet','Earth-like world',       false, 25000, 6300, 1.02, 9.84, 285, false, false, false, true,  false, 4, 0)
ON CONFLICT (id) DO NOTHING;

-- Sample stations
INSERT INTO stations (id, system_id64, name, station_type, distance_from_star, body_name, landing_pad_size, has_market, has_shipyard, has_outfitting, has_refuel, has_repair, has_rearm, has_universal_cartographics, primary_economy, allegiance, government) VALUES
  (1, 10477373803,    'Mars High',           'Coriolis',  227940,  'Mars',     'L', true, true, true, true, true, true, true, 'Refinery',     'Federation', 'Democracy'),
  (2, 10477373803,    'Galileo',             'Ocellus',   386,     'Earth',    'L', true, true, true, true, true, true, true, 'HighTech',     'Federation', 'Democracy'),
  (3, 10477373803,    'Daedalus',            'Coriolis',  220,     'Earth',    'L', true, true, true, true, true, true, true, 'Industrial',   'Federation', 'Democracy'),
  (4, 1109989017963,  'Hutton Orbital',      'Outpost',   6784000, 'Eden',     'M', true, false,true, true, true, true, true, 'Refinery',     'Independent','None'),
  (5, 5378341272451,  'Jameson Memorial',    'Ocellus',   325,     'Founders World','L', true, true, true, true, true, true, true, 'HighTech', 'PilotsFederation','Democracy'),
  (6, 76051116745449, 'Lave Station',        'Coriolis',  300,     'Lave',     'L', true, true, true, true, true, true, true, 'Agriculture',  'Alliance',   'Democracy'),
  (7, 1109989017900,  'Jaques Station',      'AsteroidBase',300,   NULL,       'L', true, true, true, true, true, true, true, 'HighTech',     'Independent','None'),
  (8, 908486931187,   'Sirius Atmospherics', 'Coriolis',  380,     NULL,       'L', true, true, true, true, true, true, true, 'HighTech',     'Independent','Corporate'),
  (9, 5031654888146,  'Ray Gateway',         'Orbis',     323,     NULL,       'L', true, true, true, true, true, true, true, 'Refinery',     'Independent','Democracy'),
  (10,10477373803000, 'Capitol',             'Ocellus',   320,     'Capitol',  'L', true, true, true, true, true, true, true, 'Industrial',   'Empire',     'Patronage')
ON CONFLICT (id) DO NOTHING;

-- Pre-populate ratings so /api/search returns scored systems
INSERT INTO ratings (system_id64, score, score_agriculture, score_refinery, score_industrial, score_hightech, score_military, score_tourism, economy_suggestion, elw_count, ww_count, ammonia_count, gas_giant_count, rocky_count, metal_rich_count, icy_count, hmc_count, landable_count, terraformable_count, bio_signal_total, geo_signal_total, slots, body_quality, compactness, signal_quality, orbital_safety, star_bonus)
SELECT id64,
  -- Compose a deterministic "score" from population & body_count for variety
  LEAST(95, 30 + (body_count * 4) + LEAST(40, GREATEST(0, ((population)::bigint / 1000000)::int)))::smallint,
  CASE primary_economy WHEN 'Agriculture' THEN 95 ELSE 30 + (body_count * 2) END,
  CASE primary_economy WHEN 'Refinery'    THEN 90 ELSE 25 + body_count * 3 END,
  CASE primary_economy WHEN 'Industrial'  THEN 92 ELSE 28 + body_count * 3 END,
  CASE primary_economy WHEN 'HighTech'    THEN 95 ELSE 30 + body_count * 3 END,
  CASE primary_economy WHEN 'Military'    THEN 85 ELSE 20 + body_count * 2 END,
  CASE primary_economy WHEN 'Tourism'     THEN 88 ELSE 22 + body_count * 2 END,
  primary_economy,
  CASE WHEN name IN ('Sol', 'Lave', 'Shinrarta Dezhra') THEN 1 ELSE 0 END,
  CASE WHEN body_count > 8 THEN 2 ELSE 0 END,
  -- Trailing literals map to: ammonia_count, gas_giant_count, rocky_count,
  -- metal_rich_count, icy_count, hmc_count, landable_count,
  -- terraformable_count, bio_signal_total, geo_signal_total, slots,
  -- body_quality, compactness, signal_quality, orbital_safety, star_bonus
  -- (16 values to match the 16 trailing target columns — the previous
  -- 17-value list raised "INSERT has more expressions than target columns"
  -- and left the seed `ratings` table empty, breaking integration tests).
  0, 2, 3, 1, 1, 2, 2, 3, 4, 8, 5, 70, 75, 80, 75, 5
FROM systems
ON CONFLICT (system_id64) DO NOTHING;

-- Mark them as not dirty so build_ratings doesn't try to recompute
UPDATE systems SET rating_dirty = false, cluster_dirty = false WHERE rating_dirty = true;

-- App meta — pretend imports/ratings/clusters all completed
INSERT INTO app_meta (key, value) VALUES
  ('import_complete',    'true'),
  ('ratings_built',      'true'),
  ('grid_built',         'true'),
  ('clusters_built',     'true'),
  ('eddn_enabled',       'false'),
  ('schema_version',     '2.0'),
  ('last_nightly_update','preview-seed')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- Print result counts so we know it worked.
SELECT 'systems' AS table, COUNT(*) AS rows FROM systems
UNION ALL SELECT 'bodies',   COUNT(*) FROM bodies
UNION ALL SELECT 'stations', COUNT(*) FROM stations
UNION ALL SELECT 'ratings',  COUNT(*) FROM ratings;
