# ED-Finder V3 Search, Spatial and Derived-Data Decision

**Status:** proposed V3 authority; becomes authoritative only when reviewed and merged
**Scope:** PostgreSQL 18 search, spatial indexing, map aggregation, clustering, Ratings v3.4 migration, archetype judgement, derived-data generation and publication

## Why this decision exists

The retained production V3 database is a namespaced canonical-generation model. The current published canonical generation contains `systems`, `bodies` and `stations` under a generation-specific schema and uses `v3_meta.current_canonical_generation` to identify the live canonical generation. The historical application/search implementation instead assumes unqualified `public.systems`, `ratings`, old map materialisations and old coordinate names.

This decision does not recreate the historical `public` schema. It defines a clean V3 derived-data architecture around the retained canonical-generation model.

The design goal is that future changes to search requirements, grid sizes, map LOD, clustering algorithms, scoring algorithms or canonical generations require a **rebuild and publication of derived data**, not another application-wide schema redesign.

## Non-negotiable boundaries

1. **Canonical source data stays canonical.** Generation schemas such as `v3_gen_<generation_key>` remain immutable/source-oriented and are never reshaped merely to suit one UI.
2. **Derived data is disposable and reproducible.** Ratings, archetypes, search projections, spatial cells and clusters may always be rebuilt from named canonical inputs and named rule versions.
3. **Exact spatial truth is coordinates, not cells.** Elite `x/y/z` light-year coordinates remain authoritative. Grid/cell identifiers are accelerators or aggregation keys only.
4. **Finder owns querying and ranking.** The renderer does not calculate ranking, cluster membership or scoring.
5. **Clusters are outputs, not the search index.** A clustering algorithm may change without changing exact spatial search or canonical identity.
6. **No hidden `search_path` contract.** Application-facing SQL uses explicit stable V3 application/derived relations.
7. **Publication is atomic.** A partial rebuild must never become the current derived generation.

## 1. Derived-generation identity

Add an explicit derived-generation identity linked to one canonical generation.

Conceptually:

```text
v3_meta.derived_generation
- derived_generation_id UUID PK
- canonical_generation_id UUID FK
- generation_key TEXT UNIQUE
- scorer_version TEXT
- archetype_version TEXT
- search_projection_version TEXT
- spatial_pyramid_version TEXT
- cluster_algorithm_version TEXT
- lifecycle_state BUILDING|VALIDATING|READY|PUBLISHED|RETIRED|FAILED
- manifest_sha256 BYTEA
- validation_receipt JSONB
- created_at / validated_at / published_at / retired_at / failed_at

v3_meta.current_derived_generation
- singleton BOOLEAN PK CHECK(singleton)
- derived_generation_id UUID UNIQUE FK
- publication_sequence BIGINT
- published_at TIMESTAMPTZ
```

A derived generation is immutable once published. Recalculation produces another generation and publication flips only the current pointer after validation.

## 2. Exact spatial search: PostgreSQL `cube` + GiST

Do not make a coarse grid the primary Finder search primitive.

For the stable application search projection, retain numeric coordinates and also expose a 3-D `cube` point:

```text
position_ly = cube(ARRAY[x_ly, y_ly, z_ly])
```

Create a GiST index on `position_ly`.

Use it for:

- nearest-system / k-nearest-neighbour queries;
- search-around-here;
- bounded-radius candidate retrieval;
- route and local-neighbour primitives;
- map target lookup where exact distance matters.

A radius query first narrows with an index-supported cube/bounds predicate and then applies exact Euclidean distance. KNN uses the cube Euclidean distance ordering operator.

The raw numeric coordinates remain in the projection because they are the public/API truth and are useful for vector calculations and rendering.

### Why not PostGIS as the baseline

ED-Finder needs ordinary 3-D Euclidean galactic coordinates, not Earth geography or GIS topology. PostgreSQL's supplied `cube` type directly supports N-dimensional Euclidean distance and GiST KNN. PostGIS may still be justified later by a separate requirement, but it is not required merely to search the Galaxy.

## 3. Search projection

Create a generation-scoped application search projection containing only facts required for high-frequency Finder/Explore/Inspect discovery.

Conceptually:

```text
v3_derived.system_search
- derived_generation_id
- id64
- name
- x_ly / y_ly / z_ly
- position_ly cube
- galaxy_region_id
- main-star summary required by product
- body-count / factual summary inputs required by Finder
- current colonisation factual summary when authoritative
- source/freshness fields needed for confidence
PRIMARY KEY (derived_generation_id, id64)
```

