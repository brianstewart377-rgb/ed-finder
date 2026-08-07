# Bodies Composite Identity Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status as of 2026-08-07 (verified, not assumed — re-ran Task 0's own checks)

- **Task 1: merged but NOT applied to production.** `sql/041_bodies_composite_identity_index.sql` exists, is registered in `sql/migration-manifest.txt` (`|manual`), and shipped in PR #411 (commit `59bf8ac0`). Directly queried production tonight: `idx_bodies_system_id64_id` does not exist yet (`SELECT indexname FROM pg_indexes WHERE tablename='bodies' AND indexname='idx_bodies_system_id64_id'` → 0 rows). This is the next concrete action — a monitored `CREATE INDEX CONCURRENTLY` run against the live ~573M-row table, per the Production Rollout Runbook below. Nothing else in this plan can proceed before this is confirmed built and valid.
- **Tasks 2-6: not started.** `sql/001_schema.sql` still shows bare `id BIGINT PRIMARY KEY` on `bodies`. `apps/eddn/src/eddn_listener.py` still writes `ON CONFLICT (id)`. `apps/importer/src/import_spansh.py:954` still calls `upsert_via_temp(conn, 'bodies', BODY_COLS, body_batch, 'id', ...)` — bare string conflict target, not yet `['id', 'system_id64']`.
- **The "Known issues in Tasks 2-5" section below is still unresolved** — Task 2/3 as currently drafted have not been corrected for any of the 4 issues listed. Do not execute Task 2 or Task 3 as literally written without applying those corrections first; this was deliberately left as a to-do rather than silently patched into the task bodies during this status check, since resolving FK-cascade SQL on a 573M-row table's dependent tables deserves focused attention in the session that actually executes it, not a tail-end edit. One piece of groundwork *is* done: the Postgres 16 column-list syntax issue 2 depends on (`ON DELETE SET NULL (body_id)`) was verified directly against a real Postgres 16 instance tonight and confirmed to work as expected (parent-row delete nulled only the named column, left the sibling `NOT NULL` column untouched).
- Recommend whoever picks this up next also re-decide the resolution to issue 3 (schema/writer deploy gap) explicitly before writing Task 2's SQL — the plan currently doesn't commit to either of its own two offered options (temporary `UNIQUE (id)` constraint vs. atomic schema+writer deploy).

**Goal:** Replace `bodies.id BIGINT PRIMARY KEY` (a source-supplied id with no sequence, currently guarded but not truly fixed against cross-system collisions) with a composite `(system_id64, id)` identity, so that two different systems whose bodies coincidentally share the same numeric id — which happens routinely because the Elite Dangerous journal's `BodyID` field is only unique *within* a system — can both be stored correctly instead of one silently colliding with the other.

**Architecture:** `bodies.id` stops being globally unique and starts being unique only within a system, matching the pattern this codebase already uses successfully for `body_scan_facts` and `body_slot_predictions` (`PRIMARY KEY (system_address, body_id)`), and matching how every existing consumer of `bodies.id` already reads it (every join site found in this repo already scopes by `system_id64` alongside `body_id`/`bodies.id` — see Task 0 for the full audit). The three FK-dependent tables (`body_rings`, `attractions`, `station_body_links`) already carry their own `system_id64` column, so their foreign keys become composite too, with no new columns needed. Because the *existing* 573M rows in `bodies` are already globally unique (the current PK enforces it), this migration needs **no data backfill** — it is purely a constraint-shape change, built non-blocking via `CREATE INDEX CONCURRENTLY` (this codebase already has 8 precedents for that pattern, including on a comparably large table: `sql/039_ratings_score_viable_index.sql` against the ~189M-row `ratings` table).

**Tech Stack:** PostgreSQL 16, asyncpg (eddn listener), psycopg2 (Spansh importer), pytest + real local Postgres for regression tests.

## Global Constraints

