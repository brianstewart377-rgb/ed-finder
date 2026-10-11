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
`floor(confidence * 1_000_000 + 0.5)` — round-half-up, named explicitly rather
than left to `round()`'s default, which is ties-to-even in Python and
ties-away-from-zero in PostgreSQL `numeric` (the same ambiguity review round 16
removed from the ranking key; found by sweeping for it rather than by review).
Unlike completeness there is no integer source here, because model confidence is
genuinely a float, so the rule is instead pinned to one place: a shared helper
computes it, the validator **calls that helper** rather than reimplementing the
expression, and it is never recomputed in SQL. The validator compares integers
with no tolerance, the ranking SQL uses `(a.<key>_confidence_ppm / 1000000.0)` (a
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
    -- served in its own order by an index. Integer definition (section 3.1):
    -- (score × confidence_ppm × completeness_ppm + 50_000_000) // 100_000_000,
    -- range 0..1,000,000. Never round() -- see the rounding rule.
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
    -- exact integer completeness input to every <key>_weighted_e4, stored so the
    -- builder, the validator and the explanation route read one value instead of
    -- each re-deriving it: min(system_rating_vector.completeness) x 100
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
`(<key>_score × <key>_confidence_ppm × completeness_ppm + 50_000_000) //
100_000_000` — the exact integer form defined below, which is the definition
rather than an implementation of one. It is the integer nearest
`score × confidence × completeness × 10000`, and the search product must still
be READY before the archetype build because the completeness input comes from
the same generation's rating vector, as today. An integer in 1e-4 units is exact and 4 bytes;
ordering by it equals ordering by the double product except for ties within
0.0001, which `system_id64` then breaks deterministically — that rounding is part
of the new ranking identity, not a hidden difference. Measured heap: 221.7 B/row
(≈ 44 GB), 35 B more than without the eight keys.

**The rounding rule is integer arithmetic, not `round()` (review round 16).**
`round()` is not a cross-language contract: Python's built-in is ties-to-even,
so `round(2.5) == 2`, while PostgreSQL `numeric` rounds ties away from zero, so
`round(2.5::numeric) == 3`. This integer is both persisted and used as **the
canonical ordering key**, so a half-integer disagreement between the builder and
the exact validator — or between two implementations claiming the same manifest —
would silently order tied systems differently while every version string matched.
The definition is therefore closed in integers, with no floating-point value
anywhere in it:

```
completeness_ppm   = min(system_rating_vector.completeness) × 100   -- smallint[], 1e-4 units
numerator          = <key>_score × <key>_confidence_ppm × completeness_ppm
<key>_weighted_e4  = (numerator + 50_000_000) // 100_000_000
```

**In SQL the numerator must be cast to `bigint` before the first multiplication
(review round 19).** The declared operands are `smallint` and `integer`, so
PostgreSQL evaluates `smallint × integer × integer` as **`integer`** and
overflows at entirely ordinary values — `100 × 1_000_000 × 1_000_000` is 1e14
against an `integer` ceiling of 2.1e9. The bigint range quoted below is the range
of the *result*, which the expression never reaches: validation would raise
`integer out of range` and no correct product row could pass, so the immutable
build could never reach READY. The exact expression the validator and the
boundary tests use is therefore:

```sql
((<key>_score::bigint * <key>_confidence_ppm * completeness_ppm) + 50000000)
    / 100000000
```

The first cast is enough — PostgreSQL promotes the rest of the chain once one
operand is `bigint` — and integer division in SQL truncates towards zero, which
equals the floor here because every operand is non-negative.

**The completeness input is the rating-vector integers, not
`system_search.completeness` (review round 17).** That column is
`double precision` (`sql/v3/migrations/004_v3_search_spatial_clusters.sql:41`),
so reading it would put a float back into a definition whose whole purpose is to
have none, and the "exact `completeness_ppm`" the first draft of this section
assumed did not exist. The exact source does exist and the builder already reads
it, but **the column is `system_rating_vector.completeness`, a `smallint[]` in
1e-4 units (`003_ratings_v4_derived.sql:120`) — not `evidence_completeness`
(review round 24).** That name exists only as a `double precision` alias in the
unnested `system_economy_rating` view, where it is already
`completeness[i] / 10000` (`003_ratings_v4_derived.sql:223`), so an instruction
naming it would either raise an undefined-column error against
`system_rating_vector`, preventing the immutable product from reaching READY, or
reintroduce the float this rule exists to remove. The builder divides the raw array
by `10000.0` at `scripts/v3_system_archetype.py:277`; taking `min()` of the raw
`smallint[]` **before** that division and scaling by 100 gives `completeness_ppm`
in `0..1_000_000` with no float in the path.

`completeness_ppm integer` is **persisted on the wide row**, so the builder, the
exact validator and the explanation route all read one stored integer and cannot
diverge by recomputing from different sources. That adds 4 bytes per row
(≈ 0.8 GB over 198.5 M). The capacity gate does not hold a heap constant to
correct — round 18 moved every per-row cost into the footprint receipt it already
verifies — but the receipt must be produced **against the final migration text**,
including this column, before the build, as section 8 requires. The 221.7 B/row
in section 3.4 is the measurement as taken, and is superseded by that receipt.

The divisor follows from the units and is not a tuning constant:
`score × (conf_ppm / 1e6) × (comp_ppm / 1e6) × 1e4 = score × conf_ppm ×
comp_ppm / 1e8`. The `(n + divisor/2) // divisor` form is round-half-up on
non-negative integers, which every language and PostgreSQL compute identically
because no rounding mode is involved. Both ppm inputs are already stored as
exact integers, so nothing becomes a float on the way in.

Range, checked rather than assumed: `<key>_score` is `0..100` and both ppm
values are `0..1_000_000`, so the numerator is at most 1e14 — exact in
`bigint` (max 9.2e18) — and the key is `0..1_000_000`, comfortably inside
`integer`. Verified against the floating-point product over 500,000 random
`(score, confidence_ppm, completeness_ppm)` triples: **zero disagreements** at
any non-tie input, so this rule changes nothing except making the ties
decidable.

A worked tie, to show the rule bites: `score = 1`, `confidence_ppm = 50`,
`completeness_ppm = 1_000_000` gives a numerator of exactly `50_000_000`, a
true half. The integer rule yields **1**. Python's `round(0.5)` yields **0**
(ties-to-even) and PostgreSQL `round(0.5::numeric)` yields **1** (half away
from zero) — the two would have disagreed on a persisted ordering key while
every version string matched.

The builder, the exact validator and the ranking-identity tests all carry
half-boundary vectors — a numerator landing exactly on `50_000_000`, two keys
landing on the same `_weighted_e4` so `system_id64` must break the tie, and the
`0` and maximum ends — and assert the same integer from all three.
`RANKING_VERSION` covers this rule, so changing it is a ranking change and not
an optimisation.

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

  **The literal is the only floor predicate — the parameter is dropped, not kept
  beside it (F4 review round 37).** "Redundant literal" above describes how the
  behaviour was *measured*, against a parameterized form; it is not the shape to
  ship. Keeping a parameterized `<key>_score >= $n` next to the literal defeats the
  **index-only** window, because the partial carries only
  `(generation, <key>_weighted_e4, system_id64)` and evaluating a parameterized
  `<key>_score` forces a heap fetch for every candidate row — losing the acceptance
  criterion the bounded-plan proof rests on. Nothing is lost by dropping it:
  `min_score` is validated to exactly 60, 76 or 88, so the server-chosen literal
  **is** the requested value in every accepted case, and the route branches on the
  validated floor to emit it.

Measured on the disposable PostgreSQL 18.4 (200,000 rows, bell-shaped scores
with 16.9 % ≥ 60, 2.1 % ≥ 76, 0.19 % ≥ 88 per key; `v4_weighted_key_tier_partials`
in the committed evidence): ≥ 60 partial 8.5 B/row, ≥ 76 1.1 B/row, ≥ 88 0.2 B/row
per key — ≈ 79 B/row for all 24 — plus primary key 40.7 and weighted index 40.8;
indexes total 160 B/row ≈ 32 GB. Each partial's size is 49.8 B × (fraction of
systems at or above that floor). The three predicates are **nested**, not
disjoint — a system scoring ≥ 88 on a key is indexed in that key's ≥ 60, ≥ 76
**and** ≥ 88 partials — so the cost is driven by the sum of all 24 fractions:

```text
partial-index GB  ≈  49.8 B × 198.5 M × Σ(f60 + f76 + f88 over the 8 keys) / 1e9
                  ≈  9.9 GB × Σ_all
archetype total   ≈  44 GB heap + 16 GB (primary key + weighted index) + 9.9 × Σ_all
```

The synthetic sample's Σ_all is 8 × (0.169 + 0.021 + 0.0019) = **1.54** ⇒ 15.2 GB
of partials (measured 15.6) ⇒ ≈ 76 GB. The absolute ceiling, if every fraction
were 1 (every system at tier S on every archetype), is 24 × 9.9 = 237 GB of
partials ⇒ **≈ 297 GB** — not the ≈ 132 GB of the rejected full-score-index
layout, which this design no longer uses. So **the capacity gate is on Σ_all,
not on the ≥ 60 fraction alone**: the pre-build gate computes Σ_all from the
calibration probe's per-key tier histogram and may proceed only while
`Σ_all ≤ 4.0` (≈ 40 GB of partials, archetype ≈ 100 GB, new data ≈ 187 GB,
≈ 105 GB left of the 292 GB observed free) **and** the re-measured total plus
Search plus WAL/temp/vacuum room fits the free space in a fresh step 0 receipt.
Above that the design is revisited — the fallback is to index fewer floors (only
≥ 60, accepting a residual filter for the A and S floors) or fewer archetypes.
The histogram is read at that gate, after the governed probe has run, never in
PR1 (whose receipt uses the declared synthetic distribution, section 10). The earlier
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
asyncpg encoding failure (tests cover both bounds), and with three **optional
identity query parameters**, each bounded by request validation rather than
reaching the database as free text — `expected_generation_id` typed
`uuid.UUID`, `expected_archetype_version`
`Query(None, min_length=1, max_length=128)` (the bound the column's own CHECK
uses) and `expected_manifest_sha256`
`Query(None, pattern=r'^[0-9a-f]{64}$')` (exactly 64 lower-case hex
characters) — that a client copies from the ranking envelope of the card it is
explaining. A malformed or oversized value is a 422 from validation, never a
409 identity conflict and never a database parameter; tests cover an over-128
version, an empty version, 63- and 65-character hashes, upper-case hex and a
non-hex string. When any
is supplied and differs from the current published product, the route answers
HTTP 409 with the same detail string as the version rule in section 4.3, so a
product republished between a card's ranking response and the user expanding
its explanation can never be explained against a different product than the one
that produced the displayed score; the 200 response always echoes the identity
it computed against so the client can re-check it (F4 design review, round 18).
Leave the existing legacy
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

- the one matching `system_rating_vector` row;
- the matching `economy_opportunity` rows grouped by economy ordinal; **and**
- the one matching generation-pinned `v3_app.system_archetype` wide row — the
  eight score/tier/confidence-ppm triples and the summary columns — because the
  response contract requires the recomputed values to be compared against the
  stored ones and to fail closed on a mismatch. Reading it in the same round
  trip is what makes that comparison possible and keeps it on one consistent
  snapshot; a later second read could see a different row. If the wide row is
  absent the route is a 404 for that system, not a computed explanation.

The query must use the leading `(derived_generation_id, system_id64)` keys and
return the same `SystemVectors` fields as `_read_chunk_vectors`, then call the
shared `fit_all` and `summarise` and compare every recomputed value with the
stored row (a test seeds a deliberately divergent stored row and asserts the
fail-closed response rather than a plausible-looking explanation). The existing source relations have primary
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
wide row.

**The identity check and the data read share one snapshot (review round 16).**
Checking the identity first and reading the data afterwards leaves a window: if
`current_derived_generation` changes between the two statements, the request
validates the card's expected identity against the **old** product and then
computes the explanation from the **newly published** generation. Making the
data query internally consistent does not close that window, because the window
is between the check and the query, not inside the query. The result would be an
explanation stamped with an identity it was not computed under — the exact
confusion the 409 exists to prevent, arriving with a 200.

So the identity lookup, the expected-value comparison and the
generation-pinned data read all run inside **one read-only `REPEATABLE READ`
transaction**, as the rankings path already does. A publication committing
mid-request is then invisible to that request: it either serves entirely from
the pre-publication snapshot or, on the next request, entirely from the new one,
and in the case that matters it returns 409 rather than a mixed answer.

A test publishes a new generation **between** the identity statement and the
data statement — by committing from a second connection while the request is
suspended between them — and asserts the response is consistent with exactly one
snapshot: either the pre-publication explanation, or a 409, never an explanation
computed from the new generation under the old identity. The current product manifest and model version already form the
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
generation identity, source policy, and code identity.

**Add a second, generation-free digest `archetype_model_sha256` (F4 review round
31).** `product_manifest()` hashes `derived_generation_id`, `generation_key`,
`canonical_generation_id`, `canonical_publication_sequence` and `expected_rows`
alongside the coefficients (`scripts/v3_system_archetype.py:128-138`), so
`archetype_manifest_sha256` changes on **every** rebuild even when the model is
byte-identical. That is correct for its job — identifying one build exactly — but
it makes the digest useless for answering "were these two scores produced by the
same model?", which is what the F4 snapshot comparison needs. Requiring the
manifest digest to match there would make cross-generation comparison impossible
rather than merely strict: the feature would silently never fire.

`archetype_model_sha256` therefore covers a **canonical semantic manifest**: the
coefficients, the anchors, the archetype key order, the `_weighted_e4` integer
expression carried as a literal string, the confidence rounding rule and the tier
thresholds. It excludes generation identity, publication sequence and
`expected_rows` — everything describing *which data* was scored rather than *how*.

**It includes `model_file_sha256` — the shared model file alone — and excludes the
broad `code_sha256` (review round 19).** `code_identity()` hashes three files:
the builder `scripts/v3_system_archetype.py`, the model
`scripts/v3_system_archetype_model.py`, and the migration
`011_v3_system_archetype.sql` (`scripts/v3_system_archetype.py:64-73`). Taking all
three was self-defeating — a comment, a batching fix in the builder or a
storage-only migration change would alter the digest while every score stayed
bit-identical, suppressing the comparison this field exists to enable through an
edit that changed nothing. Taking none of them was the opposite error, left over
from round 32: the digest then rested entirely on declared constants, so a change
to the model's *logic* that left its constants alone would not show up.

