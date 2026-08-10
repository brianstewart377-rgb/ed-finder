# Scoring Cleanup Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the dead `ratings.score_breakdown` column via a reviewed,
landmine-aware migration, without touching any live scoring behaviour.

**Architecture:** `ratings.score_breakdown` is entirely NULL and unread by the
application (confirmed 2026-08-10; it is reconstructed at read time from other
columns by `ratings_breakdown.py`, never selected from the column). Three
orphaned SQL objects in `sql/003_functions.sql` still *reference* the column and
must be handled first — one of them, the `system_detail` view, hard-blocks the
`DROP COLUMN`. A single new numbered migration (`043`) recreates the view minus
the column, drops the two orphaned functions, then drops the column. Phase 2
(retiring the still-live `score_<economy>` columns) is scoped but **deferred** —
it is a scoring-path change, not a cleanup, and is out of scope here.

**Tech Stack:** PostgreSQL 16, `scripts/apply_migrations.sh` (manifest + SHA256
ledger), pytest with `@pytest.mark.db` + `psycopg2` (mirrors the existing
`tests/integration/` DB tests), `docker-compose.local.yml` (local Postgres on
`127.0.0.1:55432`).

## Global Constraints

- **No hidden scoring/CP/economy/service/optimiser changes.** This migration
  removes a NULL, unread column only. It must not alter any value the Finder,
  simulation, or optimiser returns. (ROADMAP hard boundary.)
- **Ledger discipline — never edit an applied base file.** `001_schema.sql` and
  `003_functions.sql` are checksum-pinned in the `schema_migrations` ledger; the
  apply script hashes each manifest file and re-application is `ON CONFLICT DO
  NOTHING`. Editing them in place causes checksum drift. **All changes go in a
  new numbered migration** appended to `sql/migration-manifest.txt`.
- **Next migration number is `043`.** (`042_exploration_facts.sql` is the latest;
  `999_refresh_materialized_views.sql` is a re-runnable sentinel, not a number to
  take.)
- **Prove against real `postgres:16-alpine` before push.** Python mock tests
  cannot catch malformed SQL — PR #403 shipped broken SQL to production with all
  checks green. This migration requires a real-Postgres test.
- **Do NOT touch `system_archetype_scores.score_breakdown`.** A second, unrelated
  column of the same name exists on the archetype-scores table; it is alive
  (written by `build_archetype_scores.py`, read by `routers/archetypes.py`). The
  migration targets `ratings` and `system_detail` only. A test asserts the
  archetype column still exists (collision guard).
- **Preserve the Storage Recovery baseline** (`docs/ROADMAP.md`): do not write
  `score_breakdown`, do not create indexes on retired ratings score columns.
- **A merge is not a deploy.** Applying the migration to production is a separate
  owner-approved step (see "Production apply runbook" at the end). The PR only
  lands the migration file + test.
- **Migration timeout policy:** default `MIGRATION_STATEMENT_TIMEOUT=1h`,
  `MIGRATION_LOCK_TIMEOUT=30s` are correct here — every statement is a metadata
  operation (instant). Do not set either to `0`.

---

## Landmine summary (why this is not a one-line `DROP COLUMN`)

Established by discovery on 2026-08-10:

1. **Name collision.** `ratings.score_breakdown` (dead, drop target) vs
   `system_archetype_scores.score_breakdown` (alive, must not touch). Every
   statement is table-qualified; a guard test asserts the archetype column
   survives.