- No canonical database write lane changes may deploy without going through this repo's normal PR → CI → explicit-owner-approved-deploy sequence (`CLAUDE.md` "Frontend deployment" section describes the general shape; there is no equivalent "backend deploy" doc, so treat `scripts/deploy_main.sh` + explicit owner go-ahead as the only sanctioned path — never edit production directly).
- Migration sessions default to `MIGRATION_STATEMENT_TIMEOUT=1h` / `MIGRATION_LOCK_TIMEOUT=30s` (`scripts/apply_migrations.sh`). `CREATE INDEX CONCURRENTLY` does not hold a long lock and is exempt from the practical effect of the lock timeout, but it also **cannot run inside a transaction block** — each migration touching it must be its own file with nothing else in it, matching the existing `sql/039_ratings_score_viable_index.sql` precedent.
- Every bug fix / behavior change ships with a regression test that would have failed before the change (`CLAUDE.md` working agreement). The existing body/ring upsert tests that matter here are real-Postgres integration tests, not mocks — mocks cannot catch malformed SQL (`CLAUDE.md` known-hazards section, citing PR #403).
- Do not silently merge or paper over the two writers' existing behavior differences; where this plan changes `eddn_listener.py` and `import_spansh.py`, it changes them in separate, clearly-labeled tasks.
- This plan produces working, testable software at the end of every task — no task leaves the tree in a broken state.

---

## Task 0: Confirm the research this plan is built on (no code changes)

This task is a verification checkpoint, not an implementation step — it exists so whoever executes this plan re-confirms the load-bearing facts before touching schema, since they may have drifted since this plan was written (2026-08-05).

**Files:** none modified. Read-only.

- [x] **Step 1: Confirm current `bodies` PK shape** — re-verified 2026-08-07: still bare `id BIGINT PRIMARY KEY`, no sequence, no composite key.

Run: `grep -n "CREATE TABLE IF NOT EXISTS bodies" -A 3 sql/001_schema.sql`
Expected: `id BIGINT PRIMARY KEY` on its own, no sequence, no composite key. If this has already changed, stop and re-plan — this document assumes the pre-migration state.

- [ ] **Step 2: Confirm the three FK-dependent tables still carry their own `system_id64`** — not re-verified 2026-08-07, still needs a fresh check.

Run: `grep -n "system_id64.*NOT NULL REFERENCES systems" sql/001_schema.sql sql/021_station_body_links.sql`
Expected: three matches — `body_rings`, `attractions` (both in `sql/001_schema.sql`), `station_body_links` (`sql/021_station_body_links.sql`). If `sql/024_body_rings.sql` exists and is the live definition of `body_rings` (it re-declares the table as `CREATE TABLE IF NOT EXISTS`), check it too — it has the same `system_id64 NOT NULL` shape as of this writing.

- [x] **Step 3: Confirm the two writers are still the only writers of `bodies`** — re-verified 2026-08-07: `eddn_listener.py` still does `ON CONFLICT (id)` (composite conflict target not yet applied — matches "Tasks 2-6 not started" above), `import_spansh.py:954` still calls `upsert_via_temp(conn, 'bodies', BODY_COLS, body_batch, 'id', ...)` with the bare-string conflict_col form, no third writer found. (The second grep below needs `-A2`/multi-line matching to actually find the import_spansh.py call — its argument list wraps onto the next line — a single-line grep on this exact string silently returns nothing even though the call exists; don't take a no-match on the literal pattern as "writer removed.")

Run: `grep -rln "INSERT INTO bodies" apps/` and separately `grep -rln "upsert_via_temp(conn, 'bodies'" apps/`
Expected: `apps/eddn/src/eddn_listener.py` for the first, `apps/importer/src/import_spansh.py` for the second, and nothing else. If a third writer has appeared, this plan does not cover it — stop and extend the plan before proceeding.

- [ ] **Step 4: Confirm no other join site reads `bodies.id`/`bodies` without scoping by `system_id64`**

Run: `grep -rn "JOIN bodies\|bodies\.id\s*=\|=\s*bodies\.id\|body_id\s*=\s*b\.id\|b\.id\s*=.*body_id" apps/ --include=*.py`
Expected: every match's surrounding SQL already includes a `system_id64` equality alongside the id comparison, in the same `ON`/`WHERE` clause. As of this writing that's true for all matches across `apps/api/src/local_search.py`, `apps/api/src/routers/{simulation,systems,archetypes,simulate}.py`, `apps/importer/src/{build_ratings,build_archetype_scores,build_topology,enrich_system_data,enrichment_warehouse_sql}.py`. The one exception is `apps/api/src/routers/systems.py`'s `GET /api/body/{body_id}` endpoint (`SELECT * FROM bodies WHERE id = $1`, no system scoping) — confirmed to have zero frontend callers as of this writing (Task 7 handles it). If this step finds a *new* unscoped site, add a task to fix it before Task 2 (the PK swap) — an unscoped read becomes ambiguous, not just stale, once ids are no longer globally unique.

---

## Task 1: Composite unique index on `bodies`, built non-blocking

**Files:**
- Create: `sql/041_bodies_composite_identity_index.sql`
- Modify: `sql/migration-manifest.txt` (append filename)
- Test: `tests/integration/test_bodies_composite_identity.py` (new)

**Interfaces:**
- Produces: a unique index `idx_bodies_system_id64_id ON bodies (system_id64, id)` that Task 2 converts into the primary key.

- [ ] **Step 1: Write the migration file**

```sql
-- sql/041_bodies_composite_identity_index.sql
--
-- Part 1 of the bodies composite-identity migration (see
-- docs/superpowers/plans/2026-08-05-bodies-composite-identity-migration.md).
-- bodies.id is a source-supplied id (Spansh dump id, or the Elite Dangerous
-- journal's BodyID) that is unique only within a system, not globally — the
-- current bare `id BIGINT PRIMARY KEY` cannot represent that. This index is
-- the non-blocking first step; sql/042 swaps it in as the real primary key
-- once it's built and verified.
--
-- CONCURRENTLY: do not wrap this file in a transaction when applying. On the
-- ~573M-row bodies table this will take a long time — run it during a
-- monitored low-traffic window, not as part of a routine deploy. Existing
-- rows are already globally unique on id (the current PK enforces it), so
-- this cannot fail on a duplicate — it is purely an index build, no data
-- changes.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_bodies_system_id64_id
    ON bodies (system_id64, id);
```

- [ ] **Step 2: Register it in the migration manifest**

Append `041_bodies_composite_identity_index.sql` as a new line at the end of `sql/migration-manifest.txt` (matching the existing one-filename-per-line format).

- [ ] **Step 3: Write the failing test**

```python
# tests/integration/test_bodies_composite_identity.py
from __future__ import annotations

import os

import psycopg2
import pytest


@pytest.mark.db
def test_composite_identity_index_exists():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'bodies'
                  AND indexname = 'idx_bodies_system_id64_id'
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, (
        "idx_bodies_system_id64_id is missing — run "
        "sql/041_bodies_composite_identity_index.sql against the test database"
    )
    assert 'UNIQUE' in row[0]
    assert '(system_id64, id)' in row[0]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_bodies_composite_identity.py -v` (with `DATABASE_URL`, `REDIS_URL`, `EDFINDER_TEST_DB_ALLOW_DESTRUCTIVE_RESET=yes` set per `docs/development/windows-dev-environment.md` / this repo's established local test invocation)
Expected: FAIL — `row is None`.

- [ ] **Step 5: Apply the migration to the local test database**

Run: `bash scripts/apply_migrations.sh` (or the direct `psql` invocation the script uses if running against the local `docker-compose.local.yml` Postgres directly — confirm against `scripts/apply_migrations.sh`'s own `DATABASE_URL` branch)
Expected: migration applies; on a small local dev database the index build is near-instant (this is only slow at production's 573M-row scale).

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_bodies_composite_identity.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sql/041_bodies_composite_identity_index.sql sql/migration-manifest.txt tests/integration/test_bodies_composite_identity.py
git commit -m "Add non-blocking composite (system_id64, id) index on bodies"
```

---

## Known issues in Tasks 2-5 below, found by GitHub review on PR #411 (2026-08-05)

Not yet fixed in the task bodies below — resolve these before executing
Task 2, not after writing the migration files:

1. **Task 2 as written cannot run before Task 3.** `body_rings_body_id_fkey`,
   `attractions_body_id_fkey`, and `station_body_links_body_id_fkey` still
   reference `bodies(id)` (i.e. `bodies_pkey`) at the point Task 2's
   `DROP CONSTRAINT bodies_pkey` runs. PostgreSQL refuses to drop a
   constraint that other tables' foreign keys still depend on without
   `CASCADE`. Either drop/recreate those three FK constraints as part of
   Task 2's own migration file (ahead of the `DROP CONSTRAINT bodies_pkey`
   line), or merge Tasks 2 and 3 into one migration — do not rely on Task 3
   running as a separate, later step while Task 2 is written as it currently
   is.

2. **Task 3's `ON DELETE SET NULL` clauses need a column list.** Without one,
   PostgreSQL nulls *every* column in a multi-column foreign key on delete —
   both `system_id64` and `body_id` — but `system_id64` is `NOT NULL` on all
   three dependent tables, so deleting a `bodies` row would start raising a
   NOT NULL violation instead of just clearing `body_id` (the current,
   intended, single-column behavior). PostgreSQL 15+ supports naming which
   column(s) to null: change all three clauses in Task 3's migration file
   from `ON DELETE SET NULL` to `ON DELETE SET NULL (body_id)`.

3. **Tasks 2/3 (schema) and Tasks 4/5 (writer code) must not go live with a
   gap between them.** `eddn_listener.py` and `import_spansh.py` still issue
   `ON CONFLICT (id)` until Task 4/5's code ships. Task 2 removes the bare
   `id` unique constraint entirely and does not add a replacement
   `UNIQUE (id)`, so from the moment Task 2's migration is applied until
   Task 4/5's writer code is deployed, every body upsert fails outright with
   "no unique or exclusion constraint matching the ON CONFLICT specification"
   — body ingestion is completely down for that gap. Either deploy the
   schema and writer changes atomically, or keep a temporary
   `UNIQUE (id)` constraint alongside the new composite PK until the writer
   deploy is confirmed, then drop it in a follow-up migration.

4. **Task 3's FK validation is not actually metadata-only if written as a
   plain `ADD CONSTRAINT`.** A normal `FOREIGN KEY` addition validates every
   existing row immediately, which on production-sized `body_rings`,
   `attractions`, and `station_body_links` can mean a long scan under
   normal migration lock/timeout budgets — contrary to Task 3's current
   description of this as a safe, ordinary constraint swap. Split it into
   `ADD CONSTRAINT ... NOT VALID` followed by a separately-run, separately-
   monitored `VALIDATE CONSTRAINT` step (with the composite indexes the FKs
   need already in place), the same way Task 1 treats the big index build
   as its own deliberate, monitored operation rather than routine migration
   traffic.

---

## Task 2: Swap `bodies`' primary key to the composite index

**Do not start this task until Task 1's index has been built and verified in production** (see the Production Rollout Runbook at the end of this plan — this is a deploy-sequencing dependency, not just a code dependency). **Also read "Known issues in Tasks 2-5" immediately above — Task 2 as drafted below has not yet been corrected for issue 1.**

**Files:**
- Create: `sql/042_bodies_composite_primary_key.sql`
- Modify: `sql/migration-manifest.txt`
- Test: `tests/integration/test_bodies_composite_identity.py` (extend)

**Interfaces:**
- Consumes: `idx_bodies_system_id64_id` from Task 1.
- Produces: `bodies` now accepts two rows with the same `id` as long as `system_id64` differs. This is the property Task 4/5's writer changes and Task 6's regression tests depend on.

- [ ] **Step 1: Write the migration file**

```sql
-- sql/042_bodies_composite_primary_key.sql
--
-- Part 2 of the bodies composite-identity migration — see sql/041 and
-- docs/superpowers/plans/2026-08-05-bodies-composite-identity-migration.md.
--
-- This swap is fast (metadata-only): idx_bodies_system_id64_id already
-- exists from sql/041, built CONCURRENTLY ahead of time, so promoting it to
-- the primary key does not require a table scan or index build here. Still
-- takes an ACCESS EXCLUSIVE lock for the duration of the constraint swap
-- itself, which should be sub-second once the index is warm — but confirm
-- the index exists (Task 1's test) before applying this in production.
ALTER TABLE bodies
    DROP CONSTRAINT bodies_pkey,
    ADD CONSTRAINT bodies_pkey PRIMARY KEY USING INDEX idx_bodies_system_id64_id;
```

- [ ] **Step 2: Register it in the migration manifest**

Append `042_bodies_composite_primary_key.sql` to `sql/migration-manifest.txt`.

- [ ] **Step 3: Write the failing test**

Add to `tests/integration/test_bodies_composite_identity.py`:

```python
@pytest.mark.db
def test_same_id_different_system_now_coexists():
    """This is the actual property the whole migration exists to provide:
    two systems whose bodies coincidentally share a numeric id (routine,
    since the ED journal's BodyID is only unique within a system) must both
    be storable, not one silently dropped or corrupting the other."""
    owner_id, other_id = 95_000_000_000_001, 95_000_000_000_002
    body_id = 950_000_001
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', ([owner_id, other_id],))
            cur.execute(
                "INSERT INTO systems (id64, name) VALUES (%s, 'Owner'), (%s, 'Other')",
                (owner_id, other_id),
            )
            cur.execute(
                "INSERT INTO bodies (id, system_id64, name) VALUES (%s, %s, 'Owner Body')",
                (body_id, owner_id),
            )
            cur.execute(
                "INSERT INTO bodies (id, system_id64, name) VALUES (%s, %s, 'Other Body')",
                (body_id, other_id),
            )
            conn.commit()

            cur.execute(
                'SELECT system_id64, name FROM bodies WHERE id = %s ORDER BY system_id64',
                (body_id,),
            )
            rows = cur.fetchall()
    finally:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', ([owner_id, other_id],))
        conn.commit()
        conn.close()

    assert rows == [(owner_id, 'Owner Body'), (other_id, 'Other Body')]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_bodies_composite_identity.py::test_same_id_different_system_now_coexists -v`
Expected: FAIL — the second `INSERT` raises a unique-violation on the old bare-`id` primary key.

- [ ] **Step 5: Apply the migration locally and re-run**

Run: `bash scripts/apply_migrations.sh` then `.venv/Scripts/python.exe -m pytest tests/integration/test_bodies_composite_identity.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add sql/042_bodies_composite_primary_key.sql sql/migration-manifest.txt tests/integration/test_bodies_composite_identity.py
git commit -m "Swap bodies primary key to composite (system_id64, id)"
```

---

## Task 3: Convert the three dependent foreign keys to composite

**Files:**
- Create: `sql/043_body_dependent_composite_fks.sql`
- Modify: `sql/migration-manifest.txt`
- Test: `tests/integration/test_bodies_composite_identity.py` (extend)

**Interfaces:**
- Consumes: `bodies_pkey` from Task 2 (composite PK is a prerequisite — a plain `REFERENCES bodies(id)` FK requires `id` alone to carry a unique constraint, which Task 2 removes).
- Produces: `body_rings.body_id`, `attractions.body_id`, `station_body_links.body_id` are still nullable single columns (unchanged), but the FK constraint backing them is now `FOREIGN KEY (system_id64, body_id) REFERENCES bodies (system_id64, id)`.

- [ ] **Step 1: Write the migration file**

```sql
-- sql/043_body_dependent_composite_fks.sql
--
-- Part 3 of the bodies composite-identity migration — see sql/041, sql/042,
-- and docs/superpowers/plans/2026-08-05-bodies-composite-identity-migration.md.
--
-- body_rings, attractions, and station_body_links each already carry their
-- own NOT NULL system_id64 column (their own FK to systems(id64)), so no
-- new columns are needed — only the constraint target changes. MATCH SIMPLE
-- (the default) means a NULL body_id still passes the FK check regardless
-- of system_id64, matching current nullable-body_id semantics.
--
-- These are metadata-only constraint swaps, not index builds — safe to run
-- inside the normal migration transaction/lock-timeout budget, unlike
-- sql/041.
ALTER TABLE body_rings
    DROP CONSTRAINT IF EXISTS body_rings_body_id_fkey,
    ADD CONSTRAINT body_rings_body_id_fkey
        FOREIGN KEY (system_id64, body_id) REFERENCES bodies (system_id64, id)
        ON DELETE SET NULL;

ALTER TABLE attractions
    DROP CONSTRAINT IF EXISTS attractions_body_id_fkey,
    ADD CONSTRAINT attractions_body_id_fkey
        FOREIGN KEY (system_id64, body_id) REFERENCES bodies (system_id64, id)
        ON DELETE SET NULL;

ALTER TABLE station_body_links
    DROP CONSTRAINT IF EXISTS station_body_links_body_id_fkey,
    ADD CONSTRAINT station_body_links_body_id_fkey
        FOREIGN KEY (system_id64, body_id) REFERENCES bodies (system_id64, id)
        ON DELETE SET NULL;
```

- [ ] **Step 2: Verify the actual constraint names before relying on `IF EXISTS`**

Run: `docker exec ed-postgres psql -U edfinder -d edfinder -At -c "SELECT conname, conrelid::regclass FROM pg_constraint WHERE confrelid = 'bodies'::regclass AND contype = 'f';"` against local dev
Expected: three rows. If any constraint name differs from the `{table}_body_id_fkey` guess above (Postgres auto-names differently in some cases), update the migration file's `DROP CONSTRAINT` lines to match the real names exactly — do not guess in the file that actually ships.

- [ ] **Step 3: Register it in the migration manifest**

Append `043_body_dependent_composite_fks.sql` to `sql/migration-manifest.txt`.

- [ ] **Step 4: Write the failing test**

Add to `tests/integration/test_bodies_composite_identity.py`:

```python
@pytest.mark.db
def test_body_rings_fk_allows_same_body_id_different_system():
    """Companion to test_same_id_different_system_now_coexists: rings for
    two different systems' bodies that happen to share a numeric body_id
    must both be insertable against the FK, not just the bodies rows
    themselves."""
    owner_id, other_id = 95_000_000_000_003, 95_000_000_000_004
    body_id = 950_000_002
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM body_rings WHERE body_id = %s', (body_id,))
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', ([owner_id, other_id],))
            cur.execute(
                "INSERT INTO systems (id64, name) VALUES (%s, 'Owner'), (%s, 'Other')",
                (owner_id, other_id),
            )
            cur.execute(
                "INSERT INTO bodies (id, system_id64, name) VALUES (%s, %s, 'Owner Body')",
                (body_id, owner_id),
            )
            cur.execute(
                "INSERT INTO bodies (id, system_id64, name) VALUES (%s, %s, 'Other Body')",
                (body_id, other_id),
            )
            cur.execute(
                """
                INSERT INTO body_rings (system_id64, body_id, ring_name, source, confidence)
                VALUES (%s, %s, 'Owner Ring A', 'spansh_dump', 'source_ring_payload'),
                       (%s, %s, 'Other Ring A', 'spansh_dump', 'source_ring_payload')
                """,
                (owner_id, body_id, other_id, body_id),
            )
            conn.commit()

            cur.execute(
                'SELECT system_id64, ring_name FROM body_rings WHERE body_id = %s ORDER BY system_id64',
                (body_id,),
            )
            rows = cur.fetchall()
    finally:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM body_rings WHERE body_id = %s', (body_id,))
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', ([owner_id, other_id],))
        conn.commit()
        conn.close()

    assert rows == [(owner_id, 'Owner Ring A'), (other_id, 'Other Ring A')]
```

- [ ] **Step 5: Run test to verify it fails, apply migration, verify it passes**

Run before: FAIL (old single-column FK still enforces `body_id` global uniqueness-by-reference — inserting the second ring for a `body_id` already referenced from a *different* `bodies` row is fine under the OLD FK actually, since FK just checks existence, not exclusivity — re-derive the exact failure mode empirically here rather than assuming; if it does not fail as expected, that is itself a signal to re-examine this test before proceeding, not to weaken the assertion).
Apply: `bash scripts/apply_migrations.sh`
Run after: PASS.

- [ ] **Step 6: Commit**

```bash
git add sql/043_body_dependent_composite_fks.sql sql/migration-manifest.txt tests/integration/test_bodies_composite_identity.py
git commit -m "Convert body_rings/attractions/station_body_links FKs to composite (system_id64, body_id)"
```

---

## Task 4: Update `eddn_listener.py`'s bodies upsert

**Do not start this task until Tasks 1-3 are live in production** (writer code assuming composite conflict handling will break against the old bare-`id` schema).

**Files:**
- Modify: `apps/eddn/src/eddn_listener.py:940-1006` (the bodies `INSERT ... ON CONFLICT`)
- Test: `tests/integration/test_eddn_system_colonisation_writes.py` (modify existing collision tests — their expected outcome flips)

**Interfaces:**
- Consumes: composite PK from Task 2.
- Produces: no more re-parenting risk *and* no more silent data loss — a colliding `BodyID` from a different system is now a normal, successful insert of a distinct row, not a rejected no-op.

- [ ] **Step 1: Update the failing tests first**

In `tests/integration/test_eddn_system_colonisation_writes.py`, the two tests added for the original stopgap fix (`test_scan_with_colliding_body_id_from_other_system_does_not_reparent` and `test_scan_from_owning_system_still_updates_after_guard`) tested the *stopgap's* behavior (no-op on collision). Replace the first with the real-fix behavior:

```python
@pytest.mark.asyncio
async def test_scan_with_colliding_body_id_from_other_system_stores_both(
    pool,
    isolated_eddn_system_writes,
):
    """Superseded by the composite-identity migration
    (docs/superpowers/plans/2026-08-05-bodies-composite-identity-migration.md):
    a colliding BodyID from a different system used to be a no-op (silent
    data loss) under the stopgap guard. Now it's a normal, independent row —
    the whole class of bug this migration exists to close."""
    owner_system_id = TEST_SYSTEM_IDS[7]
    intruder_system_id = TEST_SYSTEM_IDS[8]
    body_id = TEST_BODY_IDS[2]

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO systems (id64, name) VALUES ($1, 'EDDN Composite Owner System')",
            owner_system_id,
        )
        await conn.execute(
            "INSERT INTO systems (id64, name) VALUES ($1, 'EDDN Composite Intruder System')",
            intruder_system_id,
        )

    await eddn_listener.handle_scan(
        pool, {},
        {
            'SystemAddress': owner_system_id,
            'BodyID': body_id,
            'BodyName': 'Owner System Body 1 a',
            'PlanetClass': 'Rocky body',
        },
    )
    await eddn_listener.flush_pending(pool)

    await eddn_listener.handle_scan(
        pool, {},
        {
            'SystemAddress': intruder_system_id,
            'BodyID': body_id,
            'BodyName': 'Intruder System Body 1 a',
            'PlanetClass': 'Icy body',
        },
    )
    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT system_id64, name, subtype FROM bodies WHERE id = $1 ORDER BY system_id64',
            body_id,
        )

    assert [dict(r) for r in rows] == [
        {'system_id64': owner_system_id, 'name': 'Owner System Body 1 a', 'subtype': 'Rocky body'},
        {'system_id64': intruder_system_id, 'name': 'Intruder System Body 1 a', 'subtype': 'Icy body'},
    ]
```

Keep `test_scan_from_owning_system_still_updates_after_guard` as-is — same-system re-scan updating in place is still correct behavior and is unaffected by this migration; only rename it to `test_scan_from_owning_system_still_updates` since "guard" no longer describes the mechanism.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_eddn_system_colonisation_writes.py::test_scan_with_colliding_body_id_from_other_system_stores_both -v`
Expected: FAIL — under the current stopgap, the intruder's row is still silently dropped, so the query returns only one row, not two.

- [ ] **Step 3: Change the ON CONFLICT target and remove the ownership guard**

In `apps/eddn/src/eddn_listener.py`, change:

```python
                            ON CONFLICT (id) DO UPDATE SET
                                system_id64       = EXCLUDED.system_id64,
```

to:

```python
                            ON CONFLICT (system_id64, id) DO UPDATE SET
```

(drop the `system_id64 = EXCLUDED.system_id64,` line entirely — `system_id64` is now part of the conflict target, so on a real conflict it is by definition already equal to `EXCLUDED.system_id64`; setting it is a no-op at best, and keeping it invites exactly the kind of "SET a column that's part of the key" confusion this whole incident started from).

Then change the `WHERE` clause from:

```python
                            WHERE
                                bodies.system_id64 = EXCLUDED.system_id64
                                AND (
                                    bodies.name IS DISTINCT FROM COALESCE(NULLIF(EXCLUDED.name, 'Unknown'), bodies.name)
```

to:

```python
                            WHERE
                                bodies.name IS DISTINCT FROM COALESCE(NULLIF(EXCLUDED.name, 'Unknown'), bodies.name)
```

(drop the `bodies.system_id64 = EXCLUDED.system_id64 AND (` guard and its closing `)` — the ownership guard is now structurally unnecessary, since a "collision" from a different system is no longer the same conflict target at all. Keep every other `OR bodies.x IS DISTINCT FROM ...` line unchanged — that part is still doing its original job of skipping genuinely no-op updates.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_eddn_system_colonisation_writes.py -v`
Expected: all tests in the file PASS, including the renamed same-system test and the new cross-system test.

- [ ] **Step 5: Commit**

```bash
git add apps/eddn/src/eddn_listener.py tests/integration/test_eddn_system_colonisation_writes.py
git commit -m "Store colliding-BodyID bodies as independent rows via composite conflict target"
```

---

## Task 5: Update `import_spansh.py`'s bodies upsert and remove the now-dead guard machinery

**Do not start until Task 4 is merged** (both writers should change together conceptually, but land as separate commits/PRs per this repo's existing pattern today).

**Files:**
- Modify: `apps/importer/src/import_spansh.py` — `upsert_via_temp()` (`conflict_col` needs to accept a composite target), the `flush_bodies()`/`flush_rings()` closures inside `import_galaxy()` (remove `rejected_body_ids`/`rings_skipped_rejected_body` entirely — dead code once collisions can't happen), and the one `bodies` call site
- Modify: `tests/integration/test_import_spansh_body_upsert.py` (collision tests flip expected outcome, same as Task 4)
- Modify: `tests/test_stage17n2c_data_trust.py` (remove the now-stale content-contract tests for `guard_col`/`rejected_body_ids`/the ownership-rejection query — they'd be asserting dead code exists)

**Interfaces:**
- Consumes: composite PK from Task 2.
- Produces: `upsert_via_temp(conn, 'bodies', BODY_COLS, body_batch, ['id', 'system_id64'])` — `conflict_col` is now a list for this call site; existing `systems`/`stations` call sites keep passing a bare string and are unaffected.

- [ ] **Step 1: Update `upsert_via_temp` to accept a composite `conflict_col`**

In `apps/importer/src/import_spansh.py`, change the signature and the two places `conflict_col` is interpolated into SQL:

```python
def upsert_via_temp(conn, target_table: str, columns: List[str],
                    rows: List[Tuple], conflict_col,
                    update_cols: Optional[List[str]] = None) -> int:
    """conflict_col: a single column name (str) or a list of column names
    forming a composite ON CONFLICT target."""
    if not rows:
        return 0
    conflict_cols = [conflict_col] if isinstance(conflict_col, str) else list(conflict_col)
    if update_cols is None:
        update_cols = [c for c in columns if c not in conflict_cols]
    temp = f"_tmp_{target_table}"
    col_list   = ', '.join(columns)
    set_clause = ', '.join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    change_cols = [
        c for c in update_cols
        if c not in {'updated_at', 'rating_dirty', 'cluster_dirty'}
    ]
    where_clause = ''
    if change_cols:
        comparisons = ' OR '.join(
            f"{target_table}.{c} IS DISTINCT FROM EXCLUDED.{c}"
            for c in change_cols
        )
        where_clause = f"\n            WHERE {comparisons}"
    conflict_target = ', '.join(conflict_cols)
```

(This deliberately deletes `guard_col` and `returning_col` entirely — both existed only to work around bare-`id` collisions, which are now structurally impossible. Removing them is not optional cleanup; leaving them would be dead code implementing a guard against a condition that can no longer occur, which is exactly the kind of stale defensive code this repo's working agreement says not to keep.)

Then change the `INSERT` statement's `ON CONFLICT` clause from:

```python
                ON CONFLICT ({conflict_col}) DO UPDATE
```

to:

```python
                ON CONFLICT ({conflict_target}) DO UPDATE
```

And remove the `RETURNING`/`rejected_keys` block that followed it (the whole `if returning_col and guard_col:` section and its `cur.fetchall()` call) along with the final `return (count, rejected_keys) if returning_col else count` — restore a plain `return count`.

- [ ] **Step 2: Simplify `flush_bodies()`/`flush_rings()` in `import_galaxy()`**

Remove `rejected_body_ids` and `rings_skipped_rejected_body` from the batch-state block, and simplify:

```python
    def flush_bodies():
        flush_systems()
        if body_batch:
            upsert_via_temp(conn, 'bodies', BODY_COLS, body_batch, ['id', 'system_id64'])
            body_batch.clear()

    def flush_rings():
        flush_bodies()
        if ring_batch:
            upsert_body_rings(conn, ring_batch)
            ring_batch.clear()
```

Remove the final-summary `if rings_skipped_rejected_body:` log block near the end of `import_galaxy()` (it has nothing to report now — the condition it logged can't happen).

- [ ] **Step 3: Update the one `bodies` call site's column order note**

`BODY_COLS[0]` is `'id'`; the new composite conflict target list is `['id', 'system_id64']` — order doesn't need to match `BODY_COLS`' order, it only needs both column names present. No other change needed at the call site itself beyond what Step 2 already shows.

- [ ] **Step 4: Update the real-Postgres tests**

In `tests/integration/test_import_spansh_body_upsert.py`, replace `test_body_upsert_with_colliding_id_from_other_system_is_noop` with:

```python
@pytest.mark.db
def test_body_upsert_with_colliding_id_from_other_system_stores_both(pg_conn):
    """Superseded by the composite-identity migration: a colliding id from a
    different system used to be a no-op. Now it's an independent row."""
    owner_id, intruder_id = TEST_SYSTEM_IDS
    _insert_test_systems(pg_conn)

    import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, owner_id, 'Owner System Body 1 a', 'Planet', 'Rocky body')],
        ['id', 'system_id64'],
    )
    import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, intruder_id, 'Intruder System Body 1 a', 'Planet', 'Icy body')],
        ['id', 'system_id64'],
    )

    with pg_conn.cursor() as cur:
        cur.execute(
            'SELECT system_id64, name, subtype FROM bodies WHERE id = %s ORDER BY system_id64',
            (TEST_BODY_ID,),
        )
        rows = cur.fetchall()

    assert rows == [
        (owner_id, 'Owner System Body 1 a', 'Rocky body'),
        (intruder_id, 'Intruder System Body 1 a', 'Icy body'),
    ]
