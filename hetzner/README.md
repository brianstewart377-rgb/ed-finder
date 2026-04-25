# ED Finder — Hetzner PostgreSQL Stack
## Complete setup and import guide

---

## Server spec
- **Hetzner AX41-SSD**: Intel i7-8700 (6C/12T) · 128 GB RAM · 3 × 1 TB NVMe (RAID-5 ~1.8 TB usable)
- **OS**: Ubuntu 24.04 LTS
- **Domain**: ed-finder.app (Cloudflare proxied — A/AAAA records point to Hetzner IP)

---

## Stack
| Service | Image | Purpose |
|---|---|---|
| PostgreSQL 16 | `postgres:16-alpine` | Main database (186M+ systems) |
| pgBouncer | `edoburu/pgbouncer` | Connection pooling (transaction mode) |
| Redis 7 | `redis:7-alpine` | API response cache |
| FastAPI | `python:3.12-slim` | API backend |
| EDDN Listener | `python:3.12-slim` | Live game data ingestion |
| Nginx | `nginx:alpine` | SSL + static file serving |

---

## Import script versions (current)

| Script | Version | Key fix |
|---|---|---|
| `import_spansh.py` | 2.0 | COPY-via-temp-table (10–50× faster than INSERT) |
| `build_grid.py` | 2.3 | Disable RI triggers + ctid-range batching |
| `build_ratings.py` | 2.2 | Disable RI triggers on dirty-flag UPDATE |
| `build_clusters.py` | 1.3 | Disable RI triggers on dirty-flag UPDATE |

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

### build_ratings.py changelog

| Version | Fix |
|---|---|
| v2.0 | Fixed server-side cursor truncation at ~74M rows; batch body fetch (one query per chunk instead of per system); dynamic work dispatch; corrected score_economy() math |
| v2.1 | Added startup/stage banners, safe log path, per-worker heartbeat |
| v2.2 | Disabled RI triggers on `UPDATE systems SET rating_dirty = FALSE` — eliminated ~252M spurious trigger evaluations per run; fixed startup banner (was still saying v2.1); fixed "Next step" footer (incorrectly said `build_grid.py` — should be `build_clusters.py`) |

### build_clusters.py changelog

| Version | Fix |
|---|---|
| v1.0 | Initial version |
| v1.1 | Log directory auto-creation; resume-safe mode; grid-aware queries; fetchmany streaming |
| v1.2 | Added startup/stage banners, per-worker heartbeat, safe log path, spatial-grid-missing warning |
| v1.3 | Disabled RI triggers on `UPDATE systems SET cluster_dirty = FALSE` — eliminated ~2.5B spurious trigger evaluations across 73M anchors; fixed startup banner (was still saying v1.2); fixed worker_id collision (was `chunks % workers`, causing multiple chunks to share the same ID and produce confusing logs) |

### 002_indexes.sql changelog

| Addition | Reason |
|---|---|
| `idx_sys_grid_null` — partial index on `systems(id64) WHERE grid_cell_id IS NULL` | Allows `build_grid.py` v2.2+ to find the resume page in <1s instead of a 74 GB sequential scan (~5 min) on restart |

---

## Repository layout

```
hetzner/
├── backend/                 # Docker build context for ALL Python services
│   ├── Dockerfile           # FastAPI API server (main.py)
│   ├── Dockerfile.eddn      # EDDN live listener (eddn_listener.py)
│   ├── Dockerfile.import    # One-shot import runner (import_spansh.py etc.)
│   ├── requirements.txt     # Shared Python dependencies
│   ├── main.py              # FastAPI application
│   ├── eddn_listener.py     # EDDN WebSocket listener
│   ├── local_search.py      # Search logic (imported by main.py)
│   ├── import_spansh.py     # Bulk Spansh dump importer
│   ├── build_grid.py        # Spatial grid builder       (v2.3 — single source)
│   ├── build_ratings.py     # Economy rating computer    (v2.2 — single source)
│   ├── build_clusters.py    # Cluster summary builder    (v1.3 — single source)
│   └── progress.py          # Shared progress-bar helper
├── config/
│   └── nginx.conf           # Nginx SSL + proxy config
├── scripts/
│   ├── nightly_update.sh    # Nightly delta-import cron script
│   └── watch_grid.sh        # Live progress watcher for build_grid.py
├── sql/
│   ├── 001_schema.sql       # Table definitions (auto-run on first postgres start)
│   ├── 002_indexes.sql      # All indexes including idx_sys_grid_null
│   └── 003_functions.sql    # PL/pgSQL helpers (grid lookup, distance, etc.)
├── tests/
│   └── test_smoke.py        # Basic smoke tests
├── docker-compose.yml       # Full service stack
├── setup.sh                 # First-time server setup script
└── README.md                # This file
```

