# ED Finder — Hetzner PostgreSQL Stack
## Complete setup and import guide

---

## Server spec
- **Hetzner AX41-SSD**: Intel i7-8700 (6C/12T) · 128 GB RAM · 3 × 1 TB NVMe (RAID-5 ~1.8 TB usable)
- **OS**: Ubuntu 24.04 LTS
- **Domain**: ed-finder.app (Cloudflare proxied — A/AAAA records point to Hetzner IP)

---

## Stack
| Service | Image / Tooling | Purpose |
|---|---|---|
| PostgreSQL 16 | `postgres:16-alpine` | Main database (186M+ systems) |
| pgBouncer | `edoburu/pgbouncer:v1.23.1-p3` | Connection pooling (transaction mode) |
| Redis 7 | `redis:7-alpine` | API response cache + EDDN pub/sub bridge + rate-limit store |
| FastAPI | `python:3.12-slim` · Pydantic 2.9 | API backend (`apps/api/`) — strict request/response models |
| EDDN Listener | `python:3.12-slim` | Live game data ingestion (`apps/eddn/`) |
| Importer | `python:3.12-slim` | Spansh dump + post-import builders (`apps/importer/`) |
| Frontend v2 | Vite 6 + React 19 + TS 5 + Tailwind 3 | SPA (`frontend-v2/`) — TanStack Query, Zustand, codegen-typed wire contract |
| Nginx | `nginx:alpine` | SSL + static `frontend-v2/dist/` serving + `/api/*` proxy |

**Type contract**: the frontend's `src/types/api.gen.ts` is auto-generated from the FastAPI `/openapi.json` via `openapi-typescript`. CI fails any push that drifts the checked-in baseline from what the running API actually emits — so backend response shapes and frontend types never silently diverge.

---

## Import script versions (current)

| Script | Version | Key fix |
|---|---|---|
| `import_spansh.py` | 3.0 (v2.6 auto-finalize) | COPY-via-temp-table + galaxy region + structured error logging |
| `build_grid.py` | 2.4 | Disable RI triggers + ctid-range batching + auto index repair |
| `build_ratings.py` | 2.5 | CPU-protection + index-only-scan friendly dirty-system query |
| `build_clusters.py` | 2.3 | Stabilized hybrid clustering + API-trigger support |
| `nightly_update.sh` | 1.2 | Added Sunday full cluster rebuild |

## API / frontend versions

