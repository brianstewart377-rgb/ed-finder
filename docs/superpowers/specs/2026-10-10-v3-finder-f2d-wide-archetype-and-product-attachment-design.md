# V3 Finder F2d — wide archetype product and product attachment/publication

**Status:** Design only; not implemented. Depends on PR #805 (step 0 receipt,
capacity decision, ROADMAP amendment), which merges first; this document cites
files that PR adds.

**Date:** 2026-10-10

**Base:** `origin/main` at `6b623bcb896b67004c2ba64f7df45c8b4d78e0ce`

**Owner decision:** A + B: rewrite unapplied migration `011` to one wide
archetype row per system with explanations computed on demand; attach the two
Finder products to the already-published
`ratings_v4_prod_p4_parallel_v1` generation behind a new explicit
product-publication gate in migration `015`; defer purge; accept a new ranking
identity. (`docs/operations/v3-finder-production-rollout-state.md` (PR #805),
`docs/operations/v3-finder-capacity-decision-2026-10-10.md` (PR #805))

## 1. Context and terms

Production had 292 GB free on 2026-10-10. The complete published Ratings V4
generation occupies about 313 GB, while the current eight-rows-per-system
archetype layout was measured at about 978 GB for 1.588 billion rows, including
about 410 bytes of explanation JSON per row. A fresh ratings generation plus
Search, Archetype, and the old summary would require about 1,413 GB. The current
plan therefore cannot fit. (`docs/operations/v3-finder-production-rollout-state.md` (PR #805),
`docs/operations/v3-finder-capacity-decision-2026-10-10.md` (PR #805))

Migration `011` is registered but has never been applied to production, so its
bytes may be replaced before application, following the precedent used for
`010`. Registration is not evidence of application. (`docs/ROADMAP.md:121-127,140-151`,
`docs/operations/v3-finder-production-rollout-state.md` (PR #805))

In this design:

- A **derived generation** is the immutable Ratings V4 generation and its
  lifecycle record.
- A **derived product** is a separately registered, built, validated projection
  attached to that generation, such as `system_search` or `system_archetype`.
- **READY** means a product passed validation. **Published** means a separate,
  explicit product-publication action made that READY product visible to
  application views. Today products have only BUILDING/READY/FAILED and a
  published generation may expose READY products immediately; migration `015`
  separates those states. (`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:6-30`,
  `apps/api/src/local_search.py:602-643`)
- **Wide row** means one `v3_derived.system_archetype` row contains all eight
  archetype score/tier/confidence triples and the existing summary fields.

## 2. Goal and non-goals

### Goal

Store exactly one archetype product row for every Ratings V4 system while
preserving the current model outputs: all eight scores, tiers, six-decimal
confidence values, primary and secondary archetypes, Best Colony Potential,
best tier, archetype confidence, and weighted potential. Only the storage
layout and explanation delivery change. The current model computes those
values deterministically and defines the eight-key tie-break order.
(`scripts/v3_system_archetype_model.py:23-42,85-205`)

“Identical confidence” means the same value produced by the model rounded to
six decimal places. Migration `011` stores every confidence as an **exact
integer in parts per million** (`<key>_confidence_ppm integer CHECK (BETWEEN 0
AND 1000000)`, likewise `archetype_confidence_ppm`): the builder writes
`round(confidence * 1_000_000)`, the validator compares integers with no
tolerance, the ranking SQL uses `(a.<key>_confidence_ppm / 1000000.0)` (a
`double precision` expression that yields the nearest double to the six-decimal
value — the same value Python's `round(x, 6)` produces), and the API serializes
`ppm / 1e6`. A `real` column was rejected after review because the ranking
expression would multiply a float32 approximation (a few 1e-8 off the
six-decimal value) and could reorder near-ties; `double precision` was measured
at +14 GB for the same information. Integer ppm costs the same 4 bytes as
`real` (measured: identical 186 B/row heap) and is exact. The current model
already rounds fit and summary confidence to six places.
(`scripts/v3_system_archetype_model.py:114-131,141-145,192-205`)

### Non-goals

- Do not rebuild Ratings V4. Both products attach to
  `ratings_v4_prod_p4_parallel_v1`, whose complete validated vectors already
  exist. (`docs/operations/v3-finder-capacity-decision-2026-10-10.md` (PR #805))
- Do not change any canonical relation or scoring input. Archetypes remain a
  reproducible derived layer over `system_rating_vector` and
  `economy_opportunity`; canonical V3 remains source truth.
  (`docs/development/v3-search-spatial-derived-data-decision.md:11-24,83-132`)
- Do not change fit coefficients, tier boundaries, key order, score semantics,
  or ranking response fields. A storage-shape version and ranking identity
  change are still required because reproducibility hashes describe the live
  implementation. (`scripts/v3_system_archetype_model.py:23-42,85-205`,
  `apps/api/src/ranking/profile.py:132-183`,
  `apps/api/src/local_search.py:790-839,951-964`)
- Do not add a purge path or delete retained `p4`/`opt1` data. Current Search
  rows and receipts are insert-only and no governed purge exists; the owner
  explicitly deferred purge. (`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:165-206`,
  `docs/operations/v3-finder-production-rollout-state.md` (PR #805))
- Do not make explanations searchable, sortable, or persisted in the
  archetype product.

## 3. Rewritten migration `011`: one wide row per system

### 3.1 Relation

**Decision:** replace both current product tables with one table. The current
`011` stores eight keyed rows plus a separate summary row; it also stores a
large explanation object on every keyed row. (`sql/v3/migrations/011_v3_system_archetype.sql:7-43`)

The rewritten `v3_derived.system_archetype` is:

```sql
CREATE TABLE v3_derived.system_archetype (
    derived_generation_id uuid NOT NULL
        REFERENCES v3_meta.derived_generation,
    system_id64 bigint NOT NULL CHECK (system_id64 >= 0),
    archetype_version text NOT NULL
        CHECK (length(archetype_version) BETWEEN 1 AND 128),

    paradise_score smallint NOT NULL CHECK (paradise_score BETWEEN 0 AND 100),
    paradise_tier char(1) NOT NULL CHECK (paradise_tier IN ('S','A','B','C','D')),
    paradise_confidence_ppm integer NOT NULL CHECK (paradise_confidence_ppm BETWEEN 0 AND 1000000),

    mining_hub_score smallint NOT NULL CHECK (mining_hub_score BETWEEN 0 AND 100),
    mining_hub_tier char(1) NOT NULL CHECK (mining_hub_tier IN ('S','A','B','C','D')),
    mining_hub_confidence_ppm integer NOT NULL CHECK (mining_hub_confidence_ppm BETWEEN 0 AND 1000000),

    manufacturing_hub_score smallint NOT NULL CHECK (manufacturing_hub_score BETWEEN 0 AND 100),
    manufacturing_hub_tier char(1) NOT NULL CHECK (manufacturing_hub_tier IN ('S','A','B','C','D')),
    manufacturing_hub_confidence_ppm integer NOT NULL CHECK (manufacturing_hub_confidence_ppm BETWEEN 0 AND 1000000),

    megacomplex_score smallint NOT NULL CHECK (megacomplex_score BETWEEN 0 AND 100),
    megacomplex_tier char(1) NOT NULL CHECK (megacomplex_tier IN ('S','A','B','C','D')),
    megacomplex_confidence_ppm integer NOT NULL CHECK (megacomplex_confidence_ppm BETWEEN 0 AND 1000000),

    research_hub_score smallint NOT NULL CHECK (research_hub_score BETWEEN 0 AND 100),
    research_hub_tier char(1) NOT NULL CHECK (research_hub_tier IN ('S','A','B','C','D')),
    research_hub_confidence_ppm integer NOT NULL CHECK (research_hub_confidence_ppm BETWEEN 0 AND 1000000),

    stronghold_score smallint NOT NULL CHECK (stronghold_score BETWEEN 0 AND 100),
    stronghold_tier char(1) NOT NULL CHECK (stronghold_tier IN ('S','A','B','C','D')),
    stronghold_confidence_ppm integer NOT NULL CHECK (stronghold_confidence_ppm BETWEEN 0 AND 1000000),

    population_capital_score smallint NOT NULL CHECK (population_capital_score BETWEEN 0 AND 100),
    population_capital_tier char(1) NOT NULL CHECK (population_capital_tier IN ('S','A','B','C','D')),
    population_capital_confidence_ppm integer NOT NULL CHECK (population_capital_confidence_ppm BETWEEN 0 AND 1000000),

    flexible_score smallint NOT NULL CHECK (flexible_score BETWEEN 0 AND 100),
    flexible_tier char(1) NOT NULL CHECK (flexible_tier IN ('S','A','B','C','D')),
    flexible_confidence_ppm integer NOT NULL CHECK (flexible_confidence_ppm BETWEEN 0 AND 1000000),

    -- canonical picked-ranking key per archetype, stored so the ranking is
    -- served in its own order by an index: round(score × confidence ×
    -- completeness × 10,000), 0..1,000,000
    paradise_weighted_e4 integer NOT NULL CHECK (paradise_weighted_e4 BETWEEN 0 AND 1000000),
    mining_hub_weighted_e4 integer NOT NULL CHECK (mining_hub_weighted_e4 BETWEEN 0 AND 1000000),
    manufacturing_hub_weighted_e4 integer NOT NULL CHECK (manufacturing_hub_weighted_e4 BETWEEN 0 AND 1000000),
    megacomplex_weighted_e4 integer NOT NULL CHECK (megacomplex_weighted_e4 BETWEEN 0 AND 1000000),
    research_hub_weighted_e4 integer NOT NULL CHECK (research_hub_weighted_e4 BETWEEN 0 AND 1000000),
    stronghold_weighted_e4 integer NOT NULL CHECK (stronghold_weighted_e4 BETWEEN 0 AND 1000000),
    population_capital_weighted_e4 integer NOT NULL CHECK (population_capital_weighted_e4 BETWEEN 0 AND 1000000),
    flexible_weighted_e4 integer NOT NULL CHECK (flexible_weighted_e4 BETWEEN 0 AND 1000000),

    primary_archetype text NOT NULL,
    secondary_archetype text,
    best_colony_potential smallint NOT NULL
        CHECK (best_colony_potential BETWEEN 0 AND 100),
    best_tier char(1) NOT NULL CHECK (best_tier IN ('S','A','B','C','D')),
    archetype_confidence_ppm integer NOT NULL
        CHECK (archetype_confidence_ppm BETWEEN 0 AND 1000000),
    weighted_potential double precision NOT NULL
        CHECK (weighted_potential BETWEEN 0 AND 100),
    computed_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (derived_generation_id, system_id64),
    FOREIGN KEY (derived_generation_id, system_id64)
        REFERENCES v3_derived.system_rating_vector
        DEFERRABLE INITIALLY DEFERRED,
    CHECK (primary_archetype IN (
        'paradise','mining_hub','manufacturing_hub','megacomplex',
        'research_hub','stronghold','population_capital','flexible'
    )),
    CHECK (secondary_archetype IS NULL OR secondary_archetype IN (
        'paradise','mining_hub','manufacturing_hub','megacomplex',
        'research_hub','stronghold','population_capital','flexible'
    )),
    CHECK (secondary_archetype IS NULL OR secondary_archetype <> primary_archetype)
);
```

The column groups follow `ARCHETYPE_KEYS` order exactly: `paradise`,
`mining_hub`, `manufacturing_hub`, `megacomplex`, `research_hub`,
`stronghold`, `population_capital`, `flexible`. This order is also the current
tie-break for equal scores. (`scripts/v3_system_archetype_model.py:22-33,192-205`)

`weighted_potential` remains double precision and retains the exact, unrounded
`best_colony_potential * (system_search confidence * completeness)` semantics;
reducing it to a small integer would collapse the default ordering into large
ties. (`scripts/v3_system_archetype_model.py:155-189`,
`sql/v3/migrations/011_v3_system_archetype.sql:30-39`)

**`<key>_weighted_e4` is the picked-ranking key, stored.** The ranking profile
orders a picked archetype by `score × fit confidence × completeness`
(`apps/api/src/ranking/ranking_sql.py:451-477`); review showed that any design
which takes a candidate window by *raw score* and sorts it by the weighted
product afterwards is an approximation (a score-99 system with full certainty
can be dropped behind 10,001 score-100 systems with near-zero certainty). So the
builder stores the canonical key itself for every archetype:
`round(<key>_score × (<key>_confidence_ppm / 1e6) × completeness × 10000)`,
where `completeness` is the same generation's `system_search.completeness` for
the system (the builder already reads `system_search` confidence/completeness
for `weighted_potential`, so the search product must be READY before the
archetype build, as today). An integer in 1e-4 units is exact and 4 bytes;
ordering by it equals ordering by the double product except for ties within
0.0001, which `system_id64` then breaks deterministically — that rounding is part
of the new ranking identity, not a hidden difference. Measured heap: 221.7 B/row
(≈ 44 GB), 35 B more than without the eight keys.

### 3.2 Summary projection

**Decision:** do not keep a physical
`v3_derived.system_archetype_summary` table. Its six values already exist on
the wide row, so a second 198.5-million-row table would duplicate the current
35 GB summary relation and create a consistency problem. The measured old
summary footprint was 96 bytes of table plus 79 bytes of indexes per row.
(`docs/operations/v3-finder-production-rollout-state.md` (PR #805))

Keep the stable application name as a view:

```sql
CREATE VIEW v3_app.system_archetype_summary AS
SELECT derived_generation_id, system_id64,
       primary_archetype, secondary_archetype,
       best_colony_potential, best_tier,
       (archetype_confidence_ppm / 1000000.0)::double precision AS archetype_confidence,
       weighted_potential, computed_at
FROM v3_app.system_archetype;
```

The stored column is the exact integer `archetype_confidence_ppm`; the view
projects the double-precision `archetype_confidence` the ranking SQL and the
response models already read, so the no-pick path and the summary fields need
no code change. The `v3_app.system_archetype` view exposes every wide column as
stored (the eight `_confidence_ppm` integers included) **and** the same derived
`<key>_confidence` doubles, so the ranking column map in section 6 may reference
either form; the migration test creates both views against the wide table and
selects every projected column.

That preserves the join name used by both ranked and count query builders while
removing duplicated storage. The current common SQL always joins that name.
(`apps/api/src/ranking/ranking_sql.py:246-263,294-301,512-546`)

### 3.3 Indexes

In addition to the primary key, create the `weighted_potential` index and, for
each of the eight archetypes, **three partial indexes over the stored weighted
key, one per exposed tier floor**:

```text
(derived_generation_id, weighted_potential DESC)

for every <key> in ARCHETYPE_KEYS:
  (derived_generation_id, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 60   -- tier B floor
  (derived_generation_id, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 76   -- tier A floor
  (derived_generation_id, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 88   -- tier S floor
```

Why this shape (each point came out of review):

- **Canonical order from the index.** A picked ranking is served by scanning the
  matching partial index in `<key>_weighted_e4 DESC, system_id64` order and
  stopping after the requested page (or after 10,001 rows for the bounded count,
  section 6). No candidate window by raw score, no post-hoc sort: the first
  10,000 rows of the index *are* the top 10,000 of the canonical ranking.
- **Partial, per tier floor.** The F4 product exposes exactly the floors
  B/A/S ⇒ 60/76/88, and nothing else may call below B (section 6). One index per
  floor keeps every exposed query index-only and bounded; a single `>= 60` index
  would make an S-floor query filter through the whole B population (measured:
  the ≥ 60 index read 33,695 entries to return 4,095 ≥ 76 rows at 200k). The A
  and S partials are tiny (measured 1.1 and 0.2 B/row).
- **`system_id64` trailing**, so ties on the integer key are broken inside the
  index without a sort.
- **The floor must be a literal in the SQL** (section 6): PostgreSQL decides
  partial-index applicability at planning time and a parameter cannot prove
  `$n >= 60`; measured under `plan_cache_mode = force_generic_plan`, the
  parameter-only form fell back to a parallel sequential scan while the form
  with a redundant literal used the partial index
  (`docs/operations/evidence/2026-10-10-wide-archetype-footprint-200k.json`
  method notes; PostgreSQL 18 docs, “Partial Indexes”).

Measured on the disposable PostgreSQL 18.4 (200,000 rows, bell-shaped scores
with 16.9 % ≥ 60, 2.1 % ≥ 76, 0.19 % ≥ 88 per key; `v4_weighted_key_tier_partials`
in the committed evidence): ≥ 60 partial 8.5 B/row, ≥ 76 1.1 B/row, ≥ 88 0.2 B/row
per key — ≈ 79 B/row for all 24 — plus primary key 40.7 and weighted index 40.8;
indexes total 160 B/row ≈ 32 GB. Each partial's size is 49.8 B × (fraction of
systems at or above that floor), so **the step 6 calibration probe's per-key tier
histogram sizes them for real** before PR1's final re-measurement; the design
stops and is revisited if the histogram implies the ≥ 60 fraction above ≈ 40 %
on several keys (that would put the indexes alone near 80 GB). The earlier
score-ordered partial layout (`v3_partial_ge60_score_sysid`, ≈ 67 GB) and the
deduplicated layout (≈ 65 GB) are kept in the evidence as rejected alternatives:
the first cannot serve canonical order, the second cannot bound the probe.
(`apps/api/src/ranking/ranking_sql.py:451-477`,
`sql/v3/migrations/011_v3_system_archetype.sql:45-56`)

### 3.4 Measured footprint

The earlier PostgreSQL 18.4 sample used real builder rows, replicated each
relation to about 200,000 rows with the same DDL and indexes, ran
`VACUUM ANALYZE`, measured `pg_table_size` and `pg_indexes_size`, and
extrapolated linearly to 198.5 million systems. The same method was applied on
2026-10-10 to the wide DDL in section 3.1 (foreign keys to other relations
omitted; 200,000 synthetic rows of realistic shape; PostgreSQL 18.4) for both
index variants. The production gate repeats it with the final migration text.
(`docs/operations/v3-finder-production-rollout-state.md`, section “Disposable-sample
footprint measurement”, PR #805)

| Object (198.5 M rows) | Measured B/row | Estimated size |
|---|---:|---:|
| table heap without the stored weighted keys (`pg_table_size`; average tuple 180 B) | 186.4 | 37.0 GB |
| primary key `(derived_generation_id, system_id64)` | 40.7 | 8.1 GB |
| `weighted_potential` index | 40.8 | 8.1 GB |
| eight stored `<key>_weighted_e4` columns (heap grows from 186.4 to 221.7 B/row) | +35.3 | +7.0 GB (heap 44.0 GB) |
| 24 partial `(derived_generation_id, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 60 / 76 / 88` indexes (bell-shaped synthetic distribution; `v4_weighted_key_tier_partials` in the committed evidence) | 8 × (8.5 + 1.1 + 0.2) ≈ 79 | 15.6 GB |
| **total, section 3.3 layout** (synthetic distribution) | **382** | **≈ 76 GB** |
| *(rejected)* score-ordered partial `>= 60` indexes without the stored key (`v3_partial_ge60_score_sysid`) | 336 | ≈ 67 GB — cannot serve canonical order |
| *(rejected)* deduplicated `(derived_generation_id, <key>_score DESC)` indexes (`v2_score_only`) | 328 | ≈ 65 GB — cannot bound the probe without a tie sort |
| *(reference)* full unique-entry score indexes (`v1_with_system_id64`) | 667 | ≈ 132 GB |

The decision text's earlier “about 80 GB” and this design's first-draft
“about 90 GB” were unmeasured guesses: the heap is wider than assumed (186 B,
not 150 B) and a unique-entry score index is 49.8 B/row, not 30 B. The
measured layout is **≈ 76 GB** of persistent product data on the synthetic
distribution (the tier-partial indexes scale with the real per-floor fractions —
see section 3.3); re-measuring with
integer-ppm confidences gave the identical 186.4 B/row heap (same 4-byte width
and alignment as `real`), while `double precision` confidences measured
256 B/row (≈ 79 GB total) because of 8-byte alignment padding. The production gate
must replace this sample figure with a measurement of the final `011` text and
must stop if Search (≈ 87 GB measured) plus Archetype, WAL, temporary files and
vacuum working room do not fit the free space reported by a fresh step 0
receipt (292 GB on 2026-10-10).

### 3.5 Receipts and mutation guards

Keep `v3_derived.archetype_build_chunk` with its current primary key, source and
content seals, system count, product FK, and Ratings-chunk FK. It is the
resumability and coverage boundary. (`sql/v3/migrations/011_v3_system_archetype.sql:58-75`,
`scripts/v3_system_archetype.py:215-246,770-833`)

Keep all three mutation properties:

1. Product rows and chunk receipts may be inserted only while that product is
   BUILDING.
2. UPDATE, DELETE, and TRUNCATE of product rows and receipts remain rejected.
3. The generation must be in an allowed attachment state; rewritten `011`
   initially retains BUILDING/VALIDATING/READY, and `015` adds PUBLISHED.

The current guard applies those rules to the keyed table, summary table, and
receipts; the rewrite drops only the obsolete summary-table trigger target and
renames no externally used guard unless needed for clarity.
(`sql/v3/migrations/011_v3_system_archetype.sql:77-130`)

## 4. Explanation on demand

### 4.1 Endpoint and shared model

**Decision:** add
`GET /api/archetypes/system/{id64}/explanation` with the path parameter declared
`Path(ge=0, le=9223372036854775807)` as the active Ratings V4 routes do, so a
negative or over-`bigint` value is a 422 validation response rather than an
asyncpg encoding failure (tests cover both bounds); leave the existing legacy
`GET /api/archetypes/system/{id64}` unchanged until its topology/pair/trait
contract has a complete V3 replacement. The existing endpoint still reads
legacy `systems`, `system_archetype_scores`, topology, pair, trait, and body
relations. (`apps/api/src/routers/archetypes.py:631-759`)

Move the DB-free implementation to
`shared_contracts/v3_system_archetype_model.py`. Keep
`scripts/v3_system_archetype_model.py` as a compatibility re-export during the
transition, and make the builder, calibration probe, ranking profile, and API
import the shared implementation. This prevents two fit implementations. The
API image copies `shared_contracts/` but does not copy the repository `scripts/`
tree. (`apps/api/Dockerfile:12-24`,
`apps/api/src/ranking/profile.py:35-40`,
`scripts/v3_system_archetype_model.py:1-8,45-62,85-205`)

### 4.2 Read and compute path

For the current generation and requested `id64`, one parameterized SQL round
trip reads:

- the one matching `system_rating_vector` row; and
- the matching `economy_opportunity` rows grouped by economy ordinal.

The query must use the leading `(derived_generation_id, system_id64)` keys and
return the same `SystemVectors` fields as `_read_chunk_vectors`, then call the
shared `fit_all` and `summarise`. The existing source relations have primary
keys beginning with those two columns, and the builder currently reads exactly
those vector and opportunity inputs. (`sql/v3/migrations/003_ratings_v4_derived.sql:109-126,165-185`,
`scripts/v3_system_archetype.py:249-281`,
`scripts/v3_system_archetype_model.py:148-205`)

Cost is one database round trip backed by two index probes, touching about one
vector row plus `N` eligible opportunity rows, followed by eight small
in-process fits. It does not scan the wide product or the Galaxy. Explanation
objects are returned, not stored, indexed, filtered, or searchable. The current
fit functions already construct the explanation objects.
(`scripts/v3_system_archetype_model.py:85-152`)

The response contains generation identity, `archetype_version`, and the eight
unchanged key/score/tier/confidence values plus each computed explanation. It
must compare recomputed score/tier/confidence-ppm and summary values to
the stored wide row and fail closed on a mismatch; explanation delivery must
never silently describe a different stored score.

### 4.3 Exact version rule

Serve explanations only when all three version values are equal **and** the
deployed code is the code that built the product:

```text
v3_meta.derived_product.product_version
    == v3_derived.system_archetype.archetype_version
    == deployed shared model ARCHETYPE_VERSION
and
sha256(deployed shared_contracts/v3_system_archetype_model.py)
    == product manifest `model_file_sha256`
```

The hash comparison matters because explanations are no longer persisted: a
change to the shared model's explanation construction without a version bump
would leave all three version strings equal and the stored score/tier/
confidence comparison passing, yet serve explanations produced by different
code than the manifest records. The API computes the deployed model file's hash
once at start-up and compares it with the manifest's recorded hash (section
5.1 adds it to `product_manifest`). The product must also be READY and
product-published on the current PUBLISHED generation. On any version **or
hash** mismatch, return HTTP 409 with the exact FastAPI detail string:

```text
explanation unavailable for this product version
```

Perform this check before reading vector/opportunity inputs or calling
`fit_all`. The exact contract tests patch `fit_all`, supply a READY and
published product whose version differs from the deployed model — and,
separately, one whose versions all match but whose manifest `model_file_sha256`
differs from the deployed file's hash — assert HTTP 409 and the exact detail
string for both, and assert `fit_all` was not called. Matching
versions must return all eight explanations and values identical to the stored
wide row. The current product manifest and model version already form the
reproducibility identity this rule extends to API delivery.
(`scripts/v3_system_archetype.py:128-168,181-212`)

## 5. Builder, manifest, and validator

### 5.1 Version and manifest

Set `ARCHETYPE_VERSION = 'v3-archetype-4'`. The fit coefficients do not change,
but the persisted product changes from eight keyed rows plus a summary row and
stored explanations to one wide row without explanations. Version `3` was
already introduced solely because the stored summary shape gained
`weighted_potential`, so a shape-driven version bump is the established rule.
(`scripts/v3_system_archetype_model.py:10-20`)

`product_manifest` continues to hash the coefficients, anchors, key order,
generation identity, source policy, and code identity. Add a canonical ordered
`wide_columns` list (the eight `_weighted_e4` keys and their exact definition
`round(score × confidence × completeness × 10000)` included),
`storage_layout: "one-row-per-system-v1"`,
`explanation_delivery: "on-demand"`, confidence storage/rounding policy, and
the shared model file hash as `model_file_sha256` (the value section 4.3 compares against the deployed file). Remove the persisted-explanation field policy. The
current manifest already hashes coefficients, anchors, key order, field policy,
and code files; registration rejects any existing manifest mismatch.
(`scripts/v3_system_archetype.py:64-73,104-168,181-212`)

### 5.2 Build

Keep the CLI unchanged: `--generation-key`, `--follow`, `--poll-seconds`,
`--max-chunks`, and `--validate`, with the same environment-based DSN and
fail-closed exit codes. (`scripts/v3_system_archetype.py:1109-1154`)

For every Ratings chunk:

1. Read vectors and opportunities exactly as today.
2. Call `fit_all`, `summarise`, and `weighted_potential` exactly once per
   system.
3. Pivot the ordered eight fits into one wide tuple.
4. Insert one wide row per system, then one unchanged
   `archetype_build_chunk` receipt in the same transaction.

The current builder performs the same source read and computations but inserts
eight rows plus one summary; the rewrite changes only the materialization.
(`scripts/v3_system_archetype.py:249-281,491-550`)

The chunk `content_sha256` covers every persisted wide-row column in stable
`system_id64` order, including `archetype_version` and the explicitly assigned
`computed_at` timestamp. The builder must assign one explicit timestamp per
chunk so the inserted value and the sealed value are identical. Validation
recomputes that seal from the stored wide rows; semantic reproducibility is
separately proved by recomputing model values from immutable inputs. The current
content seal covers the keyed and summary semantic rows but omits the timestamp;
the new shape makes the complete stored row the seal boundary.
(`scripts/v3_system_archetype.py:284-309,333-409,770-833`)

### 5.3 Validation

`validate_product` must gate all of the following before BUILDING → READY:

- base generation state is READY or PUBLISHED;
- every Ratings chunk has exactly one matching archetype receipt;
- `count(system_archetype) == count(system_rating_vector)` and every system has
  exactly one `v3-archetype-4` row;
- every one of the eight score columns is 0–100;
- every `<key>_weighted_e4` equals
  `round(<key>_score × <key>_confidence_ppm / 1e6 × completeness × 10000)`
  exactly, with `completeness` read from the same generation's `system_search`
  row (the validator fails closed if that row is missing);
- every tier equals `tier_of(its score)`;
- each stored `_confidence_ppm` integer equals `round(model confidence × 10⁶)`
  exactly (no tolerance);
- primary, secondary, best potential, best tier, archetype confidence, and
  full-precision weighted potential equal a fresh model recomputation;
- source and complete-wide-row content seals match; and
- no `public.*` relation is read.

Today coverage expects eight keyed rows and one summary row, and the validator
already gates scores/tiers, summary top-two/weighted values, seals, base state,
and READY promotion. Those tests become per-column wide-row tests rather than
being deleted. (`scripts/v3_system_archetype.py:588-833,836-1010`,
`tests/test_v3_system_archetype_validate.py:91-473`)

Registration, row insertion, and validation in both
`scripts/v3_system_archetype.py` and `scripts/v3_system_search.py` must accept
the current PUBLISHED generation after `015`; product lifecycle still must be
BUILDING for writes and READY remains terminal. Both builders currently reject
PUBLISHED in code even if the database guard were relaxed, so migration-only
work is insufficient. (`scripts/v3_system_archetype.py:181-212,836-894`,
`scripts/v3_system_search.py:162-193,413-414,549-588`)

## 6. Ranking SQL and F3 behavior

Set `RANKING_VERSION = 'v3-colony-potential-2'` and record the newly computed
`ranking_sha256`. The identity hash includes score-resolution rules, uncertainty,
tie-breaks, tier thresholds, filter keys, and archetype keys; the drift-guard
test pins the reviewed hash. (`apps/api/src/ranking/profile.py:33-54,132-183`,
`tests/test_ranking_profile_identity.py:37-61`)

Create an immutable mapping from each shared `ARCHETYPE_KEYS` value to its
trusted wide-column expressions, for example:

```python
ARCHETYPE_COLUMNS = {
    "paradise": ("a.paradise_score", "a.paradise_tier", "(a.paradise_confidence_ppm / 1000000.0)", "a.paradise_weighted_e4"),
    # ...seven more fixed entries...
}
```

The canonical mapping is **part of the hashed ranking identity**: it is declared
in `profile.py`'s `PROFILE_SPEC` (as
`archetype_columns: {key: {score, tier, confidence, weighted_key}}`, with the confidence
expression written out, e.g. `paradise_confidence_ppm / 1000000.0`) and therefore
enters `_canonical_base()` and `ranking_sha256`; `ranking_sql.py` derives
`ARCHETYPE_COLUMNS` from that spec rather than declaring its own copy, and the
identity test mutates one mapping entry and asserts the digest changes. Today
`_canonical_base()` hashes only the generic score rule and the key list
(`apps/api/src/ranking/profile.py:132-183`), which would let a swapped mapping
change production rankings under an unchanged `ranking_sha256`.
The router first rejects a key outside `ARCHETYPE_KEYS`; the SQL builder then
looks up the fixed expression. No raw or transformed user string is ever
formatted as a SQL identifier. SQL values remain parameters. The current
router already returns 422 for an unknown key, while the current SQL binds the
key as a row value and reads `a.archetype_score`; only that row-form resolution
changes. (`apps/api/src/routers/archetypes.py:294-316`,
`apps/api/src/ranking/ranking_sql.py:303-329`)

`build_ranked_query` and `build_count_query` continue sharing `_build_common`.
For a picked archetype, join the one wide `v3_app.system_archetype` row by
`system_id64`, select the mapped score/confidence columns, and **order by the
stored key**: `a.<key>_weighted_e4 DESC, s.system_id64 ASC` (distance is not a
term for a picked ranking — selected mode is galaxy-wide by the F4 design — and
the response still reports `primary_score`, `ranking_confidence` and
`uncertainty_factor` from the stored columns). The picked `WHERE` carries **two**
floor predicates: a **literal** tier-floor predicate chosen server-side — the
largest of `>= 60`, `>= 76`, `>= 88` not above the requested `min_score`, emitted
as text so the planner can prove the matching partial index applies under a
generic plan — and the parameterized `>= $n` for the exact requested value.
Measured under `plan_cache_mode = force_generic_plan`: parameter-only ⇒ parallel
sequential scan + sort; with the literal ⇒ index scan on the matching partial,
10,001 rows read. For no pick, keep the `v3_app.system_archetype_summary` join
and `sum.weighted_potential DESC NULLS LAST` unchanged. Preserve `system_id64`
tie-breaks and all selected aliases.
(`apps/api/src/ranking/ranking_sql.py:246-263,294-329,451-506,512-546`)

**The count is bounded too.** Today `/api/archetypes/rankings` awaits
`build_count_query(..., cap=None)`, an exact count over every qualifying row —
≈ 34 M rows at the synthetic 17 % B fraction, unbounded by any index. PR1
changes the picked count to `SELECT count(*) FROM (SELECT 1 … LIMIT 10001) t`
with the same literal + parameter floor: the response's `total` is
`min(count, 10000)` and `is_truncated` is `count = 10001`, exactly the
within-window contract the F4 design already specifies for selected mode, now
honest for the count as well as the page. The galaxy-wide local-search path
already caps its count the same way (`apps/api/src/local_search.py:248-254`).
Tests execute the ranked and count SQL on the disposable PG18 fixture with
`plan_cache_mode = force_generic_plan` and assert, from `EXPLAIN (FORMAT JSON)`,
that the matching partial index is used for each floor and that no plan node
reads more than 10,001 archetype rows.

The partial indexes (section 3.3) cover only rows scoring ≥ 60, so **PR1
changes the rankings route's `min_score` contract deliberately**: today it is
`Query(40, ge=0, le=100)` (`apps/api/src/routers/archetypes.py:511`) and the SQL
binds the requested floor directly (`apps/api/src/ranking/ranking_sql.py:355-357`);
after PR1 it is `Query(60, ge=60, le=100)` — the default request and every
accepted value fall inside the indexed range, and a value below 60 is a 422
rather than a silently truncated or unbounded result. This is a real contract
change and is treated as one: the default, the bounds, the three literal tier
floors, the stored-key definition (`round(score × confidence × completeness ×
10000)`), the 10,000 window and the `is_truncated` rule are all declared in
`PROFILE_SPEC` and therefore hashed into `ranking_sha256`; the route's
`Query(...)` declaration is built from those spec constants rather than typed
beside them, and the identity test mutates the default, a bound, a floor literal
and the key definition in turn and asserts the digest changes each time. The
OpenAPI parameter constraint changes so PR1
regenerates all three typed clients (`apps/web/src/lib/api/generated/*` and
`packages/api-client/src/generated/api.gen.ts`), and the tests cover the default
request, `min_score=60`, `min_score=59` → 422 and `min_score=100`. Nothing in
`apps/web` calls `/api/archetypes/rankings` yet (the F4 UI is unbuilt and the
legacy frontend is retired), so no live caller loses a result. The alternative —
indexing all scores so 0–59 stays bounded — costs ≈ 95 GB of indexes for rows
no planned caller asks for. With the page and the count both served from the
tier partials in canonical order, the F4 design's slice 1c no longer needs a
separate raw-score candidate window: it inherits this contract and specifies
the browser side of the 10,000 window.

The outward ranking and Search response fields do not change: selected score,
tier, confidence, primary, secondary, Best Colony Potential, archetype
confidence, completeness, uncertainty, and ranking identity remain present.
Only `ranking_version`/`ranking_sha256` change. (`apps/api/src/routers/archetypes.py:389-406,422-494`,
`apps/api/src/local_search.py:790-839,951-964`)

Tests must cover all eight key-to-column mappings (score, tier, confidence
**and weighted key**), that the SQL map is derived from the hashed spec and that
mutating a mapping, the floor default/bounds or a floor literal changes
`ranking_sha256`, the literal-floor selection for `min_score` 60/70/76/88/100,
the bounded count, both ranked and count SQL,
unknown-key rejection, and adversarial strings that must never appear in SQL.
Retain selected weighted ordering, no-pick indexable ordering, count/page filter
parity, deterministic tie-breaks, and no-legacy-relation assertions.
(`tests/test_ranking_sql.py:18-73,465-505,597-639,690-712`)

## 7. Migration `015`: attach and publish products on a PUBLISHED generation

Create `sql/v3/migrations/015_v3_derived_product_publication.sql`. It is
additive to applied migration `006`; do not rewrite `006`, because `006` is
already in the production lineage. The existing guards and publication
function are defined in `006`. (`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:32-99,136-206,208-286`,
`sql/v3/migration-manifest.txt:45-55`)

### 7.1 Allowed attachment lifecycle

Replace the relevant guard functions so PUBLISHED joins the existing allowed
base states:

```text
BUILDING | VALIDATING | READY | PUBLISHED
```

This applies to product registration, BUILDING product rows, and chunk receipts,
and to BUILDING → READY/FAILED. Keep every other rule: the product starts
BUILDING without terminal evidence; identity and manifest are immutable;
READY requires a VERIFIED receipt; FAILED requires evidence; product data and
receipts are insert-only; and RETIRED/FAILED base generations reject attachment
or writes. The current exact rules are in migration `006` and rewritten `011`.
(`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:32-99,136-206`,
`sql/v3/migrations/011_v3_system_archetype.sql:77-130`)

### 7.2 Product publication state and audit

Add:

```sql
ALTER TABLE v3_meta.derived_product
    ADD COLUMN published_at timestamptz;
```

`NULL` means the product is not published. Publication is one-way: only NULL →
one timestamp is allowed, only for a READY/VERIFIED product on the current
PUBLISHED generation; the timestamp cannot be changed or cleared.

Add an insert-only audit table:

```sql
CREATE TABLE v3_meta.derived_product_publication_audit (
    derived_generation_id uuid NOT NULL,
    product_code text NOT NULL,
    product_version text NOT NULL,
    manifest_sha256 bytea NOT NULL CHECK (octet_length(manifest_sha256) = 32),
    published_at timestamptz NOT NULL,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    PRIMARY KEY (derived_generation_id, product_code),
    FOREIGN KEY (derived_generation_id, product_code)
        REFERENCES v3_meta.derived_product
);
```

Reject UPDATE, DELETE, and TRUNCATE on the audit. The publication invariants
live in the **table guards themselves**, so a caller who bypasses the function
with paired direct DML (an `UPDATE … SET published_at` plus a hand-written
audit row in one transaction) meets exactly the same checks:

- the existing `BEFORE UPDATE` lifecycle guard on `v3_meta.derived_product`
  keeps its current branch for BUILDING → READY/FAILED (which legitimately
  updates `lifecycle_state`, validation/failure evidence and their timestamps)
  and gains a **publication branch** that applies only when
  `NEW.published_at IS DISTINCT FROM OLD.published_at`: that branch rejects any
  other column changing in the same statement, rejects the change unless the
  old value is `NULL`, itself takes the shared advisory transaction lock
  `764003001` (so no publication can race a generation pointer swap, whether or
  not the function was used), and then requires: the row's generation is the
  current derived pointer **and** `PUBLISHED`; the product is `READY` with a
  `VERIFIED` validation receipt; the new value equals `transaction_timestamp()`;
- a deferred constraint trigger on the same transition requires, at commit, an
  audit row with the exact generation, product, version, manifest hash and
  timestamp;
- the product **INSERT** guard (registration) requires `published_at IS NULL`:
  a product can never be born published, so the only way a timestamp appears is
  the audited UPDATE branch above;
- the audit `INSERT` guard requires, at commit (deferred), that the referenced
  product row's `published_at` equals the audit timestamp and that the
  recorded version and manifest hash match the product row — an audit row
  without the matching publication, or with a different timestamp, fails the
  transaction.

`publish_derived_product` therefore adds nothing the guards do not already
enforce; it is the audited, actor-recording convenience path. A disposable-PG18
test performs the paired direct-DML publication on (a) a non-current
generation, (b) a non-PUBLISHED generation, (c) a product without a VERIFIED
receipt, (d) an already-published product, and (e) a mismatched audit timestamp,
and asserts each fails at the statement or at commit; and that the valid paired
DML on the current PUBLISHED generation holds advisory lock `764003001` while
it runs (observed from a second session with `pg_try_advisory_xact_lock`).

Add:

```text
v3_meta.publish_derived_product(generation_id uuid,
                                product_code text,
                                actor text)
    -> timestamptz
```

The function must:

1. reject a blank actor;
2. take advisory transaction lock `764003001`, the same lock used by product
   mutation and `publish_derived_generation`;
3. require the generation to be the current pointer and PUBLISHED;
4. lock the product row and require READY, VERIFIED, and `published_at IS NULL`;
5. set one transaction timestamp;
6. update `published_at` and insert the matching audit row atomically; and
7. return the timestamp.

It fails if the product is missing, BUILDING, FAILED, already published, belongs
to a non-current/non-PUBLISHED generation, lacks VERIFIED evidence, or changes
while waiting for the lock — and every one of those conditions is also enforced
by the row guards above, so the function is not the only line of defence. The
current guard and generation publisher already share this advisory lock,
preventing registration/finalization from racing a generation pointer swap.
(`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:38-40,69-92,220-267`)

### 7.3 Application visibility

Recreate these application views so they join the current PUBLISHED generation
to the matching product row and require both conditions:

```text
lifecycle_state = 'READY' AND published_at IS NOT NULL
```

- `v3_app.system_search`
- `v3_app.system_archetype`
- `v3_app.system_archetype_summary`

Also update `_current_derived_generation` in `local_search.py` to require both
Finder product rows to be READY and product-published. A missing, BUILDING,
FAILED, READY-but-unpublished, or absent publication timestamp returns 503;
it must not look like a valid empty search. Today the helper requires only
READY, and both local Search and the rankings router use it.
(`apps/api/src/local_search.py:602-643`,
`apps/api/src/routers/archetypes.py:365-373`)

This is defense in depth: views cannot leak partially built rows, and the API
can distinguish unavailable product state from zero matches.

### 7.4 Relationship to generation publication and existing data

Do not change `publish_derived_generation` to publish products. It still
requires every registered product to be READY/VERIFIED before flipping the
generation pointer, but `published_at` is independent and may remain NULL.
This preserves the existing atomic generation completeness gate while allowing
a later explicit product launch. (`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:245-284`)

The pre-`010` READY `system_search` on `ratings_v4_prod_p4_opt1` receives a NULL
`published_at` when `015` is applied and remains invisible because `opt1` is not
the current PUBLISHED generation. The current PUBLISHED
`ratings_v4_prod_p4_parallel_v1` has no Finder products before this rollout.
(`docs/operations/v3-finder-production-rollout-state.md` (PR #805))

### 7.5 Disposable PostgreSQL 18 tests

On a fresh PostgreSQL 18 database, test every rule:

1. registration on BUILDING, VALIDATING, READY, and current PUBLISHED succeeds;
   registration with a non-NULL `published_at` fails whatever the base state;
   registration on RETIRED/FAILED fails;
2. rows and receipts insert only while the product is BUILDING; mutation and
   manifest drift still fail;
3. BUILDING → READY with VERIFIED evidence and BUILDING → FAILED with evidence
   work on PUBLISHED; all other transitions fail;
4. READY-but-unpublished products are absent from all three `v3_app` views and
   make Finder API reads return 503;
5. product publication rejects every wrong state, wrong generation, blank actor,
   missing receipt, and repeat publication;
6. successful publication sets the exact timestamp and exact audit row under
   the shared advisory lock; direct timestamp mutation without audit fails at
   commit; **paired direct DML** (timestamp update plus hand-written audit row)
   fails for a non-current generation, a non-PUBLISHED generation, a product
   without VERIFIED evidence, an already-published product and a mismatched
   timestamp, and when it is valid it demonstrably holds advisory lock
   `764003001`;
7. publishing both products in one transaction makes views and API reads
   available;
8. `publish_derived_generation` succeeds when every registered product is READY
   but unpublished and does not populate `published_at`; and
9. the inherited `opt1` READY product remains NULL/unpublished and invisible.

The present tests already exercise the migration guards, insert-only behavior,
indexes, builder coverage, READY promotion, and API READY gate; extend those
contracts rather than replace them. (`tests/test_v3_system_archetype_migration.py:93-209`,
`tests/test_v3_system_archetype_build.py:62-152`,
`tests/test_v3_system_archetype_validate.py:91-208`,
`tests/test_local_search_v3.py:564-595`)

## 8. Production rollout replacing ROADMAP steps 4–9

The current roadmap says to create a fresh generation, build Search, calibrate,
build Archetype, validate both, and publish the generation. Steps 4–9 are
replaced below; steps 0–3 remain prerequisites. (`docs/ROADMAP.md:154-179`)

All production work remains owner-dispatched through governed actions; this
design authorizes no deployment or production access.

**Authority updates are part of the sequence, not implied by this spec.** This
document is lower in the authority chain than `docs/ROADMAP.md` and
`docs/development/v3-search-spatial-derived-data-decision.md`, so it cannot
replace either; the rollout below is authorized only once both say so:

- `docs/ROADMAP.md` — PR #805 (which this PR depends on and which merges first)
  records the owner's A + B decision in the controlling sequence, marks steps
  4–9 superseded, lists the replacement steps 4′–9′, and blocks every production
  step beyond step 0 (including migration plan/apply) until the rewritten `011`
  and `015` are registered. PR #805 also adds
  `docs/operations/v3-finder-capacity-decision-2026-10-10.md` (the decision and
  its numbers) and the step 0 receipt; the citations in this document resolve
  when it merges.
- `docs/development/v3-search-spatial-derived-data-decision.md` currently says
  “Published derived generations are immutable. Recalculation creates a new
  generation” (its section 1). **PR2 amends that sentence** with the explicit
  exception this design introduces: the ratings relations of a published
  generation stay immutable and are never recalculated in place; *derived
  products* (separately registered, insert-only projections with their own
  manifests and receipts) may be **added** to the published generation and
  become visible only through the explicit product-publication gate of
  migration `015`. PR2's file list and tests include that amendment, so no
  operator is left with two contradictory procedures.

| # | Governed step | Reuse/build status | Persistent product disk written |
|---:|---|---|---:|
| 1 | Amend step-1 registration to ordered `[014, 010, 011-rewritten, 013, 015]`, recompute every migration-set/transition identity, and re-attest reachable prefixes. | Reuse the V3 manifest/schema-identity mechanism; PR1 (rewritten `011`) and PR2 (`015`) each recut the authority and the hard-coded lineage tests, so this step is complete when PR2 merges. Current registered tail is `[014,010,011,013]`. (`sql/v3/migration-manifest.txt:52-55`, `docs/ROADMAP.md:121-127`) | negligible catalog/empty-DDL space |
| 2 | Run governed migration `plan`, review the exact receipt, then separately `apply`. | Reuse `.github/workflows/v3-production-schema-migration.yml`; no new action. The pending-set process is already the roadmap step 2. (`docs/ROADMAP.md:162-168`) | negligible product rows; creates empty `011`/`015` structures |
| 3 | Validate all 18 deferred `system_search` constraints after `010`. | Reuse built `v3-system-search-validate-constraints-start/status`; it changes catalog validation flags, not data rows. (`scripts/operator/actions/v3-system-search-validate-constraints.sh:1-6,24-55,70-90`) | no product rows |
| 4 | Run the bounded coefficient-calibration probe on `ratings_v4_prod_p4_parallel_v1` and record the decision before Archetype registration. | Reuse built `v3-archetype-calibration-probe` unchanged. It is read-only and reads vectors, not the stored product. (`scripts/operator/actions/v3-archetype-calibration-probe.sh:1-5,21,77-85,135-157`, `scripts/v3_archetype_calibration_probe.py:212-220,256-298`) | 0 GB |
| 5 | Register, build, and validate post-`010` `system_search` on the pinned current `ratings_v4_prod_p4_parallel_v1`. | Retarget the existing F1 start/status action from `opt1`, pin exact `010` and `015` ledger hashes, accept only the exact current PUBLISHED generation, and retain its validation receipt. The current action is hard-coded to `opt1` and checks only `006`. (`scripts/operator/actions/v3-system-search-f1.sh:15-20,76-113,175-176`) | about **87 GB** (measured/extrapolated post-`010`) (`docs/operations/v3-finder-production-rollout-state.md` (PR #805)) |
| 6 | Register, build, and validate wide `system_archetype` on the same pinned generation. | Build a new governed Archetype start/status action using the F1 safety pattern; it must invoke the existing CLI build then `--validate`, pin rewritten `011` and `015`, and receipt READY/VERIFIED plus row/chunk counts. The roadmap records that this governed validation route does not exist today. (`docs/ROADMAP.md:190-195`, `scripts/v3_system_archetype.py:1109-1154`) | **about 76 GB** on the synthetic distribution (section 3.4); the tier-partial indexes are sized from the step-4 calibration histogram and re-measured with the final migration text before the build |
| 7 | In one governed transaction, call `publish_derived_product` for `system_search` and `system_archetype`; verify both timestamps/audits and view counts. | Build a new product-publish action, modeled on the pinned, separately receipted spatial publish pattern; no derived-generation publication occurs. The current workflow allowlist has no Archetype-build or product-publish operation. (`.github/workflows/chatgpt-ed-new-ops.yml:10-24,81-84`) | negligible metadata/audit rows |
| 8 | Revise the F3 application-release gate to require exact current generation key/UUID/sequence, both product versions/manifests, READY+published timestamps, validation/publication audits, row counts, and the new ranking version/SHA. | Amend the existing release authority; no new build action. Its current assumptions predate attach-to-PUBLISHED. (`docs/operations/v3-production-application-release.md:286-337`) | 0 GB |
| 9 | Build the immutable release, run preflight, and promote only after the revised gate passes. | Reuse the existing governed application release and deployment workflows; no new Finder data action. (`CLAUDE.md:31-37,82-91`) | 0 GB of Finder product data |

Total new persistent Finder data is planned at about 163 GB (87 GB Search plus
76 GB Archetype, both from PostgreSQL 18.4 samples; the archetype figure moves
with the real per-floor fractions, and the design stops if the histogram puts
the ≥ 60 fraction above ≈ 40 % on several keys), leaving about 129 GB from
the observed 292 GB before transient WAL/temp/vacuum use. The
re-measurement of the final wide relation and all its indexes, not this
arithmetic, decides whether step 6 may start.
(`docs/operations/v3-finder-production-rollout-state.md` (PR #805))

## 9. Fixtures and validation lanes

The shared fixture seed already runs the genuine Search and Archetype
register/build/validate pipelines, then publishes the generation. Update it to
apply `015`, build one wide row per system, publish the generation, and then
publish both products in one transaction. Update the Cypress wrapper's wording
and assertions to require READY **and** product-published.
(`scripts/dev/seed_v3_fixture_generation.py:27-52,267-300`,
`scripts/dev/seed_cypress_v3_generation.py:1-11,32-43`)

Review Lab reads `sql/v3/migration-manifest.txt` from current main and applies
every declared V3 migration in order, and nothing else — a seed may not apply a
migration the manifest does not declare. The rewritten `011` therefore has to be
registered (manifest hash **and** the production authority recut) in the same PR
that rewrites it (PR1), and `015` in the same PR that adds it and makes the seed
publish products (PR2); otherwise those PRs' Review Lab runs fail at their own
heads. Its dedicated seed delegates to the
same shared fixture builder. (`scripts/dev/review_lab/lifecycle.py:426-443`,
`tests/test_review_lab_v3.py:505-518`,
`scripts/dev/seed_review_v3_generation.py:1-19`)

Change tests as follows:

- Migration/builder tests assert one wide row per system, all 24 key columns,
  all constraints, eight picked-score indexes, the weighted index, folded
  summary view, complete-row seal, and unchanged chunk resumability.
- Cypress and Review Lab seed tests assert both product rows are READY,
  `published_at IS NOT NULL`, one wide row per fixture system, and unchanged
  Search/ranking response fields.
- Product E2E keeps the normal Finder journey; Review Lab keeps isolated
  synthetic/failure behavior. Source, migration, builder, lifecycle, and API
  invariants remain normal CI, not duplicated browser tests. The lane authority
  assigns those responsibilities explicitly.
  (`docs/development/v3-browser-validation-lanes.md:7-21,29-60,62-103,122-148`)
- The calibration-probe test continues to assert that vectors are read and no
  archetype product rows are written; the probe does not depend on the stored
  layout. (`scripts/v3_archetype_calibration_probe.py:22-29,98-114,212-220,256-298`)

## 10. Implementation plan: small PRs

Every PR must pass every protected check on its exact latest head and both
required reviews, with every substantive finding dispositioned. The exact
branch-protection configuration is **Unverified** from repository contents;
the repository requires at least backend, integration, migration/script,
canonical-safety, Svelte, Cypress, image-parity, Review Lab, and security gates.
(`docs/development/pull-request-acceptance-policy.md:3-45`, `CLAUDE.md:190-200`)

### Sequencing rule: every PR green at its own head

Three facts force the PR boundaries (review finding, round 1):

1. CI checks every manifest hash against the migration file bytes, and the
   production-operator, watchlist and application-deployment tests recompute the
   migration-set/schema identities and compare them with
   `deploy/v3-production/target-authority.json`. Changing a registered
   migration's bytes therefore requires the manifest hash **and the full authority
   recut and its tests** in the same PR — there is no "mechanical hash refresh"
   that leaves the authority for later.
   (`sql/v3/migration-manifest.txt:52-55`, `tests/test_v3_lineage_migrations.py:34-60`,
   `tests/test_v3_watchlist_postgres.py`, `tests/test_v3_production_application_deployment.py`)
2. Review Lab and the PostgreSQL rankings integration tests apply the fixture
   migrations and then execute the live ranking SQL. The current SQL joins
   `a.archetype_key` and reads `a.archetype_score`/`a.confidence`, columns the
   wide rewrite removes, so the ranking SQL and router adaptation must land with
   the schema change, not after it. (`apps/api/src/ranking/ranking_sql.py:303-329`)
3. Review Lab applies only manifest-declared migrations, so the fixture seed can
   publish products only once `015` is registered in the same PR.

Four PRs follow; the earlier five-PR split (schema first, ranking SQL third,
registration fourth) could not have been green at any intermediate head.

### PR1 — wide `011` + model + builder/validator + ranking SQL + registration

Files:

- `sql/v3/migrations/011_v3_system_archetype.sql` (rewritten)
- `shared_contracts/v3_system_archetype_model.py` (new canonical model)
- `scripts/v3_system_archetype_model.py` (compatibility re-export)
- `scripts/v3_system_archetype.py`
- `scripts/v3_archetype_calibration_probe.py` (shared-model import only)
- `apps/api/src/ranking/profile.py` (`RANKING_VERSION = 'v3-colony-potential-2'`,
  new pinned `ranking_sha256`)
- `apps/api/src/ranking/ranking_sql.py` (fixed key → wide-column map; no-pick
  path unchanged through the `v3_app.system_archetype_summary` view)
- `apps/api/src/routers/archetypes.py` (`min_score` → `Query(60, ge=60, le=100)`;
  response fields unchanged)
- `apps/web/src/lib/api/generated/types.gen.ts`,
  `apps/web/src/lib/api/generated/sdk.gen.ts`,
  `packages/api-client/src/generated/api.gen.ts` (regenerated for the changed
  parameter constraint)
- `scripts/dev/measure_wide_archetype_footprint.py` (gains `--migration-sql
  sql/v3/migrations/011_v3_system_archetype.sql`: applies the final migration
  text to the disposable database instead of its built-in DDL, fills the real
  `v3_derived.system_archetype` with synthetic rows whose per-key ≥ 60 fractions
  come from the calibration-probe histogram, and sizes the heap and all nine
  indexes; the committed built-in layouts stay as the pre-migration reference)
- `tests/test_measure_wide_archetype_footprint.py`
- `scripts/dev/seed_v3_fixture_generation.py`,
  `scripts/dev/seed_cypress_v3_generation.py` (wide rows; generation publication
  as today — product publication waits for PR2)
- `sql/v3/migration-manifest.txt` (rewritten `011` hash)
- `deploy/v3-production/target-authority.json` and
  `docs/operations/v3-production-application-release.md` (recomputed
  migration-set/schema identities for the ordered set
  `[014, 010, 011-rewritten, 013]`)
- `scripts/operator/actions/v3-derived-lifecycle-status.sh` (pending-set
  contract, if it pins hashes)
- tests: `tests/test_v3_system_archetype_migration.py`,
  `tests/test_v3_system_archetype_model.py`,
  `tests/test_v3_system_archetype_register.py`,
  `tests/test_v3_system_archetype_build.py`,
  `tests/test_v3_system_archetype_validate.py`,
  `tests/test_v3_system_archetype_cli.py`,
  `tests/test_v3_archetype_calibration_probe.py`,
  `tests/test_ranking_profile_identity.py`, `tests/test_ranking_sql.py`,
  `tests/test_archetype_rankings_v3.py`,
  `tests/test_ranking_identity_and_no_legacy.py`,
  `tests/test_seed_cypress_v3_generation.py`,
  `tests/test_seed_review_v3_generation.py`,
  `tests/test_v3_lineage_migrations.py`,
  `tests/test_v3_production_migration_operation.py`,
  `tests/test_v3_system_search_production_operator.py`,
  `tests/test_v3_watchlist_postgres.py`,
  `tests/test_v3_production_application_deployment.py`

Focused checks: Ruff for changed Python; all `test_v3_system_archetype_*`,
calibration, ranking profile/SQL/identity and no-legacy tests; disposable-PG18
migration/build/validate and rankings integration tests; both seed test modules;
exact `011` file hash, ordered migration-set identity and schema-identity
reproduction, plan exact-prefix and every reachable accepted-release prefix; a
new PG18 footprint receipt from
`scripts/dev/measure_wide_archetype_footprint.py --migration-sql …` run against
the final `011` text (heap and all nine indexes, partial ones included);
migration/script, PostgreSQL integration, canonical-safety,
application-deployment, Cypress, Review Lab and security CI. The rankings
response shape does not change, but the `min_score` parameter constraint does,
so PR1 regenerates the typed clients and the OpenAPI drift check proves they
match.

### PR2 — migration `015`, builders on PUBLISHED, API publication gate, registration

Files:

- `sql/v3/migrations/015_v3_derived_product_publication.sql` (new)
- `scripts/v3_system_search.py`, `scripts/v3_system_archetype.py` (accept the
  current PUBLISHED base generation)
- `apps/api/src/local_search.py` (`_current_derived_generation` requires READY
  **and** `published_at`)
- `scripts/dev/seed_v3_fixture_generation.py` (publish both products in one
  transaction after generation publication)
- `sql/v3/migration-manifest.txt` (`015` appended)
- `deploy/v3-production/target-authority.json` and
  `docs/operations/v3-production-application-release.md` (identities recut for
  `[014, 010, 011-rewritten, 013, 015]`)
- `docs/development/v3-search-spatial-derived-data-decision.md` (section 1:
  the product-attachment exception to generation immutability, as worded in
  section 8 above)
- `docs/ROADMAP.md` (step 4′ progress note only; the sequence itself comes from
  PR #805)
- tests: `tests/test_v3_derived_product_publication.py` (new: the full
  disposable-PG18 lifecycle matrix of section 7.5, including paired direct DML),
  `tests/test_local_search_v3.py`, `tests/test_archetype_rankings_v3.py`,
  `tests/integration/conftest.py`, `tests/test_seed_cypress_v3_generation.py`,
  `tests/test_seed_review_v3_generation.py`, `tests/test_v3_lineage_migrations.py`,
  `tests/test_v3_production_migration_operation.py`,
  `tests/test_v3_system_search_production_operator.py`,
  `tests/test_v3_watchlist_postgres.py`,
  `tests/test_v3_production_application_deployment.py`

Focused checks: Ruff; the new lifecycle matrix; Search and Archetype builder
tests on PUBLISHED; local Search and rankings READY-but-unpublished (503) and
fully-published cases; fixture seed tests; exact `015` hash and recut
identities; backend unit, PostgreSQL-integration, migration/script,
canonical-safety, application-deployment, Cypress, Review Lab and security CI.

### PR3 — on-demand explanation endpoint and generated clients

Files:

- `apps/api/src/routers/archetypes.py` (new
  `GET /api/archetypes/system/{id64}/explanation`; legacy route untouched)
- `apps/api/src/models.py` (response model)
- `apps/web/src/lib/api/generated/types.gen.ts`,
  `apps/web/src/lib/api/generated/sdk.gen.ts` **and**
  `packages/api-client/src/generated/api.gen.ts` — all three are regenerated by
  `pnpm generate:api` and the OpenAPI drift check fails on any of them
  (`apps/web/package.json:28`, `.github/workflows/ci.yml:524`)
- tests: `tests/test_archetype_system_v3.py` (new: exact-version rule, 409
  detail string, `fit_all` not called on mismatch, values identical to the
  stored wide row on match), `tests/test_ranking_identity_and_no_legacy.py`

Focused checks: Ruff; disposable-PG18 explanation endpoint tests; OpenAPI
generation/drift; `pnpm check`, `pnpm test`, `pnpm build`; backend,
integration, Svelte, Cypress, Review Lab and image-parity CI.

### PR4 — governed operator actions and revised release gate

Files:

- `scripts/operator/actions/v3-system-search-f1.sh` (retarget from `opt1` to the
  exact current PUBLISHED `ratings_v4_prod_p4_parallel_v1`; pin `010` and `015`
  ledger hashes)
- `scripts/operator/actions/v3-system-archetype.sh` (new start/status: build
  then `--validate`, pin rewritten `011` and `015`, receipt READY/VERIFIED plus
  row/chunk counts)
- `scripts/operator/actions/v3-publish-derived-products.sh` (new: both products
  in one transaction via `publish_derived_product`; receipts timestamps, audits
  and view counts)
- `.github/workflows/chatgpt-ed-new-ops.yml` (allowlist entries)
- `docs/operations/v3-finder-production-rollout-state.md`,
  `docs/operations/v3-production-application-release.md` (revised F3 release
  gate: exact generation key/UUID/sequence, both product versions/manifests,
  READY + `published_at`, validation/publication audits, row counts, new ranking
  version/SHA)
- `deploy/v3-production/target-authority.json` (release-gate fields only; the
  migration identities were recut in PR1/PR2)
- tests: `tests/test_v3_system_search_production_operator.py`,
  `tests/test_v3_system_archetype_production_operator.py` (new),
  `tests/test_v3_product_publication_operator.py` (new),
  `tests/test_v3_production_application_deployment.py`

Focused checks: shell/action contract tests; exact generation UUID/key/sequence,
current-pointer, migration-hash, worker-name, resource-bound, receipt and
start/status tests; repeat/concurrent publication failures; allowlist/workflow
schema; revised release-preflight tests; operator, canonical-safety, migration,
application-deployment and security CI. The existing action is demonstrably
pinned to `opt1`, while the current workflow lacks Archetype and product-publish
operations. (`scripts/operator/actions/v3-system-search-f1.sh:15-24,76-113,175-176`,
`.github/workflows/chatgpt-ed-new-ops.yml:10-24,81-84`)

## 11. Risks and open questions

Each unresolved choice is phrased for an explicit yes/no disposition.

1. **Yes/no: approve the section 3.3 layout — eight stored `<key>_weighted_e4`
   ranking keys, primary key, weighted index, and 24 partial
   `(generation, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 60 / 76 /
   88` indexes (≈ 76 GB on the synthetic distribution; sized from the
   calibration probe's real tier histogram and re-measured with the final `011`
   text before the production build; the design stops if the ≥ 60 fraction
   exceeds ≈ 40 % on several keys)?** This refines the partial layout the owner
   approved on 2026-10-10 (question 6 of the capacity decision, ≈ 66 GB): review
   round 5 showed a raw-score window sorted afterwards is an approximation of
   the ranking profile, so the canonical key is stored and indexed instead
   (+10 GB). The deduplicating and score-ordered variants are kept in the
   evidence as rejected; the full unique-entry variant costs ≈ 95 GB of indexes
   for rows no caller can ask for.
   **Owner: yes to the partial principle on 2026-10-10 and yes to the
   stored-key refinement on 2026-10-11 (recorded as question 6b of the capacity
   decision).**
2. **Yes/no: approve exact integer parts-per-million confidence storage
   (`<key>_confidence_ppm integer`, 0–1,000,000) with the ranking expression
   `ppm / 1000000.0` and API serialization `ppm / 1e6`?** Same 4 bytes as
   `real`, exact six-decimal semantics everywhere, no tolerance in validation;
   `real` would let float32 error reorder near-ties and `double precision`
   measured +14 GB.
3. **Yes/no: approve moving the canonical pure fit model into
   `shared_contracts/` with a temporary `scripts/` re-export?** Without this,
   the release API image cannot call the same `fit_all` implementation because
   it does not contain `scripts/`. (`apps/api/Dockerfile:20-24`)
4. **Yes/no: approve the new additive explanation route and leave the legacy
   `/api/archetypes/system/{id64}` route unchanged until all of its V2-only
   topology/pair/trait fields have a V3 source?** Repointing the old route now
   would silently drop fields. (`apps/api/src/routers/archetypes.py:631-759`)
5. **Yes/no: approve HTTP 409 with exact detail
   `explanation unavailable for this product version` for model/product version
   mismatch?** This is a stable compatibility conflict, not “system not found.”
   **Owner: yes (2026-10-10, recorded as question 5 of the capacity decision;
   the exact detail string and the model-hash check are this design's
   implementation of that rule).**
6. **Yes/no: require production publication of both Finder products in one
   transaction?** The API fails closed unless both are published, but one
   transaction gives a cleaner audit boundary.
7. **Yes/no: accept the four-PR sequencing in section 10, where PR1 (wide
   `011` + ranking SQL + full registration/authority recut) and PR2 (`015` +
   publication gate + recut) each carry their own registration so every head is
   green?** The alternative — a separate registration PR — cannot pass the
   manifest-integrity and authority-identity tests at intermediate heads.
8. **Yes/no: accept no purge before Finder promotion?** This is the recorded
   owner decision; changing it would require a separate destructive-data design
   and authority. (`docs/operations/v3-finder-production-rollout-state.md` (PR #805))

## 12. Design acceptance

Implementation is acceptable only when:

- every system produces one wide row whose model outputs match the pre-rewrite
  outputs under the exact integer-ppm confidence rule;
- the measured PG18 heap and every index fit the approved disk/WAL/temp/vacuum
  envelope;
- READY is not visible until explicit product publication;
- product attachment to PUBLISHED retains every existing fail-closed manifest,
  receipt, transition, insert-only, and generation-publication rule;
- ranking response fields are unchanged and carry the new pinned identity;
- explanation mismatch fails with the exact version rule and message;
- Cypress and Review Lab use the real wide product and explicit publication;
  and
- exact-head CI/review acceptance is complete under the repository policy.
  (`docs/development/pull-request-acceptance-policy.md:3-45`)

Planned implementation commit message:

```text
docs(finder): F2d design — wide-row archetype product and product attachment/publication on a published generation
```
