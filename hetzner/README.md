# ED Finder — Hetzner PostgreSQL Stack
## Complete setup guide for production deployment

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

## First-time setup

### 0. Prerequisites — DNS
Point your domain at the server **before** running setup (Let's Encrypt needs to reach port 80):
- In Cloudflare DNS: A record → your Hetzner IPv4, AAAA → your Hetzner IPv6
- SSL/TLS mode: set to **Full** (origin has a real cert)
- Both `ed-finder.app` and `www.ed-finder.app` should resolve to the server

### 1. Clone and run setup
```bash
git clone https://github.com/brianstewart377-rgb/ed-finder.git /opt/ed-finder-src
cd /opt/ed-finder-src/hetzner
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
| `galaxy.json.gz` | ~102 GB | All 186M systems + bodies + stations (single file) |
| `galaxy_populated.json.gz` | ~3.6 GB | Faction/economy enrichment data |
| `galaxy_stations.json.gz` | ~3.6 GB | Station market/service data |

> **Note:** Spansh no longer provides separate `bodies.json.gz` or `attractions.json.gz`.
> All body and station data is now nested inside `galaxy.json.gz`. The importer
> handles this in a single pass — no separate body import step needed.

### 3. Drop indexes before importing (critical for speed)

Dropping non-essential indexes before the bulk load makes the import **10–50× faster**
(COPY into unindexed tables, rebuild indexes after):

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

### 4. Import the downloaded files (~8–24 hrs with COPY, fully resumable)

```bash
screen -r import   # re-attach, or: screen -S import
docker compose --profile import run --rm importer \
    import_spansh.py --all --resume
# Ctrl+A D to detach
```

### 5. Monitor the import
```bash
# Re-attach screen
screen -r import

# Check status table
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT dump_file, status, rows_processed FROM import_meta;"

# Row counts while running
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;"

# Disk usage
df -h /data
```

### 6. Rebuild indexes (3–5 hours — run AFTER import completes)
```bash
docker compose exec postgres \
    psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/002_indexes.sql
```
> Indexes were dropped before the import for speed. Rebuild them now.

### 7. Build ratings (2–4 hours)
```bash
docker compose --profile import run --rm importer \
    python3 build_ratings.py --rebuild --workers 12
```

### 8. Build spatial grid (10–30 minutes)
```bash
docker compose --profile import run --rm importer python3 build_grid.py
```

### 9. Build cluster summary (8–24 hours — the long one)
```bash
screen -S clusters
docker compose --profile import run --rm importer \
    python3 build_clusters.py --workers 12
# Ctrl+A D to detach
```

### 10. Start EDDN live listener
```bash
docker compose up -d eddn
```

### 11. Verify everything
```bash
docker compose ps
curl https://ed-finder.app/api/health
curl https://ed-finder.app/api/status | python3 -m json.tool
```

---

## Estimated timeline (first deployment)

| Step | Duration |
|---|---|
| Setup script | 5–10 minutes |
| Download all dumps (aria2c, 16-conn, 1 Gbps) | 15–30 minutes |
| Drop indexes (before import) | < 1 minute |
| Import `galaxy.json.gz` (COPY method) | 8–24 hours |
| Import `galaxy_populated.json.gz` | 1–2 hours |
| Import `galaxy_stations.json.gz` | 1–2 hours |
| Rebuild indexes (002_indexes.sql) | 3–5 hours |
| Build ratings | 2–4 hours |
| Build spatial grid | 10–30 minutes |
| Build cluster_summary | 8–24 hours |
| **Total** | **~2–3 days** |

> **Import speed notes:**
> - **Download**: `aria2c` with 16 parallel connections completes 110 GB in ~15–30 min on Hetzner 1 Gbps. Without aria2c (wget/curl single-stream), ~25–35 min. Streaming directly from URL into PostgreSQL (`--all` without `--download-only` first) is bottlenecked by DB insert speed to ~300 kB/s → ~100 hours — always download first.
> - **COPY vs INSERT**: The v2.0 importer uses `COPY`-via-temp-table instead of `INSERT … ON CONFLICT`. This is 10–50× faster: ~5–15 MB/s with indexes dropped (target 8–24 h) vs ~250 kB/s with live indexes (~5 days). **Always drop indexes before the bulk import** (step 3) and rebuild afterward (step 6).
> - **PostgreSQL tuning during import**: The importer automatically applies `synchronous_commit=off`, `work_mem=256MB`, `maintenance_work_mem=4GB` per-session. For even faster loads, also run `ALTER SYSTEM SET fsync=off; SELECT pg_reload_conf();` before importing and re-enable after.

The API serves live traffic as soon as `galaxy.json.gz` import completes.
Cluster search requires cluster_summary to be built first.

---

## Known issues and fixes (lessons from first deployment)

### 1. System nginx grabs port 80
Ubuntu 24.04 installs nginx as a system service. It starts on boot and holds port 80/443, preventing the Docker nginx container from binding.
```bash
# Fix (setup.sh does this automatically):
systemctl stop nginx && systemctl mask nginx
```

### 2. pgBouncer authentication failure
PostgreSQL 16 defaults to `scram-sha-256`. The `edoburu/pgbouncer` image uses `AUTH_TYPE=md5` for client connections but needs the password stored as md5 on the postgres side.
```bash
# Fix (setup.sh does this automatically):
docker compose exec postgres psql -U edfinder -d edfinder -c \
    "SET password_encryption = md5; ALTER USER edfinder WITH PASSWORD 'yourpassword';"
docker compose exec postgres sed -i 's/scram-sha-256/md5/g' \
    /var/lib/postgresql/data/pg_hba.conf
docker compose exec postgres psql -U edfinder -d edfinder -c "SELECT pg_reload_conf();"
```

### 3. nginx upstream DNS crash on startup
Static `upstream { server api:8000; }` blocks resolve DNS once at startup. If the `api` container isn't ready yet, nginx crashes with `host not found in upstream`.  
**Fix**: use Docker's internal resolver + a variable for lazy per-request DNS:
```nginx
resolver 127.0.0.11 valid=10s ipv6=off;
# then in location blocks:
set $api_upstream http://api:8000;
proxy_pass $api_upstream;
```

### 4. Frontend 403 Forbidden
The compose file originally used `../frontend:/var/www/html:ro` which resolves to `/opt/frontend` (doesn't exist). Files are at `/opt/ed-finder-src/frontend/`.  
**Fix**: use the absolute path in docker-compose.yml:
```yaml
- /opt/ed-finder-src/frontend:/var/www/html:ro
```
Also ensure files are world-readable: `chmod -R 755 /opt/ed-finder-src/frontend/`

### 5. Cloudflare 521 (Web server is down)
Cloudflare couldn't reach the origin. Causes:
- System nginx holding port 80 (see fix #1)
- DNS A record not pointing at the Hetzner IP
- Docker nginx container restarting

Check: `ss -tlnp | grep -E ':80|:443'` — should show `docker-proxy` not `nginx`.

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

### Galaxy-wide endpoints (requires full import)
| Method | Path | Description |
|---|---|---|
| POST | `/api/search/galaxy` | Galaxy-wide economy search |
| POST | `/api/search/cluster` | Multi-economy cluster search |
| GET | `/api/status` | Full import + data status |

#### Galaxy search example
```json
POST /api/search/galaxy
{
    "economy": "HighTech",
    "min_score": 50,
    "limit": 100
}
```

#### Cluster search example
```json
POST /api/search/cluster
{
    "requirements": [
        {"economy": "HighTech",    "min_count": 1, "min_score": 50},
        {"economy": "Agriculture", "min_count": 2, "min_score": 40},
        {"economy": "Refinery",    "min_count": 2, "min_score": 35},
        {"economy": "Industrial",  "min_count": 1, "min_score": 35}
    ],
    "limit": 50
}
```

---

## Database schema summary

| Table | Rows (est.) | Description |
|---|---|---|
| `systems` | 186M | All known systems |
| `bodies` | ~800M | All scanned bodies (from galaxy.json.gz) |
| `stations` | ~5M | Stations, carriers, outposts |
| `ratings` | ~70M | Pre-computed economy scores |
| `spatial_grid` | ~100k | 500ly grid cells |
| `cluster_summary` | ~70M | Pre-aggregated empire coverage |
| `factions` | ~80k | Player & NPC factions |
| `import_meta` | 3 rows | Import status per dump file |
| `watchlist` | user data | Watched systems |
| `system_notes` | user data | Personal notes |

---

## PostgreSQL tuning (applied via docker-compose.yml)
Settings for 128 GB RAM / i7-8700 (12 threads):
- `shared_buffers = 32GB` — 25% of RAM for Postgres buffer pool
- `effective_cache_size = 96GB` — planner hint for total available cache
- `work_mem = 256MB` — per-operation sort/hash memory
- `maintenance_work_mem = 4GB` — for index builds and VACUUM
- `max_parallel_workers = 12` — use all 12 threads

---

## Maintenance

### Reinstall / Nuke

```bash
# Pull latest code and rebuild containers (PRESERVES database):
sudo bash setup.sh --reinstall

# Destroy EVERYTHING including the database (full re-import required):
sudo bash setup.sh --nuke
```

`--reinstall`: stops containers, removes images (forces rebuild), re-pulls code, restarts.  
`--nuke`: asks for `NUKE IT` confirmation, then destroys all Docker volumes including PostgreSQL data.

### Update the app (no data loss)
```bash
cd /opt/ed-finder-src
git pull origin main

# Copy updated files
cp hetzner/config/nginx.conf /opt/ed-finder/config/nginx.conf
cp hetzner/docker-compose.yml /opt/ed-finder/docker-compose.yml

# Rebuild and restart changed services only
cd /opt/ed-finder
docker compose up -d --build api nginx
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

### Resume a failed import
```bash
screen -S import
docker compose --profile import run --rm importer import_spansh.py --all --resume
# Ctrl+A D
```

### Manual nightly update
```bash
/opt/ed-finder/import/nightly_update.sh
```

### Restart individual services
```bash
docker compose restart api        # restart API
docker compose restart nginx      # reload nginx config
docker compose restart eddn       # restart EDDN listener
docker compose up -d --build api  # rebuild + restart API
```
