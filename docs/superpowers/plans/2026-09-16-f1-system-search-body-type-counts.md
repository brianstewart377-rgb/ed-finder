# F1 — system_search Per-Body-Type Count Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing `v3_derived.system_search` product with per-body-type COUNT columns so the V3 Finder's body-composition sliders (all 18 V2 sliders) can filter systems.

**Architecture:** `system_search` already exists (migrations `004`/`006`, builder `scripts/v3_system_search.py`, product lifecycle). This adds count columns via a forward migration `010`, extends the builder's single read projection to compute them from `v3_derived.body_mechanics.body_class` (fine subType) + `{schema}.bodies` (walkable/atmosphere) + `{schema}.rings` + signals, keeps the legacy parity SQL and both tests in lockstep, then the product is rebuilt/republished through the reviewed operation (out of scope here — this plan delivers migration + builder + tests).

**Tech Stack:** PostgreSQL 18 (`cube`, GiST), Python 3.14, psycopg 3, pytest. uv-managed venv.

## Global Constraints

- Python runtime: exact CPython 3.14; run via the repo venv (`.venv/Scripts/python.exe` on Windows).
- Migrations are append-only in the V3 lineage `sql/v3/migrations/`; next free number is **`010`**. Register in `sql/v3/migration-manifest.txt` as `<sha256>  010_v3_system_search_body_type_counts.sql  v3/migrations/010_v3_system_search_body_type_counts.sql`. Do NOT edit already-shipped migrations `003`/`004`/`006`.
- Derived-write guards are insert-only and reject writes unless the generation is `BUILDING`; never mutate published rows.
- Unknown ≠ absent: a count of 0 means "no positive observation in the pinned canonical generation", never asserted absence. Reflect this in `field_policy`.
- Per-type counts come from `v3_derived.body_mechanics.body_class` (excludes barycentre/belt-cluster), normalised like the scorer's `_body_key` (lowercase, `-`→space, collapse whitespace). Stars also use `spectral_class` fallback.
- Column names mirror V2 exactly: `elw_count, ww_count, ammonia_count, terraformable_count, gas_giant_count, hmc_count, metal_rich_count, rocky_count, rocky_ice_count, icy_count, black_hole_count, neutron_count, white_dwarf_count, other_star_count, ring_count, walkable_count, bio_signal_total, geo_signal_total`.
- Tests require env `RATINGS_V4_VALIDATION_DATABASE_URL` → a localhost DB named `ratings_v4_validation`.
- The `v3_app.system_search` view is `SELECT s.*`; Postgres freezes `*` at creation, so the view MUST be recreated in migration `010` to expose new columns.

---

## The 18 new columns and their exact derivations

All counts are non-negative integers. Source and match rule:

| Column | Source | Match rule (on normalised `nk = lower(regexp_replace(body_class,'[-]',' ','g'))`, whitespace-collapsed) |
|---|---|---|
| `elw_count` | body_mechanics | `nk IN ('earth like world','earthlike world','elw')` |
| `ww_count` | body_mechanics | `nk IN ('water world','ww')` |
| `ammonia_count` | body_mechanics | `nk IN ('ammonia world','ammonia')` |
| `terraformable_count` | body_mechanics | `terraformable IS TRUE` |
| `gas_giant_count` | body_mechanics | `nk LIKE '%gas giant%'` |
| `hmc_count` | body_mechanics | `nk IN ('high metal content world','high metal content body','high metal content','hmc')` |
| `metal_rich_count` | body_mechanics | `nk IN ('metal rich body','metal rich')` |
| `rocky_count` | body_mechanics | `nk IN ('rocky body','rocky')` (exact — excludes rocky ice) |
| `rocky_ice_count` | body_mechanics | `nk IN ('rocky ice body','rocky ice world','rocky ice')` |
| `icy_count` | body_mechanics | `nk IN ('icy body','icy')` |
| `black_hole_count` | body_mechanics | `nk LIKE '%black hole%' OR spectral_class IN ('H','SupermassiveBlackHole')` |
| `neutron_count` | body_mechanics | `nk = 'neutron star' OR spectral_class = 'N'` |
| `white_dwarf_count` | body_mechanics | `nk LIKE '%white dwarf%' OR spectral_class LIKE 'D%'` |
| `other_star_count` | body_mechanics | `spectral_class IS NOT NULL AND NOT (black hole/neutron/white dwarf rule)` |
| `ring_count` | `{schema}.rings` | `count(*) WHERE lifecycle_state='ACTIVE' AND kind='RING'` |
| `walkable_count` | `{schema}.bodies` | `is_landable IS TRUE AND (atmosphere_classification_id IS NULL OR atmo.public_code='no_atmosphere')`, ACTIVE |
| `bio_signal_total` | signals | `sum(signal_count)` for `saa_signaltype_biological`, ACTIVE bodies |
| `geo_signal_total` | signals | `sum(signal_count)` for `saa_signaltype_geological`, ACTIVE bodies |

