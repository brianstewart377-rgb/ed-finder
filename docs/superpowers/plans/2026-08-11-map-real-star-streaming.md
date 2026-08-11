# Real-Star LOD Streaming ("in-game zoom") — Design & Phased Plan

> **Status:** Committed project, design agreed 2026-08-11. Multi-phase; implementation is a set of focused follow-on sessions, not a single sitting. This is the #6 item from the map menu — the "feels like the game" leap.

**Goal:** When the user zooms into the galaxy map past a threshold, stream and render the *actual individual star systems* for the visible region, colored by spectral type — the dense real starfield Elite Dangerous's in-game map shows on zoom, instead of our current aggregate heatmap.

---

## What is already built (the head start)

- **Rendering is mostly done.** The **glow point shader** (feature #2, merged `8365a58e`) and the **`spectralStarColor` blackbody map** (`features/system-detail/body-thumbnail/bodyThumbnailParams.ts`, from feature #3) are both in `main`. "Real stars, glowing, in their true colors" — the *look* — largely exists; #6's new work is **streaming/LOD + a backend viewport endpoint**, not the visuals.
- **Spatial infrastructure exists.** `systems` already carries a two-level spatial grid (`grid_cell_id` → `macro_grid_id`, both indexed: `idx_sys_grid`, `idx_sys_macro`) *and* coordinate indexes (`idx_sys_x/y/z`, composite `idx_sys_coords`). The 200-LY score **heatmap** (`/api/map/heatmap`, ≤50k voxels) is effectively the top level of the pyramid.
- **Bounded-query precedent exists.** `GalaxySearchRequest` + `in_bounding_box(...)` (sql/003_functions) already query systems within a frustum; the viewport endpoint is a capped, read-only variant of the same pattern.

## Locked decisions (agreed 2026-08-11)

1. **Live bbox query, not a precomputed tile pyramid — for v1.** Use a capped viewport query on `idx_sys_coords` + `LIMIT`. Only build an offline octree/tile pyramid if measured perf demands it. (Research leaned toward precomputed tiles for billion-point scale, but our indexes + a per-viewport cap make live queries a far cheaper, sufficient v1 — measure before optimizing.)
2. **Importance ranking:** at partial zoom show the *notable* stars first — populated/named systems, then by star brightness — so the field fills in from "important" to "everything" as you zoom deeper. Never a random subset.
3. **Zoom threshold + cap:** a tuned hysteresis switch point (heatmap ⟷ real stars) and a hard per-viewport cap of ~**20–40k** systems on screen. Never render the full 186M.

## Boundaries (must hold)

- **Explore-only, read-only.** No canonical writes; no planner-map fusion; the viewport endpoint reads `systems` only. Consistent with the map's Explore mandate and `docs/ROADMAP.md`.
- **Needs its own roadmap slice.** This is a new map *capability*, beyond "bounded post-cutover polish." Add a roadmap entry before/with Phase 1 (draft in Phase 1, Step 0) rather than sliding it in as polish.
- **Keep the aggregate lane.** The heatmap stays as the zoomed-out view; #6 adds the zoomed-in lane, it does not replace the aggregate.

---

## Phase 1 — Backend viewport endpoint (the data lane)

**Deliverable:** `GET /api/map/systems` (or `POST` with a bbox body) returning capped, importance-ordered individual systems within a bounding box.

- **Step 0 — Roadmap slice.** Add a short `docs/ROADMAP.md` entry authorizing "real-star viewport streaming on the Explore map (read-only)"; sync the CLAUDE.md stage line if needed ([[feedback_sync_claude_md_roadmap_status]]).
- **Step 1 — Contract.** Request: `{ min_x,max_x, min_y,max_y, min_z,max_z, limit (≤ cap), min_importance? }`. Response: `{ systems: [{ id64, name, x, y, z, main_star_class, populated }], truncated: bool }`. Add to `models.py` (drives `api.gen.ts`); validate bounds with `ge/le` guards (cf. `test_pagination_input_bounds.py`) and reject absurd volumes.
- **Step 2 — Query.** `SELECT id64, name, x, y, z, main_star_class, (population>0) AS populated FROM systems WHERE x BETWEEN … AND y BETWEEN … AND z BETWEEN … ORDER BY <importance> LIMIT $cap`. Importance v1: `population > 0 DESC, <brightness-from-star-class>`, using `idx_sys_coords`. Cache per rounded-bbox in Redis (short TTL); rate-limit like the other map endpoints.
- **Step 3 — Tests.** Real-Postgres integration test (like the map suite): bbox returns only in-bounds systems, honors the cap + `truncated`, orders populated first; input-bounds rejection test. `EXPLAIN` confirms index use (not a seq scan).
- **Step 4 — PR + verify** (data-invariants, openapi-types drift, Review Lab).

## Phase 2 — Client LOD (render real stars on zoom)

**Deliverable:** the map switches from heatmap (zoomed out) to a glowing, spectral-colored real-star `Points` cloud (zoomed in).

- **Step 1 — API client.** Add `mapSystems(bbox, limit)` to `lib/api/map.ts` (+ its generated type).
- **Step 2 — Viewport hook.** A `useViewportSystems` hook: on camera settle (debounced), compute the frustum bbox + zoom, and above the threshold fetch systems for the visible bbox; LRU-cache results by rounded bbox; cancel stale requests.
- **Step 3 — Render layer.** A `<RealStarLayer>` rendering the fetched systems as a `Points` cloud, reusing the merged **`GlowPointsMaterial`** with **per-vertex spectral colors** (`spectralStarColor(main_star_class)` → color buffer). Selectable/hoverable like the existing system dots.
- **Step 4 — LOD switch.** Hysteresis: below threshold render the heatmap only; above it fade the heatmap down and the real stars up (avoid a hard pop). Cap enforced; show a subtle "showing brightest N" affordance when `truncated`.
- **Step 5 — Tests + Review Lab visual.** Map vitest for the layer + hook; Review Lab exercises the zoom in-browser.

## Phase 3 — Importance & performance tuning

- Refine the importance ranking (brightness model from spectral class/abs-magnitude; optionally weight by rating/notability).
- Tune the threshold, cap, and debounce against real feel; add request coalescing.
- **Only if measured perf is inadequate:** build the offline tile pyramid (octree from the `grid_cell/macro_grid` hierarchy; serve static tiles) per the research (`deck.gl` 3D-Tiles or `potree-core`/`three-loader`, BSD-2). Decide this on data, not spec.

---

## Risks / open questions
- **Query latency at deep zoom on dense regions** (the Bubble/Colonia): the cap protects the client, but the DB query still scans a dense bbox — validate `idx_sys_coords` performance with `EXPLAIN (ANALYZE)` on a dense region in Phase 1; add `grid_cell_id` filtering if needed.
- **`main_star_class` completeness:** not all systems have a scanned main star; color falls back to the `spectralStarColor` default — fine.
- **Star brightness for ranking:** deriving apparent/absolute magnitude from spectral class is approximate; v1 can rank by `population>0` + class order and refine in Phase 3.
- **Prod Node/deploy:** frontend changes ship via the owner-approved deploy (glow/#3 are already awaiting one); no new infra.
