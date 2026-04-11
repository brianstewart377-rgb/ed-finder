# ED:Finder — Self-Hosted Colony Finder

A self-hosted Elite Dangerous system finder for locating uncolonised candidates.
Runs as two Docker containers (FastAPI backend + Nginx frontend) on any Linux host
including Raspberry Pi.

---

## Current Status

| Component | Status |
|-----------|--------|
| Frontend  | ✅ Latest — v3.30 all 34 audit checks pass |
| Backend   | ✅ All endpoints functional |
| Local DB  | ✅ Phase 1 (systems) + Phase 2 (bodies) supported |
| Audit     | ✅ `python3 localdb/audit.py` — 34 checks, 0 bugs |
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

### v3.30 — Distance slider auto-search fix + Python walkable tidal fix
- **[BUG-DIST] Distance slider replaced result cards on release** — `_attachIncrementalSearch` was wiring `dist-slider` and `min-dist-slider` to `_debouncedSearch` via the `change` event. When you released the slider after results were loaded, a full new search fired for the new distance range, silently replacing all result cards with a different set of systems. Users experienced this as "the distances shown on my results changed". **Fix:** distance sliders removed from `_attachIncrementalSearch` entirely. Users must press Search to apply a new distance. A `↵ press Search` hint appears on the label when you move the slider.
- **[BUG-WALK-PY] Python walkable count ignored tidal lock** — `_count_body_types` in `local_search.py` counted walkable bodies as `landable + no atmosphere` but did not check `is_tidal_lock`. The JS version (fixed in v3.28) correctly excludes tidally locked bodies. A system with tidally locked airless landable planets would have an inflated walkable count in Phase 2 DB searches. **Fix:** added `and not is_tidal` guard matching JS exactly.
- **Audit script** — two new checks added: S1 (Python walkable tidal check), T1 (dist-slider HTML onchange does not call runSearch). Total: 34 checks.

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
# v3.31: 39 checks covering distance, demo mode, enrichment, body filters, schema
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