`body_class` normalisation SQL (used verbatim below):
```sql
lower(btrim(regexp_replace(regexp_replace(bm.body_class,'[-]',' ','g'),'\s+',' ','g')))
```

Star bodies are identified as `bm.spectral_class IS NOT NULL`. `black_hole`/`neutron`/`white_dwarf` are subsets; `other_star_count` = star rows minus those three.

---

### Task 1: Migration `010` — add count columns and recreate the app view

**Files:**
- Create: `sql/v3/migrations/010_v3_system_search_body_type_counts.sql`
- Modify: `sql/v3/migration-manifest.txt` (append the `010` line)
- Test: `tests/test_v3_system_search_body_type_counts_migration.py`

**Interfaces:**
- Produces: 18 new `NOT NULL DEFAULT 0` integer columns on `v3_derived.system_search` (names per Global Constraints), and a recreated `v3_app.system_search` view exposing them. No new tables/functions.

- [ ] **Step 1: Write the failing migration test**

```python
# tests/test_v3_system_search_body_type_counts_migration.py
from pathlib import Path
import pytest
from tests.ratings_v4_pg_fixture import canonical_database

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'sql/v3/migrations'
NEW_COLUMNS = [
    'elw_count', 'ww_count', 'ammonia_count', 'terraformable_count',
    'gas_giant_count', 'hmc_count', 'metal_rich_count', 'rocky_count',
    'rocky_ice_count', 'icy_count', 'black_hole_count', 'neutron_count',
    'white_dwarf_count', 'other_star_count', 'ring_count', 'walkable_count',
    'bio_signal_total', 'geo_signal_total',
]


@pytest.fixture
def migrated():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in ('003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
                     '006_v3_derived_product_lifecycle.sql',
                     '010_v3_system_search_body_type_counts.sql'):
            connection.execute((MIGRATIONS / name).read_text())
        yield connection


def test_new_count_columns_exist_on_base_table(migrated):
    rows = migrated.execute(
        '''SELECT column_name FROM information_schema.columns
            WHERE table_schema='v3_derived' AND table_name='system_search' '''
    ).fetchall()
    present = {row[0] for row in rows}
    assert set(NEW_COLUMNS) <= present


def test_app_view_exposes_new_columns(migrated):
    rows = migrated.execute(
        '''SELECT column_name FROM information_schema.columns
            WHERE table_schema='v3_app' AND table_name='system_search' '''
    ).fetchall()
    present = {row[0] for row in rows}
    assert set(NEW_COLUMNS) <= present
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_v3_system_search_body_type_counts_migration.py -v`
Expected: FAIL — migration file `010_...sql` does not exist yet (`FileNotFoundError`).

- [ ] **Step 3: Write migration `010`**

