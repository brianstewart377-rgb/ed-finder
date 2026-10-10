# V3 Finder F2d — wide archetype product and product attachment/publication

**Status:** Design only; not implemented

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
six decimal places. Migration `011` will use the required PostgreSQL `real`
columns; builders, validators, and API serialization must compare or emit the
six-decimal model value so float32 representation does not become a visible
behavior change. The current model already rounds fit and summary confidence to
six places. (`scripts/v3_system_archetype_model.py:114-131,141-145,192-205`)

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
    paradise_confidence real NOT NULL CHECK (paradise_confidence BETWEEN 0 AND 1),

    mining_hub_score smallint NOT NULL CHECK (mining_hub_score BETWEEN 0 AND 100),
    mining_hub_tier char(1) NOT NULL CHECK (mining_hub_tier IN ('S','A','B','C','D')),
    mining_hub_confidence real NOT NULL CHECK (mining_hub_confidence BETWEEN 0 AND 1),

    manufacturing_hub_score smallint NOT NULL CHECK (manufacturing_hub_score BETWEEN 0 AND 100),
    manufacturing_hub_tier char(1) NOT NULL CHECK (manufacturing_hub_tier IN ('S','A','B','C','D')),
    manufacturing_hub_confidence real NOT NULL CHECK (manufacturing_hub_confidence BETWEEN 0 AND 1),

    megacomplex_score smallint NOT NULL CHECK (megacomplex_score BETWEEN 0 AND 100),
    megacomplex_tier char(1) NOT NULL CHECK (megacomplex_tier IN ('S','A','B','C','D')),
    megacomplex_confidence real NOT NULL CHECK (megacomplex_confidence BETWEEN 0 AND 1),

    research_hub_score smallint NOT NULL CHECK (research_hub_score BETWEEN 0 AND 100),
    research_hub_tier char(1) NOT NULL CHECK (research_hub_tier IN ('S','A','B','C','D')),
    research_hub_confidence real NOT NULL CHECK (research_hub_confidence BETWEEN 0 AND 1),

    stronghold_score smallint NOT NULL CHECK (stronghold_score BETWEEN 0 AND 100),
    stronghold_tier char(1) NOT NULL CHECK (stronghold_tier IN ('S','A','B','C','D')),
    stronghold_confidence real NOT NULL CHECK (stronghold_confidence BETWEEN 0 AND 1),

    population_capital_score smallint NOT NULL CHECK (population_capital_score BETWEEN 0 AND 100),
    population_capital_tier char(1) NOT NULL CHECK (population_capital_tier IN ('S','A','B','C','D')),
    population_capital_confidence real NOT NULL CHECK (population_capital_confidence BETWEEN 0 AND 1),

    flexible_score smallint NOT NULL CHECK (flexible_score BETWEEN 0 AND 100),
    flexible_tier char(1) NOT NULL CHECK (flexible_tier IN ('S','A','B','C','D')),
    flexible_confidence real NOT NULL CHECK (flexible_confidence BETWEEN 0 AND 1),

    primary_archetype text NOT NULL,
    secondary_archetype text,
    best_colony_potential smallint NOT NULL
        CHECK (best_colony_potential BETWEEN 0 AND 100),
    best_tier char(1) NOT NULL CHECK (best_tier IN ('S','A','B','C','D')),
    archetype_confidence real NOT NULL
        CHECK (archetype_confidence BETWEEN 0 AND 1),
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
       archetype_confidence, weighted_potential, computed_at