```

Delete `test_returning_col_reports_ids_rejected_by_guard` and `test_unchanged_same_system_body_is_not_reported_as_rejected` — they test the now-removed `guard_col`/`returning_col` mechanism directly and have nothing left to assert once it's gone. Keep `test_body_upsert_from_owning_system_still_updates_after_guard`, renamed to drop "after_guard" from its name, updating its calls to the new `['id', 'system_id64']` conflict_col form — same-system update-in-place is unaffected by this migration.

In `tests/test_stage17n2c_data_trust.py`, delete `test_spansh_temp_upsert_guard_col_scopes_to_matching_owner`, `test_spansh_flush_rings_drops_rows_for_guard_rejected_bodies`, and `test_spansh_upsert_via_temp_rejection_uses_ownership_query_not_returning` — all three assert source strings for machinery this task deletes. Keep `test_spansh_temp_upsert_skips_noop_updates`, updating its asserted literal strings to match Step 1's rewritten `upsert_via_temp` (no more `excluded_change_cols`/`guard_col` — back to the simpler pre-guard shape, but keep the `conflict_cols`/composite-target awareness).

- [ ] **Step 5: Run the full import_spansh test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_import_spansh_body_upsert.py tests/test_stage17n2c_data_trust.py tests/test_import_spansh_runtime.py -v`
Expected: all PASS. `tests/test_import_spansh_runtime.py`'s deadlock-retry tests call `upsert_via_temp` with a bare string `conflict_col` (`'id64'` for systems) — confirm they still pass unmodified, proving the `isinstance(conflict_col, str)` branch preserves the existing single-column call sites.