```sql
-- sql/v3/migrations/010_v3_system_search_body_type_counts.sql
-- Adds per-body-type COUNT columns to v3_derived.system_search for Finder
-- body-composition sliders. Additive only; does not touch canonical relations.
BEGIN;

ALTER TABLE v3_derived.system_search
    ADD COLUMN elw_count            integer NOT NULL DEFAULT 0 CHECK(elw_count >= 0),
    ADD COLUMN ww_count             integer NOT NULL DEFAULT 0 CHECK(ww_count >= 0),
    ADD COLUMN ammonia_count        integer NOT NULL DEFAULT 0 CHECK(ammonia_count >= 0),
    ADD COLUMN terraformable_count  integer NOT NULL DEFAULT 0 CHECK(terraformable_count >= 0),
    ADD COLUMN gas_giant_count      integer NOT NULL DEFAULT 0 CHECK(gas_giant_count >= 0),
    ADD COLUMN hmc_count            integer NOT NULL DEFAULT 0 CHECK(hmc_count >= 0),
    ADD COLUMN metal_rich_count     integer NOT NULL DEFAULT 0 CHECK(metal_rich_count >= 0),
    ADD COLUMN rocky_count          integer NOT NULL DEFAULT 0 CHECK(rocky_count >= 0),
    ADD COLUMN rocky_ice_count      integer NOT NULL DEFAULT 0 CHECK(rocky_ice_count >= 0),
    ADD COLUMN icy_count            integer NOT NULL DEFAULT 0 CHECK(icy_count >= 0),
    ADD COLUMN black_hole_count     integer NOT NULL DEFAULT 0 CHECK(black_hole_count >= 0),
    ADD COLUMN neutron_count        integer NOT NULL DEFAULT 0 CHECK(neutron_count >= 0),
    ADD COLUMN white_dwarf_count    integer NOT NULL DEFAULT 0 CHECK(white_dwarf_count >= 0),
    ADD COLUMN other_star_count     integer NOT NULL DEFAULT 0 CHECK(other_star_count >= 0),
    ADD COLUMN ring_count           integer NOT NULL DEFAULT 0 CHECK(ring_count >= 0),
    ADD COLUMN walkable_count       integer NOT NULL DEFAULT 0
        CHECK(walkable_count BETWEEN 0 AND landable_count),
    ADD COLUMN bio_signal_total     integer NOT NULL DEFAULT 0 CHECK(bio_signal_total >= 0),
    ADD COLUMN geo_signal_total     integer NOT NULL DEFAULT 0 CHECK(geo_signal_total >= 0);

-- v3_app.system_search is SELECT s.*; recreate so new columns are exposed.
CREATE OR REPLACE VIEW v3_app.system_search AS
SELECT s.* FROM v3_meta.current_derived_generation c
JOIN v3_derived.system_search s USING(derived_generation_id);

COMMIT;
```

- [ ] **Step 4: Append the manifest line**

Compute the sha256 and append to `sql/v3/migration-manifest.txt`:

Run: `.venv/Scripts/python.exe -c "import hashlib,pathlib; p=pathlib.Path('sql/v3/migrations/010_v3_system_search_body_type_counts.sql'); print(hashlib.sha256(p.read_bytes()).hexdigest())"`

Then add the line (use the printed hash):
```text
<printed-sha256>  010_v3_system_search_body_type_counts.sql  v3/migrations/010_v3_system_search_body_type_counts.sql
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_v3_system_search_body_type_counts_migration.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add sql/v3/migrations/010_v3_system_search_body_type_counts.sql sql/v3/migration-manifest.txt tests/test_v3_system_search_body_type_counts_migration.py
git commit -m "feat(finder): migration 010 adds system_search body-type count columns"
```

---

### Task 2: Extend the builder projection to populate the counts

**Files:**
- Modify: `scripts/v3_system_search.py` — `projection_query_sql()` (SELECT + new CTEs), `_insert_chunk` INSERT column list, `_chunk_content_sha` SELECT, `product_manifest.field_policy`, `PRODUCT_VERSION`, `code_identity()` file list.
- Modify: `scripts/operator/v3_system_search_legacy.sql` — mirror the new output columns in the same positions (keeps the parity test green).
- Test: `tests/test_ratings_v4_system_search.py` (extend), `tests/test_ratings_v4_search_projection.py` (extend).

