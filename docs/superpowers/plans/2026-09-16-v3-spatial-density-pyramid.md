# V3 Spatial Density Pyramid (#2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `v3_spatial.cell_summary` as a reconciled, generation-scoped, multi-resolution density pyramid (scope B: all four aux counters), and repoint `/api/map/heatmap` at it — so the wide map shows a truthful full-catalogue density swirl.

**Architecture:** A Python (Psycopg 3) builder aggregates `v3_derived.system_search` (one row per system, with `x_ly/y_ly/z_ly`, `landable_count`, `station_count`, `has_biologicals`, `has_terraformable`) into `cell_summary` per pyramid level via a set-based `GROUP BY`, generation-scoped and immutable, with a hard reconciliation gate (Σ `system_count` == canonical `{gen}.systems` count). Publication mirrors the existing `scripts/v3_system_search.py` derived-product lifecycle. The API reads the active published pyramid.

**Tech Stack:** CPython 3.14, Psycopg 3 (sync/importer), PostgreSQL 18 (`v3_spatial`/`v3_derived`/`v3_meta` schemas, `cube` extension), FastAPI/asyncpg (map API), pytest with a disposable test DB via `tests/helpers/db_isolation`.

## Global Constraints

- Exact CPython 3.14; sync/importer DB access via **Psycopg 3**; parameterized SQL only; follow `docs/development/bulk-database-write-safety.md`.
- **Truth gate:** density comes only from real coordinates; **Σ `system_count` per complete level must equal the canonical `{gen}.systems` count** (hard gate); ratings are never an input/filter. Aux counters are physical facts.
- `cell_summary` is **immutable once written** (migration 004 triggers) — build then freeze; never UPDATE/DELETE published rows.
- Generation-scoped: everything keys on `derived_generation_id` referencing `v3_meta.derived_generation`.
- **No production DB writes from this task.** Build/validate on fixtures + a bounded subset only. The full-catalogue production build+publish is a separate owner-dispatched governed workflow (authored here, not executed).
- DB tests use disposable/test DBs via `tests/helpers/db_isolation` (fail-closed; never prod).
- `main` protected → branch `feat/v3-spatial-density-pyramid` → PR. API access from web stays via the generated facade (client work is #2b, not here).

## File Structure

- Create `scripts/v3_spatial_pyramid.py` — the builder + reconciliation + publication (mirrors `scripts/v3_system_search.py` structure: generation resolution, chunk/lifecycle, receipt).
- Create `tests/test_v3_spatial_pyramid.py` — builder + reconciliation tests on a fixture generation.
- Modify `apps/api/src/routers/map.py` — repoint `map_heatmap` (~172) onto `cell_summary`; keep a labelled fallback.
- Create `tests/test_map_heatmap_pyramid.py` — API contract tests for the repointed endpoint.
- Create `.github/workflows/v3-spatial-pyramid.yml` + `scripts/operator/actions/v3-spatial-pyramid.sh` — governed build/publish operator entry (mirrors `v3-system-search-*`); authored, not run.
- Modify `docs/development/v3-spatial-density-pyramid-design.md` — record the chosen pyramid ladder + source-path decision from Task 1.

Before writing tasks, the implementer reads `scripts/v3_system_search.py` in full (the reference for generation resolution, chunking, derived-product lifecycle, and receipts) and migration `sql/v3/migrations/004_v3_search_spatial_clusters.sql` (schemas for `cell_level`, `cell_summary`, `system_search`).

---

### Task 1: Confirm source completeness + register the pyramid levels

**Files:**
- Create: `scripts/v3_spatial_pyramid.py` (level registry + generation resolution skeleton)
- Test: `tests/test_v3_spatial_pyramid.py`
- Modify: `docs/development/v3-spatial-density-pyramid-design.md` (record ladder + source decision)

**Interfaces:**
- Produces: `PYRAMID_VERSION = 'pyramid_v1'` and `CELL_LEVELS: list[CellLevel]` (each: `level:int`, `cell_size_ly:float`, `intended_scale:str`, `target_count_min:int|None`, `target_count_max:int|None`); `register_cell_levels(conn, version) -> None` (idempotent INSERT into `v3_spatial.cell_level`); `resolve_source(conn, derived_generation_id) -> Literal['system_search','canonical']` (returns `'system_search'` when its row count for the generation equals the canonical `{gen}.systems` count, else `'canonical'`).

- [ ] **Step 1: Write failing tests**

In `tests/test_v3_spatial_pyramid.py` (reuse the `db_conn` fixture pattern from `tests/test_journal_commander_association.py`, which routes through `tests/helpers/db_isolation` and applies `sql/v3/migrations/*.sql`):

```python
def test_cell_levels_registered(db_conn):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, CELL_LEVELS, register_cell_levels
    register_cell_levels(db_conn, PYRAMID_VERSION)
    rows = db_conn.execute(
        "SELECT level, cell_size_ly FROM v3_spatial.cell_level WHERE spatial_pyramid_version=%s ORDER BY level",
        (PYRAMID_VERSION,),
    ).fetchall()
    assert [r[0] for r in rows] == [lvl.level for lvl in CELL_LEVELS]
    # sizes strictly decrease as level increases (coarse -> fine)
    sizes = [r[1] for r in rows]
    assert sizes == sorted(sizes, reverse=True)

def test_register_cell_levels_is_idempotent(db_conn):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels
    register_cell_levels(db_conn, PYRAMID_VERSION)
    register_cell_levels(db_conn, PYRAMID_VERSION)  # must not raise or duplicate
    n = db_conn.execute(
        "SELECT count(*) FROM v3_spatial.cell_level WHERE spatial_pyramid_version=%s",
        (PYRAMID_VERSION,),
    ).fetchone()[0]
    from scripts.v3_spatial_pyramid import CELL_LEVELS
    assert n == len(CELL_LEVELS)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && CORS_ORIGINS=http://testserver python -m uv run pytest ../../tests/test_v3_spatial_pyramid.py -k "cell_levels or idempotent" -v`
Expected: FAIL (module/functions not defined).

- [ ] **Step 3: Implement the level registry + source resolver**

In `scripts/v3_spatial_pyramid.py` define `PYRAMID_VERSION='pyramid_v1'` and a proposed power-of-two ladder (initial values; benchmarked in Task 7). Example concrete ladder (whole-Galaxy → local), each with `intended_scale` and target bounds:

```python
from dataclasses import dataclass

PYRAMID_VERSION = 'pyramid_v1'

@dataclass(frozen=True)
class CellLevel:
    level: int
    cell_size_ly: float
    intended_scale: str
    target_count_min: int | None = None
    target_count_max: int | None = None

# Coarse (whole galaxy) -> fine (local). Sizes benchmarked in Task 7; these are
# the deterministic starting ladder recorded in the design doc.
CELL_LEVELS = [
    CellLevel(0, 2560.0, 'wide'),
    CellLevel(1, 1280.0, 'wide'),
    CellLevel(2, 640.0, 'regional'),
    CellLevel(3, 320.0, 'regional'),
    CellLevel(4, 160.0, 'local'),
    CellLevel(5, 80.0, 'local'),
    CellLevel(6, 40.0, 'local'),
]

def register_cell_levels(conn, version: str = PYRAMID_VERSION) -> None:
    for lvl in CELL_LEVELS:
        conn.execute(
            """INSERT INTO v3_spatial.cell_level
                 (spatial_pyramid_version, level, cell_size_ly, intended_scale,
                  target_count_min, target_count_max)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (spatial_pyramid_version, level) DO NOTHING""",
            (version, lvl.level, lvl.cell_size_ly, lvl.intended_scale,
             lvl.target_count_min, lvl.target_count_max),
        )
```

For `resolve_source`, compare the `system_search` row count for the derived generation to the canonical `{gen}.systems` count (resolve the canonical schema the same way `apps/api/src/edfinder_api/v3_schema.py` does). Return `'system_search'` on exact equality, else `'canonical'`. (The reconciliation gate in Task 3 is the ultimate enforcement; this just picks the cheap path when safe.)

Record the chosen ladder + the source-path rule in the design doc's "Open items" (resolve the pyramid-level and legacy-fallback items).

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/api && CORS_ORIGINS=http://testserver python -m uv run pytest ../../tests/test_v3_spatial_pyramid.py -k "cell_levels or idempotent" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/v3_spatial_pyramid.py tests/test_v3_spatial_pyramid.py docs/development/v3-spatial-density-pyramid-design.md
git commit -m "feat(spatial): register pyramid_v1 cell levels + source resolver"
```

---

### Task 2: Cell aggregation → `cell_summary` (fixture generation, TDD)

**Files:**
- Modify: `scripts/v3_spatial_pyramid.py` (aggregation)
- Test: `tests/test_v3_spatial_pyramid.py`

**Interfaces:**
- Consumes: `CELL_LEVELS`, `register_cell_levels`.
- Produces: `build_level(conn, *, derived_generation_id, version, level, cell_size_ly, source) -> int` (inserts one row per occupied cell for that level from the chosen source; returns rows inserted) and `build_all_levels(conn, *, derived_generation_id, version=PYRAMID_VERSION, source) -> dict[int,int]` (level→cell count).

- [ ] **Step 1: Write failing tests**

Add a fixture that seeds a tiny generation: a `v3_meta.derived_generation` row, a canonical `{gen}.systems` set (or the legacy `systems` table for tests), and matching `v3_derived.system_search` rows with known coords + aux flags, then asserts the cells:

```python
@pytest.mark.anyio
def test_build_level_aggregates_counts_and_centroid(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, build_level
    register_cell_levels(db_conn, PYRAMID_VERSION)
    # size 100ly: two systems at (10,10,10),(20,20,20) share cell key (0,0,0);
    # one at (150,0,0) is its own cell. Aux: first two landable_count 1 & 2,
    # one has_biologicals; the third terraformable.
    n = build_level(db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
                    level=99, cell_size_ly=100.0, source='system_search')
    assert n == 2  # two occupied cells
    origin_cell = db_conn.execute(
        """SELECT system_count, landable_count, station_count,
                  biological_system_count, terraformable_system_count,
                  centroid_x_ly, centroid_y_ly, centroid_z_ly, origin_x_ly
             FROM v3_spatial.cell_summary
            WHERE derived_generation_id=%s AND level=99 AND origin_x_ly=0
            """, (seeded_generation,)).fetchone()
    assert origin_cell[0] == 2                      # system_count
    assert origin_cell[1] == 3                      # SUM(landable_count) 1+2
    assert origin_cell[3] == 1                      # biological_system_count (COUNT FILTER)
    assert origin_cell[5] == pytest.approx(15.0)    # centroid_x avg(10,20)
```

(Register `level=99` with a 100ly size in the fixture, or add a helper that inserts an ad-hoc `cell_level` row for the test size.)

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/api && CORS_ORIGINS=http://testserver python -m uv run pytest ../../tests/test_v3_spatial_pyramid.py -k build_level -v`
Expected: FAIL (`build_level` not defined).

- [ ] **Step 3: Implement the aggregation**

`build_level` runs one set-based INSERT…SELECT…GROUP BY. Cell key = integer triple `floor(coord/size)` encoded as `"ix.iy.iz"` (satisfies the `^[A-Za-z0-9_.-]{1,64}$` CHECK; negatives use `-`). `origin = key*size`. For `source='system_search'`:

```python
def build_level(conn, *, derived_generation_id, version, level, cell_size_ly, source) -> int:
    src = "v3_derived.system_search" if source == "system_search" else _canonical_systems_join(conn, derived_generation_id)
    # For system_search the aux columns are present; for canonical fall back the
    # SELECT must join bodies/stations (see _canonical_select). Both share the
    # same GROUP BY + cell-key math below.
    sql = f"""
    INSERT INTO v3_spatial.cell_summary
      (derived_generation_id, spatial_pyramid_version, level, cell_key,
       origin_x_ly, origin_y_ly, origin_z_ly, system_count,
       centroid_x_ly, centroid_y_ly, centroid_z_ly,
       landable_count, station_count, biological_system_count,
       terraformable_system_count, representative_system_id64)
    SELECT %(gen)s, %(ver)s, %(lvl)s,
           floor(x_ly/%(sz)s)::bigint || '.' || floor(y_ly/%(sz)s)::bigint || '.' || floor(z_ly/%(sz)s)::bigint,
           floor(x_ly/%(sz)s)*%(sz)s, floor(y_ly/%(sz)s)*%(sz)s, floor(z_ly/%(sz)s)*%(sz)s,
           count(*), avg(x_ly), avg(y_ly), avg(z_ly),
           coalesce(sum(landable_count),0), coalesce(sum(station_count),0),
           count(*) FILTER (WHERE has_biologicals),
           count(*) FILTER (WHERE has_terraformable),
           min(system_id64)
      FROM {src}
     WHERE derived_generation_id = %(gen)s
     GROUP BY 4,5,6,7
    """
    cur = conn.execute(sql, {"gen": derived_generation_id, "ver": version, "lvl": level, "sz": cell_size_ly})
    return cur.rowcount
```

(Adjust `GROUP BY` ordinals to the cell-key expressions; verify against Postgres. `build_all_levels` loops `CELL_LEVELS`.)

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/api && CORS_ORIGINS=http://testserver python -m uv run pytest ../../tests/test_v3_spatial_pyramid.py -k build_level -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/v3_spatial_pyramid.py tests/test_v3_spatial_pyramid.py
git commit -m "feat(spatial): aggregate system_search into cell_summary per level"
```

---

### Task 3: Reconciliation gate + validation receipt (TDD)

**Files:**
- Modify: `scripts/v3_spatial_pyramid.py`
- Test: `tests/test_v3_spatial_pyramid.py`

**Interfaces:**
- Consumes: `build_all_levels`.
- Produces: `reconcile(conn, *, derived_generation_id, version, canonical_count) -> dict` (per-level Σ system_count; raises `ReconciliationError` if any complete level's Σ != `canonical_count`); `build_receipt(...) -> dict` (source path, per-level cell + system counts, reconciliation result, coverage, pyramid version).

- [ ] **Step 1: Write failing tests**

```python
def test_reconcile_passes_when_sum_matches(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, build_all_levels, reconcile
    register_cell_levels(db_conn, PYRAMID_VERSION)
    build_all_levels(db_conn, derived_generation_id=seeded_generation, source='system_search')
    result = reconcile(db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
                       canonical_count=SEEDED_SYSTEM_COUNT)
    assert all(v == SEEDED_SYSTEM_COUNT for v in result['per_level_system_sum'].values())

def test_reconcile_fails_closed_on_incomplete_source(db_conn, seeded_generation_missing_one):
    from scripts.v3_spatial_pyramid import reconcile, ReconciliationError
    # build from a system_search missing one system -> Σ != canonical -> raise
    with pytest.raises(ReconciliationError):
        reconcile(db_conn, derived_generation_id=seeded_generation_missing_one,
                  version='pyramid_v1', canonical_count=SEEDED_SYSTEM_COUNT)
```

- [ ] **Step 2: Run to verify fail** — `... -k reconcile -v` → FAIL.

- [ ] **Step 3: Implement** `reconcile` (per level: `SELECT level, sum(system_count) FROM cell_summary WHERE derived_generation_id=%s AND spatial_pyramid_version=%s GROUP BY level`; compare each to `canonical_count`; raise `ReconciliationError` on mismatch) and `build_receipt` (assemble the dict; no secrets).

- [ ] **Step 4: Run to verify pass** — `... -k reconcile -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/v3_spatial_pyramid.py tests/test_v3_spatial_pyramid.py
git commit -m "feat(spatial): reconciliation gate + validation receipt"
```

---

### Task 4: Register the pyramid derived-product + mark READY; resolve via current generation (TDD)

**Architecture correction (from Task-4 investigation):** there is **no product-level `PUBLISHED` state and no per-pyramid pointer**. `v3_meta.derived_product.lifecycle_state` is only `BUILDING`/`READY`/`FAILED`; products (like `system_search`) build to **READY** and never publish. `PUBLISHED` + the atomic pointer are **generation-level** (`v3_meta.current_derived_generation`, swapped by `v3_meta.publish_derived_generation(actor, reason)`, gated on **all** products READY). So the pyramid is a derived-product built to READY; publishing the generation is the existing owner/ops cutover (out of scope here); the "active pyramid" is whichever belongs to the current published generation.

**Files:**
- Modify: `scripts/v3_spatial_pyramid.py`
- Test: `tests/test_v3_spatial_pyramid.py`

**Interfaces:**
- Produces: `mark_pyramid_ready(conn, *, derived_generation_id, version, receipt) -> None` — ensure the spatial-pyramid `v3_meta.derived_product` row exists for the generation and transition it `BUILDING → READY`, storing the validation `receipt` (mirror exactly how `scripts/v3_system_search.py` registers and transitions its product; confirm the `product_code`/columns/allowed transitions in `sql/v3/migrations/006_v3_derived_product_lifecycle.sql`). No PUBLISHED, no pointer swap.
- Produces: `pyramid_for_current_generation(conn) -> tuple[uuid, str] | None` — return `(derived_generation_id, version)` of the spatial pyramid belonging to the **current published derived generation** (`v3_meta.current_derived_generation`) when its spatial-pyramid product is READY, else `None`. This is what the API (Task 5) uses to find the active pyramid; resolve it the same way the app resolves the active `system_search` generation.

- [ ] **Step 1: Write failing tests** — `mark_pyramid_ready` sets the product `lifecycle_state='READY'` (assert the row); `pyramid_for_current_generation` returns the generation+version when that generation is current AND the pyramid product is READY, and `None` when no generation is current or the product isn't READY.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** mirroring `v3_system_search.py`'s product registration/READY transition (idempotent; parameterized; the receipt stored on the product row per the migration-006 columns). Do NOT invent a PUBLISHED state or pointer.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(spatial): register pyramid derived-product + mark READY; resolve via current generation`.

---

### Task 5: Repoint `/api/map/heatmap` onto the pyramid (TDD)

**Files:**
- Modify: `apps/api/src/routers/map.py` (`map_heatmap` ~172)
- Test: `tests/test_map_heatmap_pyramid.py`

**Interfaces:**
- Consumes: `pyramid_for_current_generation` (async equivalent via asyncpg in the API — resolve the current published derived generation whose spatial-pyramid product is READY), `cell_summary`.
- Produces: `map_heatmap` reads the pyramid of the current published generation: cells by bounds + a level chosen from the requested scale/voxel + target budget; response includes `generation_id`, `source_system_count`, `coverage_at`, `bounds`, `count`, `truncated`, and `cells:[{origin, centroid, system_count, landable_count, station_count, biological_system_count, terraformable_system_count}]`. When no current generation has a READY pyramid, return the existing legacy path behind an explicit `"source":"legacy-fallback"` flag.

- [ ] **Step 1: Write failing contract tests** (mirror existing `tests/integration/test_map_systems_viewport.py` style): seed a published pyramid; assert `/api/map/heatmap` returns cells from `cell_summary` with the metadata fields and honest `truncated`; assert the legacy-fallback flag path when none published.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** the repoint (asyncpg query on `cell_summary` for the active generation; level selection from bounds/budget; keep the legacy branch labelled).
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(api): serve /api/map/heatmap from reconciled cell_summary pyramid`.

---

### Task 6: Governed build/publish workflow + operator action (authored, not run)

**Files:**
- Create `.github/workflows/v3-spatial-pyramid.yml` + `scripts/operator/actions/v3-spatial-pyramid.sh`
- Modify `docs/development/v3-spatial-density-pyramid-design.md` (record the governed run procedure)

**Interfaces:** Produces a manual-only, target-confirmed operator workflow (mirror `v3-system-search-profile.yml` / the ratings operator workflows) that runs `scripts/v3_spatial_pyramid.py` against the pinned generation, emits the receipt artifact, and requires owner dispatch. **Do not run it** — this task authors and validates the YAML/shell only.

- [ ] **Step 1:** Author the workflow + action mirroring an existing `v3-system-search-*` operator workflow (same credential boundary, literal target confirmation, receipt upload). 
- [ ] **Step 2:** Validate YAML/shell locally (`scripts/checks` lane if present; `actionlint`/`bash -n`). No execution against any host.
- [ ] **Step 3:** Document the owner run sequence in the design doc.
- [ ] **Step 4: Commit** `feat(ops): governed spatial-pyramid build/publish workflow (manual-only)`.

---

### Task 7: Full validation, benchmark note, and PR

**Files:** none (validation + PR)

- [ ] **Step 1: Repo + backend gates**

```bash
make state-check
cd apps/api && CORS_ORIGINS=http://testserver python -m uv run pytest ../../tests/test_v3_spatial_pyramid.py ../../tests/test_map_heatmap_pyramid.py -v
```
Expected: PASS.

- [ ] **Step 2: Bounded-subset build** on the disposable DB (a few-thousand-system fixture generation) end-to-end: `register_cell_levels` → `build_all_levels` → `reconcile` → `mark_pyramid_ready` → make the fixture generation current (or assert `pyramid_for_current_generation`) → hit `/api/map/heatmap`. (Generation publish `v3_meta.publish_derived_generation` is the owner/ops step, exercised via the fixture pointer here, not run against prod.) Record per-level cell counts and confirm they fall within the `cell_level` target bounds; note any ladder adjustment in the design doc (resolves the benchmark open item).

- [ ] **Step 3: Self-review** the diff with the `code-review` skill (adversarial pass); fix findings.

- [ ] **Step 4: Push + open PR**

```bash
git push -u origin feat/v3-spatial-density-pyramid
gh pr create --fill --base main
```
PR body notes: truth-gate reconciliation, scope B, source-path decision, that production build/publish is a separate owner-dispatched governed step (not run here), and the Codex-waiver status.

- [ ] **Step 5: Owner step (post-merge, governed):** dispatch the Task-6 workflow to build+publish the full-catalogue pyramid to production, then #2b consumes it.

---

## Self-Review

**Spec coverage:** source decision + levels (Task 1), scope-B aggregation (Task 2), reconciliation/receipt (Task 3), publication/rollback (Task 4), API repoint + fallback (Task 5), governed workflow (Task 6), validation + subset build + PR (Task 7). All spec sections map to a task.

**Placeholder scan:** Core SQL (aggregation, cell-key, reconciliation) is concrete. Publication (Task 4) and the operator workflow (Task 6) are specified as "mirror `scripts/v3_system_search.py` / `v3-system-search-*`" — a concrete existing reference, not a vague placeholder; the implementer reads that file (named) to match the exact lifecycle/pointer mechanics, which are repo-specific and must not be guessed.

**Type/name consistency:** `PYRAMID_VERSION`, `CELL_LEVELS`, `register_cell_levels`, `build_level`, `build_all_levels`, `reconcile`/`ReconciliationError`, `build_receipt`, `mark_pyramid_ready`, `pyramid_for_current_generation` are defined and consumed consistently across tasks; the API (Task 5) consumes `pyramid_for_current_generation` + `cell_summary` columns exactly as Task 2 writes them. (Task 4 corrected: product→READY + generation-level publish, no per-pyramid PUBLISHED/pointer.)