- [ ] **Step 6: Commit**

```bash
git add apps/importer/src/import_spansh.py tests/integration/test_import_spansh_body_upsert.py tests/test_stage17n2c_data_trust.py
git commit -m "Store colliding Spansh body ids as independent rows; remove now-dead guard machinery"
```

---

## Task 6: Handle the unused `GET /api/body/{body_id}` endpoint

**Files:**
- Modify: `apps/api/src/routers/systems.py:348-364`
- Modify: `apps/api/src/models.py` (if a response model exists for this endpoint — confirm during implementation)
- Test: whatever existing test file covers `apps/api/src/routers/systems.py`'s body-detail route (locate via `grep -rl "get_body\|/api/body/" tests/`)

**Interfaces:**
- Produces: the endpoint either requires `system_id64` as an additional required query parameter, or is explicitly marked deprecated and left returning a best-effort single match (`ORDER BY system_id64 LIMIT 1`) with a code comment explaining why the result is now ambiguous by construction.

- [ ] **Step 1: Re-confirm zero live callers before deciding**

Run: `grep -rn "api/body/\${" frontend/src/` and `grep -rn "'/api/body/" frontend/src/`
Expected: no matches (re-confirming Task 0 Step 4's finding, since this plan may execute weeks after being written). If a caller now exists, this task must add `system_id64` as a required parameter and update that caller — do not silently leave an ambiguous bare-id lookup live in a real code path.

- [ ] **Step 2: If still unused, require `system_id64` explicitly**

Change the route signature in `apps/api/src/routers/systems.py`:

```python
@router.get('/api/body/{body_id}')
async def get_body(
    body_id: int,
    system_id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    cache_key = f'body:{BODY_CACHE_VERSION}:{system_id64}:{body_id}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT * FROM bodies WHERE id = $1 AND system_id64 = $2',
            body_id, system_id64,
        )
        if not row:
            raise HTTPException(404, f'Body {body_id} not found in system {system_id64}')
```

- [ ] **Step 3: Regenerate frontend types and confirm no drift failure**

Run: `cd frontend && yarn types:gen` then `yarn typecheck`
Expected: `src/types/api.gen.ts` updates to reflect the new required `system_id64` query parameter; typecheck passes (since Step 1 confirmed nothing calls this route today, there should be nothing to fix).

- [ ] **Step 4: Update or add the endpoint's test**

Locate the existing test for this route (`grep -rl "api/body/\|get_body" tests/`) and update its call to include `system_id64`; if none exists, add one asserting a 404 when `system_id64` doesn't match the body's actual owner even though `body_id` alone would have matched pre-migration — this is the regression test proving the ambiguity this task closes.

- [ ] **Step 5: Run the relevant test file and commit**

Run: `.venv/Scripts/python.exe -m pytest <the test file from Step 4> -v`
Expected: PASS.

```bash
git add apps/api/src/routers/systems.py frontend/src/types/api.gen.ts <test file>
git commit -m "Require system_id64 on GET /api/body/{body_id} now that body ids are only unique per-system"
```

---

## Task 7: Full regression pass

**Files:** none new — this task runs the existing suites, it doesn't add code.

- [ ] **Step 1: Run the full local unit + integration suite**

Run: `make test-unit && make test-db && make test-integration` (or the equivalent PowerShell-wrapped invocation per `docs/development/windows-dev-environment.md`)
Expected: all green. Pay particular attention to `tests/test_trust_layer.py` (cross-checks `domain.facilities`, `mechanics.confidence`/`constants`/`link_rules`, `regional.regional_analysis`, `simulation.build_preview` stay mutually consistent — this migration doesn't touch any of those directly, but confirm it stays green) and anything under `tests/` matching `body_ring` or `station_body_link` by name, since Task 3's FK changes are the highest-risk schema touch here.

- [ ] **Step 2: Run the full CI-equivalent local pass**

Run: `make test-ci-local`
Expected: green, matching what `.github/workflows/ci.yml`'s required jobs would report.

- [ ] **Step 3: If anything is red, stop and fix before proceeding to the production rollout**

Per `CLAUDE.md`'s working agreement: "Red main is stop-the-line." Do not proceed to the rollout runbook below with a red local CI-equivalent pass.

---

## Production Rollout Runbook

This is **not** a single deploy — it is a sequence with a mandatory pause for the long-running index build, because `bodies` has ~573M rows in production (confirmed 2026-08-05 via `pg_stat_user_tables.n_live_tup`) and `CREATE INDEX CONCURRENTLY` at that scale can run for hours. Do not compress these steps into one deploy window.

1. **Deploy Task 1 alone** (the `CONCURRENTLY` index). Do not bundle it with Task 2 in the same deploy — `scripts/apply_migrations.sh` applies pending migrations in manifest order as part of `scripts/deploy_main.sh`, and Task 2's migration must not run until Task 1's index is confirmed fully built, which will outlast a normal deploy window.
2. **Monitor the index build to completion.** `CREATE INDEX CONCURRENTLY` runs as its own backend; check progress via `SELECT phase, blocks_done, blocks_total FROM pg_stat_progress_create_index;` while it runs, and confirm completion via `SELECT indisvalid FROM pg_index WHERE indexrelid = 'idx_bodies_system_id64_id'::regclass;` (must be `t` — a `CONCURRENTLY` build that failed partway leaves an *invalid* index, which must be dropped and retried, not left in place).
3. **Deploy Task 2** (the PK swap) once Task 1's index is confirmed valid. This should be fast (metadata-only), but run it in a low-traffic window regardless, since it takes a brief `ACCESS EXCLUSIVE` lock on `bodies` — anything holding a long-running transaction against `bodies` at that moment will block it.
4. **Deploy Task 3** (the composite FKs). Independent of Task 2 in principle, but do not run it before Task 2 — a composite FK referencing `bodies (system_id64, id)` requires that exact composite unique constraint to already exist as `bodies`' primary key (or a matching unique constraint), which Task 2 provides.
5. **Only after Tasks 1-3 are confirmed live**, deploy Task 4 and Task 5 together (the two writers). Deploying the writer code before the schema change lands would attempt `ON CONFLICT (system_id64, id)` against a table that doesn't yet have that composite key, which fails outright — a loud failure, not a silent one, but avoid it by sequencing correctly regardless.
6. **Deploy Task 6** whenever convenient — it has no ordering dependency on the others beyond Task 2/3 already being live (its query already always included `system_id64`, since it's the *fix* for the one place that didn't).
7. **After every deploy step above, run the same drift-monitoring approach used for the original stopgap incident** (`docs/development/full-stack-adversarial-audit-2026-07-10.md` process, or simply re-run the `body_rings.association_status` drift query from `shared_contracts/data_invariant_contracts.py`'s `RING_ASSOCIATION_STATUS_DRIFT_SQL`) for at least an hour post-deploy of Tasks 4/5, confirming the count does not climb — this is the same verification discipline used for the original 2026-08-04 incident response, and this migration is the promised follow-up to it.

---

## Self-Review

**Spec coverage:** the PR #406 Codex Review finding this plan exists to close ("Preserve colliding bodies instead of dropping them... requires a system-scoped identity or a generated canonical body ID") is addressed by Tasks 1-5 (system-scoped identity, chosen over a generated canonical id per the research in this plan's introduction). The FK blast radius (Task 0 Step 2) is addressed by Task 3. The one unscoped API consumer found (Task 0 Step 4) is addressed by Task 6. The pre-existing batch-duplicate `CardinalityViolation` crash risk found while reviewing PR #409 is a separate, already-tracked follow-up (task #1 in this session's task list) — deliberately out of scope for this plan, since it's an orthogonal robustness gap in `upsert_via_temp`'s batching, not part of the identity-model fix.

**Placeholder scan:** no TBD/TODO markers; every SQL and Python step shows complete code, not a description of code.

**Type consistency:** `upsert_via_temp`'s `conflict_col` parameter is used consistently as `str | list[str]` across Task 5's rewrite and its existing `systems`/`stations` call sites (unchanged, still pass a bare string). `BODY_COLS` composition is unchanged by this plan — only the conflict target passed alongside it changes.
