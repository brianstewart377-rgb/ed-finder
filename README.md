# ED:Finder — Self-Hosted Colony Finder

A self-hosted Elite Dangerous system finder for locating uncolonised candidates.
Runs as two Docker containers (FastAPI backend + Nginx frontend) on any Linux host
including Raspberry Pi.

---

## Current Status

| Component | Status |
|-----------|--------|
| Frontend  | ✅ Latest — v3.45, all 58 audit checks pass |
| Backend   | ✅ All endpoints functional |
| Local DB  | ✅ Phase 1 (systems) + Phase 2 (bodies) supported |
| EDDN      | ✅ Real-time colonisation updates (24/7 ZeroMQ listener) |
| Delta     | ✅ Nightly Spansh galaxy_1day.json.gz applied at 02:00 UTC |
| Audit     | ✅ `python3 localdb/audit.py` — 58 checks, 0 bugs |
| Git       | ✅ `main` branch |

---

## Features Implemented

### Finder Tab
- **Search** — distance-filtered system search via Spansh API or local galaxy DB
- **Deep Scan** — exhaustive local DB scan (no rate limit) or distance-band slicing via Spansh
- **Uncolonised filter** — multi-signal heuristic (population, factions, is_colonised, is_being_colonised)
- **Body-type sliders** — dual min/max range for ELW, Water worlds, Rocky, Icy, Ammonia, Gas Giants, etc.
  - ⚠️ Requires Phase 2 local DB or Spansh body enrichment to function
  - Shows orange warning banner if sliders are set but body data is unavailable
- **Rating score range** — dual min/max slider (0–100) with live re-filter as you drag
- **Economy filter** — AI-inferred economy type (Refinery, Agriculture, Industrial, High Tech, Military, Tourism)
- **Slot filters** — min landable bodies, min signal count
- **Toggle filters** — Bio, Geo, Ring, Terraformable, Volcanism, No Tidal Lock, Zero Population
- **Sort** — Rating ↓ (default), Distance ↑, Economy A-Z, Body Count ↓, Population ↓
- **Export** — CSV and JSON download of current results
- **Re-filter** — re-apply filters to already-loaded results without a new API call
- **Share URL** — shareable link with all filter state encoded in hash
- **Search history** — last 20 searches with restore and preset save/load

### Distance Sliders
> ⚠️ **Important behaviour change (v3.30):** The distance sliders no longer automatically
> trigger a new search when you release the slider thumb. Moving the distance slider
> after results have been displayed will NOT change or replace your current results.
> **You must press the Search button to apply a new distance range.**
> The label shows `↵ press Search` as a reminder when you move the slider.
> Rating sliders still update results live as you drag (they are purely client-side).

### System Cards
- Rating score (0–100) with colour-coded badge
- Economy suggestion with confidence indicator
- Population potential estimate
- Colonised/Free status pill using full heuristic
- Body pills with detail popovers (gravity, signals, rings, tidal lock, surface temperature)
- Warning tags (tidal lock Agriculture risk, volcanism, ELW/Water worlds, exotic stars)
- Score breakdown mini-bar (Slots, Body Quality, Compactness, Signal Quality, Orbital Safety)
- Pin to Pinned tab
- Add to Compare (up to 6 systems side-by-side radar chart)
- Personal notes (stored in backend SQLite)
- Add to Watchlist
- Open in Optimizer

### Optimizer Tab
- Auto-suggest best economy based on body composition
- Plan A (low disruption), Plan B (moderate), Plan C (maximum output)
- Step-by-step build order with cargo cost breakdown
- Contamination warnings for conflicting structures

### Route Planner Tab
- Multi-hop waypoint route builder
- Per-hop system search within radius
- Best Pick suggestion per hop (uses full colonisation heuristic)
- "Load into Finder" for any hop
- Save / load route to localStorage

### Watchlist Tab
- Track systems for colonisation status and population changes
- Per-system alert config (notify on colonised, notify when pop exceeds threshold)
- Background poll every 5 minutes with browser notifications
- Change log with diff display

### Galactic Map Tab
- Canvas-based 2D projection (XZ/XY/YZ planes)
- Zoom (mouse wheel), pan (drag), double-click to reset
- Colour modes: rating, economy, distance
- Pinned and watchlist system overlays
- PNG export

### Compare Tab
- Side-by-side table with winner highlighting
- Radar chart (score dimensions)
- CSV export

---

## User Guide

### Basic Search Workflow

1. **Set your reference system** — type a system name in the "Reference System" box and select from the autocomplete dropdown. You **must** select from the dropdown; typing without selecting will warn you.

2. **Set distance** — use the Max Distance slider. The label shows `↵ press Search` when you change it — this is a reminder that distance changes require a new search. Rating sliders update live.

3. **Press SCAN** — results appear sorted by rating by default.

