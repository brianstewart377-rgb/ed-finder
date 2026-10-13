# V3 Finder F2d — wide archetype product and product attachment/publication

**Status:** Design only; not implemented. PR #805 (step 0 receipt, capacity
decision, ROADMAP amendment) merged at `c774fb0`; this document cites files it
added.

**Date:** 2026-10-10 (rewritten 2026-10-12 after 52 review rounds; the rounds
are recorded in `2026-10-10-v3-finder-f2d-review-history.md`)

**Base:** `origin/main` at `b0b2f28161ce` (after PR #807)

**Owner decision:** A + B: rewrite unapplied migration `011` to one wide
archetype row per system with explanations computed on demand; attach the two
Finder products to the already-published `ratings_v4_prod_p4_parallel_v1`
generation behind a new explicit product-publication gate in migration `015`;
defer purge; accept a new ranking identity.
(`docs/operations/v3-finder-production-rollout-state.md`,
`docs/operations/v3-finder-capacity-decision-2026-10-10.md`, both PR #805)

**How to read this document.** Each rule is stated once, as what is built, what
each check refuses, and which test proves it. Where a rule exists because a
review found a specific failure, the failure is named in one sentence; the
reasoning behind each round is in the review history, not here.

## 1. Context and terms

Production had 292 GB free on 2026-10-10. The published Ratings V4 generation
occupies about 313 GB; the current eight-rows-per-system archetype layout was
measured at about 978 GB for 1.588 billion rows, including about 410 bytes of
explanation JSON per row. A fresh ratings generation plus Search, Archetype and
the old summary would need about 1,413 GB and cannot fit.
(`docs/operations/v3-finder-production-rollout-state.md`,
`docs/operations/v3-finder-capacity-decision-2026-10-10.md`)

Migration `011` is registered but has never been applied to production, so its
bytes may be replaced before application, as was done for `010`. Registration
is not evidence of application. (`docs/ROADMAP.md:121-127,140-151`)

Terms:

- A **derived generation** is the immutable Ratings V4 generation and its
  lifecycle record.
- A **derived product** is a separately registered, built, validated projection
  attached to that generation: `system_search` or `system_archetype`.
- **READY** means a product passed validation. **Published** means a separate,
  explicit product-publication action made that READY product visible to the
  application views. Today products have only BUILDING/READY/FAILED and a
  published generation may expose READY products immediately; migration `015`
  separates those states.
  (`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:6-30`,
  `apps/api/src/local_search.py:602-643`)
- **Wide row** means one `v3_derived.system_archetype` row holding all eight
  archetype score/tier/confidence triples and the summary fields.
- **Physical table vs. view.** `v3_derived.system_search` and
  `v3_derived.system_archetype` are the tables; `v3_app.system_search`,
  `v3_app.system_archetype` and `v3_app.system_archetype_summary` are views over
  them (`sql/v3/migrations/004_v3_search_spatial_clusters.sql:22,174`,
  `011_v3_system_archetype.sql:7,133-137`). Queries name the views; `VACUUM`,
  `ANALYZE`, size measurements and `pg_stat_user_tables` reads name the tables.

## 2. Goal and non-goals

### Goal

Store exactly one archetype row per Ratings V4 system while preserving the
current model outputs: all eight scores, tiers and six-decimal confidences,
primary and secondary archetype, Best Colony Potential, best tier, archetype
confidence and weighted potential. Only the storage layout and explanation
delivery change. (`scripts/v3_system_archetype_model.py:23-42,85-205`)

**Confidence is stored as an exact integer in parts per million**
(`<key>_confidence_ppm integer CHECK (BETWEEN 0 AND 1000000)`, likewise
`archetype_confidence_ppm`). One shared helper computes
`floor(confidence × 1_000_000 + 0.5)` from the model's **already six-decimal
rounded** confidence (`_fit_anchored`/`_fit_flexible` return `round(conf, 6)`,
`summarise` returns `round(archetype_confidence, 6)`;
`scripts/v3_system_archetype_model.py:131,145,192-205`). On such an input the
half-up rule never meets a tie, so the stored value equals today's model output
exactly: checked exhaustively for every `k` in `0..1_000_000`. Applied to the
raw product instead it would change output (`0.9999 × 0.9950 = 0.9949005`
rounds to `994900` today; half-up on the raw value gives `994901`), so a test
pins that example and the exhaustive conversion. The validator calls the same
helper and compares integers with no tolerance; the ranking SQL reads
`(a.<key>_confidence_ppm / 1000000.0)`; the API serializes `ppm / 1e6`. `real`
was rejected because float32 error could reorder near-ties; `double precision`
measured +14 GB; integer ppm costs the same 4 bytes as `real` (measured 186
B/row heap either way).

### Non-goals

- Do not rebuild Ratings V4; both products attach to
  `ratings_v4_prod_p4_parallel_v1`.
- Do not change any canonical relation or scoring input; archetypes stay a
  derived layer over `system_rating_vector` and `economy_opportunity`.
  (`docs/development/v3-search-spatial-derived-data-decision.md:11-24,83-132`)
- Do not change fit coefficients, tier boundaries, key order, score semantics
  or ranking response fields. A storage-shape version bump and a new ranking
  identity are still required because reproducibility hashes describe the live
  implementation.
- Do not add a purge path or delete retained `p4`/`opt1` data; the owner
  deferred purge. (`006_v3_derived_product_lifecycle.sql:165-206`)
- Do not make explanations searchable, sortable or persisted.

## 3. Rewritten migration `011`: one wide row per system

### 3.1 Relation

Replace the keyed table and the summary table with one table:

```sql
CREATE TABLE v3_derived.system_archetype (
    derived_generation_id uuid NOT NULL
        REFERENCES v3_meta.derived_generation,
    system_id64 bigint NOT NULL CHECK (system_id64 >= 0),
    archetype_version text NOT NULL
        CHECK (length(archetype_version) BETWEEN 1 AND 128),

    -- one group per key, in ARCHETYPE_KEYS order: paradise, mining_hub,
    -- manufacturing_hub, megacomplex, research_hub, stronghold,
    -- population_capital, flexible
    <key>_score smallint NOT NULL CHECK (<key>_score BETWEEN 0 AND 100),
    <key>_tier char(1) NOT NULL CHECK (<key>_tier IN ('S','A','B','C','D')),
    <key>_confidence_ppm integer NOT NULL CHECK (<key>_confidence_ppm BETWEEN 0 AND 1000000),
    -- the stored picked-ranking key (section 3.1, "weighted key")
    <key>_weighted_e4 integer NOT NULL CHECK (<key>_weighted_e4 BETWEEN 0 AND 1000000),

    primary_archetype text NOT NULL,
    secondary_archetype text,
    best_colony_potential smallint NOT NULL
        CHECK (best_colony_potential BETWEEN 0 AND 100),
    best_tier char(1) NOT NULL CHECK (best_tier IN ('S','A','B','C','D')),
    archetype_confidence_ppm integer NOT NULL
        CHECK (archetype_confidence_ppm BETWEEN 0 AND 1000000),
    weighted_potential double precision NOT NULL
        CHECK (weighted_potential BETWEEN 0 AND 100),
    -- exact integer completeness input to every <key>_weighted_e4
    completeness_ppm integer NOT NULL
        CHECK (completeness_ppm BETWEEN 0 AND 1000000),
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

The `<key>_…` lines are written out for all eight keys in the migration; the
column order is `ARCHETYPE_KEYS` order, which is also the tie-break for equal
scores (`scripts/v3_system_archetype_model.py:22-33,192-205`).
`weighted_potential` stays `double precision` with its unrounded
`best_colony_potential × (system_search confidence × completeness)` semantics,
because reducing it to a small integer would collapse the default ordering into
large ties.

**The weighted key.** The ranking profile orders a picked archetype by
`score × fit confidence × completeness` (`apps/api/src/ranking/ranking_sql.py:451-477`).
Any design that takes a window by raw score and sorts it by the product
afterwards is an approximation (a score-99 system with full certainty can be
dropped behind 10,001 score-100 systems with near-zero certainty), so the
builder stores the canonical key for every archetype. Its definition is closed
in integers, because `round()` is ties-to-even in Python and half-away-from-zero
in PostgreSQL `numeric`, and a half-integer disagreement between the builder
and the validator would order tied systems differently under matching version
strings:

```
completeness_ppm   = min(system_rating_vector.completeness) × 100   -- smallint[] in 1e-4 units
numerator          = <key>_score × <key>_confidence_ppm × completeness_ppm
<key>_weighted_e4  = (numerator + 50_000_000) // 100_000_000
```

In SQL the first operand is cast to `bigint` before multiplying —
`((<key>_score::bigint * <key>_confidence_ppm * completeness_ppm) + 50000000) / 100000000`
— because `smallint × integer × integer` evaluates as `integer` and overflows at
ordinary values (`100 × 1e6 × 1e6 = 1e14`); integer division truncates towards
zero, which equals the floor because every operand is non-negative. The
numerator is at most `1e14` (exact in `bigint`) and the key is `0..1_000_000`.
The completeness source is `system_rating_vector.completeness smallint[]`
(`003_ratings_v4_derived.sql:120`): `min()` of the raw array before any
division, times 100 — not `system_search.completeness` (`double precision`,
`004_v3_search_spatial_clusters.sql:41`) and not `evidence_completeness`, which
exists only as a `double precision` alias in the unnested view
(`003_ratings_v4_derived.sql:223`). `completeness_ppm` is persisted so the
builder, the validator and the explanation route read one stored integer.
Ordering by the key equals ordering by the double product except for ties
within 0.0001, which `system_id64` breaks — that rounding is part of the new
ranking identity; a PR1 test compares the integer rule with the floating-point
product over 500,000 random triples and asserts zero disagreements at non-tie
inputs. Worked tie: `score = 1`, `confidence_ppm = 50`,
`completeness_ppm = 1_000_000` gives numerator `50_000_000`; the rule yields 1,
Python `round(0.5)` yields 0, PostgreSQL `round(0.5::numeric)` yields 1.

Tests: the builder, the exact validator and the ranking-identity tests carry
half-boundary vectors (a numerator landing on `50_000_000`, two keys on the
same `_weighted_e4` so `system_id64` breaks the tie, the 0 and maximum ends)
and assert the same integer from all three. `RANKING_VERSION` covers this rule.

Measured heap: 221.7 B/row (≈ 44 GB at 198.5 M rows) before `completeness_ppm`,
which adds 4 B/row (≈ 0.8 GB). The capacity gate reads per-row costs from a
receipt measured against the final migration text (section 8), never from these
figures.

### 3.2 Summary projection

No physical `system_archetype_summary` table: its six values live on the wide
row, and a second 198.5 M-row table would duplicate the current 35 GB summary
relation and create a consistency problem. Keep the application name as a view:

```sql
CREATE VIEW v3_app.system_archetype_summary AS
SELECT derived_generation_id, system_id64,
       primary_archetype, secondary_archetype,
       best_colony_potential, best_tier,
       (archetype_confidence_ppm / 1000000.0)::double precision AS archetype_confidence,
       weighted_potential, computed_at
FROM v3_app.system_archetype;
```

`v3_app.system_archetype` exposes every wide column as stored **and** the
derived `<key>_confidence` doubles, so the ranking column map (section 6) may
reference either form; the migration test creates both views and selects every
projected column. The no-pick path and the summary fields need no code change.
(`apps/api/src/ranking/ranking_sql.py:246-263,294-301,512-546`)

### 3.3 Indexes

Besides the primary key: the `weighted_potential` index and, per archetype,
three partial indexes over the stored key, one per exposed tier floor:

```text
(derived_generation_id, weighted_potential DESC NULLS LAST, system_id64)

for every <key> in ARCHETYPE_KEYS:
  (derived_generation_id, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 60   -- tier B floor
  (derived_generation_id, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 76   -- tier A floor
  (derived_generation_id, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= 88   -- tier S floor
```

26 physical indexes in all. Why this shape:

- **Canonical order from the index.** A picked ranking scans the matching
  partial in `<key>_weighted_e4 DESC, system_id64` order and stops after the
  page (or after 10,001 rows for the bounded count); the first 10,000 index
  rows *are* the top 10,000.
- **Partial per floor.** The product exposes exactly B/A/S ⇒ 60/76/88 and
  nothing may call below B. A single `>= 60` index would make an S-floor query
  filter through the whole B population (33,695 entries read to return 4,095
  rows ≥ 76 at 200k rows, measured during the 2026-10-10 footprint work; the
  committed evidence records sizes, not this read count). The A and S partials are tiny (1.1 and
  0.2 B/row).
- **`system_id64` trailing** breaks key ties inside the index without a sort.
- **The no-pick index matches the `ORDER BY` literally**, null ordering
  included: `weighted_potential DESC NULLS LAST, system_id64 ASC`
  (`ranking_sql.py:461-477`). `weighted_potential` is built from an integer
  potential and discrete confidence and completeness, so large tie groups are
  reachable; without the trailing column PostgreSQL would read and sort a whole
  leading tie group before returning the smallest ids. The committed evidence
  measured the weighted index without the trailing column; the extra 8-byte
  column adds roughly 8 B/row (≈ 1.6 GB), and PR1's re-measurement with the
  final `011` is the figure the gate uses.
- **The floor is a literal in the SQL**, never a parameter (section 6):
  partial-index applicability is decided at planning time and a parameter
  cannot prove `$n >= 60`. Observed under `plan_cache_mode = force_generic_plan`
  on the disposable database during the 2026-10-10 footprint work: parameter-only
  ⇒ parallel sequential scan; literal ⇒ the matching partial. That observation
  is not in the committed evidence; PR1's plan tests (section 6) are the
  committed proof.

Measured on disposable PostgreSQL 18.4 at 200,000 rows with a bell-shaped
synthetic distribution (per-key means 16.8 % ≥ 60, 2.0 % ≥ 76, 0.19 % ≥ 88;
`v4_weighted_key_tier_partials` in the committed evidence): ≥ 60 partial 8.5
B/row, ≥ 76 1.1, ≥ 88 0.2 per key ≈ 79 B/row for all 24; primary key 40.7;
weighted index 40.8; indexes ≈ 160 B/row ≈ 32 GB. Each partial's size is 49.8 B
× (fraction of systems at or above its floor), and the three predicates are
**nested**, so the cost is driven by the sum of all 24 fractions:

```text
partial-index GB  ≈  49.8 B × 198.5 M × Σ(f60 + f76 + f88 over the 8 keys) / 1e9  ≈  9.9 GB × Σ_all
archetype total   ≈  44 GB heap + 16 GB (primary key + weighted index) + 9.9 GB × Σ_all
```

The synthetic `Σ_all`, summed over the 24 recorded fractions, is 1.52 (1.54
from the rounded percentages the capacity decision quotes) ⇒ 15.1 GB of partials
by the formula (measured 15.6) ⇒ ≈ 76 GB (the evidence total is 75.7 GB). The ceiling if every fraction were 1 is 24 × 9.9 =
237 GB of partials ⇒ ≈ 297 GB. **The capacity gate is therefore on `Σ_all`,
computed from the complete-read tier counts (section 8), and refuses `Σ_all >
4.0`** (≈ 40 GB of partials, archetype ≈ 100 GB). Above that the design is
revisited: fewer floors (only ≥ 60, with a residual filter for A and S) or fewer
archetypes. The score-ordered partial layout (`v3_partial_ge60_score_sysid`, ≈
67 GB; cannot serve canonical order) and the deduplicated layout (≈ 65 GB;
cannot bound the probe) stay in the evidence as rejected.

### 3.4 Measured footprint

Method: real builder rows replicated to ≈ 200,000 with the same DDL and indexes
on PostgreSQL 18.4, `VACUUM ANALYZE`, `pg_table_size` + `pg_indexes_size`,
linear extrapolation to 198.5 M systems; foreign keys to other relations
omitted. (`docs/operations/v3-finder-production-rollout-state.md`, "Disposable-sample
footprint measurement")

| Object (198.5 M rows) | Measured B/row | Estimated size |
|---|---:|---:|
| table heap without the stored weighted keys (average tuple 180 B) | 186.4 | 37.0 GB |
| primary key `(derived_generation_id, system_id64)` | 40.7 | 8.1 GB |
| `weighted_potential` index | 40.8 | 8.1 GB |
| eight stored `<key>_weighted_e4` columns (heap 186.4 → 221.7 B/row) | +35.3 | +7.0 GB (heap 44.0 GB) |
| 24 tier partials (synthetic distribution) | ≈ 79 | 15.6 GB |
| **total as measured** (`v4_weighted_key_tier_partials`, synthetic distribution) | **382** | **≈ 76 GB** |
| section 3.3 layout as designed: + trailing `system_id64` on the weighted index (≈ 8) + `completeness_ppm` (4), pending PR1's re-measurement | ≈ 394 | ≈ 78 GB |
| *(rejected)* score-ordered `>= 60` partials without the stored key | 336 | ≈ 67 GB |
| *(rejected)* deduplicated `(derived_generation_id, <key>_score DESC)` | 328 | ≈ 65 GB |
| *(reference)* full unique-entry score indexes | 667 | ≈ 132 GB |

Integer-ppm confidences measured the same 186.4 B/row heap as `real`, and
`double precision` 256 B/row because of 8-byte alignment (both measured during
the same work; the committed script builds the `real` variant only). These are
sample figures: the production gate measures the final `011` text and stops unless the
measured Search projection (section 8, never the ≈ 87 GB fixture figure) plus
Archetype plus working room fits the free space reported by a fresh step 0
receipt (292 GB on 2026-10-10).

### 3.5 Receipts and mutation guards

Keep `v3_derived.archetype_build_chunk` with its primary key, source and content
seals, system count, product FK and Ratings-chunk FK; it is the resumability
and coverage boundary (`011_v3_system_archetype.sql:58-75`,
`scripts/v3_system_archetype.py:215-246,770-833`). Keep all three mutation
properties:

1. product rows and chunk receipts may be inserted only while that product is
   BUILDING;
2. UPDATE, DELETE and TRUNCATE of product rows and receipts are rejected;
3. the generation must be in an allowed attachment state — rewritten `011`
   retains BUILDING/VALIDATING/READY and `015` adds PUBLISHED.

The rewrite drops only the summary-table trigger target and renames no
externally used guard. (`011_v3_system_archetype.sql:77-130`)

## 4. Explanation on demand

### 4.1 Endpoint and shared model

Add `GET /api/archetypes/system/{id64}/explanation`. The path parameter is
`Path(ge=0, le=9223372036854775807)`, as the active Ratings V4 routes declare
it, so a negative or over-`bigint` value is a 422 rather than an asyncpg
encoding failure. Three optional identity query parameters let a client pin the
product a card's score came from: `expected_generation_id: uuid.UUID`,
`expected_archetype_version: Query(None, min_length=1, max_length=128)` and
`expected_manifest_sha256: Query(None, pattern=r'^[0-9a-f]{64}$')`. A malformed
value is a 422 from validation, never a 409 and never a database parameter.
When any is supplied and differs from the current published product the route
answers 409 with the section 4.3 detail string, and a 200 always echoes the
identity it computed against. Tests: both path bounds; an over-128 and an empty
version; 63- and 65-character, upper-case and non-hex hashes.

Leave the legacy `GET /api/archetypes/system/{id64}` unchanged until its
topology/pair/trait contract has a complete V3 replacement; it still reads
legacy relations (`apps/api/src/routers/archetypes.py:631-759`).

Move the DB-free model to `shared_contracts/v3_system_archetype_model.py` and
keep `scripts/v3_system_archetype_model.py` as a re-export, so the builder, the
calibration probe, the ranking profile and the API import one implementation.
The API image copies `shared_contracts/` but not `scripts/`
(`apps/api/Dockerfile:12-24`, `apps/api/src/ranking/profile.py:35-40`).

### 4.2 Read and compute path

One parameterized round trip, inside one read-only `REPEATABLE READ`
transaction together with the identity check (section 4.3), reads for the
current generation and the requested `id64`:

- the one `system_rating_vector` row and the integer opportunity groups,
  through the **same two shared query constants** the builder uses (section
  5.1), narrowed to one system by their parameters, not by rewriting them;
- the one generation-pinned `v3_app.system_archetype` wide row: the eight
  score/tier/confidence-ppm triples, `completeness_ppm`, the eight
  `<key>_weighted_e4` keys and the summary columns.

If the wide row is absent the route is a 404. Otherwise it calls
`score_raw_system`, builds the explanations from the same inputs, and compares
**every** recomputed value — scores, tiers, confidence ppm, `completeness_ppm`,
all eight keys and the summary values — with the stored row, failing closed on
any mismatch: explanation delivery never describes a different stored score or
ranking key. Cost is two index probes and eight in-process fits; nothing scans
the product or the galaxy, and explanations are returned, not stored.
(`003_ratings_v4_derived.sql:109-126,165-185`, `scripts/v3_system_archetype.py:249-281`)

Tests seed a divergent stored `completeness_ppm` and, separately, one divergent
`<key>_weighted_e4`, and assert the fail-closed response.

### 4.3 Exact version rule

Serve an explanation only when

```text
v3_meta.derived_product.product_version
    == v3_derived.system_archetype.archetype_version
    == deployed shared model ARCHETYPE_VERSION
and
sha256(deployed shared_contracts/v3_system_archetype_model.py)
    == product manifest `model_file_sha256`
```

and the product is READY and product-published on the current PUBLISHED
generation. The hash matters because explanations are no longer persisted: a
change to explanation construction without a version bump would leave all
three version strings equal. The API hashes its deployed model file once at
start-up. On any mismatch, before reading inputs or calling the model, return
HTTP 409 with the exact detail:

```text
explanation unavailable for this product version
```

The identity lookup, the expected-value comparison and the data read run in the
same `REPEATABLE READ` transaction, as the rankings path does, so a publication
committing mid-request is invisible: the request serves entirely from one
snapshot or answers 409, never an explanation computed under the new generation
and stamped with the old identity.

Tests: with the model patched, a READY published product whose version differs
⇒ 409 with the exact string and the model not called; versions equal but
`model_file_sha256` differing ⇒ the same; matching ⇒ all eight explanations
with values identical to the stored row; and a publication committed from a
second connection between the identity statement and the data statement ⇒ a
response consistent with exactly one snapshot.

## 5. Builder, manifest and validator

### 5.1 Version and manifest

`ARCHETYPE_VERSION = 'v3-archetype-4'`: coefficients are unchanged, the
persisted shape is not, and version 3 was itself a shape-driven bump
(`scripts/v3_system_archetype_model.py:10-20`).

`product_manifest()` keeps hashing coefficients, anchors, key order, generation
identity, source policy and code identity (`scripts/v3_system_archetype.py:104-168`),
and gains: a canonical ordered `wide_columns` list carrying the weighted-key
integer expression verbatim (never a `round(...)` form), `storage_layout:
"one-row-per-system-v1"`, `explanation_delivery: "on-demand"`, the confidence
storage/rounding policy, and `model_file_sha256`, the SHA-256 of the canonical
`shared_contracts/v3_system_archetype_model.py` (section 4.3 compares it with
the deployed file).
`code_identity()` hashes the canonical model file **and** the re-export,
alongside the builder and `011`; a test edits only the canonical file and
asserts `code_sha256` changes. The manifest records the CPython version beside
the digests.

**Two digests with two jobs.** `archetype_manifest_sha256` identifies one exact
build and changes on every rebuild, because it embeds the generation identity,
publication sequence and `expected_rows`. `archetype_model_sha256` answers
"were these two scores produced by the same model?" for the F4 cross-generation
comparison, so it must stay equal across equivalent builds and change on every
scoring change. It covers a canonical semantic manifest — the coefficients,
anchors, key order, tier thresholds, the `_weighted_e4` expression, the
confidence rounding rule, the `completeness_ppm` derivation rule — **and the
scoring code itself**, hashed as follows. It excludes `ARCHETYPE_VERSION`,
explanation construction, every storage-shape constant and every whole-file
hash: a storage-only version bump or an explanation-only edit must not move it.
Both digests are persisted on the product row and returned in the shared
ranking identity of both response envelopes (section 6).

**What the model digest hashes.** PR1 gives the model module one scoring entry
point, `score_raw_system(vector_row, opportunity_groups)`, taking the rating
vector row exactly as selected (all six arrays unscaled, as a named row) and the
system's opportunity groups as integer triples `(economy_ordinal, row_count,
local_score_sum)`, and returning every model value the wide row persists. The
scaling, the opportunity mean (`local_score_sum / row_count`, divided once),
`completeness_ppm`, the confidence helper, `fit_all`, `_fit_anchored`,
`_fit_flexible`, `_quality`, `_clamp`, `tier_of`, `summarise`,
`weighted_potential` and the weighted-key expression are all reachable from it;
the builder, the validator and the explanation route call it and nothing below
it, and `_read_chunk_vectors` becomes a pure fetch. PR1 also moves explanation
construction out of `_fit_*` into separate `_explain_*` functions. The digest
then covers:

- `score_raw_system` and **every function reachable from it** by walking the
  call graph (not a hand-maintained list), excluding only the `_explain_*`
  functions;
- every module-level assignment a covered function reads (recursively through
  the values' own expressions) and every class the graph references, such as
  `SystemVectors`;
- the two shared SQL constants below, whitespace-collapsed.

Each function is hashed as `ast.dump(tree, include_attributes=False)` with its
docstring removed, so comments, formatting and line positions do not move the
digest while any tree change does. **The walk fails closed:** if a covered
function or hashed value refers to any name that is not a definition in the
model module, a builtin, or on the explicit standard-library allowlist — the
members of `math`, and `dataclasses.dataclass` and `dataclasses.field`, which
the canonical model's `@dataclass(frozen=True)` classes and
`field(default_factory=dict)` need
(`scripts/v3_system_archetype_model.py:8,45-57`) — the digest cannot be
computed and the build cannot register. Allowlisted names are resolved through
the module's own import statement, so a rebinding or a same-named import from
elsewhere is refused. Annotations are hashed but not name-checked (the module
uses `from __future__ import annotations`).

**The two shared reads are complete query contracts.** Which rows enter a group
is as score-affecting as how the group is aggregated, so each read is one
module-level SQL constant in the model module — select list, joins, `WHERE`,
`GROUP BY`, ordering — with only the generation and the chunk or system as
parameters, used verbatim by the builder, the validator and the explanation
route. The opportunity read returns `count(*)::int` and
`sum(local_score)::bigint` per `(system_id64, economy_ordinal)`, no `avg` and
no float cast; the vector read returns the six arrays unscaled in the order
`score_raw_system` unpacks them. Moving the mean out of SQL can change its last
bit against today's `avg(smallint)`; that is acceptable because `v3-archetype-4`
rebuilds every row and no `v3-archetype-3` value is ever compared with a
`v3-archetype-4` one.

The validator turns the digest from a declaration into a checked claim: it
asserts the digest is stable across two builds of the same model on different
generations (not that those builds produce equal keys — a later generation may
legitimately give a system different vectors), and asserts key equality against
a committed **database-shaped frozen fixture**: raw `system_rating_vector` and
`economy_opportunity` rows inserted into disposable PostgreSQL 18, read through
the builder's real chunk read, passed to `score_raw_system`, and compared on
`completeness_ppm`, every score/tier/confidence ppm and every weighted key —
including the half and endpoint vectors and an opportunity group whose mean is
not exactly representable (local scores `1, 1, 2`). A unit test drives
`score_raw_system` from the same rows' integer groups and must agree.

Digest tests: **unchanged** by an edit confined to an `_explain_*` function and
by a comment-, docstring- or formatting-only edit to a covered function;
**changed** by an edit to each covered member named above and to each clause of
each query constant; changing only a referenced global's value or a referenced
class moves it; the unchanged canonical model produces a digest; and a scoring
function that calls an imported repository helper, or a `dataclass` imported
from a module other than `dataclasses`, makes the computation fail.

### 5.2 Build

Keep the CLI (`--generation-key`, `--follow`, `--poll-seconds`, `--max-chunks`,
`--validate`, environment DSN, fail-closed exit codes;
`scripts/v3_system_archetype.py:1109-1154`). Per Ratings chunk: read the raw
vectors and integer groups through the shared constants; call
`score_raw_system` once per system; pivot the eight fits into one wide tuple;
insert one wide row per system and one `archetype_build_chunk` receipt in the
same transaction. The chunk `content_sha256` covers every persisted column in
`system_id64` order, including `archetype_version` and one explicitly assigned
`computed_at` per chunk, so the inserted and sealed values are identical.
(`scripts/v3_system_archetype.py:249-281,284-309,491-550,770-833`)

### 5.3 Validation

`validate_product` gates BUILDING → READY on all of:

- base generation READY or PUBLISHED;
- the same generation's `system_search` **READY with a VERIFIED receipt** — the
  keys no longer depend on Search, but `weighted_potential` reads Search
  confidence and the envelope joins Search — and `register_product` applies the
  same check so a build cannot start against an unverified dependency (test: a
  complete-but-unverified Search fails both);
- every Ratings chunk has exactly one archetype receipt;
- `count(system_archetype) == count(system_rating_vector)` and every system has
  exactly one `v3-archetype-4` row;
- every score is 0–100 and every tier equals `tier_of(score)`;
- every `<key>_weighted_e4` equals the integer expression on the **stored**
  `completeness_ppm`, and that stored value equals
  `min(system_rating_vector.completeness) × 100` re-derived on the same
  generation (missing row or disagreement fails);
- every `_confidence_ppm` equals the **shared half-up helper** applied to a
  fresh model confidence, exactly — the validator calls the helper rather than
  reimplementing it, because a `round()` reimplementation would reject a
  correctly built half-boundary row and the immutable product could never reach
  READY (test: a half-boundary vector);
- primary, secondary, best potential, best tier, archetype confidence and
  full-precision weighted potential equal a fresh recomputation;
- source and complete-row content seals match; no `public.*` relation is read.

Existing coverage tests (eight rows plus a summary) become per-column wide-row
tests (`scripts/v3_system_archetype.py:588-1010`,
`tests/test_v3_system_archetype_validate.py:91-473`). Registration, insertion
and validation in both `scripts/v3_system_archetype.py` and
`scripts/v3_system_search.py` must accept a PUBLISHED base after `015`; both
reject it in code today, so migration-only work is insufficient
(`scripts/v3_system_archetype.py:181-212,836-894`,
`scripts/v3_system_search.py:162-193,413-414,549-588`).

## 6. Ranking SQL and F3 behaviour

`RANKING_VERSION = 'v3-colony-potential-2'`, with the newly computed
`ranking_sha256` pinned by the drift-guard test
(`apps/api/src/ranking/profile.py:33-54,132-183`,
`tests/test_ranking_profile_identity.py:37-61`).

**Everything that decides a ranking is declared in `PROFILE_SPEC` and hashed.**
The key → column map (`archetype_columns: {key: {score, tier, confidence,
weighted_key}}`, with the confidence expression written out), the floor default
and the accepted floor set, the stored-key integer expression verbatim, the
10,000 window and its combined offset/limit bound, the `is_truncated` and
`total = min(qualifying, 10000)` rules, the hard-filter rejection set, and
`tie_break = ["system_id64"]` all enter `_canonical_base()`. `ranking_sql.py`
derives `ARCHETYPE_COLUMNS` from the spec, and the route's `Query(...)`
declarations are built from its constants. The identity test mutates each in
turn and asserts the digest changes. The router rejects a key outside
`ARCHETYPE_KEYS` with 422 before any SQL is built; no user string is ever
formatted as an identifier (`apps/api/src/routers/archetypes.py:294-316`).

**Picked archetype: four stages, the relation touched twice.**

1. **Window (index-only).** Over `v3_app.system_archetype` alone, selecting
   `system_id64` and `<key>_weighted_e4` for the generation, with the floor as a
   **server-chosen literal** (`<key>_score >= 60`, `>= 76` or `>= 88`, picked
   from a fixed three-entry map by the validated `min_score`) and `ORDER BY
   <key>_weighted_e4 DESC, system_id64 ASC`. The page query uses `LIMIT 10000`,
   the count query `LIMIT 10001` (the sentinel). The literal is the only floor
   predicate: a parameterized `<key>_score >= $n` beside it would force a heap
   fetch per candidate and lose the index-only scan.
2. **Join (no filtering).** `v3_app.system_search` for the response columns
   only.
3. **Page.** Restate `ORDER BY <key>_weighted_e4 DESC, system_id64 ASC` on the
   ≤ 10,000 survivors, then `OFFSET`/`LIMIT`; an ordered subquery says nothing
   about the final order.
4. **Fetch.** Join `v3_app.system_archetype` again by primary key for the ≤
   `page_size` paged rows (the route bounds `page_size` at 500,
   `routers/archetypes.py:517`) to read the selected score, tier, confidence and
   summary columns, and **repeat the `ORDER BY`** on the outermost `SELECT`,
   because a join may emit the page in any order.

The count query uses stages 1–2 only. INCLUDE payload on the partials was
rejected (payload on every indexed row to save ≤ 500 key lookups). The no-pick
path keeps the `v3_app.system_archetype_summary` join and
`weighted_potential DESC NULLS LAST, system_id64` order, and the anchored
nearest-first path is rewritten as in section 8 (plan probe).

**Contract changes in PR1**, all hashed:

- `min_score: Literal[60, 76, 88] = Query(60)` (today `Query(40, ge=0, le=100)`,
  `routers/archetypes.py:511`): any other value is a 422 rather than a
  truncated or unbounded result; the partials cover only ≥ 60, and indexing all
  scores would cost ≈ 95 GB for rows no planned caller asks for.
- `offset: Query(0, ge=0, le=9999)`, `limit` keeps `ge=1, le=500`, and a
  route-level `offset + limit <= 10000` (422 otherwise).
- The picked count is `SELECT count(*) FROM (SELECT 1 … LIMIT 10001) t`;
  `total = min(count, 10000)`, `is_truncated = count = 10001`. The galaxy-wide
  local-search count changes the same way — `LIMIT cap + 1`, `total =
  min(count, cap)`, `total_is_capped = count > cap` — for every count, anchored
  included (today the flag is set when `total >= cap`,
  `apps/api/src/local_search.py:922,965-970`, so exactly 10,000 matches is
  indistinguishable from a million). The local-search request model enforces
  `from >= 0`, `size >= 1`, `from + size <= 10_000`.
- **Hard filters are rejected, not redefined.** A picked request carrying
  `galaxy_region`, `max_distance_ly`, `has_elw`, `min_slots` or
  `max_contamination` is a 422 naming the parameters ("archetype ranking is
  unfiltered in the initial product; filter in Any mode or drop the filter"): a
  filter inside the window would make the scan unbounded, and a filter after it
  would silently change what a filter means (an empty page while millions
  match), while the product contract says Finder filters select the results
  (`docs/colonisation-redesign/spatial-platform-product-contract.md:102-110`).
  **Galaxy-wide Any-mode requests carrying any hard filter are also a 422**
  ("pick an anchor area or remove the filter"; owner decision 2026-10-12): the
  cap limits matching rows, not rows examined, and filters such as
  `has_biologicals` or `main_star_class_in` have no supporting Search index.
  Anchored Any requests keep every filter, and are bounded in one of two ways.
  For this classification the request's own radius is not a hard filter:
  `_v3_hard_filters` records `max_distance_ly` for every anchored request
  (`local_search.py:737-743`), but it is the KNN path's intrinsic upper-radius
  predicate; `min_distance_ly` and every other entry are hard filters. An
  **unfiltered nearest-first** request (`sort_by='distance'`, no entry other
  than `max_distance_ly`) is bounded by
  the inner `LIMIT` of section 8.7 at any radius the route accepts
  (`max_distance_ly` defaults to 500 ly and is capped at `MAX_SEARCH_RADIUS`,
  10,000 ly by default; `apps/api/src/local_search.py:55,252-253`). Every
  other anchored request — one carrying a hard filter, or one sorted by score
  (`sort_by='development'`, the request default, which the route maps to score
  order even with an anchor; `local_search.py:665-671,886-910`) — has no index
  that orders by score and distance together, so its only bound is the bounding
  box's candidate count. PR1 therefore caps the radius of those requests at the
  500 ly the publication probe measures and answers 422 above it ("reduce the
  radius, sort by distance, or remove the filter"); the Explore flow sends 500
  ly and sorts anchored requests by distance today, so no live caller changes. The F4 UI
  disables — not hides — the hard filters while an archetype is picked and in
  galaxy-wide Any mode until an anchor is set, showing the same reason text as
  the 422 so the combination is never offered. Filtered archetype ranking is
  deferred work needing a filter-first access path.
- **Tie-break is `system_id64` only, in both modes.** `PROFILE_SPEC`'s
  `tie_break = ["distance", "system_id64"]` becomes `["system_id64"]`: a
  per-request distance tie-break cannot live in any index, so a leading tie
  group larger than 10,001 would have to be read and sorted. Distance stays a
  displayed fact and the primary key of the nearest-first sort.
- **Additive response fields.** `is_truncated: bool` on
  `ArchetypeRankingsResponse` (`apps/api/src/models.py:911-924` has
  `extra='forbid'`), and the product identity `archetype_version`,
  `archetype_manifest_sha256` and `archetype_model_sha256` on the shared ranking
  identity of **both** the rankings and the local-search envelopes.
  `_current_derived_generation()` returns them from the published product row and
  fails closed (503) when the product is missing or not READY, never an envelope
  without identity. PR1 regenerates all three typed clients
  (`apps/web/src/lib/api/generated/*`, `packages/api-client/src/generated/api.gen.ts`).

Nothing in `apps/web` calls `/api/archetypes/rankings` yet, so no live caller
loses a result; the route is live from the moment the release deploys, so the
bounded form ships in that release (section 8).

Tests (disposable PostgreSQL 18, `plan_cache_mode = force_generic_plan`):
`EXPLAIN (FORMAT JSON)` shows the matching partial for each floor, the window
node is an `Index Only Scan` with ≤ 10,001 rows, the sort node's input ≤
10,000, the fetch node's rows ≤ `page_size` at both 50 and 500; the returned
rows' `<key>_weighted_e4` values are non-increasing with ties by ascending
`system_id64` on a fixture seeded with ties, and two adjacent pages concatenate
with no repeat or gap; all eight key → column mappings (score, tier, confidence
and weighted key) and that the SQL map is derived from the spec; 60/76/88
accepted, 59/70/100 → 422; `offset=9999,limit=1` → 200, `offset=9999,limit=2`
and `offset=10000` → 422; `from=9950,size=50` ok, `from=10000,size=1` and
`from=10001` → 422; counts at exactly 10,000 (flag false) and 10,001 (flag
true) for picked, galaxy-wide and anchored; the 422 for each hard filter on a
picked request and on a galaxy-wide Any request, the same filters accepted
when anchored at 500 ly, a filtered anchored request at 501 ly → 422, a
score-sorted anchored request at 501 ly → 422, an unfiltered nearest-first
anchored request at 10,000 ly accepted, and a nearest-first request with
`min_distance_ly` at 501 ly → 422; `system_id64` tie cases in both modes; both envelopes carry all
three identity fields; unknown-key rejection and adversarial strings that never
appear in SQL; and the retained no-legacy-relation assertions
(`tests/test_ranking_sql.py`, `tests/test_archetype_rankings_v3.py`,
`tests/test_local_search_v3.py`, `tests/test_ranking_identity_and_no_legacy.py`).

## 7. Migration `015`: attach and publish products on a PUBLISHED generation

Create `sql/v3/migrations/015_v3_derived_product_publication.sql`, additive to
applied migration `006`, which is in the production lineage and is not
rewritten (`006_v3_derived_product_lifecycle.sql:32-99,136-206,208-286`,
`sql/v3/migration-manifest.txt`).

### 7.1 Allowed attachment lifecycle

PUBLISHED joins the allowed base states — `BUILDING | VALIDATING | READY |
PUBLISHED` — for product registration, BUILDING product rows and chunk
receipts, and for BUILDING → READY/FAILED. Every other rule stays: the product
starts BUILDING without terminal evidence; identity and manifest are immutable;
READY requires a VERIFIED receipt; FAILED requires evidence; product data and
receipts are insert-only; RETIRED/FAILED bases reject attachment and writes.
Products have no VALIDATING state; their lifecycle is `BUILDING | READY |
FAILED` (`006_v3_derived_product_lifecycle.sql:10-11`).

### 7.2 Product publication state and audit

```sql
ALTER TABLE v3_meta.derived_product ADD COLUMN published_at timestamptz;

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

`NULL` means unpublished. Publication is one-way, NULL → one timestamp, for a
READY/VERIFIED product on the current PUBLISHED generation; the timestamp is
never changed or cleared. UPDATE, DELETE and TRUNCATE on the audit are
rejected.

**The invariants live in the table guards**, so paired direct DML (an `UPDATE …
SET published_at` plus a hand-written audit row) meets the same checks as the
function:

- the `BEFORE UPDATE` lifecycle guard on `v3_meta.derived_product` keeps its
  BUILDING → READY/FAILED branch and gains a **publication branch** for `NEW.published_at
  IS DISTINCT FROM OLD.published_at`: no other column may change in the
  statement; the old value must be NULL; the branch takes advisory transaction
  lock `764003001`; the row's generation must be the current pointer **and**
  PUBLISHED; the product must be READY with a VERIFIED receipt; the new value
  must equal `transaction_timestamp()`;
- a deferred constraint trigger requires, at commit, an audit row with the exact
  generation, product, version, manifest hash and timestamp, **and re-verifies
  that the product's base is still the current PUBLISHED generation**;
- the product `INSERT` guard requires `published_at IS NULL` (a product is never
  born published);
- the audit `INSERT` guard requires, at commit, that the product row's
  `published_at` equals the audit timestamp and its version and manifest hash
  match.

`v3_meta.publish_derived_product(generation_id uuid, product_code text, actor
text) -> timestamptz` is the audited convenience path: reject a blank actor;
take lock `764003001` (shared with product mutation and
`publish_derived_generation`); require the generation to be the current pointer
and PUBLISHED; lock the product row and require READY, VERIFIED and
`published_at IS NULL`; set one transaction timestamp; update `published_at`
and insert the audit row; return the timestamp.
(`006_v3_derived_product_lifecycle.sql:38-40,69-92,220-267`)

### 7.3 Application visibility

Recreate `v3_app.system_search`, `v3_app.system_archetype` and
`v3_app.system_archetype_summary` to join the current PUBLISHED generation to
its product row and require `lifecycle_state = 'READY' AND published_at IS NOT
NULL`. `_current_derived_generation()` in `local_search.py` requires both
Finder products READY and published; anything else — missing, BUILDING, FAILED,
READY-but-unpublished — is a 503, never a valid-looking empty search
(`apps/api/src/local_search.py:602-643`, `apps/api/src/routers/archetypes.py:365-373`).

### 7.4 Generation pointer flips

For **this** rollout the pointer already points at `parallel_v1` and does not
move; `published_at` stays NULL until the explicit product launch (step 9). For
every **later** promotion the following rules apply, so the Finder is never
down between a flip and a separate product publication (the atomic-publication
guarantee of `docs/development/v3-search-spatial-derived-data-decision.md:345-348`):

- **Counterpart rule.** A pointer flip may commit only if every Finder product
  **published on the outgoing generation** has a published counterpart on the
  incoming one. Quantifying over the outgoing published set (not the incoming
  registrations) makes a missing counterpart and an unpublished counterpart the
  same violation. The first launch passes because the outgoing generation has
  no published Finder products.
- **Unfinished-product rule.** A flip refuses while any product on the outgoing
  generation is `BUILDING`, or is `READY` with `published_at IS NULL`, unless
  the incoming generation publishes a product with the same `product_code` in
  the same transaction. Retiring the base would otherwise strand the product:
  `015` rejects further chunks and the BUILDING → FAILED transition on a
  retired base, READY is terminal, and no purge exists. The READY-unpublished
  case covers this rollout's own window between the Search build (step 7) and
  the Archetype registration (step 8), when the outgoing generation has no
  BUILDING and no published product yet a ≈ 80 GB insert-only Search would be
  stranded by a flip. This refusal raises its own error, distinct from the
  counterpart rule's. A `FAILED` or published outgoing product never blocks.
- **Same-transaction publication.** `publish_derived_generation` takes the
  incoming products to publish as an argument and, in one transaction:
  verifies each is READY/VERIFIED; moves the pointer and retires the outgoing
  generation; publishes each named product through the routine
  `publish_derived_product` uses (its current-PUBLISHED check now passes);
  then evaluates both rules against the state about to commit, raising on any
  violation so the flip rolls back. `publish_derived_product` alone remains the
  path for attaching products to the already-current generation.
- **The old overload is dropped.** `CREATE OR REPLACE FUNCTION` with a new
  argument list would leave the seven-argument
  `v3_meta.publish_derived_generation(uuid, uuid, bigint, uuid, bigint, text,
  text)` (`006:210-214`) callable without either rule, so `015` executes `DROP
  FUNCTION` on that signature in the same transaction.
- **The pointer table enforces the full contract itself.** A privileged
  connection could update `current_derived_generation` directly, so `015`
  adds: a `BEFORE UPDATE` row trigger taking `pg_advisory_xact_lock(764003001)`
  so a direct update waits for an in-flight publication; a `DEFERRABLE
  INITIALLY DEFERRED` constraint trigger that evaluates at commit exactly what
  the function checks — the new target READY with a VERIFIED receipt (or an
  eligible RETIRED generation) on the current canonical generation, different
  from the old target, `publication_sequence` = old + 1, old target RETIRED and
  new target PUBLISHED in the same transaction, a matching
  `derived_publication_audit` row, and both Finder rules; statement triggers
  rejecting `TRUNCATE` and `DELETE` unconditionally; and a `BEFORE INSERT` row
  trigger that allows `INSERT` only into an empty table (the first publication
  — migration `003` creates the table empty), under the same lock and the same
  deferred contract with no old target and `publication_sequence = 1`. Because
  a row-level `BEFORE INSERT` trigger fires for every proposed row of `INSERT …
  ON CONFLICT DO UPDATE`, the publisher uses a plain `UPDATE` once the singleton
  exists (`006:276-281` uses `ON CONFLICT` today).

The pre-`010` READY `system_search` on `ratings_v4_prod_p4_opt1` gets a NULL
`published_at` and stays invisible because `opt1` is not current; `parallel_v1`
has no Finder products before this rollout.

### 7.5 Disposable PostgreSQL 18 tests

1. Registration on BUILDING, VALIDATING, READY and current PUBLISHED succeeds;
   with a non-NULL `published_at` it fails whatever the base; on RETIRED/FAILED
   it fails.
2. Rows and receipts insert only while BUILDING; mutation and manifest drift
   fail.
3. BUILDING → READY with VERIFIED evidence and → FAILED with evidence work on
   PUBLISHED; every other transition fails.
4. READY-but-unpublished products are absent from all three views and make
   Finder reads 503.
5. `publish_derived_product` rejects every wrong state, wrong generation, blank
   actor, missing receipt and repeat; success sets the exact timestamp and audit
   row under the lock.
6. Direct timestamp mutation without audit fails at commit; paired direct DML
   fails for a non-current generation, a non-PUBLISHED generation, a product
   without VERIFIED evidence, an already-published product and a mismatched
   timestamp; valid paired DML demonstrably holds lock `764003001` (observed
   from a second session with `pg_try_advisory_xact_lock`).
7. Publishing both products in one transaction makes views and API reads
   available.
8. First launch: `publish_derived_generation` succeeds when the **incoming**
   generation's registered products are READY but unpublished and the
   **outgoing** generation has no Finder products at all (the fixture bootstrap:
   the generation is published first, its products afterwards through
   `publish_derived_product`), and does not set `published_at`; the same call
   is refused when the outgoing generation holds a READY-unpublished product
   the incoming transaction does not replace. A later promotion is
   refused when a published outgoing product lacks a published counterpart
   (unpublished or unregistered); naming both counterparts commits atomically
   with the Finder answering throughout; naming only one is refused with the
   pointer unchanged; naming a non-READY/VERIFIED product is refused before the
   flip; an outgoing `BUILDING` product refuses the flip and the same flip
   commits once it is `FAILED`; an outgoing READY-unpublished product refuses
   the flip unless the incoming transaction publishes the same `product_code`.
9. `to_regprocedure` of the old seven-argument signature is NULL after `015`,
   exactly one `publish_derived_generation` exists in `pg_proc`, and the old
   call fails.
10. Pointer table: a direct `UPDATE` violating any part of the contract is
    rejected at commit with the pointer unchanged (non-READY target, skipped or
    repeated sequence, missing lifecycle or audit changes, either Finder rule);
    one satisfying it commits; a two-session race (product publication against
    a direct pointer update) never commits an audit on a generation that is no
    longer current; `TRUNCATE` and `DELETE` are rejected; a first `INSERT` into
    an empty table that meets the contract commits and a second is refused.
11. The inherited `opt1` product stays unpublished and invisible.

Extend the existing migration, builder, validator and API gate tests rather than
replacing them (`tests/test_v3_system_archetype_migration.py:93-209`,
`tests/test_v3_system_archetype_build.py:62-152`,
`tests/test_v3_system_archetype_validate.py:91-208`,
`tests/test_local_search_v3.py:564-595`).

## 8. Production rollout replacing ROADMAP steps 4–9

**Authority.** `docs/ROADMAP.md` controls the rollout order and its gates; this
section is the detail beneath it, and where the two disagree the ROADMAP wins
and the difference is a defect to fix in the same change. The shared invariants
— the governed apply set `[014, 010, 011-rewritten, 013, 015]`, the `Σ_all ≤
4.0` refusal limit, the attach target `ratings_v4_prod_p4_parallel_v1` and the
complete-read capacity input — are checked across the ROADMAP, this design, the
capacity decision and the rollout-state record by
`tests/test_finder_rollout_doc_invariants.py`. This document is lower in the
authority chain than the ROADMAP and
`docs/development/v3-search-spatial-derived-data-decision.md`; PR #805 records
the owner's decision and the replacement steps in the ROADMAP, and PR2 amends
the derived-data decision's "published generations are immutable" sentence with
the explicit exception: ratings relations stay immutable, while derived
products may be **added** to a published generation and become visible only
through the `015` product-publication gate.

All production work is owner-dispatched through governed actions; this design
authorizes no deployment or production access.

**Order.** The release carrying the bounded ranking route deploys **before any
Finder product exists on the target generation**, and the products are
published **last**: publication is what makes `/api/archetypes/rankings` live,
and the currently deployed API gates only on READY
(`apps/api/src/local_search.py:620-643`), so products reaching READY under it
would turn the 503 into a valid-looking empty search (the post-`015` views hide
unpublished rows) and a picked ranking into an error on the removed
`archetype_key` column. From migration apply until publication the Finder is
503 for a verified reason.

| # | Governed step | Reuse/build | Product disk |
|---:|---|---|---:|
| 1 | Amend step-1 registration to ordered `[014, 010, 011-rewritten, 013, 015]`; recompute every migration-set/transition identity; re-attest reachable prefixes. | PR1 (rewritten `011`) and PR2 (`015`) each recut the authority and lineage tests; complete when PR2 merges. Current tail is `[014, 010, 011, 013]`. | negligible |
| 2 | Governed migration `plan`, review the receipt, then `apply`. | `.github/workflows/v3-production-schema-migration.yml`; no new action. | empty structures |
| 3 | Validate all 18 deferred `system_search` constraints after `010`. | Built `v3-system-search-validate-constraints-start/status`. | none |
| 4 | Revise the F3 release gate and **deploy the release first** (section 8.1). | Amend the release authority; reuse the governed release workflows. | 0 |
| 5 | Coefficient calibration, the complete read, and the eligible footprint measurement (section 8.2). | Built `v3-archetype-calibration-probe` for coefficient review; PR4's complete-read action for the capacity input; PR4's disposable-PostgreSQL measurement workflow for the gate's receipts. | 0 (nothing on production) |
| 6 | **Combined capacity gate** (section 8.4) — the last point of no return, before the Search build. | New read-only action modelled on `v3-derived-lifecycle-status`. | 0 |
| 7 | Register, build, validate post-`010` `system_search` on `parallel_v1`; `VACUUM (ANALYZE)` (section 8.5). | Retarget `v3-system-search-f1.sh` from `opt1`; pin `010`/`015` hashes. | ≈ 80 GB (gate charges the measured projection) |
| 8 | Register, build, validate wide `system_archetype` on `parallel_v1`; `VACUUM (ANALYZE)` (section 8.5). | New start/status action in the F1 pattern: build then `--validate`, pin `011`/`015`, receipt READY/VERIFIED and counts. | ≈ 76 GB synthetic; sized from the real histogram |
| 9 | **Go-live:** publish both products in one governed transaction (section 8.6). | New product-publish action; no generation publication. | audit rows |
| 10 | Post-go-live verification (section 8.8). | Read-only `v3-derived-lifecycle-status` and the plan probe. | 0 |

### 8.1 Release gate (step 4)

The gate requires: the exact current PUBLISHED generation key/UUID/sequence;
`[014, 010, 011-rewritten, 013, 015]` applied with exact ledger hashes; the new
`ranking_version`/`ranking_sha256`; the built-image contracts (bounded ranking
route, `Literal[60, 76, 88]` floor, hard-filter rejection, bounded
`from`/`offset`, publication check in `_current_derived_generation()`); and
**no Finder product rows on `parallel_v1`** — not an empty
`v3_meta.derived_product`, because the READY `system_search` retained on `opt1`
would block it permanently. It must **not** require product READY, receipts,
row counts, `published_at` or an audit: those would force the products to be
built under the old image.

After promotion: the live request proves only that the Finder answers 503 with
the not-ready reason. The ranking identity is proved by the deployed image
digest equalling the accepted-release attestation, which **must record the
concrete `ranking_version`/`ranking_sha256`** (step 4 adds the field if the
format lacks it) — not by `/openapi.json`, where both are unconstrained `str`
(`apps/api/src/models.py:378-379`). `/openapi.json` proves parameter shape
only where the schema is concrete (the floor enum, the individual
`offset`/`limit`/`from`/`size` maxima); the combined bounds are proved by a
behavioural probe, which a 503 does not prevent because validation raises 422
first: `offset=9999&limit=1` and `from=9999&size=1` accepted (503),
`offset=9999&limit=2` and `from=9999&size=2` rejected (422).

**Rollback boundary.** The previously accepted image gates on READY only and
reads the removed keyed columns, so the release authority records the F2d
release as the **minimum schema-compatible image**: earlier images are marked
incompatible with the applied set, the rollback target list is cut to images at
or after it, and the gate refuses to promote unless a compatible rollback
artifact is recorded. A rollback below that line is an incident with its own
reviewed plan. Tests assert the trimmed list and the refusal. (This amends the
F3 gate at `docs/operations/v3-production-application-release.md:286-337`.)

### 8.2 Calibration and the complete read (step 5)

Run the built, read-only `v3-archetype-calibration-probe` action (200,000
systems, 1,500 s; scores through `score_raw_system` after PR1) for coefficient
review, and record an explicit `coefficient_decision: accepted` in the
committed evidence — anything else, including absent, refuses the build,
because a complete in-bounds histogram proves the build *fits*, not that its
logic was *approved*.

**The capacity input is a complete read, not a sample.** The probe's stride
sampling (`scripts/v3_archetype_calibration_probe.py:27,48-67`) has no
uncertainty bound and can understate `Σ_all` if tier frequency correlates with
chunk order; a seeded sample cannot give a simultaneous bound over 24 fractions
that is both valid and narrow enough. So PR4 adds a detached read-only
start/status action, `v3-archetype-calibration-complete.sh`, that scores
**every** system through `score_raw_system`, checkpoints per chunk so a restart
resumes, and writes a sealed receipt with `mode: complete`, per-key tier counts
**in total and per canonical chunk ordinal** with the chunk plan's identity,
the system count, and the identities of section 8.3. The sampled mode's output
is refused by the gate. Tests cover the start/status contract, a restart that
resumes from the checkpoint, and that the receipt's per-key totals equal the
generation's system count.

**The eligible footprint receipt is produced here, not by PR1.** PR1's receipt
uses the declared synthetic distribution and is gate-ineligible; the real
fractions exist only after the complete read. So PR4 adds a dispatchable GitHub
Actions workflow, `v3-finder-capacity-measurement.yml`, that runs on a
disposable PostgreSQL 18 service container — never on production — and, from a
checkout whose `f2d_operator_code_sha256` is the attested one: converts the
committed complete-read receipt with `convert_calibration_histogram.py`; runs
`measure_wide_archetype_footprint.py --migration-sql <the registered 011>
--fractions-json <that output>` for the Archetype receipt; runs the Search
pre/post-`010` fills and the fixed-cost fills of section 8.4; and uploads the
sealed receipts, each recording the operator-code identity, the input digests
and the migration hashes. A reviewed PR commits them under
`docs/operations/evidence/`, and the capacity gate reads only committed
receipts. The gate refuses a receipt whose `011` hash is not the applied ledger
entry, so a measurement taken before step 2's apply must be repeated if `011`
changed.

The probe receipt also carries the **expected product manifest** that
`product_manifest()` produces for the pinned generation and the attested code
— computed, not read from a row, because the product is not registered until
step 8 — and its `archetype_model_sha256` from the shared function. Steps 6 and
8 compare against it, and step 8's registration must produce a manifest
byte-identical to it or refuse, so the build is exactly what was
capacity-tested.

### 8.3 Pinned code identities

The operator workflow runs the `trusted-main` checkout, which can be newer than
the attested F2d release, and the rollout itself commits to `main` between the
release and the builds (the coefficient decision and the histogram at step 5),
so the actions cannot be pinned to a commit. They are pinned to the **content**
of the code that runs.

**The operator code runs only at its attested identity.** The repository
carries an explicit file manifest, `deploy/v3-production/f2d-operator-code.txt`,
listing every file the F2d operator path executes: the F2d actions and the
shared shell helpers they source under `scripts/operator/`,
`scripts/v3_system_search.py`, `scripts/v3_system_archetype.py`,
`shared_contracts/v3_system_archetype_model.py` and its re-export,
`scripts/v3_archetype_calibration_probe.py`,
`scripts/dev/measure_wide_archetype_footprint.py`,
`scripts/dev/convert_calibration_histogram.py`, the exact `psycopg` requirement
and wheel the complete read installs, and the manifest itself.
`f2d_operator_code_sha256` is the SHA-256 of the canonical JSON `[path, file
SHA-256]` list over that manifest, computed from the release source and recorded
in the F2d accepted-release attestation. Every F2d operator action — the complete
read, the capacity gate, both build actions, the publish action and the plan
probe — computes the same value over its own checkout **before anything else**
and refuses unless it equals the attested one; inside the container the complete
read also refuses if any loaded module under `/work` lies outside the manifest.
A documentation or evidence commit does not move the identity; a change to any
listed file does, and then only a later accepted release that re-attests the new
value can run the actions. Every receipt records the identity of the checkout
that produced it, and every consumer refuses a receipt whose identity is not the
attested one. A missing attested value is a refusal, never a match.

**The built products are bound to the release too.**

| Identity recorded in the F2d release attestation | Covers | Checked by |
|---|---|---|
| `f2d_operator_code_sha256` | the operator-code manifest above | every F2d operator action before anything else; every consumer against the producing receipt |
| Search manifest code identity | `scripts/v3_system_search.py` as the Search manifest hashes it | `v3-system-search-f1.sh` at registration and build; the publish action before `COMMIT` |
| Archetype manifest `code_sha256` | builder, canonical model, re-export, `011` | the complete read, the Archetype build action, the publish action |
| In-container `model_file_sha256` | SHA-256 of `shared_contracts/v3_system_archetype_model.py` **inside the running API container** (image pinned by the attested digest) | the complete read and the Archetype build action refuse unless the checkout's file hashes the same; the publish action compares the Archetype manifest's `model_file_sha256` before `COMMIT` (the Search manifest has no such field) |
| `ranking_version`/`ranking_sha256` and the image digest | the built API | the publish action (section 8.6) |

Tests: a checkout in which any manifest-listed file differs from the attested
identity is refused by every action before any read or write, while a checkout
that differs only in files outside the manifest is accepted; a receipt carrying
a different identity is refused by its consumer; a probe importing a repository
module outside the manifest is refused; a probe run with a different model file
is refused by the in-container check.

### 8.4 Combined capacity gate (step 6)

One governed read-only action, called as a fail-closed precondition by **both**
build actions. It must pass before the Search build, because `system_search` is
itself an irreversible 198.5 M-row insert-only write. In order, aborting with a
distinct exit code and a receipt on any failure:

- (a) the committed evidence carries `coefficient_decision: accepted`;
- (b) the complete-read receipt's `code_identity`, `coefficients` and
  `archetype_model_sha256` equal the expected manifest's `code_sha256`,
  `coefficients` and `archetype_model_sha256`, and its
  `f2d_operator_code_sha256` equals the attestation's;
- (c) the receipt has `mode: complete`, covers all eight keys and three floors,
  and its per-key totals equal the generation's system count;
- (d) `Σ_all`, the sum of the 24 per-key tier fractions, cross-checks the
  receipt's own `sigma_all`, and `Σ_all ≤ 4.0`;
- (e) a footprint receipt exists from `measure_wide_archetype_footprint.py
  --migration-sql <the applied 011> --fractions-json <converted histogram>` with
  `score_distribution_source: measured-histogram`, `capacity_gate_eligible:
  true` (set only by the final-migration path, which applies the final `011`,
  creates every index on the empty relation, then fills in canonical chunk
  order), an `011` hash equal to the applied ledger entry, `fractions_sha256`
  equal to the canonical form of the committed histogram, and
  `f2d_operator_code_sha256` (recorded by the script and by the converter)
  equal to the attestation's;
- (f) a fresh read-only `df` of the data volume, through the step 0 action's
  path, satisfies `available_bytes >= required_bytes`.

**Histogram conversion.** The probe emits `S`/`A`/`B`/`C`/`D` counts under
`per_archetype.<key>.tier_histogram`; `--fractions-json` takes `{<key>: {"60":
f, "76": f, "88": f}}`. The committed converter
`scripts/dev/convert_calibration_histogram.py` computes, per key, `total = S +
A + B + C + D`, `f["88"] = S / total`, `f["76"] = (S + A) / total`, `f["60"] =
(S + A + B) / total`; asserts `f["60"] >= f["76"] >= f["88"]`, every key present
and each `total` equal to the probe's recorded row count; and refuses a receipt
whose `mode` is not `complete`. The gate refuses a fractions file the converter
did not produce.

**Arithmetic.** Integers throughout; every division rounds up; `system_count`
is the live count of eligible systems, read in the same run. Every per-row cost
comes from the footprint receipt (the gate refuses a receipt missing any of the
four), never from a constant in this document.

```
projected_heap_bytes        = heap_bytes_per_row × system_count
projected_fixed_index_bytes = (primary_key_bytes_per_row + weighted_index_bytes_per_row) × system_count
projected_tier_index_bytes  = tier_index_bytes_per_row_per_unit_fraction × sigma_all × system_count
projected_archetype_bytes   = heap + fixed_index + tier_index
projected_search_bytes      = 0 if system_search is already written for this generation, else
                              (real_pre010_bytes_per_row + measured_010_delta_bytes_per_row) × system_count
projected_new_bytes         = projected_archetype_bytes + projected_search_bytes
required_bytes              = ceil(1.15 × projected_new_bytes)
gate passes  iff  available_bytes >= required_bytes
```

The Search term is measured, never the ≈ 87 GB fixture figure:
`real_pre010_bytes_per_row` is the committed step 0 receipt's real pre-`010`
`system_search` on `opt1`, 80,522,969,088 bytes for 198,528,286 rows (≈ 405.6
B/row; `docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json`),
and `measured_010_delta_bytes_per_row` is the difference between the final
post-`010` DDL and the pre-`010` DDL **each filled from empty with the same
rows** on disposable PostgreSQL 18, digest-bound like the Archetype receipt. It
is never a populated table sized before and after `ALTER TABLE`: `010` adds 18
`NOT NULL DEFAULT 0` columns (`010_v3_system_search_body_type_counts.sql:13-32`)
that PostgreSQL stores as fast defaults without rewriting existing tuples, so
that delta would read near zero while every newly built row stores the
integers. The gate refuses if either input or its provenance is absent.

**Fixed-cost fields for the resume arithmetic.** The same measurement run also
records `search_fixed_bytes_per_row` — the final post-`010` DDL filled with
rows whose `name`, `region_name` and `main_star_class` are one character each
(the minimum the CHECKs allow), so the per-row heap and index bytes contain
essentially no variable text — and `archetype_fixed_bytes_per_row`, the heap
plus primary-key plus weighted-index bytes per row with the shortest archetype
name (`paradise`) in both text columns, whose 16 bytes the maximum-width term
below then counts again, conservatively. The gate refuses a receipt missing
either field. The reserve is 15 % of the projected new footprint — the only
denominator that scales with the WAL, index-build spill (≈ 8 GB peak for the
primary key) and measurement error being covered; 15 % of the volume would
equal the entire free reading. Worked example at `sigma_all = 1.52`: archetype
75.3 GB; with Search unwritten and charged at the pre-`010` rate alone (the
`010` delta is a gate input, not known here), projected ≈ 156 GB and required ≈
179 GB. At `sigma_all = 4.0`: archetype 99.8 GB. The formula reproduces the
measured 75.7 GB archetype total within 0.4 %; the gate recomputes from its own
readings every time.

**Resumes.** Both builds are chunked and resumable, and a fresh `df` already
reflects the rows written, so charging the full product again would refuse a
restart near the ceiling and strand insert-only rows. A resume is recognised
only when the sealed chunk receipts belong to the same product, generation and
manifest identity; anything else pays the full projection. The remaining cost
is bounded **from the unsealed source data**, not scaled from rows or
extrapolated from the rows written — neither of those is an upper bound when
the tail is wider than the head:

```
rows_left            = system_count − rows in this product's sealed chunk receipts
bytes_done           = size of the product's table + indexes + TOAST now − the same at the start receipt
fixed_left           = Search:    search_fixed_bytes_per_row    × rows_left
                       Archetype: archetype_fixed_bytes_per_row × rows_left     (receipt fields above)
variable_left        = Search:   Σ over the unsealed source rows of
                                 octet_length(name) + COALESCE(octet_length(region_name), 0)
                                                    + COALESCE(octet_length(main_star_class), 0),
                                 read from the canonical source by one aggregate, × 2
                                 (stored once in the heap and, for name, once more in the lower(name) index;
                                 region_name and main_star_class are nullable, 004:31-32, and a NULL inside
                                 SUM's expression would drop the whole row)
                       Archetype: 2 × 63 bytes × rows_left
                                 (primary_archetype and secondary_archetype are each CHECKed to at most
                                 63 characters of [a-z0-9_], 011:25-26 — a maximum, not an average)
tier_left            = Archetype only: tier_index_bytes_per_row_per_unit_fraction × tier_entries_left,
                       the exact per-key tier counts of the unsealed chunks from the complete read
remaining_bytes      = fixed_left + variable_left + tier_left
projected_<product>_bytes = max(remaining_bytes, projected_<product>_bytes − bytes_done)
```

`fixed_left` is exact per row because those widths do not vary; `variable_left`
is exact for Search (the source text is read, not estimated) and a maximum for
Archetype; `tier_left` is exact. The 15 % reserve covers index fill factor and
page-level overhead as it does for a fresh build. The subtraction term keeps the
original budget when the early chunks were cheaper than projected. The gate
refuses a resume when the chunk plan differs from the complete read's or a
chunk's counts are missing, and the receipt records every input, both
estimates and the term charged.

Tests: `available_bytes == required_bytes` passes and `required_bytes − 1`
refuses; the receipt reports every input and intermediate; the committed
synthetic `2026-10-10-wide-archetype-footprint-200k.json` fed in unchanged is
refused as synthetic and gate-ineligible; missing or incomplete histogram,
`Σ_all > 4.0`, a receipt from a different `011`, insufficient space, an absent
or non-`accepted` decision, a probe/manifest `coefficients` mismatch, a
probe/manifest `archetype_model_sha256` mismatch, and each identity mismatch of
8.3 are refused with distinct exit codes, varied independently so one valid
field cannot mask another; resume at 90 % rows and 90 % bytes with matching receipts passes while
the same space with a different manifest identity refuses; an early saving (90
% rows, 70 % bytes) is charged the source-derived remainder, not 10 %; a wide tail (90 % of the
Search rows written for 50 % of the projection, the unsealed 10 % carrying
names six times longer) is charged their measured text bytes, which exceed the
projection's remaining 50 %; a dense tail (90 % rows and bytes, 30 % of tier
entries unsealed) is charged the full tier term for those entries.

### 8.5 Builds (steps 7 and 8)

The retargeted Search action and the new Archetype action each: accept only the
exact current PUBLISHED `parallel_v1`; pin their migration ledger hashes
(`010`/`015`, `011`/`015`); refuse unless their code identity matches section
8.3; call the capacity gate and record its receipt beside their own; run the
build and then validation; and, as their
**last action after the final insert**, run and receipt `VACUUM (ANALYZE)` on
the **physical table** — `v3_derived.system_search` and
`v3_derived.system_archetype`; the `v3_app` names are views and PostgreSQL
rejects `VACUUM` on a view. The receipt records the final-insert time and the
table's `pg_stat_user_tables.last_vacuum` and `last_analyze`. The vacuum
populates the visibility map so an `Index Only Scan` is achievable and
`ANALYZE` refreshes statistics that would otherwise describe a table part-way
through a 198.5 M-row append (Search doubles beside the retained `opt1` rows).
Archetype registration must produce a manifest byte-identical to the complete
read's expected manifest (section 8.2).

### 8.6 Publication (step 9)

`v3-publish-derived-products.sh` publishes both products with
`publish_derived_product` in one transaction and receipts timestamps, audit rows
and view counts. It runs **only in the protected production workflow**, under
the `v3-production-application-authority` concurrency group and holding the
host deployment lock from before its first image check until after commit, so a
deployment cannot swap the image between check and commit. Before publishing it
refuses, with distinct exit codes, unless:

- the running API container's image digest equals the F2d accepted-release
  attestation, and the attestation carries concrete
  `ranking_version`/`ranking_sha256` — the identity is taken from the
  attestation alone (no envelope exists while the API answers 503, and the
  OpenAPI fields are unconstrained strings);
- the behavioural probe pairs of section 8.1 pass against the deployed image;
- the Search and Archetype manifests' code identities and the Archetype
  manifest's `model_file_sha256` equal the attestation and the in-container
  hash (section 8.3);
- both physical tables' `last_vacuum` and `last_analyze` postdate their own
  final inserts as recorded in each build's sealed receipt.

Then, **on its own connection inside the transaction, after both
`published_at` updates and before `COMMIT`** — where it can see its own newly
visible rows — it runs the plan probe of section 8.7 and rolls back on any
mismatch, because `published_at` is one-way and the first assertion against
production statistics must be made while it can still be undone. Its last
statement before `COMMIT` repeats the image-digest check. Tests cover the
out-of-order case (products READY, old image digest), an identity mismatch, a
Search table whose analyze predates its final insert, and a failed plan
assertion rolling the publication back.

### 8.7 Plan probe

`v3-archetype-plan-probe.sh` is a read-only action; the publish action runs the
same assertions pre-commit. **The SQL comes from the deployed image:** every
page and count statement is generated by running `build_ranked_query` /
`build_count_query` inside the running API container (pinned by the attested
digest) and its SHA-256 recorded, because a `trusted-main` checkout could
validate newer SQL than the image executes. Each statement runs as `EXPLAIN
(ANALYZE, BUFFERS, FORMAT JSON)` under `plan_cache_mode = force_generic_plan`
with a 60 s statement timeout, after asserting both physical tables'
`last_vacuum`/`last_analyze` postdate their final inserts. It writes nothing.

Assertions, for **all eight archetypes at all three floors** (24 page/count
pairs — planner choices depend on each key's own statistics) and for **both
live no-pick requests** the Explore flow sends
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:123-142`):

- **Picked page and count.** The window node is an `Index Only Scan` on the
  expected `(generation, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score
  >= …` partial with ≤ 10,001 actual rows and **`Heap Fetches: 0`**; the sort
  node's input ≤ 10,000; the fetch node's rows ≤ `page_size` at 50 and 500.
- **Every other node** reading `system_search` or `system_archetype` in any
  probed plan **except the no-pick sentinel count (next but one)** is an `Index
  Scan`/`Index Only Scan` on that relation's `(derived_generation_id,
  system_id64)` primary key with `(Actual Rows + Rows Removed by Filter) ×
  Actual Loops ≤ 10,001`; any `Seq Scan`, `Bitmap Heap Scan`, or hash/merge
  join input over either relation fails — `Actual Rows` counts emitted rows,
  not examined ones.
- **Galaxy-wide no-pick page.** Window node an index scan on the
  `weighted_potential` index with ≤ 10,001 rows; other nodes as above.
- **No-pick sentinel count — the one exception to the node-type rule.** No
  node type is prescribed, because `build_count_query` has no `ORDER BY` and
  may legitimately stop at its `LIMIT 10001` by any path, a sequential scan
  that stops at the limit included; the plan must be capped by that `LIMIT`,
  and every node reading either relation satisfies the same `(rows + removed)
  × loops ≤ 10,001` bound, so a scan that discards another generation's rows
  or reads the table through still fails.
- **Anchored nearest-first.** PR1 rewrites the anchored page and its sentinel
  count around a GiST KNN scan on `system_search_position_gist`
  (`004_v3_search_spatial_clusters.sql:52`), **limit inside, radius outside**:

  ```sql
  SELECT … FROM (
      SELECT …, s.position_ly <-> :anchor AS distance_ly
        FROM v3_app.system_search s JOIN … (the archetype summary, by primary key)
       WHERE s.position_ly <@ :bounding_cube          -- index condition
       ORDER BY s.position_ly <-> :anchor,            -- KNN order from the index
                sum.weighted_potential DESC NULLS LAST,
                s.system_id64
       LIMIT :inner_limit                             -- offset + page, or 10,001
  ) nearest
  WHERE nearest.distance_ly <= :radius                -- the exact radius
  ```

  A radius filter cannot stop a KNN scan, but the inner `LIMIT` does; because
  the scan is in distance order, the rows within the radius are a prefix of it,
  so the count is exact below 10,001 and capped otherwise. The existing
  tie-break (weighted potential, then `system_id64`) is kept, served by an
  incremental sort over each equal-distance group. The probe runs this request
  at Sol and at the densest 500-ly window (anchor from the highest-count cell
  of the spatial pyramid, recorded), and requires the KNN index scan under the
  inner `Limit`, an `Incremental Sort` rather than a `Sort`, and `(Actual Rows
  + Rows Removed by Filter) × Actual Loops ≤ (inner_limit + T) × G`, with tie
  slack `T = 1,000` (the equal-distance group straddling the limit must be
  finished; exact ties need equal squared distances on the 1/32-ly grid, so a
  larger group at a probed anchor fails) and `G` = the number of generations
  holding Search rows, read at probe time and recorded (`G = 2` while `opt1` is
  retained, because the position index does not lead with the generation).
  The probe also runs the two anchored requests the inner `LIMIT` cannot bound
  — the anchored request with the most selective accepted hard filter, and the
  anchored **score-sorted** request (`sort_by='development'`) — at the densest
  window and the 500-ly radius the route allows them (section 6); for both, the
  bound is the bounding box's candidate count × `G`, measured with a count at
  that window, and the plan must read `system_search` through
  `system_search_position_gist` and nothing else by sequential scan.

### 8.8 Post-go-live verification (step 10)

From the live application: results are served; the envelopes carry the expected
generation, `ranking_version`/`ranking_sha256` and **all three** product
identity fields (F4 decides comparability from `archetype_model_sha256` alone,
so a two-field check would silently disable it); the read-only plan probe still
passes against the committed state; and `v3-derived-lifecycle-status` reports
both products' `published_at` and `derived_product_publication_audit` rows
independently of the publisher's receipt (PR4 adds those reads; today the
action selects lifecycle fields only, `v3-derived-lifecycle-status.sh:443-454`).

Total new persistent Finder data is about 157 GB plus the `010` delta on the
synthetic distribution (Search ≈ 80.5 GB at the pre-`010` rate plus ≈ 76 GB
Archetype), leaving roughly 135 GB of the observed 292 GB before transient use;
the gate's own measurement, not this arithmetic, decides whether step 6 passes.

## 9. Fixtures and validation lanes

The shared fixture seed already runs the real Search and Archetype
register/build/validate pipelines and publishes the generation. Update it to
apply `015`, build one wide row per system, publish the generation, then
publish both products in one transaction; the shared seed's assertions (which
the Cypress wrapper delegates to) require READY **and** product-published
(`scripts/dev/seed_v3_fixture_generation.py:27-52,267-300`,
`scripts/dev/seed_cypress_v3_generation.py:1-11,32-43`).

Review Lab applies every migration `sql/v3/migration-manifest.txt` declares, in
order, and nothing else (`scripts/dev/review_lab/lifecycle.py:426-443`,
`tests/test_review_lab_v3.py:505-518`), so the rewritten `011` is registered
(manifest hash **and** authority recut) in PR1 and `015` in PR2, or those PRs'
own Review Lab runs fail.

Test changes:

- migration/builder tests assert one wide row per system, all 24 key columns,
  all constraints, the 26 physical indexes by name and predicate, the summary
  view, the complete-row seal and unchanged chunk resumability;
- Cypress and Review Lab seed tests assert both products READY with
  `published_at IS NOT NULL`, one wide row per fixture system, and unchanged
  Search/ranking response fields;
- Product E2E keeps the Finder journey and Review Lab the isolated synthetic
  behaviour; source, migration, builder, lifecycle and API invariants stay in
  normal CI (`docs/development/v3-browser-validation-lanes.md`);
- the calibration-probe test keeps asserting that vectors are read and no
  product rows are written, and adds that the probe's per-key tier counts equal
  the tiers the builder persisted for the same fixture chunk.

## 10. Implementation plan: small PRs

Every PR passes every protected check on its exact head with both reviews and
every substantive finding dispositioned
(`docs/development/pull-request-acceptance-policy.md`). Three facts fix the PR
boundaries: CI checks every manifest hash against the migration bytes and the
operator/watchlist/deployment tests recompute the migration-set and schema
identities against `deploy/v3-production/target-authority.json`, so a changed
migration needs the hash **and the full authority recut** in the same PR; the
rankings integration tests and Review Lab execute the live ranking SQL, which
reads columns the wide rewrite removes, so the SQL lands with the schema; and
Review Lab applies only declared migrations, so the seed can publish products
only once `015` is declared in the same PR. Four PRs, each green at its own head.

### PR1 — wide `011`, model, builder/validator, ranking SQL, registration

- `sql/v3/migrations/011_v3_system_archetype.sql` (rewritten);
  `sql/v3/migration-manifest.txt`; `deploy/v3-production/target-authority.json`
  and `docs/operations/v3-production-application-release.md` recut for
  `[014, 010, 011-rewritten, 013]`.
- `shared_contracts/v3_system_archetype_model.py` (canonical model:
  `score_raw_system`, the two query constants, `_explain_*` split out,
  `archetype_model_sha256`); `scripts/v3_system_archetype_model.py` (re-export).
- `scripts/v3_system_archetype.py` (wide build, pure fetch, `code_identity()`
  over the canonical file and the re-export, manifest fields of section 5.1,
  per-column validator, PUBLISHED-ready structure); `scripts/v3_system_search.py`
  untouched until PR2.
- `scripts/v3_archetype_calibration_probe.py` scores raw rows through
  `score_raw_system` (no private copy of the old scaling or SQL `avg`) and
  records `archetype_model_sha256`.
- `apps/api/src/ranking/profile.py`, `ranking_sql.py`, `routers/archetypes.py`,
  `models.py`, `local_search.py`: everything in section 6, including the
  local-search sentinel count, the combined `from + size` bound, the galaxy-wide
  hard-filter refusal, the anchored KNN path and both envelopes' identity
  fields; regenerated clients `apps/web/src/lib/api/generated/types.gen.ts`,
  `sdk.gen.ts` and `packages/api-client/src/generated/api.gen.ts`.
- `scripts/dev/measure_wide_archetype_footprint.py`: `--migration-sql` applies
  the final `011` to the disposable database, fills the real table in canonical
  chunk order after creating every index, sizes the heap and all 26 indexes, and
  emits `heap_bytes_per_row`, `primary_key_bytes_per_row`,
  `weighted_index_bytes_per_row` and
  `tier_index_bytes_per_row_per_unit_fraction` from unrounded bytes with the
  round-up rule (tests prove the tier value is normalized by the receipt's own
  `sigma_all`); `--fractions-json` for the gate; the committed built-in layouts
  stay as the pre-migration reference; PR1's own receipt uses the declared
  synthetic distribution and is labelled gate-ineligible.
- `scripts/operator/actions/v3-derived-lifecycle-status.sh` pending-set
  contract, if it pins hashes.
- `scripts/dev/seed_v3_fixture_generation.py`, `seed_cypress_v3_generation.py`
  (wide rows; product publication waits for PR2).
- Tests: `test_v3_system_archetype_{migration,model,register,build,validate,cli}.py`,
  `test_v3_archetype_calibration_probe.py`, `test_ranking_profile_identity.py`,
  `test_ranking_sql.py`, `test_archetype_rankings_v3.py`,
  `test_local_search_v3.py`, `test_ranking_identity_and_no_legacy.py`,
  `test_measure_wide_archetype_footprint.py`, both seed test modules,
  `test_v3_lineage_migrations.py`, `test_v3_production_migration_operation.py`,
  `test_v3_system_search_production_operator.py`, `test_v3_watchlist_postgres.py`,
  `test_v3_production_application_deployment.py`.

Checks: Ruff; the archetype, calibration, ranking and no-legacy suites;
disposable-PG18 migration/build/validate and rankings integration; exact `011`
hash and identity reproduction; a new footprint receipt from
`--migration-sql` against the final text; the OpenAPI drift check for the
additive response fields; migration/script, PostgreSQL integration,
canonical-safety, application-deployment, Cypress, Review Lab and security CI.

### PR2 — migration `015`, builders on PUBLISHED, API publication gate

- `sql/v3/migrations/015_v3_derived_product_publication.sql` (section 7);
  manifest and authority recut for `[014, 010, 011-rewritten, 013, 015]`.
- `scripts/v3_system_search.py`, `scripts/v3_system_archetype.py` accept a
  PUBLISHED base.
- `apps/api/src/local_search.py`: `_current_derived_generation()` requires
  READY **and** `published_at`.
- `scripts/dev/seed_v3_fixture_generation.py` publishes both products after
  generation publication.
- `docs/development/v3-search-spatial-derived-data-decision.md` section 1
  amendment (section 8); `docs/ROADMAP.md` step 4′ progress note.
- Tests: `tests/test_v3_derived_product_publication.py` (new; the section 7.5
  matrix), `test_ranking_identity_and_no_legacy.py` (its fixture must apply
  `015`, use the new publisher and publish both products),
  `test_local_search_v3.py`, `test_archetype_rankings_v3.py`,
  `tests/integration/conftest.py`, both seed test modules, the lineage,
  migration-operation, operator, watchlist and deployment tests.

### PR3 — on-demand explanation endpoint

- `apps/api/src/routers/archetypes.py` (new route; legacy route untouched),
  `apps/api/src/models.py`, all three regenerated clients
  (`pnpm generate:api`; the drift check fails on any of them,
  `apps/web/package.json:28`, `.github/workflows/ci.yml:524`).
- Tests: `tests/test_archetype_system_v3.py` (new; section 4),
  `test_ranking_identity_and_no_legacy.py`.

Checks: Ruff; disposable-PG18 endpoint tests; OpenAPI generation/drift; `pnpm
check`, `pnpm test`, `pnpm build`; backend, integration, Svelte, Cypress,
Review Lab and image-parity CI.

### PR4 — governed operator actions and revised release gate

- `scripts/operator/actions/v3-archetype-calibration-complete.sh` (new,
  section 8.2) with its `chatgpt-ed-new-ops.yml` allowlist entries and receipt
  upload; `scripts/dev/convert_calibration_histogram.py` (new).
- The capacity gate action (new, section 8.4).
- `scripts/operator/actions/v3-system-search-f1.sh` (retarget, pins,
  identity, gate, `VACUUM (ANALYZE)` on `v3_derived.system_search`;
  today hard-coded to `opt1` and checking only `006`,
  `v3-system-search-f1.sh:15-24,76-113,175-176`).
- `scripts/operator/actions/v3-system-archetype.sh` (new, section 8.5).
- `scripts/operator/actions/v3-publish-derived-products.sh` (new, section
  8.6) and `v3-archetype-plan-probe.sh` (new, section 8.7), sharing their SQL
  generation and plan assertions.
- `scripts/operator/actions/v3-derived-lifecycle-status.sh` reads
  `published_at` and the publication audit (section 8.8).
- `.github/workflows/chatgpt-ed-new-ops.yml` allowlist entries;
  `docs/operations/v3-finder-production-rollout-state.md`;
  `docs/operations/v3-production-application-release.md` and
  `deploy/v3-production/target-authority.json` (release gate of section 8.1,
  attestation identities of section 8.3, rollback boundary);
  `deploy/v3-production/f2d-operator-code.txt` (new: the operator-code manifest
  of section 8.3, with a test that every F2d action and every file it executes
  is listed).
- Tests: `tests/test_v3_system_search_production_operator.py`,
  `tests/test_v3_system_archetype_production_operator.py` (new),
  `tests/test_v3_product_publication_operator.py` (new),
  `tests/test_v3_production_application_deployment.py`, converter and
  lifecycle-status contract tests (a published and an unpublished product).

Checks: shell/action contract tests including every refusal of sections 8.3,
8.4 and 8.6 with its own exit code; exact generation UUID/key/sequence,
current-pointer, migration-hash, worker-name, resource-bound, receipt and
start/status tests; repeat/concurrent publication failures; allowlist/workflow
schema; release-preflight tests; operator, canonical-safety, migration,
application-deployment and security CI.

## 11. Risks and open questions

**Status (2026-10-12).** Answered: **1, 5, 8 and 9**.
Open questions: **2, 3, 4, 6 and 7**; each blocks the code PR that encodes it.
`docs/ROADMAP.md` holds the authoritative list and
`tests/test_finder_rollout_doc_invariants.py` checks that this status agrees
with it.

1. **Approve the section 3.3 layout** — eight stored `<key>_weighted_e4` keys,
   primary key, weighted index and 24 tier partials (≈ 76 GB synthetic, sized
   from the real histogram; the capacity decision's "stops if the ≥ 60 fraction
   exceeds ≈ 40 % on several keys" is the same stop, expressed here as the gate
   on `Σ_all`)? **Owner: yes** (partial principle
   2026-10-10, stored-key refinement 2026-10-11; capacity decision questions 6
   and 6b).
2. **Approve exact integer parts-per-million confidence storage** with
   `ppm / 1000000.0` in SQL and `ppm / 1e6` in the API? Same 4 bytes as `real`,
   exact, no tolerance; `real` can reorder near-ties, `double precision` costs
   +14 GB.
3. **Approve moving the canonical model into `shared_contracts/`** with a
   temporary `scripts/` re-export? Without it the API image has no `fit_all`
   (`apps/api/Dockerfile:20-24`).
4. **Approve the additive explanation route** and leave the legacy
   `/api/archetypes/system/{id64}` unchanged until its V2-only fields have a V3
   source? Repointing it now would drop fields.
5. **HTTP 409 with exact detail `explanation unavailable for this product
   version`** for a version/hash mismatch? **Owner: yes** (2026-10-10; capacity
   decision question 5).
6. **Require production publication of both Finder products in one
   transaction?** The API fails closed unless both are published; one
   transaction gives a cleaner audit boundary.
7. **Accept the four-PR sequencing of section 10**, where PR1 and PR2 each
   carry their own registration and authority recut so every head is green? A
   separate registration PR cannot pass the manifest-integrity and
   authority-identity tests at intermediate heads.
8. **Accept no purge before Finder promotion?** **Owner: yes** — the recorded
   decision; changing it needs a separate destructive-data design and authority.
9. **Accept that the initial archetype ranking takes no hard filters**, and
   that galaxy-wide Any-mode requests refuse them until an anchor is set?
   **Owner: yes** (2026-10-12); filtered archetype ranking is deferred work.

## 12. Design acceptance

Implementation is acceptable only when: every system produces one wide row
whose model outputs match the pre-rewrite outputs under the integer-ppm rule;
the measured PG18 heap and every index fit the approved disk/WAL/temp/vacuum
envelope; READY is not visible until explicit product publication; attachment
to a PUBLISHED generation retains every fail-closed manifest, receipt,
transition, insert-only and generation-publication rule; ranking response
fields are unchanged apart from the additive fields and carry the new pinned
identity; explanation mismatch fails with the exact rule and message; Cypress
and Review Lab use the real wide product and explicit publication; and
exact-head CI/review acceptance is complete under the repository policy.

Planned implementation commit message:

```text
docs(finder): F2d design — wide-row archetype product and product attachment/publication on a published generation
```

### Review round history

Rounds 8–52 (2026-10-11 to 2026-10-12), with each finding's disposition, are in
`docs/superpowers/specs/2026-10-10-v3-finder-f2d-review-history.md`, beside this
file (rounds 1–7 were dispositioned in the PR threads only); the PR #806
review threads hold the same record. Text above this heading
is the current design; the history records superseded text and is evidence
only.
