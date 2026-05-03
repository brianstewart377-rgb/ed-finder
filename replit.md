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

## Deployment
Configured as `autoscale` target. Run command: `python3 backend/main.py`