4. **Read the results** — each card shows:
   - System name + distance from your reference
   - Economy icon + confidence dot (green=high, gold=medium, red=low)
   - COL (colonised) or FREE pill
   - Population potential
   - Rating badge (color-coded: green ≥ 70, gold 50–70, red < 50)
   - Score mini-bar breakdown
   - Click the card header to expand body pills

5. **Use body filters** — set ELW/Water World/etc sliders to find systems with specific bodies.  
   ⚠️ These only work when body data is available (Phase 2 local DB or Spansh enrichment). If you set a body slider and see a warning banner, the filter cannot be applied until Phase 2 import completes.

### Filter Behaviour Reference

| Filter | Behaviour | When It Applies |
|--------|-----------|----------------|
| Max/Min Distance | Requires new Search (↵ hint shown) | Server-side (DB/API) |
| Results per Page | Requires new Search | Server-side |
| Body sliders (ELW, WW, etc.) | Live in Re-filter | Client-side (needs body data) |
| Rating slider | Live as you drag | Client-side |
| Economy dropdown | Live in Re-filter | Client-side |
| Toggles (Bio, Geo, etc.) | Live in Re-filter | Client-side |
| Min Landable / Min Signals | Live in Re-filter | Client-side |

> **Important:** If you change the **reference system** you **must press Search** to retrieve results for the new location. The existing result cards are NOT automatically replaced when you change the reference — they stay on screen from the previous search until you press Search.

Use the **🔄 Re-filter** button to re-apply client-side filters to already-loaded results without re-fetching.

### Phase 1 vs Phase 2 Local DB

| Feature | Phase 1 (systems only) | Phase 2 (+ bodies) |
|---------|------------------------|-------------------|
| Distance search | ✅ | ✅ |
| Colonised filter | ✅ | ✅ |
| ELW/WW/body sliders | ❌ shows warning | ✅ |
| Bio/Geo toggles | ❌ shows warning | ✅ |
| Tidal lock toggle | ❌ shows warning | ✅ |
| Walkable body count | ❌ estimated | ✅ exact |
| Surface temperature in pill | ❌ — | ✅ |
| Rings info | ❌ — | ✅ |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Backend health + Spansh reachability |
| GET | `/api/health` | Simple health check |
| POST | `/api/systems/search` | Proxy Spansh systems/search |
| GET | `/api/system/{id64}` | Fetch + cache single system |
| POST | `/api/systems/batch` | Batch fetch up to 100 systems |
| GET | `/api/autocomplete?q=` | System name autocomplete |
| POST | `/local/search` | Local galaxy DB search (Phase 1+2) |
| GET | `/local/status` | Local DB stats (system/body count) |
| GET | `/api/watchlist` | List watched systems |
| POST | `/api/watchlist/{id64}` | Add system to watchlist |
| DELETE | `/api/watchlist/{id64}` | Remove from watchlist |
| GET | `/api/watchlist/changes` | Check for status changes |
| PATCH | `/api/watchlist/{id64}/alert` | Update alert config |
| GET | `/api/notes` | List all notes |
| GET | `/api/note/{id64}` | Get note for system |
| PUT | `/api/note/{id64}` | Upsert note |
| DELETE | `/api/note/{id64}` | Delete note |
| GET | `/api/cache/stats` | Cache analytics |
| POST | `/api/cache/clear` | Invalidate cache |
| POST | `/api/refresh` | Trigger background refresh |

---

## Bug Fixes Log (most recent first)

### v3.45 — Colony Planner deep enhancements + 10 UI improvements + bug fixes

