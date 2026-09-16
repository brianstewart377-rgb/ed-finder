# V3 Spatial Pyramid Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-model the V3 spatial density pyramid as an independently-published artifact keyed to the canonical generation, with its own lifecycle and CAS publish pointer, so it no longer has to be built before the ratings `derived_generation` is published.

**Architecture:** A new migration replaces the derived-keyed `v3_spatial.cell_summary` + `spatial_pyramid` derived-product path with canonical-keyed tables: `v3_spatial.spatial_generation` (lifecycle envelope), a rebuilt `v3_spatial.cell_summary` (pure-density cells), `v3_spatial.current_spatial_generation` (singleton pointer), `v3_spatial.spatial_publication_audit`, and a `v3_spatial.publish_spatial_pyramid` CAS function. The builder (`scripts/v3_spatial_pyramid.py`) reads the canonical `{gen}.systems` catalogue only, aggregates per-cell `system_count` + representative star, reconciles Σ==canonical, and marks a `spatial_generation` READY. The map API serves the published spatial pyramid or a labelled legacy fallback.

**Tech Stack:** PostgreSQL 18 (`sql/v3/migrations/`), CPython 3.14 + Psycopg 3 (builder + unit tests), FastAPI + asyncpg (`apps/api/`), pytest, governed GitHub Actions operator workflow (bash).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-16-v3-spatial-pyramid-decoupling-design.md` (authority for this plan).
- Source of truth: **pure canonical density** — per-cell `system_count` from the canonical `{gen}.systems` catalogue only; **no** ratings-derived aux counters (`landable_count`, `station_count`, `biological_system_count`, `terraformable_system_count`) in the base pyramid.
- Go-live: **explicit CAS** — `v3_spatial.current_spatial_generation` singleton pointer + `v3_spatial.publish_spatial_pyramid(target, expected_current, expected_sequence, expected_canonical, actor, reason)` + `v3_spatial.spatial_publication_audit`.
- Scope: **clean replace** the derived-keyed `cell_summary` + `spatial_pyramid` product path; **do not touch** `v3_spatial.cluster_*`.
- Keying: everything spatial keys to `spatial_generation_id` → `canonical_generation_id`; freeze is on the **spatial** lifecycle, never the ratings generation state.
- `pyramid_version` string ~ `^[a-z][a-z0-9_]{0,62}$`; keep `PYRAMID_VERSION = 'pyramid_v1'` and the existing `CELL_LEVELS` ladder (levels 0–6, 2560→40 ly). `cell_summary.spatial_pyramid_version` == its `spatial_generation.pyramid_version`; it exists only to satisfy the existing `cell_level(spatial_pyramid_version, level)` FK.
- Reconciliation is a fail-closed truth gate: Σ `system_count` at **every registered level** must equal the canonical system count; empty/missing level or mismatch → `ReconciliationError`, nothing marked READY. No procedural/random fill; empty input → no cells.
- Publish CAS gates on the candidate's `canonical_generation_id == v3_meta.current_canonical_generation`; rollback = publish a prior READY/RETIRED spatial generation.
- Branch → PR; `main` protected; **no production DB writes from this coding task**. Full prod build+publish is the owner-dispatched governed workflow only.
- Parameterised SQL only; no secrets in code/args/logs. CPython 3.14; Ruff `py314`.
- Tests run against a disposable local Postgres (per `tests/helpers/db_isolation.py`, e.g. `docker-compose.localtest.yml` at `127.0.0.1:55434`, DB `ratings_v4_validation`); apply migrations there with `DATABASE_URL=<disposable> bash scripts/apply_migrations.sh` before integration tests. Never target a production-looking host.

---

## File Structure

- **Create** `sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql` — the whole schema change (Tasks 1–2).
- **Modify** `sql/v3/migration-manifest.txt` — append `011_...` (Task 1).
- **Rewrite** `scripts/v3_spatial_pyramid.py` — canonical-density builder + spatial_generation lifecycle (Tasks 3–4).
- **Rewrite** `tests/test_v3_spatial_pyramid.py` — unit/contract on canonical fixtures (Tasks 3–4).
- **Rewrite** `scripts/operator/actions/v3-spatial-pyramid.sh` + **modify** `.github/workflows/v3-spatial-pyramid.yml` — pin canonical, build + publish ops (Task 5).
- **Modify** `apps/api/src/routers/map.py` — serving path (Task 6).
- **Modify** `tests/integration/test_map_heatmap_pyramid.py` — API + lifecycle/publish integration (Task 6).
- **Regenerate** `apps/web/src/lib/api/` OpenAPI types (Task 6).

---

## Task 1: Migration 011 — canonical-keyed tables, guards, clean replace

**Files:**
- Create: `sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql`
- Modify: `sql/v3/migration-manifest.txt` (append the new filename after `010_...`)
- Test: `tests/integration/test_spatial_generation_lifecycle.py` (create)

**Interfaces:**
- Produces (schema): `v3_spatial.spatial_generation(spatial_generation_id uuid PK, canonical_generation_id uuid, pyramid_version text, lifecycle_state text, expected_systems bigint, validation_receipt jsonb, validation_sha256 bytea, created_at, validated_at, published_at, failed_at, failure, UNIQUE(canonical_generation_id, pyramid_version))`; rebuilt `v3_spatial.cell_summary(spatial_generation_id, spatial_pyramid_version, level, cell_key, system_count, representative_system_id64, origin_x_ly, origin_y_ly, origin_z_ly, centroid_x_ly, centroid_y_ly, centroid_z_ly, PK(spatial_generation_id, level, cell_key))`; trigger `v3_spatial.guard_spatial_generation()`; statement trigger `v3_spatial.guard_cell_summary()`.
- Keeps: `v3_spatial.cell_level(spatial_pyramid_version, level, ...)` unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_spatial_generation_lifecycle.py` (reuse the `db_conn` fixture pattern from `tests/test_v3_spatial_pyramid.py`, copying the fixture verbatim so this file is self-contained):