> **Single source of truth:** All import scripts live **only** in `backend/`.
> The `Dockerfile.import` copies them into the image at build time.
> When running scripts with `docker run -v`, always mount from `backend/` — there
> is no separate `import/` directory.

---

## First-time setup (fresh server)

### 0. DNS prerequisites
Point your domain at the server **before** running setup (Let's Encrypt needs port 80):
- Cloudflare DNS: A record → Hetzner IPv4, AAAA → Hetzner IPv6
- SSL/TLS mode: **Full** (origin has a real cert)
- Both `ed-finder.app` and `www.ed-finder.app` should resolve to the server

### 1. Clone and run setup
```bash
git clone https://github.com/brianstewart377-rgb/ed-finder.git /opt/ed-finder-src
cd /opt/ed-finder-src/hetzner

> **Note:** All paths in this document assume the repo is cloned to `/opt/ed-finder-src`.
> If you cloned elsewhere, adjust the paths accordingly.
chmod +x setup.sh
sudo ./setup.sh
```

The script handles everything automatically:
- Kills system nginx (Ubuntu 24.04 ships with it pre-installed — it grabs port 80)
- Obtains Let's Encrypt cert before Docker starts
- Fixes PostgreSQL md5 auth for pgBouncer
- Starts all services and verifies health

### 2. Download the Spansh dumps (~15–30 min on Hetzner's 1 Gbps link)

> **⚠️ Important:** Download files **first**, then import separately. Running
> `--all` without downloading first streams the gzip through the JSON parser into
> PostgreSQL simultaneously — insert speed limits the pipeline to ~300 kB/s,
> meaning 110 GB takes ~100 hours instead of 15 minutes.
>
> The setup script installs `aria2c`, which opens 16 parallel connections and
> can saturate the 1 Gbps uplink (~125 MB/s). The full 110 GB downloads in
> approximately 15–30 minutes.

```bash
screen -S import
docker compose --profile import run --rm importer \
    import_spansh.py --download-only
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

Dropping non-essential indexes before the bulk load makes the import **10–50× faster**:

```bash
docker compose exec postgres psql -U edfinder -d edfinder -c "
DO \$\$ DECLARE r RECORD; BEGIN
  FOR r IN SELECT indexname FROM pg_indexes
    WHERE tablename IN ('systems','bodies','stations','factions')
    AND indexname NOT LIKE '%pkey%'
  LOOP
    EXECUTE 'DROP INDEX IF EXISTS ' || r.indexname;
    RAISE NOTICE 'Dropped %', r.indexname;
  END LOOP;
END \$\$;"
```

### 4. Import the downloaded files (~8–24 hrs, fully resumable)

```bash
screen -r import   # re-attach, or: screen -S import
docker compose --profile import run --rm importer \
    import_spansh.py --all --resume
# Ctrl+A D to detach
```

### 5. Monitor the import
```bash
screen -r import

# Check status table
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT dump_file, status, rows_processed FROM import_meta;"

# Row counts while running
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;"
```

### 6. Rebuild indexes after import (3–5 hours)
```bash
docker compose exec postgres \
    psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/002_indexes.sql
```

> Indexes were dropped before the import for speed. Rebuild them now.
> `idx_sys_grid_null` is included in `002_indexes.sql` — this partial index
> lets `build_grid.py` resume from exactly the right page in under 1 second.

### 7. Run the three post-import scripts (in order)

**Always run these in this exact order. Each one depends on the previous.**

#### Export your password into the shell first (do this once per session)
```bash
# .env lives in /opt/ed-finder/ (the install dir), NOT the repo dir
export POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD /opt/ed-finder/.env | cut -d= -f2)
echo "Password loaded: ${POSTGRES_PASSWORD:0:4}****"  # sanity check
```

#### Pull the latest scripts
```bash
git fetch origin && git reset --hard origin/main
```

Verify versions:
```bash
head -5 backend/build_grid.py      # must say: Version: 2.3
head -5 backend/build_ratings.py   # must say: Version: 2.2
head -5 backend/build_clusters.py  # must say: Version: 1.3
```

#### Kill any stuck DB processes
```bash
docker exec ed-postgres psql -U edfinder -d edfinder -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE query LIKE 'UPDATE systems%' AND state != 'idle';"
```

#### 7a. build_grid.py (~1 hour)

Assigns every system to a 500ly spatial grid cell. Required before build_clusters.py.

```bash
docker rm -f ed-importer-run 2>/dev/null; true
docker run --rm \
  --network ed-finder_default \
  --name ed-importer-run \
  --entrypoint python3 \
  -e DATABASE_URL="postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder" \
  -e LOG_FILE=/data/logs/build_grid.log \
  -v /opt/ed-finder-src/hetzner/backend/build_grid.py:/app/build_grid.py \
  -v /opt/ed-finder-src/hetzner/backend/progress.py:/app/progress.py \
  -v /data/logs:/data/logs \
  hetzner-importer:latest \
  build_grid.py