- **[NEW] CP (Construction Point) Calculator** — enter planned T2/T3 port counts; exact Yellow/Green CP requirements with T1 facility count calculated per Mega Guide v2.3.0 formula (T2 costs 3+2(n−1)Y, T3 costs 6+6(n−1)G); warns when T2s are planned before T3s.
- **[NEW] Body Suitability Panel** — per-body-type colour bar (Ideal/Good/Warn/Avoid) for the chosen economy based on Mega Guide v2.3.0 body economy rules; hover each row for specific placement advice.
- **[NEW] Economy Pairing Guide** — shows Compatible / OK / Caution / Avoid secondary economies for the chosen primary per patch 4.2.0.1 cannibalization rules.
- **[NEW] Commodity Checklist** — key commodities (CMM Composite, Insulating Membranes, H.E. Suits, Steel, Battle Weapons etc.) shown as ✅/❌/⚠️ for the current system bodies and economy; explains orbital vs. ground exclusivity rules.
- **[NEW] Body Intake Upload** — upload the ED System Intake Calc CSV/ODS spreadsheet (or any CSV with Body Name, Type, Orbital Slots, Ground Slots) to generate colony plans directly from scouting notes without a Spansh system lookup.
- **[NEW] Phased Build Timeline** — Plan A reorganised into Phase 1 (T1 foundation), Phase 2 (T2 economy core), Phase 3 (T3 starport) with live CP balance per step.
- **[NEW] Plan Colony toast** — orange confirmation toast when a search result is sent to the Colony Planner tab.
- **[NEW] Extraction economy** — full build template with Asteroid Base + Refinery Hub pairing and body suitability data.
- **[FIX] _setOptEco body-suitability panels** — body suitability + eco pairing panels were in a dead `window._setOptEco` wrapper (silently skipped because original is a function declaration, not a `window.X` assignment); panels now update live on economy tile click via inline patching.
- **[FIX] runOptimizer commodity checklist** — checklist render was in a dead `window.runOptimizer` wrapper; inlined into `runOptimizer()` directly; checklist now renders after plan generation.
- **[FIX] buildPlanA phased timeline** — phased CP-annotated timeline was in a dead `window.buildPlanA` wrapper; inlined into `buildPlanA()` directly; timeline always renders in Plan A output.
- **[FIX] _annotatePlanStepsWithCP re-added** — was inadvertently removed from patch block but still referenced inline by `buildPlanA`; restored as `window._annotatePlanStepsWithCP` assignment.
- **[FIX] openInOptimizer double-patch consolidated** — two window wrappers (body preload + toast) merged into function body; single execution path with no double-firing risk.
- **[FIX] passesBodyFilters null safety** — `tog-bio`, `tog-geo`, `tog-ring`, `tog-terra` now use `?.checked` (was bare `.checked`; could throw if DOM not ready).
- **[FIX] Eco tile active state** — was using fragile `onclick.toString()` match; now uses `data-eco` attribute.
- **[FIX] _setOptEco event.currentTarget** — was null in inline onclick context; fixed by passing `this` as explicit `el` parameter.
- **[FIX] updateFilterBadge debounce** — slider drag was firing 100+ DOM reads/second; now debounced at 80ms.
- **[FIX] Distance delta badge** — `_captureRefForDelta` now also fires at `runSearch()` start so previous reference is correctly captured.
- **[FIX] Plan Colony pre-fill** — `openInOptimizer` now passes full body data from search results to `optSystem` (no extra Spansh fetch).
- **[FIX] favicon.ico** — added orange 16×16 favicon to eliminate browser 404 noise; added explicit `<link rel="icon">` in HTML head.

### v3.44 — Colony Planner overhaul + Score mini-bar redesign

- **[IMPR] Colony Planner full redesign** — two-column layout (controls left, plans right); system snapshot card shows star type, body count, landable/ringed/bio/geo counts, auto-detected economy with confidence, rating and colonisation status; collapsible material cost table per plan.
- **[NEW] Economy score grid** — 8 clickable tiles (Refinery, Agriculture, Industrial, High Tech, Military, Tourism, Extraction, Auto) with proportional fit-score bars auto-populated from Spansh data; best economy auto-selected.
- **[NEW] Cargo hold slider** — set your ship/FC cargo hold (100–25,000 t) and the cost table recalculates runs per commodity in real time.
- **[NEW] Economy Warnings panel** — pre-run warnings for geo contamination (Refinery), tidal-lock penalty (Agriculture), missing Ammonia World (High Tech), Military Hub prerequisites, and Tourism premium body absence.
- **[NEW] 8th economy: Extraction** — full build plan added for ring-focused Extraction colonies.
- **[NEW] Build Timeline** — each plan rendered as a stepped timeline with T1/T2/T3 badges, per-step contamination warnings and expandable commodity cost `<details>` panel.
- **[NEW] 🏗️ Plan Colony button** — every result card now has a button that opens the Colony Planner pre-loaded with the system's body data (no extra network call when Phase 2 data is already loaded).
- **[IMPR] Score mini-bar redesign** — segmented pill bar (5 colour-coded fill-height segments); single hover popover replaces the old per-column titles; popover shows all 6 score dimensions with labelled progress bars and exact values.

### v3.43 — 10 UI improvements

- **[NEW] Expand All / Collapse All** — single ⊞/⊟ button opens or closes all result cards simultaneously; state resets on new search.
- **[NEW] Body-type colour mini-bar** — proportional colour segments in card header (ELW=green, WW=blue, AMM=purple, HMC=orange, Metal-Rich=gold…); visible in compact density mode.
- **[IMPR] Active filter chips** — each active filter shown as a removable chip with ×; clicking the × removes that filter and re-searches immediately.
- **[IMPR] Autocomplete highlight** — matched portion of each system name suggestion bolded in orange for faster visual scanning.
- **[NEW] EDMC copy button** — 📋 EDMC button in each card's external-link bar copies the system name in EDMC-ready format with distinct toast feedback.
- **[NEW] Distance delta badge** — shows LY change vs previous search reference (green=closer, gold=further) next to each system's current distance.
- **[NEW] Filter panel collapse memory** — each sidebar panel's open/closed state saved in localStorage and restored on reload.
- **[NEW] Body mini-bar in compact view** — colour-coded body-type proportion bar appears in compact card headers alongside the score mini-bars.
- **[IMPR] Styled external link buttons** — Spansh, EDSM, and Inara displayed as icon pill buttons with branded hover colours; EDMC copy button added alongside.
- **[NEW] Radius density hint** — live label below the Max Distance slider estimates approximate system count in the search sphere, with colour coding (good/warn).

