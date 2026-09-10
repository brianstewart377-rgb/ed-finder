# ED-Finder V3 Search, Spatial and Derived-Data Decision

**Status:** merged V3 architecture authority (PR #645); implementation and production publication require their own validation
**Scope:** PostgreSQL 18 search, spatial indexing, map aggregation, clustering, Ratings V4, archetype judgement, derived-data generation and publication

## Why this decision exists

The retained production V3 database is a namespaced canonical-generation model. The current canonical generation supplies system/body/station truth while the historical application assumes an old `public.*` search/ratings/map schema.

V3 will not recreate that historical schema. It will build a clean, versioned application/derived layer from the currently published canonical generation.

The design goal is simple: future changes to search requirements, map cell sizes, LOD policy, clustering algorithms, scoring rules or canonical generations must normally require a **derived rebuild and atomic publication**, not another application-wide schema redesign.

The detailed mechanics evidence for Ratings V4 is in [`ratings-v4-mechanics-evidence.md`](ratings-v4-mechanics-evidence.md).

## Non-negotiable boundaries

1. Canonical V3 generation schemas remain source truth and are not reshaped for one UI.
2. Search projections, ratings, archetypes, map cells and clusters are reproducible derived data.
3. Exact spatial truth is Elite `x/y/z` light-year coordinates, never a grid cell.
4. Finder owns querying/ranking. The renderer does not calculate rankings, scores or cluster membership.
5. Clusters are domain-derived outputs, not the search index.
6. Application SQL uses explicit V3 relations; no hidden `search_path` contract.
7. A partial/failed derived build can never become current.
8. Ratings V3.4 is historical/regression evidence. **Ratings V4 is the target scoring authority.**

## 1. Derived-generation identity

A derived generation is linked to one canonical generation and records every rule/model family that can change independently.

Conceptually:

```text
v3_meta.derived_generation
- derived_generation_id UUID PK
- canonical_generation_id UUID FK
- generation_key TEXT UNIQUE
- mechanics_version TEXT
- scorer_version TEXT
- archetype_version TEXT
- ranking_version TEXT
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

Published derived generations are immutable. Recalculation creates a new generation; publication flips a single current pointer after validation.

## 2. Exact spatial search: PostgreSQL `cube` + GiST

Do not make a coarse grid the primary Finder search primitive.

The stable system-search projection retains numeric coordinates and a 3-D PostgreSQL `cube` point:

```text
position_ly = cube(ARRAY[x_ly, y_ly, z_ly])
```

A GiST index on `position_ly` supports:

- K-nearest-neighbour queries;
- search/find around here;
- bounded-radius candidate retrieval;
- route/local-neighbour primitives;
- exact map target lookup.

Radius queries use an index-supported bounds/cube predicate followed by exact Euclidean distance. Raw numeric LY coordinates remain the API/rendering truth.

### Why not PostGIS by default

The problem is 3-D Euclidean galactic space, not terrestrial geography/GIS topology. PostgreSQL `cube` directly supports N-dimensional Euclidean distance and GiST KNN. PostGIS remains available if a later requirement independently justifies it.

## 3. Stable search projection

Generation-scoped derived search data contains only hot Finder/Explore/Inspect facts.

```text
v3_derived.system_search
- derived_generation_id
- id64
- name
- x_ly / y_ly / z_ly
- position_ly cube
- galaxy_region_id
- required main-star summary
- required factual body/system summary
- source/freshness/completeness fields
PRIMARY KEY (derived_generation_id, id64)
```

Indexes are driven by measured workloads: spatial GiST, autocomplete/name, region and proven hot filter/ranking fields.

Heavy judgement/domain outputs stay in separate relations.

## 4. Ratings V4 scoring model

V4 separates mechanics, suitability, specialisation, archetype judgement and Finder preference.

The pipeline is:

```text
canonical facts
  -> versioned mechanics features
  -> seven independent economy potentials
  -> economy specialisation quality
  -> archetype judgement
  -> Finder ranking profile
```

### Seven raw economy scores

V4 retains the seven user-facing economy families:

- Agriculture
- Refinery
- Industrial
- High Tech
- Military
- Tourism
- Extraction

Each raw score answers only:

> How naturally and strongly can the known physical/system mechanics support this economy?

Raw scores are **absolute mechanics-based 0-100 values**, not galaxy percentiles and not query-specific rankings.

### Potential and specialisation are separate

Each economy produces at least:

- `potential_score` — natural/evidenced support for the economy;
- `specialisation_quality` — how cleanly a build can make the economy dominant/top-two without unwanted competing local influence;
- `evidence_completeness`;
- `confidence`;
- contributor/explanation payload;
- mechanics/scorer versions.

The August 2025 top-two-economy protection means V4 does **not** attenuate one honest raw economy score merely because other economies are also strong.

### Mechanics evidence

Inheritance, local-body modifiers, strong-link modifiers, reserve level, rings, biologicals, geologicals, volcanism, terraformability, tidal-lock rules and evidence discrepancies are governed by `ratings-v4-mechanics-evidence.md`.

Important consequences include:

- ELW can inherit Agriculture/High Tech/Military/Tourism, but these are not equal suitability evidence; Agriculture/Tourism/High Tech have additional positive mechanics while Military does not.
- Geologicals and volcanism are different mechanics.
- reserve level is a first-class Extraction/Industrial/Refinery feature.
- Military raw potential is conservative and does not absorb generic strategic judgement.
- generic body diversity, compactness and distance from arrival are not raw economy mechanics.
- unknown evidence is not scored as known absence.

Conceptually:

```text
v3_derived.system_economy_rating
- derived_generation_id
- system_id64
- mechanics_version
- scorer_version
- economy
- potential_score
- specialisation_quality
- evidence_completeness
- confidence
- explanation JSONB
- computed_at
PRIMARY KEY (derived_generation_id, system_id64, economy)
```

A compact one-row-per-system projection may additionally expose the seven scores for hot Finder queries, but the semantic authority remains explicit and versioned.

## 5. Headline judgement and archetypes

V4 does not define a universal raw-system score by simply blending unrelated features.

The headline **Best Colony Potential** is an archetype-level judgement: the highest justified potential across viable versioned colony archetypes, with the winning archetype named.

Examples of archetype families may include:

- Agriculture/Tourism Paradise
- Extraction/Refinery Mining Hub
- Refinery/Industrial Megacomplex
- High-Tech/Research Hub
- Military/Industrial Stronghold
- flexible multi-role / expansion-capital patterns

Archetype logic may consume:

- economy potential;
- specialisation quality;
- explicit economy synergy/pair rules;
- buildable capacity/slot evidence;
- accessibility/compactness where relevant;
- strategic/domain features;
- confidence/completeness.

Those factors must not leak backwards and corrupt raw economy semantics.

Conceptually:

```text
v3_derived.system_archetype
- derived_generation_id
- system_id64
- archetype_version
- archetype_key
- archetype_score
- confidence
- explanation JSONB
- computed_at
PRIMARY KEY (derived_generation_id, system_id64, archetype_key)
```

A separate summary projection may expose primary/secondary archetype and Best Colony Potential for hot queries.

## 6. Finder ranking profiles

Finder ranking is query-specific and separately versioned.

A ranking profile may combine, as appropriate:

- selected economy potential;
- selected archetype score;
- Best Colony Potential;
- distance;
- confidence/completeness;
- accessibility;
- user/query constraints;
- later programme-specific factors.

Ranking logic is not scattered as accidental router SQL and does not mutate stored mechanics truth.

## 7. Map data: multi-resolution spatial pyramid

Do not choose one permanent grid-cell size.

Build a **multi-resolution 3-D spatial pyramid** from exact system coordinates. Cells exist only for aggregation/LOD.

Use hierarchical power-of-two cells (octree-style), with a deterministic key such as Morton/Z-order or an equivalent encoding. Encoding details are themselves versioned.

```text
v3_spatial.cell_level
- spatial_pyramid_version
- level
- cell_size_ly
- intended_scale / target-budget metadata

v3_spatial.cell_summary
- derived_generation_id
- spatial_pyramid_version
- level
- cell_key
- deterministic bounds/origin
- system_count
- centroid_x/y/z
- factual summary counters for that LOD
- explicitly versioned derived score/archetype summaries required by map layers
- representative_system_id64 where the selection rule is explicit
PRIMARY KEY (derived_generation_id, spatial_pyramid_version, level, cell_key)
```

The map chooses level from semantic zoom, viewport volume and target-count budget rather than assuming one grid serves Galaxy, regional and local use.

### Existing `grid_x/grid_y/grid_z/macro_grid_key`

Preserve these canonical-generation fields as existing evidence. Do not make their exact encoding the permanent V3 Search/Grid/Cluster API contract unless benchmarking proves it is the right pyramid implementation.

Changing cell sizes/encoding is a derived rebuild, not a schema redesign.

## 8. Clusters are independent derived products

Cluster membership is domain analysis, not spatial truth.

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
- membership_score/confidence where meaningful
PRIMARY KEY (cluster_run_id, cluster_id, system_id64)
```

DBSCAN/HDBSCAN/domain-specific or later approaches can replace one another without changing exact spatial search. Different domains may publish different cluster sets. Map hulls are projections of membership, never membership authority.

## 9. Stable application boundary

FastAPI must not reference generation-specific canonical schema names.

Expose an explicit stable `v3_app` boundary, for example:

```text
v3_app.system_search
v3_app.system_economy_rating
v3_app.system_archetype
v3_app.system_detail
v3_app.map_cells(...)
v3_app.cluster_members(...)
```

Views/functions/query helpers resolve the currently published derived generation explicitly.

## 10. Rebuild and publication pipeline

Order is explicit:

1. Resolve and record immutable current canonical generation identity.
2. Create a BUILDING derived generation.
3. Build factual system/search features.
4. Build versioned mechanics features.
5. Build Ratings V4 economy potential/specialisation.
6. Build archetype judgement and headline Best Colony Potential.
7. Build configured spatial-pyramid levels.
8. Build configured cluster runs.
9. Validate counts, referential integrity, coordinate invariants, score ranges, evidence completeness, reproducibility samples, query plans and bounded performance.
10. Produce manifest/checksum + validation receipt.
11. Mark READY.
12. Atomically publish `current_derived_generation`.
13. Retain at least the previous compatible derived generation for rollback.

Failure before publication leaves the previous generation current.

## 11. Resource and operational rules

A full-Galaxy derived build is a bounded operator job, never API startup work.

Require:

- resumable/chunked stages;
- bounded concurrency/memory;
- explicit statement/lock policy;
- truthful progress totals or `unknown` totals;
- no long blocking DDL on canonical tables;
- index construction staged after bulk load where appropriate;
- `ANALYZE` before validation benchmarks;
- explain/latency evidence for radius, KNN, autocomplete and map scales;
- deterministic version/manifests sufficient to reproduce the generation.

## 12. Deliberately avoided designs

- recreating old V2 `public.*` merely to keep old SQL working;
- carrying Ratings V3.4 forward as final V3 scoring authority;
- one permanent `grid_cell_id` size;
- using clusters as the search index;
- request-time global rating calculation;
- renderer-owned scoring/ranking/clustering;
- treating map materialisations as canonical truth;
- requiring canonical-data mutation for scorer/archetype changes;
- representing unknown mechanics inputs as zero/false.

## 13. Benchmark/configuration decisions that do not reopen architecture

These remain versioned and benchmark-driven:

- pyramid cell sizes/levels;
- Morton/Z-order encoding details;
- generated vs stored `cube` position;
- name-index strategy;
- hot typed columns vs explanation JSON;
- map cell summary payloads;
- cluster algorithms/parameters;
- V4 normalization coefficients after mechanics review;
- retained derived-generation count.

## Acceptance bar

Before production authority:

- Ratings V4 contract and coefficient manifest are frozen against the mechanics evidence audit;
- representative single/mixed-economy systems demonstrate explainable V4 output;
- V3.4 comparison is used as regression evidence only;
- exact 3-D radius/KNN queries use indexes and meet Search budgets;
- Galaxy/regional/local map responses are target-count bounded;
- changing scorer, pyramid or cluster algorithm requires derived rebuild only;
- partial builds cannot publish;
- API reads an explicit published generation;
- canonical/derived/mechanics/scorer/archetype/ranking/pyramid/cluster versions appear in operational receipts.