```python
"""Migration 011 schema + lifecycle-guard contract, on a disposable DB.

Requires migration 011 already applied to the disposable test database
(DATABASE_URL=<disposable> bash scripts/apply_migrations.sh). Skips when no
disposable Postgres is reachable.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest

os.environ.setdefault('CORS_ORIGINS', 'http://testserver')
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from tests.helpers import db_isolation  # noqa: E402


@pytest.fixture
def db_conn():
    target = db_isolation.default_target(os.environ)
    try:
        conn = psycopg.connect(target.dsn)
    except psycopg.OperationalError as exc:
        pytest.skip(f'disposable test Postgres unreachable at {target.redacted_dsn}: {exc}')
        return
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _seed_canonical(conn) -> uuid.UUID:
    """Minimal canonical_generation chain (no {gen}.systems needed here)."""
    gid, run_id = uuid.uuid4(), uuid.uuid4()
    key = 'spatialtest_' + gid.hex[:16]
    source_id = conn.execute(
        "INSERT INTO v3_source.source(source_code,display_name,authority_class) "
        "VALUES(%s,'Fixture','OPERATOR_ADJUDICATION') RETURNING source_id", (key,),
    ).fetchone()[0]
    rights_id = conn.execute(
        "INSERT INTO v3_source.source_rights_policy(source_id,policy_version,rights_class,retention_class,effective_at) "
        "VALUES(%s,'test','CANONICAL_ELIGIBLE','TEST',now()) RETURNING rights_policy_id", (source_id,),
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO v3_source.source_run(source_run_id,source_id,rights_policy_id,acquisition_kind,trust_zone,
               run_state,idempotency_key,started_at,completed_at,importer_version,importer_code_sha256,
               importer_config_sha256,normalizer_version,normalizer_sha256)
           VALUES(%s,%s,%s,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',%s,now(),now(),'test',%s,%s,'test',%s)""",
        (run_id, source_id, rights_id, key, b'x' * 32, b'x' * 32, b'x' * 32),
    )
    conn.execute(
        "INSERT INTO v3_meta.canonical_generation(generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id) "
        "VALUES(%s,%s,%s,%s,%s)", (gid, key, 'v3_gen_' + key, b'x' * 32, run_id),
    )
    return gid


def test_spatial_generation_insert_defaults_building(db_conn):
    gid = _seed_canonical(db_conn)
    sgid = db_conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',3) RETURNING spatial_generation_id, lifecycle_state",
        (gid,),
    ).fetchone()
    assert sgid[1] == 'BUILDING'


def test_spatial_generation_ready_requires_receipt(db_conn):
    gid = _seed_canonical(db_conn)
    sgid = db_conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',3) RETURNING spatial_generation_id", (gid,),
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException):
        db_conn.execute(
            "UPDATE v3_spatial.spatial_generation SET lifecycle_state='READY' "
            "WHERE spatial_generation_id=%s", (sgid,),
        )


def test_cell_summary_frozen_after_publish(db_conn):
    """Once a spatial_generation leaves BUILDING/VALIDATING/READY, cells are frozen."""
    gid = _seed_canonical(db_conn)
    sgid = db_conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',1) RETURNING spatial_generation_id", (gid,),
    ).fetchone()[0]
    db_conn.execute(
        "INSERT INTO v3_spatial.cell_level(spatial_pyramid_version,level,cell_size_ly,intended_scale) "
        "VALUES('pyramid_v1',0,2560.0,'wide') ON CONFLICT DO NOTHING",
    )
    db_conn.execute(
        "INSERT INTO v3_spatial.cell_summary(spatial_generation_id,spatial_pyramid_version,level,cell_key,"
        "system_count,representative_system_id64,origin_x_ly,origin_y_ly,origin_z_ly,"
        "centroid_x_ly,centroid_y_ly,centroid_z_ly) "
        "VALUES(%s,'pyramid_v1',0,'0.0.0',1,1001,0,0,0,10,10,10)", (sgid,),
    )
    # Force the generation into RETIRED directly is blocked; simulate a frozen
    # state by marking FAILED (a terminal non-mutable state).
    db_conn.execute(
        "UPDATE v3_spatial.spatial_generation SET lifecycle_state='FAILED',failed_at=now(),failure='test' "
        "WHERE spatial_generation_id=%s", (sgid,),
    )
    with pytest.raises(psycopg.errors.RaiseException):
        db_conn.execute(
            "INSERT INTO v3_spatial.cell_summary(spatial_generation_id,spatial_pyramid_version,level,cell_key,"
            "system_count,representative_system_id64,origin_x_ly,origin_y_ly,origin_z_ly,"
            "centroid_x_ly,centroid_y_ly,centroid_z_ly) "
            "VALUES(%s,'pyramid_v1',0,'9.9.9',1,1002,0,0,0,10,10,10)", (sgid,),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=<disposable> python -m pytest tests/integration/test_spatial_generation_lifecycle.py -v`
Expected: FAIL/ERROR — `v3_spatial.spatial_generation` does not exist (migration not written yet).

- [ ] **Step 3: Write the migration file**

Create `sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql`:

```sql
-- Decouple the spatial density pyramid from the ratings derived_generation.
-- The pyramid becomes an independently-published artifact keyed to the
-- canonical generation, with its own lifecycle and CAS publish pointer.
-- Clean-replaces the derived-keyed cell_summary + spatial_pyramid product path
-- (empty/unused on prod). Clusters (v3_spatial.cluster_*) are untouched.
BEGIN;

-- 1. Drop the derived-keyed pyramid storage (its migration-004 immutability
--    triggers drop with the table). cell_level (version/level keyed) is kept.
DROP TABLE IF EXISTS v3_spatial.cell_summary;

-- 2. Spatial generation: the build envelope, keyed to the canonical generation.
CREATE TABLE v3_spatial.spatial_generation (
    spatial_generation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_generation_id uuid NOT NULL
        REFERENCES v3_meta.canonical_generation(generation_id),
    pyramid_version text NOT NULL
        CHECK(pyramid_version ~ '^[a-z][a-z0-9_]{0,62}$'),
    lifecycle_state text NOT NULL DEFAULT 'BUILDING'
        CHECK(lifecycle_state IN
              ('BUILDING','VALIDATING','READY','PUBLISHED','RETIRED','FAILED')),
    expected_systems bigint NOT NULL CHECK(expected_systems > 0),
    validation_receipt jsonb
        CHECK(validation_receipt IS NULL OR jsonb_typeof(validation_receipt)='object'),
    validation_sha256 bytea CHECK(validation_sha256 IS NULL OR octet_length(validation_sha256)=32),
    created_at timestamptz NOT NULL DEFAULT now(),
    validated_at timestamptz,
    published_at timestamptz,
    failed_at timestamptz,
    failure text,
    UNIQUE(canonical_generation_id, pyramid_version),
    CHECK(lifecycle_state <> 'READY' OR
          (validation_receipt IS NOT NULL AND validation_sha256 IS NOT NULL
           AND validated_at IS NOT NULL)),
    CHECK((lifecycle_state='FAILED')=(failed_at IS NOT NULL))
);

COMMENT ON TABLE v3_spatial.spatial_generation IS
    'Independently-published spatial density pyramid keyed to one canonical generation. Decoupled from the ratings derived_generation lifecycle.';

-- 3. Cell summary: pure-density cells for a spatial generation.
CREATE TABLE v3_spatial.cell_summary (
    spatial_generation_id uuid NOT NULL REFERENCES v3_spatial.spatial_generation,
    spatial_pyramid_version text NOT NULL,
    level smallint NOT NULL,
    cell_key text NOT NULL,
    system_count bigint NOT NULL CHECK(system_count > 0),
    representative_system_id64 bigint NOT NULL,
    origin_x_ly double precision NOT NULL,
    origin_y_ly double precision NOT NULL,
    origin_z_ly double precision NOT NULL,
    centroid_x_ly double precision NOT NULL,
    centroid_y_ly double precision NOT NULL,
    centroid_z_ly double precision NOT NULL,
    PRIMARY KEY(spatial_generation_id, level, cell_key),
    FOREIGN KEY(spatial_pyramid_version, level)
        REFERENCES v3_spatial.cell_level(spatial_pyramid_version, level)
);
CREATE INDEX cell_summary_gen_level
    ON v3_spatial.cell_summary(spatial_generation_id, level);

COMMENT ON COLUMN v3_spatial.cell_summary.representative_system_id64 IS
    'System nearest the cell data-centroid (tiebreak min(system_id64)); the density->real-star handoff for the map client.';

-- 4. Lifecycle guard on spatial_generation.
CREATE FUNCTION v3_spatial.guard_spatial_generation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(764004001);
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'spatial generations are retained';
    END IF;
    IF TG_OP='INSERT' THEN
        IF NEW.lifecycle_state<>'BUILDING'
           OR NEW.validation_receipt IS NOT NULL
           OR NEW.validated_at IS NOT NULL
           OR NEW.published_at IS NOT NULL
           OR NEW.failed_at IS NOT NULL THEN
            RAISE EXCEPTION 'new spatial generations must start BUILDING without receipts';
        END IF;
        RETURN NEW;
    END IF;
    -- UPDATE: validate the transition shape. Pointer integrity for
    -- PUBLISHED/RETIRED is enforced by publish_spatial_pyramid under the same
    -- advisory lock; here we only allow well-formed transitions.
    IF OLD.canonical_generation_id<>NEW.canonical_generation_id
       OR OLD.pyramid_version<>NEW.pyramid_version
       OR OLD.expected_systems<>NEW.expected_systems
       OR OLD.created_at<>NEW.created_at THEN
        RAISE EXCEPTION 'spatial generation identity is immutable';
    END IF;
    IF NOT (
        (OLD.lifecycle_state='BUILDING'  AND NEW.lifecycle_state IN ('VALIDATING','READY','FAILED'))
     OR (OLD.lifecycle_state='VALIDATING' AND NEW.lifecycle_state IN ('READY','FAILED'))
     OR (OLD.lifecycle_state='READY'      AND NEW.lifecycle_state IN ('PUBLISHED','RETIRED'))
     OR (OLD.lifecycle_state='PUBLISHED'  AND NEW.lifecycle_state='RETIRED')
     OR (OLD.lifecycle_state='RETIRED'    AND NEW.lifecycle_state='PUBLISHED')
    ) THEN
        RAISE EXCEPTION 'invalid spatial generation transition % -> %',
            OLD.lifecycle_state, NEW.lifecycle_state;
    END IF;
    IF NEW.lifecycle_state='READY' AND
       (NEW.validation_receipt IS NULL
        OR NEW.validation_receipt->>'status'<>'VERIFIED'
        OR NEW.validation_sha256 IS NULL
        OR NEW.validated_at IS NULL) THEN
        RAISE EXCEPTION 'READY spatial generation requires a VERIFIED validation receipt';
    END IF;
    IF NEW.lifecycle_state='FAILED' AND
       (NEW.failed_at IS NULL OR NEW.failure IS NULL OR btrim(NEW.failure)='') THEN
        RAISE EXCEPTION 'FAILED spatial generation requires failure evidence';
    END IF;
    IF NEW.lifecycle_state='PUBLISHED' AND NEW.published_at IS NULL THEN
        RAISE EXCEPTION 'PUBLISHED spatial generation requires published_at';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER guard_spatial_generation
BEFORE INSERT OR UPDATE OR DELETE ON v3_spatial.spatial_generation
FOR EACH ROW EXECUTE FUNCTION v3_spatial.guard_spatial_generation();

-- 5. Freeze cell_summary once its spatial generation is not mutable.
CREATE FUNCTION v3_spatial.guard_cell_summary()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE identifier uuid; base_state text;
BEGIN
    IF TG_OP='TRUNCATE' THEN
        RAISE EXCEPTION 'cell_summary is insert-only';
    END IF;
    FOR identifier IN
        SELECT DISTINCT spatial_generation_id FROM changed_rows ORDER BY 1
    LOOP
        SELECT lifecycle_state INTO base_state
          FROM v3_spatial.spatial_generation
         WHERE spatial_generation_id=identifier FOR SHARE;
        IF base_state NOT IN ('BUILDING','VALIDATING','READY') THEN
            RAISE EXCEPTION 'cell_summary for spatial generation % is immutable in state %',
                identifier, base_state;
        END IF;
    END LOOP;
    RETURN NULL;
END $$;

CREATE FUNCTION v3_spatial.reject_cell_summary_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'cell_summary rows are insert-only';
END $$;

CREATE TRIGGER cell_summary_insert
AFTER INSERT ON v3_spatial.cell_summary
REFERENCING NEW TABLE AS changed_rows
FOR EACH STATEMENT EXECUTE FUNCTION v3_spatial.guard_cell_summary();

CREATE TRIGGER cell_summary_update
BEFORE UPDATE ON v3_spatial.cell_summary
FOR EACH STATEMENT EXECUTE FUNCTION v3_spatial.reject_cell_summary_mutation();

CREATE TRIGGER cell_summary_delete
BEFORE DELETE ON v3_spatial.cell_summary
FOR EACH STATEMENT EXECUTE FUNCTION v3_spatial.reject_cell_summary_mutation();

CREATE TRIGGER cell_summary_truncate
BEFORE TRUNCATE ON v3_spatial.cell_summary
FOR EACH STATEMENT EXECUTE FUNCTION v3_spatial.reject_cell_summary_mutation();

COMMIT;
```