```

> `${POSTGRES_PASSWORD}` is exported by the shell when you `source .env` or set it
> manually. Alternatively paste the literal password from `.env`.

Wait for: `Spatial Grid Complete` in the output.

If it crashes or is interrupted, re-run the exact same command — it resumes automatically.

#### 7b. build_ratings.py (~3–5 hours)

Computes economy scores for all systems with body data. Required before build_clusters.py.

```bash
docker rm -f ed-importer-run 2>/dev/null; true
docker run --rm \
  --network ed-finder_default \
  --name ed-importer-run \
  --entrypoint python3 \
  -e DATABASE_URL="postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder" \
  -e LOG_FILE=/data/logs/build_ratings.log \
  -v /opt/ed-finder-src/hetzner/backend/build_ratings.py:/app/build_ratings.py \
  -v /opt/ed-finder-src/hetzner/backend/progress.py:/app/progress.py \
  -v /data/logs:/data/logs \
  hetzner-importer:latest \
  build_ratings.py
```

Wait for: `Ratings Complete` in the output.

#### 7c. build_clusters.py (~8–24 hours)

Builds the empire-location cluster summary. The longest step.

```bash
docker rm -f ed-importer-run 2>/dev/null; true
docker run --rm \
  --network ed-finder_default \
  --name ed-importer-run \
  --entrypoint python3 \
  -e DATABASE_URL="postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder" \
  -e LOG_FILE=/data/logs/build_clusters.log \
  -v /opt/ed-finder-src/hetzner/backend/build_clusters.py:/app/build_clusters.py \
  -v /opt/ed-finder-src/hetzner/backend/progress.py:/app/progress.py \
  -v /data/logs:/data/logs \
  hetzner-importer:latest \
  build_clusters.py