**Interfaces:**
- Consumes: `v3_derived.body_mechanics` (columns `body_class`, `spectral_class`, `terraformable`, `is_main_star`, keyed by `derived_generation_id, system_id64, body_pk`); `{schema}.bodies` (`is_landable`, `atmosphere_classification_id`, `lifecycle_state`); `v3_vocab.atmosphere_classification` (`public_code`); `{schema}.rings` (`kind`, `lifecycle_state`); signals via existing LATERAL.
- Produces: `projection_query_sql()` returning the original 20 columns **plus the 18 new count columns appended in the fixed order** listed in Global Constraints; `PRODUCT_VERSION = 'v3-system-search-2'`.

- [ ] **Step 1: Write the failing end-to-end count test**

Add to `tests/test_ratings_v4_system_search.py` (uses the existing `database`, `_ratings_generation`, `_ready_ratings`, `register_product`, `build_available`, `validate_product` helpers already in that file):

```python
def test_search_projection_populates_body_type_counts(database):
    connection, canonical, _, _ = database
    generation = _ratings_generation(connection, canonical)
    _ready_ratings(connection, generation)
    gen, state, manifest_sha = register_product(connection, generation.key)
    build_available(connection, gen, manifest_sha)

    row = connection.execute(
        '''SELECT elw_count, ww_count, ammonia_count, terraformable_count,
                  gas_giant_count, hmc_count, metal_rich_count, rocky_count,
                  rocky_ice_count, icy_count, black_hole_count, neutron_count,
                  white_dwarf_count, other_star_count, ring_count, walkable_count,
                  bio_signal_total, geo_signal_total, body_count, landable_count
             FROM v3_derived.system_search
            WHERE derived_generation_id=%s
            ORDER BY (elw_count + ww_count) DESC, system_id64
            LIMIT 1''',
        (gen.identifier,),
    ).fetchone()
    # Every count is a non-negative int and no per-type count exceeds body_count;
    # walkable never exceeds landable. Exact per-fixture values are asserted in the
    # projection-parity test where the fixture is fully controlled.
    counts = row[:18]
    assert all(isinstance(v, int) and v >= 0 for v in counts)
    assert row[15] <= row[19]                     # walkable_count <= landable_count
    assert max(counts[:14]) <= row[18]            # per body/star type <= body_count
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ratings_v4_system_search.py::test_search_projection_populates_body_type_counts -v`
Expected: FAIL — `column "elw_count" does not exist` (migration not applied in this test yet) OR the columns exist but the projection never inserts them. First make the test apply `010`: confirm the `database` fixture (lines ~20-26) applies `003+004+006`; add `010` to that list in this task's Step 3.

- [ ] **Step 3: Apply `010` in the end-to-end fixture**

In `tests/test_ratings_v4_system_search.py`, extend the migration list in the `database` fixture:

```python
        for name in ('003_ratings_v4_derived.sql',
                     '004_v3_search_spatial_clusters.sql',
                     '006_v3_derived_product_lifecycle.sql',
                     '010_v3_system_search_body_type_counts.sql'):
            connection.execute((MIGRATIONS / name).read_text())
```

- [ ] **Step 4: Bump product version and code identity**

In `scripts/v3_system_search.py`:

```python
PRODUCT_VERSION = 'v3-system-search-2'
```

```python
def code_identity(root: Path = ROOT) -> dict[str, str]:
    files = (
        'scripts/v3_system_search.py',
        'sql/v3/migrations/004_v3_search_spatial_clusters.sql',
        'sql/v3/migrations/006_v3_derived_product_lifecycle.sql',
        'sql/v3/migrations/010_v3_system_search_body_type_counts.sql',
    )
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in files
    }
```

- [ ] **Step 5: Add a `type_summary` CTE and walkable/ring/signal aggregates to `projection_query_sql()`**

Replace the body of `projection_query_sql()` so that (a) `body_summary` gains `walkable_count`, (b) `ring_summary` returns `ring_count` (not just a bool), (c) the signals LATERAL returns `bio_signal_total`/`geo_signal_total`, (d) a new `type_summary` CTE over `v3_derived.body_mechanics` returns the 14 body/star + terraformable counts, and (e) the final SELECT appends the 18 columns in fixed order. Keep exactly the existing two `JOIN LATERAL`s (signals + main-star) — do NOT add a third.