- [ ] **Step 4: Register the migration in the manifest**

Append `011_v3_spatial_pyramid_decouple.sql` to `sql/v3/migration-manifest.txt` on its own line, immediately after `010_v3_system_search_body_type_counts.sql` (match the exact existing format — bare filename, no path, if that is what the file uses; otherwise mirror the `010` line's format exactly).

- [ ] **Step 5: Apply the migration and run the tests**

Run:
```
DATABASE_URL=<disposable> bash scripts/apply_migrations.sh
DATABASE_URL=<disposable> python -m pytest tests/integration/test_spatial_generation_lifecycle.py -v
```
Expected: PASS (3 tests). If the disposable DB already had a prior 011 attempt, recreate it (drop/recreate the database) before applying, since migrations are apply-once via the ledger.

- [ ] **Step 6: Commit**

```bash
git add sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql sql/v3/migration-manifest.txt tests/integration/test_spatial_generation_lifecycle.py
git commit -m "feat(spatial): migration 011 canonical-keyed spatial pyramid tables + guards"
```

---

## Task 2: Migration 011 — publish pointer, audit, CAS function

**Files:**
- Modify: `sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql` (append before `COMMIT;`)
- Test: `tests/integration/test_spatial_publish.py` (create)

**Interfaces:**
- Consumes: `v3_spatial.spatial_generation`, `v3_meta.current_canonical_generation` (existing singleton with `generation_id`, `publication_sequence`).
- Produces: `v3_spatial.current_spatial_generation(singleton boolean PK, spatial_generation_id uuid, publication_sequence bigint, published_at timestamptz)`; `v3_spatial.spatial_publication_audit(...)`; function `v3_spatial.publish_spatial_pyramid(target_ uuid, expected_current_ uuid, expected_sequence_ bigint, expected_canonical_ uuid, actor_ text, reason_ text) RETURNS bigint`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_spatial_publish.py` (copy the `db_conn` fixture + `_seed_canonical` helper verbatim from Task 1's test, plus this helper and tests):

```python
def _ready_spatial_generation(conn, canonical_id, version='pyramid_v1', expected=1):
    """Insert a spatial_generation and force it READY with a minimal VERIFIED receipt."""
    sgid = conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,%s,%s) RETURNING spatial_generation_id", (canonical_id, version, expected),
    ).fetchone()[0]
    conn.execute(
        "UPDATE v3_spatial.spatial_generation "
        "SET lifecycle_state='READY',validation_receipt=%s::jsonb,validation_sha256=%s,validated_at=now() "
        "WHERE spatial_generation_id=%s",
        ('{"status":"VERIFIED"}', b'y' * 32, sgid),
    )
    return sgid


def _current_canonical(conn):
    return conn.execute(
        "SELECT generation_id, publication_sequence FROM v3_meta.current_canonical_generation WHERE singleton"
    ).fetchone()


def test_publish_requires_candidate_matches_current_canonical(db_conn):
    """A pyramid whose canonical != the live canonical pointer cannot publish."""
    other = _seed_canonical(db_conn)          # not the current canonical
    sgid = _ready_spatial_generation(db_conn, other)
    cur = _current_canonical(db_conn)
    if cur is None:
        pytest.skip('no current_canonical_generation seeded on this disposable DB')
    cur_ptr = db_conn.execute(
        "SELECT spatial_generation_id, publication_sequence FROM v3_spatial.current_spatial_generation WHERE singleton"
    ).fetchone()
    expected_current = cur_ptr[0] if cur_ptr else None
    expected_sequence = cur_ptr[1] if cur_ptr else 0
    with pytest.raises(psycopg.errors.RaiseException):
        db_conn.execute(
            "SELECT v3_spatial.publish_spatial_pyramid(%s,%s,%s,%s,%s,%s)",
            (sgid, expected_current, expected_sequence, cur[0], 'tester', 'unit test'),
        )