```

Wait for: `Cluster Summary Complete` in the output.

> **Checking progress while any script is running** (run in a second terminal):
> ```bash
> # Live DB activity
> docker exec ed-postgres psql -U edfinder -d edfinder \
>   -c "SELECT phase, rows_done, rows_total FROM pg_stat_progress_update;"
>
> # Tail the log
> tail -f /data/logs/build_grid.log      # or build_ratings / build_clusters
> ```

### 8. Start EDDN live listener
```bash
docker compose up -d eddn
```

### 9. Verify everything
```bash
docker compose ps
curl https://ed-finder.app/api/health
curl https://ed-finder.app/api/status | python3 -m json.tool
```

---

## Estimated timeline (first deployment)

| Step | Duration |
|---|---|
| Setup script | 5–10 min |
| Download all dumps (aria2c, 1 Gbps) | 15–30 min |
| Drop indexes | < 1 min |
| Import galaxy.json.gz | 8–24 hrs |
| Import galaxy_populated + stations | 2–4 hrs |
| Rebuild indexes (002_indexes.sql) | 3–5 hrs |
| build_grid.py | ~1 hr |
| build_ratings.py | 3–5 hrs |
| build_clusters.py | 8–24 hrs |
| **Total** | **~2–3 days** |

---

## Re-running scripts on an existing database

All three post-import scripts are **fully resume-safe** by default:
- `build_grid.py` — skips already-assigned rows; resumes from first unassigned page
- `build_ratings.py` — skips systems that already have a ratings row
- `build_clusters.py` — skips anchors that already have a cluster_summary row

To force a full rebuild from scratch, pass `--rebuild` (or `--reset-cache` for the grid)
using the same `docker run` command from step 7, with an extra argument appended:

```bash
# Grid — wipe app_meta cache and reassign all grid_cell_ids
docker run --rm --network ed-finder_default --name ed-importer-run --entrypoint python3 \
  -e DATABASE_URL="postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder" \
  -e LOG_FILE=/data/logs/build_grid.log \
  -v /opt/ed-finder-src/hetzner/backend/build_grid.py:/app/build_grid.py \
  -v /opt/ed-finder-src/hetzner/backend/progress.py:/app/progress.py \
  -v /data/logs:/data/logs \
  hetzner-importer:latest build_grid.py --reset-cache

# Ratings — re-rate every system (even already-rated ones)
docker run --rm --network ed-finder_default --name ed-importer-run --entrypoint python3 \
  -e DATABASE_URL="postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder" \
  -e LOG_FILE=/data/logs/build_ratings.log \
  -v /opt/ed-finder-src/hetzner/backend/build_ratings.py:/app/build_ratings.py \
  -v /opt/ed-finder-src/hetzner/backend/progress.py:/app/progress.py \
  -v /data/logs:/data/logs \
  hetzner-importer:latest build_ratings.py --rebuild

# Clusters — recompute all anchors
docker run --rm --network ed-finder_default --name ed-importer-run --entrypoint python3 \
  -e DATABASE_URL="postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder" \
  -e LOG_FILE=/data/logs/build_clusters.log \
  -v /opt/ed-finder-src/hetzner/backend/build_clusters.py:/app/build_clusters.py \
  -v /opt/ed-finder-src/hetzner/backend/progress.py:/app/progress.py \
  -v /data/logs:/data/logs \
  hetzner-importer:latest build_clusters.py --rebuild
```

---

## Known issues and fixes

### 1. System nginx grabs port 80
Ubuntu 24.04 installs nginx as a system service. It starts on boot and holds port 80/443.
```bash
# Fix (setup.sh does this automatically):
systemctl stop nginx && systemctl mask nginx
```

### 2. pgBouncer authentication failure
PostgreSQL 16 defaults to `scram-sha-256`. pgBouncer uses md5.
```bash
# Fix (setup.sh does this automatically):
export POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD /opt/ed-finder/.env | cut -d= -f2)
docker compose exec postgres psql -U edfinder -d edfinder -c \
    "SET password_encryption = md5; ALTER USER edfinder WITH PASSWORD '${POSTGRES_PASSWORD}';"