```python
def projection_query_sql() -> str:
    return '''
WITH target AS MATERIALIZED (
    SELECT v.system_id64,v.loaded_body_count,v.completeness,v.confidence
      FROM v3_derived.system_rating_vector v
     WHERE v.derived_generation_id=%(generation_id)s AND v.chunk_ordinal=%(chunk_ordinal)s
),
body_summary AS (
    SELECT b.system_id64,
           (count(*) FILTER (
               WHERE b.lifecycle_state='ACTIVE' AND b.is_landable IS TRUE
           ))::integer AS landable_count,
           (count(*) FILTER (
               WHERE b.lifecycle_state='ACTIVE' AND b.is_landable IS TRUE
                 AND (b.atmosphere_classification_id IS NULL OR atmo.public_code='no_atmosphere')
           ))::integer AS walkable_count,
           bool_or(
               b.lifecycle_state='ACTIVE'
               AND ts.public_code IN ('terraformable','terraformed','terraforming')
           ) AS has_terraformable
      FROM {schema}.bodies b
      JOIN target t ON t.system_id64=b.system_id64
 LEFT JOIN v3_vocab.terraforming_state ts
        ON ts.terraforming_state_id=b.terraforming_state_id
 LEFT JOIN v3_vocab.atmosphere_classification atmo
        ON atmo.atmosphere_classification_id=b.atmosphere_classification_id
  GROUP BY b.system_id64
),
type_summary AS (
    SELECT bm.system_id64,
           (count(*) FILTER (WHERE nk IN ('earth like world','earthlike world','elw')))::integer AS elw_count,
           (count(*) FILTER (WHERE nk IN ('water world','ww')))::integer AS ww_count,
           (count(*) FILTER (WHERE nk IN ('ammonia world','ammonia')))::integer AS ammonia_count,
           (count(*) FILTER (WHERE bm.terraformable IS TRUE))::integer AS terraformable_count,
           (count(*) FILTER (WHERE nk LIKE '%gas giant%'))::integer AS gas_giant_count,
           (count(*) FILTER (WHERE nk IN ('high metal content world','high metal content body','high metal content','hmc')))::integer AS hmc_count,
           (count(*) FILTER (WHERE nk IN ('metal rich body','metal rich')))::integer AS metal_rich_count,
           (count(*) FILTER (WHERE nk IN ('rocky body','rocky')))::integer AS rocky_count,
           (count(*) FILTER (WHERE nk IN ('rocky ice body','rocky ice world','rocky ice')))::integer AS rocky_ice_count,
           (count(*) FILTER (WHERE nk IN ('icy body','icy')))::integer AS icy_count,
           (count(*) FILTER (WHERE nk LIKE '%black hole%' OR bm.spectral_class IN ('H','SupermassiveBlackHole')))::integer AS black_hole_count,
           (count(*) FILTER (WHERE nk='neutron star' OR bm.spectral_class='N'))::integer AS neutron_count,
           (count(*) FILTER (WHERE nk LIKE '%white dwarf%' OR bm.spectral_class LIKE 'D%'))::integer AS white_dwarf_count,
           (count(*) FILTER (
               WHERE bm.spectral_class IS NOT NULL
                 AND NOT (nk LIKE '%black hole%' OR bm.spectral_class IN ('H','SupermassiveBlackHole'))
                 AND NOT (nk='neutron star' OR bm.spectral_class='N')
                 AND NOT (nk LIKE '%white dwarf%' OR bm.spectral_class LIKE 'D%')
           ))::integer AS other_star_count
      FROM (
          SELECT bm.system_id64, bm.terraformable, bm.spectral_class,
                 lower(btrim(regexp_replace(regexp_replace(bm.body_class,'[-]',' ','g'),'\\s+',' ','g'))) AS nk
            FROM v3_derived.body_mechanics bm
           WHERE bm.derived_generation_id=%(generation_id)s
      ) bm
      JOIN target t ON t.system_id64=bm.system_id64
  GROUP BY bm.system_id64
),
ring_summary AS (
    SELECT r.system_id64,
           (count(*) FILTER (WHERE r.lifecycle_state='ACTIVE' AND r.kind='RING'))::integer AS ring_count
      FROM {schema}.rings r
      JOIN target t ON t.system_id64=r.system_id64
  GROUP BY r.system_id64
),
station_summary AS (
    SELECT st.system_id64,
           (count(*) FILTER (WHERE st.lifecycle_state='ACTIVE'))::integer
               AS station_count
      FROM {schema}.stations st
      JOIN target t ON t.system_id64=st.system_id64
  GROUP BY st.system_id64
)
SELECT %(generation_id)s,t.system_id64,s.name,s.x_ly,s.y_ly,s.z_ly,
       cube(ARRAY[s.x_ly,s.y_ly,s.z_ly]),
       s.galaxy_region_id,gr.display_name,ms.main_star_class,
       t.loaded_body_count,COALESCE(bs.landable_count,0),
       COALESCE(ss.station_count,0),COALESCE(rs.ring_count,0)>0,
       COALESCE(sig.bio_signal_total,0)>0,
       COALESCE(sig.geo_signal_total,0)>0,
       COALESCE(bs.has_terraformable,false),
       s.source_updated_at,
       (SELECT min(value)::double precision/10000 FROM unnest(t.completeness) AS value),
       (SELECT min(value)::double precision/10000 FROM unnest(t.confidence) AS value),
       COALESCE(ty.elw_count,0),COALESCE(ty.ww_count,0),COALESCE(ty.ammonia_count,0),
       COALESCE(ty.terraformable_count,0),COALESCE(ty.gas_giant_count,0),
       COALESCE(ty.hmc_count,0),COALESCE(ty.metal_rich_count,0),COALESCE(ty.rocky_count,0),
       COALESCE(ty.rocky_ice_count,0),COALESCE(ty.icy_count,0),
       COALESCE(ty.black_hole_count,0),COALESCE(ty.neutron_count,0),
       COALESCE(ty.white_dwarf_count,0),COALESCE(ty.other_star_count,0),
       COALESCE(rs.ring_count,0),COALESCE(bs.walkable_count,0),
       COALESCE(sig.bio_signal_total,0),COALESCE(sig.geo_signal_total,0)
  FROM target t
  JOIN {schema}.systems s ON s.id64=t.system_id64
 LEFT JOIN v3_vocab.galaxy_region gr ON gr.galaxy_region_id=s.galaxy_region_id
 LEFT JOIN body_summary bs USING(system_id64)
 LEFT JOIN type_summary ty USING(system_id64)
 LEFT JOIN ring_summary rs USING(system_id64)
 LEFT JOIN station_summary ss USING(system_id64)
 LEFT JOIN LATERAL (
    SELECT sum(bs.signal_count) FILTER (WHERE st.public_code='saa_signaltype_biological')::integer AS bio_signal_total,
           sum(bs.signal_count) FILTER (WHERE st.public_code='saa_signaltype_geological')::integer AS geo_signal_total
      FROM {schema}.bodies b
      JOIN {schema}.body_signal_current bs ON bs.body_pk=b.body_pk
      JOIN v3_vocab.signal_type st ON st.signal_type_id=bs.signal_type_id
     WHERE b.system_id64=t.system_id64 AND b.lifecycle_state='ACTIVE'
 ) sig ON true
 LEFT JOIN LATERAL (
    SELECT bm.body_class AS main_star_class
      FROM v3_derived.body_mechanics bm
     WHERE bm.derived_generation_id=%(generation_id)s
       AND bm.system_id64=t.system_id64 AND bm.is_main_star IS TRUE
  ORDER BY bm.body_pk
     LIMIT 1
 ) ms ON true
ORDER BY t.system_id64
    '''.strip()
```

