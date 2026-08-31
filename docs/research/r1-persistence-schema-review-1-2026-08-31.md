# R1 Persistence / Storage Schema — Review 1

Date: 2026-08-31
Status: pre-migration design only
Branch: `chatgpt-ed-new-ops-requests`

## 1. Purpose

Define what R1/VNext must persist so Finder search, programme-relative assessment, System Detail, saved plans and later Build Pack/Audit can dovetail without recreating a monolithic ratings table.

This review does **not** authorize migrations or table creation.

## 2. Design rule

Do not duplicate canonical galaxy facts into R1.

The normalized V3 canonical generation remains the factual store for systems, bodies, rings, signals, stations, source lineage and freshness. R1 should persist only information that is:

1. missing from the canonical model and belongs there permanently;
2. expensive enough to materialize for Finder performance but completely rebuildable;
3. a versioned R1 model/programme definition needed for reproducibility; or
4. user/project state that must survive beyond one request (saved plan, assessment, Build Pack/audit continuity).

Transient search requests, comparison contexts and ordinary candidate assessments should not create database rows.

## 3. Upstream canonical correction — not an R1 ratings table

### `v3_vocab.body_subtype`

Required in a future canonical generation.

Suggested fields:

- `body_subtype_id` PK
- `body_type_id` FK to `v3_vocab.body_type`
- `public_code`
- `display_name`
- `active`

Purpose: preserve explicit source body identity such as:

- High metal content world
- Metal-rich body
- Rocky body
- Icy body
- Water world
- Earth-like world
- Ammonia world
- gas-giant variants
- Black Hole
- Neutron Star
- White Dwarf variants
- other exact source subtypes

Do not derive this identity from atmosphere/composition/physics.

### Future canonical `bodies.body_subtype_id`

Add to the next immutable canonical generation, not by mutating the retained generation in place.

This fixes a source-model omission rather than creating an R1 workaround table.

Until that future generation exists, bounded research may use an explicitly provenance-labelled external identity overlay.

## 4. Existing stores to reuse

### Normalized V3 generation

Reuse directly for factual evidence:

- systems;
- bodies;
- body signals and completeness;
- rings/reserves;
- stations/placement/economies/services;
- source/run/freshness/lifecycle metadata.

### `v3_source` / `v3_meta`

Reuse for source lineage, generation identity and publication/effective history.

### existing `evidence_records`

Reuse for imported/manual/observational evidence that does not belong in the canonical generation. Do not turn it into the typed R1 body model.

### existing `derived_features`

Potentially reuse for experimental/research derived features, but do not make it the authoritative Finder comparison contract. Its generic JSONB shape is not a substitute for typed search-capability or saved-plan state.

## 5. New R1 tables — proposed minimum

### A. `r1_model_revision`

Small registry table.

Purpose: immutable reproducibility identity for an assessment/search capability model.

Suggested fields:

- `model_revision_id` text PK
- `friendly_version`
- `code_commit_sha`
- `model_sha256`
- `canonical_contract_revision`
- `mechanics_revision_id`
- `created_at`
- `effective_from`
- `effective_to` nullable
- `status` (`experimental`, `shadow`, `active`, `retired`)
- `notes`

No score weights or arbitrary mechanics need to be stored as mutable row values. The row identifies immutable code/config.

### B. `r1_mechanics_revision`

Small registry table, independent of product-fit strategy.

Suggested fields:

- `mechanics_revision_id` text PK
- `game_version_or_patch`
- `rules_sha256`
- `source_evidence_refs` JSONB or array
- `effective_from`
- `effective_to` nullable
- `status`
- `notes`

Purpose: allow a mechanics rule to change without pretending the player-preference model changed, and vice versa.

### C. `r1_programme_revision`

Small immutable registry of programme/template contracts such as `P-ER-01`.

Suggested fields:

- `programme_id`
- `programme_revision`
- `programme_name`
- `definition_sha256`
- `definition_json` JSONB
- `created_at`
- `status`

Primary key `(programme_id, programme_revision)`.

This holds explicit player objective/requirements, not a universal ranking formula.

### D. `r1_system_capability_current`

Rebuildable Finder acceleration table: **not a rating table**.

One current row per system for the active capability projection.

Purpose: let factual filters and the first stage of Finder candidate selection work against ~198M systems without running detailed body allocation for the whole galaxy.

Suggested identity/version columns:

- `system_id64` PK
- `canonical_generation_id`
- `capability_revision`
- `model_revision_id`
- `evidence_snapshot_sha256`
- `built_at`

Suggested typed/indexable capability families (exact list frozen in Review 2):

- explicit canonical body-identity counts (ELW, WW, HMC, metal-rich, rocky, icy, true Ammonia, gas-giant/exotic classes as needed);
- modifier/presence counts kept separate from base identity (terraformable, geological, biological, rings, atmosphere, tidal, volcanism);
- body-data completeness / evidence-disposition flags;
- predicted surface-capacity summary and count of Unknown predictions;
- current-patch orbital-capacity facts where known;
- distance/logistics summary fields needed for cheap prefiltering;
- compact factual minima/maxima/counts used by Finder filters.

Hard rule: no `overall_score`, no suggested economy, no programme Plan Fit, no pair resilience.

The table is disposable/rebuildable from canonical facts + immutable capability revision. Historical copies are not required for every generation.

### E. `r1_saved_plan`

Persistent only when a user explicitly chooses/saves a plan or a Build Pack needs continuity.

Suggested fields:

