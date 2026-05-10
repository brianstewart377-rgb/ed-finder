-- =============================================================================
-- ED Finder — Migration 012: Topology Tables
-- Phase 1 of the Colonisation Engine Redesign (v4.0)
--
-- Creates:
--   • colony_archetype   enum
--   • build_complexity   enum
--   • system_slot_topology     table
--   • economy_pair_synergy     table
--   • pair_synergy_constants   table  (+ seed data)
--
-- Design principles:
--   • Purely additive — no existing tables touched.
--   • All slot counts are ESTIMATES inferred from body physics.
--     Frontier does not expose actual slot counts via any public API.
--   • JSONB fields for topology traits absorb future mechanic changes
--     without requiring schema migrations.
--
-- Run after: 011_autocomplete_index.sql
-- Run before: 013_archetype_scores.sql
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- New enum: colonisation archetype
-- ─────────────────────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE colony_archetype AS ENUM (
        'refinery_industrial',      -- Rocky + Icy megacomplex
        'extraction_refinery',      -- Mining hub, metal-rich focus
        'agriculture_terraforming', -- Farming + terraforming colony
        'hitech_tourism',           -- Prestige, ELW/exotic stars
        'expansion_capital',        -- Strategic expansion node
        'trade_logistics',          -- Trade hub + carrier support
        'population_capital',       -- Maximum population growth
        'ax_forward_base',          -- Anti-xeno military forward base
        'military_industrial',      -- Military + Industrial complex
        'flexible_multirole',       -- High diversity, no dominant archetype
        'unknown'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- New enum: build complexity
-- ─────────────────────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE build_complexity AS ENUM (
        'trivial',      -- Simple single-economy build
        'simple',       -- Clean pair, no sequencing issues
        'moderate',     -- Some contamination management required
        'advanced',     -- Nested ports / tight sequencing
        'expert'        -- Multi-phase, requires deep game knowledge
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Table: system_slot_topology
--
-- Inferred slot topology per system. Populated by build_topology.py.
-- Slot counts are ESTIMATES — not authoritative.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_slot_topology (
    system_id64             BIGINT      PRIMARY KEY REFERENCES systems(id64),

    -- ── Estimated slot counts (inferred, not authoritative) ──────────────────
    estimated_orbital_slots     SMALLINT    NOT NULL DEFAULT 0,
    estimated_ground_slots      SMALLINT    NOT NULL DEFAULT 0,
    estimated_total_slots       SMALLINT    NOT NULL DEFAULT 0,

    -- ── Slot quality (distance-weighted, type-weighted) ──────────────────────
    orbital_slot_quality        REAL        NOT NULL DEFAULT 0,   -- 0-100
    ground_slot_quality         REAL        NOT NULL DEFAULT 0,   -- 0-100
    slot_density_score          REAL        NOT NULL DEFAULT 0,   -- 0-100: quality ÷ distance

    -- ── Per-body slot estimates (JSONB array) ─────────────────────────────────
    -- Each element: {body_id, body_name, body_type, distance_ls,
    --                est_orbital, est_ground, local_group_id, parent_body_id}
    body_slots                  JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- ── Local body groupings ──────────────────────────────────────────────────
    -- Groupings derived from Spansh parents[] array.
    -- Each element: {group_id, anchor_body_id, anchor_name,
    --                member_body_ids[], group_orbital_slots, group_ground_slots}
    local_body_groups           JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- ── Topology metrics (all 0-100) ──────────────────────────────────────────
    strong_link_potential       REAL        NOT NULL DEFAULT 0,
    weak_link_stability         REAL        NOT NULL DEFAULT 0,
    nesting_potential           REAL        NOT NULL DEFAULT 0,
    orbital_synergy             REAL        NOT NULL DEFAULT 0,
    ground_synergy              REAL        NOT NULL DEFAULT 0,
    build_flexibility           REAL        NOT NULL DEFAULT 0,
    contamination_risk          REAL        NOT NULL DEFAULT 0,   -- higher = worse

    -- ── Topology flags (fast filter support) ─────────────────────────────────
    has_viable_surface_port     BOOLEAN     NOT NULL DEFAULT FALSE,  -- ≥1 landable Rocky/HMC
    has_deep_orbital_anchor     BOOLEAN     NOT NULL DEFAULT FALSE,  -- body with ≥6 orbital slots
    has_ringed_gas_giant        BOOLEAN     NOT NULL DEFAULT FALSE,
    has_binary_or_trinary       BOOLEAN     NOT NULL DEFAULT FALSE,  -- multiple stars

    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE system_slot_topology IS
    'Inferred slot topology per system. Slot counts are ESTIMATES derived from '
    'body physics (radius, gravity, body_type, is_landable, ring presence). '
    'They are not authoritative — Frontier does not expose actual slot counts '
    'via any public API or data feed. '
    'Recomputed by build_topology.py whenever a system is flagged dirty.';

COMMENT ON COLUMN system_slot_topology.estimated_orbital_slots IS
    'Sum of estimated orbital slots across all bodies in the system. INFERRED.';
COMMENT ON COLUMN system_slot_topology.estimated_ground_slots IS
    'Sum of estimated ground slots across all landable bodies. INFERRED.';
COMMENT ON COLUMN system_slot_topology.body_slots IS
    'Per-body slot breakdown. Array of {body_id, body_name, body_type, '
    'distance_ls, est_orbital, est_ground, local_group_id, parent_body_id}.';
COMMENT ON COLUMN system_slot_topology.contamination_risk IS
    '0-100. Higher values indicate greater risk of unwanted third economies '
    'entering the top-2 from body-type economy contributions.';

-- Indexes for topology-filtered queries
CREATE INDEX IF NOT EXISTS idx_topo_contamination
    ON system_slot_topology (contamination_risk ASC)
    WHERE contamination_risk < 0.30;

CREATE INDEX IF NOT EXISTS idx_topo_orbital_slots
    ON system_slot_topology (estimated_orbital_slots DESC)
    WHERE estimated_orbital_slots >= 20;

CREATE INDEX IF NOT EXISTS idx_topo_ground_slots
    ON system_slot_topology (estimated_ground_slots DESC)
    WHERE estimated_ground_slots >= 10;

CREATE INDEX IF NOT EXISTS idx_topo_surface_port
    ON system_slot_topology (has_viable_surface_port)
    WHERE has_viable_surface_port = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Table: economy_pair_synergy
--
-- Per-system precomputed economy pair synergy scores.
-- Populated by build_topology.py after slot topology is computed.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS economy_pair_synergy (
    system_id64         BIGINT          NOT NULL REFERENCES systems(id64),
    economy_a           economy_type    NOT NULL,
    economy_b           economy_type    NOT NULL,
    synergy_score       REAL            NOT NULL,   -- 0-100
    purity_achievable   REAL            NOT NULL DEFAULT 0,  -- 0-1
    -- [{body, economy_added, severity, count}] — up to 5 contamination paths
    contamination_paths JSONB           NOT NULL DEFAULT '[]'::jsonb,
    notes               TEXT,

    PRIMARY KEY (system_id64, economy_a, economy_b)
);

COMMENT ON TABLE economy_pair_synergy IS
    'Per-system precomputed economy pair synergy scores. '
    'Derived by applying PAIR_MODIFIERS body-count adjustments to the '
    'global pair_synergy_constants baseline. Populated by build_topology.py.';

CREATE INDEX IF NOT EXISTS idx_pair_synergy_system
    ON economy_pair_synergy (system_id64);

CREATE INDEX IF NOT EXISTS idx_pair_synergy_score
    ON economy_pair_synergy (economy_a, economy_b, synergy_score DESC)
    WHERE synergy_score >= 60;

-- ─────────────────────────────────────────────────────────────────────────────
-- Table: pair_synergy_constants
--
-- Global baseline synergy values for each economy pair.
-- These are system-independent constants seeded from ED mechanics research.
-- Per-system synergy (economy_pair_synergy) starts from these and applies
-- body-count modifiers on top.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pair_synergy_constants (
    economy_a           economy_type    NOT NULL,
    economy_b           economy_type    NOT NULL,
    base_synergy        REAL            NOT NULL CHECK (base_synergy BETWEEN 0 AND 1),
    contamination_risk  REAL            NOT NULL CHECK (contamination_risk BETWEEN 0 AND 1),
    notes               TEXT,

    PRIMARY KEY (economy_a, economy_b)
);

COMMENT ON TABLE pair_synergy_constants IS
    'Global baseline economy pair synergy constants. '
    'Values derived from ED Trailblazers colonisation mechanics research '
    '(2025). These are the system-independent starting point; '
    'build_topology.py applies per-system body-count modifiers on top. '
    'Can be updated without code changes to tune pair scoring.';

COMMENT ON COLUMN pair_synergy_constants.base_synergy IS
    '0-1. How well this pair works together in a clean system. '
    '1.0 = perfect synergy, 0.0 = fundamentally incompatible.';
COMMENT ON COLUMN pair_synergy_constants.contamination_risk IS
    '0-1. Baseline probability that this pair suffers third-economy '
    'contamination in a typical system.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: pair_synergy_constants
--
-- Values based on ED colonisation mechanics (Trailblazers Update 3, 2025).
-- Pairs are stored in canonical order (lexicographic on economy name).
-- The application layer must look up both (A,B) and (B,A) orderings.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO pair_synergy_constants
    (economy_a, economy_b, base_synergy, contamination_risk, notes)
VALUES
    -- Tier S: near-perfect synergy pairs
    ('Refinery',     'Industrial',  0.95, 0.12,
        'Rocky-Ice bodies serve both economies; very clean stacking. '
        'CMM Composite production enabled.'),

    ('Agriculture',  'Tourism',     0.91, 0.08,
        'ELW and Water Worlds serve both. ELW strong link is excellent for both. '
        'Low contamination from competing body types.'),

    -- Tier A: strong synergy pairs
    ('HighTech',     'Tourism',     0.88, 0.15,
        'Gas Giants and exotic star systems serve both. '
        'Ammonia Worlds are excellent dual-contributors.'),

    ('Extraction',   'Refinery',    0.82, 0.22,
        'HMC bodies host both Extraction and Refinery hubs. '
        'Geo signals on HMC are useful; Rocky geo signals risk contamination.'),

    ('Agriculture',  'HighTech',    0.79, 0.18,
        'ELW anchors both economies. Bio signals support Agriculture. '
        'Tidal-lock bodies weaken Agriculture strong links.'),

    -- Tier B: moderate synergy pairs
    ('HighTech',     'Military',    0.76, 0.20,
        'ELW serves both Military and HighTech. '
        'Gas Giants add HighTech but not Military directly.'),

    ('Industrial',   'Military',    0.74, 0.18,
        'Icy bodies and military settlements are compatible. '
        'Rocky-Ice provides Industrial support without heavy contamination.'),

    ('Refinery',     'Military',    0.58, 0.30,
        'Moderate synergy. Rocky bodies help Refinery; less Military support. '
        'Requires careful hub placement to maintain clean economies.'),

    ('Extraction',   'Industrial',  0.55, 0.35,
        'HMC geo contamination can cause Extraction vs Industrial tension. '
        'Manageable with dedicated Refinery Hubs.'),

    -- Tier C/D: poor or incompatible pairs
    ('Agriculture',  'Refinery',    0.28, 0.72,
        'Competing economies. Bio bodies heavily contaminate Refinery. '
        'Avoid unless deliberate multi-economy build.'),

    ('Tourism',      'Refinery',    0.22, 0.78,
        'Very poor pairing. ELW/exotic body economies fight Refinery '
        'for the top-2 slots. Near-impossible to maintain clean stack.'),

    ('Agriculture',  'Extraction',  0.35, 0.60,
        'Bio signals compete with geo signals. Moderate contamination risk. '
        'Avoid unless system has very distinct body populations.'),

    ('Tourism',      'Military',    0.45, 0.45,
        'Moderate conflict. Tourism favours prestige/exotic; '
        'Military favours settlement coverage. Some ELW overlap.'),

    ('Tourism',      'Industrial',  0.40, 0.50,
        'Industrial economy from Icy bodies conflicts with Tourism aesthetic. '
        'Gas Giants help both but overall mix is unstable.'),

    ('Agriculture',  'Military',    0.38, 0.55,
        'Bio signals from Agriculture bodies add competing economies. '
        'Limited shared body type support.')

ON CONFLICT (economy_a, economy_b) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema version marker
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON SCHEMA public IS
    'ED Finder schema — migration 012 applied (topology tables + pair synergy constants).';