Note: the `has_biologicals`/`has_geologicals` boolean output columns are preserved by deriving them from the new signal totals (`...>0`), and `has_rings` from `ring_count>0`, so the existing 20-column prefix is unchanged in meaning and position.

- [ ] **Step 6: Extend the INSERT column list in `_insert_chunk`**

Replace the INSERT column list (currently lines ~382-387) to append the 18 columns in the same order the SELECT produces them:

```python
        query = sql.SQL(
            '''INSERT INTO v3_derived.system_search(
                derived_generation_id,system_id64,name,x_ly,y_ly,z_ly,position_ly,
                galaxy_region_id,region_name,main_star_class,body_count,landable_count,
                station_count,has_rings,has_biologicals,has_geologicals,
                has_terraformable,source_observed_at,completeness,confidence,
                elw_count,ww_count,ammonia_count,terraformable_count,gas_giant_count,
                hmc_count,metal_rich_count,rocky_count,rocky_ice_count,icy_count,
                black_hole_count,neutron_count,white_dwarf_count,other_star_count,
                ring_count,walkable_count,bio_signal_total,geo_signal_total
            )
            '''
        ) + sql.SQL(projection_query_sql()).format(
            schema=sql.Identifier(generation.canonical_schema),
        )
```

- [ ] **Step 7: Extend `_chunk_content_sha` so the seal covers the new columns**