- `plan_id` UUID/content ID PK
- optional owner/account reference
- `system_id64`
- `programme_id`
- `programme_revision`
- `model_revision_id`
- `mechanics_revision_id`
- `canonical_generation_id`
- `evidence_snapshot_sha256`
- `plan_state` (`draft`, `selected`, `build_pack`, `archived`)
- `carrier_mode`
- `created_at`
- `updated_at`

Search-generated candidate plans remain ephemeral until explicitly saved/selected.

### F. `r1_plan_node`

Typed structure for the concrete proposed build.

Suggested fields:

- `plan_node_id` PK
- `plan_id` FK
- `node_key` stable within plan
- `node_kind` (station/orbital/surface facility/support node/etc.)
- `body_pk` nullable where applicable
- `parent_node_id` nullable
- `facility_type_code`
- `intended_role_code`
- `locality_key`
- `ordinal`
- `metadata_json` only for non-core extension data

Core fields required for allocation/link reasoning should be typed, not buried in JSON.

### G. `r1_plan_allocation`

Explicit scarce-resource/requirement allocation. This is what prevents fake flexibility/double use.

Suggested fields:

- `allocation_id` PK
- `plan_id` FK
- `requirement_id`
- `resource_kind`
- `resource_key` (body/node/evidence/capacity unit)
- `plan_node_id` nullable FK
- `allocation_quantity` nullable
- `allocation_state`
- `evidence_refs` JSONB/array

Unique constraints must stop the same exclusive resource from being credited twice unless the programme/mechanics contract explicitly allows sharing.

### H. `r1_plan_assessment`

Immutable/versioned assessment result for saved plans, Build Packs, golden/calibration runs, or explicit audit snapshots. **Do not write one row per ordinary Finder result.**

Suggested fields:

- `assessment_id` content-addressed/UUID PK
- `plan_id` nullable FK (nullable for frozen golden/research assessments)
- `system_id64`
- `programme_id`
- `programme_revision`
- `model_revision_id`
- `mechanics_revision_id`
- `canonical_generation_id`
- `evidence_snapshot_sha256`
- `candidate_plan_sha256`
- `carrier_mode`
- `assessment_state`
- `evidence_disposition`
- `reserve_capacity`
- `logistics_state`
- `plan_pair_resilience` nullable, explicitly plan-relative
- `plan_fit` nullable
- `fit_strategy_revision` nullable
- `result_sha256`
- `trace_json` JSONB containing the deterministic full assessment payload
- `created_at`

Top-level fields are indexed/queryable; the immutable deterministic trace carries complete explainability without prematurely exploding every trace element into dozens of tables.

### I. `r1_assessment_condition` — optional at first

Only create if UI/analytics need relational querying of conditions independently of `trace_json`.

Potential fields:

- `assessment_id`
- `condition_id`
- `severity`
- `action`
- `reason`
- evidence/requirement/allocation refs
- stable ordinal

Review 2 should decide whether this is needed in R1 or can remain inside deterministic trace JSON initially.

## 6. Tables specifically **not** proposed

Do not create:

- `r1_ratings`
- `r1_economy_scores`
- `r1_system_value`
- global programme score columns per system
- a table storing Plan Fit for every system/programme combination
- a system-level pair-stability/resilience table
- an R1 duplicate of every body row
- an R1 duplicate provenance/source-run hierarchy
- a row for every transient Finder comparison
- a persistent search-context table unless saved searches become a separately approved feature.

## 7. Search/assessment storage flow

```text
canonical V3 facts
        +
body subtype identity
        ↓
rebuildable r1_system_capability_current
        ↓
Finder factual filtering / candidate narrowing
        ↓
bounded detailed body read for candidate systems
        ↓
ephemeral programme plan + assessment
        ↓
rank results in selected comparison context
        ↓
user opens/refines candidate
        ↓
(no write yet)
        ↓
user explicitly saves/selects plan
        ↓
r1_saved_plan + nodes + allocations
        ↓
immutable r1_plan_assessment snapshots as needed
        ↓
Build Pack / later observed audit
```

## 8. Why this dovetails Finder and Ratings

Finder uses the same factual capability projection that detailed assessment uses, but only materializes context-independent facts needed to narrow the galaxy cheaply.

Programme-specific value remains computed from explicit programme + allocation + plan. It is not pre-baked into the system row.

This permits:

- factual searches with no universal score;
- fast candidate discovery;
- purpose-specific comparison/ranking;
- exact search-to-detail semantic continuity;
- future programme additions without rerating the galaxy into a new universal number;
- rebuilding capability summaries when canonical/mechanics revisions change.

## 9. Review 2 questions to freeze before migrations

1. Exact `body_subtype` vocabulary and source-normalization rules.
2. Exact typed columns/indexes in `r1_system_capability_current`.
3. Whether capability cache is a normal table, materialized generation, or swap-built shadow table.
4. Exact lifecycle/rebuild/cutover strategy for ~198M systems.
5. Exact model/mechanics/programme registry constraints.
6. Whether `r1_assessment_condition` is relational in R1 or remains in immutable `trace_json`.
7. Saved-plan ownership/privacy boundaries.
8. Exact allocation uniqueness/sharing constraints.
9. Which assessment types are allowed to persist (saved plan, Build Pack, golden/calibration) and which must remain ephemeral.
10. Retention policy for old assessments and model revisions.
11. Migration/file allow-list and rollback procedure.

Until Review 2 is accepted, no tables or migrations should be created.
