# ED-Finder Colonisation Engine Redesign
## Complete Implementation Guide — v4.0

**Date:** 2026-05-10  
**Status:** Design document — approved for phased implementation  
**Scope:** Schema, scoring engine, API, migration, pipeline  

---

## Table of Contents

1. [Data Availability Audit — EDDN & Spansh](#1-data-availability-audit)
2. [Core Philosophy](#2-core-philosophy)
3. [PostgreSQL Schema Design](#3-postgresql-schema-design)
4. [Archetype Scoring Engine](#4-archetype-scoring-engine)
5. [Economy Pair Synergy Model](#5-economy-pair-synergy-model)
6. [Topology & Contamination Modelling](#6-topology--contamination-modelling)
7. [Buildability Scoring](#7-buildability-scoring)
8. [Explainability System](#8-explainability-system)
9. [Async Computation Pipeline](#9-async-computation-pipeline)
10. [API Endpoints](#10-api-endpoints)
11. [Reranking Redesign](#11-reranking-redesign)
12. [Migration Strategy](#12-migration-strategy)
13. [Architecture Diagrams](#13-architecture-diagrams)
14. [Caching Strategy](#14-caching-strategy)
15. [Performance Recommendations](#15-performance-recommendations)
16. [Implementation Phases](#16-implementation-phases)
17. [Risks & Unknowns](#17-risks--unknowns)
18. [Future-Proofing](#18-future-proofing)

---

## 1. Data Availability Audit

### 1.1 Critical Question

> Can EDDN and/or Spansh expose sufficient slot information to support
> per-body orbital/ground slot counts, available vs occupied slot tracking,
> and body-level facility placement?

### 1.2 EDDN — What Is Available

EDDN emits the following schema events relevant to colonisation:

| Schema | What It Provides |
|--------|-----------------|
| `Journal/Scan` | BodyID, BodyName, PlanetClass, Landable, DistanceFromArrivalLS, Radius, SurfaceGravity, TerraformState, Volcanism, bio/geo signals |
| `Journal/FSSDiscoveryScan` | SystemAddress, system-level body count, star class |
| `Journal/SAASignalsFound` | BodyName, Signals[] with Type (Biology/Geology) + Count |
| `Journal/FSDJump` + `Location` | SystemAddress, system economy, population |
| `Journal/Colonisation` | System being colonised flag |

**EDDN does NOT expose:**
- Orbital slot counts per body
- Ground slot counts per body
- Which slots are already occupied by constructions
- Colonisation facility placement data
- Slot topology (local-body groupings)
- Construction state of individual slots

**Verdict:** EDDN provides rich body-physics data (mass, gravity, volcanism, temperature, bio/geo signals, terraform state, landability, distance) but **zero slot topology data**. All slot information must be inferred.

### 1.3 Spansh Galaxy Dump — What Is Available

The Spansh `galaxy.json.gz` dump (already imported by `import_spansh.py`) provides per-body:

| Field | Available? | Notes |
|-------|-----------|-------|
| `subType` | ✅ | Planet class, star type — used for economy inference |
| `isLandable` | ✅ | Ground slot eligibility |
| `distanceToArrival` | ✅ | Ls from primary star |
| `terraformingState` | ✅ | Terraformable / not terraformable |
| `volcanismType` | ✅ | Geo signal proxy |
| `signals.genuses` | ✅ | Bio signal count |
| `signals.geology` | ✅ | Geo signal count |
| `isTerraformingCandidate` | ✅ | |
| `rings` | ✅ | Ring presence / type |
| `orbital_slot_count` | ❌ | Not in Spansh data |
| `ground_slot_count` | ❌ | Not in Spansh data |
| `occupied_orbital_slots` | ❌ | Not in Spansh data |
| `occupied_ground_slots` | ❌ | Not in Spansh data |
| `colonisation_facilities` | ❌ | Not in Spansh data |
| `parent_body_id` | ✅ | Available as `parents[]` array — enables local-body grouping |
| `bodyId` | ✅ | In-system body identifier |

### 1.4 Slot Count Inference Rules

**Official ED colonisation mechanics (Trailblazers, 2025)** establish these slot rules:

```
Ground slots:   Every landable body has ground slots
                Larger bodies (Rocky, HMC) → more ground slots
                Slot count ≈ f(radius, gravity, body_type)

Orbital slots:  Every body has orbital slots
                Stars have more orbital slots than planets
                Gas Giants have more orbital slots than Rocky bodies
                Distance from star affects usability (not slot count)
                Slot count ≈ f(body_type, mass, ring_count)
```

**ED Wiki confirmed formulas (community-derived, not officially published):**

| Body Type | Approx Orbital Slots | Approx Ground Slots |
|-----------|---------------------|---------------------|
| Main Star (large) | 8–12 | 0 |
| Main Star (small) | 4–6 | 0 |
| Secondary Star | 4–8 | 0 |
| Gas Giant (ringed) | 4–6 | 0 |
| Gas Giant (plain) | 2–4 | 0 |
| Rocky Body (large, landable) | 2–4 | 4–8 |
| Rocky Body (small, landable) | 1–2 | 2–4 |
| HMC (landable) | 2–4 | 3–6 |
| Icy Body | 1–3 | 0–2 |
| Rocky Ice | 2–4 | 2–4 |
| ELW | 3–5 | 5–10 |
| Water World | 2–4 | 0 |
| Ammonia World | 2–4 | 0 |

> **Important:** These are approximate ranges. Exact slot counts are displayed
> in Architect Mode in-game. The Frontier API does not expose them externally.
> ED-Finder must **estimate** slot counts from body properties, not read them directly.

### 1.5 Canonical Source of Truth

| Data Type | Best Source | Update Frequency | Reliability |
|-----------|-------------|-----------------|-------------|
| Body physics (type, mass, temp, gravity) | Spansh galaxy dump + EDDN | Nightly dump / real-time EDDN | High |
| Bio/geo signal counts | EDDN SAASignalsFound | Real-time | High |
| Terraform state | Spansh + EDDN Scan | Nightly + real-time | High |
| Estimated orbital slots | **Inferred from body_type + mass** | Computed from body data | Medium |
| Estimated ground slots | **Inferred from is_landable + radius** | Computed from body data | Medium |
| Actual occupied slots | **Not available externally** | N/A | — |
| Parent/local body grouping | Spansh `parents[]` array | Nightly dump | Medium |

### 1.6 Recommendation: Inference Engine, Not Direct Slot Reading

**ED-Finder must build a slot inference engine** that estimates:

1. `estimated_orbital_slots` — from body_type, mass, ring presence
2. `estimated_ground_slots` — from is_landable, radius, gravity, body_type  
3. `estimated_total_slots` — sum across all bodies in system
4. `slot_quality_score` — weighted by body type and distance

This is not a limitation — it is correct. The in-game Architect Mode shows exact slots, but these are not available via any API or data feed. The Spansh colonisation-specific dumps (when they exist) do capture some constructed facility data, but not pre-colonisation slot topology.

---

## 2. Core Philosophy

### 2.1 The Fundamental Shift

**Current ED-Finder asks:**
> "What is the overall best system?"

**New ED-Finder asks:**
> "What kind of colony would this system become — and how well would it become that?"

### 2.2 Three Inviolable Design Laws

**Law 1: Systems are archetypes, not score objects.**  
A Refinery Megacomplex and an ELW Tourism Capital must never share a global leaderboard. They live in different archetype categories. Score them within their category only.

**Law 2: Economy compatibility outweighs economy strength.**  
A system with Refinery=70 + Industrial=68 that pair cleanly scores higher than a system with Refinery=90 that is heavily contaminated by Agriculture and HighTech. Purity is a force multiplier.

**Law 3: Explainability is a first-class feature.**  
Every score must be traceable. Every ranking must be justifiable. A CMDR should be able to read exactly why a system scored the way it did and immediately understand it. The rationale is not a caption — it is part of the product.

### 2.3 Current System Assessment (Honest Audit)

**What works well in v3.1 (keep):**
- `classify_bodies()` contamination logic — excellent foundation
- `_distance_weight()` — smart and defensible
- Complementary pair detection (`COMPLEMENTARY_PAIRS`) — exactly right direction  
- `compute_confidence()` — solid data-freshness model
- `generate_rationale()` with per-economy highlight builders — good architecture, needs expanding
- Per-economy score columns in `ratings` table — already positions us for archetype pivot
- `score_breakdown` JSONB — already stores the right data, just needs richer content
- Dirty-flag architecture — correct async pattern for scale
- Multiprocess worker pool — correct for CPU-bound rating computation

**What needs replacing in v3.1:**
- Single `score` column — becomes `overall_development_potential` (supporting role, not star)
- Generic dimension weights (`economy 0.42, slots 0.23, strategic 0.18`) — becomes archetype scores
- `RerankWeights` model — becomes `ArchetypeWeights` + preset profiles
- `compute_slot_score()` — replace with topology-aware slot model
- `compute_strategic_score()` — split into topology metrics + buildability
- `score` overall formula — replace with archetype-gated overall development potential

---

## 3. PostgreSQL Schema Design

### 3.1 Design Principles

- **Keep PostgreSQL** — the workload (joins, analytical queries, weighted ranking, partial indexes, materialized views) is PostgreSQL's home turf
- **JSONB for flexibility** — traits, explanations, and inferred slot data live in JSONB so Frontier mechanic changes don't require schema migrations
- **Additive migration** — new tables are added alongside existing ones; no DROP TABLE in Phase 1 or 2
- **Precompute aggressively** — nothing is computed at API request time that can be precomputed

### 3.2 New Enum Types

```sql
-- ─────────────────────────────────────────────────────────────────
-- New enum: colonisation archetype
-- ─────────────────────────────────────────────────────────────────
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

-- ─────────────────────────────────────────────────────────────────
-- New enum: build complexity
-- ─────────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE build_complexity AS ENUM (
        'trivial',      -- Simple single-economy build
        'simple',       -- Clean pair, no sequencing issues
        'moderate',     -- Some contamination management required
        'advanced',     -- Nested ports / tight sequencing
        'expert'        -- Multi-phase, requires deep game knowledge
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
```

### 3.3 Table: `system_slot_topology`

Inferred slot topology. Populated by the new `build_topology.py` importer stage.

```sql
CREATE TABLE IF NOT EXISTS system_slot_topology (
    system_id64             BIGINT      PRIMARY KEY REFERENCES systems(id64),

    -- ── Estimated slot counts (inferred, not authoritative) ──────────
    estimated_orbital_slots     SMALLINT    DEFAULT 0,
    estimated_ground_slots      SMALLINT    DEFAULT 0,
    estimated_total_slots       SMALLINT    DEFAULT 0,

    -- ── Slot quality (distance-weighted, type-weighted) ──────────────
    orbital_slot_quality        REAL        DEFAULT 0,  -- 0-100
    ground_slot_quality         REAL        DEFAULT 0,  -- 0-100
    slot_density_score          REAL        DEFAULT 0,  -- 0-100: total quality ÷ distance

    -- ── Per-body slot estimates (JSONB array) ─────────────────────────
    -- [{body_id, body_name, body_type, distance_ls,
    --   est_orbital, est_ground, local_group_id, parent_body_id}]
    body_slots                  JSONB       DEFAULT '[]',

    -- ── Local body groupings ──────────────────────────────────────────
    -- Groupings derived from Spansh parents[] array.
    -- [{group_id, anchor_body_id, anchor_name, member_body_ids[],
    --   group_orbital_slots, group_ground_slots}]
    local_body_groups           JSONB       DEFAULT '[]',

    -- ── Topology metrics ─────────────────────────────────────────────
    strong_link_potential       REAL        DEFAULT 0,  -- 0-100
    weak_link_stability         REAL        DEFAULT 0,  -- 0-100
    nesting_potential           REAL        DEFAULT 0,  -- 0-100
    orbital_synergy             REAL        DEFAULT 0,  -- 0-100
    ground_synergy              REAL        DEFAULT 0,  -- 0-100
    build_flexibility           REAL        DEFAULT 0,  -- 0-100
    contamination_risk          REAL        DEFAULT 0,  -- 0-100 (higher = worse)

    -- ── Topology flags (fast filter support) ─────────────────────────
    has_viable_surface_port     BOOLEAN     DEFAULT FALSE,  -- ≥1 landable Rocky/HMC
    has_deep_orbital_anchor     BOOLEAN     DEFAULT FALSE,  -- body with ≥6 orbital slots
    has_ringed_gas_giant        BOOLEAN     DEFAULT FALSE,
    has_binary_or_trinary       BOOLEAN     DEFAULT FALSE,  -- multiple stars

    updated_at                  TIMESTAMP   DEFAULT NOW()
);

COMMENT ON TABLE system_slot_topology IS
    'Inferred slot topology per system. Slot counts are ESTIMATES derived '
    'from body physics; they are not authoritative (Frontier does not expose '
    'actual slot counts via any public API or data feed). '
    'Recomputed by build_topology.py whenever a system is flagged dirty.';
```

### 3.4 Table: `system_archetype_scores`

The heart of the new engine. Replaces the role of the single `score` column.

```sql
CREATE TABLE IF NOT EXISTS system_archetype_scores (
    system_id64             BIGINT      PRIMARY KEY REFERENCES systems(id64),

    -- ── Primary archetype identification ─────────────────────────────
    primary_archetype       colony_archetype    DEFAULT 'unknown',
    secondary_archetype     colony_archetype    DEFAULT 'unknown',
    archetype_confidence    REAL        DEFAULT 0,  -- 0-1

    -- ── Per-archetype scores (0-100 each) ────────────────────────────
    score_refinery_industrial       REAL    DEFAULT 0,
    score_extraction_refinery       REAL    DEFAULT 0,
    score_agriculture_terraforming  REAL    DEFAULT 0,
    score_hitech_tourism            REAL    DEFAULT 0,
    score_expansion_capital         REAL    DEFAULT 0,
    score_trade_logistics           REAL    DEFAULT 0,
    score_population_capital        REAL    DEFAULT 0,
    score_ax_forward_base           REAL    DEFAULT 0,
    score_military_industrial       REAL    DEFAULT 0,
    score_flexible_multirole        REAL    DEFAULT 0,

    -- ── Composite development potential (supporting metric) ──────────
    overall_development_potential   REAL    DEFAULT 0,  -- 0-100

    -- ── Buildability ─────────────────────────────────────────────────
    buildability_score      REAL        DEFAULT 0,  -- 0-100
    build_complexity        build_complexity    DEFAULT 'moderate',
    cp_efficiency           REAL        DEFAULT 0,  -- 0-100: CP cost per tier
    t3_scaling_viability    REAL        DEFAULT 0,  -- 0-100: ease of T3 builds
    slot_efficiency         REAL        DEFAULT 0,  -- 0-100: slots per economy tier

    -- ── Purity & contamination ────────────────────────────────────────
    purity_score            REAL        DEFAULT 0,  -- 0-100: top-2 economy cleanliness
    contamination_risk      REAL        DEFAULT 0,  -- 0-100: risk of 3rd economy bleed
    stable_top_two_prob     REAL        DEFAULT 0,  -- 0-1: probability of stable top-2

    -- ── Data quality ─────────────────────────────────────────────────
    confidence              REAL        DEFAULT 0.85,

    -- ── Explainability payload (JSONB) ────────────────────────────────
    score_breakdown         JSONB       DEFAULT '{}',
    rationale               JSONB       DEFAULT '{}',  -- structured, not plain text

    updated_at              TIMESTAMP   DEFAULT NOW(),
    dirty                   BOOLEAN     DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_archetype_scores_primary
    ON system_archetype_scores (primary_archetype, score_refinery_industrial DESC)
    WHERE score_refinery_industrial > 0;

CREATE INDEX IF NOT EXISTS idx_archetype_scores_hitech
    ON system_archetype_scores (score_hitech_tourism DESC)
    WHERE score_hitech_tourism >= 40;

CREATE INDEX IF NOT EXISTS idx_archetype_scores_odp
    ON system_archetype_scores (overall_development_potential DESC)
    WHERE overall_development_potential >= 50;

CREATE INDEX IF NOT EXISTS idx_archetype_scores_dirty
    ON system_archetype_scores (dirty)
    WHERE dirty = TRUE;
```

### 3.5 Table: `economy_pair_synergy`

Lookup table for precomputed pair synergy scores. Populated by `build_topology.py`.

```sql
CREATE TABLE IF NOT EXISTS economy_pair_synergy (
    system_id64         BIGINT      NOT NULL REFERENCES systems(id64),
    economy_a           economy_type    NOT NULL,
    economy_b           economy_type    NOT NULL,
    synergy_score       REAL        NOT NULL,   -- 0-100
    purity_achievable   REAL        DEFAULT 0,  -- 0-1: probability top-2 stays clean
    contamination_paths JSONB       DEFAULT '[]',  -- which body types cause contamination
    notes               TEXT,
    PRIMARY KEY (system_id64, economy_a, economy_b)
);

-- Global pair synergy constants table (system-independent baseline)
CREATE TABLE IF NOT EXISTS pair_synergy_constants (
    economy_a           economy_type    NOT NULL,
    economy_b           economy_type    NOT NULL,
    base_synergy        REAL        NOT NULL,  -- 0-1 baseline
    contamination_risk  REAL        NOT NULL,  -- 0-1 baseline risk
    notes               TEXT,
    PRIMARY KEY (economy_a, economy_b)
);

-- Seed with ED-accurate base values
INSERT INTO pair_synergy_constants (economy_a, economy_b, base_synergy, contamination_risk, notes)
VALUES
    ('Refinery',    'Industrial',   0.95, 0.12, 'Rocky-Ice bodies serve both; very clean'),
    ('Agriculture', 'Tourism',      0.91, 0.08, 'ELW/WW serve both; ELW strong link excellent'),
    ('HighTech',    'Tourism',      0.88, 0.15, 'Gas Giants + exotics serve both'),
    ('Extraction',  'Refinery',     0.82, 0.22, 'HMC serves both; Geo signals needed for Ext'),
    ('Agriculture', 'HighTech',     0.79, 0.18, 'ELW anchors both; bio signals useful'),
    ('HighTech',    'Military',     0.76, 0.20, 'ELW serves both; GG adds HT, not Mil directly'),
    ('Industrial',  'Military',     0.74, 0.18, 'Icy bodies + military settlements compatible'),
    ('Refinery',    'Military',     0.58, 0.30, 'Moderate: Rocky bodies help Refinery, less Military'),
    ('Extraction',  'Industrial',   0.55, 0.35, 'HMC geo contamination can cause issues'),
    ('Agriculture', 'Refinery',     0.28, 0.72, 'Competing: bio bodies contaminate Refinery heavily'),
    ('Tourism',     'Refinery',     0.22, 0.78, 'Very poor: ELW/exotic economies fight Refinery')
ON CONFLICT (economy_a, economy_b) DO NOTHING;
```

### 3.6 Table: `system_archetype_traits`

Fast-filter tags and human-readable trait labels. Replaces current body-count columns in ratings.

```sql
CREATE TABLE IF NOT EXISTS system_archetype_traits (
    system_id64         BIGINT      PRIMARY KEY REFERENCES systems(id64),

    -- ── Boolean fast-filter flags ─────────────────────────────────────
    has_elw             BOOLEAN     DEFAULT FALSE,
    has_water_world     BOOLEAN     DEFAULT FALSE,
    has_ammonia_world   BOOLEAN     DEFAULT FALSE,
    has_black_hole      BOOLEAN     DEFAULT FALSE,
    has_neutron_star    BOOLEAN     DEFAULT FALSE,
    has_white_dwarf     BOOLEAN     DEFAULT FALSE,
    has_ringed_body     BOOLEAN     DEFAULT FALSE,
    has_terraformables  BOOLEAN     DEFAULT FALSE,
    has_pristine_res    BOOLEAN     DEFAULT FALSE,  -- reserve_level in system
    has_bio_signals     BOOLEAN     DEFAULT FALSE,
    has_geo_signals     BOOLEAN     DEFAULT FALSE,
    is_scoopable_star   BOOLEAN     DEFAULT FALSE,

    -- ── Counts ───────────────────────────────────────────────────────
    elw_count           SMALLINT    DEFAULT 0,
    ww_count            SMALLINT    DEFAULT 0,
    ammonia_count       SMALLINT    DEFAULT 0,
    gas_giant_count     SMALLINT    DEFAULT 0,
    rocky_clean_count   SMALLINT    DEFAULT 0,
    rocky_ice_count     SMALLINT    DEFAULT 0,
    icy_count           SMALLINT    DEFAULT 0,
    hmc_count           SMALLINT    DEFAULT 0,
    metal_rich_count    SMALLINT    DEFAULT 0,
    landable_count      SMALLINT    DEFAULT 0,
    terraformable_count SMALLINT    DEFAULT 0,
    bio_signal_total    SMALLINT    DEFAULT 0,
    geo_signal_total    SMALLINT    DEFAULT 0,
    total_body_count    SMALLINT    DEFAULT 0,

    -- ── Slot estimates (denormalised from system_slot_topology) ───────
    est_orbital_slots   SMALLINT    DEFAULT 0,
    est_ground_slots    SMALLINT    DEFAULT 0,
    est_total_slots     SMALLINT    DEFAULT 0,

    -- ── UI tag array (fast display, no join needed) ───────────────────
    -- e.g. ["Rocky-Ice", "Pristine", "Low Contamination", "T3 Friendly"]
    display_tags        TEXT[]      DEFAULT '{}',

    updated_at          TIMESTAMP   DEFAULT NOW()
);

-- GIN index for tag-based filtering
CREATE INDEX IF NOT EXISTS idx_traits_display_tags
    ON system_archetype_traits USING gin(display_tags);

CREATE INDEX IF NOT EXISTS idx_traits_elw
    ON system_archetype_traits (elw_count DESC)
    WHERE has_elw = TRUE;

CREATE INDEX IF NOT EXISTS idx_traits_slots
    ON system_archetype_traits (est_total_slots DESC)
    WHERE est_total_slots >= 20;
```

### 3.7 Materialized View: `mv_archetype_rankings`

Pre-sorted rankings per archetype. Refreshed after each `build_archetype_scores.py` run.

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_archetype_rankings AS
SELECT
    s.id64,
    s.name,
    s.x, s.y, s.z,
    s.distance_to_sol,
    s.main_star_type,
    s.galaxy_region_id,
    a.primary_archetype,
    a.secondary_archetype,
    a.archetype_confidence,
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
    a.overall_development_potential,
    a.buildability_score,
    a.build_complexity,
    a.purity_score,
    a.contamination_risk,
    a.confidence,
    t.has_elw,
    t.has_black_hole,
    t.has_neutron_star,
    t.elw_count,
    t.landable_count,
    t.est_total_slots,
    t.display_tags,
    topo.strong_link_potential,
    topo.weak_link_stability,
    topo.contamination_risk     AS topo_contamination_risk
FROM systems s
JOIN system_archetype_scores a   ON a.system_id64 = s.id64
JOIN system_archetype_traits t   ON t.system_id64 = s.id64
LEFT JOIN system_slot_topology topo ON topo.system_id64 = s.id64
WHERE a.dirty = FALSE
  AND a.overall_development_potential > 0
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_archetype_id64
    ON mv_archetype_rankings (id64);
CREATE INDEX IF NOT EXISTS idx_mv_archetype_refinery
    ON mv_archetype_rankings (score_refinery_industrial DESC);
CREATE INDEX IF NOT EXISTS idx_mv_archetype_hitech
    ON mv_archetype_rankings (score_hitech_tourism DESC);
CREATE INDEX IF NOT EXISTS idx_mv_archetype_agri
    ON mv_archetype_rankings (score_agriculture_terraforming DESC);
CREATE INDEX IF NOT EXISTS idx_mv_archetype_odp
    ON mv_archetype_rankings (overall_development_potential DESC);
CREATE INDEX IF NOT EXISTS idx_mv_archetype_region
    ON mv_archetype_rankings (galaxy_region_id, score_refinery_industrial DESC);
```

### 3.8 Relationship to Existing `ratings` Table

The existing `ratings` table is **preserved intact** through Phase 1 and Phase 2. No columns are dropped. The new tables are purely additive.

```
EXISTING (preserved):    ratings
                         ↕ joined via system_id64
NEW (additive):          system_archetype_scores
                         system_slot_topology
                         system_archetype_traits
                         economy_pair_synergy
                         pair_synergy_constants
                         mv_archetype_rankings (materialized view)
```

The `ratings` table becomes a **legacy compatibility layer** that:
1. Continues to power the existing `/api/ratings/rerank` endpoint unchanged
2. Provides `score_breakdown` JSONB for backward-compat API consumers
3. Is eventually superseded by `system_archetype_scores` in Phase 4

---

## 4. Archetype Scoring Engine

### 4.1 File: `apps/importer/src/build_archetype_scores.py`

This is the new scoring engine. It runs after `build_ratings.py` and reads from both the existing `ratings` table and the new `system_slot_topology` table.

### 4.2 Archetype Definitions

Each archetype has:
- **Primary body requirements** (body types that maximally support it)
- **Economy pair target** (the economy combination it optimises for)
- **Topology requirements** (slot type preferences)
- **Contamination tolerance** (how much economy bleed it can absorb)
- **Purity multiplier** (reward for clean economy stacks)

```python
ARCHETYPE_DEFINITIONS = {

    'refinery_industrial': {
        'label':         'Refinery / Industrial Megacomplex',
        'description':   'Rocky and Icy body manufacturing hub',
        'economy_pair':  ('Refinery', 'Industrial'),
        'body_weights':  {
            'rocky_clean':   1.0,    # Perfect Refinery body
            'rocky_ice':     0.80,   # Refinery + Industrial hybrid
            'icy':           0.70,   # Pure Industrial
            'rocky_rings':   0.55,   # Refinery + mild Extraction
            'hmc':           0.35,   # Usable with effort
            'rocky_geo':     0.15,   # Heavy contamination
            'rocky_bio':     0.20,   # Moderate contamination
        },
        'slot_preference': 'ground_heavy',  # Surface ports for CMM Composite
        'requires_landable': True,
        'contamination_tolerance': 0.30,    # Can handle up to 30% contamination
        'purity_multiplier':       1.35,    # +35% score for clean stacks
        'buildability_profile': 'standard',
        'tags': ['Manufacturing', 'CMM Composite', 'Refinery Hub'],
    },

    'extraction_refinery': {
        'label':         'Extraction / Refinery Mining Hub',
        'description':   'HMC and metal-rich mining support system',
        'economy_pair':  ('Extraction', 'Refinery'),
        'body_weights':  {
            'hmc':           1.0,
            'metal_rich':    0.90,
            'rocky_rings':   0.70,
            'hmc_geo':       0.80,   # Geo signals boost Extraction
            'rocky_geo':     0.50,
        },
        'slot_preference': 'balanced',
        'requires_landable': False,  # Extraction works orbital
        'contamination_tolerance': 0.40,
        'purity_multiplier':       1.20,
        'buildability_profile': 'mining_focus',
        'tags': ['Mining Hub', 'Extraction', 'Metal-Rich'],
    },

    'agriculture_terraforming': {
        'label':         'Agriculture / Terraforming Colony',
        'description':   'Population growth and terraforming focus',
        'economy_pair':  ('Agriculture', 'Tourism'),  # Tourism via ELW/WW
        'body_weights':  {
            'elw':           1.0,
            'ww':            0.80,
            'terraformable': 0.60,   # Future agriculture boost
            'rocky_bio':     0.45,   # Bio signals = Agriculture + Terraforming
            'ammonia':       0.30,   # Contamination risk but HighTech bonus
        },
        'slot_preference': 'ground_heavy',
        'requires_landable': True,
        'contamination_tolerance': 0.35,
        'purity_multiplier':       1.40,
        'buildability_profile': 'growth_focus',
        'tags': ['Agriculture', 'Terraforming', 'ELW', 'Population Growth'],
    },

    'hitech_tourism': {
        'label':         'HighTech / Tourism Prestige Colony',
        'description':   'Prestige system with ELW, exotics, and high-tech industry',
        'economy_pair':  ('HighTech', 'Tourism'),
        'body_weights':  {
            'elw':           1.0,
            'ammonia':       0.90,
            'black_hole':    0.85,
            'neutron':       0.70,
            'white_dwarf':   0.55,
            'gas_giant':     0.65,
            'ww':            0.60,
        },
        'slot_preference': 'orbital_heavy',
        'requires_landable': False,
        'contamination_tolerance': 0.45,
        'purity_multiplier':       1.30,
        'buildability_profile': 'prestige',
        'tags': ['Prestige', 'HighTech', 'Tourism', 'Exotic'],
    },

    'expansion_capital': {
        'label':         'Expansion Capital',
        'description':   'Strategic node for further colonisation chains',
        'economy_pair':  ('Industrial', 'HighTech'),  # Flexibility is the point
        'body_weights':  {
            # Rewards body diversity, not specialisation
            'elw':           0.70,
            'gas_giant':     0.65,
            'rocky_clean':   0.60,
            'icy':           0.60,
            'hmc':           0.55,
        },
        'slot_preference': 'balanced',
        'requires_landable': True,
        'contamination_tolerance': 0.55,   # Expansion capitals tolerate diversity
        'purity_multiplier':       1.00,   # No purity bonus — flexibility is valued
        'diversity_bonus':         1.30,   # +30% for high body diversity
        'buildability_profile': 'flexible',
        'tags': ['Expansion', 'Capital', 'Strategic', 'Flexible'],
    },

    'military_industrial': {
        'label':         'Military / Industrial Complex',
        'description':   'Defensive stronghold with manufacturing capacity',
        'economy_pair':  ('Military', 'Industrial'),
        'body_weights':  {
            'elw':           0.90,
            'gas_giant':     0.70,
            'icy':           0.65,
            'rocky_clean':   0.60,
            'neutron':       0.50,
            'black_hole':    0.45,
        },
        'slot_preference': 'balanced',
        'requires_landable': True,
        'contamination_tolerance': 0.40,
        'purity_multiplier':       1.25,
        'buildability_profile': 'military',
        'tags': ['Military', 'Industrial', 'Defence', 'Stronghold'],
    },

    'ax_forward_base': {
        'label':         'AX Forward Operating Base',
        'description':   'Anti-xeno military infrastructure hub',
        'economy_pair':  ('Military', 'HighTech'),
        'body_weights':  {
            'elw':           1.0,   # ELW gives Military + HighTech + Tourism
            'neutron':       0.80,  # Prestige + AX jump route proximity
            'black_hole':    0.70,
            'gas_giant':     0.60,
            'rocky_clean':   0.50,
        },
        'slot_preference': 'balanced',
        'requires_landable': True,
        'contamination_tolerance': 0.50,
        'purity_multiplier':       1.20,
        'strategic_bonus':         0.20,  # +20% if within 200 Ly of known Thargoid territory
        'buildability_profile': 'military',
        'tags': ['AX', 'Military', 'Forward Base', 'Anti-Xeno'],
    },

    'flexible_multirole': {
        'label':         'Flexible Multi-Role Colony',
        'description':   'High diversity, multiple viable specialisation paths',
        'economy_pair':  None,   # No fixed pair — scored by diversity
        'body_weights':  {
            # All body types valued equally; diversity metric drives score
        },
        'slot_preference': 'balanced',
        'requires_landable': False,
        'contamination_tolerance': 0.70,
        'purity_multiplier':       1.00,
        'diversity_bonus':         1.50,
        'buildability_profile': 'flexible',
        'tags': ['Multi-Role', 'Flexible', 'Generalist'],
    },
}
```

### 4.3 Archetype Score Formula

```python
def compute_archetype_score(
    archetype_key: str,
    counts: dict,          # from classify_bodies()
    topology: dict,        # from build_topology.py
    pair_synergy: float,   # from pair_synergy_constants
    main_star_type: str,
) -> dict:
    """
    Compute a 0-100 archetype score for a single archetype.

    Returns:
        {
            'score': float,          # 0-100 final score
            'body_contribution': float,
            'topology_contribution': float,
            'purity_contribution': float,
            'buildability_contribution': float,
            'notes': list[str],
        }
    """
    defn = ARCHETYPE_DEFINITIONS[archetype_key]

    # ── 1. Body composition score (0-60 pts) ─────────────────────────
    body_score = 0.0
    body_notes = []
    for body_key, weight in defn['body_weights'].items():
        count = counts.get(body_key, 0)
        if count > 0:
            # Diminishing returns: sqrt scaling after first 3 bodies
            contribution = min(count, 3) * weight + max(count - 3, 0) * weight * 0.4
            body_score += contribution * 20.0   # scale to 0-60 range
            if count >= 1:
                body_notes.append(f"{count}× {body_key.replace('_', ' ')}")

    body_score = min(body_score, 60.0)

    # ── 2. Topology score (0-25 pts) ─────────────────────────────────
    topo_score = 0.0
    if topology:
        slot_pref = defn.get('slot_preference', 'balanced')
        if slot_pref == 'ground_heavy':
            topo_score = topology.get('ground_synergy', 0) * 0.25
        elif slot_pref == 'orbital_heavy':
            topo_score = topology.get('orbital_synergy', 0) * 0.25
        else:
            topo_score = (
                topology.get('orbital_synergy', 0) * 0.12 +
                topology.get('ground_synergy', 0) * 0.13
            )
        topo_score = min(topo_score, 25.0)

    # ── 3. Purity / contamination (multiplier, not additive) ─────────
    contamination = topology.get('contamination_risk', 0.5) if topology else 0.5
    tolerance = defn['contamination_tolerance']
    purity_factor = 1.0
    if contamination > tolerance:
        # Penalty ramps up beyond tolerance threshold
        excess = (contamination - tolerance) / (1.0 - tolerance)
        purity_factor = 1.0 - (excess * (1.0 - 1.0 / defn['purity_multiplier']))
    else:
        # Bonus for clean stacks
        clean_ratio = 1.0 - (contamination / max(tolerance, 0.01))
        purity_factor = 1.0 + (clean_ratio * (defn['purity_multiplier'] - 1.0))

    # ── 4. Pair synergy boost (0-15 pts) ─────────────────────────────
    synergy_pts = pair_synergy * 15.0 if pair_synergy else 0.0

    # ── 5. Diversity bonus (for expansion/flexible archetypes) ────────
    diversity_factor = 1.0
    if 'diversity_bonus' in defn:
        from build_ratings import compute_body_diversity
        diversity = compute_body_diversity(counts) / 30.0  # normalise 0-1
        diversity_factor = 1.0 + (diversity * (defn['diversity_bonus'] - 1.0))

    # ── 6. Surface port requirement check ────────────────────────────
    if defn.get('requires_landable') and counts.get('landable', 0) == 0:
        body_score *= 0.40   # Severe cap: no landable = very limited utility

    # ── 7. Compose final score ────────────────────────────────────────
    raw_score = (body_score + topo_score + synergy_pts) * purity_factor * diversity_factor
    final_score = min(float(raw_score), 100.0)

    return {
        'score': round(final_score, 2),
        'body_contribution': round(body_score, 2),
        'topology_contribution': round(topo_score, 2),
        'purity_factor': round(purity_factor, 3),
        'synergy_pts': round(synergy_pts, 2),
        'contamination_risk': round(contamination, 3),
        'notes': body_notes,
    }
```

### 4.4 Overall Development Potential

```python
def compute_overall_development_potential(
    archetype_scores: dict,   # archetype_key -> score
    diversity: int,           # 0-30 from compute_body_diversity()
    has_standout: bool,       # ELW / BH / neutron / 2+ WW / 5+ terraformable
    buildability: float,      # 0-100
) -> float:
    """
    Overall development potential is a SUPPORTING metric — not the star.
    It answers: "across all possible colony types, how good is this system?"

    Deliberately does NOT replace archetype scores. Used as a secondary sort
    when two systems tie on their primary archetype score.
    """
    # Top-3 archetype average (60% weight)
    top3 = sorted(archetype_scores.values(), reverse=True)[:3]
    top3_avg = sum(top3) / 3 if top3 else 0

    # Diversity bonus (20% weight)
    diversity_bonus = (diversity / 30.0) * 20.0

    # Buildability (20% weight)
    buildability_contribution = buildability * 0.20

    raw = top3_avg * 0.60 + diversity_bonus + buildability_contribution

    # Rarity gate: systems without a standout body are capped at 82
    # (prevents generic rocky-heavy systems from inflating ODP)
    if not has_standout and raw > 82:
        raw = 82.0

    return round(min(raw, 100.0), 2)
```

---

## 5. Economy Pair Synergy Model

### 5.1 File: `apps/importer/src/build_topology.py` (new)

### 5.2 System-Specific Pair Synergy

The base synergy constants in `pair_synergy_constants` are global. Per-system synergy is modified by:

```python
PAIR_MODIFIERS = {
    # Body-type modifiers that increase synergy for a pair
    'Refinery+Industrial': {
        'rocky_ice':      +0.08,   # Rocky Ice inherently serves both
        'icy':            +0.05,   # Icy = pure Industrial, strengthens pairing
        'rocky_clean':    +0.04,   # More clean Rocky = less contamination
        'rocky_geo':      -0.12,   # Geo signals = Extraction contamination
        'rocky_bio':      -0.08,   # Bio signals = Agriculture contamination
    },
    'Agriculture+Tourism': {
        'elw':            +0.12,   # ELW drives both Agriculture and Tourism
        'ww':             +0.08,   # Water World contributes to both
        'ammonia':        +0.06,   # Ammonia World boosts Tourism, not Agriculture
        'terraformable':  +0.04,   # Terraformable body = Agriculture strong link
        'tidal_lock':     -0.06,   # Tidal lock decreases Agriculture strong link
        'icy':            -0.05,   # Icy decreases Agriculture strong link
    },
    'HighTech+Tourism': {
        'black_hole':     +0.15,   # Black hole is a massive Tourism/HT draw
        'neutron':        +0.10,
        'ammonia':        +0.10,
        'gas_giant':      +0.06,
        'elw':            +0.08,
    },
    'Extraction+Refinery': {
        'hmc':            +0.10,   # HMC hosts both Extraction and Refinery Hubs
        'hmc_geo':        +0.08,   # HMC with geo = strong Extraction
        'metal_rich':     +0.06,
        'rocky_rings':    +0.04,
        'rocky_geo':      -0.05,   # Geo on Rocky = adds Industrial contamination
    },
}

def compute_system_pair_synergy(
    economy_a: str,
    economy_b: str,
    counts: dict,
    topology: dict,
) -> float:
    """
    Compute system-specific pair synergy (0-1).
    Starts from global base, applies body-type modifiers.
    """
    pair_key = f'{economy_a}+{economy_b}'
    alt_key  = f'{economy_b}+{economy_a}'

    # Fetch base synergy
    base = BASE_SYNERGY.get(pair_key, BASE_SYNERGY.get(alt_key, 0.50))
    modifiers = PAIR_MODIFIERS.get(pair_key, PAIR_MODIFIERS.get(alt_key, {}))

    adjusted = base
    for body_key, modifier in modifiers.items():
        count = counts.get(body_key, 0)
        if count > 0:
            # Modifier applies once for first body, 50% for subsequent
            effect = modifier + modifier * 0.5 * (min(count, 4) - 1)
            adjusted += effect

    # Topology modifier: if topology confirms clean build path, boost
    if topology:
        if topology.get('contamination_risk', 0.5) < 0.20:
            adjusted += 0.05   # Very clean system bonus
        elif topology.get('contamination_risk', 0.5) > 0.70:
            adjusted -= 0.10   # High contamination penalty

    return round(max(0.0, min(1.0, adjusted)), 3)
```

### 5.3 Contamination Modelling

```python
def compute_contamination_risk(counts: dict, target_pair: tuple) -> dict:
    """
    Model the risk that a third economy contaminates the target pair.

    Returns:
        {
            'risk_score':         float,  # 0-1 overall risk
            'primary_contaminant': str,   # most likely third economy
            'contamination_paths': list,  # [{body, economy_added, severity}]
            'mitigation':         str,    # how to address it
        }
    """
    economy_a, economy_b = target_pair
    contamination_events = []

    # Map body types to economies they ADD (contamination sources)
    BODY_ECONOMY_ADDS = {
        'rocky_geo':    ['Extraction', 'Industrial'],   # severe
        'rocky_bio':    ['Agriculture', 'Terraforming'], # moderate
        'rocky_rings':  ['Extraction'],                  # mild
        'rocky_mixed':  ['Extraction', 'Industrial', 'Agriculture', 'Terraforming'],  # severe
        'hmc_geo':      ['Extraction'],                  # useful if Extraction is target
        'ammonia':      ['HighTech', 'Tourism'],
        'elw':          ['Agriculture', 'HighTech', 'Military', 'Tourism'],
        'ww':           ['Agriculture', 'Tourism'],
        'gas_giant':    ['HighTech', 'Industrial'],
        'neutron':      ['HighTech', 'Tourism'],
        'black_hole':   ['HighTech', 'Tourism'],
    }

    SEVERITY = {
        'rocky_geo':   0.85,
        'rocky_mixed': 0.95,
        'rocky_bio':   0.55,
        'rocky_rings': 0.25,
        'ammonia':     0.40,
        'gas_giant':   0.30,
    }

    contaminant_scores = {}
    for body_key, economies in BODY_ECONOMY_ADDS.items():
        count = counts.get(body_key, 0)
        if count == 0:
            continue
        severity = SEVERITY.get(body_key, 0.20)
        for eco in economies:
            if eco not in (economy_a, economy_b):
                # This economy would be ADDED as contamination
                score = severity * min(count, 3) / 3
                contaminant_scores[eco] = contaminant_scores.get(eco, 0) + score
                contamination_events.append({
                    'body':     body_key,
                    'economy':  eco,
                    'severity': round(severity, 2),
                    'count':    count,
                })

    overall_risk = min(sum(contaminant_scores.values()) / max(len(contaminant_scores), 1), 1.0)
    primary = max(contaminant_scores, key=contaminant_scores.get) if contaminant_scores else None

    mitigation = _suggest_mitigation(economy_a, economy_b, primary, overall_risk)

    return {
        'risk_score':          round(overall_risk, 3),
        'primary_contaminant': primary,
        'contamination_paths': contamination_events[:5],   # top 5 for API
        'mitigation':          mitigation,
    }


def _suggest_mitigation(eco_a, eco_b, contaminant, risk) -> str:
    if risk < 0.20:
        return "Low risk — standard build order sufficient"
    if risk < 0.45:
        return (f"Moderate {contaminant} contamination risk. "
                f"Sequence {eco_a} facilities first to establish top-2 before "
                f"{contaminant} gains foothold.")
    if risk >= 0.45:
        return (f"High {contaminant} contamination risk. "
                f"Refinery/Industrial Hubs required to maintain {eco_a}+{eco_b} "
                f"dominance. Consider dedicated strong-link facilities on "
                f"contaminating bodies.")
    return "Evaluate build order carefully."
```

---

## 6. Topology & Contamination Modelling

### 6.1 Topology Metrics

```python
def compute_topology_metrics(bodies: list, system_id64: int) -> dict:
    """
    Compute system-level topology metrics from body data.
    These metrics describe HOW bodies are arranged, not just WHAT they are.
    """

    # ── Strong link potential ─────────────────────────────────────────
    # Strong links are boosted by: ELW, WW, Ammonia, GG, Ringed bodies
    strong_link_bodies = sum([
        counts.get('elw', 0)       * 25,
        counts.get('ww', 0)        * 18,
        counts.get('ammonia', 0)   * 20,
        counts.get('gas_giant', 0) * 12,
        counts.get('rocky_rings', 0) * 8,
        counts.get('black_hole', 0)  * 22,
        counts.get('neutron', 0)     * 18,
    ])
    strong_link_potential = min(strong_link_bodies, 100)

    # ── Weak link stability ───────────────────────────────────────────
    # Weak links are DECREASED by: tidal lock, icy bodies (for Agri)
    # Stability = how resistant the system is to weak-link degradation
    destabilisers = (
        counts.get('tidal_lock', 0) * 8 +
        counts.get('icy', 0) * 4
    )
    weak_link_stability = max(100 - destabilisers, 0)

    # ── Orbital synergy ───────────────────────────────────────────────
    # How well the orbital slot distribution supports the primary economy
    orbital_bodies = (
        counts.get('gas_giant', 0) * 6 +
        counts.get('elw', 0)       * 5 +
        counts.get('ww', 0)        * 4 +
        counts.get('ammonia', 0)   * 4 +
        counts.get('rocky_ice', 0) * 3 +
        counts.get('icy', 0)       * 3 +
        counts.get('rocky_clean', 0) * 3 +
        counts.get('hmc', 0)       * 3 +
        counts.get('metal_rich', 0) * 2
    )
    orbital_synergy = min(orbital_bodies * 5, 100)

    # ── Ground synergy ────────────────────────────────────────────────
    ground_bodies = (
        counts.get('landable', 0) * 10 +
        counts.get('landable_rocky_clean', 0) * 5 +
        counts.get('landable_hmc', 0) * 4
    )
    ground_synergy = min(ground_bodies * 4, 100)

    # ── Build flexibility ─────────────────────────────────────────────
    # How many distinct viable build paths exist
    from build_ratings import compute_body_diversity
    diversity = compute_body_diversity(counts)
    build_flexibility = int(diversity / 30.0 * 100)

    # ── Nesting potential ─────────────────────────────────────────────
    # Ability to use local-body grouping for supporting facilities
    # (requires parent-body data from Spansh)
    # For now: estimate from gas giant + moon presence
    nesting_potential = min(
        counts.get('gas_giant', 0) * 20 +
        counts.get('rocky_clean', 0) * 8,
        100
    )

    return {
        'strong_link_potential':  strong_link_potential,
        'weak_link_stability':    weak_link_stability,
        'contamination_risk':     contamination_data.get('risk_score', 0.5),
        'orbital_synergy':        orbital_synergy,
        'ground_synergy':         ground_synergy,
        'build_flexibility':      build_flexibility,
        'nesting_potential':      nesting_potential,
        'has_viable_surface_port': (
            counts.get('landable', 0) > 0 and
            (counts.get('landable_rocky_any', 0) + counts.get('landable_hmc', 0)) > 0
        ),
        'has_deep_orbital_anchor': counts.get('gas_giant', 0) > 0,
        'has_ringed_gas_giant':   counts.get('rocky_rings', 0) > 0,
    }
```

### 6.2 Estimated Slot Computation

```python
# Slot estimation constants — derived from community observation
# of in-game Architect Mode slot counts
SLOT_ESTIMATES = {
    # (body_type_key): (orbital_slots_per_body, ground_slots_per_body)
    # Ground slots require is_landable=True

    # Stars
    'main_star_large':   (10, 0),   # O/B/A main stars
    'main_star_medium':  (7, 0),    # F/G/K main stars
    'main_star_small':   (4, 0),    # M/L/T dwarfs
    'secondary_star':    (5, 0),    # Any non-main star

    # Gas Giants
    'gas_giant_ringed':  (5, 0),    # Gas Giant with rings
    'gas_giant_plain':   (3, 0),    # Gas Giant without rings

    # Planets (orbital only if not landable)
    'elw':               (4, 8),    # ELW — large ground slot count
    'ww':                (3, 0),    # Water World — not landable typically
    'ammonia':           (3, 0),    # Ammonia World — not landable
    'rocky_large':       (3, 6),    # Rocky Body, large (radius > 3000 km)
    'rocky_medium':      (2, 4),    # Rocky Body, medium
    'rocky_small':       (2, 2),    # Rocky Body, small
    'rocky_ice':         (3, 3),    # Rocky Ice — both surface and orbital
    'icy_large':         (2, 2),    # Icy Body, large, landable
    'icy_small':         (2, 0),    # Icy Body, small, not landable
    'hmc_large':         (3, 5),    # HMC, large, landable
    'hmc_medium':        (2, 3),    # HMC, medium
    'metal_rich':        (2, 3),    # Metal Rich (often landable)
}


def estimate_body_slots(body: dict) -> tuple:
    """
    Estimate orbital and ground slot counts for a single body.

    Returns (estimated_orbital, estimated_ground).
    Ground slots are 0 for non-landable bodies.
    """
    sub = str(body.get('subtype') or '').lower()
    is_landable = bool(body.get('is_landable', False))
    radius = float(body.get('radius') or 0)  # km
    is_main_star = bool(body.get('is_main_star', False))
    sc = str(body.get('spectral_class') or '')
    has_rings = bool(body.get('has_rings', False))

    # ── Stars ─────────────────────────────────────────────────────────
    if body.get('body_type') == 'Star':
        if is_main_star:
            if sc and sc[0].upper() in ('O', 'B', 'A'):
                return (10, 0)
            elif sc and sc[0].upper() in ('F', 'G', 'K'):
                return (7, 0)
            else:
                return (4, 0)
        else:
            return (5, 0)

    # ── Gas Giants ────────────────────────────────────────────────────
    if 'gas giant' in sub:
        return (5 if has_rings else 3, 0)

    # ── Special worlds ────────────────────────────────────────────────
    if 'earth-like' in sub:
        return (4, 8 if is_landable else 0)
    if 'water world' in sub:
        return (3, 0)
    if 'ammonia' in sub:
        return (3, 0)

    # ── Rocky Ice ─────────────────────────────────────────────────────
    if 'rocky ice' in sub:
        return (3, 3 if is_landable else 0)

    # ── Rocky Bodies ──────────────────────────────────────────────────
    if 'rocky body' in sub or sub == 'rocky':
        if radius > 5000:
            return (3, 6 if is_landable else 0)
        elif radius > 2500:
            return (2, 4 if is_landable else 0)
        else:
            return (2, 2 if is_landable else 0)

    # ── HMC ───────────────────────────────────────────────────────────
    if 'high metal content' in sub:
        if radius > 4000:
            return (3, 5 if is_landable else 0)
        else:
            return (2, 3 if is_landable else 0)

    # ── Metal Rich ────────────────────────────────────────────────────
    if 'metal-rich' in sub or 'metal rich' in sub:
        return (2, 3 if is_landable else 0)

    # ── Icy ───────────────────────────────────────────────────────────
    if 'icy body' in sub or sub == 'icy':
        if is_landable and radius > 2000:
            return (2, 2)
        return (2, 0)

    # ── Default ───────────────────────────────────────────────────────
    return (1, 1 if is_landable else 0)
```

---

## 7. Buildability Scoring

### 7.1 Formula

```python
def compute_buildability(
    counts: dict,
    topology: dict,
    archetype_key: str,
    pair_synergy: float,
) -> dict:
    """
    Buildability = how easy is it to realise this archetype in practice.

    Factors:
    - CP efficiency:      how many construction points needed per economy tier
    - T3 scaling:         ease of advancing to T3 (requires strong links + sufficient slots)
    - Slot efficiency:    orbital/ground ratio matches archetype needs
    - Contamination mgmt: how much extra work is needed to maintain top-2 economies
    - Topology flexibility: number of viable sequencing paths
    """
    # ── CP efficiency (0-100) ─────────────────────────────────────────
    # Systems where each facility directly supports the target economy
    # are more CP-efficient than systems requiring "hub" investments first.
    # Proxy: clean body count for the archetype / total relevant bodies
    defn = ARCHETYPE_DEFINITIONS[archetype_key]
    primary_bodies = sum(
        counts.get(k, 0) * w
        for k, w in defn['body_weights'].items()
        if w >= 0.70  # only count high-value bodies
    )
    all_bodies = max(sum(counts.get(k, 0) for k in defn['body_weights']), 1)
    cp_efficiency = min(primary_bodies / all_bodies * 100, 100)

    # ── T3 scaling (0-100) ────────────────────────────────────────────
    # T3 requires strong links — approximated by strong_link_potential
    t3_scaling = topology.get('strong_link_potential', 0) if topology else 30.0

    # ── Slot efficiency (0-100) ───────────────────────────────────────
    slot_pref = defn.get('slot_preference', 'balanced')
    ground = topology.get('ground_synergy', 50) if topology else 50
    orbital = topology.get('orbital_synergy', 50) if topology else 50

    if slot_pref == 'ground_heavy':
        slot_efficiency = ground * 0.70 + orbital * 0.30
    elif slot_pref == 'orbital_heavy':
        slot_efficiency = orbital * 0.70 + ground * 0.30
    else:
        slot_efficiency = (ground + orbital) / 2.0

    # ── Contamination management penalty ─────────────────────────────
    contamination = topology.get('contamination_risk', 0.5) if topology else 0.5
    contamination_penalty = contamination * 30   # up to -30 from contamination

    # ── Topology flexibility bonus ────────────────────────────────────
    flexibility = topology.get('build_flexibility', 50) if topology else 50
    flexibility_bonus = flexibility * 0.10       # up to +10

    # ── Compose ───────────────────────────────────────────────────────
    raw = (
        cp_efficiency    * 0.35 +
        t3_scaling       * 0.25 +
        slot_efficiency  * 0.20 +
        flexibility_bonus
    ) - contamination_penalty

    score = round(max(0.0, min(100.0, raw)), 2)

    # ── Classify complexity ────────────────────────────────────────────
    if score >= 80 and contamination < 0.20:
        complexity = 'simple'
    elif score >= 65 and contamination < 0.40:
        complexity = 'moderate'
    elif score >= 45:
        complexity = 'advanced'
    elif score >= 25:
        complexity = 'expert'
    else:
        complexity = 'trivial' if score > 15 else 'expert'

    return {
        'buildability_score': score,
        'build_complexity':   complexity,
        'cp_efficiency':      round(cp_efficiency, 2),
        't3_scaling_viability': round(t3_scaling, 2),
        'slot_efficiency':    round(slot_efficiency, 2),
    }
```

---

## 8. Explainability System

### 8.1 Structured Rationale (JSONB)

The new `rationale` field in `system_archetype_scores` is **structured JSONB**, not a plain string. This allows the frontend to render richer explanations without parsing.

```python
def generate_structured_rationale(
    archetype_key: str,
    archetype_score: dict,
    counts: dict,
    topology: dict,
    buildability: dict,
    contamination: dict,
    confidence: float,
) -> dict:
    """
    Generate a full structured rationale for a system's archetype score.

    Returns:
    {
        "summary":    "One-sentence description (<=200 chars)",
        "tier":       "S / A / B / C / D",
        "headline":   "92 — Refinery / Industrial Megacomplex",
        "positives":  ["Rocky-Ice world", "Pristine reserves", ...],
        "risks":      ["Moderate geo-signal contamination", ...],
        "complexity": "Moderate — some contamination management required",
        "build_path": "Sequence Refinery facilities first, then Industrial...",
        "tags":       ["Rocky-Ice", "Pristine", "Low Contamination"],
        "score_breakdown": {
            "body_composition":   58.2,
            "topology":           22.1,
            "pair_synergy_pts":   11.4,
            "purity_factor":      1.12,
        }
    }
    """
    defn = ARCHETYPE_DEFINITIONS[archetype_key]
    score = archetype_score['score']

    # ── Tier ─────────────────────────────────────────────────────────
    if score >= 88:   tier = 'S'
    elif score >= 76: tier = 'A'
    elif score >= 60: tier = 'B'
    elif score >= 45: tier = 'C'
    else:             tier = 'D'

    # ── Summary sentence ─────────────────────────────────────────────
    score_word = 'Exceptional' if score >= 88 else \
                 'Excellent'   if score >= 76 else \
                 'Solid'       if score >= 60 else \
                 'Functional'  if score >= 45 else \
                 'Limited'
    summary = (
        f"{score_word} candidate for {defn['label']}. "
        f"{_archetype_context(archetype_key, counts, score)}"
    )[:200]

    # ── Positive traits ───────────────────────────────────────────────
    positives = _build_positives(archetype_key, counts, topology, buildability)

    # ── Risks ─────────────────────────────────────────────────────────
    risks = _build_risks(counts, topology, contamination, buildability)

    # ── Complexity description ────────────────────────────────────────
    complexity_map = {
        'trivial':  'Trivial — straightforward single-economy build',
        'simple':   'Simple — clean pair, standard build order',
        'moderate': 'Moderate — some contamination management required',
        'advanced': 'Advanced — nested ports or tight sequencing needed',
        'expert':   'Expert — multi-phase build, deep game knowledge required',
    }
    complexity_str = complexity_map.get(buildability['build_complexity'], 'Moderate')

    # ── Tags ─────────────────────────────────────────────────────────
    tags = _compute_display_tags(archetype_key, counts, topology, buildability, contamination)

    return {
        'summary':    summary,
        'tier':       tier,
        'headline':   f"{int(score)} — {defn['label']}",
        'positives':  positives[:6],   # max 6 bullet points
        'risks':      risks[:4],       # max 4 warnings
        'complexity': complexity_str,
        'build_path': _suggest_build_path(archetype_key, counts, contamination),
        'tags':       tags,
        'score_breakdown': {
            'body_composition':    archetype_score.get('body_contribution', 0),
            'topology':            archetype_score.get('topology_contribution', 0),
            'pair_synergy_pts':    archetype_score.get('synergy_pts', 0),
            'purity_factor':       archetype_score.get('purity_factor', 1.0),
            'contamination_risk':  archetype_score.get('contamination_risk', 0),
        },
        'data_confidence': confidence,
    }


def _compute_display_tags(archetype_key, counts, topology, buildability, contamination) -> list:
    tags = []

    # Body type tags
    if counts.get('elw', 0) >= 1:
        tags.append(f"{'ELW' if counts['elw'] == 1 else str(counts['elw']) + '× ELW'}")
    if counts.get('black_hole', 0) >= 1:
        tags.append('Black Hole')
    if counts.get('neutron', 0) >= 1:
        tags.append('Neutron Star')
    if counts.get('rocky_clean', 0) >= 3:
        tags.append(f"{counts['rocky_clean']} Clean Rocky")
    if counts.get('rocky_ice', 0) >= 2:
        tags.append('Rocky-Ice')

    # Quality tags
    if contamination and contamination.get('risk_score', 1) < 0.20:
        tags.append('Low Contamination')
    elif contamination and contamination.get('risk_score', 0) > 0.60:
        tags.append('High Contamination')

    if buildability['build_complexity'] in ('trivial', 'simple'):
        tags.append('T3 Friendly')

    # Slot tags
    est_total = counts.get('est_total_slots', 0)
    if est_total >= 40:
        tags.append(f'{est_total}+ Slots')
    elif est_total >= 25:
        tags.append(f'{est_total} Slots')

    if counts.get('landable', 0) >= 8:
        tags.append(f"{counts['landable']} Ground Slots")

    return tags[:8]   # max 8 tags for UI
```

---

## 9. Async Computation Pipeline

### 9.1 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1: Raw Data Ingestion                                      │
│  import_spansh.py → systems, bodies, stations tables             │
│  eddn_listener.py → real-time updates → rating_dirty = TRUE      │
└─────────────────────────┬────────────────────────────────────────┘
                          │ (nightly or on-dirty)
┌─────────────────────────▼────────────────────────────────────────┐
│  LAYER 2: Body Classification                                     │
│  build_ratings.py → ratings table (EXISTING — preserved)         │
│  classify_bodies() → contamination flags, economy scores         │
└─────────────────────────┬────────────────────────────────────────┘
                          │ (after build_ratings.py completes)
┌─────────────────────────▼────────────────────────────────────────┐
│  LAYER 3: Topology Analysis (NEW)                                 │
│  build_topology.py → system_slot_topology table                  │
│  estimate_body_slots() → inferred slot counts                    │
│  compute_topology_metrics() → strong/weak link, contamination    │
│  compute_system_pair_synergy() → economy_pair_synergy table      │
└─────────────────────────┬────────────────────────────────────────┘
                          │ (after build_topology.py completes)
┌─────────────────────────▼────────────────────────────────────────┐
│  LAYER 4: Archetype Scoring (NEW)                                 │
│  build_archetype_scores.py → system_archetype_scores table       │
│  compute_archetype_score() × 9 archetypes per system             │
│  generate_structured_rationale() → JSONB rationale               │
│  → system_archetype_traits table                                  │
└─────────────────────────┬────────────────────────────────────────┘
                          │ (after build_archetype_scores.py completes)
┌─────────────────────────▼────────────────────────────────────────┐
│  LAYER 5: Materialized View Refresh (NEW)                         │
│  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings    │
│  Redis cache invalidation → api key prefix bump                  │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────────┐
│  LAYER 6: API Serving                                             │
│  FastAPI → reads from mv_archetype_rankings                      │
│  Redis → caches query results (TTL 300s)                         │
│  Dynamic reranking → Python-side weight application              │
└──────────────────────────────────────────────────────────────────┘
```

### 9.2 New Script: `build_topology.py`

```python
"""
ED Finder — Topology & Slot Inference Engine
Version: 1.0

Runs AFTER build_ratings.py. Reads from bodies + ratings tables,
writes to system_slot_topology and economy_pair_synergy.

Usage:
    python3 build_topology.py              # process all unprocessed systems
    python3 build_topology.py --rebuild    # reprocess all systems
    python3 build_topology.py --dirty      # only dirty systems
    python3 build_topology.py --workers 4
"""

# Worker function processes systems in chunks of 10,000.
# Each worker: fetches bodies for its chunk, computes topology,
# upserts to system_slot_topology.
# Same multiprocessing pattern as build_ratings.py.
```

### 9.3 New Script: `build_archetype_scores.py`

```python
"""
ED Finder — Archetype Scoring Engine
Version: 1.0

Runs AFTER build_topology.py. Reads from bodies + ratings +
system_slot_topology tables, writes to system_archetype_scores
and system_archetype_traits.

Usage:
    python3 build_archetype_scores.py --rebuild
    python3 build_archetype_scores.py --dirty
    python3 build_archetype_scores.py --workers 4
"""
```

### 9.4 Updated Build Order

```bash
# Full pipeline (nightly):
1. python3 import_spansh.py --all        # ~4-6h
2. python3 build_grid.py                 # ~1-2h
3. python3 build_ratings.py              # ~3-5h (existing)
4. python3 build_topology.py             # ~1-2h (NEW)
5. python3 build_archetype_scores.py     # ~2-3h (NEW)
6. python3 build_clusters.py             # ~2-4h (existing)
7. psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings"
```

### 9.5 Dirty-Flag Strategy

```sql
-- New trigger: when system_archetype_scores is set dirty,
-- also invalidate the materialized view row
-- (handled by the REFRESH CONCURRENTLY at end of dirty cycle)

-- Updated dirty propagation:
-- EDDN Scan event → systems.rating_dirty = TRUE
--   → build_ratings.py --dirty picks it up
--   → marks system_archetype_scores.dirty = TRUE
--   → build_archetype_scores.py --dirty picks it up
--   → REFRESH MATERIALIZED VIEW CONCURRENTLY (incremental)
```

---

## 10. API Endpoints

### 10.1 New: `GET /api/archetypes/rankings`

```
GET /api/archetypes/rankings?archetype=refinery_industrial&min_score=60
    &galaxy_region=18&max_distance_ly=500&limit=50

Response:
{
    "archetype":     "refinery_industrial",
    "archetype_label": "Refinery / Industrial Megacomplex",
    "results": [
        {
            "id64":   12345678901,
            "name":   "HD 49188",
            "coords": {"x": -22.4, "y": 12.1, "z": 55.3},
            "score":  92,
            "tier":   "S",
            "primary_archetype": "refinery_industrial",
            "buildability_score": 78,
            "build_complexity":   "moderate",
            "purity_score":       88,
            "contamination_risk": 0.14,
            "confidence":         0.97,
            "tags":   ["Rocky-Ice", "Pristine", "Low Contamination", "T3 Friendly"],
            "rationale": {
                "summary":    "Exceptional Refinery/Industrial candidate...",
                "tier":       "S",
                "headline":   "92 — Refinery / Industrial Megacomplex",
                "positives":  ["8 clean rocky bodies", "3 rocky-ice bodies", "15 landable"],
                "risks":      ["2 geo-signal rocky bodies — moderate Extraction contamination"],
                "complexity": "Moderate — some contamination management required",
                "tags":       ["Rocky-Ice", "Pristine", "Low Contamination"]
            }
        }
    ],
    "total":   1847,
    "count":   50,
    "source":  "mv_archetype_rankings",
    "query_ms": 12
}
```

### 10.2 New: `POST /api/archetypes/rerank`

```
POST /api/archetypes/rerank
{
    "id64s": [12345, 67890, ...],
    "archetype": "refinery_industrial",
    "weights": {
        "purity":       0.30,
        "buildability": 0.25,
        "slots":        0.20,
        "expansion":    0.15,
        "logistics":    0.10
    },
    "profile": null   // or: "industrial_empire", "space_farms", etc.
}

Response:
{
    "archetype":        "refinery_industrial",
    "profile_applied":  null,
    "weights_applied":  {...},
    "results": [
        {
            "id64":           12345,
            "reranked_score": 94,
            "original_score": 92,
            "rationale":      "Strong Refinery/Industrial; 8 clean rocky bodies..."
        }
    ]
}
```

### 10.3 New: `GET /api/archetypes/system/{id64}`

Full archetype breakdown for a single system.

```
GET /api/archetypes/system/12345678901

Response:
{
    "id64":   12345678901,
    "name":   "HD 49188",

    "archetypes": {
        "refinery_industrial": {
            "score": 92, "tier": "S",
            "rank_global": 147,
            "rationale": {...full structured rationale...}
        },
        "extraction_refinery": {
            "score": 78, "tier": "A", ...
        },
        ...all 9 archetypes...
    },

    "primary_archetype":   "refinery_industrial",
    "secondary_archetype": "extraction_refinery",
    "overall_development_potential": 88,
    "buildability_score": 78,
    "build_complexity":   "moderate",

    "topology": {
        "estimated_orbital_slots":  34,
        "estimated_ground_slots":   28,
        "strong_link_potential":    72,
        "weak_link_stability":      88,
        "contamination_risk":       0.14,
        "orbital_synergy":          68,
        "ground_synergy":           82
    },

    "economy_pairs": [
        {
            "economy_a": "Refinery",
            "economy_b": "Industrial",
            "synergy_score": 91,
            "purity_achievable": 0.88,
            "contamination_paths": [...]
        }
    ],

    "tags":       ["Rocky-Ice", "Pristine", "Low Contamination", "T3 Friendly"],
    "confidence": 0.97
}
```

### 10.4 New: `POST /api/archetypes/simulate`

Build simulation — given an intended build plan, score the system against it.

```
POST /api/archetypes/simulate
{
    "id64": 12345678901,
    "planned_archetype": "refinery_industrial",
    "planned_facilities": [
        {"type": "StarPort", "tier": 3, "body": "main_star"},
        {"type": "RefineryHub", "tier": 2, "body": "rocky_1"},
        ...
    ]
}

Response:
{
    "simulation_score": 87,
    "economy_prediction": {
        "primary":    "Refinery",
        "secondary":  "Industrial",
        "tertiary":   "Extraction",  // contamination from rocky_geo_1
        "purity":     0.84
    },
    "recommendations": [
        "Add Refinery Hub to rocky_geo_1 to suppress Extraction contamination",
        "3 additional Industrial facilities recommended for T3 scaling"
    ]
}
```

### 10.5 Updated: `POST /api/ratings/rerank`

> Stage 7B status: this section is historical design material. The current
> `/api/ratings/rerank` contract remains the v3.1 ratings rerank endpoint with
> `id64s`, optional `weights`, and optional `economy`. It does not implement
> `use_archetype_engine`, `archetype`, or `profile`, and the UI now presents
> the feature as Advanced Search Tuning.

**Backward-compatible.** The existing endpoint is unchanged. It continues to read from the `ratings` table using the v3.1 weights. A new optional field `use_archetype_engine` switches to the new scoring system:

```python
# In ratings.py — additive, not replacing:
class RerankRequest(BaseModel):
    id64s:   List[int]
    weights: Optional[RerankWeights] = None
    economy: Optional[str]           = None
    # NEW optional fields:
    archetype:            Optional[str]  = None   # e.g. 'refinery_industrial'
    use_archetype_engine: bool           = False  # default: use legacy engine
    profile:              Optional[str]  = None   # preset profile name
```

### 10.6 New: `GET /api/archetypes/profiles`

```
GET /api/archetypes/profiles

Response:
{
    "profiles": [
        {
            "id":          "industrial_empire",
            "label":       "Industrial Empire",
            "description": "Refinery/Industrial megacomplex focus",
            "archetype":   "refinery_industrial",
            "weights": {
                "purity": 0.35, "buildability": 0.25, "slots": 0.20,
                "expansion": 0.10, "logistics": 0.10
            }
        },
        {
            "id":          "space_farms",
            "label":       "Space Farms",
            "description": "Agriculture and terraforming focus",
            "archetype":   "agriculture_terraforming",
            "weights": {...}
        },
        {
            "id":          "prestige_capital",
            "label":       "Prestige Capital",
            "description": "HighTech / Tourism prestige colony",
            "archetype":   "hitech_tourism",
            "weights": {...}
        },
        {
            "id":          "ax_logistics",
            "label":       "AX Logistics",
            "description": "Military / HighTech anti-xeno forward base",
            "archetype":   "ax_forward_base",
            "weights": {...}
        },
        {
            "id":          "expansion_capital",
            "label":       "Expansion Capital",
            "description": "Flexible system for multi-jump colonisation chains",
            "archetype":   "expansion_capital",
            "weights": {...}
        },
        {
            "id":          "generalist",
            "label":       "Generalist",
            "description": "Balanced weights, no archetype preference",
            "archetype":   null,
            "weights": {...}
        }
    ]
}
```

---

## 11. Reranking Redesign

### 11.1 New Weight Dimensions

Replace:
```python
_DEFAULT_WEIGHTS = {
    'economy': 0.42, 'slots': 0.23, 'strategic': 0.18,
    'safety': 0.10, 'terraforming': 0.05, 'diversity': 0.02
}
```

With:
```python
_DEFAULT_ARCHETYPE_WEIGHTS = {
    'purity':       0.30,   # clean economy stack, low contamination
    'buildability': 0.25,   # ease of build, CP efficiency, T3 scaling
    'slots':        0.20,   # total slot count + topology quality
    'expansion':    0.15,   # flexibility for future growth
    'logistics':    0.10,   # distance from hub, scoopable star
}
```

### 11.2 Updated `RerankWeights` Model

```python
class ArchetypeRerankWeights(BaseModel):
    purity:       float = 0.30
    buildability: float = 0.25
    slots:        float = 0.20
    expansion:    float = 0.15
    logistics:    float = 0.10
```

### 11.3 Fast Reranking SQL

```sql
-- Reranking query against system_archetype_scores
-- All weights applied in Python after single DB fetch (same pattern as v3.1)

SELECT
    a.system_id64              AS id64,
    a.score_refinery_industrial AS archetype_score,
    a.purity_score,
    a.buildability_score,
    t.est_total_slots          AS slots,
    a.overall_development_potential AS expansion,
    CASE WHEN s.main_star_is_scoopable THEN 80 ELSE 40 END AS logistics,
    a.confidence,
    a.rationale
FROM system_archetype_scores a
JOIN systems s              ON s.id64 = a.system_id64
JOIN system_archetype_traits t ON t.system_id64 = a.system_id64
WHERE a.system_id64 = ANY($1::bigint[])
  AND a.dirty = FALSE;
```

---

## 12. Migration Strategy

### 12.1 Phase 1 — Parallel Infrastructure (No Breaking Changes)

**Duration:** 2-3 days  
**Risk:** Zero — purely additive

```sql
-- Run: sql/012_topology_tables.sql
CREATE TABLE system_slot_topology ...      -- new
CREATE TABLE system_archetype_scores ...   -- new
CREATE TABLE system_archetype_traits ...   -- new
CREATE TABLE economy_pair_synergy ...      -- new
CREATE TABLE pair_synergy_constants ...    -- new
INSERT INTO pair_synergy_constants ...     -- seed data

-- Existing tables untouched:
-- systems, bodies, stations, ratings, clusters, etc.
```

**Deliverables:**
- New schema deployed
- `pair_synergy_constants` seeded
- No API changes

### 12.2 Phase 2 — Build Pipeline Extension

**Duration:** 1 week  
**Risk:** Low — new scripts alongside existing ones

```bash
# New scripts added:
apps/importer/src/build_topology.py         # new
apps/importer/src/build_archetype_scores.py # new

# Existing scripts unchanged:
apps/importer/src/build_ratings.py          # preserved
apps/importer/src/import_spansh.py          # preserved
```

**Test:** Run `build_topology.py --limit 10000` and `build_archetype_scores.py --limit 10000`. Compare archetype scores against manual expectations for known systems.

**Validation queries:**
```sql
-- Check archetype distribution
SELECT primary_archetype, COUNT(*), AVG(score_refinery_industrial)
FROM system_archetype_scores
GROUP BY primary_archetype ORDER BY COUNT(*) DESC;

-- Verify purity scores are reasonable
SELECT system_id64, purity_score, contamination_risk
FROM system_archetype_scores
ORDER BY purity_score DESC LIMIT 20;

-- Cross-check: top refinery systems should match top ratings.score_refinery
SELECT a.system_id64, s.name,
       r.score_refinery,
       a.score_refinery_industrial
FROM system_archetype_scores a
JOIN ratings r ON r.system_id64 = a.system_id64
JOIN systems s ON s.id64 = a.system_id64
ORDER BY a.score_refinery_industrial DESC LIMIT 20;
```

### 12.3 Phase 3 — Beta API Endpoints

**Duration:** 1 week  
**Risk:** Low — new routes, no existing routes changed

```python
# New router: apps/api/src/routers/archetypes.py
# Mounted at /api/archetypes/...

# Existing routers unchanged:
# routers/ratings.py     → /api/ratings/rerank (unchanged)
# routers/search.py      → /api/local/search   (unchanged)
# routers/systems.py     → /api/system/{id64}  (unchanged)
```

**Frontend flag:** Add `?engine=v4` query parameter to enable new archetype data in system detail response. Existing frontend continues using v3.1 data.

### 12.4 Phase 4 — Full Cutover

**Duration:** 2 weeks  
**Risk:** Medium — user-visible changes

1. Deploy new frontend components (archetype cards, tier badges, structured rationale)
2. Make archetype scores the primary sort in `/api/local/search` when an economy is specified
3. Map economy filter → archetype: `economy=Refinery` → `archetype=refinery_industrial`
4. The single legacy `score` column becomes `overall_development_potential` in API responses
5. Remove `score` from primary UI display; replace with archetype tier badge

**Backward compat preserved:**
- `/api/ratings/rerank` endpoint unchanged
- `ratings.score` column preserved in DB
- `_rating.score` field preserved in API responses (now = `overall_development_potential`)

### 12.5 Phase 5 — Cleanup (Optional, Future)

- Drop `compute_strategic_score()` (superseded by topology metrics)
- Consolidate `compute_slot_score()` into topology engine
- Migrate `score_breakdown` to structured archetype breakdown only
- Archive `ratings` table (keep for historical queries, stop writing)

---

## 13. Architecture Diagrams

### 13.1 Data Flow

```
EDDN (real-time)                  Spansh (nightly)
     │                                  │
     ▼                                  ▼
eddn_listener.py               import_spansh.py
     │                                  │
     └──────────────┬───────────────────┘
                    ▼
          ┌─────────────────┐
          │    systems      │
          │    bodies       │
          │    stations     │
          └────────┬────────┘
                   │ rating_dirty=TRUE
                   ▼
          ┌─────────────────┐
          │ build_ratings   │◄── classify_bodies()
          │      .py        │    score_refinery()
          └────────┬────────┘    score_agriculture()
                   │             ...
                   ▼
          ┌─────────────────┐
          │    ratings      │   (EXISTING — preserved)
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ build_topology  │◄── estimate_body_slots()
          │      .py (NEW)  │    compute_topology_metrics()
          └────────┬────────┘    compute_system_pair_synergy()
                   │
                   ▼
          ┌─────────────────────────┐
          │ system_slot_topology    │ (NEW)
          │ economy_pair_synergy    │ (NEW)
          └─────────┬───────────────┘
                    │
                    ▼
          ┌──────────────────────────┐
          │ build_archetype_scores   │◄── compute_archetype_score()
          │        .py (NEW)         │    compute_buildability()
          └──────────┬───────────────┘    generate_structured_rationale()
                     │
                     ▼
          ┌────────────────────────────┐
          │ system_archetype_scores    │ (NEW)
          │ system_archetype_traits    │ (NEW)
          └──────────┬─────────────────┘
                     │
                     ▼
          ┌────────────────────────────┐
          │ mv_archetype_rankings      │ (MATERIALIZED VIEW)
          │ REFRESH CONCURRENTLY       │
          └──────────┬─────────────────┘
                     │
                     ▼
          ┌────────────────────────────┐
          │         FastAPI            │
          │  /api/archetypes/rankings  │
          │  /api/archetypes/rerank    │
          │  /api/archetypes/system    │
          │  /api/ratings/rerank (v3.1)│
          └──────────┬─────────────────┘
                     │
                     ▼
                  Redis
               (cache layer)
```

### 13.2 Score Composition

```
SYSTEM ARCHETYPE SCORE COMPOSITION
───────────────────────────────────────────────────────────

Body Composition          Topology             Pair Synergy
(0–60 pts)                (0–25 pts)           (0–15 pts)
    │                          │                    │
    │  ×  Purity Factor        │                    │
    │     (0.70 – 1.35)        │                    │
    │                          │                    │
    └──────────────────────────┴────────────────────┘
                               │
                       RAW SCORE (0–100)
                               │
                   ÷ Contamination Penalty
                   × Diversity Bonus (optional)
                               │
                  ARCHETYPE SCORE (0–100, per archetype)
                               │
             ┌─────────────────┴──────────────────┐
             │                                     │
      Primary Sort for                   Secondary Sort for
      archetype-specific                 tie-breaking within
      API queries                        archetype tier

              Combined across archetypes:
              OVERALL DEVELOPMENT POTENTIAL (0–100)
              (supporting metric, not primary ranking signal)
```

---

## 14. Caching Strategy

### 14.1 Redis Cache Keys

```python
# Archetype ranking results (long TTL — changes only after rebuild)
f"arch:rank:{archetype}:{region}:{min_score}:{limit}:{offset}"
TTL: 600s (10 min)

# System archetype detail (medium TTL)
f"arch:sys:{id64}"
TTL: 300s (5 min)

# Rerank results (short TTL — user-specific)
f"arch:rerank:{hash(id64s + weights)}"
TTL: 120s (2 min)

# Profile definitions (permanent until rebuild)
"arch:profiles"
TTL: 3600s (1 hour)

# Materialized view staleness flag
"mv:archetype_rankings:last_refresh"
TTL: no expiry — updated by build pipeline
```

### 14.2 Cache Invalidation

```python
# After build_archetype_scores.py completes:
async def invalidate_archetype_cache(redis):
    # Bump a version counter — all arch: keys are prefixed with version
    await redis.incr("arch:version")
    # Force MV refresh timestamp update
    await redis.set("mv:archetype_rankings:last_refresh",
                    datetime.now(UTC).isoformat())
```

---

## 15. Performance Recommendations

### 15.1 Index Strategy

```sql
-- Critical indexes for archetype queries
CREATE INDEX IF NOT EXISTS idx_arch_scores_refinery
    ON system_archetype_scores (score_refinery_industrial DESC)
    WHERE score_refinery_industrial >= 40 AND dirty = FALSE;

CREATE INDEX IF NOT EXISTS idx_arch_scores_hitech
    ON system_archetype_scores (score_hitech_tourism DESC)
    WHERE score_hitech_tourism >= 40 AND dirty = FALSE;

-- Composite: region + archetype (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_mv_arch_region_refinery
    ON mv_archetype_rankings (galaxy_region_id, score_refinery_industrial DESC)
    WHERE score_refinery_industrial >= 30;

-- Topology: fast contamination filter
CREATE INDEX IF NOT EXISTS idx_topo_contamination
    ON system_slot_topology (contamination_risk ASC)
    WHERE contamination_risk < 0.30;

-- Traits: multi-column fast filter
CREATE INDEX IF NOT EXISTS idx_traits_filter
    ON system_archetype_traits (has_elw, landable_count DESC, est_total_slots DESC);
```

### 15.2 Materialized View Refresh Strategy

```sql
-- CONCURRENT refresh does not block reads
-- Run after every full build_archetype_scores.py completion
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;

-- For dirty-only partial rebuilds:
-- 1. Update system_archetype_scores rows
-- 2. REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings
-- The CONCURRENTLY variant handles incremental updates efficiently.
```

### 15.3 Query Pattern for `GET /api/archetypes/rankings`

```sql
-- Efficient: hits mv_archetype_rankings, no join needed
SELECT
    id64, name, x, y, z,
    primary_archetype, score_refinery_industrial AS score,
    buildability_score, build_complexity,
    purity_score, contamination_risk, confidence,
    has_elw, elw_count, landable_count, est_total_slots,
    display_tags,
    -- Rationale comes from system_archetype_scores (separate fetch or JSONB in MV)
FROM mv_archetype_rankings
WHERE score_refinery_industrial >= $1
  AND ($2::smallint IS NULL OR galaxy_region_id = $2)
ORDER BY score_refinery_industrial DESC
LIMIT $3 OFFSET $4;

-- Estimated query time on 50M rows: 2–8ms (index scan on mv)
```

---

## 16. Implementation Phases

### Summary

| Phase | Duration | Scope | Risk | Breaking Changes? |
|-------|----------|-------|------|------------------|
| 1 | 2-3 days | Schema additions | None | No |
| 2 | 1 week | Build pipeline | Low | No |
| 3 | 1 week | Beta API endpoints | Low | No |
| 4 | 2 weeks | Frontend + primary API | Medium | Minor (additive) |
| 5 | Future | Cleanup | Low | Optional |

### Phase 1 Detail — Schema (2-3 days)
- [ ] Write `sql/012_topology_tables.sql`
- [ ] Write `sql/013_archetype_scores.sql`
- [ ] Write `sql/014_materialized_views.sql`
- [ ] Test migrations against staging DB
- [ ] Deploy to production

### Phase 2 Detail — Pipeline (1 week)
- [ ] Write `apps/importer/src/build_topology.py`
- [ ] Write `apps/importer/src/build_archetype_scores.py`
- [ ] Add topology functions to shared scoring module
- [ ] Add archetype definitions to shared module
- [ ] Run `build_topology.py --limit 100000` on staging
- [ ] Run `build_archetype_scores.py --limit 100000` on staging
- [ ] Validate archetype scores for known systems
- [ ] Full pipeline run on production

### Phase 3 Detail — API (1 week)
- [ ] Write `apps/api/src/routers/archetypes.py`
- [ ] Add Pydantic models for archetype responses
- [ ] Add profile definitions
- [ ] Write unit tests for archetype scoring
- [ ] Write API integration tests
- [ ] Deploy to staging

### Phase 4 Detail — Frontend (2 weeks)
- [ ] Archetype tier badge component (S/A/B/C/D)
- [ ] Structured rationale popover (positives / risks / build path)
- [ ] Tag pill components
- [ ] Profile selector UI (replacing raw weight sliders as default)
- [ ] Archetype score table per system
- [ ] Update search sort to use archetype scores
- [ ] Update system detail page
- [ ] A/B flag for gradual rollout

---

## 17. Risks & Unknowns

### 17.1 Data Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Slot estimates are significantly wrong | Medium | Medium | Label clearly as "estimated". Allow user correction via notes system. |
| Spansh body data missing for new colonised systems | Medium | Medium | EDDN updates `rating_dirty`; dirty rebuild picks up new body data |
| Frontier changes economy mechanics again | High | Medium | JSONB `traits` field absorbs new properties. Per-economy scores stored separately so individual score functions can be updated without full schema migration. |
| Archetype synergy constants are wrong | Medium | Low | Constants are in `pair_synergy_constants` DB table — can be updated without code change. |

### 17.2 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `REFRESH MATERIALIZED VIEW CONCURRENTLY` takes >5 min | Low | Medium | Add a timeout; fall back to reading from `system_archetype_scores` directly |
| `build_archetype_scores.py` adds 2-3h to nightly pipeline | Medium | Low | Runs in parallel with `build_clusters.py` where possible; dirty-only mode for EDDN updates |
| Users confused by archetype names | Low | Low | Clear labelling + tooltips; keep "overall" score as secondary context |

### 17.3 Known Gaps

1. **Exact slot counts** — Not available from any external data source. We must use estimates. This is the most significant known limitation. Consider exposing "Report Slot Count" user contribution feature in Phase 4.

2. **Construction state** — Which slots are already occupied in an active colonisation is not available externally. The scoring engine therefore always scores "theoretical maximum potential", not "available slots". This is appropriate for pre-colonisation planning but should be clearly communicated.

3. **Reserve level** — System reserve level (Pristine/Major/Common/Low/Depleted) affects Extraction economy value significantly but is not available per-body from Spansh body data. Available at system level from `galaxy_populated.json.gz`. Wire up to `system_archetype_traits.has_pristine_res`.

4. **Parent body grouping** — The Spansh `parents[]` array is available but not currently imported. Importing and processing it would significantly improve local-body group detection and nesting potential modelling. Add to `import_spansh.py` BODY_COLS in Phase 2.

---

## 18. Future-Proofing

### 18.1 Against Frontier Mechanic Changes

The redesign is structured to absorb future mechanic changes without schema rewrites:

| Future Change | Absorption Mechanism |
|--------------|---------------------|
| New economy type added | Add to `economy_type` enum + add `pair_synergy_constants` rows + add `score_new_economy` column to `ratings` |
| Slot counts changed by Frontier | Update slot estimation constants in `build_topology.py` + re-run pipeline |
| New body type affects economies | Add to `BODY_ECONOMY_ADDS` and `SLOT_ESTIMATES` dicts |
| New archetype needed | Add to `ARCHETYPE_DEFINITIONS` + add score column to `system_archetype_scores` |
| Strong/weak link mechanics changed | Update `compute_topology_metrics()` + re-run `build_topology.py --rebuild` |
| T3/T4 buildings added | Extend `buildability_score` formula; no schema change needed |
| New Frontier API endpoints | Drop-in replacement for slot inference with authoritative data |

### 18.2 JSONB Flexibility Contracts

The following JSONB fields are intentionally schema-free to absorb future additions:

- `system_archetype_traits.display_tags` — any new tag added without schema change
- `system_archetype_scores.rationale` — structured rationale can gain new fields
- `system_archetype_scores.score_breakdown` — new score components added without migration
- `system_slot_topology.body_slots` — per-body slot data extensible
- `system_slot_topology.topology_traits` — new topology properties without migration
- `bodies.traits` (existing) — body-level traits already flexible

### 18.3 Multi-System Expansion Planning (Future Phase 6)

The archetype engine naturally extends to multi-system planning:

```python
# Future: score a candidate CHAIN of systems
def score_expansion_chain(
    anchor_id64: int,
    candidate_id64s: list,
    chain_archetype: str,   # overall chain goal
) -> dict:
    """
    Score a proposed colonisation chain holistically.
    Each system is scored for its contribution to the chain's
    overall goal, not just its individual archetype score.
    """
    # Phase 6 implementation
```

### 18.4 AI-Assisted Recommendations (Future Phase 7)

The structured `rationale` JSONB and `score_breakdown` objects provide clean inputs for an LLM-assisted recommendation layer:

```python
# Future: generate natural language build recommendations
def generate_ai_build_plan(
    system_detail: dict,
    commander_preferences: dict,
) -> str:
    # Use structured rationale + archetype scores as context
    # for an LLM to generate a step-by-step build guide
```

---

## Appendix A: New Script Run Order

```
nightly:
  import_spansh.py --all
  build_grid.py
  build_ratings.py              ← existing
  build_topology.py             ← NEW (reads from bodies + ratings)
  build_archetype_scores.py     ← NEW (reads from bodies + ratings + topology)
  build_clusters.py             ← existing
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings

dirty cycle (every 5 min):
  build_ratings.py --dirty
  build_topology.py --dirty
  build_archetype_scores.py --dirty
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings
```

## Appendix B: Pydantic Models Summary

```python
# New models to add to apps/api/src/models.py

class ArchetypeRerankWeights(BaseModel):
    purity:       float = 0.30
    buildability: float = 0.25
    slots:        float = 0.20
    expansion:    float = 0.15
    logistics:    float = 0.10

class ArchetypeRerankRequest(BaseModel):
    id64s:     List[int]
    archetype: Optional[str]                  = None
    weights:   Optional[ArchetypeRerankWeights] = None
    profile:   Optional[str]                  = None

class ArchetypeScore(BaseModel):
    model_config = ConfigDict(extra='allow')
    score:            float
    tier:             str            # S/A/B/C/D
    buildability_score: float
    build_complexity:   str
    purity_score:     float
    contamination_risk: float
    confidence:       float
    rationale:        Optional[Any]  # structured JSONB
    tags:             list[str]

class SystemArchetypeResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id64:                          int
    name:                          str
    primary_archetype:             str
    secondary_archetype:           Optional[str]
    overall_development_potential: float
    archetypes:                    dict[str, ArchetypeScore]
    topology:                      Optional[Any]
    tags:                          list[str]
    confidence:                    float

class ArchetypeRankingsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    archetype:       str
    archetype_label: str
    results:         list[Any]
    total:           int
    count:           int
    source:          str
    query_ms:        Optional[int]
```

## Appendix C: SQL File Naming Convention

```
sql/001_schema.sql              existing
sql/002_indexes.sql             existing
sql/003_functions.sql           existing
sql/004_ratings_v31.sql         existing
sql/005_map_indexes.sql         existing
sql/006_score_history.sql       existing
sql/007_profile_sync.sql        existing
sql/008_body_filter_aggregates.sql existing
sql/009_map_materialised_views.sql existing
sql/010_sync_key_scoping.sql    existing
sql/011_autocomplete_index.sql  existing
sql/012_topology_tables.sql     NEW (Phase 1)
sql/013_archetype_scores.sql    NEW (Phase 1)
sql/014_archetype_mv.sql        NEW (Phase 1)
```

---

*Document version: 4.0 | Generated: 2026-05-10 | ED-Finder Colonisation Engine Redesign*
