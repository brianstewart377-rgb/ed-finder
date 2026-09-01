-- Stage 27A SELECT-only V3 data-coverage audit pack.
-- Run only through an already-authorized read-only operator path.
-- This file performs no writes, DDL, settings changes, or function calls and
-- contains no explicit locking clause. PostgreSQL SELECTs still acquire
-- ACCESS SHARE locks. Use the authorized wrapper's statement/lock timeouts,
-- bounded concurrency, and cancellation controls to limit production impact.
-- Report the database identity/time separately through the authorized wrapper;
-- never add credentials to this file or command history.

-- 1. Systems and coordinates.
SELECT
  COUNT(*) AS systems_total,
  COUNT(*) FILTER (WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL) AS with_xyz,
  COUNT(*) FILTER (WHERE main_star_type IS NOT NULL) AS with_main_star_type,
  MIN(updated_at) AS oldest_updated_at,
  MAX(updated_at) AS newest_updated_at
FROM systems;

-- 2. Body population and physical/stellar properties.
SELECT
  COUNT(*) AS bodies_total,
  COUNT(DISTINCT system_id64) AS systems_with_bodies,
  COUNT(*) FILTER (WHERE name IS NOT NULL) AS with_name,
  COUNT(*) FILTER (WHERE subtype IS NOT NULL) AS with_subtype,
  COUNT(*) FILTER (WHERE radius IS NOT NULL) AS with_radius,
  COUNT(*) FILTER (WHERE mass IS NOT NULL) AS with_mass,
  COUNT(*) FILTER (WHERE gravity IS NOT NULL) AS with_gravity,
  COUNT(*) FILTER (WHERE surface_temp IS NOT NULL) AS with_temperature,
  COUNT(*) FILTER (WHERE surface_pressure IS NOT NULL) AS with_pressure,
  COUNT(*) FILTER (WHERE atmosphere_type IS NOT NULL) AS with_atmosphere_type,
  COUNT(*) FILTER (WHERE atmosphere_composition IS NOT NULL) AS with_atmosphere_composition,
  COUNT(*) FILTER (WHERE solid_composition IS NOT NULL) AS with_solid_composition,
  COUNT(*) FILTER (WHERE materials IS NOT NULL) AS with_materials,
  COUNT(*) FILTER (WHERE volcanism IS NOT NULL) AS with_volcanism,
  COUNT(*) FILTER (WHERE spectral_class IS NOT NULL) AS with_spectral_class,
  COUNT(*) FILTER (WHERE stellar_mass IS NOT NULL) AS with_stellar_mass,
  COUNT(*) FILTER (WHERE luminosity IS NOT NULL) AS with_luminosity,
  COUNT(*) FILTER (WHERE age_my IS NOT NULL) AS with_age,
  COUNT(*) FILTER (WHERE absolute_magnitude IS NOT NULL) AS with_absolute_magnitude,
  MIN(updated_at) AS oldest_updated_at,
  MAX(updated_at) AS newest_updated_at
FROM bodies;

-- 3. Orbital descriptor coverage. Epoch is absent from the current schema.
SELECT
  COUNT(*) AS bodies_total,
  COUNT(*) FILTER (WHERE distance_from_star IS NOT NULL) AS with_distance,
  COUNT(*) FILTER (WHERE orbital_period IS NOT NULL) AS with_period,
  COUNT(*) FILTER (WHERE semi_major_axis IS NOT NULL) AS with_semi_major_axis,
  COUNT(*) FILTER (WHERE orbital_eccentricity IS NOT NULL) AS with_eccentricity,
  COUNT(*) FILTER (WHERE orbital_inclination IS NOT NULL) AS with_inclination,
  COUNT(*) FILTER (WHERE ascending_node IS NOT NULL) AS with_ascending_node,
  COUNT(*) FILTER (WHERE arg_of_periapsis IS NOT NULL) AS with_argument_of_periapsis,
  COUNT(*) FILTER (WHERE mean_anomaly IS NOT NULL) AS with_mean_anomaly,
  COUNT(*) FILTER (
    WHERE orbital_period IS NOT NULL AND semi_major_axis IS NOT NULL
      AND orbital_eccentricity IS NOT NULL AND orbital_inclination IS NOT NULL
      AND ascending_node IS NOT NULL AND arg_of_periapsis IS NOT NULL
      AND mean_anomaly IS NOT NULL
  ) AS with_all_stored_orbital_elements
FROM bodies;

-- 4. Ring bands, association/provenance, and multiple-band population.
SELECT association_status, source, confidence,
       COUNT(*) AS ring_rows,
       COUNT(*) FILTER (WHERE ring_class IS NOT NULL) AS with_class,
       COUNT(*) FILTER (WHERE inner_radius IS NOT NULL AND outer_radius IS NOT NULL) AS with_radii,
       COUNT(DISTINCT (system_id64, body_id)) FILTER (WHERE body_id IS NOT NULL) AS associated_bodies,
       MIN(updated_at) AS oldest_updated_at,
       MAX(updated_at) AS newest_updated_at