def test_publish_swaps_pointer_and_audits(db_conn):
    cur = _current_canonical(db_conn)
    if cur is None:
        pytest.skip('no current_canonical_generation seeded on this disposable DB')
    # Build a spatial generation for the *live* canonical generation.
    sgid = _ready_spatial_generation(db_conn, cur[0])
    cur_ptr = db_conn.execute(
        "SELECT spatial_generation_id, publication_sequence FROM v3_spatial.current_spatial_generation WHERE singleton"
    ).fetchone()
    expected_current = cur_ptr[0] if cur_ptr else None
    expected_sequence = cur_ptr[1] if cur_ptr else 0
    seq = db_conn.execute(
        "SELECT v3_spatial.publish_spatial_pyramid(%s,%s,%s,%s,%s,%s)",
        (sgid, expected_current, expected_sequence, cur[0], 'tester', 'unit test'),
    ).fetchone()[0]
    assert seq == expected_sequence + 1
    state = db_conn.execute(
        "SELECT lifecycle_state FROM v3_spatial.spatial_generation WHERE spatial_generation_id=%s", (sgid,),
    ).fetchone()[0]
    assert state == 'PUBLISHED'
    ptr = db_conn.execute(
        "SELECT spatial_generation_id FROM v3_spatial.current_spatial_generation WHERE singleton"
    ).fetchone()[0]
    assert str(ptr) == str(sgid)
    audit = db_conn.execute(
        "SELECT actor, reason FROM v3_spatial.spatial_publication_audit WHERE publication_sequence=%s", (seq,),
    ).fetchone()
    assert audit == ('tester', 'unit test')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=<disposable> python -m pytest tests/integration/test_spatial_publish.py -v`
Expected: FAIL — `v3_spatial.publish_spatial_pyramid` / `v3_spatial.current_spatial_generation` do not exist.

- [ ] **Step 3: Append pointer, audit, and CAS function to the migration**

Insert the following into `sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql` immediately **before** the final `COMMIT;`:

```sql
-- 6. Publish pointer + audit + CAS function.
CREATE TABLE v3_spatial.current_spatial_generation (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    spatial_generation_id uuid NOT NULL REFERENCES v3_spatial.spatial_generation,
    publication_sequence bigint NOT NULL,
    published_at timestamptz NOT NULL
);

CREATE TABLE v3_spatial.spatial_publication_audit (
    publication_sequence bigint PRIMARY KEY,
    previous_spatial_generation_id uuid,
    published_spatial_generation_id uuid NOT NULL,
    canonical_generation_id uuid NOT NULL,
    published_at timestamptz NOT NULL,
    actor text NOT NULL CHECK(btrim(actor) <> ''),
    reason text NOT NULL CHECK(btrim(reason) <> '')
);

CREATE FUNCTION v3_spatial.publish_spatial_pyramid(
    target_ uuid, expected_current_ uuid, expected_sequence_ bigint,
    expected_canonical_ uuid, actor_ text, reason_ text
) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE candidate_ v3_spatial.spatial_generation%ROWTYPE;
        current_ uuid; sequence_ bigint; canonical_ uuid;
BEGIN
    IF actor_ IS NULL OR btrim(actor_)='' OR reason_ IS NULL OR btrim(reason_)='' THEN
        RAISE EXCEPTION 'publication needs actor and reason';
    END IF;
    PERFORM pg_advisory_xact_lock(764004001);

    SELECT generation_id INTO canonical_
      FROM v3_meta.current_canonical_generation WHERE singleton FOR SHARE;
    IF canonical_ IS DISTINCT FROM expected_canonical_ THEN
        RAISE EXCEPTION 'canonical publication changed';
    END IF;

    SELECT spatial_generation_id, publication_sequence INTO current_, sequence_
      FROM v3_spatial.current_spatial_generation WHERE singleton FOR UPDATE;
    IF current_ IS DISTINCT FROM expected_current_
       OR COALESCE(sequence_,0)<>expected_sequence_ THEN
        RAISE EXCEPTION 'spatial publication changed';
    END IF;

    SELECT * INTO candidate_ FROM v3_spatial.spatial_generation
     WHERE spatial_generation_id=target_ FOR UPDATE;
    IF NOT FOUND
       OR candidate_.lifecycle_state NOT IN ('READY','RETIRED')
       OR candidate_.canonical_generation_id<>canonical_
       OR candidate_.validation_receipt->>'status'<>'VERIFIED' THEN
        RAISE EXCEPTION 'candidate is not a READY pyramid for the current canonical generation';
    END IF;

    sequence_ := COALESCE(sequence_,0)+1;
    IF current_ IS NOT NULL THEN
        UPDATE v3_spatial.spatial_generation SET lifecycle_state='RETIRED'
         WHERE spatial_generation_id=current_;
    END IF;
    UPDATE v3_spatial.spatial_generation
       SET lifecycle_state='PUBLISHED', published_at=now()
     WHERE spatial_generation_id=target_;
    INSERT INTO v3_spatial.current_spatial_generation
        VALUES(true, target_, sequence_, now())
    ON CONFLICT(singleton) DO UPDATE
        SET spatial_generation_id=EXCLUDED.spatial_generation_id,
            publication_sequence=EXCLUDED.publication_sequence,
            published_at=EXCLUDED.published_at;
    INSERT INTO v3_spatial.spatial_publication_audit
        VALUES(sequence_, current_, target_, canonical_, now(), actor_, reason_);
    RETURN sequence_;
END $$;
```

- [ ] **Step 4: Re-apply and run the tests**

Run (recreate the disposable DB first so 011 re-applies cleanly):
```
DATABASE_URL=<disposable> bash scripts/apply_migrations.sh
DATABASE_URL=<disposable> python -m pytest tests/integration/test_spatial_publish.py tests/integration/test_spatial_generation_lifecycle.py -v
```
Expected: PASS. (`RETIRED→PUBLISHED` rollback is allowed by the Task 1 guard, so re-publishing a prior generation succeeds.)

- [ ] **Step 5: Commit**

```bash
git add sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql tests/integration/test_spatial_publish.py
git commit -m "feat(spatial): migration 011 spatial publish pointer + CAS function"
```

---

## Task 3: Builder — canonical-density aggregation, reconcile, receipt

**Files:**
- Modify: `scripts/v3_spatial_pyramid.py` (rewrite the source/aggregation/reconcile/receipt sections; keep `CellLevel`, `CELL_LEVELS`, `PYRAMID_VERSION`, `register_cell_levels`, `_json`, `_digest`)
- Test: `tests/test_v3_spatial_pyramid.py` (rewrite for canonical fixtures)

**Interfaces:**
- Consumes: `v3_spatial.spatial_generation`, `v3_spatial.cell_summary`, `v3_spatial.cell_level`, canonical `{gen}.systems`.
- Produces (Python API used by Task 4/5):
  - `canonical_schema_for_spatial(conn, spatial_generation_id) -> str`
  - `canonical_system_count(conn, spatial_generation_id) -> int`
  - `build_all_levels(conn, *, spatial_generation_id, version=PYRAMID_VERSION) -> dict[int,int]`
  - `class ReconciliationError(Exception)`
  - `reconcile(conn, *, spatial_generation_id, version, canonical_count) -> dict`
  - `build_receipt(conn, *, spatial_generation_id, version, canonical_count, per_level) -> dict`

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_v3_spatial_pyramid.py`. Keep the `db_conn` fixture; replace `_seed_generation` with a canonical-systems seeder and rewrite the build/reconcile tests:

