-- =============================================================================
-- ED Finder — Migration 014: Archetype Materialized View
-- Phase 1 of the Colonisation Engine Redesign (v4.0)
--
-- Creates:
--   • mv_archetype_rankings   materialized view
--   • All indexes on the MV
--   • Additional performance indexes on the source tables
--
-- Depends on:
--   012_topology_tables.sql    (system_slot_topology, colony_archetype enum)
--   013_archetype_scores.sql   (system_archetype_scores, system_archetype_traits)
--
-- IMPORTANT: The MV is created WITH NO DATA on first migration.
-- After running build_topology.py + build_archetype_scores.py for the first
-- time, run:
--   REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Materialized View: mv_archetype_rankings
--
-- Pre-joined, pre-sorted ranking table combining:
--   systems                → coordinates, name, region, star type
--   system_archetype_scores → all 10 archetype scores + buildability + purity
--   system_archetype_traits → boolean flags, body counts, display tags
--   system_slot_topology    → topology metrics (LEFT JOIN — may be NULL)
--
-- REFRESH CONCURRENTLY is safe (non-blocking) once the unique index
-- idx_mv_archetype_id64 exists.
--
-- Refresh frequency:
--   • After each full build_archetype_scores.py run (~nightly)
--   • After each build_archetype_scores.py --dirty run
--
-- Excludes rows where dirty = TRUE (scores not yet computed) or
-- overall_development_potential = 0 (system has no body data).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_archetype_rankings AS
SELECT
    -- ── System identity ───────────────────────────────────────────────────────
    s.id64,
    s.name,
    s.x,
    s.y,
    s.z,
    s.distance_to_sol,
    s.main_star_type,
    s.galaxy_region_id,

    -- ── Archetype classification ──────────────────────────────────────────────
    a.primary_archetype,
    a.secondary_archetype,
    a.archetype_confidence,

    -- ── All 10 archetype scores ───────────────────────────────────────────────
    a.score_refinery_industrial,
    a.score_extraction_refinery,
    a.score_agriculture_terraforming,
    a.score_hitech_tourism,
    a.score_expansion_capital,
    a.score_trade_logistics,
    a.score_population_capital,
    a.score_ax_forward_base,
    a.score_military_industrial,
    a.score_flexible_multirole,

    -- ── Composite + buildability ──────────────────────────────────────────────
    a.overall_development_potential,
    a.buildability_score,
    a.build_complexity,
    a.cp_efficiency,
    a.t3_scaling_viability,
    a.slot_efficiency,

    -- ── Purity & contamination summary ───────────────────────────────────────
    a.purity_score,
    a.contamination_risk,
    a.stable_top_two_prob,

    -- ── Data quality ─────────────────────────────────────────────────────────
    a.confidence,

    -- ── Trait flags (for filter pills) ───────────────────────────────────────
    t.has_elw,
    t.has_water_world,
    t.has_ammonia_world,
    t.has_black_hole,
    t.has_neutron_star,
    t.has_white_dwarf,
    t.has_ringed_body,
    t.has_terraformables,
    t.is_scoopable_star,

    -- ── Body counts (for filter ranges) ──────────────────────────────────────
    t.elw_count,
    t.ww_count,
    t.ammonia_count,
    t.gas_giant_count,
    t.rocky_clean_count,
    t.rocky_ice_count,
    t.icy_count,
    t.hmc_count,
    t.landable_count,
    t.terraformable_count,
    t.bio_signal_total,
    t.geo_signal_total,
    t.total_body_count,

    -- ── Slot estimates (from traits — join-free) ──────────────────────────────
    t.est_total_slots,
    t.est_orbital_slots,
    t.est_ground_slots,

    -- ── Display tags ─────────────────────────────────────────────────────────
    t.display_tags,

    -- ── Topology metrics (LEFT JOIN — NULL if topology not yet computed) ──────
    topo.estimated_orbital_slots    AS topo_orbital_slots,
    topo.estimated_ground_slots     AS topo_ground_slots,
    topo.strong_link_potential,
    topo.weak_link_stability,
    topo.nesting_potential,
    topo.orbital_synergy,
    topo.ground_synergy,
    topo.build_flexibility,
    topo.contamination_risk         AS topo_contamination_risk,
    topo.has_viable_surface_port,
    topo.has_deep_orbital_anchor,
    topo.has_ringed_gas_giant,

    -- ── Timestamp for staleness checks ───────────────────────────────────────
    a.updated_at                    AS scores_updated_at

FROM systems s
JOIN  system_archetype_scores a   ON a.system_id64 = s.id64
JOIN  system_archetype_traits t   ON t.system_id64 = s.id64
LEFT JOIN system_slot_topology topo ON topo.system_id64 = s.id64

-- Only include scored, non-dirty systems with actual score data
WHERE a.dirty = FALSE
  AND a.overall_development_potential > 0

WITH NO DATA;

COMMENT ON MATERIALIZED VIEW mv_archetype_rankings IS
    'Pre-joined archetype ranking table. Combines systems, '
    'system_archetype_scores, system_archetype_traits, and '
    'system_slot_topology (LEFT JOIN). Refreshed after each '
    'build_archetype_scores.py run via: '
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings. '
    'Created WITH NO DATA — must be refreshed after first data load.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Indexes on mv_archetype_rankings