| Component | Version | Notes |
|---|---|---|
| `apps/api/src/main.py` | 3.0.1-hetzner | Admin-token auth, CORS lockdown, path-traversal fix, Redis-backed rate limiter, Redis pub/sub SSE bridge, asyncpg `statement_cache_size=0` for pgBouncer. **Audit Phase 7 follow-up (PR #5)**: every v2-frontend-consumed endpoint declares a strict `response_model`; request models use real Pydantic sub-types (`RangeFilter`, `BodyFilters`, `CoordsModel`, `RerankWeights`, `RerankResponse`) instead of `Optional[dict]`, so the OpenAPI schema is stable across Pydantic versions and `frontend-v2/src/types/api.gen.ts` carries real per-row shapes. |
| `apps/eddn/src/eddn_listener.py` | 1.2 | Publishes events to Redis `eddn_events` channel |
| `frontend-v2/` | (Vite + React 19) | The single shipping frontend. State on `useState` + Zustand stores (`pinnedStore`, `syncKeyStore`); shared server cache on TanStack Query (`useWatchlist`). Wire types in `src/types/api.ts` re-export from the codegenned `api.gen.ts` — public type names (`SystemResult`, `SearchResponse`, `SystemDetail`, `AppStatus`, `CacheStats`, `RerankRequest`, …) preserved so consumers don't need rewriting when the backend emits a new field. |

> **Legacy `frontend/`** (vanilla JS, the original `app.js`) was removed in the audit refactor (PR #3) — `frontend-v2/` is the only frontend in the repo.

---

## Security checklist (before going live)

Copy `env.example` to `.env` on the Hetzner host and set these entries
(in addition to the existing `POSTGRES_PASSWORD`):

```ini
# Required — generate with `openssl rand -hex 32`. Admin endpoints
# (/api/admin/*, /api/cache/clear) are DISABLED unless this is set.
ADMIN_TOKEN=...

# Required unless you want the browser to block your frontend's API calls.
# Comma-separated list of origins allowed to call the API.
CORS_ORIGINS=https://ed-finder.app,https://www.ed-finder.app

# Optional — set to "true" only when debugging locally; leaks SQL/internal
# error text in HTTP responses.
EXPOSE_ERROR_DETAIL=false
```

Trigger a manual cluster rebuild from the Hetzner host:

```bash
curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" \
     http://127.0.0.1/api/admin/rebuild-clusters
```

Admin endpoints are additionally firewalled in `config/nginx.conf` (allow
`127.0.0.1` only), so they cannot be reached from the public internet even
if `ADMIN_TOKEN` leaks.

---

## Bug history — import scripts

### The 41M stall (root cause, definitively identified)

The `systems` table has 8 child tables with `FOREIGN KEY ... REFERENCES systems(id64)`:
`bodies`, `stations`, `attractions`, `factions_presence`, `ratings`, `cluster_summary`, `watchlist`, `system_notes`.

PostgreSQL automatically creates **2 referential-integrity (RI) triggers per FK** — one on the child table and one on the parent. This gives:

```
8 FKs × 2 RI triggers = 16 RI triggers
+ 1 custom trigger (trg_system_dirty)
= 17 triggers total on systems
```

These RI triggers fire on **every** `UPDATE systems` — even when only `grid_cell_id`, `rating_dirty`, or `cluster_dirty` is being changed, none of which are FK columns. For the first ~41M rows (colonised systems from `galaxy_populated.json.gz`), each RI trigger fires an index lookup on every child table to verify no orphaned rows. The remaining 145M rows are uncolonised (no children) so the cost is lower — but the damage is done in the first pass.

**Fix (all three scripts):** `SET session_replication_role = replica` at the start of any bulk `UPDATE systems`. This disables non-ALWAYS triggers for the current session only, reverts automatically on disconnect, and is safe because we never modify `id64` (the FK column).

---

### build_grid.py changelog

| Version | Fix |
|---|---|
| v1.0 | Initial version |
| v2.0 | Fixed EXISTS correlated subquery (22-min hang); removed advisory lock that never released on crash; bypassed pgBouncer (transaction-pool breaks long connections); removed ALTER TABLE autovacuum deadlock; fixed write_conn not rolled back on reconnect; fixed partial Stage 2 cells accepted as complete; documented BIGINT overflow in cell_id formula |
| v2.1 | Fixed stale `total_systems` cache causing Stage 3 to be skipped entirely |
| v2.2 | Fixed single-UPDATE stalling at 41M rows (WAL/checkpoint pressure); replaced with ctid-range page batching (10,000 pages ≈ 80 MB per commit, fully resumable) |
| v2.3 | **Root-cause fix** — disabled RI triggers (`SET session_replication_role = replica`) during Stage 3; added `--no-disable-triggers` flag to argparse (was referenced in docs but missing); corrected startup banner version |
| v2.4 | **Auto-fix missing index** — Script now detects if `idx_sys_grid_null` is missing and attempts to create it automatically to ensure instant resume. |

### build_ratings.py changelog

| Version | Fix |
|---|---|
| v2.0 | Fixed server-side cursor truncation at ~74M rows; batch body fetch (one query per chunk instead of per system); dynamic work dispatch; corrected score_economy() math |
| v2.1 | Added startup/stage banners, safe log path, per-worker heartbeat |
| v2.2 | Disabled RI triggers on `UPDATE systems SET rating_dirty = FALSE` — eliminated ~252M spurious trigger evaluations per run; fixed startup banner (was still saying v2.1); fixed "Next step" footer (incorrectly said `build_grid.py` — should be `build_clusters.py`) |
| v2.4 | **CPU Protection** — Added `--max-workers` to prevent 1000%+ CPU usage on high-core servers; optimized result draining to prevent main-loop stalls. |
| v2.5 | **Query Optimization** — Rewrote dirty-system query to be index-only scan friendly; fixed missing completion banner bug. |

### build_clusters.py changelog

| Version | Fix |
|---|---|
| v1.0 | Initial version |
| v1.1 | Log directory auto-creation; resume-safe mode; grid-aware queries; fetchmany streaming |
| v1.2 | Added startup/stage banners, per-worker heartbeat, safe log path, spatial-grid-missing warning |
| v1.3 | Disabled RI triggers on `UPDATE systems SET cluster_dirty = FALSE` — eliminated ~2.5B spurious trigger evaluations across 73M anchors; fixed startup banner (was still saying v1.2); fixed worker_id collision (was `chunks % workers`, causing multiple chunks to share the same ID and produce confusing logs) |
| v1.4 | Standardized progress banners and fixed RI trigger disable logic on reconnect. |
| v1.6 | **Smallint Fix** — Widened all cluster count columns to `INTEGER` to prevent crashes on high-density clusters. |
| v2.2 | **Stabilized Hybrid Logic** — Reverted to memory-safe anchor loop with high-speed spatial filtering. Added `--dirty-only` incremental mode. Set default quality to Score 65+. |
| v2.3 | **Automation Support** — Added API-trigger support for manual rebuilds and Sunday full-rebuild scheduling in `nightly_update.sh`. |

#### Understanding Score Levels
When running the cluster builder, the `--min-score` (default 65) determines what counts as a "viable" neighbor for a colonist:
*   **Score 40-50**: Basic viability. Includes systems with metal-rich planets or basic gas giants. Very common.
*   **Score 60-70**: High quality. Usually requires at least one **Terraformable** planet or high biological signal density.
*   **Score 80+**: "Jackpot" systems. Earth-like Worlds (ELWs), multiple Terraformables, or Neutron stars.

Higher scores lead to fewer, but much higher quality, suggested "Empire" locations.

### 002_indexes.sql changelog

| Addition | Reason |
|---|---|
| `idx_sys_grid_null` — partial index on `systems(id64) WHERE grid_cell_id IS NULL` | Allows `build_grid.py` v2.2+ to find the resume page in <1s instead of a 74 GB sequential scan (~5 min) on restart |
| `idx_sys_rating_dirty` — optimized partial index | Updated in v2.5 to index `id64` directly, allowing instant "dirty" system lookups via Index-Only Scan. |
| **002_indexes_optimized.sql** | New safe indexing script for 128GB RAM servers; limits parallel workers and memory to prevent SSH/system crashes (OOM). |

---

## Repository layout

```
ed-finder/
├── apps/                    # Per-service source — each builds its own image
│   ├── api/                 # FastAPI HTTP service
│   │   ├── Dockerfile
│   │   ├── requirements.txt # API-only deps (no importer libs in this image)
│   │   └── src/
│   │       ├── main.py             # FastAPI composition root
│   │       ├── config.py
│   │       ├── deps.py / state.py
│   │       ├── helpers.py / models.py
│   │       ├── search_economies.py # Single-source-of-truth column maps
│   │       ├── local_search.py     # Search SQL builder
│   │       ├── share_router.py     # OG image renderer
│   │       └── routers/            # FastAPI routers (admin, events, map,
│   │                               #   meta, notes, profile, ratings,
│   │                               #   search, systems, watchlist)
│   ├── eddn/                # EDDN ZMQ listener
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── eddn_listener.py
│   │       └── eddn_simulator.py
│   └── importer/            # Spansh dump + post-import builders
│       ├── Dockerfile
│       ├── requirements.txt
│       └── src/
│           ├── import_spansh.py
│           ├── build_grid.py / build_ratings.py / build_clusters.py
│           ├── progress.py
│           ├── region_map.py            # Loader for…
│           └── data/region_map.json     # …42-region RLE galaxy map
├── config/
│   ├── nginx.conf           # Nginx SSL + proxy config
│   ├── security-headers.conf
│   ├── prometheus.yml
│   └── grafana/
├── frontend-v2/             # Vite + React + TypeScript SPA (the only frontend)
│   ├── src/                 # Feature-folders: search/, map/, system-detail/,
│   │                        # watchlist/, pinned/, optimizer/, colony/, …
│   ├── src/store/           # Zustand stores (pinnedStore, syncKeyStore)
│   ├── src/lib/api.ts       # Single API client; uses types from src/types/api.ts
│   ├── src/types/api.ts     # Public type surface (re-exports api.gen.ts)
│   ├── src/types/api.gen.ts # ↑ AUTO-GENERATED — do not hand-edit. Run
│   │                        # `yarn types:gen` after any models.py change.
│   ├── e2e/                 # Playwright smoke spec — runs on every push
│   ├── playwright.config.ts # Boots vite preview on :4173, proxies /api → :8002
│   ├── index.html           # App shell
│   ├── package.json         # Yarn deps (React 19, Tailwind 3, Vite 6,
│   │                        # @tanstack/react-query, zustand,
│   │                        # @playwright/test, openapi-typescript)
│   └── vite.config.ts       # Build config — emits dist/ for /var/www/v2/
├── scripts/
│   ├── nightly_update.sh    # Nightly delta-import cron script
│   ├── run_import.sh        # Import runner wrapper
│   ├── sync_password.sh     # Password sync utility
│   ├── cleanup.sh           # Docker cleanup utility
│   ├── migrate_postgis.sh   # PostGIS migration script
│   └── watch_grid.sh        # Live progress watcher for build_grid.py
├── sql/
│   ├── 001_schema.sql       # Table definitions (auto-run on first postgres start)
│   ├── 002_indexes.sql      # All indexes including idx_sys_grid_null
│   ├── 003_functions.sql    # PL/pgSQL helpers (grid lookup, distance, etc.)
│   ├── 004_ratings_v31.sql  # v3.1 rating columns (terraforming_potential,
│   │                        # body_diversity, confidence, rationale)
│   ├── 005_map_indexes.sql  # Indexes for /api/map/{regions,heatmap,timeline}
│   ├── 006_score_history.sql
│   ├── 007_profile_sync.sql # JSONB pastebin slot for cross-device sync
│   ├── 008_body_filter_aggregates.sql
│   ├── 009_map_materialised_views.sql  # mv_map_regions / mv_map_heatmap /
│   │                                   # mv_map_timeline + refresh_map_mviews()
│   ├── 010_sync_key_scoping.sql        # Per-CMDR scoping of watchlist/notes
│   └── seed_preview.sql     # 40-system seed used by CI integration tests
├── tests/
│   ├── test_smoke.py        # Pure-Python unit smoke (no DB) — region_map,
│   │                        # economy column maps, helpers
│   └── integration/         # API + DB integration tests (real PG + Redis)
│       ├── conftest.py      # Boots an httpx.AsyncClient against main.app
│       ├── test_infrastructure.py
│       ├── test_phase2_search_no_fallback.py   # §C5 contract — no inline fallback
│       ├── test_phase3_sync_key_scoping.py     # §H1 contract — watchlist scope
│       └── test_phase5_map_materialised_views.py
├── .github/
│   └── workflows/ci.yml     # 6-job CI: backend smoke, integration (PG+Redis),
│                            # v2 build, nginx config syntax, OpenAPI types drift
│                            # check, Frontend v2 E2E (Playwright)
├── docker-compose.yml       # Full service stack
├── pyproject.toml           # Project metadata (real deps live in apps/*/requirements.txt)
├── setup.sh                 # First-time server setup script
└── README.md                # This file
```

> **Single directory deployment:** The repo is cloned directly to `/opt/ed-finder`.
> All services run from that one directory — there is no separate `/opt/ed-finder-src`.
> All import scripts live **only** in `apps/importer/src/`. Always use `scripts/run_import.sh`
> to run them — never use raw `docker run`. The wrapper handles network, DNS,
> password verification, and volume mounts correctly.

---

## CI / quality gates (`.github/workflows/ci.yml`)

Every push and PR runs **6 parallel jobs** on GitHub-hosted runners:

| Job | What it checks | Typical wall-time |
|---|---|---|
| **Backend smoke tests + compose validate** | `python -m unittest tests/test_smoke.py` (56 pure-Python tests) and `docker compose config` | ~25 s |
| **Backend integration (PG+Redis)** | Spawns `postgres:16-alpine` + `redis:7-alpine` service containers, applies `sql/001…010` + `seed_preview.sql`, runs `pytest tests/integration/` (44 tests covering Phase-2/3/5/6 contracts) | ~50 s |
| **Frontend v2 build** | `yarn install` + `yarn typecheck` + `yarn test --run` (28 vitest) + `yarn build` | ~45 s |
| **Nginx config syntax** | `nginx -t` against `config/nginx.conf` | ~20 s |
| **OpenAPI types drift check** | Boots the API, regenerates `frontend-v2/src/types/api.gen.ts`, fails if it drifts from the checked-in baseline | ~55 s |
| **Frontend v2 E2E (Playwright)** | Spawns PG+Redis services, boots uvicorn on :8002, runs `yarn build` then `yarn e2e` (vite preview on :4173 proxying `/api → :8002`, Playwright drives Chromium against the production bundle — 6 tests) | ~2–3 min |

**Adding a new test**: pure-Python unit → `tests/test_smoke.py`; needs DB → `tests/integration/test_phase*.py`; frontend logic → `frontend-v2/src/**/*.test.ts(x)` (vitest); user-flow → `frontend-v2/e2e/*.spec.ts` (Playwright).

---

## Type contract workflow (backend ↔ frontend)

The Pydantic models in `apps/api/src/models.py` are the **single source of truth** for HTTP wire types. Workflow when adding/changing a field:

```bash
# 1. Edit the model
$EDITOR apps/api/src/models.py            # add / tighten a field

# 2. Make sure the SQL projection / helpers.sys_row_to_dict actually emits it.
$EDITOR apps/api/src/helpers.py            # if camelCase passthrough is needed
$EDITOR apps/api/src/local_search.py       # if the search SQL needs the column

# 3. Regenerate the TS types from the running API
docker compose up -d --build api           # bake the new model into the image
cd frontend-v2
VITE_OPENAPI_URL=http://127.0.0.1:8000/openapi.json yarn types:gen
git diff src/types/api.gen.ts              # review the schema delta

# 4. (Optional) Add a friendlier alias in the wrapper
$EDITOR src/types/api.ts                   # re-export with a nicer name if needed

# 5. Commit BOTH the model change AND the regenerated api.gen.ts
git add apps/api/src/models.py frontend-v2/src/types/api.gen.ts
git commit
```

**If you skip step 3**, the `OpenAPI types drift check` CI job will fail your PR with a diff showing exactly what regeneration would have produced.

**Avoid `Optional[dict]` in request models** — Pydantic 2.10+ emits `additionalProperties: false` for `dict`, which `openapi-typescript` renders as the strict-empty `Record<string, never>` (TypeScript will then refuse to pass real values through it). Use a sub-model (`RangeFilter`, `BodyFilters`, `CoordsModel`, …) or `Any` (genuinely opaque) instead.

---

## Audit refactor history

The codebase passed through a 9-phase audit in May 2026. All phases shipped to production. AUDIT_REPORT.md (95 KB), AUDIT_PATCHES.diff (1.5 MB / 23 620 lines) and REFACTOR_LOG.md track the full detail and live on the `Mahoosive` branch.

| Phase | Theme | Landed in |
|---|---|---|
| 1 | Centralise economy/body-filter mappings (`search_economies.py`); delete legacy `/frontend/`; monorepo `apps/{api,eddn,importer}/`; `RegionMapData.py` → `data/region_map.json` | PR #3 |
| 2 | Remove inline SQL fallback in `routers/search.py` ("no silent fallback"); contract test `test_phase2_search_no_fallback.py` | PR #3 |
| 3 | User scope on `watchlist` / `notes` via `sync_key`; `sql/010_sync_key_scoping.sql` | PR #3 |
| 4 | `statement_timeout` on heavy map queries | PR #3 |
| 5 | Materialised views for `/api/map/{regions,heatmap,timeline}`; `sql/009_map_materialised_views.sql` + `refresh_map_mviews()` | PR #3 |
| 6 | API integration tests + Vitest + Playwright e2e (78 new tests across 3 layers) | PR #3 |
| 7 | `openapi-typescript` CI drift check; `api.gen.ts` baseline | PR #4 |
| 7b | Strict `response_model=` on every v2-frontend-consumed endpoint; replace `Optional[dict]` request fields with real Pydantic sub-models; `useWatchlist` on TanStack Query; Playwright E2E in CI | PR #5 |
| 8+ | (in flight) Broaden TanStack Query into `useSearch` / `useAutocomplete`; tighten remaining request dicts; `_redesign/` Phase-2 wiring | TBD |

---

## First-time setup (fresh server)

### 0. DNS prerequisites
Point your domain at the server **before** running setup (Let's Encrypt needs port 80):
- Cloudflare DNS: A record → Hetzner IPv4, AAAA → Hetzner IPv6
- SSL/TLS mode: **Full** (origin has a real cert)
- Both `ed-finder.app` and `www.ed-finder.app` should resolve to the server

### 1. Clone and run setup
```bash
git clone https://github.com/brianstewart377-rgb/ed-finder.git /opt/ed-finder
cd /opt/ed-finder
chmod +x setup.sh
sudo ./setup.sh
```

> **Note:** All paths in this document assume the repo is cloned to `/opt/ed-finder`.
> This is the single working directory — there is no separate source/install split.

The script handles everything automatically:
- Kills system nginx (Ubuntu 24.04 ships with it pre-installed — it grabs port 80)
- Obtains Let's Encrypt cert before Docker starts
- Fixes PostgreSQL md5 auth for pgBouncer
- Starts all services and verifies health

### 2. Download the Spansh dumps (~15–30 min on Hetzner's 1 Gbps link)

> **Important:** Download files **first**, then import separately. Running
> `--all` without downloading first streams the gzip through the JSON parser into
> PostgreSQL simultaneously — insert speed limits the pipeline to ~300 kB/s,
> meaning 110 GB takes ~100 hours instead of 15 minutes.
>
> The setup script installs `aria2c`, which opens 16 parallel connections and
> can saturate the 1 Gbps uplink (~125 MB/s). The full 110 GB downloads in
> approximately 15–30 minutes.

```bash
screen -S import
/opt/ed-finder/scripts/run_import.sh --download-only
# Ctrl+A D to detach, reattach: screen -r import
```

Files downloaded (~110 GB total):

| File | Compressed | Contents |
|---|---|---|
| `galaxy.json.gz` | ~102 GB | All 186M systems + bodies + stations |
| `galaxy_populated.json.gz` | ~3.6 GB | Faction/economy enrichment data |
| `galaxy_stations.json.gz` | ~3.6 GB | Station market/service data |

> **Note:** Spansh no longer provides separate `bodies.json.gz` or `attractions.json.gz`.
> All body and station data is nested inside `galaxy.json.gz`. The importer handles this
> in a single pass — no separate body import step needed.

### 3. Drop indexes before importing (critical for speed)

Dropping non-essential indexes before a large import can reduce import time by 50–80%:

```bash
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "DO \$\$ DECLARE r RECORD; BEGIN FOR r IN
        SELECT indexname FROM pg_indexes WHERE tablename IN
        ('systems','bodies','stations','factions')
        AND indexname NOT LIKE '%pkey%'
        LOOP EXECUTE 'DROP INDEX IF EXISTS '||r.indexname;
        END LOOP; END\$\$;"
```

### 4. Import (~8–24 hrs with COPY method, fully resumable)

```bash
screen -r import
/opt/ed-finder/scripts/run_import.sh --all
# Ctrl+A D to detach
```

### 5. Rebuild indexes (after import)

```bash
docker compose exec postgres psql -U edfinder -d edfinder \
    -f /docker-entrypoint-initdb.d/002_indexes.sql
```

### 6. Build ratings + grid + clusters

```bash
/opt/ed-finder/scripts/run_import.sh build_ratings.py --rebuild --workers 12
/opt/ed-finder/scripts/run_import.sh build_grid.py
screen -S clusters
/opt/ed-finder/scripts/run_import.sh build_clusters.py --workers 12
```

### 7. Start EDDN listener

```bash
docker compose up -d eddn
```

---

## Operations

### Deploy a code-only change (no schema migration)

For PRs that touch only Python or TypeScript — the common case post-launch:

```bash
ssh root@<hetzner-ip>
cd /opt/ed-finder

git log -1 --oneline > /tmp/pre-deploy-commit.txt   # rollback target
git pull --ff-only origin main

# Frontend: nginx serves frontend-v2/dist/ directly, so it must be
# rebuilt on the host (not inside a container).
( cd frontend-v2 && yarn install --frozen-lockfile && yarn build )

# API: rebuild the image so the new Python source is baked in.
docker compose up -d --build api
sleep 5
docker compose logs --tail=50 api | grep -E "Application startup complete|ERROR"

# Reload nginx so /v2/ serves the new dist.
docker compose exec nginx nginx -s reload

# Verify the new code is live (substitute real schema refs you care about).
curl -s http://localhost:8000/api/health
docker compose exec -T api python3 -c "import urllib.request,json; \
  d=json.load(urllib.request.urlopen('http://localhost:8000/openapi.json')); \
  print(d['components']['schemas']['SearchResponse']['properties']['results']['items'])"
```

> **Cloudflare**: if you cache `/v2/index.html` in the dashboard, **purge** it after deploy or users keep getting the old bundle until their TTL expires.

**Rollback** (~3 min):
```bash
PREV=$(awk '{print $1}' /tmp/pre-deploy-commit.txt)
cd /opt/ed-finder && git reset --hard "$PREV"
( cd frontend-v2 && yarn build )
docker compose up -d --build api
docker compose exec nginx nginx -s reload
```

### Reinstall / Nuke

```bash
# Pull latest code and rebuild containers (PRESERVES database):
cd /opt/ed-finder
git pull origin main
sudo bash setup.sh --reinstall

# Destroy EVERYTHING including the database (full re-import required):
sudo bash setup.sh --nuke
```

### Check import status
```bash
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT dump_file, status, rows_processed, error_message FROM import_meta;"
```

### Check database size
```bash
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) \
        FROM pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;"
```

### Check post-import script status
```bash
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT key, value, updated_at FROM app_meta ORDER BY key;"
# Look for: grid_built=true, ratings_built=true, clusters_built=true
```

### Automation & Scheduling

#### Weekly Full Rebuild
The `nightly_update.sh` script (which runs via cron) has been updated to perform a **Full Cluster Rebuild every Sunday**. On other days, it only processes "dirty" systems updated via EDDN. This ensures your cluster data is perfectly in sync every week.

#### Manual Trigger (API)
You can now trigger a cluster rebuild (dirty systems only) manually via the API. This is useful if you've just done a large manual data injection and don't want to wait for the nightly cron.

**Endpoint:** `POST /api/admin/rebuild-clusters`

Example using `curl`:
```bash
curl -X POST http://localhost:8000/api/admin/rebuild-clusters
```

You can check the status of the job by querying the recent events endpoint:
```bash
curl http://localhost:8000/api/events/recent
```
Look for the `jobs` object in the response.

### Resume a failed import
```bash
/opt/ed-finder/scripts/run_import.sh --all
# No --resume flag needed — interrupted imports auto-resume from checkpoint
```

### Manual nightly update
```bash
# Export password first so the script can use it
export POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD /opt/ed-finder/.env | cut -d= -f2)
/opt/ed-finder/scripts/nightly_update.sh
```

### Restart individual services
```bash
docker compose restart api
docker compose restart nginx
docker compose restart eddn
docker compose up -d --build api
```

### import_spansh.py changelog

| Version | Fix |
|---|---|
| v2.0 | Initial high-speed COPY importer |
| v2.6 | **Auto-Finalize** — Automatically triggers the index rebuild from `002_indexes.sql` once the import is complete, ensuring the database is ready for post-import scripts immediately. |