```python
def _seed_spatial(conn, *, systems=None):
    """Seed a canonical_generation + a real {gen}.systems relation + a
    BUILDING spatial_generation. Returns (spatial_generation_id, schema, count).

    Only the columns the builder reads (system_id64, x_ly, y_ly, z_ly) are
    created on the fixture systems table; the real relation has more, but the
    builder never selects them.
    """
    import uuid
    from psycopg import sql

    gid, run_id = uuid.uuid4(), uuid.uuid4()
    key = 'spx_' + gid.hex[:16]
    schema = 'v3_gen_' + key
    source_id = conn.execute(
        "INSERT INTO v3_source.source(source_code,display_name,authority_class) "
        "VALUES(%s,'Fixture','OPERATOR_ADJUDICATION') RETURNING source_id", (key,),
    ).fetchone()[0]
    rights_id = conn.execute(
        "INSERT INTO v3_source.source_rights_policy(source_id,policy_version,rights_class,retention_class,effective_at) "
        "VALUES(%s,'test','CANONICAL_ELIGIBLE','TEST',now()) RETURNING rights_policy_id", (source_id,),
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO v3_source.source_run(source_run_id,source_id,rights_policy_id,acquisition_kind,trust_zone,
               run_state,idempotency_key,started_at,completed_at,importer_version,importer_code_sha256,
               importer_config_sha256,normalizer_version,normalizer_sha256)
           VALUES(%s,%s,%s,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',%s,now(),now(),'test',%s,%s,'test',%s)""",
        (run_id, source_id, rights_id, key, b'x' * 32, b'x' * 32, b'x' * 32),
    )
    conn.execute(
        "INSERT INTO v3_meta.canonical_generation(generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id) "
        "VALUES(%s,%s,%s,%s,%s)", (gid, key, schema, b'x' * 32, run_id),
    )
    conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    conn.execute(sql.SQL(
        'CREATE TABLE {}.systems (system_id64 bigint PRIMARY KEY, '
        'x_ly double precision NOT NULL, y_ly double precision NOT NULL, z_ly double precision NOT NULL)'
    ).format(sql.Identifier(schema)))
    if systems is None:
        systems = [(1001, 10.0, 10.0, 10.0), (1002, 20.0, 20.0, 20.0), (1003, 150.0, 0.0, 0.0)]
    for sid, x, y, z in systems:
        conn.execute(
            sql.SQL('INSERT INTO {}.systems(system_id64,x_ly,y_ly,z_ly) VALUES(%s,%s,%s,%s)').format(sql.Identifier(schema)),
            (sid, x, y, z),
        )
    sgid = conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',%s) RETURNING spatial_generation_id", (gid, len(systems)),
    ).fetchone()[0]
    return str(sgid), schema, len(systems)


_TEST_LEVEL = 30
_TEST_SIZE = 100.0


def _register_test_level(conn, version='pyramid_v1'):
    conn.execute(
        "INSERT INTO v3_spatial.cell_level(spatial_pyramid_version,level,cell_size_ly,intended_scale) "
        "VALUES(%s,%s,%s,'test') ON CONFLICT DO NOTHING", (version, _TEST_LEVEL, _TEST_SIZE),
    )


def test_build_level_aggregates_density_and_centroid(db_conn):
    from scripts.v3_spatial_pyramid import build_level
    sgid, _schema, _n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    n = build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                    level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    assert n == 2  # (10,10,10)+(20,20,20) share one cell; (150,0,0) is another
    cell = db_conn.execute(
        "SELECT system_count, representative_system_id64, centroid_x_ly "
        "FROM v3_spatial.cell_summary WHERE spatial_generation_id=%s AND cell_key='0.0.0'", (sgid,),
    ).fetchone()
    assert cell[0] == 2
    assert cell[1] == 1001            # nearest the (15,15,15) centroid; tiebreak min id
    assert abs(cell[2] - 15.0) < 1e-9


def test_reconcile_passes_when_sum_matches_canonical(db_conn):
    from scripts.v3_spatial_pyramid import build_level, reconcile, canonical_system_count
    sgid, _schema, n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    count = canonical_system_count(db_conn, sgid)
    assert count == n
    result = reconcile(db_conn, spatial_generation_id=sgid, version='pyramid_v1', canonical_count=count)
    assert result['per_level_system_sum'][_TEST_LEVEL] == n


def test_reconcile_fails_closed_on_short_level(db_conn):
    from scripts.v3_spatial_pyramid import build_level, reconcile, ReconciliationError
    sgid, _schema, n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    with pytest.raises(ReconciliationError):
        reconcile(db_conn, spatial_generation_id=sgid, version='pyramid_v1', canonical_count=n + 1)
```

