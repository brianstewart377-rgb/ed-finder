# V3 Finder F2c (ranking profile) + F3 slice 1 (API cutover) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship a versioned ranking profile (`v3-colony-potential-1`) and repoint the two Finder endpoints the UI needs (`POST /api/local/search`, `GET /api/archetypes/rankings`) off the legacy V2 relations onto the published V3 `v3_app.*` projections through that profile.

**Architecture:** A pure, DB-free ranking-profile module (identity + a parameterized-SQL builder) under `apps/api/src/ranking/`. Routers select a `ranking_version` + pass query params; the profile emits the `WHERE`/`ORDER BY` over the published `v3_app.*` views; the router executes it generation-pinned exactly like `apps/api/src/routers/ratings_v4.py`'s `_current()` pattern. No ranking SQL in routers.

**Tech Stack:** FastAPI, **asyncpg** (async; NOT psycopg — the API layer is async), Pydantic models in `apps/api/src/models.py`, pytest. Design: `docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md`.

## Global Constraints

- **asyncpg async** throughout the API (`async def`, `await connection.fetch(...)`, `$1` placeholders). Parameterized SQL only — never interpolate values.
- **Generation-pinned reads:** resolve the published generation once per request via the `_current()` pattern (`v3_meta.current_derived_generation JOIN derived_generation WHERE lifecycle_state='PUBLISHED'`, 404 if none), then read `v3_app.*` views (which already embed that join) or `WHERE derived_generation_id=$1`.
- **No legacy/`public.*`** in the repointed paths: no `systems`, `ratings`, `mv_archetype_rankings`, `system_archetype_scores`, `system_archetype_traits`, `cluster_summary`.
- **Ranking logic lives in the profile module**, not routers. Routers select `ranking_version` + pass params.
- `ranking_version = "v3-colony-potential-1"`; its `ranking_sha256` is the sha256 of the canonical profile spec; every ranked response echoes `{ranking_version, ranking_sha256, derived_generation_id, publication_sequence}`.
- Tier thresholds (from the projection): S≥88, A≥76, B≥60, C≥45, else D.
- Behavioural parity with V2, **numeric parity is a non-goal**. Confidence×completeness is a SOFT modifier (never a hard filter): unknown ≠ absent.
- Ranking order: hard filters first (body-count sliders / feature minima / min-score / distance / region) → primary score (archetype_score | economy potential | best_colony_potential) → × uncertainty factor → distance tie-break → system_id64.

---

### Task 1: Ranking-profile identity module (pure, no DB)

