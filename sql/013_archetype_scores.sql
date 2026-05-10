-- =============================================================================
-- ED Finder — Migration 013: Archetype Score Tables
-- Phase 1 of the Colonisation Engine Redesign (v4.0)
--
-- Creates:
--   • system_archetype_scores   table
--   • system_archetype_traits   table
--
-- Depends on: 012_topology_tables.sql (colony_archetype, build_complexity enums)
-- Run before: 014_archetype_mv.sql
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Table: system_archetype_scores
--
-- The heart of the new engine. One row per system, storing per-archetype
-- scores (0-100 each), buildability metrics, purity/contamination summary,
-- and structured JSONB rationale.
--
-- Replaces the role of the single `ratings.score` column as the primary
-- ranking signal — but ratings.score is PRESERVED for backward compatibility.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_archetype_scores (
    system_id64             BIGINT      PRIMARY KEY REFERENCES systems(id64),

    -- ── Primary archetype identification ─────────────────────────────────────
    primary_archetype       colony_archetype    NOT NULL DEFAULT 'unknown',
    secondary_archetype     colony_archetype    NOT NULL DEFAULT 'unknown',
    archetype_confidence    REAL                NOT NULL DEFAULT 0,  -- 0-1

    -- ── Per-archetype scores (0-100 each) ────────────────────────────────────
    -- Each score is independent: a Refinery/Industrial score of 92 does NOT
    -- imply a poor Agriculture/Terraforming score — they are separate axes.
    score_refinery_industrial       REAL    NOT NULL DEFAULT 0,
    score_extraction_refinery       REAL    NOT NULL DEFAULT 0,
    score_agriculture_terraforming  REAL    NOT NULL DEFAULT 0,
    score_hitech_tourism            REAL    NOT NULL DEFAULT 0,
    score_expansion_capital         REAL    NOT NULL DEFAULT 0,
    score_trade_logistics           REAL    NOT NULL DEFAULT 0,
    score_population_capital        REAL    NOT NULL DEFAULT 0,
    score_ax_forward_base           REAL    NOT NULL DEFAULT 0,
    score_military_industrial       REAL    NOT NULL DEFAULT 0,
    score_flexible_multirole        REAL    NOT NULL DEFAULT 0,

    -- ── Composite development potential ──────────────────────────────────────
    -- Supporting metric, NOT the primary ranking signal.
    -- = top-3 archetype average × 0.60 + diversity × 0.20 + buildability × 0.20
    -- Used as a tie-breaker when two systems have equal archetype scores.
    overall_development_potential   REAL    NOT NULL DEFAULT 0,  -- 0-100

    -- ── Buildability ─────────────────────────────────────────────────────────
    buildability_score      REAL            NOT NULL DEFAULT 0,  -- 0-100
    build_complexity        build_complexity NOT NULL DEFAULT 'moderate',
    cp_efficiency           REAL            NOT NULL DEFAULT 0,  -- 0-100
    t3_scaling_viability    REAL            NOT NULL DEFAULT 0,  -- 0-100
    slot_efficiency         REAL            NOT NULL DEFAULT 0,  -- 0-100

    -- ── Purity & contamination ────────────────────────────────────────────────
    purity_score            REAL            NOT NULL DEFAULT 0,  -- 0-100
    contamination_risk      REAL            NOT NULL DEFAULT 0,  -- 0-100
    stable_top_two_prob     REAL            NOT NULL DEFAULT 0,  -- 0-1

    -- ── Data quality ─────────────────────────────────────────────────────────
    confidence              REAL            NOT NULL DEFAULT 0.85,

    -- ── Explainability payload (JSONB) ────────────────────────────────────────
    -- score_breakdown: per-component score decomposition
    -- {body_composition, topology, pair_synergy_pts, purity_factor,
    --  contamination_risk, diversity_factor, per_archetype: {...}}
    score_breakdown         JSONB           NOT NULL DEFAULT '{}'::jsonb,

    -- rationale: structured human-readable explanation per primary archetype
    -- {summary, tier, headline, positives[], risks[], complexity,
    --  build_path, tags[], score_breakdown, data_confidence}
    rationale               JSONB           NOT NULL DEFAULT '{}'::jsonb,

    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- dirty = TRUE means this row needs recomputation.
    -- Set to TRUE by build_ratings.py whenever it updates the matching
    -- ratings row, then cleared by build_archetype_scores.py.
    dirty                   BOOLEAN         NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE system_archetype_scores IS
    'Per-system archetype scores computed by build_archetype_scores.py. '
    'Each score column is an independent 0-100 measure of how well the '
    'system suits that colony archetype. The existing ratings table is '
    'preserved unchanged — this table is purely additive.';

COMMENT ON COLUMN system_archetype_scores.primary_archetype IS
    'The archetype with the highest score for this system.';
COMMENT ON COLUMN system_archetype_scores.secondary_archetype IS
    'The archetype with the second-highest score. Useful for systems '
    'that suit multiple colony types well.';
COMMENT ON COLUMN system_archetype_scores.archetype_confidence IS
    '0-1. How decisively this system belongs to its primary archetype. '
    'Low values indicate a flexible/generalist system.';
COMMENT ON COLUMN system_archetype_scores.overall_development_potential IS
    'Composite metric across all archetypes. Supporting role only — '
    'use per-archetype scores for ranking within an archetype category.';
COMMENT ON COLUMN system_archetype_scores.purity_score IS
    '0-100. How cleanly the system''s bodies support its primary economy '
    'pair without adding competing third economies.';
COMMENT ON COLUMN system_archetype_scores.contamination_risk IS
    '0-100. Estimated risk that a third economy enters the top-2. '
    'Derived from body types that add competing economies.';
COMMENT ON COLUMN system_archetype_scores.rationale IS
    'Structured JSONB rationale for the primary archetype score. '
    'Schema: {summary, tier, headline, positives[], risks[], '
    'complexity, build_path, tags[], score_breakdown, data_confidence}. '
    'JSONB contract — schema is flexible for future mechanic changes.';
COMMENT ON COLUMN system_archetype_scores.dirty IS
    'TRUE when this row needs recomputation. Cleared by '
    'build_archetype_scores.py after successful update.';

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Primary archetype ranking indexes (used by GET /api/archetypes/rankings)
CREATE INDEX IF NOT EXISTS idx_arch_scores_refinery
    ON system_archetype_scores (score_refinery_industrial DESC)
    WHERE score_refinery_industrial >= 40 AND dirty = FALSE;

CREATE INDEX IF NOT EXISTS idx_arch_scores_hitech
    ON system_archetype_scores (score_hitech_tourism DESC)
    WHERE score_hitech_tourism >= 40 AND dirty = FALSE;

CREATE INDEX IF NOT EXISTS idx_arch_scores_agri
    ON system_archetype_scores (score_agriculture_terraforming DESC)
    WHERE score_agriculture_terraforming >= 40 AND dirty = FALSE;

CREATE INDEX IF NOT EXISTS idx_arch_scores_extraction
    ON system_archetype_scores (score_extraction_refinery DESC)
    WHERE score_extraction_refinery >= 40 AND dirty = FALSE;

CREATE INDEX IF NOT EXISTS idx_arch_scores_military
    ON system_archetype_scores (score_military_industrial DESC)
    WHERE score_military_industrial >= 40 AND dirty = FALSE;

CREATE INDEX IF NOT EXISTS idx_arch_scores_ax
    ON system_archetype_scores (score_ax_forward_base DESC)
    WHERE score_ax_forward_base >= 40 AND dirty = FALSE;

CREATE INDEX IF NOT EXISTS idx_arch_scores_expansion
    ON system_archetype_scores (score_expansion_capital DESC)
    WHERE score_expansion_capital >= 40 AND dirty = FALSE;

-- Overall development potential (secondary sort / general browse)
CREATE INDEX IF NOT EXISTS idx_arch_scores_odp
    ON system_archetype_scores (overall_development_potential DESC)
    WHERE overall_development_potential >= 50 AND dirty = FALSE;

-- Primary archetype categorical index (for "show me refinery_industrial systems")
CREATE INDEX IF NOT EXISTS idx_arch_scores_primary_archetype
    ON system_archetype_scores (primary_archetype, score_refinery_industrial DESC)
    WHERE dirty = FALSE;

-- Dirty-flag index (used by build_archetype_scores.py --dirty mode)
CREATE INDEX IF NOT EXISTS idx_arch_scores_dirty
    ON system_archetype_scores (dirty)
    WHERE dirty = TRUE;

-- Purity index (for "find clean-stack systems")
CREATE INDEX IF NOT EXISTS idx_arch_scores_purity
    ON system_archetype_scores (purity_score DESC)
    WHERE purity_score >= 70 AND dirty = FALSE;


-- ─────────────────────────────────────────────────────────────────────────────
-- Table: system_archetype_traits
--
-- Fast-filter boolean flags and counts for the archetype API.
-- Denormalised from the body data for O(1) filter operations.
-- Also stores estimated slot totals (denormalised from system_slot_topology)
-- for queries that need slot counts without a join.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_archetype_traits (
    system_id64         BIGINT      PRIMARY KEY REFERENCES systems(id64),

    -- ── Boolean fast-filter flags ─────────────────────────────────────────────
    has_elw             BOOLEAN     NOT NULL DEFAULT FALSE,
    has_water_world     BOOLEAN     NOT NULL DEFAULT FALSE,
    has_ammonia_world   BOOLEAN     NOT NULL DEFAULT FALSE,
    has_black_hole      BOOLEAN     NOT NULL DEFAULT FALSE,
    has_neutron_star    BOOLEAN     NOT NULL DEFAULT FALSE,
    has_white_dwarf     BOOLEAN     NOT NULL DEFAULT FALSE,
    has_ringed_body     BOOLEAN     NOT NULL DEFAULT FALSE,
    has_terraformables  BOOLEAN     NOT NULL DEFAULT FALSE,
    has_pristine_res    BOOLEAN     NOT NULL DEFAULT FALSE,  -- pristine reserve level
    has_bio_signals     BOOLEAN     NOT NULL DEFAULT FALSE,
    has_geo_signals     BOOLEAN     NOT NULL DEFAULT FALSE,
    is_scoopable_star   BOOLEAN     NOT NULL DEFAULT FALSE,

    -- ── Body type counts ──────────────────────────────────────────────────────
    elw_count           SMALLINT    NOT NULL DEFAULT 0,
    ww_count            SMALLINT    NOT NULL DEFAULT 0,
    ammonia_count       SMALLINT    NOT NULL DEFAULT 0,
    gas_giant_count     SMALLINT    NOT NULL DEFAULT 0,
    rocky_clean_count   SMALLINT    NOT NULL DEFAULT 0,
    rocky_ice_count     SMALLINT    NOT NULL DEFAULT 0,
    icy_count           SMALLINT    NOT NULL DEFAULT 0,
    hmc_count           SMALLINT    NOT NULL DEFAULT 0,
    metal_rich_count    SMALLINT    NOT NULL DEFAULT 0,
    landable_count      SMALLINT    NOT NULL DEFAULT 0,
    terraformable_count SMALLINT    NOT NULL DEFAULT 0,
    bio_signal_total    SMALLINT    NOT NULL DEFAULT 0,
    geo_signal_total    SMALLINT    NOT NULL DEFAULT 0,
    total_body_count    SMALLINT    NOT NULL DEFAULT 0,

    -- ── Slot estimates (denormalised from system_slot_topology) ───────────────
    -- These mirror system_slot_topology values for join-free filter queries.
    est_orbital_slots   SMALLINT    NOT NULL DEFAULT 0,
    est_ground_slots    SMALLINT    NOT NULL DEFAULT 0,
    est_total_slots     SMALLINT    NOT NULL DEFAULT 0,

    -- ── UI display tags (array of short labels) ───────────────────────────────
    -- Computed by _compute_display_tags() in build_archetype_scores.py.
    -- Examples: ["Rocky-Ice", "Pristine", "Low Contamination", "T3 Friendly",
    --            "2× ELW", "Black Hole", "34 Slots"]
    -- Max 8 tags per system.
    display_tags        TEXT[]      NOT NULL DEFAULT '{}',

    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE system_archetype_traits IS
    'Fast-filter trait flags and counts for the archetype API. '
    'Denormalised from body data and system_slot_topology for O(1) '
    'filter operations without joins. Populated by build_archetype_scores.py.';

COMMENT ON COLUMN system_archetype_traits.display_tags IS
    'Human-readable tag array for UI display. Max 8 tags. '
    'Examples: ["Rocky-Ice", "Pristine", "2× ELW", "34 Slots", '
    '"Low Contamination", "T3 Friendly", "Black Hole"]. '
    'Computed by _compute_display_tags() in build_archetype_scores.py.';

COMMENT ON COLUMN system_archetype_traits.est_total_slots IS
    'Denormalised copy of system_slot_topology.estimated_total_slots. '
    'Updated whenever build_topology.py writes a new topology row.';

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- GIN index on display_tags for tag-based filtering
CREATE INDEX IF NOT EXISTS idx_traits_display_tags
    ON system_archetype_traits USING gin(display_tags);

-- ELW filter (most common prestige query)
CREATE INDEX IF NOT EXISTS idx_traits_elw
    ON system_archetype_traits (elw_count DESC)
    WHERE has_elw = TRUE;

-- Slot count filter
CREATE INDEX IF NOT EXISTS idx_traits_slots
    ON system_archetype_traits (est_total_slots DESC)
    WHERE est_total_slots >= 20;

-- Exotic body fast filter (black hole / neutron used in AX / HighTech queries)
CREATE INDEX IF NOT EXISTS idx_traits_exotic
    ON system_archetype_traits (has_black_hole, has_neutron_star)
    WHERE has_black_hole = TRUE OR has_neutron_star = TRUE;

-- Multi-column filter index (most common combined filter pattern)
CREATE INDEX IF NOT EXISTS idx_traits_filter
    ON system_archetype_traits (has_elw, landable_count DESC, est_total_slots DESC);

-- Terraformable systems filter
CREATE INDEX IF NOT EXISTS idx_traits_terra
    ON system_archetype_traits (terraformable_count DESC)
    WHERE has_terraformables = TRUE;