FROM body_rings
GROUP BY association_status, source, confidence
ORDER BY association_status, source, confidence;

-- A physical band may have duplicate source rows. A non-blank ring_name is its
-- identity within a body (case/outer-whitespace normalized). For an unnamed
-- band, the complete stored physical signature is its identity; exactly equal
-- signatures collapse, while distinct signatures remain distinct. This can
-- undercount genuinely separate unnamed bands whose stored signatures are
-- indistinguishable, so report that limitation with the audit result.
WITH physical_ring_bands AS (
  SELECT DISTINCT
    system_id64,
    body_id,
    NULLIF(lower(btrim(ring_name)), '') AS normalized_ring_name,
    CASE WHEN NULLIF(btrim(ring_name), '') IS NULL THEN ring_type END AS unnamed_ring_type,
    CASE WHEN NULLIF(btrim(ring_name), '') IS NULL THEN ring_class END AS unnamed_ring_class,
    CASE WHEN NULLIF(btrim(ring_name), '') IS NULL THEN mass_mt END AS unnamed_mass_mt,
    CASE WHEN NULLIF(btrim(ring_name), '') IS NULL THEN inner_radius END AS unnamed_inner_radius,
    CASE WHEN NULLIF(btrim(ring_name), '') IS NULL THEN outer_radius END AS unnamed_outer_radius
  FROM body_rings
  WHERE body_id IS NOT NULL AND association_status = 'local_matched'
), bands_per_body AS (
  SELECT system_id64, body_id, COUNT(*) AS physical_band_count
  FROM physical_ring_bands
  GROUP BY system_id64, body_id
)
SELECT
  COUNT(*) FILTER (WHERE physical_band_count > 1) AS bodies_with_multiple_physical_ring_bands,
  COALESCE(SUM(physical_band_count), 0) AS distinct_physical_ring_bands
FROM bands_per_body;

-- 5. Station data and body association. Missing links stay missing.
SELECT
  COUNT(*) AS stations_total,
  COUNT(*) FILTER (WHERE station_type::text <> 'Unknown') AS with_known_type,
  COUNT(*) FILTER (WHERE distance_from_star IS NOT NULL) AS with_distance,
  COUNT(*) FILTER (WHERE body_name IS NOT NULL) AS with_body_name,
  COUNT(*) FILTER (WHERE primary_economy IS NOT NULL) AS with_primary_economy,
  COUNT(*) FILTER (WHERE has_market OR has_shipyard OR has_outfitting OR has_refuel OR has_repair OR has_rearm) AS with_selected_service,
  MIN(updated_at) AS oldest_updated_at,
  MAX(updated_at) AS newest_updated_at
FROM stations;

SELECT association_status, lane, association_confidence, association_source,
       COUNT(*) AS links,
       COUNT(*) FILTER (WHERE body_id IS NOT NULL) AS with_body_id
FROM station_body_links
GROUP BY association_status, lane, association_confidence, association_source
ORDER BY association_status, lane, association_confidence, association_source;

-- 6. Defensive identity checks. Non-zero rows are unresolved audit findings;
-- do not auto-repair or name-match them.
SELECT COUNT(*) AS cross_system_station_body_links
FROM station_body_links l
JOIN bodies b ON b.id = l.body_id
WHERE l.system_id64 <> b.system_id64;

SELECT COUNT(*) AS cross_system_ring_body_links
FROM body_rings r
JOIN bodies b ON b.id = r.body_id
WHERE r.system_id64 <> b.system_id64;

-- 7. Personal exploration population by source/type without exposing sync keys.
SELECT source, event_type, COUNT(*) AS facts,
       COUNT(DISTINCT system_id64) AS systems,
       COUNT(*) FILTER (WHERE body_id IS NOT NULL) AS with_body_id,
       COUNT(*) FILTER (WHERE body_id IS NULL AND body_name IS NOT NULL) AS name_only_body,
       MIN(observed_at) AS first_observed_at,
       MAX(observed_at) AS last_observed_at
FROM exploration_facts
GROUP BY source, event_type
ORDER BY source, event_type;

SELECT
  COUNT(*) AS body_completeness_rows,
  COUNT(*) FILTER (WHERE body_id IS NOT NULL) AS with_body_id,
  COUNT(*) FILTER (WHERE body_id IS NULL) AS without_body_id,
  COUNT(*) FILTER (WHERE fss_state = 'scanned') AS scanned,
  COUNT(*) FILTER (WHERE dss_state = 'mapped') AS mapped,
  COUNT(*) FILTER (WHERE first_discovered) AS first_discovered,
  COUNT(*) FILTER (WHERE first_mapped) AS first_mapped
FROM exploration_body_completeness;

SELECT
  (SELECT COUNT(*) FROM exploration_visits) AS visits,
  (SELECT COUNT(*) FROM exploration_expedition_routes) AS route_legs,
  (SELECT COUNT(*) FROM exobiology_organisms) AS organism_rows,
  (SELECT COUNT(*) FROM exobiology_sales) AS exobiology_sale_rows,
  (SELECT COUNT(*) FROM codex_observations) AS codex_rows;