**But the model file is not scoring-only either (review round 24).** It also
defines `ARCHETYPE_VERSION` — which this very design bumps to `v3-archetype-4`
**solely because the persisted storage shape changed** — and it contains the
explanation construction. Hashing the whole file would therefore move
`archetype_model_sha256` for a storage-only version bump, an explanation-only edit
or a non-semantic refactor, while the weighted scores stayed comparable:
suppressing the cross-generation comparison through a change that provably altered
no score. The design would have broken its own field on its own next version bump.

So the digest covers a **named set of members of the model file**, not the file:
the coefficients, the anchors, the archetype key order, the tier thresholds, the
`_weighted_e4` integer expression, the confidence rounding rule, **and the source
text of the named scoring functions**. It explicitly excludes
`ARCHETYPE_VERSION`, the explanation construction and every storage-shape
constant.

**That exclusion requires a small refactor in PR1 (review round 25).** Hashing
`fit_all` and everything it calls does **not** currently exclude explanation
construction, because `_fit_anchored` and `_fit_flexible` build their explanation
dictionaries **inside** the scoring functions themselves
(`scripts/v3_system_archetype_model.py:120-145`) — so an explanation-only edit
would still move the digest and silently suppress the F4 comparison with scores
provably unchanged, which is the exact defect this scope was narrowed to avoid.
The exclusion was unimplementable as written.

PR1 therefore **separates explanation construction out of the scoring path**: each
`_fit_*` function returns its score, tier and confidence, and a distinct
`_explain_*` function builds the dictionary from the same `SystemVectors`.
`archetype_model_sha256` hashes the `_fit_*` functions and excludes the
`_explain_*` ones. That is a behaviour-preserving refactor of code PR1 already
changes, and it is what makes the stated exclusion true rather than aspirational.
A test asserts the digest is unchanged by an edit confined to an `_explain_*`
function and changed by any edit to a `_fit_*` one.

That keeps the property round 19 was after — a change to **how scores are
computed** always moves the digest — while a change to how they are stored,
versioned or explained never does, which is exactly what hashing the whole file
could not give. `code_identity()`'s three whole files stay in
`archetype_manifest_sha256`, where identifying one exact build is the point.

The honest cost is that hashing declared values makes the digest a **declaration**
that the semantics are unchanged, not a proof: two builds could agree on every
declared constant and still compute different scores through a code change the
manifest does not describe. The validator therefore converts the declaration into
a checked claim — **two builds whose `archetype_model_sha256` agree must produce
identical `<key>_weighted_e4` values for a shared sample of systems** — asserted
during validation rather than left to trust. `archetype_manifest_sha256`, which
does cover the source files, remains the field for exact-build identity. It is persisted
on the product row and exposed in `ranking_provenance` beside
`archetype_manifest_sha256`, which keeps its own job and its own meaning. PR1
owns both the column and the envelope field. The validator asserts the digest is
**stable across two builds of the same model on different generations** and
changes when any covered component does — but it does **not** assert that those
two generations produced identical keys (review round 22). They legitimately may
not: a later generation rebuilt from different canonical data can give the same
system different rating vectors or completeness, and so a different
`<key>_weighted_e4`, under an identical model. Requiring equal keys would reject
that valid rebuild and block READY. The key-equality assertion is against the
committed **frozen input fixture** of `(score, confidence_ppm,
completeness_ppm)` vectors instead, as section 5.2 states; this list is the
implementation of that, not a second weaker rule.

Add a canonical ordered `wide_columns` list (the eight `_weighted_e4` keys and their exact definition
the integer definition `(score × confidence_ppm × completeness_ppm + 50_000_000) // 100_000_000` included verbatim, not a `round(...)` form),
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
- the same generation's `system_search` product is **READY with a VERIFIED
  validation receipt**. The stated reason has to change with round 17: the stored
  ranking keys take their completeness from the **rating vector**, not from
  `system_search.completeness`, so the keys no longer depend on Search at all.
  The dependency remains for a different and still-sufficient reason — the
  builder reads `system_search` confidence for `weighted_potential`, and the
  rankings envelope joins `system_search` for its response columns — so a
  complete-but-unverified Search product (all rows inserted, validation not run
  or failed on another invariant) must still fail Archetype promotion; registration (`register_product`) applies the same check
  so a build cannot start against an unverified dependency, and the tests cover
  the complete-but-unverified case;
- every Ratings chunk has exactly one matching archetype receipt;
- `count(system_archetype) == count(system_rating_vector)` and every system has
  exactly one `v3-archetype-4` row;
- every one of the eight score columns is 0–100;
- every `<key>_weighted_e4` equals
  `(<key>_score × <key>_confidence_ppm × completeness_ppm + 50_000_000) // 100_000_000`
  exactly — the same integer expression the builder and the manifest carry, with
  no `round(...)` and no floating-point value anywhere in it — using the
  `completeness_ppm` **stored on the row**, and the validator additionally
  re-derives that stored `completeness_ppm` from
  `min(system_rating_vector.completeness) × 100` on the same generation's rating vector and
  fails closed if the row is missing or the two disagree;
- every tier equals `tier_of(its score)`;
- each stored `_confidence_ppm` integer equals the value returned by **the shared
  half-up helper** (`floor(confidence * 1_000_000 + 0.5)`; section 3.1) called on
  a fresh model confidence, exactly and with no tolerance. The validator **calls
  that helper** rather than writing the expression itself: at an exact half,
  Python's `round()` is ties-to-even while the builder's helper is half-up, so a
  validator that reimplemented it with `round()` would **reject a correctly built
  row** and the immutable product could never reach READY — a build failure with
  no bad data to point at. The validator's tests include a half-boundary
  confidence vector;
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
`uncertainty_factor` from the stored columns). The requested floor is **one of
exactly three values** — 60, 76 or 88, the tier floors B/A/S — and the picked
`WHERE` carries it as a **literal** tier-floor predicate chosen server-side from
that validated value (`<key>_score >= 60`, `>= 76` or `>= 88`, emitted as text so
the planner can prove the matching partial index applies under a generic plan;
no user string is ever interpolated — the literal is picked from a fixed
three-entry map). Because the floor can only be one of the three indexed
values, the literal *is* the exact requested floor: there is no residual heap
filter on raw score, and the scan is index-only and bounded for every accepted
request (an arbitrary value such as 100 would have been served from the `>= 88`
partial with a heap filter that could read that whole partial — review round 6 —
which is why non-tier values are not accepted). Measured under
`plan_cache_mode = force_generic_plan`: parameter-only ⇒ parallel sequential
scan + sort; with the literal ⇒ index scan on the matching partial, reading at
most the query's own limit (10,000 for a page, 10,001 for the count). For no pick, keep the `v3_app.system_archetype_summary` join
and `sum.weighted_potential DESC NULLS LAST` unchanged. Preserve all selected
aliases.
(`apps/api/src/ranking/ranking_sql.py:246-263,294-329,451-506,512-546`)

**The whole bounded structure is PR1's, including the window-then-filter
order.** The picked query is built in four stages, and the archetype relation is
touched exactly twice — once index-only for the window, once by primary key for
the page:

1. **Window (index-only).** An inner query over `v3_app.system_archetype`
   alone selecting only `system_id64` and `<key>_weighted_e4` — generation,
   literal floor, `ORDER BY <key>_weighted_e4 DESC, system_id64 ASC`. The limit
   differs by query and that difference matters: the **page** query uses
   `LIMIT 10000`, because its stage-3 sort must receive at most 10,000 rows (the
   plan assertion and the production probe both require that); the **count**
   query uses `LIMIT 10001`, because the 10,001st row is precisely the sentinel
   that sets `is_truncated`. A single 10,001-row window for both would push an
   11th-thousand row into the page sort and fail the assertion. Those are exactly the partial index's own columns
   `(derived_generation_id, <key>_weighted_e4, system_id64)`, so this stage is a
   genuine `Index Only Scan` with no heap access.
2. **Join (no filtering).** Join `v3_app.system_search` to those ≤ 10,001 rows
   **for the response columns only**. No hard filter appears here or anywhere
   else in the query: a picked request carrying one is rejected with 422 before
   any SQL is built (see “Hard filters in selected mode” below), so there is no
   filtering stage to implement. The join is for data, not selection.
3. **Page.** Restate the order explicitly on the ≤ 10,000 survivors —
   `ORDER BY <key>_weighted_e4 DESC, system_id64 ASC` — then `OFFSET`/`LIMIT`.
   The outer `ORDER BY` is required, not decorative: an ordered index scan
   inside a subquery or CTE says nothing about the final result order and the
   planner may choose a hash join for stage 2. Sorting ≤ 10,000 rows is cheap
   and bounded; the plan tests assert the sort node's input rows are ≤ 10,000.
4. **Fetch (bounded, by primary key).** Join `v3_app.system_archetype` again on
   `(derived_generation_id, system_id64)` for the ≤ `page_size` paged rows only,
   to read the selected `<key>_score`, `<key>_tier`, `<key>_confidence_ppm` and
   the summary columns the response reports — at most `page_size` primary-key
   lookups per request, which the route bounds at **500**
   (`apps/api/src/routers/archetypes.py:517`), not 50: the F4 facade exposes
   1–50, but the API contract is the limit that matters here and the plan probe
   must exercise a 500-row page so a legal large page is never truncated or
   left unverified.

   **The outermost `SELECT` repeats `ORDER BY <key>_weighted_e4 DESC,
   system_id64 ASC` after this join (review round 15).** Stage 3's `ORDER BY`
   orders stage 3's output; it does not survive being joined again. A hash or
   nested-loop plan for this fetch may emit the page in any order, so without a
   final `ORDER BY` the response would contain the correct 50 systems in an
   arbitrary sequence — the worst shape of this bug, because every row is right
   and only the ranking is wrong, which no row-set assertion would catch. The
   sort is over at most `page_size` (≤ 500) already-materialized rows.

   The plan assertions therefore require: the window node is an `Index Only
   Scan` on the expected partial index with ≤ 10,001 actual rows, and the fetch
   node's actual rows are ≤ `page_size` (tested at both 50 and the route's
   maximum 500); for the count query the window node may read exactly 10,001.
   **A plan assertion is not sufficient on its own**: the tests also assert the
   returned rows' actual order — that the response's `<key>_weighted_e4` values
   are non-increasing and ties break by ascending `system_id64` — on a fixture
   seeded with deliberate ties, and that two adjacent pages concatenate into one
   correctly ordered sequence with no repeated or skipped system. Bounding the
   sort node's input proves the query is cheap; only the row order proves it is
   right.

Carrying those columns as INCLUDE payload on the 24 partial indexes was
rejected: it would add payload to every indexed row to save at most `page_size`
(≤ 500) key lookups per request. The count query needs stages 1 and 2 only (and stage 2 only for its join shape — it filters nothing).

**Hard filters are rejected on a picked archetype, not redefined (review round
9).** A filter inside the inner `WHERE` would let the index scan run past 10,001
entries looking for matches — unbounded again — so the only bounded placement is
*after* the window. But filtering after the window silently changes what a
filter means: a selective `galaxy_region`, `max_distance_ly` or `has_elw`
request would discard every qualifying system ranked below the global first
10,000 and could return an empty page while millions of matching systems exist,
and `is_truncated` would describe the unfiltered population. The product
contract says Finder filters select the results
(`docs/colonisation-redesign/spatial-platform-product-contract.md:102-110`), so
this design does not quietly weaken them. PR1 therefore makes
`/api/archetypes/rankings` **reject** a picked request that carries any hard
filter — `galaxy_region`, `max_distance_ly`, `has_elw`, `min_slots`,
`max_contamination` — with HTTP 422 naming the unsupported parameters and the
reason (“archetype ranking is unfiltered in the initial product; filter in Any
mode or drop the filter”). Consequences, all honest and bounded:

- stage 2 becomes a plain join for the response columns, with no filter
  predicates, so `total = min(qualifying, 10000)` and `is_truncated =
  qualifying > 10000` mean exactly what they say — the Finder never shows an
  empty page while matches exist;
- Any mode keeps every filter, unchanged: it runs through local search, which
  has its own indexes and its own (already capped) count;
- the F4 UI disables — not hides — the hard filters while an archetype is
  picked, with the same reason as the 422, so the combination is never offered
  (F4 design, picker anatomy);
- filtered archetype ranking stays the documented deferred work: it needs a
  filter-first bounded access path (a denormalized projection co-locating the
  stored ranking key with hot search predicates, or per-filter composite
  indexes), which no cheap index can provide on the wide row.

The disposable-PG18 tests assert the 422 for each hard filter on a picked
request, that Any mode with the same filters is unaffected, and — from the plan —
that the inner scan reads ≤ 10,001 entries. Because the route is live in
production from the moment the release deploys, this bounded form ships in that
release (section 8 step 5), not in a later F4 slice.

**Tie-break.** The current profile breaks ties by Sol distance, then
`system_id64` (`PROFILE_SPEC` `("distance", "system_id64")`), and the route
passes Sol coordinates for that purpose. The stored key's ties are broken inside
the index by `system_id64` alone; honouring a distance tie-break would require
sorting the whole window by distance for equal keys and would defeat the
index-order guarantee. The new identity therefore **changes the picked-mode
tie-break to `system_id64` only**. `PROFILE_SPEC` today has one global
`tie_break = ["distance", "system_id64"]`; it becomes **mode-specific** —
`tie_break: {"picked": ["system_id64"], "no_pick": ["distance", "system_id64"]}`
— so the hash describes exactly what each path executes: the no-pick path keeps
its distance-then-id order unchanged, the picked path drops distance, and the
SQL builder reads the mode's list rather than a shared constant. The identity
test mutates each list separately and asserts the digest changes; the
response-order tests replace the Sol-distance tie cases for picked mode and keep
them for no-pick. Distance from Sol remains a displayed fact, not an ordering
term, for picked results.