Append the 18 columns to the SELECT in `_chunk_content_sha` (currently lines ~222-237), in the same order, after `s.confidence`:

```python
    rows = connection.execute(
        '''SELECT s.system_id64,s.name,s.x_ly,s.y_ly,s.z_ly,
                  s.galaxy_region_id,s.region_name,s.main_star_class,
                  s.body_count,s.landable_count,s.station_count,s.has_rings,
                  s.has_biologicals,s.has_geologicals,s.has_terraformable,
                  s.source_observed_at,s.completeness,s.confidence,
                  s.elw_count,s.ww_count,s.ammonia_count,s.terraformable_count,
                  s.gas_giant_count,s.hmc_count,s.metal_rich_count,s.rocky_count,
                  s.rocky_ice_count,s.icy_count,s.black_hole_count,s.neutron_count,
                  s.white_dwarf_count,s.other_star_count,s.ring_count,s.walkable_count,
                  s.bio_signal_total,s.geo_signal_total
             FROM v3_derived.system_search s
             JOIN v3_derived.system_rating_vector v
               ON v.derived_generation_id=s.derived_generation_id
              AND v.system_id64=s.system_id64
            WHERE s.derived_generation_id=%s AND v.chunk_ordinal=%s
            ORDER BY s.system_id64''',
        (generation_id, ordinal),
    ).fetchall()
    return _digest(rows)
```

- [ ] **Step 8: Document the new columns in `product_manifest.field_policy`**

Add these keys to the `field_policy` dict (after `confidence`):

```python
            'per_type_counts': (
                'counts of ACTIVE v3_derived.body_mechanics rows whose normalised '
                'body_class matches each Finder type; barycentre/belt-cluster bodies '
                'are excluded from body_mechanics and therefore uncounted'
            ),
            'star_counts': (
                'black_hole/neutron/white_dwarf resolved from body_class or '
                'spectral_class; other_star_count = star rows (spectral_class present) '
                'minus those three'
            ),
            'walkable_count': 'landable ACTIVE bodies with no/absent atmosphere (atmosphere_classification no_atmosphere or null)',
            'ring_count': 'ACTIVE canonical RING rows (asteroid BELT rows excluded)',
            'bio_signal_total': 'sum of biological signal_count over ACTIVE bodies',
            'geo_signal_total': 'sum of geological signal_count over ACTIVE bodies',
            'zero_counts': 'a 0 count means no positive observation in the pinned canonical generation, not proven absence',
```