Indexes are workload-driven and may include:

- GiST `position_ly`;
- name prefix/trigram search;
- `galaxy_region_id`;
- explicit ranking/filter columns proven by Search requirements.

Do not bake every later feature into this row. Heavy domain outputs live in their own derived relations and are joined only when the query needs them.

## 4. Ratings v3.4 remains a scoring contract, not the whole judgement model

Retain the accepted **Ratings v3.4 Best-Build Potential** semantics:

- overall 0-100 best-build potential;
- seven economy suitability scores including Extraction;
- complementary top pair and pair score;
- confidence;
- rationale;
- score dimensions: slots, strategic, safety, terraforming, diversity.

Migrate those semantics to a versioned derived relation rather than recreating the old historical `ratings` table contract verbatim.

Conceptually:

```text
v3_derived.system_rating
- derived_generation_id
- system_id64
- scorer_version
- best_build_score
- score_agriculture
- score_refinery
- score_industrial
- score_hightech
- score_military
- score_tourism
- score_extraction
- top_pair_a / top_pair_b / pair_score
- confidence
- rationale
- dimensions JSONB (or typed columns when the final scorer implementation proves they are hot query fields)
- computed_at
PRIMARY KEY (derived_generation_id, system_id64)
```

The scorer reads normalized canonical V3 body/vocabulary facts through an explicit adapter. Historical assumptions such as old body flags or enum types are not silently recreated.

## 5. Archetype judgement is a separate derived layer

Do not overload Ratings v3.4 to become every later judgement.

Archetype judgement consumes named rating outputs plus named mechanics/rule inputs and writes a separate versioned result:

```text
v3_derived.system_archetype
- derived_generation_id
- system_id64
- archetype_version
- primary_archetype
- secondary_archetype
- archetype_confidence
- overall_development_potential
- buildability_score
- build_complexity
- purity_score
- contamination_risk
- estimated_total_slots
- display_tags
- computed_at
PRIMARY KEY (derived_generation_id, system_id64)
```

This resolves the current roadmap ambiguity cleanly:

- Ratings v3.4 remains the accepted suitability/best-build scorer.
- Archetype judgement is a separately versioned interpretation layer.
- Finder may rank using either or both through an explicit ranking profile.

## 6. Finder ranking profiles are versioned

Search ranking must not be hard-coded as an accidental SQL expression spread through routers.

Define a named ranking-profile version in code/manifest. A profile declares which derived fields participate and how they are ordered/weighted.

Examples may include:

- `distance`;
- `best_build`;
- `development`;
- later economy-specific or programme-specific ranking.

The API response states the active ranking/profile version where operationally useful. Changing ranking logic does not require rewriting canonical data.

## 7. Map data: a multi-resolution spatial pyramid

Do not choose one permanent grid cell size.

Build a **multi-resolution 3-D cell pyramid** from exact system coordinates. Cells are an aggregation/LOD mechanism only.

Use power-of-two hierarchical cells (octree-style) with a deterministic integer key, preferably a Morton/Z-order code or equivalent stable hierarchical encoding. Store the level and cell bounds explicitly enough that the encoding can be changed by a later pyramid version without changing public APIs.

Conceptually:

```text
v3_spatial.cell_level
- spatial_pyramid_version
- level
- cell_size_ly
- intended_scale / target_budget metadata

v3_spatial.cell_summary
- derived_generation_id
- spatial_pyramid_version
- level
- cell_key
- min/max x/y/z or deterministic cell origin
- system_count
- centroid_x/y/z
- factual summary counters required at that LOD
- optional derived score summaries required by named map layers
- representative_system_id64 when the selection rule is explicit/versioned
PRIMARY KEY (derived_generation_id, spatial_pyramid_version, level, cell_key)
```

The map chooses a level from semantic zoom, viewport volume and target-count budget. It does not assume that one cell size fits Galaxy, regional and local views.

### Relationship to existing `grid_x/grid_y/grid_z/macro_grid_key`

The current canonical generation already contains these values. Preserve them as existing canonical-generation fields and evidence. Do **not** make them the permanent V3 Search/Grid/Cluster API contract unless benchmarks prove that exact encoding is the best pyramid implementation.

The new derived pyramid may reuse their calculation if it matches the chosen version, but the public contract is level + cell identity + bounds/summary, not those historical column names.

## 8. Clusters are independently versioned derived products

Cluster membership is domain analysis, not spatial truth and not a renderer responsibility.

Store cluster output separately from the cell pyramid:

