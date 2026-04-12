# ED Finder — Hetzner PostgreSQL Stack
## Complete setup guide for production deployment

---

## Server spec
- **Hetzner AX41**: Intel i7-8700 · 128 GB RAM · 2 × 1 TB SSD
- **OS**: Ubuntu 24.04 LTS
- **Domain**: ed-finder.app

---

## Stack
| Service | Image | Purpose |
|---|---|---|
| PostgreSQL 16 | `postgres:16-alpine` | Main database (186M+ systems) |
| pgBouncer | `edoburu/pgbouncer` | Connection pooling (24 users) |
| Redis 7 | `redis:7-alpine` | API response cache |
| FastAPI | `python:3.12-slim` | API backend |
| EDDN Listener | `python:3.12-slim` | Live game data ingestion |
| Nginx | `nginx:alpine` | SSL + static file serving |

---

## First-time setup

### 1. On the Hetzner server
```bash
# Clone or copy the project
git clone https://github.com/YOUR/ed-finder.git /opt/ed-finder-src
cd /opt/ed-finder-src/hetzner

# Run setup (as root)
sudo chmod +x setup.sh
sudo ./setup.sh
```

### 2. Download Spansh dumps (~200 GB total — takes hours)
```bash
cd /opt/ed-finder
docker compose --profile import run --rm importer \
    python3 import_spansh.py --download
```

Downloads to `/data/dumps/`:
| File | Size (compressed) | Contents |
|---|---|---|
| `galaxy.json.gz` | ~8 GB | All 186M systems |
| `bodies.json.gz` | ~80 GB | All scanned bodies |
| `galaxy_stations.json.gz` | ~15 GB | All stations |
| `galaxy_populated.json.gz` | ~2 GB | Populated system detail |
| `attractions.json.gz` | ~1 GB | Biologicals, geology, POIs |

### 3. Run the import (1–3 days, fully resumable)
```bash
# Start import in screen so it survives disconnection
screen -S import
docker compose --profile import up importer
# Ctrl+A, D to detach

# Monitor progress
docker logs ed-importer -f
# or:
docker compose exec importer python3 import_spansh.py --status
```

### 4. Build ratings (2–4 hours)
```bash
docker compose --profile import run --rm importer \
    python3 build_ratings.py --rebuild --workers 12
```

### 5. Build spatial grid (10–30 minutes)
```bash
docker compose --profile import run --rm importer \
    python3 build_grid.py
```

### 6. Build cluster summary (8–24 hours — the long one)
```bash
screen -S clusters
docker compose --profile import run --rm importer \
    python3 build_clusters.py --workers 12
# Ctrl+A, D to detach and let it run
```

### 7. Build indexes (3–5 hours)
```bash
# Run AFTER all data is loaded — much faster this way
docker compose exec postgres \
    psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/002_indexes.sql
```

### 8. Start full stack
```bash
cd /opt/ed-finder
docker compose up -d
docker compose ps
```

### 9. Verify
```bash
curl https://ed-finder.app/api/health
curl https://ed-finder.app/api/status | python3 -m json.tool
```

---

## API endpoints

### Existing (Pi-compatible)
| Method | Path | Description |
|---|---|---|
| POST | `/api/local/search` | Standard distance search |
| GET | `/api/local/status` | DB health + stats |
| GET | `/api/local/autocomplete` | System name autocomplete |
| GET | `/api/system/{id64}` | Full system detail |
| GET | `/api/body/{body_id}` | Body detail |
| POST | `/api/systems/batch` | Batch system lookup |
| GET/POST/DELETE | `/api/watchlist/...` | Watchlist CRUD |
| GET/POST/DELETE | `/api/systems/{id64}/note` | Notes CRUD |

### New (Hetzner only)
| Method | Path | Description |
|---|---|---|
| POST | `/api/search/galaxy` | Galaxy-wide economy search |
| POST | `/api/search/cluster` | Multi-economy cluster search |

#### Galaxy-wide search example
```json
POST /api/search/galaxy
{
    "economy": "HighTech",
    "min_score": 50,
    "limit": 100
}
```
Returns the 100 highest-scoring uncolonised High Tech candidates in the entire galaxy, sorted by score.

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
Returns the 50 best anchor points in the galaxy where within 500ly you can find enough viable systems to build all four economy types.

---

## Database schema summary

| Table | Rows (est.) | Description |
|---|---|---|
| `systems` | 186M | All known systems |
| `bodies` | ~800M | All scanned bodies |
| `stations` | ~5M | Stations, carriers, outposts |
| `attractions` | ~2M | Biologicals, geology, POIs |
| `ratings` | ~70M | Pre-computed scores (visited only) |
| `spatial_grid` | ~100k | 500ly grid cells |
| `cluster_summary` | ~70M | Pre-aggregated empire coverage |
| `factions` | ~80k | Player & NPC factions |
| `system_factions` | ~500k | Faction presence per system |
| `watchlist` | user data | Watched systems |
| `system_notes` | user data | Personal notes |

---

## Postgres tuning (applied via docker-compose.yml)
Key settings for 128GB RAM:
- `shared_buffers = 32GB` — 25% of RAM for Postgres buffer pool
- `effective_cache_size = 96GB` — tells planner how much OS + Postgres cache exists
- `work_mem = 256MB` — per-operation sort/hash memory (high = fast aggregations)
- `maintenance_work_mem = 4GB` — for index builds and VACUUM
- `max_parallel_workers = 12` — uses all 12 threads of i7-8700

---

## Maintenance

### Check import status
```bash
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT * FROM import_progress;"
```

### Check database size
```bash
docker compose exec postgres psql -U edfinder -d edfinder \
    -c "SELECT schemaname, relname, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 20;"
```

### Manual nightly update
```bash
/opt/ed-finder/import/nightly_update.sh
```

### Restart individual services
```bash
docker compose restart api       # restart API
docker compose restart eddn      # restart EDDN listener
docker compose restart nginx     # reload nginx config
```

### Update the app (no data loss)
```bash
cd /opt/ed-finder-src
git pull
cp -r hetzner/backend/* /opt/ed-finder/backend/
cp hetzner/config/nginx.conf /opt/ed-finder/config/
cp -r frontend/* /opt/ed-finder/frontend/
docker compose up -d --build api nginx
```

---

## Estimated timeline (first deployment)

| Step | Duration |
|---|---|
| Setup script | 5 minutes |
| Download dumps | 4–12 hours |
| Import galaxy.json.gz | 2–4 hours |
| Import bodies.json.gz | 24–48 hours |
| Import stations + attractions | 2–4 hours |
| Build ratings | 2–4 hours |
| Build spatial grid | 10–30 minutes |
| Build cluster_summary | 8–24 hours |
| Build indexes | 3–5 hours |
| **Total** | **~3–5 days** |

All steps are resumable if interrupted. The server can serve live traffic from the API as soon as `import galaxy.json.gz` completes — cluster search just won't be available until cluster_summary is built.