2. **Hard dependency — the `system_detail` view.** It selects `r.score_breakdown`
   directly, so `ALTER TABLE ratings DROP COLUMN score_breakdown` fails with a
   dependency error until the view is recreated without the column. `CREATE OR
   REPLACE VIEW` **cannot** drop a column from a view (Postgres errors "cannot
   drop columns from view"), so it must be `DROP VIEW` + `CREATE VIEW`.
3. **Soft dependency — two plpgsql functions.** `search_galaxy_economy()` and
   `search_economy_near()` reference `r.score_breakdown` inside dynamic `EXECUTE
   format(...)` strings. Dynamic SQL is not dependency-tracked, so the drop is
   *not* blocked — but the functions would become latent-broken (fail on next
   call). Both are **orphaned** (no caller in `apps/` or `scripts/`; the app's
   galaxy/economy search runs inline SQL in `local_search.py`). They are dropped.
4. **DB objects are invisible to app-code greps** (CLAUDE.md debugging rule #4).
   These three objects were found only by reading `sql/003_functions.sql`, not by
   grepping `apps/`. A `pg_depend` verification step (Task 1) confirms no *other*
   object depends on the column before execution.

---

## File structure

- **Create:** `sql/043_drop_ratings_score_breakdown.sql` — the migration
  (recreate view minus column, drop two orphaned functions, drop column).
- **Modify:** `sql/migration-manifest.txt` — append the new filename.
- **Create:** `tests/integration/test_drop_ratings_score_breakdown_migration.py` —
  real-Postgres regression + collision-guard test (mirrors the connection style
  of `tests/integration/test_bodies_composite_identity.py`).
- **Do NOT modify:** `sql/001_schema.sql`, `sql/003_functions.sql` (checksum-pinned).
- **Do NOT modify:** `apps/api/src/ratings_breakdown.py`, `local_search.py`,
  `models.py` — they never read the `ratings.score_breakdown` *column*
  (reconstruction reads the `score_<economy>` columns, which Phase 1 keeps).

---

## Phase 1 — Drop the dead `ratings.score_breakdown` column

### Task 1: Real-Postgres regression + collision-guard test (write first, watch it fail)

**Files:**
- Test: `tests/integration/test_drop_ratings_score_breakdown_migration.py`

**Interfaces:**
- Consumes: a migrated local test DB reached via `os.environ['DATABASE_URL']`
  (the `tests/integration/` convention; `docker-compose.local.yml` binds it to
  `127.0.0.1:55432`).
- Produces: assertions used as the pass/fail gate for Task 2.

Before writing, run this `pg_depend` check against a migrated local DB and record
the result in the test's module docstring — it proves the view is the only hard
blocker:

```sql
-- Objects that depend on ratings.score_breakdown (expect: only system_detail view).
SELECT DISTINCT dependent.relname AS dependent_object, dependent.relkind
FROM pg_depend d
JOIN pg_rewrite rw ON rw.oid = d.objid
JOIN pg_class dependent ON dependent.oid = rw.ev_class
JOIN pg_class tbl ON tbl.oid = d.refobjid
JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
WHERE tbl.relname = 'ratings' AND a.attname = 'score_breakdown';
```

- [ ] **Step 1: Write the failing test**

```python
"""Real-Postgres regression for migration 043 (drop ratings.score_breakdown).

Landmine-aware: (1) the ratings column is dropped; (2) the same-named
system_archetype_scores.score_breakdown column is NOT touched (collision
guard); (3) the system_detail view still exists and no longer exposes the
column; (4) the two orphaned search functions are gone.

pg_depend check (run 2026-08-10 against a migrated local DB) confirmed the
system_detail view is the only hard dependency on ratings.score_breakdown.
Connection style mirrors tests/integration/test_bodies_composite_identity.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.db

ROOT = Path(__file__).resolve().parents[2]


def _conn():
    return psycopg2.connect(os.environ['DATABASE_URL'])


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def test_ratings_score_breakdown_column_dropped():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            assert not _column_exists(cur, 'ratings', 'score_breakdown')
    finally:
        conn.close()


def test_archetype_score_breakdown_column_preserved():
    # Collision guard: the same-named archetype column is alive and untouched.
    conn = _conn()
    try:
        with conn.cursor() as cur:
            assert _column_exists(cur, 'system_archetype_scores', 'score_breakdown')
    finally:
        conn.close()


def test_system_detail_view_valid_without_column():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_class WHERE relname = 'system_detail' AND relkind = 'v'")
            assert cur.fetchone() is not None
            assert not _column_exists(cur, 'system_detail', 'score_breakdown')
            cur.execute("SELECT * FROM system_detail LIMIT 0")  # view still resolves
    finally:
        conn.close()


def test_orphaned_search_functions_removed():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT proname FROM pg_proc "
                "WHERE proname IN ('search_galaxy_economy', 'search_economy_near')"
            )
            assert cur.fetchall() == []
    finally:
        conn.close()
```

- [ ] **Step 2: Run the test against the current local DB to verify it fails**

Run (Windows): `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/reset_local_db.ps1 -ConfirmReset`
then: `python -m pytest tests/integration/test_drop_ratings_score_breakdown_migration.py -q`
Expected: FAIL — `test_ratings_score_breakdown_column_dropped` fails (column
still present) and `test_orphaned_search_functions_removed` fails (functions
still present). The two "preserved/valid" tests pass already.

If `DATABASE_URL` is unset in the shell, export the local test DSN first
(`postgresql://edfinder:edfinder@127.0.0.1:55432/edfinder`) — the `reset_local_db`
script provisions that database.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/integration/test_drop_ratings_score_breakdown_migration.py
git commit -m "test: real-Postgres regression for dropping ratings.score_breakdown (fails until migration 043)"
```

### Task 2: Migration 043 + manifest (make the test pass)

**Files:**
- Create: `sql/043_drop_ratings_score_breakdown.sql`
- Modify: `sql/migration-manifest.txt` (append one line)

**Interfaces:**
- Consumes: the schema after `042` (ratings has `score_breakdown`; `system_detail`
  view + the two functions reference it).
- Produces: the end-state Task 1 asserts.

- [ ] **Step 1: Write the migration**

```sql
-- 043_drop_ratings_score_breakdown.sql
--
-- Retire the dead ratings.score_breakdown column (entirely NULL since the
-- 2026-07-15 storage-recovery repack; reconstructed at read time from the
-- score_<economy> columns by apps/api/src/ratings_breakdown.py, never read
-- from the column). See docs/superpowers/plans/2026-08-10-scoring-cleanup-migration.md.
--
-- Landmines handled here:
--   * system_detail view selects r.score_breakdown directly (HARD dependency —
--     blocks the column drop). CREATE OR REPLACE VIEW cannot remove a column,
--     so drop + recreate without it.
--   * search_galaxy_economy() / search_economy_near() reference the column via
--     dynamic EXECUTE (soft dependency; latent-broken after the drop). Both are
--     orphaned (no caller in apps/ or scripts/) — dropped.
--   * The identically-named system_archetype_scores.score_breakdown column is
--     ALIVE and is deliberately NOT touched.
--
-- Every statement below is a metadata operation (the column is 100% NULL), so
-- this is effectively instant and holds ACCESS EXCLUSIVE on ratings only
-- momentarily.

BEGIN;

-- 1. Recreate system_detail without score_breakdown (hard blocker).
DROP VIEW IF EXISTS system_detail;
CREATE VIEW system_detail AS
SELECT
    s.*,
    gr.name AS galaxy_region,
    r.score,
    r.score_agriculture, r.score_refinery, r.score_industrial,
    r.score_hightech, r.score_military, r.score_tourism,
    r.economy_suggestion,
    r.elw_count, r.ww_count, r.ammonia_count,
    r.gas_giant_count, r.rocky_count, r.metal_rich_count,
    r.icy_count, r.rocky_ice_count, r.hmc_count,
    r.landable_count, r.terraformable_count,
    r.bio_signal_total, r.geo_signal_total,
    r.neutron_count, r.black_hole_count, r.white_dwarf_count,
    r.slots, r.body_quality, r.compactness,
    r.signal_quality, r.orbital_safety, r.star_bonus,
    r.computed_at AS score_computed_at
FROM systems s
LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
LEFT JOIN ratings r ON r.system_id64 = s.id64;

-- 2. Drop the two orphaned functions that reference the column via dynamic SQL.
--    (Confirmed unused: verify zero calls on production first — see runbook.)
DROP FUNCTION IF EXISTS search_galaxy_economy(TEXT, SMALLINT, INTEGER, INTEGER, SMALLINT);
DROP FUNCTION IF EXISTS search_economy_near(TEXT, REAL, REAL, REAL, REAL, SMALLINT, INTEGER, INTEGER, SMALLINT);

-- 3. Drop the dead column (targets ratings only — NOT system_archetype_scores).
ALTER TABLE ratings DROP COLUMN IF EXISTS score_breakdown;

COMMIT;
```

> **Before finalising the migration**, diff the recreated `system_detail` body
> against the current definition in `sql/003_functions.sql` and confirm the ONLY
> difference is the removed `r.score_breakdown,` line. If `003_functions.sql`'s
> view has drifted from what is quoted above (e.g. a later migration altered it),
> reproduce the *current* definition minus that one line — do not paste this block
> blindly.

- [ ] **Step 2: Append to the manifest**

Add exactly this line to the end of `sql/migration-manifest.txt` (no `|manual`
suffix — this runs in the standard automated path):

```
043_drop_ratings_score_breakdown.sql
```

- [ ] **Step 3: Apply to the local DB and run the test**

Run (Windows): `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/reset_local_db.ps1 -ConfirmReset`
(applies the manifest including 043)
then: `python -m pytest tests/integration/test_drop_ratings_score_breakdown_migration.py -q`
Expected: PASS — all four tests green.

- [ ] **Step 4: Commit**

```bash
git add sql/043_drop_ratings_score_breakdown.sql sql/migration-manifest.txt
git commit -m "feat(db): migration 043 — drop dead ratings.score_breakdown column"
```

### Task 3: Guard the reconstruction path + full local CI parity + PR

**Files:**
- Test: `tests/integration/test_drop_ratings_score_breakdown_migration.py` (add one test)

**Interfaces:**
- Consumes: `apps/api/src/ratings_breakdown.py::reconstruct_score_breakdown(rating_row, bodies=())`
  (verified signature: takes a mapping row + optional bodies sequence, returns a
  nested dict).
- Produces: proof the API `score_breakdown` response field is unaffected by the
  column drop (it is reconstructed from the `score_<economy>` columns, which
  Phase 1 keeps).

- [ ] **Step 1: Add the reconstruction-unaffected test**

```python
def test_reconstruction_unaffected_by_column_drop():
    # The API's score_breakdown response field is rebuilt from the
    # score_<economy> columns (which Phase 1 keeps), not read from the dropped
    # column. Prove reconstruction still runs and yields a JSON-serialisable
    # result from a rating row with no rocky bodies (the common path — the
    # function only touches `bodies` when rating_row['rocky_count'] is truthy).
    import json
    sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))
    from ratings_breakdown import reconstruct_score_breakdown  # noqa: E402

    row = {
        'score_agriculture': 10, 'score_refinery': 20, 'score_industrial': 30,
        'score_hightech': 40, 'score_military': 50, 'score_tourism': 60,
        'score_extraction': 15, 'rocky_count': 0,
    }
    out = reconstruct_score_breakdown(row, ())
    assert isinstance(out, dict) and out   # non-empty reconstruction
    json.dumps(out)                        # matches the JSONB API contract