### v3.42 — 6 UI improvements

- **[IMPR] Score Breakdown tooltip enhanced** — per-component mini progress bars + body-driver
  chips (e.g. `3× ELW`, `2× Neutron`) now shown on hover over any rating badge.  Popover
  stays open while hovering over it (pointer-events now auto).
- **[IMPR] Economy badge coloured** — the economy pill in each result card header now uses the
  full `economy-tag` CSS class with per-economy colours (green=Agriculture, purple=HiTech,
  blue=Industrial, orange=Refinery, gold=Tourism, red=Military, pink=Extraction).
- **[IMPR] Economy preset sub-label dynamic** — after clicking a preset, the sub-text on the
  button updates to show exact slider ranges applied (e.g. "ELW ≥1 · WW ≥1 · Bio ≥2").
- **[NEW] Slider drag tooltip** — floating label shows current `min – max` range while
  dragging any body-type dual slider thumb (mouse and touch).
- **[NEW] ↺ Preset button** — appears alongside Reset Filters when an economy preset is
  active; re-applies the preset from scratch (useful after manual slider tweaks).
- **[NEW] Mobile sticky FAB** — 🔍 Search button fixed at bottom-right on screens ≤640px,
  shows the result count badge so you never have to scroll up to search again.

### v3.41 — Economy Presets

- **[NEW] Economy Preset buttons** — Added 8 one-click economy preset buttons in the
  Filters panel below the Quick Filter pills.  Clicking a preset (Agriculture, High Tech,
  Industrial, Refinery, Extraction, Military, Tourism, Terraforming) automatically sets
  the body-type sliders, toggles (Bio, Geo, Ring, Terra, No-Tidal) and the Economy
  dropdown to the optimal configuration for that colonisation economy type.
- Clicking the active preset again, or pressing **Reset Filters**, clears all preset
  settings.  An amber "active" indicator appears below the grid while a preset is active.
- Uses the ED colonisation economy guide (ELW + WW → Agriculture, Rocky + HMC → Refinery,
  Gas Giants + Rocky Ice → Industrial, etc.) as documented in the in-app Economy Guide table.

### v3.40 — Missing `is_tidal_lock` column graceful fallback

- **[BUG] 502 crash on any search with ELW/tidal filters when DB was imported before v3.28** —
  `local_search.py` hardcoded `is_tidal_lock` in the `SELECT` column list; if the column was
  absent (pre-migration DB) SQLite raised `no such column: is_tidal_lock`, which the API
  caught and returned as a 502.  Root cause: `migrate_v3_28.sql` adds the column but the
  Pi's DB predated that migration.
- **Fix** — `_probe_bodies_schema()` reads `PRAGMA table_info(bodies)` once at startup and
  caches the result.  The two body `SELECT` queries now use `_bodies_tidal_col()` which
  substitutes `0 AS is_tidal_lock` when the column is absent, so all searches succeed.
  Tidal-lock filter is silently disabled (treated as non-locked) until migration is applied.
- **Status API** — `local_db_status()` now returns `has_tidal_lock_col: bool` and refreshes
  the schema cache on every call so the flag flips to `true` immediately after migration
  without needing a container restart.
- **Frontend warning** — when `has_tidal_lock_col` is `false` a dismissible amber banner
  appears above the results panel with the exact migration command to run.
- **Migration command** (run once on the Pi — two options):
  ```bash
  # Option A: Pi's own sqlite3 directly on the bind-mounted file (works NOW, no rebuild)
  docker compose stop eddn delta
  sqlite3 ~/ed-finder-WORKING/data/galaxy.db < ~/ed-finder-WORKING/localdb/migrate_v3_28.sql
  docker compose start eddn delta
  docker compose restart api

  # Option B: Inside the container using sqlite3 .read (works after docker compose up --build)
  docker compose exec api sqlite3 /data/galaxy.db ".read /app/localdb/migrate_v3_28.sql"
  docker compose restart api
  ```
  > **Note:** `python:3.12-slim` does not include the `sqlite3` CLI binary. Option A uses the
  > Pi's own sqlite3 on the bind-mounted `./data/galaxy.db` file. The Dockerfile now installs
  > `sqlite3` via apt so Option B works after the next `docker compose up --build`.

### v3.39 — Re-filter pool shrinkage fix

- **[BUG] Re-filter shrinks result pool on each click** — root cause: `renderResultsProgressive`
  overwrote `window._lastResults.systems` with the filtered subset; the next refilter
  operated on that already-reduced set instead of the original API results.  Fixed by
  introducing `window._allResults` (set once per `runSearch` / `appendSearch` / `runDeepScan`,
  cleared on every new search) so `_refilterInPlace` always works from the full unfiltered set.
- **[BUG] Live filter badge showed wrong total after refilter** — `_doFilterLiveBadge` now
  also reads from `_allResults` so the X / Y counter stays accurate.