```text
v3_spatial.cluster_run
- derived_generation_id
- cluster_run_id
- owner/domain
- algorithm
- algorithm_version
- parameters JSONB
- lifecycle / validation receipt

v3_spatial.cluster
- cluster_run_id
- cluster_id
- centroid / bounds
- member_count
- summary / provenance

v3_spatial.cluster_member
- cluster_run_id
- cluster_id
- system_id64
- membership_score/confidence when meaningful
PRIMARY KEY (cluster_run_id, cluster_id, system_id64)
```

Consequences:

- DBSCAN/HDBSCAN/domain-specific or later algorithms can replace one another without changing Finder's exact spatial index.
- Different domains may publish different cluster sets.
- A cluster can be rebuilt or retired independently.
- Map hulls/visualisations are projections of cluster membership, never the source of membership truth.

## 9. Stable application boundary

The application must not reference generation-specific canonical schema names.

Expose a stable `v3_app` boundary through reviewed SQL views/functions or an equally explicit stable query layer. It resolves the current derived generation and presents the API contract needed by FastAPI.

Examples:

```text
v3_app.system_search
v3_app.system_rating
v3_app.system_archetype
v3_app.system_detail
v3_app.map_cells(...)
v3_app.cluster_members(...)
```

Whether the implementation uses stable views, SQL functions, or queries that bind the current derived-generation ID is an implementation choice, but publication semantics must remain atomic and generation-aware.

No production application query may depend on whichever schema happens to appear first in `search_path`.

## 10. Rebuild and publication pipeline

Order is explicit:

1. Resolve the current canonical generation and record its immutable identity.
2. Create a BUILDING derived generation.
3. Build the factual search projection.
4. Build Ratings v3.4-compatible scoring from normalized V3 inputs.
5. Build archetype judgement using its own version.
6. Build all configured spatial-pyramid levels.
7. Build configured cluster runs.
8. Validate row counts, referential integrity, coordinate invariants, score ranges, reproducibility samples, query plans and bounded performance.
9. Produce a manifest/checksum and validation receipt.
10. Mark READY.
11. Atomically publish `current_derived_generation`.
12. Retain at least the previous compatible derived generation until rollback eligibility is known.

Failure before publication leaves the previous generation current.

## 11. Resource and operational rules

A full derived bootstrap over the Galaxy is a bounded operator job, not API startup work.

Require:

- resumable/chunked build stages;
- bounded concurrency and memory;
- statement and lock policy appropriate for offline derived builds;
- progress receipts that use real or explicitly unknown totals;
- no long blocking DDL on canonical generation tables;
- index construction staged after bulk load where benchmarks support it;
- `ANALYZE` before validation benchmarks;
- explain-plan and latency evidence for representative exact-radius, KNN, autocomplete, galaxy-map, regional-map and local-map queries;
- deterministic version/manifests sufficient to reproduce a generation.

## 12. What this deliberately avoids

- Recreating V2 `public.*` merely to keep old SQL running.
- Treating one `grid_cell_id` size as the permanent spatial architecture.
- Coupling cluster membership to map-cell membership.
- Running rating logic inline on request paths.
- Letting the renderer calculate ranking, scores or clusters.
- Treating a materialized map view as canonical truth.
- Making a scorer rewrite require a canonical-data rebuild.
- Making a canonical-generation publication immediately invalidate the previous application release without explicit compatibility evidence.

## 13. Decisions to benchmark, not bikeshed

The architecture above is stable while these implementation values remain benchmark-driven:

- exact spatial-pyramid cell sizes/levels;
- Morton/Z-order encoding details;
- whether generated or explicitly stored `cube` position performs best;
- name-index strategy and thresholds;
- which rating/archetype fields deserve dedicated columns versus JSON detail;
- cell summary payloads at each semantic LOD;
- cluster algorithm and parameters per domain;
- retained derived-generation count.

These are versioned configuration/algorithm decisions, not reasons to reopen the architecture.

## Acceptance bar

Before this becomes production data authority, prove on production-like scale that:

- exact 3-D distance and KNN queries use an index and meet the Search latency budget;
- galaxy/regional/local map queries are bounded by a target-count contract rather than raw catalogue size;
- a pyramid-version change requires only rebuilding derived rows;
- a cluster-algorithm change requires only rebuilding cluster runs;
- a scorer/archetype version change does not mutate canonical source facts;
- publishing a failed/partial build is impossible;
- API queries resolve an explicit published derived generation;
- canonical generation, derived generation, scorer, archetype, pyramid and cluster versions are visible in operational receipts.