```

This test does not require the database, but lives in the same file for cohesion
(the `pytest.mark.db` module marker is harmless for it). If you prefer a stricter
value assertion, read `reconstruct_score_breakdown`'s return statement in
`apps/api/src/ratings_breakdown.py` and assert the exact nested key (the return
groups economies/dimensions/bodies into sub-dicts — do not assume a flat shape).

- [ ] **Step 2: Run the full test file**

Run: `python -m pytest tests/integration/test_drop_ratings_score_breakdown_migration.py -q`
Expected: PASS (5 tests).

- [ ] **Step 3: Run lint + the focused local CI parity pass**

Run: `ruff check apps tests scripts shared_contracts`
Run: `make test-ci-local`
Expected: clean lint; migration-path + DB jobs green.

- [ ] **Step 4: Commit, push, open the PR**

```bash
git add tests/integration/test_drop_ratings_score_breakdown_migration.py
git commit -m "test: prove score_breakdown reconstruction survives the column drop"
git push -u origin db/drop-ratings-score-breakdown
gh pr create --title "feat(db): retire dead ratings.score_breakdown column (migration 043)" \
  --body "Landmine-aware drop of the NULL, unread ratings.score_breakdown column. Recreates the orphaned system_detail view without it, drops two orphaned search functions that referenced it via dynamic SQL, then drops the column. Does NOT touch the alive system_archetype_scores.score_breakdown (collision guard test included). Proven against real postgres:16-alpine. Plan: docs/superpowers/plans/2026-08-10-scoring-cleanup-migration.md"