- **[BUG] Cache-age badge flipped to "🔴 live data" after refilter** — `_refilterInPlace` now
  preserves the original `cacheAge` value and passes it through to `renderResultsProgressive`.

### v3.38.1 — Configurable search-radius cap

- `MAX_SEARCH_RADIUS_LY` environment variable (default `200`) — override in `docker-compose.yml`
  per-host (Pi = 200, Hetzner CX32 = 500, CX52 = 750).
- Status endpoint returns `max_search_radius_ly` so the frontend reads the cap dynamically.
- Distance slider max and hint text update automatically to the configured cap.

### v3.38 — Local DB search radius cap (200 LY)

- Searches beyond 200 LY on a Raspberry Pi caused OOM / 502 crashes (340 LY ≈ 30 k grid cells × 67 M rows JOIN).
- Server-side cap added: requests over the limit are truncated with a warning.
- Frontend slider clamped to 200 LY when local DB is active; reverts to 500 LY for Spansh.
- SQLite busy-timeout set to 30 s to prevent silent hangs.

### v3.37 — Deep Scan hidden with local DB + SSE build fix

- **[UI] Deep Scan hidden when local DB active** — button auto-hides when local DB is available; shown when offline. Local DB has no 10k cap so Deep Scan is redundant.
- **[BUG] Deep Scan local path used distance sort** — now sends `sort_by: "rating"` and `min_rating` matching `runSearch` behaviour.
- **[SSE] 404 on `/api/sse/eddn`** — endpoint exists since v3.35.3 but requires `docker compose up --build -d` (not just restart) to pick up new image.

### v3.36 — EDDN daily updates complete + nightly delta status tracking

- **[EDDN] Full daily update pipeline confirmed operational:**
  - `eddn` container: 24/7 ZeroMQ listener writing real-time FSDJump/Location events to `galaxy.db`
  - `delta` container: downloads `galaxy_1day.json.gz` from Spansh at startup (catch-up) then every
    night at 02:00 UTC — keeps body counts, new systems, and economy data current
  - `api` container: pre-warms Sol/Colonia searches daily; watchlist checked every 6 h
- **[DELTA] `delta_last_run` written to `import_meta`** — `nightly_delta.py` now records the UTC
  timestamp after each successful run so the status panel (ℹ️ icon) can show when the last delta ran.
- **[UI] "Nightly delta" row in status panel** — shows last delta run time or
  `"never (runs nightly at 02:00 UTC)"` if not yet run.

### v3.35 — Server-side rating sort: highest-rated systems on page 1

**Root cause of the original bug:** All previous sort fixes only re-ordered results *after*
they arrived from the DB. But the DB returns systems sorted by **distance ascending**. So
page 1 contained the nearest systems (often low-rated), and high-rated systems farther away
only appeared on later pages — client-side re-sorting within a page couldn't fix cross-page ordering.

- **[CRITICAL] Server-side `rate_system()` in `local_search.py`** — Python function that
  exactly mirrors `rateSystem()` in `frontend/index.html` (same 6 components: star bonus,
  slots, body quality, compactness, signal quality, orbital safety → max 100 pts).
  The server now computes a rating for every matched system **before** pagination, then
  sorts by `(−rating, +distance)` so page 1 always contains the highest-rated systems
  regardless of where they are in the search radius.
- **`sort_by` parameter** — `local_db_search()` now accepts `sort_by: 'rating'` (default)
  or `'distance'` (legacy). Both `runSearch()` and `appendSearch()` send `sort_by: 'rating'`
  so every page, including Load More, comes back in rating order.
- **Server-side `min_rating` filter** — previously the note said "applied client-side only".
  Now applied in `local_db_search()` after ratings are computed, so the `total` count and
  pagination are accurate when a minimum rating is set.
- **Audit expanded to 58 checks** (6 new AA1–AA6 checks covering server-side rating logic).

### v3.34 — Guaranteed highest-score-first sort across all render paths

- **[SORT-GUARANTEE] `renderResults()` never sorted** — systems were rendered in API arrival order (distance ascending from the DB). The sort dropdown in this code path also defaulted to `Distance ↑` instead of `Rating ↓`. Fix: `renderResults()` now sorts by the saved sort preference (default `rating desc`) before building cards, and its dropdown correctly shows `Rating ↓` first.
- **[SORT-GUARANTEE] `appendSearch()` (Load More) appended in distance order** — new pages from the DB arrive sorted by distance. They were pushed onto the end of the results list and rendered as new cards at the bottom, completely ignoring rating order. Fix: after appending the new page, the entire combined list (`_lastResults.systems`) is re-sorted by the current sort preference, all existing cards are removed, and all cards are re-rendered in correct order.
- **Audit expanded to 56 checks** — added Z1–Z4 covering: renderResults sort, dropdown default, appendSearch re-sort, appendSearch card-clear.

### v3.33 — Galactic-core dense-region fix + error message overhaul