--
-- The unique index on id64 is required for REFRESH CONCURRENTLY.
-- All other indexes support the expected query patterns.
-- ─────────────────────────────────────────────────────────────────────────────

-- Required for REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_archetype_id64
    ON mv_archetype_rankings (id64);

-- Per-archetype ranking indexes (primary query pattern for each archetype)
CREATE INDEX IF NOT EXISTS idx_mv_archetype_refinery
    ON mv_archetype_rankings (score_refinery_industrial DESC)
    WHERE score_refinery_industrial >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_archetype_extraction
    ON mv_archetype_rankings (score_extraction_refinery DESC)
    WHERE score_extraction_refinery >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_archetype_agri
    ON mv_archetype_rankings (score_agriculture_terraforming DESC)
    WHERE score_agriculture_terraforming >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_archetype_hitech
    ON mv_archetype_rankings (score_hitech_tourism DESC)
    WHERE score_hitech_tourism >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_archetype_expansion
    ON mv_archetype_rankings (score_expansion_capital DESC)
    WHERE score_expansion_capital >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_archetype_military
    ON mv_archetype_rankings (score_military_industrial DESC)
    WHERE score_military_industrial >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_archetype_ax
    ON mv_archetype_rankings (score_ax_forward_base DESC)
    WHERE score_ax_forward_base >= 30;

-- Overall development potential (secondary sort / generalist browse)
CREATE INDEX IF NOT EXISTS idx_mv_archetype_odp
    ON mv_archetype_rankings (overall_development_potential DESC);

-- Region + archetype composite (most common filtered query pattern)
CREATE INDEX IF NOT EXISTS idx_mv_arch_region_refinery
    ON mv_archetype_rankings (galaxy_region_id, score_refinery_industrial DESC)
    WHERE score_refinery_industrial >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_arch_region_hitech
    ON mv_archetype_rankings (galaxy_region_id, score_hitech_tourism DESC)
    WHERE score_hitech_tourism >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_arch_region_agri
    ON mv_archetype_rankings (galaxy_region_id, score_agriculture_terraforming DESC)
    WHERE score_agriculture_terraforming >= 30;

CREATE INDEX IF NOT EXISTS idx_mv_arch_region_odp
    ON mv_archetype_rankings (galaxy_region_id, overall_development_potential DESC);

-- Purity filter (for "clean stack" queries)
CREATE INDEX IF NOT EXISTS idx_mv_arch_purity
    ON mv_archetype_rankings (purity_score DESC)
    WHERE purity_score >= 60;

-- Primary archetype categorical (for browsing by category)
CREATE INDEX IF NOT EXISTS idx_mv_arch_primary
    ON mv_archetype_rankings (primary_archetype, overall_development_potential DESC);

-- ELW + black hole prestige filter
CREATE INDEX IF NOT EXISTS idx_mv_arch_elw
    ON mv_archetype_rankings (elw_count DESC, score_hitech_tourism DESC)
    WHERE has_elw = TRUE;

-- Slot count filter
CREATE INDEX IF NOT EXISTS idx_mv_arch_slots
    ON mv_archetype_rankings (est_total_slots DESC)
    WHERE est_total_slots >= 20;

-- Buildability filter
CREATE INDEX IF NOT EXISTS idx_mv_arch_buildability
    ON mv_archetype_rankings (buildability_score DESC)
    WHERE buildability_score >= 50;

-- ─────────────────────────────────────────────────────────────────────────────
-- Additional performance indexes on source tables
-- (supplementing the indexes in 013_archetype_scores.sql)
-- ─────────────────────────────────────────────────────────────────────────────

-- system_archetype_scores: composite region query via systems join
-- (Galaxy-region filtered archetype queries are common; this partial
-- index on the score table complements the MV region indexes above.)
CREATE INDEX IF NOT EXISTS idx_arch_scores_confidence
    ON system_archetype_scores (confidence DESC)
    WHERE confidence >= 0.85 AND dirty = FALSE;

-- system_slot_topology: strong-link + orbital synergy combined filter
CREATE INDEX IF NOT EXISTS idx_topo_strong_link
    ON system_slot_topology (strong_link_potential DESC)
    WHERE strong_link_potential >= 50;

CREATE INDEX IF NOT EXISTS idx_topo_orbital_synergy
    ON system_slot_topology (orbital_synergy DESC)
    WHERE orbital_synergy >= 40;

CREATE INDEX IF NOT EXISTS idx_topo_ground_synergy
    ON system_slot_topology (ground_synergy DESC)
    WHERE ground_synergy >= 40;

-- ─────────────────────────────────────────────────────────────────────────────
-- Refresh helper comment
-- ─────────────────────────────────────────────────────────────────────────────
-- To populate the MV after the first data load:
--
--   REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;
--
-- To check when the MV was last populated:
--
--   SELECT schemaname, matviewname, ispopulated,
--          pg_size_pretty(pg_relation_size('mv_archetype_rankings')) AS size
--   FROM   pg_matviews
--   WHERE  matviewname = 'mv_archetype_rankings';
--
-- To check row count:
--
--   SELECT COUNT(*) FROM mv_archetype_rankings;
--
-- Estimated refresh time on 50M scored rows: 3–8 minutes.
-- CONCURRENTLY variant does not block reads during refresh.
-- ─────────────────────────────────────────────────────────────────────────────