**The count is bounded too.** Today `/api/archetypes/rankings` awaits
`build_count_query(..., cap=None)`, an exact count over every qualifying row —
≈ 34 M rows at the synthetic 17 % B fraction, unbounded by any index. PR1
changes the picked count to `SELECT count(*) FROM (SELECT 1 … LIMIT 10001) t`
with the **server-selected literal floor alone** — not literal plus parameter
(review round 23): `<key>_score` is not in the partial index, so a parameterized
`<key>_score >= $n` would force a heap fetch for each of up to 10,001 candidate
rows and break the `Index Only Scan` the publication gate asserts. The count
window needs the same literal-only form as the page window for the same reason: the response's `total` is
`min(count, 10000)` and `is_truncated` is `count = 10001`, exactly the
within-window contract the F4 design already specifies for selected mode, now
honest for the count as well as the page. The galaxy-wide local-search path is
**bounded but not sentinel-based** today: it passes `cap=10000` and sets
`total_is_capped` when the returned count is `>= 10000`
(`apps/api/src/local_search.py:922,965-970`), so exactly 10,000 matches is
indistinguishable from a million. **PR1 changes that path too**, to
`LIMIT cap + 1` with `total = min(count, cap)` and
`total_is_capped = count > cap` (see PR1's `local_search.py` entry); Any mode is
not left unchanged.
Tests execute the ranked and count SQL on the disposable PG18 fixture with
`plan_cache_mode = force_generic_plan` and assert, from `EXPLAIN (FORMAT JSON)`,
that the matching partial index is used for each floor and that no plan node
reads more than 10,001 archetype rows.

The partial indexes (section 3.3) cover only rows scoring ≥ 60, so **PR1
changes the rankings route's `min_score` contract deliberately**: today it is
`Query(40, ge=0, le=100)` (`apps/api/src/routers/archetypes.py:511`) and the SQL
binds the requested floor directly (`apps/api/src/ranking/ranking_sql.py:355-357`);
after PR1 it is `min_score: Literal[60, 76, 88] = Query(60)` — the default
request and every accepted value name an indexed tier floor, and any other value
(59, 70, 100, …) is a 422 rather than a silently truncated or unbounded result.
**Pagination is bounded to the same window:** `offset` becomes
`Query(0, ge=0, le=9999)` and `limit` keeps `ge=1, le=500`, with a route-level
check that `offset + limit <= 10000` (422 otherwise) — both derived from the
hashed window constant — so no request can read rows beyond the advertised top
10,000 (today `offset=Query(0, ge=0)` is passed straight to `OFFSET`; review
round 6). This is a real contract change and is treated as one: the default, the
three accepted floors, the stored-key definition — hashed as the exact integer
expression `(score × confidence_ppm × completeness_ppm + 50_000_000) //
100_000_000`, never a `round(...)` form, because `PROFILE_SPEC` is the hashed
authority and a notation that leaves half-ties open would let two
implementations order boundary rows differently while claiming the same
`ranking_sha256` — the 10,000 window and its combined offset/limit bound, the
`is_truncated` rule, the **hard-filter rejection rule** (the exact set of
parameters a picked request may not carry, and that carrying one is a 422 — not
a post-window filter rule, which the route cannot execute and which would make
`ranking_sha256` describe behaviour that does not exist) and the
**`total = min(qualifying, 10000)` rule** are all declared in `PROFILE_SPEC`
and therefore hashed into `ranking_sha256`; the route's `Query(...)`
declarations are built from those spec constants rather than typed beside them,
and the identity test mutates the default, the accepted-floor set, the window
size, the rejected-parameter set and the key definition in turn and asserts the
digest changes each time. The response models gain
**additive fields**: `is_truncated: bool` on `ArchetypeRankingsResponse`
(`apps/api/src/models.py:911-924` has `extra='forbid'`, so returning the key
without the field would be a 500, and omitting it would make a saturated
`total=10000` indistinguishable from an exact one), and the archetype
**product identity** — `archetype_version`, `archetype_manifest_sha256` (hex,
identifying one build exactly) and `archetype_model_sha256` (hex,
generation-free model semantics; section 5.1) of the published product the scores
came from — on both the rankings envelope and the local-search envelope beside
the existing `ranking_version` / `ranking_sha256` / generation fields. All three
are required on both envelopes: the manifest digest cannot answer "same model?"
because it embeds generation identity, and the model digest cannot answer "same
build?" because it deliberately does not. The ranking hash covers score selection,
modifiers, filters and ordering but not the model coefficients, so clients that
persist or compare scores (the F4 design's saved surfaces) need the product
identity as well; the explanation route's expected-identity parameters
(section 4.1) take the same values. Both envelopes are PR1's work and PR1's
file list names every part of it — the shared identity model, the product-row
lookup in `_current_derived_generation()`, the rankings and local-search
response construction, and assertions on both envelopes in
`tests/test_local_search_v3.py` and `tests/test_archetype_rankings_v3.py`; the
local-search envelope is not deferred to PR2, which touches `local_search.py`
again only for the publication gate. The OpenAPI parameter
constraints and response schema change so PR1
regenerates all three typed clients (`apps/web/src/lib/api/generated/*` and
`packages/api-client/src/generated/api.gen.ts`), and the tests cover the default
request, each of 60/76/88, `min_score=59`/`70`/`100` → 422, `offset=9999,
limit=1` → 200, `offset=9999, limit=2` and `offset=10000` → 422, and
`is_truncated` true/false. Nothing in
`apps/web` calls `/api/archetypes/rankings` yet (the F4 UI is unbuilt and the
legacy frontend is retired), so no live caller loses a result. The alternative —
indexing all scores so 0–59 stays bounded — costs ≈ 95 GB of indexes for rows
no planned caller asks for. With the page and the count both served from the
tier partials in canonical order, the F4 design's slice 1c no longer needs a
separate raw-score candidate window: it inherits this contract and specifies
the browser side of the 10,000 window.

The outward ranking and Search response fields do not otherwise change (the one
addition is `is_truncated` above): selected score,
tier, confidence, primary, secondary, Best Colony Potential, archetype
confidence, completeness, uncertainty, and ranking identity remain present.
Beyond that, only `ranking_version`/`ranking_sha256` change. (`apps/api/src/routers/archetypes.py:389-406,422-494`,
`apps/api/src/local_search.py:790-839,951-964`)

Tests must cover all eight key-to-column mappings (score, tier, confidence
**and weighted key**), that the SQL map is derived from the hashed spec and that
mutating a mapping, the floor default/bounds or a floor literal changes
`ranking_sha256`, the literal-floor selection for each of 60/76/88 and the
rejection of every other value, the offset/limit window bound,
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

`publish_derived_generation` still requires every registered product to be
READY/VERIFIED before flipping the generation pointer. For **this** rollout,
`published_at` is independent and remains NULL until the explicit product
launch, because the pointer already points at `ratings_v4_prod_p4_parallel_v1`
and no Finder products exist on it yet — flipping nothing, so there is nothing
to make invisible. (`sql/v3/migrations/006_v3_derived_product_lifecycle.sql:245-284`)

**That independence must not outlive this rollout (review round 16).** Once
these products are registered and published, a *later* generation promotion is a
different situation. The pointer flip retires the currently visible generation
at commit; if the incoming generation's Finder products are still
`published_at = NULL`, the post-`015` views hide their rows and the Finder
answers 503 until a separate product-publication action succeeds. Between those
two commits the Finder is **down**, having been up a moment earlier — and the
authoritative derived-data contract's atomic publication guarantee
(`docs/development/v3-search-spatial-derived-data-decision.md:345-348`) exists
precisely to forbid that. It would also be an avoidable outage: the ordering is
a choice, not a constraint.

So `publish_derived_generation` **refuses the pointer flip** when the incoming
generation has registered Finder products that are not all published, unless it
publishes them in the same transaction. The rule, stated so it covers both
cases without a special case for the first launch:

> A generation pointer flip may commit only if, at commit, **every Finder
> product published on the outgoing generation has a published counterpart on
> the incoming generation.**

Quantifying over the **outgoing published set** rather than the incoming
registered set matters, and the first draft of this rule got it wrong (review
round 17). Quantified over incoming registrations, a generation that registers
and publishes only `system_search` satisfies it vacuously — `system_archetype`
is simply absent, so there is no registered product to find fault with — and the
flip commits while the Finder, which needs both, answers 503. The rule has to be
anchored to what is **visible now and must not stop being visible**, which is the
outgoing published set. A missing counterpart and an unpublished counterpart then
become the same violation, as they should be: in both cases something the Finder
is serving stops being served.

The first launch passes because the outgoing generation has no published Finder
products, so there is nothing to require a counterpart for. Every later promotion
must carry both. One rule covers both cases deliberately: an exemption dated to
this rollout is the kind of thing that outlives its reason, and that is precisely
how the original text went wrong. The guard lives in the function, next to the
READY/VERIFIED check, so no caller can skip it.

Tests cover: a later promotion whose incoming products are registered but
unpublished (refused); a later promotion that registers and publishes only
`system_search` while the outgoing generation has both published (refused — the
case the first draft of this rule let through); the same promotion publishing
both in one transaction (commits, with the Finder answering throughout); and this
rollout's first launch, where the outgoing generation has no published Finder
products (permitted).

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
   but unpublished **and the outgoing generation has no published Finder
   products** — the first-launch case — and does not populate `published_at`;
8b. the same promotion is **refused** when any Finder product published on the
   outgoing generation lacks a published counterpart on the incoming one,
   whether that counterpart is unpublished or not registered at all (section
   7.4). Without this scoping, case 8 as previously written would have driven an
   implementation that flips the pointer away from two visible products to
   unpublished replacements — the Finder outage section 7.4 exists to forbid; and
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
design authorizes no deployment or production access. **Order matters at the
end:** the application carrying the bounded ranking route (PR1–PR4) is released
and promoted *before* the products are published, because publication is what
makes `/api/archetypes/rankings` live — publishing against the current
production image would expose the old unbounded selected-ranking sort and
`COUNT(*)` (review finding on the F4 design, round 17), or, against the wide
schema, fail outright on the removed `archetype_key` column. The deployed API
returns 503 for the Finder until both products carry `published_at`, so the
interval between promotion and publication is a clean, reviewable "not ready"
state rather than a half-live one.

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
| 4 | **Revise the F3 application-release gate and deploy the release first.** The gate requires: the exact current PUBLISHED generation key/UUID/sequence; migrations `[014, 010, 011-rewritten, 013, 015]` applied with their exact ledger hashes; the new `ranking_version`/`ranking_sha256`; the bounded ranking route and the `Literal[60, 76, 88]` floor present in the built image; and the publication check live in `_current_derived_generation()`. It requires **no Finder product rows on the pinned `parallel_v1` target generation** — not an empty `v3_meta.derived_product` (review round 17): a READY `system_search` is deliberately retained on `opt1` and its purge is deferred (ROADMAP lines 140-143), so a global emptiness check would fail permanently and block the deployment it is supposed to authorize. Retained products on other generations must not block it. After promotion, verify the two things separately, because a 503 carries no response envelope and therefore cannot advertise an identity: the **live request** proves only that the Finder answers 503 (with the not-ready reason), while the **ranking identity** is proved from the deployed image digest matching the accepted-release attestation, which must record both concrete `ranking_version`/`ranking_sha256` values (this gate adds that field if the attestation format lacks it) — **not** from `/openapi.json`, where both are unconstrained `str` and a comparison would be vacuous. `/openapi.json` proves the **built-image parameter shape** only where the schema carries a concrete value: the `Literal[60, 76, 88]` floor as an enum, and the individual `offset`/`from`/`limit`/`size` maxima. It **cannot** prove the combined bounds `offset + limit <= 10000` and `from + size <= 10000` (review round 16): JSON Schema has no way to relate two fields, so an image whose route or request model omitted that validator would publish an identical schema and pass a gate that claimed to check it. The combined bounds are therefore proved by a **behavioural probe against the deployed image**, which the 503 does not prevent because a 422 is raised by request validation before the generation is ever consulted: `offset=9999&limit=1` and `from=9999&size=1` are accepted (503, not 422), while `offset=9999&limit=2` and `from=9999&size=2` are rejected with 422. The identity is re-verified from a real envelope at step 9, once products are published, which is the check that compares a value the running code actually computed. | Amend the existing release authority and reuse the governed release/deployment workflows; no new build action. Its current assumptions predate attach-to-PUBLISHED. (`docs/operations/v3-production-application-release.md:286-337`, `CLAUDE.md:31-37,82-91`) | 0 GB |
| 5 | Run the bounded coefficient-calibration probe on `ratings_v4_prod_p4_parallel_v1`, record the decision, and commit its per-key tier histogram as the capacity gate's input. **The recorded decision must be an explicit affirmative (review round 16):** a complete histogram with `Σ_all <= 4.0` is evidence that the build would *fit*, not that its scoring logic was *approved*. A review that concluded the coefficients must change would still leave a complete, in-bounds histogram behind, and the old precondition would have passed on it — launching the immutable, non-purgeable build with rejected logic. The committed evidence therefore carries an explicit `coefficient_decision: accepted` (anything else, including absent, refuses), and the probe's recorded `code_identity` and coefficient digest **must equal the manifest the Archetype builder registers**. Without that second half the first is still bypassable: an approved probe could authorize a build whose real tier fractions were never capacity-tested at all. | Reuse built `v3-archetype-calibration-probe` unchanged. It is read-only and reads vectors, not the stored product. (`scripts/operator/actions/v3-archetype-calibration-probe.sh:1-5,21,77-85,135-157`, `scripts/v3_archetype_calibration_probe.py:212-220,256-298`) | 0 GB |
| 6 | **Combined capacity gate — the last point of no return.** One governed read-only action computes `Σ_all` from the committed calibration histogram (refusing if it is absent, incomplete, or its digest does not match the recorded evidence), refuses `Σ_all > 4.0`, requires a footprint receipt for the applied `011` whose `score_distribution_source` is `measured-histogram` and whose fractions digest matches that histogram — **produced through the defined conversion below, because the probe's output is not the measurement script's input format (review round 20)**, takes a fresh read-only `df`, and refuses unless **Search (≈ 87 GB) plus the measured Archetype total plus 15 % working room** fits the free space. It must pass before step 7, because `system_search` is itself an irreversible 198.5 M-row insert-only write: building Search first and failing the gate afterwards would strand an unpublishable, non-purgeable 87 GB product. Both build actions call the same gate as a fail-closed precondition and record its receipt. | New read-only action, modelled on `v3-derived-lifecycle-status`; its arithmetic is the one in section 3.3. | 0 GB |
| 7 | Register, build, and validate post-`010` `system_search` on the pinned current `ratings_v4_prod_p4_parallel_v1`. | Retarget the existing F1 start/status action from `opt1`, pin exact `010` and `015` ledger hashes, accept only the exact current PUBLISHED generation, and retain its validation receipt. The current action is hard-coded to `opt1` and checks only `006`. (`scripts/operator/actions/v3-system-search-f1.sh:15-20,76-113,175-176`) | about **87 GB** (measured/extrapolated post-`010`) (`docs/operations/v3-finder-production-rollout-state.md` (PR #805)) |
| 8 | Register, build, and validate wide `system_archetype` on the same pinned generation. | Build a new governed Archetype start/status action using the F1 safety pattern; it must invoke the existing CLI build then `--validate`, pin rewritten `011` and `015`, and receipt READY/VERIFIED plus row/chunk counts. The roadmap records that this governed validation route does not exist today. (`docs/ROADMAP.md:190-195`, `scripts/v3_system_archetype.py:1109-1154`) | **about 76 GB** on the synthetic distribution (section 3.4); the tier-partial indexes are sized from the step-4 calibration histogram and re-measured with the final migration text before the build |
| 9 | **Go-live:** in one governed transaction, call `publish_derived_product` for `system_search` and `system_archetype`; verify both timestamps/audits and view counts. This is deliberately the last step: publication is the reviewed switch that makes the Finder visible, and it may only run once the release from step 8 is the running application (the action verifies the deployed ranking identity against the gate before publishing). | Build a new product-publish action, modeled on the pinned, separately receipted spatial publish pattern; no derived-generation publication occurs. The current workflow allowlist has no Archetype-build or product-publish operation. (`.github/workflows/chatgpt-ed-new-ops.yml:10-24,81-84`) | negligible metadata/audit rows |
| 10 | **Post-go-live verification:** confirm from the live application that the Finder serves results, that the response envelopes carry the expected generation, `ranking_version`/`ranking_sha256` and **all three** archetype identity values — `archetype_version`, `archetype_manifest_sha256` **and `archetype_model_sha256`** (review round 20: F4 decides whether scores from different generations are comparable from the model digest alone, so a response that omits or mis-populates precisely that field would pass a two-field check and silently disable the comparison, with no error anywhere) — and that a picked-archetype request's plan is still bounded — the latter through the new read-only `v3-archetype-plan-probe` action, which asserts the index, the ≤ 10,001-row window and the ≤ `page_size` fetch (exercised at `page_size` 50 and 500) from a real `EXPLAIN (ANALYZE, BUFFERS)`; `v3-derived-lifecycle-status` separately reports the product rows, publication timestamps and audit rows. **The bounded-plan probe also runs *inside* the publication transaction (review round 21):** after both `published_at` updates and **before commit**, because the transaction can see its own newly visible rows, so the picked query is planned against production statistics and the expanded views while the change is still reversible. Any plan mismatch — a scan or sort that is not the expected bounded shape — rolls the publication back. Running it only after commit, as this step originally did, exposed users the moment production statistics or view expansion chose an unbounded plan despite the disposable tests passing — and `published_at` is a one-way transition with no governed path to clear it, so the first assertion against production would have been made at the one point where failing it could not be undone. This post-commit run is kept as confirmation that the committed state still plans correctly. | Reuse the read-only `v3-derived-lifecycle-status` action plus the publish action's own receipt; no new mutation. | 0 GB |

**Rollback is constrained from the moment `011`/`015` are applied (review round
12).** Deploying first removes the forward hazard but not the backward one: the
previously accepted image's `_current_derived_generation()` gates on READY only
and its ranking SQL reads the removed keyed columns, so rolling back to it after
the products reach READY would reproduce exactly the empty-Finder/broken-ranking
failure. PR4 therefore makes the release authority record, at step 4, that **the
F2d release is the minimum schema-compatible image**: every earlier accepted
image is marked incompatible with the applied migration set, the deployment
workflow's rollback target list is cut to images at or after it, and the gate
refuses to promote unless a compatible rollback artifact (the F2d image itself,
or a later one) exists and is recorded. If a rollback is ever needed below that
line it is an incident requiring its own reviewed plan — not a routine
redeploy — because the schema cannot go back. Tests assert the trimmed rollback
list and the refusal when no compatible artifact is recorded.

**Why the release must be deployed before any product reaches READY (review
round 9).** The currently deployed API's `_current_derived_generation()` gates
only on both products being READY (`apps/api/src/local_search.py:620-643`). If
the products reached READY while that build was still live, it would stop
answering 503 and start querying the `v3_app` views — which after `015` hide
every unpublished row — so the default local search would return a
valid-looking **empty** result and a picked ranking would error against the
removed `archetype_key` column. Deploying first removes that interval entirely:
from migration apply until step 8 the Finder is 503 for a *verified* reason
(step 5's post-promotion check), first because no products exist and then
because the deployed code requires `published_at`. The release gate therefore
cannot require product rows — they do not exist when it runs — and publication
is verified after the fact by the publish action's receipt and step 9.

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
  all constraints, **all 24 tier-partial stored-key indexes** (three floors ×
  eight keys, asserted by name and predicate), the weighted index and the
  primary key — 26 physical indexes in total — folded
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
- `apps/api/src/routers/archetypes.py` (`min_score: Literal[60, 76, 88] = Query(60)`;
  `offset` bounded to the window; `is_truncated` returned)
- `apps/api/src/models.py` (`ArchetypeRankingsResponse.is_truncated: bool`,
  additive; `archetype_version`, `archetype_manifest_sha256` **and the
  generation-free `archetype_model_sha256`** (section 5.1) on the shared
  ranking-identity model both envelopes use. All three go through both envelope
  constructors, the regenerated clients and the identity tests: the model digest
  is the only one stable across equivalent-model generations, so omitting it from
  the wire leaves F4's cross-generation comparison with nothing to compare on,
  and the feature silently never fires)
- `apps/api/src/local_search.py` (**PR1, not PR2**: the galaxy-wide count query
  gains the same **10,001st-row sentinel** the picked path uses — `LIMIT cap + 1`
  instead of `LIMIT cap` — and the response reports `total = min(count, cap)`
  with `total_is_capped = count > cap`. Today the flag is set whenever
  `total >= GALAXY_WIDE_COUNT_CAP` (`apps/api/src/local_search.py:965-970`), so a
  search with exactly 10,000 matches is indistinguishable from one with a
  million and any “10,000+” copy is a claim about rows that may not exist; the
  sentinel costs one extra row and makes the flag true. Tests pin exactly 10,000
  (flag false) and 10,001 (flag true). The request model also enforces
  the same **combined** window bound as the rankings route —
  `from >= 0`, `size >= 1` and `from + size <= 10_000` — so a direct caller can
  neither post `from: 2000000000` and force an unbounded `OFFSET` against the
  ranking index nor slip past the window with `from=10000&size=500` while the
  capped total says 10,000. Nothing reachable is lost: no mode navigates past
  10,000 by contract and a galaxy-wide count is capped there. Tests pin
  `from=9_950,size=50` (ok), `from=10_000,size=1` (422) and
  `from=10_001` (422). Also: the local-search envelope's
  ranking identity gains `archetype_version`, `archetype_manifest_sha256` and
  `archetype_model_sha256`;
  `_current_derived_generation()` returns the published archetype product's
  code/version/manifest hash **and model hash** alongside the generation id and
  sequence, and
  `local_db_search_v3()` builds the envelope from it. It fails closed exactly as
  today when that product is missing or not READY — 503, never an envelope
  without identity. PR2 touches this file again only for the publication gate)
- `apps/web/src/lib/api/generated/types.gen.ts`,
  `apps/web/src/lib/api/generated/sdk.gen.ts`,
  `packages/api-client/src/generated/api.gen.ts` (regenerated for the changed
  parameter constraint and the two new identity fields on both envelopes)
- `scripts/dev/measure_wide_archetype_footprint.py` (gains `--migration-sql
  sql/v3/migrations/011_v3_system_archetype.sql`: applies the final migration
  text to the disposable database instead of its built-in DDL, fills the real
  `v3_derived.system_archetype`, and sizes the heap and all 26 physical indexes.
  PR1's receipt uses the **declared synthetic** bell-shaped distribution already
  committed and labels it as such: the calibration probe has not run — the
  rollout schedules it as a governed step after these PRs merge — so its
  histogram cannot be a PR1 input. The script also takes `--fractions-json`,
  which the pre-build capacity gate uses with the probe's real per-key tier
  fractions; the committed built-in layouts stay as the pre-migration reference)
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
the final `011` text (heap and all 26 physical indexes — 24 tier partials,
weighted index, primary key);
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
  row/chunk counts — **and the capacity gate as a fail-closed precondition of
  `start`**, because this is the irreversible 198.5-million-row write. Before it
  launches anything the action must, in this order, and abort with a distinct
  non-zero exit code and a receipt on any failure: (a) read the recorded
  calibration-probe histogram from the committed decision evidence and refuse if
  it is absent or does not cover all eight keys and three floors; (b) compute
  `Σ_all` = the sum of all 24 per-key tier fractions, cross-check it against the
  receipt's own `sigma_all`, and refuse if `Σ_all > 4.0`;
  (c) require a footprint receipt produced by
  `scripts/dev/measure_wide_archetype_footprint.py --migration-sql <the applied
  011> --fractions-json <that histogram>`, whose `score_distribution_source` is
  `measured-histogram`, whose `011` file hash matches the applied ledger entry,
  **and whose `fractions_sha256` equals the SHA-256 of the canonical form of
  that same committed histogram** (the script records `fractions_canonical`,
  `fractions_sha256` and `sigma_all` for exactly this purpose, so a stale or
  substituted JSON cannot pass as a measured histogram); (d) take a fresh `df`
  reading of the data volume through the same read-only path the step 0 action
  uses, and refuse unless `available_bytes >= required_bytes` under the exact
  arithmetic below. The receipt records every input and every intermediate, so
  the decision is reproducible from the log. **The same gate runs before the
  Search build** (rollout step 6), because Search is equally irreversible)

  **Histogram conversion (exact; the probe's output is not this script's input).**
  The calibration probe emits counts per archetype under
  `per_archetype.<key>.tier_histogram` keyed `S`/`A`/`B`/`C`/`D`, while
  `--fractions-json` takes `{<key>: {"60": f, "76": f, "88": f}}`. Handing the probe
  artifact straight to the script reports **every archetype missing** and exits, so
  the rollout's mandatory measured-histogram receipt could never be produced and
  step 6 would block indefinitely. The conversion is cumulative, because each floor
  admits its own tier and every higher one:

  ```
  total      = S + A + B + C + D                      # per archetype
  f["88"]    = S / total
  f["76"]    = (S + A) / total
  f["60"]    = (S + A + B) / total
  ```

  So `f["60"] >= f["76"] >= f["88"]` by construction, and a conversion that produced
  anything else would be wrong on its face. PR4 owns a small committed converter
  (`scripts/dev/convert_calibration_histogram.py`) rather than a documented manual
  step: the fractions digest is a fail-closed gate input, so the transformation that
  produces it has to be reproducible and reviewable, and a by-hand JSON edit is
  neither. The converter asserts the cumulative ordering, that every exposed
  archetype key is present, and that each `total` matches the probe's recorded row
  count for that key; the capacity gate refuses a histogram whose digest does not
  match the converter's canonical output.

  **Capacity arithmetic (exact; PR4 implements this formula and nothing else).**
  All byte figures are integers; every division rounds up. `system_count` is the
  live count of eligible systems the build will write, read in the same gate run.

  ```
  projected_heap_bytes        = receipt.heap_bytes_per_row × system_count
  projected_fixed_index_bytes = receipt.primary_key_bytes_per_row × system_count
                              + receipt.weighted_index_bytes_per_row × system_count
  projected_tier_index_bytes  = receipt.tier_index_bytes_per_row_per_unit_fraction
                              × sigma_all × system_count
  projected_archetype_bytes   = heap + fixed_index + tier_index
  projected_search_bytes      = 0 if system_search is already written for this
                                generation, else 87_000_000_000
  projected_new_bytes         = projected_archetype_bytes + projected_search_bytes
  required_bytes              = ceil(1.15 × projected_new_bytes)
  reserve_bytes               = required_bytes − projected_new_bytes
  gate passes  iff  available_bytes >= required_bytes
  ```

  **Every per-row cost comes from the footprint receipt, not from a constant in
  this document (review round 18).** The gate already requires that receipt and
  verifies its provenance, so reading the measured numbers out of it costs
  nothing and removes a whole class of error: section 3.1 adds a persisted
  `completeness_ppm` column after these figures were measured, which alone moves
  the heap by 4 bytes per row (≈ 0.8 GB), and any further migration edit moves it
  again. A hard-coded 221.7 would have let the irreversible build pass near the
  free-space boundary while short of the reserve the gate claims to enforce — and
  it would have done so **silently**, because the receipt it checked would have
  been present and valid and simply not consulted for the one number that
  mattered. The gate refuses when the receipt does not carry all four per-row
  measurements, rather than falling back to a default.

  The figures below are therefore illustrative of the arithmetic, not inputs to
  it; the gate recomputes from its own receipt every time.

  **The reserve is 15 % of the projected new footprint — not of free space and
  not of the volume.** This is the only denominator that scales with the risk
  being covered. The reserve exists for three things, all proportional to what
  is being written: the WAL generated while writing it, the temporary sort space
  `CREATE INDEX` spills beyond `maintenance_work_mem` (indexes are built one at a
  time, so the peak is the largest single index, ~8 GB for the primary key), and
  the gap between these measured per-row figures and reality. Fifteen per cent of
  free space would hand a trivial build a huge reserve and a vast build a tiny
  one; fifteen per cent of the 1,948 GB volume is ~292 GB, which is the entire
  current free reading, so that gate could never pass and would be indistinguishable
  from a hard stop. Both were live readings of the same sentence, which is why it
  had to be pinned.

  Worked example at the synthetic `sigma_all = 1.54` and 198.5 M systems:
  heap 44.0 GB + fixed 16.2 GB + tier 15.2 GB = 75.4 GB archetype; with Search
  unwritten, 162.4 GB projected, 186.8 GB required, 24.4 GB reserve. At the
  gate's refusal ceiling `sigma_all = 4.0`: tier 39.6 GB, archetype 99.8 GB,
  186.8 GB projected, 214.8 GB required, 28.0 GB reserve. Against the 292 GB
  free reading both pass; neither figure is assumed by the gate, which recomputes
  from its own fresh readings. The formula reproduces the directly measured
  75.7 GB archetype total (section 3.4) to within 0.4 %, the difference being
  rounding in the 9.9 GB-per-unit-`sigma_all` coefficient; where the two differ
  the gate uses the formula, because the formula is what the live `sigma_all` and
  `system_count` feed.

  **Resuming an interrupted build charges only the remainder (review round 16).**
  Both builds are chunked and resumable over 198.5 M rows, and the formula above
  is written for a build that starts from nothing. On a restart it is wrong in a
  way that fails the *safe* operation: the fresh `df` reading already reflects
  every row written so far, so charging the full product again double-counts
  that progress. Near the `Σ_all = 4.0` ceiling the arithmetic actually inverts —
  a build interrupted at 90 % needs ~21 GB to finish but would be asked for
  214.8 GB of free space it has already spent, and the gate would refuse the
  restart, stranding insert-only rows that cannot be purged. The gate would then
  be the direct cause of the stranding it exists to prevent.

  So each projected term is scaled by what remains, from the build's own sealed
  chunk receipts — the same records the build uses to resume, so there is no
  second source of truth to drift:

  ```
  written_fraction   = sealed chunk rows for this product and generation / system_count
  remaining_fraction = 1 − written_fraction            # clamped to [0, 1]
  projected_archetype_bytes ×= remaining_fraction      # when resuming Archetype
  projected_search_bytes    ×= remaining_fraction      # when resuming Search
  ```

  The reserve is still 15 % of what is actually projected, so it shrinks with the
  remaining work rather than being charged in full on every restart. A resume is
  only recognised as a resume when the sealed receipts belong to **the same
  product, generation and manifest identity** as the build now starting; anything
  else is a fresh build and pays the full projection. `written_fraction` and
  `remaining_fraction` go in the receipt beside the other inputs, so a resume's
  smaller requirement is visible as a deliberate scaling rather than looking like
  a weaker gate.

  PR4 pins this formula in four tests. Two differ only in the `df` fixture: one
  with `available_bytes == required_bytes` (passes, proving the boundary is
  inclusive) and one with `available_bytes == required_bytes − 1` (refuses). A
  third asserts the receipt reports `projected_new_bytes`, `reserve_bytes`,
  `required_bytes`, `available_bytes`, `sigma_all`, `system_count`,
  `written_fraction` and `remaining_fraction`, so a reviewer can recompute the
  decision without rerunning the gate. The fourth is the resume case: sealed
  receipts for 90 % of the rows at `Σ_all = 4.0`, with free space far below the
  full requirement, must **pass** — and the same free space with receipts from a
  different manifest identity must **refuse**, because that is a fresh build
  wearing a resume's clothes.
- `scripts/operator/actions/v3-publish-derived-products.sh` (new: both products
  in one transaction via `publish_derived_product`; receipts timestamps, audits
  and view counts — **and fails closed on the deployed application before it
  publishes anything**, because publication is what makes the route live: it
  reads the running API container's image digest and compares it with the
  accepted-release attestation for the F2d release, and takes the expected
  `ranking_version`/`ranking_sha256` **from that attestation alone** —
  deliberately **not** from a Finder response envelope, because
  `_current_derived_generation()` answers 503 until the products are published,
  so no envelope exists at this point and a check that required one could never
  pass; and deliberately **not** from the served `/openapi.json`, because
  `RankingIdentity.ranking_version` and `ranking_sha256` are unconstrained `str`
  fields (`apps/api/src/models.py:378-379`), so the schema says only that they
  are strings. A check against it would be vacuous — it would pass against any
  image, including the old keyed-schema one, which is precisely the failure this
  gate exists to catch.

  **The digest is what carries the identity.** If the running container's digest
  equals the digest the F2d release was attested at, the code inside it is the
  code that was built and attested, and the attestation records the
  `ranking_version`/`ranking_sha256` that code computes. Identity therefore
  follows from digest equality and needs no runtime surface at all. This places
  one requirement on step 4: the accepted-release attestation for the F2d release
  **must record both concrete values**. If the existing attestation format has no
  field for them, step 4 adds it; the publish action refuses when the attestation
  carries no identity to compare, rather than treating a missing value as a match.

  `/openapi.json` keeps the job it can actually do — proving parameter **shape**,
  where the values are concrete in the schema: the `Literal[60, 76, 88]` floor
  appears as an enum and the combined `from`/`offset` bound as a maximum. It is
  checked for those and not consulted for identity.

  All comparisons refuse with distinct exit codes. The live envelope's identity is
  verified immediately afterwards, at step 10, when it exists — and that check is
  the one that closes the loop, because it compares a value the running code
  actually computed against the attested one. Without that check the SQL function
  would happily publish READY products while an out-of-order dispatch or an
  application rollback left the old keyed-schema image running. Tests cover the
  out-of-order case — products READY, old image digest — and the identity
  mismatch)
- `scripts/operator/actions/v3-archetype-plan-probe.sh` (new, read-only: builds
  the real picked page and count SQL through `build_ranked_query` /
  `build_count_query` for **all eight archetypes** at each of the three floors —
  24 pairs, not one key's three (review round 22): planner choices depend on each
  weighted-key column's own statistics and its partial index's selectivity, so the
  tested key can use its bounded partial while another chooses a sequential scan
  and sort over the 198.5-million-row table. Publication would pass and that
  user-selectable archetype would serve the unbounded plan. It runs
  `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` under `plan_cache_mode =
  force_generic_plan` with a 60 s statement timeout, and **asserts** from the
  plan that the window node is an `Index Only Scan` on the expected
  `(generation, <key>_weighted_e4 DESC, system_id64) WHERE <key>_score >= …`
  index with ≤ 10,001 actual rows, that the sort node's input is ≤ 10,000, and
  that the fetch node's rows are ≤ `page_size`; it writes nothing. This is the
  executable form of step 10's bounded-plan check —
  `v3-derived-lifecycle-status` reports lifecycle and footprint data and
  contains no `EXPLAIN`, so it cannot perform it.

  **The pre-commit probe is NOT this action (review round 22).** A standalone
  action opens its own connection and therefore cannot see the publisher's
  uncommitted `published_at` updates, so it cannot plan against the newly visible
  views before the one-way publication commits — the pre-commit check would have
  been impossible as specified. The publish action therefore executes the same
  generated `EXPLAIN` statements **on its own publication connection, inside its
  transaction**, after both updates and before commit, and rolls back on any
  mismatch. The SQL builders and the plan assertions are shared between the two so
  they cannot diverge; this read-only action remains the post-commit form for step
  10 and for ad-hoc checks.

  **Both probes require an explicit `VACUUM (ANALYZE)` first — not `ANALYZE` alone
  (review round 24).** Nothing in
  the rollout analyzes `v3_app.system_archetype` after its 198.5 million rows are
  inserted, and an `EXPLAIN` on default or stale statistics is not evidence about
  the production plan in either direction: it can reject a sound build on bad
  estimates, or — worse — pass, and then autovacuum analyzes **after** commit and
  the planner moves off the bounded plan with users already being served. `ANALYZE` alone is also not sufficient for the plan to be
  *achievable*: it collects statistics but does **not** mark heap pages
  all-visible, and after a bulk insert the visibility map is empty — so PostgreSQL
  costs the required `Index Only Scan` as though every row needed a heap visit and
  may plan something else, rejecting a sound rollout. Worse, an `Index Only Scan`
  that *is* chosen still performs a heap fetch per row while the visibility map is
  cold, and an assertion on node type and row count cannot tell the difference: the
  gate would certify "index-only" over up to 10,001 random heap reads.

  So the Archetype build step runs and receipts **`VACUUM (ANALYZE)`** on the
  completed table as its last action — the vacuum for the visibility map, the
  analyze for the statistics — and each probe asserts, before reading any plan,
  that `pg_stat_user_tables.last_analyze` **and** `last_vacuum` postdate the final
  insert. The plan assertions additionally require **`Heap Fetches: 0`** on the
  window node, which is the only assertion that tests what "index-only" is
  supposed to mean)
- `.github/workflows/chatgpt-ed-new-ops.yml` (allowlist entries)
- `docs/operations/v3-finder-production-rollout-state.md`,
  `docs/operations/v3-production-application-release.md` (revised F3 release
  gate, matching rollout step 5 — the release deploys **before any Finder product
  exists on the target generation**, so the gate requires **no Finder product rows
  on the pinned `parallel_v1` generation** — *not* a globally empty
  `v3_meta.derived_product`, because a READY `system_search` is deliberately
  retained on `opt1` with its purge deferred (ROADMAP lines 140-143), so a global
  emptiness check would block this deployment permanently: the exact current
  PUBLISHED generation key/UUID/sequence; the applied migration set
  `[014, 010, 011-rewritten, 013, 015]` with its exact ledger hashes; the new
  `ranking_version`/`ranking_sha256`; and built-image contracts — the bounded
  ranking route, the `Literal[60, 76, 88]` floor, the hard-filter rejection, the
  bounded `from`/`offset`, and the publication check in
  `_current_derived_generation()`. It must **not** require product READY,
  validation receipts, row counts, `published_at` or a publication audit: any of
  those would block step 5 and force the products to be built under the old
  deployed build, recreating exactly the unsafe interval the reorder removes.
  Product validation stays with the step 6/7 build actions' receipts;
  publication is verified by the publish action's own receipt (timestamps, audit
  rows, view counts) and by the step 9 post-go-live check, both specified in
  this PR)
- `deploy/v3-production/target-authority.json` (release-gate fields only; the
  migration identities were recut in PR1/PR2)
- tests: `tests/test_v3_system_search_production_operator.py`,
  `tests/test_v3_system_archetype_production_operator.py` (new),
  `tests/test_v3_product_publication_operator.py` (new),
  `tests/test_v3_production_application_deployment.py`

Focused checks: shell/action contract tests, including the capacity gate's four
refusals (missing or incomplete histogram, `Σ_all > 4.0`, a footprint receipt
that is synthetic or built from a different `011`, and insufficient free space)
each with its own exit code, and a passing case that records the arithmetic;
exact generation UUID/key/sequence,
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
9. **Yes/no: accept that the initial archetype ranking takes no hard filters —
   a picked request carrying `galaxy_region`, `max_distance_ly`, `has_elw`,
   `min_slots` or `max_contamination` is a 422, and the F4 UI disables those
   controls while an archetype is picked (section 6)?** The alternative is to
   apply them after the top-10,000 window, which would let a selective filter
   return an empty page while millions of matching systems exist — a quiet
   change in what “filter” means, which the product contract does not allow.
   Filtered archetype ranking needs a filter-first access path and is deferred.
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

### Review round 8 (2026-10-11)

1. **P1 — Add local-search identity wiring to PR1** → the shared identity model,
   the product-row lookup in `_current_derived_generation()`, the local-search
   envelope construction and assertions on both envelopes are named in PR1's file
   list (`apps/api/src/local_search.py` is PR1 work, not deferred to PR2).
2. **P1 — Keep publication out of the pre-go-live release gate** → PR4's gate
   requires READY + VERIFIED validation receipts, identities and row counts, and
   explicitly must not require `published_at` or a publication audit; publication
   is verified by the publish action's receipt and a post-go-live check.
3. **P2 — Make the claimed index-only ranked query executable** → the picked
   query is specified in four stages: index-only window (only the partial index's
   own columns), filter, page, then a bounded primary-key fetch of ≤ `page_size`
   rows for the response columns; plan assertions cover both nodes. INCLUDE
   payload on 24 partial indexes was considered and rejected.
4. **P1 — Run calibration before making its histogram a PR1 input** → PR1's
   footprint receipt uses the declared synthetic bell-shaped distribution and says
   so; the histogram-driven measurement moves to the pre-build capacity gate,
   after the governed probe runs, via a new `--fractions-json` input.
5. **P2 — Bound the explanation identity parameters** → `expected_generation_id`
   is a `uuid.UUID`, `expected_archetype_version` is
   `Query(None, min_length=1, max_length=128)` and `expected_manifest_sha256` is
   `Query(None, pattern=r'^[0-9a-f]{64}$')`; malformed or oversized values are
   422s from validation, with tests for each case.

### Review round 9 (2026-10-11)

1. **P1 — Apply hard filters before selecting the ranking window** → neither
   placement is acceptable, so the combination is rejected: PR1 makes a picked
   request carrying `galaxy_region`, `max_distance_ly`, `has_elw`, `min_slots` or
   `max_contamination` a 422 naming the parameters and the reason, Any mode keeps
   every filter, the F4 UI disables those controls while an archetype is picked,
   and `total`/`is_truncated` then mean exactly what they say. Filtered archetype
   ranking needs a filter-first access path and stays deferred. Recorded as owner
   question 9.
2. **P1 — Record the discrete `min_score` contract in the ROADMAP** → the
   ROADMAP now states `Literal[60, 76, 88]` with default 60 (not the continuous
   60–100 range), says why — each accepted value needs its own partial index, and
   70 or 100 are 422s — and records the hard-filter rejection in the same place.
3. **P1 — Account for all 24 indexes in the capacity ceiling** → the three
   predicates per key are nested, so section 3.3 now gives the cost as
   `44 GB heap + 16 GB (PK + weighted) + 9.9 GB × Σ_all`, where Σ_all is the sum
   of all 24 per-key tier fractions (1.54 synthetically ⇒ ≈ 76 GB), states the
   true absolute ceiling of ≈ 297 GB (not the rejected layout's 132 GB), and moves
   the capacity gate onto Σ_all with a stop above 4.0 and a named fallback (index
   fewer floors or fewer archetypes). The ROADMAP, capacity decision and
   rollout-state table carry the same arithmetic.
4. **P1 — Keep the old API fail-closed until the new release is deployed** →
   the rollout is reordered: the release deploys at step 5, **before** any product
   reaches READY, gated on the applied migration set, the ranking identity, the
   bounded route and the publication check — and on no Finder product rows **on
   the pinned target generation**, because none exist there (the retained `opt1`
   `system_search` must not block it). Steps 6–7 build Search then Archetype (the deployed build keeps
   answering 503 because they are unpublished), step 8 publishes both, step 9
   verifies from the live app. The reasoning — the deployed build gates only on
   READY, and post-`015` views hide unpublished rows — is written out under the
   table.

### Review round 10 (2026-10-11, from the F4 design's review)

1. **Outer `ORDER BY` is mandatory.** Stage 3 of the picked query restates
   `ORDER BY <key>_weighted_e4 DESC, system_id64 ASC` on the ≤ 10,000 survivors
   before pagination: an ordered index scan inside a subquery does not fix the
   final order and the planner may hash-join stage 2. The plan tests assert the
   sort node's input is ≤ 10,000 rows.
2. **The 10,000 offset ceiling is enforced at the API boundary.** PR1 bounds
   `POST /api/local/search`'s `from` to 0–10,000 as well as the rankings route's
   `offset`, so a direct caller cannot force `OFFSET 2000000000` against the
   ranking index once the products are published.

3. **PR4's gate carries no product prerequisites** (round 10 follow-up). The
   gate text now matches rollout step 5 exactly: generation identity, the applied
   migration set and hashes, the ranking identity and built-image contracts —
   and explicitly not product READY, validation receipts, row counts,
   `published_at` or publication audits, any of which would force the products to
   be built under the old deployed build and recreate the unsafe interval.

### Review round 11 (2026-10-11)

1. **P1 — Separate the identity check from the 503 probe** → a 503 carries no
   response envelope, so step 5 now verifies the two separately: the live request
   proves only the 503, while the ranking identity and the bounded-route
   contracts are proved from the release evidence (the gate's recorded
   `ranking_version`/`ranking_sha256`, the deployed image digest, the served
   `/openapi.json`), with the identity re-verified from a real envelope at
   step 9. The ROADMAP says the same.
2. **P2 — Enforce the result window on `from` plus `size`** → the local-search
   request model enforces the combined bound `from + size <= 10_000` (and
   `size >= 1`), like the rankings route, so `from=10000&size=500` cannot return
   rows beyond the window a capped total of 10,000 describes; tests pin
   `9_950+50` (ok), `10_000+1` (422) and `10_001` (422).
3. **P2 — Remove the post-window filter rule from the profile** →
   `PROFILE_SPEC` hashes the **hard-filter rejection rule** (the exact rejected
   parameter set, and that carrying one is a 422) and the
   `total = min(qualifying, 10000)` rule; the post-window filter rule is gone,
   since the route cannot execute it and hashing it would make `ranking_sha256`
   describe behaviour that does not exist. The identity test mutates the
   rejected-parameter set too.
4. **P1 — Wire the capacity gate into the Archetype action** → the gate is a
   fail-closed precondition of `v3-system-archetype.sh start`, with its own exit
   codes and receipt: it requires the recorded calibration histogram covering all
   eight keys and three floors, refuses `Σ_all > 4.0`, requires a footprint
   receipt whose `score_distribution_source` is `measured-histogram` and whose
   `011` hash matches the applied ledger entry, and takes a fresh read-only `df`
   of the data volume, refusing unless the measured archetype total plus 15 %
   working room fits. Four refusal tests plus a passing case that records the
   arithmetic.

### Review round 12 (2026-10-11)

1. **P1 — Bind capacity receipts to the governed histogram** → the footprint
   script now records `fractions_canonical`, `fractions_sha256` (SHA-256 of the
   canonical, key-sorted form) and `sigma_all`, and the gate requires that digest
   to equal the digest of the committed calibration evidence, so a stale or
   substituted JSON cannot pass as a measured histogram. Verified end to end.
2. **P1 — Run the capacity gate before building Search** → correct: Search is
   itself an irreversible 198.5 M-row insert-only write, so building it first and
   failing the gate afterwards would strand an unpublishable 87 GB product. The
   rollout gains an explicit **step 6, a combined Search + Archetype capacity
   gate**, which both build actions call as a fail-closed precondition.
3. **P1 — Preserve a schema-compatible rollback release** → PR4's authority
   records the F2d release as the **minimum schema-compatible image**, marks every
   earlier accepted image incompatible with the applied migration set, trims the
   deployment workflow's rollback target list to that image and later, and refuses
   promotion unless a compatible rollback artifact is recorded; a rollback below
   that line is an incident with its own plan, not a routine redeploy.
4. **P2 — Remove the remaining post-window filter stage** → stage 2 is now
   “Join (no filtering)”, for response columns only, stating that no hard filter
   appears anywhere in the query because such a request is rejected with 422
   before any SQL is built.
5. **P2 — Add an executable production-plan verification step** → new read-only
   `v3-archetype-plan-probe.sh` runs the real page and count SQL under
   `force_generic_plan` with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` and asserts
   the index-only window (≤ 10,001 rows), the ≤ 10,000-row sort input and the
   ≤ `page_size` fetch at both 50 and the route's maximum 500; step 10 names it instead of the lifecycle-status action,
   which contains no `EXPLAIN`.
6. **P1 — Gate publication on the deployed F2d release** → the publish action
   fails closed before publishing anything: it compares the running API
   container's image digest with the accepted-release attestation for the F2d
   release and confirms the live advertised `ranking_version`/`ranking_sha256`,
   with distinct exit codes and an out-of-order test (products READY, old image).
7. **P2 — Align calibration and release ordering with the ROADMAP** → one order
   now, in both documents: 4 deploy the release, 5 calibration probe (its
   histogram is the gate's input), 6 combined capacity gate, 7 Search build,
   8 Archetype build, 9 publish, 10 post-go-live verification.

### Review round 13 (2026-10-11)

1. **P1 — Verify identity without calling the unpublished Finder** → correct:
   the Finder answers 503 until publication, so the publish action's identity
   check comes from the accepted-release attestation and the served
   `/openapi.json` plus the running image digest, never from a response envelope.
   The live envelope is checked at step 10, once it exists.
2. **P1 — Align the capacity decision with the pre-Search gate** →
   `v3-finder-capacity-decision-2026-10-10.md` section 4 is updated to put the
   combined gate before the Search build, matching the controlling sequence.
3. **P2 — Separate the page and count window sizes** → the page query's window
   is `LIMIT 10000` (so the stage-3 sort receives at most 10,000 rows, as the plan
   assertion and the production probe require) and the count query's is
   `LIMIT 10001` (the sentinel). The plan assertions distinguish the two.
4. **P2 — Read the stored row in the explanation query** → the single round trip
   also reads the generation-pinned wide `system_archetype` row, so the mandated
   recomputed-vs-stored comparison happens on one consistent snapshot; a missing
   row is a 404, and a test seeds a divergent stored row and asserts the
   fail-closed response.

5. **Any-mode count sentinel** (round 13 follow-up, from the F4 design's review).
   PR1 also gives the galaxy-wide count query the 10,001st-row sentinel
   (`LIMIT cap + 1`), so `total_is_capped` means “more than 10,000 exist” rather
   than “at least 10,000 were counted”. Without it a search with exactly 10,000
   matches raises the same flag as one with a million, and the F4 UI cannot
   honestly write “10,000+”. Tests pin exactly 10,000 (false) and 10,001 (true).

### Review round 14 (2026-10-11)

1. **P2 — Correct the stale Any-mode count claim** → the ranking section no
   longer says the galaxy-wide count is “capped the same way”: it states that the
   live path is bounded but **not** sentinel-based (`cap=10000` with
   `total_is_capped` on `>= 10000`) and that PR1 changes it to `LIMIT cap + 1`
   with `total_is_capped = count > cap`, so Any mode is not left unchanged.
2. **P2 — Keep the fetch bound consistent with the 500-row API limit** → the
   stage-4 bound is `page_size` up to the route's **500**, not 50; the plan
   assertions and the production probe exercise both 50 and 500 so a legal large
   page is neither truncated nor left unverified, and the INCLUDE-payload
   rejection is restated against the real bound.
3. **P1 — Remove the pre-publication live-identity requirement** → the ROADMAP's
   step 9′ now requires the pre-publication check to use the accepted-release
   attestation, the running image digest and the served OpenAPI contract, with the
   **response** identity verified only after publication, matching the design.

### Review round 15 (2026-10-11)

1. **P1 — Define the denominator for the capacity reserve** → correct, and the
   ambiguity was load-bearing: at `Σ_all = 4.0`, 15 % of the ~187 GB new
   footprint is ~28 GB, 15 % of the 292 GB free reading is ~44 GB, and 15 % of
   the 1,948 GB volume is ~292 GB — the last of which is the entire free space,
   so that reading would make the gate unpassable and indistinguishable from a
   hard stop. Section 10's PR4 row now pins the exact formula: the reserve is
   **15 % of the projected new footprint**, the only denominator that scales with
   the risk it covers (WAL written during the build, `CREATE INDEX` temp spill
   beyond `maintenance_work_mem`, and the gap between the measured per-row
   figures and reality). `required_bytes = ceil(1.15 × projected_new_bytes)`,
   with `projected_new_bytes` computed from the measured per-row constants, the
   live `system_count` and the calibrated `sigma_all`, plus 87 GB for Search when
   it is not yet written. Two tests differing only in the `df` fixture pin the
   boundary at `available == required` (passes) and `available == required − 1`
   (refuses); a third pins the receipt's reported inputs so the decision can be
   recomputed without rerunning the gate. The worked examples were checked
   arithmetically and reproduce the directly measured 75.7 GB archetype total to
   within 0.4 %.
2. **P1 — Do not require OpenAPI to prove the ranking identity** → correct, and
   the check was worse than merely weak: `RankingIdentity.ranking_version` and
   `ranking_sha256` are unconstrained `str` (`apps/api/src/models.py:378-379`),
   so an OpenAPI comparison would have passed against **any** image, including
   the old keyed-schema one — exactly the failure the gate exists to catch. Took
   the first of the two offered options. The deployed image digest now carries
   the identity on its own: if the digest matches the one the F2d release was
   attested at, the attested `ranking_version`/`ranking_sha256` are the values
   that code computes. That places one requirement on step 4, now recorded — the
   accepted-release attestation **must record both concrete values**, and the
   publish action refuses when the attestation carries no identity rather than
   treating a missing value as a match. `/openapi.json` keeps the job it can do,
   proving parameter shape, where the values are concrete in the schema (the
   `Literal[60, 76, 88]` enum, the combined `from`/`offset` maximum). Both
   normative sites are corrected (section 10 step 4, and the publish action).
   Rounds 12.1 and 13.1 above described the superseded version.
3. **P2 — Restate the ranking order after the fetch join** → correct. Stage 3's
   `ORDER BY` orders stage 3's output and does not survive stage 4's join, so a
   hash or nested-loop fetch plan could return the right 50 systems in an
   arbitrary sequence. That is the worst shape this bug could take: every row
   correct, only the ranking wrong, and no row-set assertion would see it. Stage
   4 now requires the outermost `SELECT` to repeat `ORDER BY <key>_weighted_e4
   DESC, system_id64 ASC` over the ≤ `page_size` materialized rows, and — taking
   the second half of the finding, which matters as much as the first — the tests
   now assert the **returned row order** on a fixture seeded with deliberate
   ties, plus that two adjacent pages concatenate into one correctly ordered
   sequence with nothing repeated or skipped. Bounding the sort node's input
   proves the query is cheap; only the row order proves it is right.

### Review round 16 (2026-10-11)

Seven findings, all accepted. Three of them (1, 4, 6) are the same class of
error on my part: treating a check that *can* be written as a check that *proves*
the thing it names.

1. **P1 — Account for partial rows when re-running the capacity gate** → correct,
   and the arithmetic inverts near the ceiling: a build interrupted at 90 % needs
   ~21 GB to finish but the full-cost formula would demand 214.8 GB of space it
   has already spent, so the gate would refuse the restart and strand the very
   insert-only rows it exists to protect. Each projected term is now scaled by
   `remaining_fraction`, computed from the build's **own sealed chunk receipts** —
   the same records the resume uses, so there is no second source of truth — and
   a resume counts as a resume only when those receipts carry the same product,
   generation and manifest identity. Both fractions go in the receipt so a
   smaller requirement reads as deliberate scaling, not a weakened gate. A fourth
   PR4 test pins it: 90 % sealed at `Σ_all = 4.0` with low free space passes, and
   the same free space with receipts from a different manifest identity refuses.
2. **P1 — Keep future generation publication atomic with Finder visibility** →
   correct, and the contract reference is the right one. This rollout is safe
   because the pointer already names `parallel_v1` and no Finder products exist
   on it, so nothing becomes invisible. A **later** promotion is a different
   thing: the flip retires the visible generation at commit, and unpublished
   incoming products mean the views hide their rows and the Finder answers 503
   until a second action lands — down, having been up a moment earlier, and
   avoidably, since the ordering was only a choice. `publish_derived_generation`
   now refuses the flip unless, at commit, every registered Finder product on
   the incoming generation is published **or** had no published counterpart on
   the outgoing one. That single rule covers the first launch (second clause) and
   every later promotion (first clause) with no special case, and it lives in the
   function beside the READY/VERIFIED check so no caller can skip it.
3. **P1 — Remove OpenAPI from the ranking-identity check** → correct, and this is
   the finding I should have anticipated when fixing round 15.2: I corrected the
   design and left the controlling ROADMAP saying the superseded thing, which is
   worse than not having fixed it, because the higher authority would have won.
   ROADMAP steps 4′ and 9′ now take the identity from the digest-bound
   accepted-release attestation alone.
4. **P2 — Verify the combined pagination bound outside OpenAPI** → correct, and
   the same mistake as 3 in a different place: JSON Schema cannot relate two
   fields, so `offset + limit <= 10000` is not expressible and an image that
   dropped the validator would publish a byte-identical schema and pass. The
   combined bounds are now proved by a behavioural probe against the deployed
   image — which the 503 does not obstruct, because request validation raises 422
   before the generation is consulted: `offset=9999&limit=1` accepted,
   `offset=9999&limit=2` rejected. OpenAPI keeps the individual maxima and the
   floor enum, which its schema does state concretely. Fixed in the design and
   the ROADMAP together this time.
5. **P1 — Pin the identity check and explanation read to one snapshot** → correct;
   making the data query internally consistent closed the wrong window. The
   window is *between* the check and the query, so a publication landing there
   would return an explanation computed from the new generation under the old
   identity — a 200 carrying exactly the confusion the 409 exists to prevent. The
   identity lookup, the comparison and the generation-pinned read now share one
   read-only `REPEATABLE READ` transaction, as the rankings path already does. A
   test commits a publication from a second connection while the request is
   suspended between the two statements and asserts the answer comes from exactly
   one snapshot: the old explanation or a 409, never a mixture.
6. **P1 — Gate builds on an approved, matching coefficient decision** → correct
   on both halves, and the second half is what makes the first worth anything. A
   complete in-bounds histogram proves the build would *fit*, not that its logic
   was *approved*: a review that rejected the coefficients leaves exactly that
   evidence behind. The committed evidence now carries an explicit
   `coefficient_decision: accepted` (anything else, absent included, refuses),
   **and** the probe's `code_identity` and coefficient digest must equal the
   manifest the builder registers — without which an approved probe could still
   authorize a build whose real tier fractions were never capacity-tested.
7. **P2 — Specify one exact weighted-key rounding rule** → correct, and this one
   would have been very hard to find later: Python's `round` is ties-to-even and
   PostgreSQL `numeric` rounds ties away from zero, so the builder and the exact
   validator could order tied systems differently while every version string
   matched. The definition is now closed in integers with no float anywhere:
   `(score × confidence_ppm × completeness_ppm + 50_000_000) // 100_000_000`. The
   divisor follows from the units rather than being chosen. Checked rather than
   asserted: the numerator peaks at 1e14 (exact in `bigint`), the key at 1e6
   (inside `integer`), and over 500,000 random triples the integer rule agrees
   with the floating-point product at **every** non-tie input — so it changes
   nothing except making ties decidable. The worked tie in the spec
   (`score=1, confidence_ppm=50, completeness_ppm=1_000_000`) is a true half where
   Python yields 0 and PostgreSQL yields 1; the rule yields 1. Half-boundary
   vectors are added to the builder, validator and ranking-identity tests.

### Review round 17 (2026-10-11)

1. **P1 — Require counterparts for every published outgoing product** → correct,
   and my round-16 rule was quantified over the wrong set. Over *incoming
   registrations*, a generation that registers and publishes only `system_search`
   satisfies it vacuously: `system_archetype` is simply absent, so there is no
   registered product to find fault with, and the flip commits while the Finder,
   which needs both, answers 503. The rule is now anchored to what is visible now
   and must not stop being visible — the **outgoing published set**: every Finder
   product published on the outgoing generation must have a published counterpart
   on the incoming one. A missing counterpart and an unpublished counterpart
   become the same violation, which is right, because in both cases something the
   Finder is serving stops being served. The first launch still passes (the
   outgoing generation publishes no Finder products), so it remains one rule with
   no dated exemption. A test now covers the search-only promotion specifically —
   the case the previous rule let through.
2. **P1 — Use an exact integer completeness source end to end** → correct on both
   counts, and the first is the more embarrassing: I specified an exact
   `completeness_ppm` input without checking that it existed.
   `system_search.completeness` is `double precision`
   (`004_v3_search_spatial_clusters.sql:41`), so reading it would have put a float
   straight back into a definition whose purpose is to have none. The exact source
   does exist and the builder already reads it — `evidence_completeness` is an
   integer array in 1e-4 units that the builder divides by `10000.0`
   (`scripts/v3_system_archetype.py:277`) — so `completeness_ppm =
   min(evidence_completeness) × 100`, taken **before** any division, which is
   exactly the source suggested. Verified: it lands in `0..1_000_000`, the
   numerator peaks at 1e14 (exact in `bigint`) and the key at 1e6 (inside
   `integer`). `completeness_ppm` is also now **persisted on the wide row**, so
   the builder, validator and explanation route read one stored integer instead of
   each deriving their own; that costs 4 bytes per row (≈ 0.8 GB), and the
   capacity gate's 221.7 B/row constant must be re-measured against the final
   migration text before the build, as section 8 already requires. On the second
   count: the manifest definition string and the validator check both still
   carried floating `round(...)` forms, which would have reintroduced the exact
   ambiguity round 16 removed. Both now carry the integer expression verbatim, and
   the validator additionally re-derives the stored `completeness_ppm` from the
   rating vector and fails closed if the two disagree.
3. **P1 — Scope the empty-product gate to the target generation** → correct, and
   the consequence is that the gate could never have passed: a READY
   `system_search` is deliberately retained on `opt1` with its purge deferred
   (ROADMAP lines 140-143), so a literal global emptiness check against
   `v3_meta.derived_product` would have blocked the very deployment it authorizes,
   permanently. Both the design and the controlling ROADMAP now require zero
   Finder product rows **on the pinned `parallel_v1` target generation** only, and
   say why, so retained products elsewhere cannot be mistaken for a blocker.

Swept rather than reviewed — three further instances of the same two errors,
fixed in the same commit:

4. The **ROADMAP** still said "no product rows" (finding 3 in the
   higher-authority document, which would have won). Fixed there too; round 16
   taught me to check the ROADMAP in the same pass rather than the round after.
5. The **`011` DDL comment** still documented the key as `round(score ×
   confidence × completeness × 10,000)`. A comment next to the column is where an
   implementer will actually look, so it now carries the integer expression and an
   explicit "never `round()`".
6. The **`_confidence_ppm` conversion** has the same tie ambiguity, and no review
   round had reached it: `round(confidence * 1_000_000)` with `round()`'s default
   mode. Unlike completeness there is no integer source, because model confidence
   is genuinely a float, so instead of inventing one the rule is pinned to a
   single place — `floor(confidence * 1_000_000 + 0.5)`, round-half-up and named
   explicitly, computed by a shared helper that the validator **calls** rather
   than reimplements, and never recomputed in SQL.

### Review round 18 (2026-10-11)

Six findings, all accepted, and all the same failure on my part: a decision made
in one section and not carried to the places that depend on it. Round 17 added
three such decisions (the persisted `completeness_ppm`, the integer key rule, the
half-up confidence helper) and round 31 on PR #801 added a fourth (the
generation-free model digest); each of those is where one of these six landed. So
after fixing the six I swept the normative body for **every** mention of each
decision rather than only the cited lines, and found two more (below).

1. **P1 — Add `completeness_ppm` to the wide-table DDL** → correct, and it was the
   most basic kind of gap: I wrote that the column is persisted and that the
   validator recomputes and compares it, and never added it to the `CREATE TABLE`.
   An implementer following the normative DDL would have had nothing to store the
   value in. Added with its range check, a comment naming the exact source, and
   its migration tests.
2. **P1 — Derive the capacity heap cost from the final measurement** → correct, and
   the silence is what makes it serious: the gate checks the footprint receipt's
   provenance and then ignored its numbers in favour of a hard-coded 221.7 B/row,
   so near the free-space boundary the irreversible build could pass while short
   of the reserve the gate claims to enforce, with a valid receipt sitting right
   there unconsulted. **Every** per-row cost now comes from the receipt — heap,
   primary key, weighted index and the tier coefficient — and the gate refuses
   when the receipt does not carry all four rather than falling back to a default.
   The figures in the document are now explicitly illustrative of the arithmetic
   rather than inputs to it, which also means a future migration edit cannot leave
   a stale constant behind.
3. **P2 — Carry `archetype_model_sha256` through PR1's envelopes** → correct.
   Section 5.1 added the digest and required it in `ranking_provenance`, but the
   implementation list, both envelope constructors and the generated-client entry
   still named only two fields — so the field would have existed in the design and
   never reached the wire, and F4's cross-generation comparison would have had
   nothing to compare on. All three digests now go through the shared model, both
   envelopes, the regenerated clients and the identity tests, with a note on why
   both hashes are needed: the manifest digest cannot answer "same model?" because
   it embeds generation identity, and the model digest cannot answer "same build?"
   because it deliberately does not.
4. **P1 — Scope the unpublished-generation success test** → correct, and this is
   the one that would have done real damage: the test as written required
   `publish_derived_generation` to **succeed** whenever registered products are
   READY but unpublished, which is section 7.4's forbidden case stated as an
   acceptance criterion. An implementer satisfying the test suite would have built
   the outage. Case 8 is now scoped to an empty outgoing published set — the
   first-launch case — and a new case 8b requires refusal when any product
   published on the outgoing generation lacks a published incoming counterpart,
   whether unpublished or not registered at all.
5. **P2 — Hash the exact integer key formula in `PROFILE_SPEC`** → correct, and
   `PROFILE_SPEC` is precisely the wrong place to leave it ambiguous, because it
   is the **hashed** authority: two implementations could order boundary rows
   differently while claiming the same `ranking_sha256`, which is the one
   guarantee that hash exists to give. The exact integer expression is now hashed,
   with the reason recorded next to it.
6. **P2 — Use the shared half-up helper in validation** → correct, and the
   direction of the failure is the notable part: a row built **correctly** by the
   half-up builder would be **rejected** by a ties-to-even validator, so the
   immutable product could never reach READY — a build that fails with no bad data
   to point at, on one row in a few hundred million. The validator now **calls**
   the shared helper rather than restating the expression, which is the only form
   of this fix that cannot drift, and its tests carry a half-boundary confidence
   vector.

Swept rather than reviewed:

7. The Search dependency's stated reason was now false — "the stored ranking keys
   depend on `system_search.completeness`" — since round 17 moved completeness to
   the rating vector. The dependency itself still holds for different reasons (the
   builder reads `system_search` confidence for `weighted_potential`, and the
   rankings envelope joins it for response columns), so the requirement stands
   with a corrected justification rather than being dropped. A requirement resting
   on a reason that no longer applies is one refactor away from being deleted as
   dead weight.
8. Section 3.1 still told the reader the capacity gate's "221.7 B/row heap
   constant must be re-measured", which finding 2 had just made meaningless. It
   now says what actually has to happen: the receipt must be produced against the
   final migration text including the new column.

### Review round 19 (2026-10-11)

1. **P1 — Cast the weighted-key numerator to bigint** → correct, and it is a hard
   failure rather than a nuance. The declared operands are `smallint` and
   `integer`, so PostgreSQL evaluates `smallint × integer × integer` as
   **`integer`** and overflows at entirely ordinary values: `100 × 1_000_000 ×
   1_000_000` is 1e14 against an `integer` ceiling of 2.1e9. The "exact in
   `bigint`" range I had verified is the range of the *result*, which the
   expression would never reach — validation would raise `integer out of range`,
   no correct product row could pass, and the immutable build could never reach
   READY. I had checked the arithmetic in Python, where integers are unbounded,
   and carried the conclusion into SQL where it does not hold.
   The spec now carries the exact casted expression
   (`(<key>_score::bigint * <key>_confidence_ppm * completeness_ppm + 50000000) /
   100000000`) for the validator and the boundary tests to use verbatim, notes
   that one cast promotes the whole chain, and records that SQL's truncating
   division equals the floor here because every operand is non-negative.
2. **P2 — Exclude build code from the model-only digest** → correct, and your
   suggested division is better than either of my two attempts. Round 31 included
   the broad `code_sha256`, which made a builder fix or a storage-only migration
   change suppress the comparison. Round 32 then removed **all** source hashes,
   which was the opposite error: the digest rested entirely on declared constants,
   so a change to the model's *logic* that left its constants alone would not show
   up at all.
   Hashing the **shared model file only** is the division that matches the field's
   meaning. `code_identity()` covers three files — builder, model, migration — and
   the model file owns scoring while the builder owns iteration, batching and
   storage and the migration owns layout. So a change to how scores are computed
   always moves the digest, and a change to how they are written never does. The
   broad `code_sha256` stays in `archetype_manifest_sha256`, where identifying one
   exact build is the point. This also retires most of the "declaration, not proof"
   caveat round 32 had to add.
3. **P1 — Scope the release gate to the target generation** → correct, and this is
   the third place the same scoping had to reach. Round 17 fixed the step-4 table
   row and the ROADMAP; the PR4 implementation list and the rollout-reordering
   paragraph still said "no product rows at all", and the implementation list is
   what someone writing the gate would read. Both now require zero Finder product
   rows **on the pinned `parallel_v1` generation**, each with the reason attached
   (the retained `opt1` `system_search`, purge deferred), because the bare scoping
   without its reason is what keeps getting simplified back to a global check.

### Review round 20 (2026-10-11)

1. **P2 — Replace the ambiguous weighted-key rounding rule** → correct, in a third
   document. Round 16 fixed the design, round 19 the DDL comment and the manifest,
   and `docs/operations/v3-finder-capacity-decision-2026-10-10.md` still defined the
   key with `round(...)`. That document is the owner-facing decision record, so an
   implementer reading it would have built rows the exact validator rejects. It now
   carries the integer expression, the Python-versus-PostgreSQL tie difference, and
   the `bigint` cast — all three, because the short form is what keeps coming back.
2. **P2 — Verify the model digest after go-live** → correct. Step 10 checked two of
   the three archetype identity values, and the omitted one is the only one F4 uses
   to decide whether scores from different generations may be compared. A response
   that omitted or mis-populated exactly that field would have passed live
   verification and silently disabled the comparison — no error, just a feature that
   never fires. Step 10 now compares all three.
3. **P1 — Convert the probe histogram before measurement** → correct, and this one
   **blocks the rollout** as written. The probe emits counts under
   `per_archetype.<key>.tier_histogram` keyed `S`/`A`/`B`/`C`/`D`;
   `--fractions-json` takes `{<key>: {"60": f, "76": f, "88": f}}`. Handing the probe
   artifact to the script reports every archetype missing and exits, so the mandatory
   measured-histogram receipt could never be produced and step 6 would block
   indefinitely — a prescribed command that cannot run, sitting on the critical path.
   The conversion is now specified exactly, and it is **cumulative** because each
   floor admits its own tier and every higher one: `f["88"] = S/total`,
   `f["76"] = (S+A)/total`, `f["60"] = (S+A+B)/total`, so
   `f["60"] >= f["76"] >= f["88"]` by construction. PR4 owns a committed converter
   rather than a documented manual step, deliberately: the fractions digest is a
   fail-closed gate input, so the transformation producing it must be reproducible
   and reviewable, and a by-hand JSON edit is neither. The converter asserts the
   cumulative ordering, that every exposed key is present, and that each total
   matches the probe's recorded row count.
4. **P1 — Remove the superseded fresh-generation instructions** → correct, and this
   is the most serious of the four because of **where** it is: the highest-authority
   programme document continued, immediately after the replacement sequence, with
   the pre-wide-row route — "the only executable path", build actions in the old
   steps 5 and 7, and an owner choice before step 4 between accepting a fresh
   Ratings V4 generation (1.59 billion keyed archetype rows plus a separate summary
   table) or designing a purge path first. An operator following the authority chain
   in order would have hit the current sequence and then been told to do something
   incompatible with it, by the same document.
   That block is now explicitly marked superseded, with each stale instruction named
   and corrected rather than silently deleted: both products attach to the published
   `parallel_v1` generation, so no fresh generation is built and no purge decision
   gates step 4; the wide row is one row per system with the summary as a view, so
   the 1.59-billion and separate-summary figures describe nothing that will be
   written; and capacity is settled by the fail-closed combined gate rather than by
   an owner choice. The parts that remain true — the insert-only triggers, the
   absence of a governed purge path — are kept and marked as no longer being
   prerequisites, with disk reclamation tracked against the read-only inventory
   instead.

### Review round 21 (2026-10-11)

1. **P1 — Compare model outputs only when source vectors match** → correct, and it
   is the same defect the F4 design had in its round 34, on this side of the
   contract: I fixed it there and left it here. A later generation may be rebuilt
   from a different canonical generation, so a system present in both can
   legitimately carry different rating vectors or completeness and therefore a
   different `<key>_weighted_e4` under an identical model. Requiring equal keys
   because the digests match would reject that valid build and **block
   publication** — failing on exactly the data refresh the generation-free digest
   exists to permit.
   The assertion is now against a committed **frozen input fixture** of
   `(score, confidence_ppm, completeness_ppm)` vectors including the half
   boundaries, which isolates the model from the data it is applied to. Of your two
   options I took the fixture rather than restricting comparison to
   byte-identical source vectors, because the fixture is deterministic and
   reviewable while "systems whose complete source vectors are byte-identical" is a
   set that could be empty on any given pair of generations — a check that silently
   verifies nothing.
2. **P2 — Regenerate the evidence with the checked-in script** → correct, and I
   could not do the first half: the disposable PostgreSQL 18 instance this was
   measured on no longer exists, so I cannot rerun it, and I would rather say that
   than commit a figure I did not produce.
   I took the second option and made the provenance verifiable rather than merely
   asserted. The artifact's fields are exactly those emitted by the script at
   **`6f9f79e`**; `fractions_canonical`, `fractions_sha256` and `sigma_all` were
   added at `c0e49fa` (round 12), which is why the current revision could not have
   produced it. That commit is now recorded in the artifact itself along with the
   reason.
   Recording it surfaced something worth stating outright, which is now also in the
   artifact: this file is **not** a capacity-gate input and must never be
   substituted for one. Its `score_distribution_source` is
   `declared-synthetic-bell` with no fractions digest, so the gate would refuse it.
   It is layout-comparison evidence for section 3.4, and the gate's input is the
   pre-build receipt measured against the final `011` with the real histogram.
3. **P1 — Gate publication on the production plan before commit** → correct, and
   this is the best finding on this PR. The step as written made its **first
   assertion against production statistics at the one moment where failing it could
   not be undone**: after `published_at` had committed, a one-way transition with no
   governed path to clear it. Disposable-fixture plans passing is not evidence about
   production statistics or view expansion, so users would have been exposed
   immediately on any divergence, with no way back.
   Your mechanism is what makes the fix available: the transaction **can see its own
   newly visible rows**, so the picked query can be planned against the real
   statistics and the expanded views after both updates and before commit, while the
   change is still reversible. Any plan mismatch now rolls the publication back. The
   post-commit probe at step 10 is kept, but as confirmation that the committed
   state still plans correctly rather than as the first check.

### Review round 22 (2026-10-11)

Six findings, all accepted. Three of them (1, 5 and the ROADMAP half of 2) are the
same lesson I have now been taught several times: a fix recorded only in the design
does not bind, because the ROADMAP outranks it.

1. **P1 — Gate the build on the approved probe identity** → correct. Round 16 added
   `coefficient_decision: accepted` and the probe-identity match to the design and
   not to the ROADMAP, which still gated on histogram completeness, digest, size and
   disk space alone. Since the ROADMAP wins, an implementation following it could
   still launch the immutable, non-purgeable build from a **rejected** probe, or from
   an approved probe whose scoring logic differs from the manifest the builder
   registers. Both checks are now in step 6′, with the cumulative histogram
   conversion alongside them, since that is the other thing step 6′ cannot be
   executed without.
2. **P1 — Run the plan probe on the publication connection** → correct, and the
   pre-commit check was **impossible as specified**. Round 21 said the probe runs
   inside the publication transaction; the implementation plan still described a
   standalone read-only action, which opens its own connection and therefore cannot
   see the publisher's uncommitted `published_at` updates. So the one thing the
   round-21 fix existed for — planning against the newly visible views while the
   change is still reversible — could not have happened. The publish action now
   executes the same generated `EXPLAIN` statements on its **own** connection inside
   its transaction, sharing the SQL builders and plan assertions with the read-only
   action so the two cannot diverge; that action remains the post-commit form.
3. **P1 — Validate model identity against frozen inputs** → correct. I fixed the
   prose in section 5.1 and left the implementation list asserting that equal digests
   must produce identical keys for a shared sample of systems **across generations** —
   which is the defect, stated as an implementation requirement. A later generation
   rebuilt from different canonical data can legitimately give a system a different
   key under an identical model, so the assertion would reject a valid rebuild and
   block READY. The list now states what it does assert (digest stability) and
   explicitly that key equality is against the frozen fixture, not across
   generations.
4. **P1 — Probe every archetype's production plan** → correct, and the same defect as
   the F4 scale receipt's (its round 35), here on the production gate where it matters
   more. One archetype at three floors tests 3 of 24 pairs, and planner choices depend
   on each weighted-key column's own statistics and its partial index's selectivity —
   so the tested key can use its bounded partial while another chooses a sequential
   scan and sort over 198.5 million rows. Publication would pass, and that
   user-selectable archetype would serve the unbounded plan. All eight keys at all
   three floors, before commit.
5. **P1 — Keep implementation blocked on unresolved owner decisions** → correct, and
   the wording was the problem: having recorded answers to questions 1 and 5, the
   ROADMAP said "this prerequisite is satisfied" — which reads as *the* prerequisite.
   Questions 2, 3, 4, 7 and 8 remain open and govern the persisted confidence
   representation, model ownership, the explanation endpoint, PR sequencing and atomic
   publication. Following that sentence, implementations of choices the owner has not
   accepted could reach `main`, authorized by the controlling document. It now names
   which prerequisite is satisfied, lists what is still open, and states that the code
   PRs encoding any unresolved choice may not merge until the answer is recorded.
   (Question 9 is answered: the 422 contract plus the owner's stated wish for filtered
   archetypes as a later increment.)
6. **P1 — Analyze the completed table before probing its plans** → correct, and I had
   not thought about statistics at all. Nothing analyzes `system_archetype` after its
   198.5 million rows are inserted, and an `EXPLAIN` on default or stale statistics is
   not evidence about the production plan **in either direction**: it can reject a
   sound build on bad estimates, or — the dangerous case — pass, and then autovacuum
   analyzes after commit and the planner moves off the bounded plan with users already
   being served. The gate would have certified a plan that was about to change. The
   Archetype build now runs and receipts `ANALYZE` on the completed table as its last
   action, and both probes assert `last_analyze` is later than the final insert before
   reading any plan.

### Review round 23 (2026-10-11)

1. **P1 — Require the plan probe before publication commits** → correct, and the
   same design-only mistake for the fourth time on this PR: rounds 21 and 22 built
   the pre-commit probe into the design and left the controlling ROADMAP directing
   the action to publish straight after the image and identity checks. Following the
   higher authority literally, the one-way `published_at` transition commits with
   the production plan never validated — and an archetype whose statistics select a
   sequential scan over 198.5 million rows goes live with no way back.
   ROADMAP step 9′ now carries the whole requirement: the publisher's **own**
   connection, inside the transaction, after both updates and before commit, **all
   eight archetypes at all three floors**, with `ANALYZE` receipted by the build
   step and `last_analyze` asserted to postdate the final insert. I put the reasons
   in alongside, because a bare instruction to run a probe is what gets simplified
   back to "publish after the identity checks".
2. **P2 — Drop the parameterized floor from the count query** → correct, and round
   22's fix reached the page window and not the count window. `<key>_score` is not
   in the partial index, so a parameterized `<key>_score >= $n` forces a heap fetch
   for each of up to **10,001** candidate rows — and it would fail the `Index Only
   Scan` assertion the publication gate now makes, so the gate I have just
   strengthened would have refused the implementation the design specified. The
   count window takes the server-selected literal alone, for exactly the reason the
   page window does.

### Review round 24 (2026-10-11)

1. **P1 — Restore the unresolved atomic-publication decision** → correct, and the
   cause is a numbering collision I walked straight into: the **capacity decision**
   and this design number their owner questions independently. The owner answered
   capacity-decision question 6 (the score-index layout) yes, and I carried that
   "6 is answered" into the ROADMAP's list of design questions — where 6 is **atomic
   publication**, which is open. The result was the worst possible pair of errors:
   the one-transaction publication PR free to merge with no owner answer, while
   question 8 (no purge), an **already accepted** decision, was listed as blocking.
   The ROADMAP now lists 2, 3, 4, 6 and 7 as open, records 1, 5, 8 and 9 as answered,
   and states explicitly that design question 6 is not the capacity decision's
   question 6 — because the collision will otherwise be made again.
2. **P1 — Vacuum the completed table before requiring index-only plans** → correct,
   and round 22's `ANALYZE` was the wrong half of the fix. `ANALYZE` collects
   statistics but does **not** mark heap pages all-visible, and after a bulk insert
   the visibility map is empty. So two things follow, and I had seen neither: the
   planner costs the required `Index Only Scan` as though every row needed a heap
   visit and may plan something else, **rejecting a sound rollout**; and an `Index
   Only Scan` that is chosen anyway still performs a heap fetch per row, which an
   assertion on node type and row count cannot detect — the gate would have
   certified "index-only" over up to 10,001 random heap reads.
   The build step now receipts **`VACUUM (ANALYZE)`**, each probe asserts both
   `last_vacuum` and `last_analyze` postdate the final insert, and the plan
   assertions require **`Heap Fetches: 0`** — which is the only one of these
   assertions that tests what "index-only" actually means.
3. **P1 — Read completeness from the actual rating-vector column** → correct, and I
   took the name from the builder's own vocabulary without checking the schema.
   `system_rating_vector` has `completeness smallint[]`
   (`003_ratings_v4_derived.sql:120`); `evidence_completeness` exists only as a
   `double precision` alias in the unnested `system_economy_rating` view, where it
   is already `completeness[i] / 10000`
   (`003_ratings_v4_derived.sql:223`). So the instruction would either raise an
   undefined-column error — preventing the immutable product from reaching READY —
   or pull in the float the whole integer rule exists to remove. Both normative
   sites and the DDL comment now name `min(system_rating_vector.completeness) × 100`.
4. **P1 — Keep storage-only changes out of the model digest** → correct, and this is
   the fourth iteration of this field's scope, each one narrowing it for a reason the
   previous had missed. Your argument is the sharpest yet because it is
   self-referential: the model file also defines `ARCHETYPE_VERSION`, and **this
   design bumps it to `v3-archetype-4` solely because the persisted storage shape
   changed**. So hashing the whole file would have broken the field on this design's
   own version bump — plus any explanation-only edit or non-semantic refactor, while
   the weighted scores stayed comparable.
   The digest now covers a **named set of members** of the model file rather than the
   file: coefficients, anchors, key order, tier thresholds, the `_weighted_e4`
   integer expression, the confidence rounding rule, and the **source text of the
   named scoring functions** (`fit_all` and what it calls). It excludes
   `ARCHETYPE_VERSION`, the explanation construction and every storage-shape
   constant. That preserves round 19's requirement — a change to how scores are
   computed always moves the digest — while a change to how they are stored,
   versioned or explained never does, which hashing the file could not deliver.

### Review round 25 (2026-10-11)

1. **P1 — Require VACUUM in the controlling publication gate** → correct, and the
   same design-only pattern for the fifth time on this PR: round 24 put
   `VACUUM (ANALYZE)`, `last_vacuum` and `Heap Fetches: 0` into the design and left
   the ROADMAP requiring `ANALYZE`/`last_analyze` alone. Since the ROADMAP outranks
   it, the weaker gate is the one that binds — and the consequence is the specific
   one round 24 identified: after the bulk insert the visibility map is empty, so an
   apparent `Index Only Scan` can still perform up to 10,001 heap fetches per request
   and be **published as bounded**. ROADMAP step 9′ now carries all three
   requirements with the reason for each, including that only the zero-heap-fetch
   assertion tests what index-only means.
2. **P1 — Exclude explanation code from the semantic digest** → correct, and the
   exclusion was **unimplementable as written**. Hashing `fit_all` and everything it
   calls does not exclude explanation construction, because `_fit_anchored` and
   `_fit_flexible` build their explanation dictionaries **inside** the scoring
   functions (`scripts/v3_system_archetype_model.py:120-145`) — which I asserted an
   exclusion for without checking. So an explanation-only edit would still move the
   digest and suppress the F4 comparison with scores provably unchanged, which is the
   precise defect round 24 narrowed this scope to avoid.
   PR1 now **separates explanation construction out of the scoring path**: each
   `_fit_*` returns score, tier and confidence, and a distinct `_explain_*` builds the
   dictionary from the same `SystemVectors`; the digest hashes the `_fit_*` functions
   and excludes the `_explain_*` ones. That is a behaviour-preserving refactor of code
   PR1 already touches, and it is what makes the exclusion true rather than
   aspirational. A test asserts the digest is unchanged by an edit confined to an
   `_explain_*` function and changed by any edit to a `_fit_*` one — which is the
   assertion that would have caught this.
3. **P1 — Probe the local-search window bound before release** → correct. Round 16
   established that JSON Schema cannot express a cross-field bound and that both
   combined bounds therefore need behavioural probes; the ROADMAP then described only
   the `offset`/`limit` pair while claiming to prove both. An image missing **only**
   the local-search `from + size` validator publishes a byte-identical OpenAPI schema
   and passes both stated probes, after which a direct `from=9999&size=2` escapes the
   10,000-row window and drives an excessive `OFFSET`. Both pairs are now required,
   accepted and rejected, with that reasoning recorded so neither is dropped as
   duplicative of the other.