FROM v3_app.system_archetype;
```

That preserves the join name used by both ranked and count query builders while
removing duplicated storage. The current common SQL always joins that name.
(`apps/api/src/ranking/ranking_sql.py:246-263,294-301,512-546`)

### 3.3 Indexes

Create these nine secondary indexes in addition to the primary key:

```text
(derived_generation_id, paradise_score DESC)
(derived_generation_id, mining_hub_score DESC)
(derived_generation_id, manufacturing_hub_score DESC)
(derived_generation_id, megacomplex_score DESC)
(derived_generation_id, research_hub_score DESC)
(derived_generation_id, stronghold_score DESC)
(derived_generation_id, population_capital_score DESC)
(derived_generation_id, flexible_score DESC)
(derived_generation_id, weighted_potential DESC)
```

The first eight provide the `min_development_score` / tier-floor range path for
a picked archetype. They deliberately do **not** carry a trailing `system_id64`:
the picked ranking orders by the computed product
`score × confidence × completeness`, which no score index can serve, the wide
row is joined through its primary key (one row per system — the old
`archetype_key` lookup no longer exists), and `ORDER BY … system_id64 ASC` is
applied by the sort either way. Leaving `system_id64` out lets PostgreSQL's
B-tree deduplication collapse the 101 distinct score values into posting lists:
measured 7.5 B/row per index instead of 49.8 B/row (section 3.4). The last index
retains the current indexable no-pick ordering. Picked ranking still applies the
profile's confidence/completeness modifier after selecting the trusted score
column, while no-pick ordering uses the stored `weighted_potential` directly.
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
| table heap (`pg_table_size`; average tuple 180 B) | 186.4 | 37.0 GB |
| primary key `(derived_generation_id, system_id64)` | 40.7 | 8.1 GB |
| `weighted_potential` index | 40.8 | 8.1 GB |
| eight `(derived_generation_id, <key>_score DESC)` indexes, deduplicated | 8 × 7.5 = 60 | 11.9 GB |
| **total, section 3.3 layout** | **328** | **≈ 65 GB** |
| *(rejected)* the same with `system_id64` trailing in each score index | 8 × 49.8 + 81.5 = 480 index | ≈ 132 GB |

The decision text's earlier “about 80 GB” and this design's first-draft
“about 90 GB” were unmeasured guesses: the heap is wider than assumed (186 B,
not 150 B) and a unique-entry score index is 49.8 B/row, not 30 B. The
measured layout is **≈ 65 GB** of persistent product data. The production gate
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
`GET /api/archetypes/system/{id64}/explanation`; leave the existing legacy
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
must compare recomputed score/tier/six-decimal confidence and summary values to
the stored wide row and fail closed on a mismatch; explanation delivery must
never silently describe a different stored score.

### 4.3 Exact version rule

Serve explanations only when all three values are equal:

```text
v3_meta.derived_product.product_version
    == v3_derived.system_archetype.archetype_version
    == deployed shared model ARCHETYPE_VERSION
```

The product must also be READY and product-published on the current PUBLISHED
generation. On any version mismatch, return HTTP 409 with the exact FastAPI
detail string:

```text
explanation unavailable for this product version
```

Perform this check before reading vector/opportunity inputs or calling
`fit_all`. The exact contract test patches `fit_all`, supplies a READY and
published product whose version differs from the deployed model, asserts HTTP
409 and the exact detail string, and asserts `fit_all` was not called. Matching
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
`wide_columns` list, `storage_layout: "one-row-per-system-v1"`,
`explanation_delivery: "on-demand"`, confidence storage/rounding policy, and
the shared model file hash. Remove the persisted-explanation field policy. The
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
- every tier equals `tier_of(its score)`;
- each stored float32 confidence rounds to the model's six-decimal value and is
  within the float32 tolerance selected by the tests;
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
    "paradise": ("a.paradise_score", "a.paradise_tier", "a.paradise_confidence"),
    # ...seven more fixed entries...
}
```

The router first rejects a key outside `ARCHETYPE_KEYS`; the SQL builder then
looks up the fixed expression. No raw or transformed user string is ever
formatted as a SQL identifier. SQL values remain parameters. The current
router already returns 422 for an unknown key, while the current SQL binds the
key as a row value and reads `a.archetype_score`; only that row-form resolution
changes. (`apps/api/src/routers/archetypes.py:294-316`,
`apps/api/src/ranking/ranking_sql.py:303-329`)

`build_ranked_query` and `build_count_query` continue sharing `_build_common`.
For a picked archetype, join the one wide `v3_app.system_archetype` row by
`system_id64` and select the mapped score/confidence columns. For no pick, keep
the `v3_app.system_archetype_summary` join and
`sum.weighted_potential DESC NULLS LAST` unchanged. Preserve distance then
`system_id64` tie-breaks and all selected aliases.
(`apps/api/src/ranking/ranking_sql.py:246-263,294-329,451-506,512-546`)

