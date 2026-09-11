# V3 derived-data completion plan

**Status:** plan, not authority. The authorities remain
[the roadmap](../ROADMAP.md),
[the search/spatial/derived-data decision](v3-search-spatial-derived-data-decision.md)
and [the Ratings V4 freeze](ratings-v4-freeze/README.md). This document exists to
make the remaining table and script work reviewable before any SQL is written.

## Purpose

Answer one question precisely: what does the database still need before Finder,
ratings and exobiology/exploration features can be designed against it, and what
has to be written and run to get there?

## Measured production scale

Read from the retained production database on 2026-09-10. These numbers constrain
every design decision below.

| Relation | Rows |
|---|---|
| `v3_gen_…r5.systems` | 198,528,286 |
| `v3_gen_…r5.bodies` | 598,724,752 |
| `v3_gen_…r5.stations` | 830,740 |
| `…body_genus_current` | 7,181,400 |
| `…body_signal_current` | 25,019,890 |
| `…ring_signal_current` | 3,295,614 |
| `v3_vocab.genus` / `signal_type` | 21 / 20 |
| `v3_identity.account` / `commander` | 2 / 0 |

Consequences: a one-row-per-system derived table is a ~200M-row build and must be
chunked and resumable; a per-body table is ~600M rows and must not duplicate
system identity per row; and the canonical exobiology facts already exist and are
populated, so exobiology is a **derived and personal** gap, not a canonical one.

## Inventory

### A. Canonical truth — exists and is populated

`v3_gen_<generation>` (systems, bodies, rings, stations, aliases, compositions,
current-signal and current-genus relations), `v3_vocab`, `v3_source`,
`v3_identity`, `v3_private`, `v3_async`, `r1_meta`, `r1_plan`, `r1_cache`. The
schema is already generation-namespaced: `v3_meta.canonical_generation` and
`v3_meta.current_canonical_generation` select the live generation.

### B. Designed and written, never applied

`sql/v3/migrations/003_ratings_v4_derived.sql` creates `v3_derived` and `v3_app`:

| Object | Purpose |
|---|---|
| `v3_meta.derived_generation` | immutable derived manifest with a lifecycle (`BUILDING → VALIDATING → READY → PUBLISHED → RETIRED/FAILED`) and an immutability trigger |
| `v3_meta.current_derived_generation` | the published pointer |
| `v3_meta.derived_publication_audit` | publication sequence, actor, reason |
| `v3_derived.build_chunk` | per-chunk coverage receipt (systems, canonical/physical bodies, eligible opportunities, content hash) |
| `v3_derived.system_rating_vector` | the seven frozen economy values per system, exact ten-thousandths |
| `v3_derived.body_mechanics` | versioned mechanics features per body |
| `v3_derived.economy_opportunity` | local opportunity per economy |
| `v3_derived.system_economy_rating`, `v3_app.system_economy_rating` | stable application boundary views |

Not present in production: neither `v3_derived` nor `v3_app` exists there, and the
migration's own header states that applying it through production "requires the
separately reviewed V3 migration operation".

### C. Designed in the decision, not yet written

The [search/spatial/derived-data decision](v3-search-spatial-derived-data-decision.md)
names these shapes explicitly; none exist as SQL today.

| Object | Notes |
|---|---|
| `v3_derived.system_search` | `position_ly cube` with a GiST index, numeric LY preserved as truth, region and hot facts; keyed by derived generation and `id64` |
| `v3_spatial.cell_level` | pyramid level metadata: version, level, cell size, scale/budget metadata |
| `v3_spatial.cell_summary` | per-level LOD aggregation keyed by `(derived_generation_id, spatial_pyramid_version, level, cell_key)` |
| `v3_spatial.cluster_run` | versioned cluster run: owner/domain, algorithm, parameters, lifecycle, validation receipt |
| `v3_spatial.cluster` | cluster centroid/bounds, member count, summary |
| `v3_spatial.cluster_member` | membership keyed by `(cluster_run_id, cluster_id, system_id64)` |
| archetype judgement | `system × archetype_key` with score, confidence, explanation JSONB, `computed_at` |
| summary projections | primary/secondary archetype and Best Colony Potential; optional compact one-row-per-system projection for hot Finder queries |

The existing canonical `grid_x/grid_y/grid_z/macro_grid_key` fields are evidence
only. Their encoding is explicitly **not** the pyramid contract, so changing cell
sizes or encoding is a derived rebuild rather than a schema redesign.

### D. Approach agreed, relation not yet written

Finder ranking is the only area here. Its approach is settled (section F); the
relation that carries it is not yet written.

### E. Exobiology and exploration — shape agreed 2026-09-10

The canonical side already exists and is populated: `v3_vocab.genus` (21 genera,
Codex-keyed as `codex_ent_…`), `body_genus_current` (7.18M bodies),
`body_signal_current` (25M) and `ring_signal_current`. Every row already carries
`source_run_id` and `observed_at`, so each fact records when and from which
import it was learned. What is missing is everything below the genus.

Three layers, in dependency order:

1. **Reference.** A species level beneath genus (genus → species → **variant**,
   the same shape as the existing genus → species step), plus a **versioned**
   value table: base value per species and the first-logged bonus. Versioning is
   required because Frontier rebalance these, so each calculated result must
   record which value version it used. **Settled:** colour makes no difference to
   payout, so value is keyed at **species**, never at variant.
2. **Facts.** Species present on a body, and first-logged claims. Agreed model:
   **every account keeps its own Codex**, and **only first-logged is shared**.
   The variant is recorded in the personal record, because it determines Codex
   completeness even though it does not affect value. The shared claim must be
   append-only with a database-enforced unique key, so two players sampling the
   same species minutes apart cannot both be recorded as first.