- **[BUG-DENSITY CRITICAL] fetchall() memory bomb for dense regions (Sgr A* search failure)** — `_spatial_search()` called `fetchall()` on the spatial grid query with no row limit. Near the galactic core a 500 LY search could match 500,000+ candidate systems, loading all of them into RAM and crashing the backend with a 502. **Fix:** replaced with streaming `fetchmany(10_000)` batches capped at `RAW_ROW_CAP = 500,000`. A `warning` field is returned in the API response and displayed as an orange banner: "Dense region — try ≤100 LY".
- **[BUG-MSG] Misleading 502 hint "slow Phase 2 SQLite query"** — This message appeared even when Phase 2 was fully imported, causing user confusion. **Fix:** updated hint to "search query crashed — likely dense star region or DB schema mismatch", pointing to `docker compose logs api` for the Python traceback.
- **[BUG-CATCH] `checkLocalDb()` catch left `_localDbHasBodies` stale** — only `_localDbAvailable` was reset on poll failure; `_localDbHasBodies` stayed `true`, causing Phase 2 banner logic to misbehave. **Fix:** both flags now reset in the catch block.
- **[BUG-EMPTY] Generic "No Systems Found" message** — replaced with context-aware tips explaining body filters needing Phase 2, toggle filters with no matches, uncolonised-only filter, or galactic-core density requiring a smaller radius.
- **Audit expanded to 51 checks** — added Y1–Y6 covering: fetchmany streaming, density warning propagation, frontend density banner, dual-flag catch reset, 502 hint text, context-aware empty state.

### v3.32 — Phase 2 search timeout root-cause fix + error-handling overhaul

- **[BUG-P1 CRITICAL] Per-system SQLite connection loop** — `local_search.py` opened a new `galaxy_conn()` for every candidate system when fetching bodies. A 500 LY search from Sgr A* with Phase 2 data generated 3,000–10,000 DB connections, taking 60–120s and always timing out. **Fix:** bodies are now fetched in a single `SELECT … WHERE system_id64 IN (…)` batch query (chunked at 900 IDs). Total DB connections reduced from N to 3.
- **[BUG-E3] TimeoutError not caught** — `AbortSignal.timeout()` throws `TimeoutError`, not `AbortError`. The catch block only handled `AbortError`, so timeouts fell through to the generic Docker error hint. **Fix:** catch block now handles both.
- **[BUG-E1] Misleading "docker compose ps" error message** — All search failures showed a Docker diagnostic hint regardless of the actual cause. **Fix:** error messages differentiated by type (network vs 502 vs timeout vs generic).
- **[BUG-STATUS] Status dot stayed green during search failures** — **Fix:** `_triggerApiPoll()` triggers an immediate re-check 1.5s after any search error.
- **[BUG-B2] Rating slider triggered full new API search** — **Fix:** `_attachIncrementalSearch` now calls `_refilterInPlace()` (no API call, 200ms debounce) instead of `runSearch()`.
- **[TIMEOUT] spanshPost timeout too short for Phase 2** — **Fix:** `/local/search` calls get 90s; Spansh proxy calls keep 30s, combined with `AbortSignal.any()`.
- **Audit script** — 6 new checks X1–X5. Total: **45 checks**.

### v3.31 — Demo fallback removal + enrichment distance preservation + Sol search fix

- **[BUG-DEMO]** Demo systems shown on API error — removed from error path entirely.
- **[BUG-DIST-ENRICH]** Enrichment spread overwrote sys.distance — all spreads now explicitly preserve `distance: sys.distance`.
- **[BUG-SOL]** Deep Scan blocked for Sol (x=0) — guard changed to `=== undefined` check.
- **Audit script** — adds U1, U1b, V1, V2, W1. Total: **39 checks**.

### v3.30 — Distance slider auto-search fix + Python walkable tidal fix

### v3.29 — ELW/body slider critical fix
- **[CRITICAL] Body-type sliders (ELW/WW/all) silently ignored** — `passesBodyFilters()` had `skipBodyFilters = _localDbAvailable && !_localDbHasBodies && bodies.length === 0` which bypassed ALL body slider filters when Phase 2 not imported. Searching for "1 ELW" returned systems with zero ELWs. **Fix:** inverted logic — if body sliders are set and bodies[] is empty, reject the system. Added orange warning banner.

### v3.28 — Full tidal lock propagation fix
- Added `is_tidal_lock` column to bodies table schema
- `_body_row` now extracts `rotationalPeriodTidallyLocked` from Spansh data
- `local_search.py` selects and normalizes `is_tidal_lock → is_rotational_period_tidally_locked`
- `surface_temp` renamed to `surface_temperature` in SELECT (body pill now shows temperature)
- `countBodyTypes` walkable now checks `!b.is_rotational_period_tidally_locked`
- `b.landable` → `b.is_landable` in `suggestEconomy` (tidal Agriculture penalty now triggers)
- Ring display in body pill fixed (was showing `[object Object]`)
- Migration: `sqlite3 /data/galaxy.db < localdb/migrate_v3_28.sql`