```

- [ ] **Step 5: Watch checks; check Octopus Review + Codex before merge**

Follow the repo merge discipline: all required checks green, and read both the
inline review comments and the top-level review body. Verify any finding against
the code before acting. Merge with `gh pr merge <n> --squash --delete-branch`.

**Merging Phase 1 does NOT apply it to production.** Proceed to the runbook.

---

## Production apply runbook (owner-approved, separate from merge)

Migration 043 changes the production schema; run it deliberately, not as a side
effect of the merge.

1. **Verify the orphaned functions are truly unused on production** before
   trusting the `DROP FUNCTION` (belt-and-braces beyond the repo grep):

   ```sql
   SELECT funcname, calls
   FROM pg_stat_user_functions
   WHERE funcname IN ('search_galaxy_economy', 'search_economy_near');
   ```
   Expect zero rows or `calls = 0`. If either shows calls, STOP — re-scope to
   recreate that function without `score_breakdown` instead of dropping it, and
   re-review. (`pg_stat_user_functions` requires `track_functions` to be on; if
   it is off, treat the repo-grep + code review as the evidence and note it.)

2. **Re-run the `pg_depend` check from Task 1 against production** and confirm the
   only dependent object is the `system_detail` view.

3. **Apply via the ledger path** (never raw psql DDL):
   ```sh
   bash scripts/apply_migrations.sh
   ```
   The default finite timeouts are correct; do not override them for this
   migration.

4. **Verify the receipt:** confirm `043_drop_ratings_score_breakdown.sql` is in
   `schema_migrations`, `ratings` no longer has `score_breakdown`, and
   `system_archetype_scores.score_breakdown` still exists.

5. **Rollback note:** the drop is not reversible from data (the column was NULL,
   so nothing is lost), but the schema is restorable — a follow-up migration can
   re-add `score_breakdown JSONB DEFAULT NULL` and recreate the view/functions
   from `003_functions.sql` if ever needed. There is no data to restore because
   the column held none.

---

## Phase 2 — Retire the `score_<economy>` columns (DEFERRED — NOT executable here)

This is scoped for completeness; **do not start it from this plan.** Unlike the
`score_breakdown` drop, the `score_<economy>` columns (`score`,
`score_agriculture`, `score_refinery`, `score_industrial`, `score_hightech`,
`score_military`, `score_tourism`, and the related `score_extraction`) are
**live**, so retiring them is a scoring-path change, not a cleanup.

**Why it is deferred:**

- **It brushes the "no hidden scoring/CP/economy/optimiser changes" hard
  boundary.** `local_search.py` selects and economy-maps these columns
  (lines ~441, ~583–588, ~995) to power the Finder. Moving that onto archetype
  scores changes how the Finder sorts/scores unless proven value-equivalent.
- **The reconstruction depends on them.** `ratings_breakdown.py` rebuilds the API
  `score_breakdown` field *from* these columns. Dropping them requires
  re-sourcing reconstruction from the archetype scores first.
- **Blast radius:** `local_search.py` (live), `ratings_breakdown.py`,
  `models.py` response fields (`score_agriculture`…), the `system_detail` view,
  and — if not already dropped in Phase 1 — the two search functions.

**Prerequisites before Phase 2 can be planned as executable tasks:**

1. An explicit roadmap authorization that the Finder may move from legacy ratings
   scores to archetype scores (the "Scoring pivot: UI reflects archetype scores,
   not legacy ratings" Foundation-Sequence item).
2. A value-equivalence study (or an accepted, documented behaviour change) so the
   pivot is not a *hidden* scoring change.
3. A re-sourcing design for `reconstruct_score_breakdown` off archetype data.

Until those exist, Phase 2 stays documented-only.

---

## Self-review

- **Spec coverage:** Phase 1 covers the roadmap's "retire the column through a
  reviewed migration" for `score_breakdown`; Phase 2 documents the remaining
  "remove legacy score dependencies" as deferred with explicit prerequisites.
- **Placeholder scan:** none — the migration SQL, manifest line, and test code are
  complete and literal. The conditional guidance ("if the view has drifted,
  reproduce the current definition"; "for a stricter assertion, read the return
  shape") are guarded instructions, not placeholders.
- **Type/name consistency:** `system_detail`, `search_galaxy_economy`,
  `search_economy_near`, `ratings`, `system_archetype_scores`,
  `score_breakdown`, and `reconstruct_score_breakdown(rating_row, bodies=())`
  are used identically in the plan, the migration, and the tests. Test path,
  connection style (`psycopg2` + `os.environ['DATABASE_URL']`), and marker
  (`@pytest.mark.db`) match `tests/integration/test_bodies_composite_identity.py`.
- **Collision guard:** the archetype-column-preserved test is the explicit check
  that the same-named-column landmine did not cause the wrong table to be hit.
