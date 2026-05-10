-- =============================================================================
-- ED Finder — Migration 015: Colonisation Simulation Engine
-- Phase 2 of the Colonisation Engine Redesign (v4.0)
--
-- Creates:
--   • journal_events          raw EDDN event store
--   • body_scan_facts         normalised per-body observed facts
--   • body_slot_predictions   per-body slot predictions with confidence
--   • buildability_analysis   per-system buildability summary
--   • facility_templates      canonical facility rule catalogue
--   • colony_simulations      versioned simulation results
--
-- Design principles:
--   • Purely additive — no existing tables touched.
--   • Separation of concerns:
--       raw facts → observed facts → predicted values → simulation outputs
--   • All derived values are versionable and recalculatable from raw facts.
--   • JSONB for structured sub-data; typed columns for filterable scalars.
--   • Confidence propagated at every layer (observed > predicted > derived).
--
-- Run after: 014_archetype_mv.sql
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Table: journal_events
-- Raw event store for EDDN-derived journal entries.
-- Never mutate — append-only. Normalisation happens in body_scan_facts.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS journal_events (
    id               BIGSERIAL PRIMARY KEY,
    system_address   BIGINT,
    system_name      TEXT,
    body_id          INTEGER,
    body_name        TEXT,
    event_type       TEXT        NOT NULL,
    event_timestamp  TIMESTAMPTZ,
    source           TEXT        NOT NULL,   -- 'eddn', 'journal_upload', 'manual'
    raw_event        JSONB       NOT NULL,
    received_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_journal_events_system_address
    ON journal_events (system_address)
    WHERE system_address IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_journal_events_body_id
    ON journal_events (body_id)
    WHERE body_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_journal_events_event_type
    ON journal_events (event_type);

CREATE INDEX IF NOT EXISTS idx_journal_events_received_at
    ON journal_events (received_at DESC);

CREATE INDEX IF NOT EXISTS idx_journal_events_raw_gin
    ON journal_events USING GIN (raw_event);

COMMENT ON TABLE journal_events IS
    'Append-only store of raw EDDN / journal events. '
    'Never mutate rows — re-normalise by inserting into body_scan_facts. '
    'Pruning policy: keep 90 days of non-Scan events; Scan events kept indefinitely.';


-- ---------------------------------------------------------------------------
-- Table: body_scan_facts
-- Normalised observed facts per body, derived from journal_events.
-- PK is (system_address, body_id) — matches journal event addressing.
-- Updated in place as new scan events arrive; data_sources tracks provenance.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS body_scan_facts (
    system_address   BIGINT      NOT NULL,
    body_id          INTEGER     NOT NULL,

    -- Identity (denormalised from event for query convenience)
    body_name        TEXT,

    -- Physical properties (from Scan event)
    radius           DOUBLE PRECISION,
    mass_em          DOUBLE PRECISION,   -- Earth masses
    gravity          DOUBLE PRECISION,   -- g
    surface_temp     DOUBLE PRECISION,   -- K
    surface_pressure DOUBLE PRECISION,   -- atm

    -- Classification
    planet_class     TEXT,
    terraform_state  TEXT,   -- 'Terraformable', 'Terraformed', 'None', ''
    atmosphere       TEXT,
    volcanism        TEXT,

    -- Orbital (useful for port-placement reasoning)
    semi_major_axis  DOUBLE PRECISION,   -- AU
    orbital_period   DOUBLE PRECISION,   -- days
    parents          JSONB,              -- [{Star:0}, {Planet:2}] etc.

    -- Signal counts (from Scan + SAASignalsFound)
    has_geo          BOOLEAN     DEFAULT FALSE,
    has_bio          BOOLEAN     DEFAULT FALSE,
    geo_signal_count INTEGER     DEFAULT 0,
    bio_signal_count INTEGER     DEFAULT 0,

    -- Derived flags
    is_landable      BOOLEAN     DEFAULT FALSE,
    is_terraformable BOOLEAN     DEFAULT FALSE,
    is_ringed        BOOLEAN     DEFAULT FALSE,

    -- Provenance
    data_sources     TEXT[]      DEFAULT '{}',   -- ['eddn_scan', 'eddn_saasignals']
    confidence       NUMERIC(4,3) DEFAULT 0.0,   -- 0.0–1.0

    updated_at       TIMESTAMPTZ DEFAULT now(),

    PRIMARY KEY (system_address, body_id)
);

CREATE INDEX IF NOT EXISTS idx_body_scan_facts_planet_class
    ON body_scan_facts (planet_class)
    WHERE planet_class IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_body_scan_facts_terraform_state
    ON body_scan_facts (terraform_state)
    WHERE terraform_state IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_body_scan_facts_updated_at
    ON body_scan_facts (updated_at DESC);

COMMENT ON TABLE body_scan_facts IS
    'Normalised per-body observed facts. Derived from journal_events. '
    'confidence reflects data completeness: 1.0 = full DSS scan, '
    '0.7 = FSS-only, 0.4 = estimated from system data.';


-- ---------------------------------------------------------------------------
-- Table: body_slot_predictions
-- Per-body slot count predictions, with confidence and explainability.
-- Recalculated by slot_prediction.py whenever body_scan_facts changes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS body_slot_predictions (
    system_address          BIGINT      NOT NULL,
    body_id                 INTEGER     NOT NULL,

    -- Predicted slot counts
    estimated_surface_slots INTEGER     DEFAULT 0,
    estimated_orbital_slots INTEGER     DEFAULT 0,

    -- Confidence + source
    slot_confidence         NUMERIC(4,3) DEFAULT 0.0,
    slot_source             TEXT        DEFAULT 'predicted',
    -- slot_source values:
    --   'confirmed'   — player-confirmed in-game
    --   'journal'     — derived from full DSS scan data
    --   'predicted'   — model estimate from radius/class/etc.
    --   'estimated'   — rough estimate, minimal data

    -- Explainability: why these numbers?
    reasons                 JSONB       DEFAULT '[]',
    -- e.g. [{"factor": "radius", "value": 4200, "contribution": "+2 surface"},
    --        {"factor": "ringed", "value": true, "contribution": "+1 orbital"}]

    calculated_at           TIMESTAMPTZ DEFAULT now(),

    PRIMARY KEY (system_address, body_id)
);

CREATE INDEX IF NOT EXISTS idx_body_slot_predictions_confidence
    ON body_slot_predictions (slot_confidence DESC);

COMMENT ON TABLE body_slot_predictions IS
    'Per-body slot predictions. Recalculated from body_scan_facts. '
    'reasons JSONB is the explainability chain — every factor that '
    'contributed to the prediction is recorded with its contribution.';


-- ---------------------------------------------------------------------------
-- Table: buildability_analysis
-- System-level buildability summary, aggregated from body_slot_predictions.
-- One row per system. Recalculated whenever slot predictions change.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS buildability_analysis (
    system_id64                 BIGINT      PRIMARY KEY,

    -- Slot totals
    estimated_orbital_slots     INTEGER     DEFAULT 0,
    estimated_ground_slots      INTEGER     DEFAULT 0,

    -- Overall confidence in the slot estimates
    slot_confidence             NUMERIC(4,3) DEFAULT 0.0,

    -- Construction-point capacity estimates
    -- Yellow CP = standard colonisation CPs (from facilities)
    -- Green CP  = bonus CPs (from specific facility combos)
    estimated_yellow_cp_capacity INTEGER    DEFAULT 0,
    estimated_green_cp_capacity  INTEGER    DEFAULT 0,

    -- Port capacity
    max_t2_ports_estimate       INTEGER     DEFAULT 0,
    max_t3_ports_estimate       INTEGER     DEFAULT 0,

    -- Composite risk/quality scores (0–100)
    cp_bottleneck_score         NUMERIC(5,2) DEFAULT 0,
    -- High = CP will be the limiting factor, not slots
    slot_exhaustion_risk        NUMERIC(5,2) DEFAULT 0,
    -- High = likely to run out of slots before finishing the build
    build_order_sensitivity     NUMERIC(5,2) DEFAULT 0,
    -- High = order of placement matters a lot (contamination risk)

    -- Complexity label (mirrors build_complexity enum from 012)
    build_complexity            TEXT        DEFAULT 'unknown',

    -- Structured recommendations
    bottlenecks                 JSONB       DEFAULT '[]',
    -- e.g. [{"type": "slot", "severity": "high", "detail": "Only 4 orbital slots"}]
    opportunities               JSONB       DEFAULT '[]',
    -- e.g. [{"type": "ringed_gas_giant", "detail": "Orbital anchor available"}]
    recommended_build_order     JSONB       DEFAULT '[]',
    -- e.g. [{"step": 1, "facility": "asteroid_base", "reason": "Unlocks T2 orbital"}]

    calculated_at               TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_buildability_slot_confidence
    ON buildability_analysis (slot_confidence DESC);

CREATE INDEX IF NOT EXISTS idx_buildability_complexity
    ON buildability_analysis (build_complexity);

CREATE INDEX IF NOT EXISTS idx_buildability_orbital_slots
    ON buildability_analysis (estimated_orbital_slots DESC);

COMMENT ON TABLE buildability_analysis IS
    'System-level buildability summary. Aggregates body_slot_predictions '
    'into CP capacity, port estimates, complexity labelling, and '
    'actionable build-order recommendations.';


-- ---------------------------------------------------------------------------
-- Table: facility_templates
-- Canonical catalogue of all buildable facilities.
-- Seeded from known ED colonisation mechanics.
-- Versionable — add new facilities without schema changes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS facility_templates (
    id                  TEXT        PRIMARY KEY,
    -- e.g. 'asteroid_base', 'refinery_t2', 'industrial_complex_t3'

    name                TEXT        NOT NULL,
    -- Human-readable: 'Asteroid Base', 'Refinery (T2)', 'Industrial Complex (T3)'

    -- Classification
    category            TEXT        NOT NULL,
    -- 'port', 'industrial', 'agricultural', 'military', 'support', 'extraction'
    tier                INTEGER     NOT NULL CHECK (tier BETWEEN 1 AND 3),

    -- Economy produced
    economy             TEXT,
    -- NULL = no economy contribution (pure support facilities)

    -- Port flags
    is_port             BOOLEAN     DEFAULT FALSE,
    is_colony_port      BOOLEAN     DEFAULT FALSE,
    -- Colony ports are T1 — placed first to establish the system
    is_support_facility BOOLEAN     DEFAULT FALSE,

    -- CP generation (what this facility contributes to the system)
    yellow_cp_generated INTEGER     DEFAULT 0,
    green_cp_generated  INTEGER     DEFAULT 0,

    -- CP cost (what this facility costs to unlock/place)
    yellow_cp_cost      INTEGER     DEFAULT 0,
    green_cp_cost       INTEGER     DEFAULT 0,

    -- Link values (for economy pair synergy calculations)
    strong_link_value   NUMERIC(5,2) DEFAULT 0,
    weak_link_value     NUMERIC(5,2) DEFAULT 0.05,

    -- Placement constraints
    allowed_location    TEXT        NOT NULL,
    -- 'orbital', 'surface', 'orbital_or_surface', 'ringed_orbital'
    pad_size            TEXT,
    -- 'S', 'M', 'L', NULL (non-port facilities)

    -- Structured rules
    prerequisites       JSONB       DEFAULT '[]',
    -- e.g. [{"facility": "asteroid_base"}, {"min_orbital_slots": 3}]
    economy_effects     JSONB       DEFAULT '{}',
    -- e.g. {"primary": "Refinery", "secondary_boost": 0.15}
    stat_effects        JSONB       DEFAULT '{}'
    -- e.g. {"population_cap_modifier": 1.2, "security_modifier": 0.1}
);

CREATE INDEX IF NOT EXISTS idx_facility_templates_category
    ON facility_templates (category);

CREATE INDEX IF NOT EXISTS idx_facility_templates_tier
    ON facility_templates (tier);

CREATE INDEX IF NOT EXISTS idx_facility_templates_economy
    ON facility_templates (economy)
    WHERE economy IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_facility_templates_is_port
    ON facility_templates (is_port)
    WHERE is_port = TRUE;

COMMENT ON TABLE facility_templates IS
    'Canonical facility catalogue. One row per buildable facility type. '
    'Seeded with known ED colonisation mechanics. Extend by INSERT — '
    'no schema changes needed for new facility types. '
    'IMPORTANT: slot costs / CP values here are ESTIMATED from observed '
    'colonisation behaviour. Mark uncertain values with a note in stat_effects.';


-- ---------------------------------------------------------------------------
-- Table: colony_simulations
-- Versioned simulation results for a given system + archetype combination.
-- Multiple rows per system (different archetypes, different versions).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS colony_simulations (
    id                   BIGSERIAL   PRIMARY KEY,

    system_id64          BIGINT      NOT NULL,
    archetype            TEXT,
    -- NULL = auto-selected best archetype from system_archetype_scores

    -- Version tag — increment when simulation logic changes so old results
    -- are identifiable and can be batch-recalculated.
    simulation_version   TEXT        NOT NULL,
    -- e.g. '1.0.0', '1.1.0-beta'

    -- The planned build
    build_order          JSONB       NOT NULL,
    -- Array of placement steps:
    -- [{"step": 1, "facility_id": "colony_ship", "location": "orbital",
    --   "economy_effect": "Colony", "cp_delta": {"yellow": 0, "green": 0}}]

    -- Projected outcomes after build completion
    projected_cp         JSONB       DEFAULT '{}',
    -- {"yellow_total": 120, "green_total": 45, "net_available": 30}
    projected_economies  JSONB       DEFAULT '{}',
    -- {"primary": "Refinery", "primary_pct": 0.42, "secondary": "Industrial",
    --  "secondary_pct": 0.38, "composition_quality": 0.81}
    projected_links      JSONB       DEFAULT '{}',
    -- {"strong_links": 3, "weak_links": 8, "dominant_pair": ["Refinery","Industrial"]}

    -- Composite scores (0–100)
    buildability_score   NUMERIC(5,2),
    composition_score    NUMERIC(5,2),
    final_score          NUMERIC(5,2),

    -- Issues and guidance
    warnings             JSONB       DEFAULT '[]',
    -- e.g. [{"severity": "high", "message": "T3 port requires 6 orbital slots — only 4 available"}]
    recommendations      JSONB       DEFAULT '[]',
    -- e.g. [{"priority": 1, "action": "Place Refinery T2 before Industrial T2 to lock economy order"}]

    created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_colony_simulations_system
    ON colony_simulations (system_id64);

CREATE INDEX IF NOT EXISTS idx_colony_simulations_archetype
    ON colony_simulations (archetype)
    WHERE archetype IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_colony_simulations_version
    ON colony_simulations (simulation_version);

CREATE INDEX IF NOT EXISTS idx_colony_simulations_final_score
    ON colony_simulations (system_id64, final_score DESC);

COMMENT ON TABLE colony_simulations IS
    'Versioned colony simulation outputs. Multiple rows per system. '
    'simulation_version allows old results to coexist with new logic '
    'during re-calculation runs. Query latest with: '
    'ORDER BY created_at DESC LIMIT 1 per system_id64+archetype.';


-- ---------------------------------------------------------------------------
-- Seed data: facility_templates
-- Initial seeding of known ED colonisation facilities.
-- These values are best-effort from community observation — mark uncertain.
-- See stat_effects->>"data_confidence" for per-facility confidence notes.
-- ---------------------------------------------------------------------------

INSERT INTO facility_templates (
    id, name, category, tier, economy,
    is_port, is_colony_port, is_support_facility,
    yellow_cp_generated, green_cp_generated,
    yellow_cp_cost, green_cp_cost,
    strong_link_value, weak_link_value,
    allowed_location, pad_size,
    prerequisites, economy_effects, stat_effects
) VALUES

-- ── Colony ports (T1, placed first) ──────────────────────────────────────
('colony_ship',
 'Colony Ship', 'port', 1, 'Colony',
 TRUE, TRUE, FALSE,
 0, 0, 0, 0, 0, 0,
 'orbital', 'L',
 '[]', '{"primary": "Colony"}',
 '{"note": "Starting facility, always placed first", "data_confidence": "confirmed"}'),

('settlement_agricultural',
 'Agricultural Settlement', 'port', 1, 'Agriculture',
 TRUE, TRUE, FALSE,
 4, 0, 0, 0, 1.0, 0.1,
 'surface', 'M',
 '[]', '{"primary": "Agriculture"}',
 '{"data_confidence": "observed"}'),

('settlement_industrial',
 'Industrial Settlement', 'port', 1, 'Industrial',
 TRUE, TRUE, FALSE,
 4, 0, 0, 0, 1.0, 0.1,
 'surface', 'M',
 '[]', '{"primary": "Industrial"}',
 '{"data_confidence": "observed"}'),

('settlement_extraction',
 'Extraction Settlement', 'port', 1, 'Extraction',
 TRUE, TRUE, FALSE,
 4, 0, 0, 0, 1.0, 0.1,
 'surface', 'M',
 '[]', '{"primary": "Extraction"}',
 '{"data_confidence": "observed"}'),

('settlement_military',
 'Military Settlement', 'port', 1, 'Military',
 TRUE, TRUE, FALSE,
 4, 0, 0, 0, 1.0, 0.1,
 'surface', 'M',
 '[]', '{"primary": "Military"}',
 '{"data_confidence": "observed"}'),

-- ── T2 orbital ports ──────────────────────────────────────────────────────
('asteroid_base',
 'Asteroid Base', 'port', 2, 'Extraction',
 TRUE, FALSE, FALSE,
 8, 2, 16, 0, 2.0, 0.2,
 'ringed_orbital', 'L',
 '[{"min_orbital_slots": 1}, {"requires_ringed_body": true}]',
 '{"primary": "Extraction", "note": "Requires ringed body in system"}',
 '{"data_confidence": "observed"}'),

('orbis_station',
 'Orbis Station', 'port', 2, NULL,
 TRUE, FALSE, FALSE,
 10, 3, 20, 0, 2.5, 0.3,
 'orbital', 'L',
 '[{"min_orbital_slots": 2}]',
 '{"primary": null, "note": "Economy set by supporting facilities"}',
 '{"data_confidence": "observed"}'),

('coriolis_station',
 'Coriolis Station', 'port', 2, NULL,
 TRUE, FALSE, FALSE,
 8, 2, 16, 0, 2.0, 0.2,
 'orbital', 'L',
 '[{"min_orbital_slots": 1}]',
 '{"primary": null, "note": "Economy set by supporting facilities"}',
 '{"data_confidence": "observed"}'),

('ocellus_station',
 'Ocellus Station', 'port', 2, NULL,
 TRUE, FALSE, FALSE,
 8, 2, 16, 0, 2.0, 0.2,
 'orbital', 'L',
 '[{"min_orbital_slots": 1}]',
 '{"primary": null, "note": "Economy set by supporting facilities"}',
 '{"data_confidence": "observed"}'),

-- ── T2 surface ports ──────────────────────────────────────────────────────
('planetary_port',
 'Planetary Port', 'port', 2, NULL,
 TRUE, FALSE, FALSE,
 8, 2, 16, 0, 2.0, 0.2,
 'surface', 'L',
 '[{"min_ground_slots": 1}]',
 '{"primary": null}',
 '{"data_confidence": "observed"}'),

('planetary_outpost',
 'Planetary Outpost', 'port', 2, NULL,
 TRUE, FALSE, FALSE,
 6, 1, 12, 0, 1.5, 0.15,
 'surface', 'M',
 '[]',
 '{"primary": null}',
 '{"data_confidence": "observed"}'),

-- ── T3 ports ─────────────────────────────────────────────────────────────
('orbis_t3',
 'Orbis Station (T3)', 'port', 3, NULL,
 TRUE, FALSE, FALSE,
 20, 8, 40, 16, 5.0, 0.5,
 'orbital', 'L',
 '[{"min_orbital_slots": 4}, {"prerequisite_port_tier": 2}]',
 '{"primary": null, "note": "Requires established T2 port network"}',
 '{"data_confidence": "estimated", "note": "T3 CP costs are community estimates"}'),

-- ── Support / industrial facilities ──────────────────────────────────────
('refinery',
 'Refinery', 'industrial', 2, 'Refinery',
 FALSE, FALSE, TRUE,
 3, 1, 6, 0, 1.5, 0.1,
 'orbital_or_surface', NULL,
 '[]',
 '{"primary": "Refinery"}',
 '{"data_confidence": "observed"}'),

('industrial_facility',
 'Industrial Facility', 'industrial', 2, 'Industrial',
 FALSE, FALSE, TRUE,
 3, 1, 6, 0, 1.5, 0.1,
 'orbital_or_surface', NULL,
 '[]',
 '{"primary": "Industrial"}',
 '{"data_confidence": "observed"}'),

('extraction_facility',
 'Extraction Facility', 'extraction', 2, 'Extraction',
 FALSE, FALSE, TRUE,
 2, 0, 4, 0, 1.0, 0.05,
 'orbital_or_surface', NULL,
 '[]',
 '{"primary": "Extraction"}',
 '{"data_confidence": "observed"}'),

('agricultural_facility',
 'Agricultural Facility', 'agricultural', 2, 'Agriculture',
 FALSE, FALSE, TRUE,
 3, 1, 6, 0, 1.5, 0.1,
 'surface', NULL,
 '[]',
 '{"primary": "Agriculture"}',
 '{"data_confidence": "observed"}'),

('military_installation',
 'Military Installation', 'military', 2, 'Military',
 FALSE, FALSE, TRUE,
 3, 0, 6, 0, 1.0, 0.05,
 'orbital_or_surface', NULL,
 '[]',
 '{"primary": "Military"}',
 '{"data_confidence": "observed"}'),

('hightech_research',
 'High Tech Research', 'support', 2, 'HighTech',
 FALSE, FALSE, TRUE,
 4, 2, 8, 4, 2.0, 0.2,
 'orbital_or_surface', NULL,
 '[]',
 '{"primary": "HighTech"}',
 '{"data_confidence": "estimated"}'),

('tourism_installation',
 'Tourism Installation', 'support', 2, 'Tourism',
 FALSE, FALSE, TRUE,
 2, 1, 4, 2, 1.0, 0.1,
 'orbital_or_surface', NULL,
 '[]',
 '{"primary": "Tourism"}',
 '{"data_confidence": "estimated"}')

ON CONFLICT (id) DO UPDATE SET
    name                = EXCLUDED.name,
    yellow_cp_generated = EXCLUDED.yellow_cp_generated,
    green_cp_generated  = EXCLUDED.green_cp_generated,
    yellow_cp_cost      = EXCLUDED.yellow_cp_cost,
    green_cp_cost       = EXCLUDED.green_cp_cost,
    strong_link_value   = EXCLUDED.strong_link_value,
    economy_effects     = EXCLUDED.economy_effects,
    stat_effects        = EXCLUDED.stat_effects;