### Audit commit `a060e22` — Full HTML/JS/backend audit
- **[CRITICAL] resetFilters()** orphaned code — button did nothing. Fixed.
- **applySearchParams** referenced non-existent element `min-rating-val`. Fixed.
- **Route planner bestCandidate** used broken `is_colonised` field. Fixed with heuristic.
- **appendSearch Load More** button never re-enabled. Fixed with `finally`.
- **_refilterInPlace** double-filtered. Simplified.
- **backend X-Cache-Age** always 0. Fixed.

---

## Deployment

### Prerequisites
- Docker + Docker Compose
- Linux host (Raspberry Pi 4+ recommended, or any AMD64/ARM64 server)

### Quick Start
```bash
cd ~/ed-finder-WORKING
docker compose up -d
```

### Update after git pull
```bash
cd ~/ed-finder-WORKING
git fetch origin && git reset --hard origin/main
docker compose restart web   # frontend-only change
# OR
docker compose restart       # backend + frontend
```

### Schema migration (first time after v3.28, Phase 2 DB only)
```bash
sqlite3 /data/galaxy.db < localdb/migrate_v3_28.sql
```

### Run audit
```bash
python3 localdb/audit.py --verbose    # full report with PASS items
python3 localdb/audit.py              # summary only
python3 localdb/audit.py --fix-report # exits 1 if bugs found (CI)
# v3.32: 45 checks — adds X1–X5 covering timeout handling, batch body fetch, rating slider wiring
```

---

## Project Structure

```
ed-finder/
├── backend/
│   └── main.py              # FastAPI backend
├── frontend/
│   └── index.html           # Full SPA
├── localdb/
│   ├── local_search.py      # Local galaxy DB search module
│   ├── import_systems.py    # Galaxy/delta importer
│   ├── audit.py             # Permanent exhaustive audit (39 checks)
│   ├── migrate_v3_28.sql    # Phase 2 schema migration
│   └── nightly_delta.py     # Nightly delta update runner
├── docker-compose.yml
├── nginx.conf
└── README.md
```

---

## Scoring System (0–100)

| Dimension | Max | Description |
|-----------|-----|-------------|
| Slots | 25 | Landable + orbital body count |
| Body Quality | 25 | ELW (+10), Water world (+8), exotic stars (+6), Ammonia (+5) etc. |
| Compactness | 20 | Max planet distance: ≤500 ls = 20pts … >250k ls = 0pts |
| Signal Quality | 15 | Bio-only, Geo-only, Both signals |
| Orbital Safety | 10 | Close binary/parent pairs penalty |
| Star Bonus | 5 | G/K (+5), F/M (+4), A/B (+3) etc. |

---

**Happy exploring, Commander! o7**

### Finder Tab
- **Search** — distance-filtered system search via Spansh API
- **Deep Scan** — distance-band slicing (up to 10 bands × 10k = 100k systems scanned)
- **Uncolonised filter** — multi-signal heuristic (population, factions, is_colonised, is_being_colonised)
- **Body-type sliders** — dual min/max range for ELW, Water worlds, Rocky, Icy, Ammonia, etc.
- **Rating score range** — dual min/max slider (0–100)
- **Economy filter** — AI-inferred economy type (Refinery, Agriculture, Industrial, High Tech, Military, Tourism)
- **Slot filters** — min landable bodies, min signal count
- **Toggle filters** — Bio, Geo, Ring, Terraformable, Volcanism, No Tidal Lock, Zero Population
- **Sort** — Rating ↓ (default), Distance ↑, Economy A-Z, Body Count ↓, Population ↓
- **Export** — CSV and JSON download of current results
- **Re-filter** — re-apply filters to already-loaded results without a new API call
- **Share URL** — shareable link with all filter state encoded in hash
- **Search history** — last 20 searches with restore and preset save/load

### System Cards
- Rating score (0–100) with colour-coded badge
- Economy suggestion with confidence indicator
- Population potential estimate
- Colonised/Free status pill using full heuristic
- Body pills with detail popovers (gravity, signals, rings, tidal lock)
- Warning tags (tidal lock Agriculture risk, volcanism, ELW/Water worlds, exotic stars)
- Score breakdown mini-bar (Slots, Body Quality, Compactness, Signal Quality, Orbital Safety)
- Pin to Pinned tab
- Add to Compare (up to 6 systems side-by-side radar chart)
- Personal notes (stored in backend SQLite)
- Add to Watchlist
- Open in Optimizer

### Optimizer Tab
- Auto-suggest best economy based on body composition
- Plan A (low disruption), Plan B (moderate), Plan C (maximum output)
- Step-by-step build order with cargo cost breakdown
- Contamination warnings for conflicting structures

### Route Planner Tab
- Multi-hop waypoint route builder
- Per-hop system search within radius
- Best Pick suggestion per hop (uses full colonisation heuristic)
- "Load into Finder" for any hop
- Save / load route to localStorage