```

### 3. nginx upstream DNS crash on startup
```nginx
# Fix: use Docker's internal resolver + a lazy variable
resolver 127.0.0.11 valid=10s ipv6=off;
set $api_upstream http://api:8000;
proxy_pass $api_upstream;
```

### 4. Frontend 403 Forbidden
The compose file used `../frontend:/var/www/html:ro` which resolves incorrectly.
```yaml
# Fix: use absolute path
- /opt/ed-finder-src/frontend:/var/www/html:ro
```

### 5. Cloudflare 521 (Web server is down)
Check: `ss -tlnp | grep -E ':80|:443'` — should show `docker-proxy`, not `nginx`.

### 6. Docker container name already in use
```bash
docker rm -f ed-importer-run 2>/dev/null
```
Always prepend `docker rm -f ed-importer-run 2>/dev/null` to any `docker run` command.

### 7. Wrong Docker network / connection timeout
The `docker-compose.yml` now pins the network name to `ed-finder_default` via an explicit
`networks:` block, so the name is always predictable regardless of which directory
`docker compose` is run from. All `docker run` commands below use `--network ed-finder_default`.

If you ever see a timeout and want to double-check:
```bash
docker network ls | grep ed
# Should show: ed-finder_default
```

### 8. Use the service hostname, not the container IP
Always use `@postgres:5432` in `DATABASE_URL` when the importer container is on
`ed-finder_default` — Docker DNS resolves the service name automatically.
Do **not** use the raw container IP (`172.19.0.x`); it can change between restarts
and bypasses Docker DNS.

### 9. build_grid stalling at ~41M rows
This was the original root cause of the multi-day debugging session. It is **fully fixed in v2.3**. The cause was 17 RI triggers firing per row UPDATE (16 FK triggers + 1 custom). The fix is `SET session_replication_role = replica` which is now applied automatically. Pull the latest code and re-run.

---

## API endpoints

### Standard endpoints
| Method | Path | Description |
|---|---|---|
| POST | `/api/local/search` | Distance-based system search |
| GET | `/api/local/status` | DB health + stats |
| GET | `/api/local/autocomplete` | System name autocomplete |
| GET | `/api/system/{id64}` | Full system detail |
| POST | `/api/systems/batch` | Batch system lookup |
| GET/POST/DELETE | `/api/watchlist/...` | Watchlist CRUD |
| GET/POST/DELETE | `/api/systems/{id64}/note` | Notes CRUD |

### Galaxy-wide endpoints (requires full import + post-import scripts)
| Method | Path | Description |
|---|---|---|
| POST | `/api/search/galaxy` | Galaxy-wide economy search |
| POST | `/api/search/cluster` | Multi-economy cluster search |
| GET | `/api/status` | Full import + data status |

---

## Database schema summary

| Table | Rows (est.) | Description |
|---|---|---|
| `systems` | 186M | All known systems |
| `bodies` | ~800M | All scanned bodies |
| `stations` | ~5M | Stations, carriers, outposts |
| `ratings` | ~70M | Pre-computed economy scores (built by build_ratings.py) |
| `spatial_grid` | ~100k | 500ly grid cells (built by build_grid.py) |
| `cluster_summary` | ~70M | Pre-aggregated empire coverage (built by build_clusters.py) |
| `factions` | ~80k | Player & NPC factions |
| `import_meta` | 3 rows | Import status per dump file |
| `app_meta` | ~10 rows | Script state (grid bounds, built flags) |
| `watchlist` | user data | Watched systems |
| `system_notes` | user data | Personal notes |

---

## PostgreSQL tuning (applied via docker-compose.yml)
Settings for 128 GB RAM / i7-8700 (12 threads):
- `shared_buffers = 32GB` — 25% of RAM for Postgres buffer pool
- `effective_cache_size = 96GB` — planner hint for total available cache
- `work_mem = 256MB` — per-operation sort/hash memory (bulk ops use 512MB+)
- `maintenance_work_mem = 4GB` — for index builds and VACUUM
- `max_parallel_workers = 12` — use all 12 threads

---

## Maintenance

### Pull latest code and re-run scripts
```bash
cd /opt/ed-finder-src/hetzner
git fetch origin && git reset --hard origin/main
# Then re-run whichever script you need
```

### Reinstall / Nuke
```bash
# Pull latest code and rebuild containers (PRESERVES database):
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

### Resume a failed import
```bash
docker compose --profile import run --rm importer import_spansh.py --all --resume
```

### Manual nightly update
```bash
# Export password first so the script can use it
export POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD /opt/ed-finder/.env | cut -d= -f2)
/opt/ed-finder-src/hetzner/scripts/nightly_update.sh
```

### Restart individual services
```bash
docker compose restart api
docker compose restart nginx
docker compose restart eddn
docker compose up -d --build api
```