- [ ] **Step 9: Run the end-to-end count test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ratings_v4_system_search.py::test_search_projection_populates_body_type_counts -v`
Expected: PASS.

- [ ] **Step 10: Update the legacy parity SQL to mirror the new columns**

In `scripts/operator/v3_system_search_legacy.sql`, add the same 18 output columns in the same positions (append after the `min(confidence)/10000` column), computing them with the legacy CTE style (`type_summary`, walkable in `body_summary`, `ring_count` in `ring_summary`, bio/geo totals in `signal_summary`). Mirror the exact match rules from the table above so `projection_query_sql()` and the legacy SQL produce identical output.

- [ ] **Step 11: Extend the projection-parity fixture and assertions**

In `tests/test_ratings_v4_search_projection.py`:
- add `atmosphere_classification_id` to the fixture `bodies` table and an `atmosphere_classification(atmosphere_classification_id, public_code)` table with a `no_atmosphere` row;
- ensure the fixture `body_mechanics` rows carry representative `body_class`/`spectral_class`/`terraformable` values covering ELW, WW, HMC, metal-rich, rocky vs rocky-ice (disambiguation), a neutron star (spectral `N`), a white dwarf (spectral `DA`), and an ordinary star;
- keep the existing `assert new == old` parity assertion (now covering the wider column set) and add an explicit tuple assertion for the new columns on the deterministic `FIRST` system.

- [ ] **Step 12: Run the full search test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ratings_v4_search_projection.py tests/test_ratings_v4_system_search.py -v`
Expected: PASS, including the existing "exactly 2 JOIN LATERAL" and CTE-absence invariants (we added a `type_summary` CTE — allowed — and no new LATERAL).

- [ ] **Step 13: Commit**

```bash
git add scripts/v3_system_search.py scripts/operator/v3_system_search_legacy.sql tests/test_ratings_v4_system_search.py tests/test_ratings_v4_search_projection.py
git commit -m "feat(finder): project per-body-type counts into system_search"
```

---

### Task 3: Full regression + record the rebuild/publish requirement

**Files:**
- Modify: `docs/development/v3-finder-delivery-plan.md` (note F1 column-extension shipped; rebuild/republish pending the reviewed operation)
- Test: whole derived/search suite

- [ ] **Step 1: Run the derived + search test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ratings_v4_production_generation.py tests/test_ratings_v4_system_search.py tests/test_ratings_v4_search_projection.py tests/test_v3_system_search_body_type_counts_migration.py -v`
Expected: PASS (no regression in the base generation, product lifecycle, or parity tests).

- [ ] **Step 2: Record the operational follow-up**

Add a short note to `docs/development/v3-finder-delivery-plan.md` under F1: the `system_search` product version is now `v3-system-search-2` with body-type counts; a **rebuild + republish through the reviewed V3 migration + derived-product operation** (apply `010`, re-register the product, `build_available` over the published Ratings V4 generation, `validate_product`, then publish) is required before the counts are queryable in production — same governed path as the Ratings V4 publish. This plan does not perform that production run.

- [ ] **Step 3: Commit**

```bash
git add docs/development/v3-finder-delivery-plan.md
git commit -m "docs(finder): record F1 system_search rebuild/republish follow-up"
```

---

## Self-Review

- **Spec coverage:** migration `010` (spec F1 item 1) → Task 1; builder projection + field_policy + version (spec F1 item 2) → Task 2 Steps 4-8; tests incl. sparse/adversarial (spec F1 item 3) → Task 2 Steps 1,11; rebuild/republish note → Task 3. Full 18-column slider set present in Global Constraints and Task 1. Economy potentials intentionally NOT copied (joined from `system_rating_vector`) — consistent with spec.
- **Placeholder scan:** all SQL and Python steps contain complete code; the only prose-described step is the legacy-SQL mirror (Task 2 Step 10), which restates the exact match rules from the column table — acceptable as it is a mechanical mirror of Step 5, but the implementer must reproduce every column.
- **Type consistency:** column names identical across migration, INSERT list, content-seal SELECT, and tests; SELECT output order matches the INSERT list order (20 existing + 18 new); `PRODUCT_VERSION` bumped once to `v3-system-search-2`.
- **Known risk to verify during implementation:** the `has_biologicals/has_geologicals/has_rings` booleans are now derived from the new totals (`>0`) rather than `bool_or`; confirm the parity test still matches the legacy SQL after both are updated in lockstep.