### Watchlist Tab
- Track systems for colonisation status and population changes
- Per-system alert config (notify on colonised, notify when pop exceeds threshold)
- Background poll every 5 minutes with browser notifications
- Change log with diff display

### Galactic Map Tab
- Canvas-based 2D projection (XZ/XY/YZ planes)
- Zoom (mouse wheel), pan (drag), double-click to reset
- Colour modes: rating, economy, distance
- Pinned and watchlist system overlays
- PNG export

### Compare Tab
- Side-by-side table with winner highlighting
- Radar chart (score dimensions)
- CSV export

### Guide / Cache Analytics
- API connection status with latency
- Cache hit/miss counts
- Cache clear and manual refresh

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Backend health + Spansh reachability |
| GET | `/api/health` | Simple health check |
| POST | `/api/systems/search` | Proxy Spansh systems/search |
| GET | `/api/system/{id64}` | Fetch + cache single system |
| POST | `/api/systems/batch` | Batch fetch up to 100 systems |
| GET | `/api/autocomplete?q=` | System name autocomplete |
| GET | `/api/watchlist` | List watched systems |
| POST | `/api/watchlist/{id64}` | Add system to watchlist |
| DELETE | `/api/watchlist/{id64}` | Remove from watchlist |
| GET | `/api/watchlist/changes` | Check for status changes |
| PATCH | `/api/watchlist/{id64}/alert` | Update alert config |
| GET | `/api/notes` | List all notes |
| GET | `/api/note/{id64}` | Get note for system |
| PUT | `/api/note/{id64}` | Upsert note |
| DELETE | `/api/note/{id64}` | Delete note |
| GET | `/api/cache/stats` | Cache analytics |
| POST | `/api/cache/clear` | Invalidate cache |
| POST | `/api/refresh` | Trigger background refresh |

---

## Bug Fixes Log (most recent first)

### Audit commit `a060e22` — Full HTML/JS/backend audit
- **[CRITICAL] resetFilters()** was orphaned code running at parse time — button did nothing on click. Fixed by wrapping in proper function declaration.
- **applySearchParams** referenced non-existent element `min-rating-val` — caused silent TypeError on preset/URL restore. Fixed with null guard.
- **Route planner bestCandidate** used `is_colonised` (broken Spansh field) — all legacy systems were incorrectly excluded. Fixed with full multi-signal heuristic.
- **appendSearch Load More** button never re-enabled on success path. Fixed with `finally` block.
- **_refilterInPlace / _doFilterLiveBadge** double-filtered (passesBodyFilters already checks rating + economy). Simplified to single pass.
- **showTab()** called `.style` on potentially null element for invalid tab IDs. Added null guard.
- **backend X-Cache-Age** always returned `0` even for cached responses. Now returns real age so "📦 cached Xh Ym ago" banner works correctly.

### Previous notable fixes
- Colonised filter removed from Spansh API call (only works for new colonies) — rely on client-side heuristic
- `buildCardBody` received `sysIsInhabited` as parameter (was ReferenceError causing cards not to render)
- ELW slider max set to 4
- Toggle knob symmetrical margins (left:30px ON position)
- Results now default-sort by Rating descending
- Deep Scan feature added (distance-band slicing)
- Rating Score Range dual slider added

---

## Deployment

### Prerequisites
- Docker + Docker Compose
- Linux host (Raspberry Pi 4+ recommended, or any AMD64/ARM64 server)

### Quick Start
```bash
cd ~/ed-finder-FINAL-COMPLETE
docker compose up -d
```

### Access
- **Local network:** `http://<your-server-ip>`
- **Custom domain:** See below

### Custom Domain (Cloudflare)
See *Custom Domain Setup* section at the bottom of this README.

### Update after git pull
```bash
cd ~/ed-finder-FINAL-COMPLETE
git pull
docker compose restart web   # frontend-only change
# OR
docker compose restart       # backend + frontend
```

---

## Project Structure

```
ed-finder-FINAL-COMPLETE/
├── backend/
│   ├── main.py              # FastAPI backend (1,240 lines)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html           # Full SPA (7,507 lines, 110 functions)
│   └── 50x.html
├── docker-compose.yml
├── nginx.conf
├── .env
└── README.md
```

---

## Scoring System (0–100)

| Dimension | Max | Description |
|-----------|-----|-------------|
| Slots | 25 | Landable + orbital body count |
| Body Quality | 25 | ELW (+10), Water world (+8), exotic stars (+6), Ammonia (+5) etc. |
| Compactness | 20 | Max planet distance: ≤500 ls = 20pts … >250k ls = 0pts |
| Signal Quality | 15 | Bio-only, Geo-only, Both, Pure Rocky bodies |
| Orbital Safety | 15 | Close binary/parent pairs penalty |

---

## Custom Domain Setup (Cloudflare)
See the section below for step-by-step instructions once you are ready to connect your domain.

---

**Happy exploring, Commander! o7**