3. **Calculated.** Exobiology value per **system** (is this worth visiting?) and
   per **body** (which body here holds it?), built from layers 1 and 2 plus the
   canonical genus and signal facts. This must be a **new relation**: the frozen
   rating vector stores exactly the seven economy values in one row, and adding
   an eighth would reopen a frozen contract.

**Settled:** a first-logged claim is scoped **globally per species**. The shared
claim therefore has one row per species for all time, and the database enforces
that uniqueness rather than the application.

#### Images

Decided: **one image per species, not per variant.** The variant is still
recorded in the personal Codex, because it determines completeness, but it does
not need its own picture.

An image is a **reference to a shipped asset**, never a blob in the database. The
species row carries the reference; the file lives where assets live and is
recorded in `assets/PROVENANCE.json`.

**Source decided:** the project owner will capture their own in-game pictures.
Every such file is therefore `frontier_derived: true` with
`commercial_use_approved: false`, a named creator, the official long-form
Frontier community attribution, and a per-file provenance record with its hash.
The existing CI guard rejects missing, stale or invalid entries and any hash
drift, so the photographs cannot be added informally.

**Until those exist:** placeholders should be **original** artwork
(`source_kind: original`), which carries no Frontier treatment and no third-party
credit, and one placeholder per **genus** visually covers every species beneath
it. Twenty-one images cover the whole Codex initially.

**Consequence to keep in view:** because the real images are Frontier-derived and
noncommercial-only, the Codex imagery is what would have to be replaced or
excluded from the shipped bundle if ED-Finder ever becomes commercial. That is a
reason to keep the species-to-image reference indirect rather than wiring file
paths through the application.

### F. Finder ranking — approach agreed 2026-09-10

Both, in that order:

1. **Published, precomputed profile values as the primary path.** Ranking values
   are computed as part of a derived generation and published under an explicit
   ranking-profile identity, so a search reads stored numbers, is reproducible,
   and can name exactly which values produced a result. Adding a profile is a
   derived rebuild, not a schema change.
2. **Query-time adjustment on top.** Constraints, personal weighting and
   distance-relative factors are applied at query time, so a one-off ranking need
   not force a rebuild.

The rule that keeps this honest: ranking logic lives in one place and never
mutates stored mechanics truth. Router SQL must not grow accidental ranking
expressions, which is the failure mode the decision explicitly warns about.

Profile inputs remain those the decision lists: a selected economy potential, a
selected archetype score, Best Colony Potential, distance, confidence and
completeness, accessibility, and user or query constraints.

## Scripts

### Exists

`scripts/ratings_v4/`: `canonical_stream.py`, `generation.py`,
`production_generation.py`, `run_generation.py` (resumable, chunked),
`verify_freeze.py`, `legacy_v34_reference.py`, `compare_legacy.py`. Ratings
generation is substantially built and covered by twelve test modules.

### To write

| Script | Purpose |
|---|---|
| search-projection builder | populate `v3_derived.system_search` and its GiST index |
| pyramid builder | build `v3_spatial.cell_level` / `cell_summary` from exact coordinates |
| cluster builder + publication | build and publish `v3_spatial.cluster*` per domain and algorithm version |
| archetype builder | judgement and the summary projection |
| Finder ranking layer | whatever shape the open decision settles on |
| exobiology / exploration builders | only after the model in section D exists |
| per-domain validators | coverage and completeness evidence proving every expected system was covered, transitioning the lifecycle and sealing receipts |

## How a migration lands in production

There is no governed delivery for a production migration yet, which is why
nothing in sections B–D can reach production. The reviewed operation itself now
exists — see
[the production schema migration runbook](../operations/v3-production-schema-migration.md)
for its gates, its operations and its remaining gap. Land a migration by:

1. commit the migration under `sql/v3/migrations/`, and, for the R1 shell style,
   `sql/r1_v3/`;
2. add its ledger name, hash and repository path to
   `sql/v3/migration-manifest.txt`;
3. regenerate the reviewed schema identity — which changes
   `schema_identity_sha256` — and re-pin it in
   `deploy/v3-production/target-authority.json`;
4. run the reviewed operation, with evidence, against the retained database.

Note the split of authority: DDL belongs to that migration operation, while
derived **data** (builds, publication, retirement) belongs to the derived
generation lifecycle already designed in `003`. A derived rebuild must never
require DDL.

## Sequencing

| Phase | Work | Blocked by |
|---|---|---|
| P0 | Reviewed production V3 migration operation | nothing |
| P1 | Apply `003`; build the first economy generation from the current canonical generation; validate; publish; record evidence | P0 |
| P2 | `004`: search projection, spatial pyramid, clusters, plus their builders and validators | P1 |
| P3 | `005`: archetype judgement, summary projections, Finder ranking layer | P2 |
| P4 | Exobiology/exploration: design, migration, builders | the open decisions in section D |

## Open decisions to settle before SQL

1. Cluster ownership: which domains publish cluster sets, and is that one run per
   domain or a shared run with domain-specific outputs?

**Settled:** Finder ranking is both — published precomputed profile values as the
primary path, with query-time adjustment on top (section F). A first-logged claim
is global per species (section E).

**Settled:** exobiology value is keyed per species, not per variant, because
colour does not affect payout. Every account keeps its own Codex; only
first-logged facts are promoted to shared data. Codex images are one per species
(not per variant) and arrive as the owner's own in-game captures, recorded as
Frontier-derived and noncommercial, with original genus placeholders in the
meantime.