(Delete the old `system_search`-based tests, the `omit_last` fixtures, and any assertions on `landable_count`/`station_count`/`biological_system_count`/`terraformable_system_count`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=<disposable> python -m pytest tests/test_v3_spatial_pyramid.py -v`
Expected: FAIL — `build_level` still has the old `derived_generation_id`/`source` signature and reads `system_search`; `canonical_system_count` is undefined.

- [ ] **Step 3: Rewrite the builder's schema/aggregation/reconcile/receipt**

In `scripts/v3_spatial_pyramid.py`:

(a) Update the module docstring and drop `PRODUCT_CODE`, `resolve_source`, `_CELL_SUMMARY_INSERT_FROM_SYSTEM_SEARCH`, `_build_level_canonical`, `_canonical_schema`, `_pyramid_product`, `_pyramid_manifest`, and `pyramid_for_current_generation` (the last three move/reshape in Task 4). Keep `CellLevel`, `CELL_LEVELS`, `PYRAMID_VERSION`, `register_cell_levels`, `_json`, `_digest`, `SCHEMA_NAME`.

(b) Add the canonical resolver + count:

```python
def canonical_schema_for_spatial(conn, spatial_generation_id) -> str:
    '''Resolve the canonical relation schema for a spatial generation via its
    canonical_generation_id. Validated against SCHEMA_NAME to keep the schema
    safe to interpolate as an identifier.'''
    row = conn.execute(
        '''SELECT cg.relation_schema
             FROM v3_spatial.spatial_generation sg
             JOIN v3_meta.canonical_generation cg
               ON cg.generation_id = sg.canonical_generation_id
            WHERE sg.spatial_generation_id = %s''',
        (spatial_generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown spatial generation')
    schema = row[0]
    if not isinstance(schema, str) or not SCHEMA_NAME.fullmatch(schema):
        raise ValueError('unsafe canonical generation relation schema')
    return schema


def canonical_system_count(conn, spatial_generation_id) -> int:
    from psycopg import sql
    schema = canonical_schema_for_spatial(conn, spatial_generation_id)
    return int(conn.execute(
        sql.SQL('SELECT count(*) FROM {}.systems').format(sql.Identifier(schema)),
    ).fetchone()[0])
```

(c) Replace `build_level`/`build_all_levels` with a canonical-only, spatial-keyed aggregation. The representative star is the system nearest the cell data-centroid, tiebreak `min(system_id64)`:

```python
def build_level(conn, *, spatial_generation_id, version, level, cell_size_ly) -> int:
    '''Aggregate one level's occupied cells from the canonical {gen}.systems
    catalogue into v3_spatial.cell_summary (insert-only). Pure density:
    system_count = COUNT(*); representative = system nearest the cell
    data-centroid (tiebreak min(system_id64)). Returns rows inserted.'''
    from psycopg import sql
    schema = canonical_schema_for_spatial(conn, spatial_generation_id)
    stmt = sql.SQL('''
        INSERT INTO v3_spatial.cell_summary
          (spatial_generation_id, spatial_pyramid_version, level, cell_key,
           origin_x_ly, origin_y_ly, origin_z_ly, system_count,
           centroid_x_ly, centroid_y_ly, centroid_z_ly, representative_system_id64)
        WITH pts AS (
            SELECT system_id64, x_ly, y_ly, z_ly,
                   floor(x_ly/%(sz)s)::bigint AS ix,
                   floor(y_ly/%(sz)s)::bigint AS iy,
                   floor(z_ly/%(sz)s)::bigint AS iz
              FROM {schema}.systems
        ), agg AS (
            SELECT ix, iy, iz, count(*) AS n,
                   avg(x_ly) AS cx, avg(y_ly) AS cy, avg(z_ly) AS cz
              FROM pts GROUP BY ix, iy, iz
        ), rep AS (
            SELECT DISTINCT ON (p.ix, p.iy, p.iz)
                   p.ix, p.iy, p.iz, p.system_id64
              FROM pts p JOIN agg a USING (ix, iy, iz)
             ORDER BY p.ix, p.iy, p.iz,
                   ((p.x_ly-a.cx)^2 + (p.y_ly-a.cy)^2 + (p.z_ly-a.cz)^2),
                   p.system_id64
        )
        SELECT %(gen)s, %(ver)s, %(lvl)s,
               a.ix || '.' || a.iy || '.' || a.iz,
               a.ix*%(sz)s, a.iy*%(sz)s, a.iz*%(sz)s,
               a.n, a.cx, a.cy, a.cz, r.system_id64
          FROM agg a JOIN rep r USING (ix, iy, iz)
    ''').format(schema=sql.Identifier(schema))
    cur = conn.execute(stmt, {
        'gen': spatial_generation_id, 'ver': version, 'lvl': level, 'sz': cell_size_ly,
    })
    return cur.rowcount


def build_all_levels(conn, *, spatial_generation_id, version: str = PYRAMID_VERSION) -> dict[int, int]:
    counts: dict[int, int] = {}
    for lvl in CELL_LEVELS:
        counts[lvl.level] = build_level(
            conn, spatial_generation_id=spatial_generation_id, version=version,
            level=lvl.level, cell_size_ly=lvl.cell_size_ly,
        )
    return counts
```

(d) Update `reconcile` and `build_receipt` to key on `spatial_generation_id` (replace `derived_generation_id` throughout; the reconcile query becomes `WHERE spatial_generation_id=%s AND spatial_pyramid_version=%s`). `build_receipt` reads the canonical generation id + `now()` from `v3_spatial.spatial_generation JOIN v3_meta.canonical_generation`, and drops the `source` field (there is only one source now — record `'source': 'canonical-catalogue'`). Keep the "re-run reconcile inside build_receipt" fail-closed behaviour and the empty-levels guard.

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL=<disposable> python -m pytest tests/test_v3_spatial_pyramid.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check scripts/v3_spatial_pyramid.py
git add scripts/v3_spatial_pyramid.py tests/test_v3_spatial_pyramid.py
git commit -m "feat(spatial): builder aggregates canonical density keyed to spatial_generation"
```

---

## Task 4: Builder — spatial_generation lifecycle helpers

**Files:**
- Modify: `scripts/v3_spatial_pyramid.py` (add lifecycle helpers)
- Test: `tests/test_v3_spatial_pyramid.py` (add lifecycle tests)

**Interfaces:**
- Consumes: Task 3's `build_all_levels`, `reconcile`, `build_receipt`, `canonical_system_count`; `register_cell_levels`.
- Produces:
  - `mark_pyramid_ready(conn, *, spatial_generation_id, version, receipt) -> None` (BUILDING/VALIDATING → READY on the `spatial_generation` row, storing the VERIFIED receipt + sha)
  - `spatial_pyramid_for_current(conn) -> tuple | None` → `(spatial_generation_id, pyramid_version, canonical_generation_id, expected_systems, validated_at)` for the currently published spatial generation, else `None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_v3_spatial_pyramid.py`:

```python
def test_mark_pyramid_ready_transitions_and_is_idempotent(db_conn):
    from scripts.v3_spatial_pyramid import (
        register_cell_levels, build_level, build_receipt, canonical_system_count,
        mark_pyramid_ready,
    )
    sgid, _schema, n = _seed_spatial(db_conn)
    register_cell_levels(db_conn, 'pyramid_v1')
    _register_test_level(db_conn)
    build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    # Build the real ladder levels too so reconcile's expected set is satisfied.
    from scripts.v3_spatial_pyramid import build_all_levels
    build_all_levels(db_conn, spatial_generation_id=sgid, version='pyramid_v1')
    count = canonical_system_count(db_conn, sgid)
    receipt = build_receipt(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                            canonical_count=count, per_level={})
    mark_pyramid_ready(db_conn, spatial_generation_id=sgid, version='pyramid_v1', receipt=receipt)
    state = db_conn.execute(
        "SELECT lifecycle_state FROM v3_spatial.spatial_generation WHERE spatial_generation_id=%s", (sgid,),
    ).fetchone()[0]
    assert state == 'READY'
    # idempotent no-op
    mark_pyramid_ready(db_conn, spatial_generation_id=sgid, version='pyramid_v1', receipt=receipt)


def test_mark_pyramid_ready_rejects_unreconciled_receipt(db_conn):
    from scripts.v3_spatial_pyramid import mark_pyramid_ready
    sgid, _schema, _n = _seed_spatial(db_conn)
    with pytest.raises(ValueError):
        mark_pyramid_ready(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                           receipt={'reconciliation': 'not-run'})
```

Note: because `_register_test_level` adds level 30, `build_all_levels` (levels 0–6) plus the test level means reconcile must see all registered levels summed to `count`. The test seeds only 3 systems, so every level's Σ == 3 == canonical count; this holds for both the 0–6 ladder and level 30. (`register_cell_levels` + `_register_test_level` together define the expected set.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=<disposable> python -m pytest tests/test_v3_spatial_pyramid.py -k pyramid_ready -v`
Expected: FAIL — `mark_pyramid_ready` not defined with this signature.

- [ ] **Step 3: Implement the lifecycle helpers**

Add to `scripts/v3_spatial_pyramid.py`:

```python
def mark_pyramid_ready(conn, *, spatial_generation_id, version: str, receipt: dict) -> None:
    '''Transition the spatial_generation BUILDING/VALIDATING -> READY, storing
    the VERIFIED validation receipt + its sha. Requires an already-reconciled
    build_receipt (receipt['reconciliation'] == 'passed') with a positive
    canonical_count. Idempotent: a no-op when the row is already READY with a
    matching validation receipt. Parameterised SQL only.'''
    if not isinstance(receipt, dict) or receipt.get('reconciliation') != 'passed':
        raise ValueError('mark_pyramid_ready requires a reconciled build_receipt (reconciliation == "passed")')
    canonical_count = receipt.get('canonical_count')
    if not isinstance(canonical_count, int) or isinstance(canonical_count, bool) or canonical_count <= 0:
        raise ValueError('receipt canonical_count must be a positive integer')

    row = conn.execute(
        '''SELECT lifecycle_state, pyramid_version
             FROM v3_spatial.spatial_generation WHERE spatial_generation_id=%s''',
        (spatial_generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown spatial generation')
    state, existing_version = row
    if existing_version != version:
        raise ValueError('spatial generation pyramid_version differs from build version')
    if state == 'READY':
        return  # idempotent no-op
    if state not in ('BUILDING', 'VALIDATING'):
        raise ValueError(f'spatial generation cannot become READY from state {state!r}')

    validation_receipt = {**receipt, 'status': 'VERIFIED'}
    validation_sha = _digest(validation_receipt)
    with conn.transaction():
        updated = conn.execute(
            '''UPDATE v3_spatial.spatial_generation
                  SET lifecycle_state='READY', validation_receipt=%s::jsonb,
                      validation_sha256=%s, validated_at=now()
                WHERE spatial_generation_id=%s
                  AND lifecycle_state IN ('BUILDING','VALIDATING')''',
            (_json(validation_receipt), validation_sha, spatial_generation_id),
        ).rowcount
        if updated != 1:
            raise ValueError('spatial generation READY transition failed')


def spatial_pyramid_for_current(conn) -> tuple | None:
    '''Return (spatial_generation_id, pyramid_version, canonical_generation_id,
    expected_systems, validated_at) for the currently published spatial
    generation, or None. Mirrors the API read exactly.'''
    row = conn.execute(
        '''SELECT c.spatial_generation_id, sg.pyramid_version,
                  sg.canonical_generation_id, sg.expected_systems, sg.validated_at
             FROM v3_spatial.current_spatial_generation c
             JOIN v3_spatial.spatial_generation sg USING (spatial_generation_id)
            WHERE sg.lifecycle_state='PUBLISHED' ''',
    ).fetchone()
    if row is None:
        return None
    return tuple(row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL=<disposable> python -m pytest tests/test_v3_spatial_pyramid.py -v`
Expected: PASS (all builder tests).

- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check scripts/v3_spatial_pyramid.py
git add scripts/v3_spatial_pyramid.py tests/test_v3_spatial_pyramid.py
git commit -m "feat(spatial): spatial_generation lifecycle + current-pyramid resolver"
```

---

## Task 5: Operator script + workflow — pin canonical, build + publish

**Files:**
- Rewrite: `scripts/operator/actions/v3-spatial-pyramid.sh`
- Modify: `.github/workflows/v3-spatial-pyramid.yml`
- Test: `tests/test_v3_spatial_pyramid_operator_contract.py` (create — a static contract test, no SSH/prod)

**Interfaces:**
- Consumes: builder Python API (Tasks 3–4); `v3_spatial.publish_spatial_pyramid` (Task 2).
- Produces: two governed sub-commands — `build <stage> <source_sha>` and `publish <stage> <source_sha>` — both fail-closed on host/context identity and target confirmation.

**Context:** This is governed prod tooling; it cannot be run against prod from a coding task. The test is a **static contract** asserting the script pins the canonical generation, gates the migration hash on migration 011, and wires the publish path — mirroring the repo's existing "Script contracts + migration paths" CI lane. Do not add SSH or DB calls to the test.

- [ ] **Step 1: Write the failing contract test**

Create `tests/test_v3_spatial_pyramid_operator_contract.py`:

```python
"""Static contract for the governed spatial-pyramid operator script.

No SSH, no DB, no prod: reads the script text and asserts it pins the canonical
generation, gates on migration 011, and exposes build + publish sub-commands.
"""
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'operator' / 'actions' / 'v3-spatial-pyramid.sh'


def test_script_exists():
    assert _SCRIPT.is_file()


def test_pins_canonical_generation_not_ratings_key():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert 'TARGET_CANONICAL_GENERATION=' in text
    assert 'TARGET_CANONICAL_SEQUENCE=' in text
    # The decoupled build must NOT pin a ratings derived generation_key.
    assert 'ratings_v4_prod_p4_opt1' not in text
    assert 'TARGET_GENERATION_KEY' not in text


def test_gates_on_migration_011():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert '011_v3_spatial_pyramid_decouple.sql' in text


def test_exposes_build_and_publish_commands():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert 'publish_spatial_pyramid' in text
    assert ' build)' in text or 'build)' in text
    assert ' publish)' in text or 'publish)' in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_v3_spatial_pyramid_operator_contract.py -v`
Expected: FAIL — the current script still pins `TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"` and has no publish command.

- [ ] **Step 3: Rewrite the operator script**

Rewrite `scripts/operator/actions/v3-spatial-pyramid.sh` preserving the existing fail-closed frame (host/fqdn/docker-context assertions, single running API slot check, migration-hash preconditions, `db_query` helper, receipt fields) but:

- Replace the pinned constants:
  ```bash
  TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"
  TARGET_CANONICAL_SEQUENCE="4"
  TARGET_EXPECTED_SYSTEMS="198528286"
  PYRAMID_VERSION="pyramid_v1"
  SPATIAL_MIGRATION_NAME="011_v3_spatial_pyramid_decouple.sql"
  SPATIAL_MIGRATION_SHA="<sha256 of the committed migration 011, LF>"
  ```
  (Compute the SHA with `sha256sum sql/v3/migrations/011_v3_spatial_pyramid_decouple.sql` on the committed LF file and paste it. Drop the `006` lifecycle pin — it no longer governs the pyramid.)
- `resolve_pinned_canonical()`: `SELECT generation_id FROM v3_meta.current_canonical_generation WHERE singleton` and assert it equals `TARGET_CANONICAL_GENERATION`; assert its `publication_sequence` == `TARGET_CANONICAL_SEQUENCE`; assert `SELECT count(*) FROM <schema>.systems` == `TARGET_EXPECTED_SYSTEMS` (resolve `<schema>` from `v3_meta.canonical_generation.relation_schema`). Fail closed on any mismatch.
- `build` sub-command: create (or resolve an existing BUILDING) `spatial_generation` for `(TARGET_CANONICAL_GENERATION, PYRAMID_VERSION)`; run, in one Python process against the container DB, `register_cell_levels → build_all_levels → build_receipt → mark_pyramid_ready` (import from `scripts/v3_spatial_pyramid.py`, staged under the trusted checkout). Idempotent: if a READY spatial_generation already exists for `(canonical, version)`, print `result=already-ready` and exit 0. Emit the safety receipt (`publication_performed=false`, `canonical_writes_performed=false`).
- `publish` sub-command: read the current spatial pointer + sequence and the live canonical id inside one DB session, then call `SELECT v3_spatial.publish_spatial_pyramid(<target_sgid>, <expected_current>, <expected_sequence>, <expected_canonical>, <actor>, <reason>)`. `<actor>`/`<reason>` come from operator-supplied environment inputs (validated non-empty). Emit `publication_performed=true` in the receipt only on success.
- Keep parameterised SQL; no secrets in logs; the `main` case dispatches `build`/`publish` and rejects anything else (`*) fail "expected build or publish" ;;`).

- [ ] **Step 4: Update the workflow**

In `.github/workflows/v3-spatial-pyramid.yml`, add a `workflow_dispatch` `operation` choice input with options `build` and `publish` (default `build`), and `actor`/`reason` string inputs used only by `publish`. Pass the chosen sub-command to the staged script (`"bash -s -- $OPERATION '$stage' '$source_sha'"`), forwarding `SPATIAL_PYRAMID_ACTOR`/`SPATIAL_PYRAMID_REASON` env for the publish path. Keep the literal target confirmation, exact-main pin, pinned SSH trust, and `persist-credentials: false` exactly as they are.

- [ ] **Step 5: Run the contract test + shellcheck**

Run:
```
python -m pytest tests/test_v3_spatial_pyramid_operator_contract.py -v
shellcheck scripts/operator/actions/v3-spatial-pyramid.sh
```
Expected: tests PASS; shellcheck clean (or only pre-existing, unrelated advisories — match the prior script's shellcheck posture).

- [ ] **Step 6: Commit**

```bash
git add scripts/operator/actions/v3-spatial-pyramid.sh .github/workflows/v3-spatial-pyramid.yml tests/test_v3_spatial_pyramid_operator_contract.py
git commit -m "feat(spatial): governed build+publish workflow pins canonical generation"
```

---

## Task 6: Map API rewire + response contract + OpenAPI

**Files:**
- Modify: `apps/api/src/routers/map.py:179-362` (the pyramid resolve + serve path)
- Test: `tests/integration/test_map_heatmap_pyramid.py` (rewrite the pyramid-path assertions)
- Regenerate: `apps/web/src/lib/api/` (OpenAPI types)

**Interfaces:**
- Consumes: `v3_spatial.current_spatial_generation`, `v3_spatial.spatial_generation`, `v3_spatial.cell_summary` (Tasks 1–2); mirrors `spatial_pyramid_for_current` (Task 4).
- Produces: `/api/map/heatmap` response with `source:"pyramid"`, `generation_id` = **canonical** generation id, `spatial_generation_id`, `pyramid_version`, `source_system_count`, `coverage_at`, and per-cell `{origin_*_ly, centroid_*_ly, system_count, representative_system_id64}`. No aux-counter fields. Legacy fallback unchanged (`source:"legacy-fallback"`).

- [ ] **Step 1: Write the failing test**

Rewrite the pyramid-path test in `tests/integration/test_map_heatmap_pyramid.py` to build a tiny spatial generation, publish it, and assert the new shape. Add (reusing that file's existing app/client + disposable-DB setup; if it seeds via SQL, seed a `spatial_generation` + `cell_summary` + publish through `v3_spatial.publish_spatial_pyramid`):

```python
def test_heatmap_serves_published_spatial_pyramid(api_client, db_conn):
    # Build + publish a 1-cell pyramid for the live canonical generation.
    cur = db_conn.execute(
        "SELECT generation_id FROM v3_meta.current_canonical_generation WHERE singleton"
    ).fetchone()
    if cur is None:
        pytest.skip('no current canonical generation on this disposable DB')
    canonical_id = cur[0]
    db_conn.execute(
        "INSERT INTO v3_spatial.cell_level(spatial_pyramid_version,level,cell_size_ly,intended_scale) "
        "VALUES('pyramid_v1',0,2560.0,'wide') ON CONFLICT DO NOTHING",
    )
    sgid = db_conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',1) RETURNING spatial_generation_id", (canonical_id,),
    ).fetchone()[0]
    db_conn.execute(
        "INSERT INTO v3_spatial.cell_summary(spatial_generation_id,spatial_pyramid_version,level,cell_key,"
        "system_count,representative_system_id64,origin_x_ly,origin_y_ly,origin_z_ly,"
        "centroid_x_ly,centroid_y_ly,centroid_z_ly) "
        "VALUES(%s,'pyramid_v1',0,'0.0.0',42,777,0,0,0,10,10,10)", (sgid,),
    )
    db_conn.execute(
        "UPDATE v3_spatial.spatial_generation SET lifecycle_state='READY',"
        "validation_receipt='{\"status\":\"VERIFIED\"}'::jsonb,validation_sha256=%s,validated_at=now() "
        "WHERE spatial_generation_id=%s", (b'z' * 32, sgid),
    )
    db_conn.execute(
        "SELECT v3_spatial.publish_spatial_pyramid(%s,NULL,0,%s,'tester','integration')",
        (sgid, canonical_id),
    )
    db_conn.commit()

    resp = api_client.get('/api/map/heatmap?voxel_size=2000&min_systems=1')
    body = resp.json()
    assert body['source'] == 'pyramid'
    assert body['generation_id'] == str(canonical_id)
    assert body['spatial_generation_id'] == str(sgid)
    assert body['pyramid_version'] == 'pyramid_v1'
    assert body['cells'][0]['representative_system_id64'] == 777
    assert 'landable_count' not in body['cells'][0]
```

(This test commits, so pair it with a teardown that deletes the seeded spatial rows, or run it against a disposable DB that is dropped after the suite. Follow whatever commit/cleanup convention the existing pyramid integration test already uses.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `DATABASE_URL=<disposable> python -m pytest tests/integration/test_map_heatmap_pyramid.py -k published_spatial -v`
Expected: FAIL — `_current_spatial_pyramid` still queries `v3_meta.current_derived_generation`/`derived_product`.

- [ ] **Step 3: Rewire `map.py`**

Replace `_current_spatial_pyramid` (lines ~179-208):

```python
async def _current_spatial_pyramid(conn: asyncpg.Connection) -> Optional[asyncpg.Record]:
    """Resolve the currently published spatial density pyramid: the
    v3_spatial.spatial_generation (lifecycle_state='PUBLISHED') referenced by
    v3_spatial.current_spatial_generation. Mirrors
    scripts/v3_spatial_pyramid.py:spatial_pyramid_for_current. Returns None
    (serve the legacy fallback) when the schema is absent or nothing qualifies.
    """
    try:
        return await conn.fetchrow(
            '''SELECT sg.spatial_generation_id,
                      sg.pyramid_version AS spatial_pyramid_version,
                      sg.canonical_generation_id,
                      sg.expected_systems AS source_system_count,
                      sg.validated_at AS coverage_at
                 FROM v3_spatial.current_spatial_generation c
                 JOIN v3_spatial.spatial_generation sg USING (spatial_generation_id)
                WHERE sg.lifecycle_state = 'PUBLISHED' '''
        )
    except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.InvalidSchemaNameError):
        return None
```

Update `SPATIAL_PYRAMID_PRODUCT_CODE` usage: it is no longer needed — remove the constant and its comment (lines ~21-25) since the pyramid is no longer a derived product.

In `map_heatmap`, update the pyramid branch (lines ~304-362):
- WHERE conditions key on `spatial_generation_id = $1 AND spatial_pyramid_version = $2 AND level = $3 AND system_count >= $4` (replace `derived_generation_id`).
- args[0] becomes `pyramid['spatial_generation_id']`.
- SELECT drops `landable_count, station_count, biological_system_count, terraformable_system_count` and adds `representative_system_id64`.
- The result dict: `'generation_id': str(pyramid['canonical_generation_id'])`, add `'spatial_generation_id': str(pyramid['spatial_generation_id'])`, keep `spatial_pyramid_version`, `source_system_count`, `coverage_at`.
- `_pyramid_level` is unchanged (still keyed by `spatial_pyramid_version`).

- [ ] **Step 4: Run the API test + regenerate OpenAPI types**

Run:
```
DATABASE_URL=<disposable> python -m pytest tests/integration/test_map_heatmap_pyramid.py -v
cd apps/web && pnpm install --frozen-lockfile && pnpm generate:api && pnpm check
```
Expected: pytest PASS; `pnpm generate:api` updates `apps/web/src/lib/api/` to the new heatmap shape with no drift left; `pnpm check` passes. (If the repo's OpenAPI check is a diff gate, commit the regenerated files.)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/routers/map.py tests/integration/test_map_heatmap_pyramid.py apps/web/src/lib/api/
git commit -m "feat(spatial): map heatmap serves canonical-keyed decoupled pyramid"
```

---

## Final validation (before opening the PR)

- [ ] Run the full focused backend suite for touched surfaces:
  `DATABASE_URL=<disposable> python -m pytest tests/test_v3_spatial_pyramid.py tests/integration/test_spatial_generation_lifecycle.py tests/integration/test_spatial_publish.py tests/integration/test_map_heatmap_pyramid.py tests/test_v3_spatial_pyramid_operator_contract.py -v`
- [ ] `make state-check`
- [ ] `python -m ruff check scripts/ apps/api/`
- [ ] `cd apps/web && pnpm check && pnpm build`
- [ ] Confirm no production DSN/host appears in any diff; the migration is applied only to disposable DBs in this work.

## Follow-ups (separate PR, not this plan)

- Correct `docs/ROADMAP.md` #2a line + `project_map_identity_programme` memory to the decoupled model and the `parallel_v1` published / `opt1` paused production reality.
- Optional: a ratings-derived aux-counter overlay product (landable/stations/biologicals/terraformable) as a separate spatial artifact.
