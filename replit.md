# ED Finder — Replit Setup

## Overview
Elite Dangerous colonisation system finder. Searches star system data (sourced from Spansh) by economy type, body types, and distance from a reference system.

## Stack
- **Frontend**: Static HTML/CSS/JS (`frontend/`) served by FastAPI
- **Backend**: FastAPI (Python 3.12) with asyncpg — `backend/main.py`
- **Database**: Replit PostgreSQL (auto-provisioned, env `DATABASE_URL`)
- **Cache**: Redis (optional — app degrades gracefully without it)

## Architecture
FastAPI serves both the API (`/api/*`) and the static frontend on a single port (5000). The frontend uses relative `/api/` paths, so no separate proxy is needed.

## Running
- **Workflow**: `Start application` → `cd backend && python3 main.py`
- **Port**: 5000 (frontend + API)

## Database
- Schema: `sql/001_schema.sql` (tables, enums)
- Indexes: `sql/002_indexes.sql`
- Functions/Views: `sql/003_functions.sql`
- Score history: `sql/006_score_history.sql`

The database ships empty — star system data is imported separately via the import pipeline scripts in `backend/` (not used in Replit; data comes from Spansh API live).

## Key Files
- `backend/main.py` — FastAPI app (API + static serving)
- `backend/local_search.py` — Local PostgreSQL search module
- `frontend/index.html` — Single-page app
- `frontend/app.js` — Frontend application logic
- `sql/` — Database schema and functions

## Known Architecture Notes
- **Two CSS variable systems**: `index.html` uses `--orange`, `--bg`, `--text-dim`; `style.css` uses `--accent`, `--bg-panel`, `--bg-card`. Intentional split — do not merge without a full audit.
- **Two search paths**: `local_search.py` (primary, runs against local DB) + inline fallback in `main.py` (used if local_search fails or is unavailable). Fallback lacks some filters local_search supports.
- **Redis optional**: Redis unavailable in Replit — app degrades gracefully to no-cache mode.
- **DB empty in Replit**: Star system data not present; structural/API testing only.
- **No /api/refresh endpoint**: `triggerRefresh()` polls `/api/status` instead and calls `checkApiConnection()` to update the status bar.
- **backdrop-filter critical rule**: NEVER add `backdrop-filter` to `.tab-content.full-width` — it creates a CSS stacking context that traps `position:fixed` modals/dropdowns inside those tabs. Only safe on `#header`, `#status-bar`, `#tabs`, `#sidebar`, `#content` (which is inside the System Finder tab only).
- **Glassmorphism theme** (v3.31): All major surfaces use `rgba(6,8,18,0.70–0.80)` for a unified dark-glass appearance. Header is darkest (0.80), full-width tab pages lightest (0.70).
- **30 Improvements (v3.32)**: U1 eco left border, U2 body count chip, U3 score fill bar, U4 finder tab badge, U6 focus glow, U7 smooth collapse, U8 card hover lift, X1 copy route names, X2 page jump, X3 dblclick briefing, X4 WL inline note, X5 eco quick-picks, X6 auto-search toggle, X7 find-on-map btn, X9 unified copy toast, M1 route overlay, M2 scale bar, M4 grid toggle, M5 shift+click ref, M6 WL-only mode, M8 map search, M9 3D labels, M10 distance ruler.

## Deployment
Configured as `autoscale` target. Run command: `python3 backend/main.py`