The outward ranking and Search response fields do not change: selected score,
tier, confidence, primary, secondary, Best Colony Potential, archetype
confidence, completeness, uncertainty, and ranking identity remain present.
Only `ranking_version`/`ranking_sha256` change. (`apps/api/src/routers/archetypes.py:389-406,422-494`,
`apps/api/src/local_search.py:790-839,951-964`)

Tests must cover all eight key-to-column mappings, both ranked and count SQL,
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

Reject UPDATE, DELETE, and TRUNCATE on the audit. Add a deferred constraint
trigger on a `derived_product.published_at` transition that requires an audit
row with the exact generation, product, version, manifest hash, and timestamp;
add an audit INSERT guard that requires the matching READY product and exact
timestamp. This prevents an unaudited timestamp update at commit while keeping
the publication function atomic.

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
while waiting for the lock. The current guard and generation publisher already
share this advisory lock, preventing registration/finalization from racing a
generation pointer swap. (`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:38-40,69-92,220-267`)

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
   commit;
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

| # | Governed step | Reuse/build status | Persistent product disk written |
|---:|---|---|---:|
| 1 | Amend step-1 registration to ordered `[014, 010, 011-rewritten, 013, 015]`, recompute every migration-set/transition identity, and re-attest reachable prefixes. | Reuse the V3 manifest/schema-identity mechanism; PR4 must update its authority and hard-coded lineage tests. Current registered tail is `[014,010,011,013]`. (`sql/v3/migration-manifest.txt:52-55`, `docs/ROADMAP.md:121-127`) | negligible catalog/empty-DDL space |
| 2 | Run governed migration `plan`, review the exact receipt, then separately `apply`. | Reuse `.github/workflows/v3-production-schema-migration.yml`; no new action. The pending-set process is already the roadmap step 2. (`docs/ROADMAP.md:162-168`) | negligible product rows; creates empty `011`/`015` structures |
| 3 | Validate all 18 deferred `system_search` constraints after `010`. | Reuse built `v3-system-search-validate-constraints-start/status`; it changes catalog validation flags, not data rows. (`scripts/operator/actions/v3-system-search-validate-constraints.sh:1-6,24-55,70-90`) | no product rows |
| 4 | Run the bounded coefficient-calibration probe on `ratings_v4_prod_p4_parallel_v1` and record the decision before Archetype registration. | Reuse built `v3-archetype-calibration-probe` unchanged. It is read-only and reads vectors, not the stored product. (`scripts/operator/actions/v3-archetype-calibration-probe.sh:1-5,21,77-85,135-157`, `scripts/v3_archetype_calibration_probe.py:212-220,256-298`) | 0 GB |
| 5 | Register, build, and validate post-`010` `system_search` on the pinned current `ratings_v4_prod_p4_parallel_v1`. | Retarget the existing F1 start/status action from `opt1`, pin exact `010` and `015` ledger hashes, accept only the exact current PUBLISHED generation, and retain its validation receipt. The current action is hard-coded to `opt1` and checks only `006`. (`scripts/operator/actions/v3-system-search-f1.sh:15-20,76-113,175-176`) | about **87 GB** (measured/extrapolated post-`010`) (`docs/operations/v3-finder-production-rollout-state.md` (PR #805)) |
| 6 | Register, build, and validate wide `system_archetype` on the same pinned generation. | Build a new governed Archetype start/status action using the F1 safety pattern; it must invoke the existing CLI build then `--validate`, pin rewritten `011` and `015`, and receipt READY/VERIFIED plus row/chunk counts. The roadmap records that this governed validation route does not exist today. (`docs/ROADMAP.md:190-195`, `scripts/v3_system_archetype.py:1109-1154`) | **about 65 GB** (200k-row PG18.4 sample, section 3.4), re-measured with the final migration text before the build |
| 7 | In one governed transaction, call `publish_derived_product` for `system_search` and `system_archetype`; verify both timestamps/audits and view counts. | Build a new product-publish action, modeled on the pinned, separately receipted spatial publish pattern; no derived-generation publication occurs. The current workflow allowlist has no Archetype-build or product-publish operation. (`.github/workflows/chatgpt-ed-new-ops.yml:10-24,81-84`) | negligible metadata/audit rows |
| 8 | Revise the F3 application-release gate to require exact current generation key/UUID/sequence, both product versions/manifests, READY+published timestamps, validation/publication audits, row counts, and the new ranking version/SHA. | Amend the existing release authority; no new build action. Its current assumptions predate attach-to-PUBLISHED. (`docs/operations/v3-production-application-release.md:286-337`) | 0 GB |
| 9 | Build the immutable release, run preflight, and promote only after the revised gate passes. | Reuse the existing governed application release and deployment workflows; no new Finder data action. (`CLAUDE.md:31-37,82-91`) | 0 GB of Finder product data |

Total new persistent Finder data is planned at about 152 GB (87 GB Search plus
65 GB Archetype, both from 200k-row PostgreSQL 18.4 samples), leaving about
140 GB from the observed 292 GB before transient WAL/temp/vacuum use. The
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
every declared V3 migration in order; it therefore receives rewritten `011`
and new `015` only after PR4 registration. Its dedicated seed delegates to the
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

### PR1 — rewrite `011`; model, builder, validator, and wide fixtures

Files:

- `sql/v3/migrations/011_v3_system_archetype.sql`
- `shared_contracts/v3_system_archetype_model.py` (new canonical model)
- `scripts/v3_system_archetype_model.py` (compatibility re-export)
- `scripts/v3_system_archetype.py`
- `scripts/v3_archetype_calibration_probe.py` (shared-model import only)
- `scripts/dev/seed_v3_fixture_generation.py`
- `scripts/dev/seed_cypress_v3_generation.py`
- `tests/test_v3_system_archetype_migration.py`
- `tests/test_v3_system_archetype_model.py`
- `tests/test_v3_system_archetype_register.py`
- `tests/test_v3_system_archetype_build.py`
- `tests/test_v3_system_archetype_validate.py`
- `tests/test_v3_system_archetype_cli.py`
- `tests/test_v3_archetype_calibration_probe.py`
- `tests/test_seed_cypress_v3_generation.py`
- `tests/test_seed_review_v3_generation.py`

Focused checks: Ruff for changed Python; all `test_v3_system_archetype_*` and
calibration tests; disposable-PG18 migration/build/validate tests; both seed
test modules; a new ~200k-row PG18 footprint receipt using
`pg_table_size`/`pg_indexes_size`; migration/script, PostgreSQL integration,
canonical-safety, Cypress, and Review Lab CI.

### PR2 — migration `015` and API publication gate

Files:

- `sql/v3/migrations/015_v3_derived_product_publication.sql` (new)
- `scripts/v3_system_search.py`
- `scripts/v3_system_archetype.py`
- `apps/api/src/local_search.py`
- `scripts/dev/seed_v3_fixture_generation.py`
- `tests/test_v3_derived_product_publication.py` (new)
- `tests/test_local_search_v3.py`
- `tests/test_archetype_rankings_v3.py`
- `tests/integration/conftest.py`
- `tests/test_seed_cypress_v3_generation.py`
- `tests/test_seed_review_v3_generation.py`

Focused checks: Ruff; the new disposable-PG18 lifecycle matrix; Search and
Archetype builder tests on PUBLISHED; local Search and rankings READY-but-
unpublished/fully-published cases; fixture seed tests; backend unit,
PostgreSQL-integration, migration/script, canonical-safety, Cypress, and Review
Lab CI.

### PR3 — ranking SQL and on-demand explanation endpoint

Files:

- `apps/api/src/ranking/profile.py`
- `apps/api/src/ranking/ranking_sql.py`
- `apps/api/src/routers/archetypes.py`
- `apps/api/src/models.py`
- `apps/web/src/lib/api/generated/types.gen.ts`
- `apps/web/src/lib/api/generated/sdk.gen.ts`
- `tests/test_ranking_profile_identity.py`
- `tests/test_ranking_sql.py`
- `tests/test_archetype_rankings_v3.py`
- `tests/test_archetype_system_v3.py` (new)
- `tests/test_ranking_identity_and_no_legacy.py`

Focused checks: Ruff; profile hash/drift guard; all eight trusted-column and
injection cases; ranked/count query tests; disposable-PG18 rankings and
explanation endpoint tests including the exact mismatch rule; no-legacy tests;
OpenAPI generation/drift; `pnpm check`, `pnpm test`, and `pnpm build`; backend,
integration, Svelte, Cypress, Review Lab, and image-parity CI.

### PR4 — registration and production authority amendment

Files:

- `sql/v3/migration-manifest.txt`
- `deploy/v3-production/target-authority.json`
- `docs/operations/v3-production-application-release.md`
- `scripts/operator/actions/v3-derived-lifecycle-status.sh`
- `tests/test_v3_lineage_migrations.py`
- `tests/test_v3_production_migration_operation.py`
- `tests/test_v3_system_search_production_operator.py`
- `tests/test_v3_watchlist_postgres.py`
- `tests/test_v3_production_application_deployment.py`

Focused checks: recompute exact `011`/`015` file hashes and ordered migration-set
identity; schema-identity reproduction; plan exact-prefix and every reachable
accepted-release prefix; target-authority schema; lifecycle-status pending-set
contract; migration/script, canonical-safety, application-deployment, and
security CI.

There is a sequencing conflict to resolve before implementation: current main
already registers the old `011` hash, and CI checks every manifest hash against
file bytes. PR1 cannot rewrite `011` and remain independently green while PR4
defers the hash amendment. (`sql/v3/migration-manifest.txt:52-55`,
`tests/test_v3_lineage_migrations.py:34-60`) The recommendation is to move the
mechanical `011` manifest hash refresh into PR1, while PR4 adds `015` and recuts
the full production authority; the owner yes/no decision is recorded below.

### PR5 — governed operator actions and revised release gate

Files:

- `scripts/operator/actions/v3-system-search-f1.sh`
- `scripts/operator/actions/v3-system-archetype.sh` (new)
- `scripts/operator/actions/v3-publish-derived-products.sh` (new)
- `.github/workflows/chatgpt-ed-new-ops.yml`
- `docs/operations/v3-finder-production-rollout-state.md`
- `docs/operations/v3-production-application-release.md`
- `deploy/v3-production/target-authority.json`
- `tests/test_v3_system_search_production_operator.py`
- `tests/test_v3_system_archetype_production_operator.py` (new)
- `tests/test_v3_product_publication_operator.py` (new)
- `tests/test_v3_production_application_deployment.py`

Focused checks: shell/action contract tests; exact generation UUID/key/sequence,
current-pointer, migration-hash, worker-name, resource-bound, receipt, and
start/status tests; repeat/concurrent publication failures; allowlist/workflow
schema; revised release-preflight tests; operator, canonical-safety, migration,
application-deployment, and security CI. The existing action is demonstrably
pinned to `opt1`, while the current workflow lacks Archetype and product-publish
operations. (`scripts/operator/actions/v3-system-search-f1.sh:15-24,76-113,175-176`,
`.github/workflows/chatgpt-ed-new-ops.yml:10-24,81-84`)

## 11. Risks and open questions

Each unresolved choice is phrased for an explicit yes/no disposition.

1. **Yes/no: approve the measured ≈ 65 GB Archetype layout (section 3.3: primary
   key, weighted index, eight deduplicating `(generation, <key>_score DESC)`
   indexes), re-measured with the final `011` text before the production
   build?** The alternative with `system_id64` trailing in each score index
   measures ≈ 132 GB for no query benefit.
2. **Yes/no: approve `real` confidence storage with six-decimal semantic/API
   equality rather than bitwise equality to the former double-precision
   column?** This follows the requested schema, but the representation rule
   must be explicit.
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
6. **Yes/no: require production publication of both Finder products in one
   transaction?** The API fails closed unless both are published, but one
   transaction gives a cleaner audit boundary.
7. **Yes/no: move the rewritten `011` manifest-hash refresh into PR1 so every PR
   can satisfy exact-head CI, leaving PR4 to register `015` and recut the full
   authority?** Keeping all registration work in PR4 makes PR1 fail the current
   manifest-integrity test. (`tests/test_v3_lineage_migrations.py:34-60`)
8. **Yes/no: accept no purge before Finder promotion?** This is the recorded
   owner decision; changing it would require a separate destructive-data design
   and authority. (`docs/operations/v3-finder-production-rollout-state.md` (PR #805))

## 12. Design acceptance

Implementation is acceptable only when:

- every system produces one wide row whose model outputs match the pre-rewrite
  outputs under the six-decimal confidence rule;
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