**Files:**
- Create: `apps/api/src/ranking/__init__.py`, `apps/api/src/ranking/profile.py`
- Test: `apps/api/tests/ranking/test_profile_identity.py` (mirror the repo's existing api test dir layout — confirm with `ls apps/api/tests`)

**Interfaces:**
- Produces: `RANKING_VERSION = "v3-colony-potential-1"`; a frozen `PROFILE_SPEC` (dataclass or dict) holding the canonical, hashable definition — `primary_score_rule` (archetype→archetype_score / economy→potential_score / none→best_colony_potential), `uncertainty` params (the confidence×completeness factor curve — start with `factor = confidence * completeness`, both in [0,1], documented as tunable), `tie_break` (`["distance","system_id64"]`), `tier_thresholds` ({S:88,A:76,B:60,C:45}), and the `hard_filter_keys` list; `ranking_sha256() -> str` (sha256 of the canonicalized spec via the same `_json`/sorted-keys style used in `scripts/v3_system_archetype.py`); `RANKING_VERSIONS: dict[str,Spec]` registry; `resolve(version) -> Spec`.

- [ ] **Step 1: Write the failing identity + drift-guard test**

```python
# apps/api/tests/ranking/test_profile_identity.py
from edfinder_api.ranking.profile import (
    RANKING_VERSION, PROFILE_SPEC, ranking_sha256, resolve, RANKING_VERSIONS,
)

def test_version_and_registry():
    assert RANKING_VERSION == "v3-colony-potential-1"
    assert RANKING_VERSION in RANKING_VERSIONS
    assert resolve(RANKING_VERSION) is PROFILE_SPEC

def test_ranking_sha_is_stable_and_matches_recorded():
    # the recorded sha in the spec must equal the sha recomputed from the live spec
    assert ranking_sha256() == PROFILE_SPEC["ranking_sha256"]

def test_tier_thresholds_match_projection_contract():
    assert PROFILE_SPEC["tier_thresholds"] == {"S": 88, "A": 76, "B": 60, "C": 45}
```

- [ ] **Step 2: Run to verify it fails**
Run: `cd /c/Users/brian/ed-finder/apps/api && <api-python> -m pytest tests/ranking/test_profile_identity.py -q`
Expected: FAIL (module missing). (Find the API test invocation the repo uses — check `apps/api/pyproject.toml`/CI; it is uv-managed CPython 3.14. Confirm the import root: existing tests import `edfinder_api.*`.)

- [ ] **Step 3: Implement `apps/api/src/ranking/profile.py`**
Define `PROFILE_SPEC` as a canonical dict with all fields above, compute `ranking_sha256()` by hashing the spec with sort_keys/compact separators (exclude the stored `ranking_sha256` field itself from the hash, then store it), a `RANKING_VERSIONS` registry, and `resolve()`. Pure stdlib (`hashlib`, `json`, `dataclasses`). No DB, no SQL execution here.

- [ ] **Step 4: Run to verify it passes** — `pytest tests/ranking/test_profile_identity.py -q` → PASS.
- [ ] **Step 5: Commit** — `feat(finder): F2c ranking-profile identity (v3-colony-potential-1)`

---

### Task 2: Ranking-profile SQL builder (pure, no DB)

**Files:**
- Modify: `apps/api/src/ranking/profile.py` (add the builder)
- Test: `apps/api/tests/ranking/test_profile_sql.py`

**Interfaces:**
- Consumes: `PROFILE_SPEC` (Task 1).
- Produces: `build_ranked_query(spec, *, picked_archetype: str|None, picked_economy: str|None, hard_filters: dict, reference_coords: tuple|None, limit: int, offset: int) -> (sql: str, params: list)` — returns a parameterized SELECT over the `v3_app.system_search s` + `v3_app.system_archetype_summary sum` (+ `v3_app.system_archetype a` joined on the picked archetype_key when `picked_archetype`), with `$1..$n` params, hard filters in `WHERE`, the primary score × uncertainty in `ORDER BY`, distance/system_id64 tie-break, `LIMIT/OFFSET`. The generation pin is applied by the caller (the `v3_app.*` views resolve `current_derived_generation`), so the builder does NOT add a generation predicate. It must emit NO literal values — only `$n` placeholders — and must never reference legacy relations.

- [ ] **Step 1: Write failing tests** (assert generated SQL/params shape, no DB):

```python
# apps/api/tests/ranking/test_profile_sql.py
from edfinder_api.ranking.profile import PROFILE_SPEC, build_ranked_query

def test_archetype_pick_orders_by_that_archetype_score():
    sql, params = build_ranked_query(
        PROFILE_SPEC, picked_archetype="mining_hub", picked_economy=None,
        hard_filters={"min_development_score": 60, "elw_count_min": 1},
        reference_coords=(0.0, 0.0, 0.0), limit=24, offset=0,
    )
    assert "v3_app.system_archetype" in sql and "mv_archetype_rankings" not in sql
    assert "systems" not in sql.split("v3_app.system_search")[0]  # no legacy `systems`
    assert "ORDER BY" in sql
    # uncertainty modifier present in the ordering expression
    assert "confidence" in sql.lower() and "completeness" in sql.lower()
    # every value is a param, not a literal
    assert "60" not in sql and "$" in sql

def test_no_pick_orders_by_best_colony_potential():
    sql, _ = build_ranked_query(
        PROFILE_SPEC, picked_archetype=None, picked_economy=None,
        hard_filters={}, reference_coords=None, limit=10, offset=0,
    )
    assert "best_colony_potential" in sql

def test_hard_filters_are_where_not_order():
    sql, params = build_ranked_query(
        PROFILE_SPEC, picked_archetype=None, picked_economy=None,
        hard_filters={"has_rings": True, "terraformable_count_min": 2},
        reference_coords=None, limit=10, offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "terraformable_count" in where
```

- [ ] **Step 2: Run → FAIL.**  **Step 3:** implement `build_ranked_query`.  **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(finder): F2c ranking-profile SQL builder`

---

### Task 3: Repoint `POST /api/local/search` onto V3 via the profile

**Files:**
- Modify: `apps/api/src/routers/search.py` (the `/api/local/search` handler), and the search implementation it delegates to (`apps/api/src/local_search.py`) — replace the legacy `systems`/`ratings`/`mv_archetype_rankings` path for this endpoint with a V3 path that calls `build_ranked_query` and executes it generation-pinned.
- Test: `apps/api/tests/.../test_local_search_v3.py`

**Interfaces:**
- Consumes: `_current()`-style pin (mirror `apps/api/src/routers/ratings_v4.py:189-200`), `build_ranked_query` (Task 2). Keeps the existing `LocalSearchRequest` in / `SearchResponse` out (Task 5 adds the identity block).

**Implementer instructions (read before coding):**
1. Read `apps/api/src/routers/ratings_v4.py` `_current()` + `_read_system()` for the exact asyncpg generation-pinned read pattern to mirror.
2. Read the current `POST /api/local/search` handler (`search.py:136+`) and the function it calls in `local_search.py` — you are replacing the legacy read for this path, not adding a parallel one (the module comment warns against a parallel impl).
3. Map `LocalSearchRequest` fields → `build_ranked_query` args: `filters.economy`→picked_economy; an archetype param (add to the request model if the UI needs archetype-picked search — else picked_archetype=None for now); body_filters/require_*/min_development_score/star_types→hard_filters; reference_coords; size/from→limit/offset.
4. Execute the built query with asyncpg against the `v3_app.*` views, generation-pinned; shape rows into `SearchResponse` (set `source` to the ranking identity, e.g. `"v3:v3-colony-potential-1"`).
5. Find and use the repo's existing **async API test harness** (how current search/ratings_v4 endpoints are tested against a DB — check `apps/api/tests/`); populate the fixture with the F2b builder so `system_archetype` exists (reuse the `canonical_database` + build pattern from `tests/test_ratings_v4_system_search.py`, adapted for the async client).

- [ ] **Step 1: Write the failing contract test** — a request returns generation-pinned results ordered by the profile, reads no legacy relation, honours a hard filter, and (once Task 5 lands) carries the ranking identity. Assert results are ordered by best_colony_potential (no pick) and that a body-count hard filter excludes non-matches.
- [ ] **Step 2: Run → FAIL.**  **Step 3:** implement the V3 path.  **Step 4: Run → PASS**, plus the existing search tests still green (or updated to the V3 contract).
- [ ] **Step 5: Commit** — `feat(finder): F3 repoint /api/local/search onto V3 projections via ranking profile`

---

### Task 4: Repoint `GET /api/archetypes/rankings` onto V3 via the profile

**Files:**
- Modify: `apps/api/src/routers/archetypes.py` (the `/rankings` handler; leave `/rerank`, `/system`, `/simulate`, `/profiles` for slice 2 — do NOT touch them).
- Test: `apps/api/tests/.../test_archetype_rankings_v3.py`

**Interfaces:** Consumes `_current()` pin + `build_ranked_query` with `picked_archetype=<the required `archetype` query param>`.

**Implementer instructions:** Read the current `/rankings` handler (`archetypes.py:243+`, orders by a `_SCORE_COL` over `mv_archetype_rankings`). Replace it with `build_ranked_query(picked_archetype=archetype, ...)` over `v3_app.system_archetype`, generation-pinned; map the existing filter params (min_score, galaxy_region, max_distance_ly, has_elw, min_slots, limit, offset) to `hard_filters`. Keep `ArchetypeRankingsResponse` (Task 5 sets its `source`/identity). Validate the `archetype` param against `RANKING_VERSIONS`' known archetype keys (the 8 V3 keys), 422 on unknown.

- [ ] **Step 1: failing contract test** (rank-by-archetype returns V3-ordered results for a known key, 422 on unknown key, no `mv_archetype_rankings` read). **2:** FAIL. **3:** implement. **4:** PASS. **5:** Commit — `feat(finder): F3 repoint /api/archetypes/rankings onto V3`

---

### Task 5: Ranking-identity block, confidence badge, and no-legacy assertion

**Files:**
- Modify: `apps/api/src/models.py` (extend `SearchResponse` + `ArchetypeRankingsResponse` with a `ranking: {ranking_version, ranking_sha256, derived_generation_id, publication_sequence}` block; add per-result `confidence`/`completeness` badge fields), the two repointed handlers to populate them.
- Test: `apps/api/tests/.../test_ranking_identity_and_no_legacy.py`

- [ ] **Step 1: failing tests** — (a) both endpoints' responses include the ranking-identity block with `ranking_version=="v3-colony-potential-1"` and a non-empty `ranking_sha256` equal to `ranking_sha256()`; (b) each result carries `confidence`/`completeness`; (c) a static test that `search.py`, `archetypes.py` (the `/rankings` + `/local/search` paths), and the V3 search path in `local_search.py` contain no `mv_archetype_rankings`/`system_archetype_scores`/`system_archetype_traits`/` FROM systems `/`public.` string.
- [ ] **Step 2:** FAIL. **3:** implement (prefer extending existing models over new ones, per the generated-facade contract; regenerate/refresh OpenAPI types if the web facade check requires it). **4:** PASS + full api test suite green. **5:** Commit — `feat(finder): F2c/F3 ranking identity + confidence badge + no-legacy guard`

---

## Out of scope (later)
- F3 slice 2: `/rerank`, `/system/{id64}`, `/simulate`, `/cluster`, `/galaxy`.
- F4 (the `apps/web` Finder UI) — unblocked by this plan.
- The governed prod build/publish of `system_archetype`; the coefficient-calibration probe; the V2 divergence report.

## Self-Review
- **Spec coverage:** profile identity+sha (T1) + SQL builder (T2) = F2c; endpoint repointing (T3/T4) + identity/badge/no-legacy (T5) = F3 slice 1. Divergence report + slice 2 explicitly deferred, matching the spec.
- **Placeholder scan:** T1/T2 carry concrete code; T3–T5 are existing-codebase edits that (per the repo's own patterns) reference the exact files + the `ratings_v4.py` template to mirror and name the test assertions — the implementer reads current router/model code (flagged) rather than the plan fabricating async handlers it cannot verify. `<api-python>` = the repo's uv-managed CPython 3.14 api test invocation (implementer confirms from `apps/api/pyproject.toml`/CI).
- **Type consistency:** `build_ranked_query` signature + `PROFILE_SPEC`/`ranking_sha256` names are fixed in T1/T2 and consumed unchanged in T3–T5.
