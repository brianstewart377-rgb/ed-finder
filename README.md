# ED:Finder — Self-Hosted Colony Finder

A self-hosted Elite Dangerous system finder for locating uncolonised candidates.
Runs as two Docker containers (FastAPI backend + Nginx frontend) on any Linux host
including Raspberry Pi.

---

## Current Status

| Component | Status |
|-----------|--------|
| Frontend  | ✅ 7,507 lines, 110 functions |
| Backend   | ✅ 1,240 lines, all endpoints functional |
| Git       | ✅ `main` branch — latest commit: audit fixes |

---

## Features Implemented

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
