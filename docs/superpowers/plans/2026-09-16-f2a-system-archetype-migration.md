# F2a — system_archetype Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the schema for the V3 Finder archetype layer: `v3_derived.system_archetype`, `v3_derived.system_archetype_summary`, `v3_derived.archetype_build_chunk`, their insert-only product guards, and published `v3_app` views — as migration `011`, registered as a derived **product** in the existing `006` lifecycle.

**Architecture:** Mirrors the merged `system_search` product (migrations `004`/`006`, builder `scripts/v3_system_search.py`). `v3_meta.derived_product` is generic and its publish-gate already requires every product be READY/VERIFIED, so no change there. This migration only adds the archetype relations + archetype-specific guards. The builder (fit model) is F2b; this is schema only.

**Tech Stack:** PostgreSQL 18, psycopg 3, pytest, CPython 3.14.

## Global Constraints

- Migration is append-only in `sql/v3/migrations/`; next free number is **`011`** (`007` is a proposal; `010` is the merged F1 migration). Do NOT edit shipped migrations.
- **Do NOT add `011` to `sql/v3/migration-manifest.txt`** — declaring a migration changes the reviewed desired-schema identity and requires fresh external authority (enforced by `test_v3_system_search_production_operator`); that declaration belongs to the governed migration operation, not this PR. (Same rule F1's `010` followed.)
- New relations are **insert-only** while their product is `BUILDING`, mirroring the `006` `system_search` guards (`guard_system_search_insert` / `reject_system_search_mutation`) but scoped to `product_code='system_archetype'`.
- Files stay **LF-terminated** (the lineage hash test rejects CRLF; local Windows `core.autocrlf` is a known artifact).
- Tests use env `RATINGS_V4_VALIDATION_DATABASE_URL` → localhost `ratings_v4_validation` (the `docker-compose.localtest.yml` DB on port 55434). Interpreter: `C:/Users/brian/ed-finder/.venv/Scripts/python.exe`.
- Archetype set is 8 keys (validated in F2b): `paradise, mining_hub, manufacturing_hub, megacomplex, research_hub, stronghold, population_capital, flexible`. This migration does not hardcode the set (any `^[a-z][a-z0-9_]{0,62}$` key), it only constrains score/tier shape.

---

### Task 1: Migration `011` — archetype relations, guards, and views

**Files:**
- Create: `sql/v3/migrations/011_v3_system_archetype.sql`
- Test: `tests/test_v3_system_archetype_migration.py`

**Interfaces:**
- Produces: `v3_derived.system_archetype`, `v3_derived.system_archetype_summary`, `v3_derived.archetype_build_chunk`, functions `v3_derived.guard_system_archetype_insert()` / `v3_derived.reject_system_archetype_mutation()`, and views `v3_app.system_archetype` / `v3_app.system_archetype_summary`. No change to `v3_meta.derived_product` or `v3_meta.publish_derived_generation` (both already generic over product_code).

- [ ] **Step 1: Write the failing migration test**

```python
# tests/test_v3_system_archetype_migration.py
from pathlib import Path
import psycopg
import pytest
from tests.ratings_v4_pg_fixture import canonical_database

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'sql/v3/migrations'
CHAIN = ('003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
         '006_v3_derived_product_lifecycle.sql', '010_v3_system_search_body_type_counts.sql',
         '011_v3_system_archetype.sql')


@pytest.fixture
def migrated():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in CHAIN:
            connection.execute((MIGRATIONS / name).read_text())
        yield connection


def _tables(connection, schema):
    return {row[0] for row in connection.execute(
        'SELECT table_name FROM information_schema.tables WHERE table_schema=%s', (schema,)
    ).fetchall()}


def test_archetype_relations_exist(migrated):
    derived = _tables(migrated, 'v3_derived')
    assert {'system_archetype', 'system_archetype_summary', 'archetype_build_chunk'} <= derived
    app = _tables(migrated, 'v3_app')
    assert {'system_archetype', 'system_archetype_summary'} <= app


def test_score_and_tier_constraints_reject_out_of_range(migrated):
    # A row referencing a non-existent generation still trips CHECKs before FK
    # only if CHECK is evaluated first; instead assert the CHECK exists by
    # attempting an out-of-range score inside a savepoint against a real system.
    gen = migrated.execute(
        'SELECT derived_generation_id, system_id64 FROM v3_derived.system_rating_vector LIMIT 1'
    ).fetchone()
    if gen is None:
        pytest.skip('fixture generation has no rating rows')
    with migrated.transaction():
        migrated.execute("UPDATE v3_meta.derived_product SET lifecycle_state=lifecycle_state WHERE false")
    with pytest.raises(psycopg.errors.CheckViolation):
        with migrated.transaction():
            migrated.execute(
                '''INSERT INTO v3_derived.system_archetype(
                       derived_generation_id,system_id64,archetype_key,archetype_version,
                       archetype_score,tier,confidence,explanation)
                   VALUES(%s,%s,'paradise','v3-archetype-1',101,'S',0.9,'{}'::jsonb)''',
                (gen[0], gen[1]),
            )


def test_archetype_rows_are_insert_only(migrated):
    # Registering nothing; the reject-mutation guard fires on UPDATE regardless.
    with pytest.raises(psycopg.errors.RaiseException, match='insert-only'):
        migrated.execute(
            "UPDATE v3_derived.system_archetype SET archetype_score=archetype_score")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:/Users/brian/ed-finder-wt-f2 && RATINGS_V4_VALIDATION_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:55434/ratings_v4_validation" C:/Users/brian/ed-finder/.venv/Scripts/python.exe -m pytest tests/test_v3_system_archetype_migration.py -v`
Expected: FAIL — `011_v3_system_archetype.sql` does not exist (`FileNotFoundError`).

- [ ] **Step 3: Write migration `011`**

```sql
-- sql/v3/migrations/011_v3_system_archetype.sql
-- Archetype judgement product attached to one Ratings V4 generation. Additive;
-- does not touch canonical relations. Mirrors the system_search product
-- lifecycle from 004/006 but scoped to product_code='system_archetype'.
BEGIN;

CREATE TABLE v3_derived.system_archetype (
    derived_generation_id uuid NOT NULL REFERENCES v3_meta.derived_generation,
    system_id64 bigint NOT NULL CHECK(system_id64 >= 0),
    archetype_key text NOT NULL CHECK(archetype_key ~ '^[a-z][a-z0-9_]{0,62}$'),
    archetype_version text NOT NULL CHECK(length(archetype_version) BETWEEN 1 AND 128),
    archetype_score smallint NOT NULL CHECK(archetype_score BETWEEN 0 AND 100),
    tier text NOT NULL CHECK(tier IN ('S','A','B','C','D')),
    confidence double precision NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    explanation jsonb NOT NULL CHECK(jsonb_typeof(explanation)='object'),
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(derived_generation_id,system_id64,archetype_key),
    FOREIGN KEY(derived_generation_id,system_id64)
        REFERENCES v3_derived.system_rating_vector DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE v3_derived.system_archetype_summary (
    derived_generation_id uuid NOT NULL REFERENCES v3_meta.derived_generation,
    system_id64 bigint NOT NULL CHECK(system_id64 >= 0),
    primary_archetype text NOT NULL CHECK(primary_archetype ~ '^[a-z][a-z0-9_]{0,62}$'),
    secondary_archetype text CHECK(secondary_archetype ~ '^[a-z][a-z0-9_]{0,62}$'),
    best_colony_potential smallint NOT NULL CHECK(best_colony_potential BETWEEN 0 AND 100),
    best_tier text NOT NULL CHECK(best_tier IN ('S','A','B','C','D')),
    archetype_confidence double precision NOT NULL CHECK(archetype_confidence BETWEEN 0 AND 1),
    PRIMARY KEY(derived_generation_id,system_id64),
    FOREIGN KEY(derived_generation_id,system_id64)
        REFERENCES v3_derived.system_rating_vector DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE v3_derived.archetype_build_chunk (
    derived_generation_id uuid NOT NULL,
    chunk_ordinal bigint NOT NULL CHECK(chunk_ordinal >= 0),
    product_code text NOT NULL DEFAULT 'system_archetype'
        CHECK(product_code='system_archetype'),
    archetype_version text NOT NULL CHECK(length(archetype_version) BETWEEN 1 AND 128),
    source_projection_sha256 bytea NOT NULL CHECK(octet_length(source_projection_sha256)=32),
    content_sha256 bytea NOT NULL CHECK(octet_length(content_sha256)=32),
    systems integer NOT NULL CHECK(systems BETWEEN 1 AND 1000),
    completed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(derived_generation_id,chunk_ordinal),
    FOREIGN KEY(derived_generation_id,chunk_ordinal)
        REFERENCES v3_derived.build_chunk(derived_generation_id,chunk_ordinal)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(derived_generation_id,product_code)
        REFERENCES v3_meta.derived_product(derived_generation_id,product_code)
        DEFERRABLE INITIALLY DEFERRED
);

-- Insert-only while the archetype product is BUILDING (mirrors 006 system_search).
CREATE FUNCTION v3_derived.guard_system_archetype_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE identifier uuid; base_state text; product_state text;
BEGIN
    FOR identifier IN SELECT DISTINCT derived_generation_id FROM changed_rows ORDER BY 1 LOOP
        SELECT lifecycle_state INTO base_state
          FROM v3_meta.derived_generation
         WHERE derived_generation_id=identifier FOR SHARE;
        IF base_state NOT IN ('BUILDING','VALIDATING','READY') THEN
            RAISE EXCEPTION 'system_archetype generation % is immutable in state %',
                identifier, base_state;
        END IF;
        SELECT lifecycle_state INTO product_state
          FROM v3_meta.derived_product
         WHERE derived_generation_id=identifier AND product_code='system_archetype'
         FOR SHARE;
        IF product_state IS DISTINCT FROM 'BUILDING' THEN
            RAISE EXCEPTION 'system_archetype product % is not BUILDING', identifier;
        END IF;
    END LOOP;
    RETURN NULL;
END $$;

CREATE FUNCTION v3_derived.reject_system_archetype_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'system_archetype rows and receipts are insert-only';
END $$;

-- Attach the guard/reject triggers to all three archetype relations.
DO $triggers$
DECLARE relation text;
BEGIN
    FOREACH relation IN ARRAY ARRAY[
        'v3_derived.system_archetype',
        'v3_derived.system_archetype_summary',
        'v3_derived.archetype_build_chunk'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER product_insert AFTER INSERT ON %s '
            'REFERENCING NEW TABLE AS changed_rows FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.guard_system_archetype_insert()', relation);
        EXECUTE format(
            'CREATE TRIGGER product_update BEFORE UPDATE ON %s FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.reject_system_archetype_mutation()', relation);
        EXECUTE format(
            'CREATE TRIGGER product_delete BEFORE DELETE ON %s FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.reject_system_archetype_mutation()', relation);
        EXECUTE format(
            'CREATE TRIGGER product_truncate BEFORE TRUNCATE ON %s FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.reject_system_archetype_mutation()', relation);
    END LOOP;
END $triggers$;

-- Published-generation convenience reads.
CREATE VIEW v3_app.system_archetype AS
SELECT s.* FROM v3_meta.current_derived_generation c
JOIN v3_derived.system_archetype s USING(derived_generation_id);

CREATE VIEW v3_app.system_archetype_summary AS
SELECT s.* FROM v3_meta.current_derived_generation c
JOIN v3_derived.system_archetype_summary s USING(derived_generation_id);

COMMIT;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:/Users/brian/ed-finder-wt-f2 && RATINGS_V4_VALIDATION_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:55434/ratings_v4_validation" C:/Users/brian/ed-finder/.venv/Scripts/python.exe -m pytest tests/test_v3_system_archetype_migration.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add sql/v3/migrations/011_v3_system_archetype.sql tests/test_v3_system_archetype_migration.py
git commit -m "feat(finder): migration 011 adds system_archetype product relations"
```

---

### Task 2: Regression guard

**Files:**
- Test: existing derived/search + migration suites

- [ ] **Step 1: Run the derived + search + archetype migration suite**

Run: `cd C:/Users/brian/ed-finder-wt-f2 && RATINGS_V4_VALIDATION_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:55434/ratings_v4_validation" C:/Users/brian/ed-finder/.venv/Scripts/python.exe -m pytest tests/test_ratings_v4_production_generation.py tests/test_ratings_v4_system_search.py tests/test_v3_system_archetype_migration.py -v`
Expected: PASS — the new migration does not touch existing relations (system_search unchanged; `derived_product`/publish function unchanged).

- [ ] **Step 2: Confirm 011 stays undeclared in the manifest and LF-terminated**

Run: `cd C:/Users/brian/ed-finder-wt-f2 && grep -c "011_v3_system_archetype" sql/v3/migration-manifest.txt; python -c "print(b'\r\n' in open('sql/v3/migrations/011_v3_system_archetype.sql','rb').read())"`
Expected: `0` (not in manifest) and `False` (LF).

- [ ] **Step 3: Commit (only if any doc note is added; otherwise skip)**

No commit needed if Steps 1-2 pass with no changes.

---

## Self-Review

- **Spec coverage:** migration `011` with `system_archetype` + `system_archetype_summary` + `archetype_build_chunk` + guards + `v3_app` views (spec §Architecture) → Task 1. No manifest declaration (Global Constraints) → Task 2 Step 2. Product registration itself happens in the F2b builder via `v3_meta.derived_product` (generic, unchanged here) — out of this plan's scope by design.
- **Placeholder scan:** full DDL and test code present; no TBDs.
- **Type consistency:** `archetype_key`/`primary_archetype`/`secondary_archetype` share the same regex; `tier`/`best_tier` share the S–D CHECK; `archetype_build_chunk` mirrors `search_build_chunk` shape with `product_code='system_archetype'`.
- **Known local caveat:** the 3 manifest-hash tests fail locally on Windows autocrlf (006 CRLF); green on Linux CI. `011` is not in the manifest so it is not hashed by that test regardless.
