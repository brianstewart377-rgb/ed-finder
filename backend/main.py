#!/usr/bin/env python3
"""
ED Finder — Hetzner Backend
Version: 3.0 (PostgreSQL 16 / asyncpg)

Server: Hetzner AX41-SSD — i7-8700, 128 GB RAM, 3×1 TB NVMe RAID-5
DB:     PostgreSQL 16 via asyncpg connection pool → pgBouncer

Improvements in v3.0:
  - Code #8:  Pydantic response models for all endpoints (auto-generates OpenAPI docs)
  - Code #9:  Dependency injection for DB pool and Redis via FastAPI Depends()
  - Code #10: Background tasks for analytics/metric increments (off critical path)
  - Code #11: Redis caching for autocomplete with 24h TTL
  - Code #12: Token-bucket rate limiting via slowapi + Redis
  - Code #13: Global RFC 7807 Problem Details error handler
  - Code #14: pydantic-settings for startup validation of all env vars
  - Code #15: Strict type hints throughout
  - Code #25: Gunicorn/Uvicorn worker support via gunicorn.conf.py
  - Code #16: Prometheus-compatible /metrics endpoint (prometheus_fastapi_instrumentator)

Endpoints:
  GET  /api/local/search           — distance search
  GET  /api/local/status           — DB health + stats
  GET  /api/local/autocomplete     — system name autocomplete
  POST /api/search/galaxy          — galaxy-wide economy search
  POST /api/search/cluster         — multi-economy cluster search
  GET  /api/system/{id64}          — full system detail
  GET  /api/body/{body_id}         — body detail
  POST /api/systems/batch          — batch system lookup
  GET  /api/watchlist              — watchlist CRUD
  POST /api/watchlist/{id64}
  DELETE /api/watchlist/{id64}
  PATCH /api/watchlist/{id64}/alert
  GET  /api/systems/{id64}/note    — notes CRUD
  POST /api/systems/{id64}/note
  DELETE /api/systems/{id64}/note
  GET  /api/systems/notes
  GET  /api/cache/stats
  POST /api/cache/clear
  GET  /api/health
  GET  /api/status
  GET  /api/metrics                — Prometheus-style metrics
  GET  /api/events/live            — SSE live EDDN feed
  GET  /api/events/recent          — recent EDDN events
  POST /api/admin/rebuild-clusters — trigger cluster rebuild
  GET  /docs                       — Swagger UI (auto-generated from response models)
"""

import os
import sys
import time
import json
import logging
import asyncio
import subprocess
from datetime import datetime, timezone
from typing import Optional, Any, AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, Response, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

# ---------------------------------------------------------------------------
# Local search module
# ---------------------------------------------------------------------------
try:
    import local_search as _ls
    _LS_AVAILABLE = True
except ImportError:
    _ls = None  # type: ignore
    _LS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Code #14: pydantic-settings — validates all env vars at startup
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    database_url: str = 'postgresql://postgres:password@localhost:5432/postgres'
    redis_url: str = 'redis://redis:6379/0'
    log_level: str = 'INFO'
    redis_max_connections: int = 20
    ttl_search: int = 3600
    ttl_system: int = 86400
    ttl_status: int = 60
    ttl_autocomplete: int = 86400   # 24h for autocomplete (Code #11)
    ttl_cluster: int = 3600
    rate_limit_search: str = '30/minute'
    rate_limit_default: str = '120/minute'
    app_version: str = '3.0.0-hetzner'

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('ed_finder')

# ---------------------------------------------------------------------------
# Code #12: Rate limiter (token bucket via slowapi + Redis)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------
_pool:  Optional[asyncpg.Pool] = None
_redis: Optional[aioredis.Redis] = None
_metrics: dict[str, Any] = {
    'requests_total':  0,
    'cache_hits':      0,
    'cache_misses':    0,
    'db_queries':      0,
    'errors_total':    0,
    'startup_time':    time.time(),
}

# ---------------------------------------------------------------------------
# Background workers for long-running tasks
# ---------------------------------------------------------------------------
_active_jobs: dict[str, Any] = {}

def run_cluster_rebuild():
    """Run build_clusters.py as a subprocess and track status."""
    job_id = "cluster_rebuild"
    if _active_jobs.get(job_id, {}).get("status") == "running":
        log.warning("Cluster rebuild already in progress, skipping trigger.")
        return

    _active_jobs[job_id] = {
        "status": "running",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None,
        "exit_code": None,
        "error": None
    }

    try:
        # Resolve the compose project directory from env var (set in docker-compose.yml
        # via COMPOSE_PROJECT_DIR) or fall back to the standard install path.
        compose_dir = os.environ.get("COMPOSE_PROJECT_DIR", "/opt/ed-finder")
        cmd = [
            "docker", "compose",
            "--project-directory", compose_dir,
            "--profile", "import",
            "run", "--rm", "importer",
            "python3", "build_clusters.py", "--dirty-only", "--workers", "6"
        ]
        log.info("Triggering background cluster rebuild: %s", " ".join(cmd))
        
        # We use check=True to raise an error if the script fails
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        _active_jobs[job_id].update({
            "status": "completed",
            "end_time": datetime.now(timezone.utc).isoformat(),
            "exit_code": 0
        })
        log.info("Background cluster rebuild completed successfully.")
        
    except subprocess.CalledProcessError as e:
        _active_jobs[job_id].update({
            "status": "failed",
            "end_time": datetime.now(timezone.utc).isoformat(),
            "exit_code": e.returncode,
            "error": e.stderr or str(e)
        })
        log.error("Background cluster rebuild failed (exit %d): %s", e.returncode, e.stderr)
    except Exception as e:
        _active_jobs[job_id].update({
            "status": "failed",
            "end_time": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        })
        log.exception("Unexpected error during background cluster rebuild")

# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _redis
    log.info(f"ED Finder Hetzner backend v{settings.app_version} starting ...")
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=5,
        max_size=20,
        command_timeout=30,
        server_settings={'application_name': 'ed_finder_api'},
    )
    try:
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        await _redis.ping()
        log.info("Redis connected ✓ (pool max=%d)", settings.redis_max_connections)
    except Exception as e:
        log.warning(f"Redis unavailable ({e}) — running without cache")
        _redis = None

    log.info("PostgreSQL pool ready ✓")
    yield

    if _pool:   await _pool.close()
    if _redis:  await _redis.aclose()
    log.info("Shutdown complete")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title='ED Finder API',
    version=settings.app_version,
    description='Search 186M Elite Dangerous star systems by economy, body types, and distance.',
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc',
)

# Code #12: attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)
# Code #3: GZip compress all responses >= 1 KB
app.add_middleware(GZipMiddleware, minimum_size=1024)

# ---------------------------------------------------------------------------
# Static file serving — frontend (must be mounted AFTER all API routes)
# We defer mount to a startup event so the path resolves correctly.
# ---------------------------------------------------------------------------
import pathlib as _pl

_FRONTEND_DIR = _pl.Path(__file__).parent.parent / 'frontend'

# ---------------------------------------------------------------------------
# Code #13: Global RFC 7807 Problem Details error handler
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def problem_details_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'type':     f'https://httpstatuses.com/{exc.status_code}',
            'title':    exc.detail if isinstance(exc.detail, str) else 'Error',
            'status':   exc.status_code,
            'detail':   exc.detail,
            'instance': str(request.url),
        },
        headers=getattr(exc, 'headers', None),
    )

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    _metrics['errors_total'] += 1
    log.exception('Unhandled error on %s %s', request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={
            'type':   'https://httpstatuses.com/500',
            'title':  'Internal Server Error',
            'status': 500,
            'detail': str(exc),
        },
    )

# ---------------------------------------------------------------------------
# Code #9: Dependency injection for DB pool and Redis
# ---------------------------------------------------------------------------
async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise HTTPException(503, 'Database pool not initialised')
    return _pool

async def get_redis() -> Optional[aioredis.Redis]:
    return _redis

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
async def cache_get(key: str, redis: Optional[aioredis.Redis] = None) -> Optional[Any]:
    r = redis or _redis
    if not r: return None
    try:
        v = await r.get(key)
        if v:
            _metrics['cache_hits'] += 1
            return json.loads(v)
    except Exception:
        pass
    _metrics['cache_misses'] += 1
    return None

async def cache_set(key: str, value: Any, ttl: int, redis: Optional[aioredis.Redis] = None):
    r = redis or _redis
    if not r: return
    try:
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Code #10: Background task helpers (analytics off the critical path)
# ---------------------------------------------------------------------------
def _inc_metric(key: str) -> None:
    _metrics[key] = _metrics.get(key, 0) + 1

def _log_query(endpoint: str, duration_ms: float) -> None:
    if duration_ms > 2000:
        log.warning('Slow query on %s: %.0fms', endpoint, duration_ms)

# ---------------------------------------------------------------------------
# Pydantic response models (Code #8)
# ---------------------------------------------------------------------------
class CoordsModel(BaseModel):
    x: float
    y: float
    z: float

class RatingModel(BaseModel):
    score: Optional[float] = None
    scoreAgriculture: Optional[float] = None
    scoreRefinery: Optional[float] = None
    scoreIndustrial: Optional[float] = None
    scoreHightech: Optional[float] = None
    scoreMilitary: Optional[float] = None
    scoreTourism: Optional[float] = None
    economySuggestion: Optional[str] = None
    breakdown: Optional[dict] = None

class BodyModel(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    subtype: Optional[str] = None
    body_type: Optional[str] = None
    distance_from_star: Optional[float] = None
    is_landable: Optional[bool] = None
    is_terraformable: Optional[bool] = None
    is_earth_like: Optional[bool] = None
    is_water_world: Optional[bool] = None
    is_ammonia_world: Optional[bool] = None
    bio_signal_count: Optional[int] = None
    geo_signal_count: Optional[int] = None
    surface_temp: Optional[float] = None
    radius: Optional[float] = None
    mass: Optional[float] = None
    gravity: Optional[float] = None
    estimated_mapping_value: Optional[int] = None
    estimated_scan_value: Optional[int] = None
    is_main_star: Optional[bool] = None
    spectral_class: Optional[str] = None
    is_scoopable: Optional[bool] = None

class StationModel(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    station_type: Optional[str] = None
    distance_from_star: Optional[float] = None
    landing_pad_size: Optional[str] = None
    has_market: Optional[bool] = None
    has_shipyard: Optional[bool] = None
    has_outfitting: Optional[bool] = None

class SystemModel(BaseModel):
    id64: Optional[int] = None
    name: str = 'Unknown'
    coords: Optional[CoordsModel] = None
    distance: Optional[float] = None
    population: int = 0
    primaryEconomy: Optional[str] = None
    secondaryEconomy: Optional[str] = None
    security: Optional[str] = None
    allegiance: Optional[str] = None
    government: Optional[str] = None
    is_colonised: bool = False
    is_being_colonised: bool = False
    main_star_type: Optional[str] = None
    main_star_subtype: Optional[str] = None
    _rating: Optional[RatingModel] = None
    bodies: list[BodyModel] = []
    stations: list[StationModel] = []

class SearchResponse(BaseModel):
    results: list[dict]
    total: int
    count: int

class SystemDetailResponse(BaseModel):
    record: dict
    system: dict

class HealthResponse(BaseModel):
    status: str
    database: str
    version: str

class WatchlistAlert(BaseModel):
    min_score: Optional[int] = None
    economy: Optional[str] = None

class NoteBody(BaseModel):
    note: str

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class SearchFilters(BaseModel):
    distance:   Optional[dict] = None
    population: Optional[dict] = None
    economy:    Optional[str]  = None

class LocalSearchRequest(BaseModel):
    filters:            Optional[SearchFilters] = None
    reference_coords:   Optional[dict]          = None
    sort_by:            Optional[str]            = 'rating'
    size:               int                      = Field(default=50, le=500)
    from_:              int                      = Field(default=0, alias='from')
    body_filters:       Optional[dict]           = None
    require_bio:        Optional[bool]           = None
    require_geo:        Optional[bool]           = None
    require_terra:      Optional[bool]           = None
    star_types:         Optional[list[str]]      = None
    min_rating:         Optional[int]            = None
    galaxy_wide:        bool                     = False

    model_config = {'populate_by_name': True}

class GalaxySearchRequest(BaseModel):
    economy:    str  = 'any'
    min_score:  int  = Field(default=0, ge=0, le=100)
    limit:      int  = Field(default=100, le=500)
    offset:     int  = 0

class ClusterRequirement(BaseModel):
    economy:    str
    min_count:  int = Field(default=1, ge=1)
    min_score:  int = Field(default=40, ge=0, le=100)

class ClusterSearchRequest(BaseModel):
    requirements:      list[ClusterRequirement]
    limit:             int = Field(default=50, le=200)
    offset:            int = 0
    reference_coords:  Optional[dict] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sys_row_to_dict(r: Any) -> dict:
    """Convert asyncpg Record to a dict the frontend understands."""
    if r is None: return {}
    d = dict(r)
    d['id64']      = d.get('id64')
    d['name']      = d.get('name', 'Unknown')
    d['coords']    = {'x': d.get('x', 0), 'y': d.get('y', 0), 'z': d.get('z', 0)}
    d['distance']  = d.get('distance')
    d['population'] = d.get('population', 0)
    d['primaryEconomy']   = d.get('primary_economy', 'Unknown')
    d['secondaryEconomy'] = d.get('secondary_economy', 'None')
    d['security']    = d.get('security', 'Unknown')
    d['allegiance']  = d.get('allegiance', 'Unknown')
    d['government']  = d.get('government', 'Unknown')
    d['is_colonised'] = d.get('is_colonised', False)
    d['is_being_colonised'] = d.get('is_being_colonised', False)
    d['_rating'] = {
        'score':            d.get('score'),
        'scoreAgriculture': d.get('score_agriculture'),
        'scoreRefinery':    d.get('score_refinery'),
        'scoreIndustrial':  d.get('score_industrial'),
        'scoreHightech':    d.get('score_hightech'),
        'scoreMilitary':    d.get('score_military'),
        'scoreTourism':     d.get('score_tourism'),
        'economySuggestion': d.get('economy_suggestion'),
        'breakdown':        d.get('score_breakdown'),
    }
    d['bodies'] = d.get('bodies', [])
    return d

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
@app.middleware('http')
async def metrics_middleware(request: Request, call_next: Any) -> Response:
    _metrics['requests_total'] += 1
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    if duration_ms > 2000:
        log.warning('Slow request %s %s: %.0fms', request.method, request.url.path, duration_ms)
    return response

# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------
@app.get('/api/health', response_model=HealthResponse)
async def health(pool: asyncpg.Pool = Depends(get_pool)):
    try:
        async with pool.acquire() as conn:
            await conn.fetchval('SELECT 1')
        return HealthResponse(
            status='ok',
            database='connected',
            version=settings.app_version,
        )
    except Exception as e:
        raise HTTPException(503, detail=str(e))


@app.get('/api/status')
async def status(
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    cache_key = 'status:main'
    cached = await cache_get(cache_key, redis)
    if cached: return cached

    async with pool.acquire() as conn:
        sys_count  = await conn.fetchval('SELECT COUNT(*) FROM systems')
        body_count = await conn.fetchval('SELECT COUNT(*) FROM bodies')
        rated      = await conn.fetchval('SELECT COUNT(*) FROM ratings WHERE score IS NOT NULL')
        clustered  = await conn.fetchval('SELECT COUNT(*) FROM cluster_summary WHERE coverage_score IS NOT NULL')
        meta_rows  = await conn.fetch("SELECT key, value FROM app_meta")
        meta = {r['key']: r['value'] for r in meta_rows}

    result = {
        'available':            True,
        'systems_count':        sys_count,
        'body_count':           body_count,
        'rated_count':          rated,
        'clustered_count':      clustered,
        'import_complete':      meta.get('import_complete') == 'true',
        'ratings_built':        meta.get('ratings_built')   == 'true',
        'grid_built':           meta.get('grid_built')      == 'true',
        'clusters_built':       meta.get('clusters_built')  == 'true',
        'eddn_enabled':         meta.get('eddn_enabled')    == 'true',
        'last_nightly_update':  meta.get('last_nightly_update', 'never'),
        'schema_version':       meta.get('schema_version', '1.0'),
        'max_search_radius_ly': 500,
        'has_body_data':        body_count > 0,
        'version':              settings.app_version,
    }
    await cache_set(cache_key, result, settings.ttl_status, redis)
    return result


@app.get('/api/local/status')
async def local_status(
    pool: asyncpg.Pool = Depends(get_pool),
):
    if _LS_AVAILABLE:
        try:
            return await _ls.local_db_status(pool)
        except Exception as exc:
            log.warning('local_db_status error: %s', exc)
    return await status(pool)


@app.get('/api/metrics', response_class=PlainTextResponse, include_in_schema=False)
async def metrics():
    uptime = time.time() - _metrics['startup_time']
    lines = [
        '# HELP ed_finder_requests_total Total HTTP requests',
        '# TYPE ed_finder_requests_total counter',
        f'ed_finder_requests_total {_metrics["requests_total"]}',
        '# HELP ed_finder_cache_hits_total Redis cache hits',
        '# TYPE ed_finder_cache_hits_total counter',
        f'ed_finder_cache_hits_total {_metrics["cache_hits"]}',
        '# HELP ed_finder_cache_misses_total Redis cache misses',
        '# TYPE ed_finder_cache_misses_total counter',
        f'ed_finder_cache_misses_total {_metrics["cache_misses"]}',
        '# HELP ed_finder_errors_total Total unhandled errors',
        '# TYPE ed_finder_errors_total counter',
        f'ed_finder_errors_total {_metrics["errors_total"]}',
        '# HELP ed_finder_db_queries_total Total DB queries dispatched',
        '# TYPE ed_finder_db_queries_total counter',
        f'ed_finder_db_queries_total {_metrics["db_queries"]}',
        '# HELP ed_finder_uptime_seconds Seconds since startup',
        '# TYPE ed_finder_uptime_seconds gauge',
        f'ed_finder_uptime_seconds {uptime:.0f}',
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Autocomplete — Code #11: Redis cache with 24h TTL
# ---------------------------------------------------------------------------
@app.get('/api/local/autocomplete')
@limiter.limit('60/minute')
async def autocomplete(
    request: Request,
    q: str = '',
    limit: int = 10,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    if len(q) < 2:
        return {'results': []}

    # Code #11: 24h TTL for autocomplete — trigram searches are expensive
    cache_key = f'ac:{q.lower()[:20]}'
    cached = await cache_get(cache_key, redis)
    if cached: return cached

    if _LS_AVAILABLE:
        try:
            results = await _ls.local_db_autocomplete(q, pool)
            result = {'results': results, 'source': 'local_db'}
            await cache_set(cache_key, result, settings.ttl_autocomplete, redis)
            return result
        except Exception as exc:
            log.warning('local_db_autocomplete error: %s', exc)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id64, name, x, y, z, population, primary_economy
            FROM systems
            WHERE name ILIKE $1
            ORDER BY
                CASE WHEN lower(name) = lower($2) THEN 0 ELSE 1 END,
                population DESC,
                name
            LIMIT $3
        """, f'{q}%', q, limit)

    result = {
        'results': [
            {
                'id64': r['id64'], 'name': r['name'],
                'x': r['x'], 'y': r['y'], 'z': r['z'],
                'population': r['population'],
                'primaryEconomy': r['primary_economy'],
            }
            for r in rows
        ]
    }
    await cache_set(cache_key, result, settings.ttl_autocomplete, redis)
    return result


# ---------------------------------------------------------------------------
# Local search
# ---------------------------------------------------------------------------
@app.post('/api/local/search', response_model=SearchResponse)
@limiter.limit(settings.rate_limit_search)
async def local_search_endpoint(
    request: Request,
    req: LocalSearchRequest,
    background_tasks: BackgroundTasks,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    # Code #10: increment metric in background — off critical path
    background_tasks.add_task(_inc_metric, 'db_queries')
    t0 = time.time()

    if _LS_AVAILABLE:
        try:
            body_dict = {
                'reference_coords': req.reference_coords or {'x': 0, 'y': 0, 'z': 0},
                'filters': {
                    'distance':   (req.filters or SearchFilters()).distance or {},
                    'population': (req.filters or SearchFilters()).population or {},
                    'economy':    (req.filters or SearchFilters()).economy or 'any',
                },
                'body_filters':   req.body_filters or {},
                'require_bio':    req.require_bio,
                'require_geo':    req.require_geo,
                'require_terra':  req.require_terra,
                'star_types':     req.star_types or [],
                'min_rating':     req.min_rating or 0,
                'economy':        (req.filters or SearchFilters()).economy or 'any',
                'size':           req.size,
                'from':           req.from_,
                'sort_by':        req.sort_by or 'rating',
                'galaxy_wide':    req.galaxy_wide,
            }
            result = await _ls.local_db_search(body_dict, pool)
            background_tasks.add_task(_log_query, 'local_search', (time.time() - t0) * 1000)
            return result
        except Exception as exc:
            log.warning('local_search delegation error: %s — falling back to inline', exc)

    # Fallback inline query
    filters     = req.filters or SearchFilters()
    ref         = req.reference_coords or {'x': 0, 'y': 0, 'z': 0}
    ref_x       = float(ref.get('x', 0))
    ref_y       = float(ref.get('y', 0))
    ref_z       = float(ref.get('z', 0))
    sort_by     = req.sort_by or 'rating'
    size        = min(req.size, 500)
    offset      = req.from_
    galaxy_wide = req.galaxy_wide

    dist_filter = filters.distance or {}
    min_dist    = float(dist_filter.get('min', 0))
    max_dist    = float(dist_filter.get('max', 500))

    pop_filter  = filters.population or {}
    pop_zero    = pop_filter.get('comparison') in ('equal', '=') and \
                  int(pop_filter.get('value', -1)) == 0

    economy     = (filters.economy or 'any').strip()
    min_rating  = req.min_rating or 0

    cache_key = f'search:{ref_x:.1f},{ref_y:.1f},{ref_z:.1f}:{min_dist}-{max_dist}:{pop_zero}:{economy}:{sort_by}:{size}:{offset}:{galaxy_wide}:{min_rating}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    params: list[Any] = []
    where  = ['r.score IS NOT NULL']
    param_n = 1

    if pop_zero:
        where.append('s.population = 0')

    if economy and economy.lower() not in ('any', 'none', ''):
        params.append(economy)
        where.append(f's.primary_economy = ${param_n}::economy_type')
        param_n += 1

    if min_rating > 0:
        params.append(min_rating)
        where.append(f'r.score >= ${param_n}')
        param_n += 1

    if req.body_filters:
        bf = req.body_filters
        for col, key in [('r.elw_count', 'elw'), ('r.ammonia_count', 'ammonia'),
                         ('r.gas_giant_count', 'gasGiant'), ('r.ww_count', 'ww'),
                         ('r.neutron_count', 'neutron')]:
            val = bf.get(key, {}).get('min', 0)
            if val > 0:
                params.append(val)
                where.append(f'{col} >= ${param_n}')
                param_n += 1

    if req.require_bio:   where.append('r.bio_signal_total > 0')
    if req.require_geo:   where.append('r.geo_signal_total > 0')
    if req.require_terra: where.append('r.terraformable_count > 0')

    dist_expr = f'distance_ly(s.x, s.y, s.z, {ref_x}, {ref_y}, {ref_z})'
    if not galaxy_wide:
        where.append(f'in_bounding_box(s.x, s.y, s.z, {ref_x}, {ref_y}, {ref_z}, {max_dist})')
        where.append(f'{dist_expr} BETWEEN {min_dist} AND {max_dist}')

    where_clause = ' AND '.join(where)
    order = 'r.score DESC NULLS LAST' if sort_by == 'rating' else f'{dist_expr} ASC'

    params.extend([size, offset])
    limit_n  = param_n
    offset_n = param_n + 1

    query = f"""
        SELECT
            s.id64, s.name, s.x, s.y, s.z,
            {dist_expr} AS distance,
            s.primary_economy, s.secondary_economy,
            s.population, s.is_colonised, s.is_being_colonised,
            s.security, s.allegiance, s.government,
            s.main_star_type, s.main_star_subtype,
            r.score, r.score_agriculture, r.score_refinery,
            r.score_industrial, r.score_hightech,
            r.score_military, r.score_tourism,
            r.economy_suggestion,
            r.elw_count, r.ww_count, r.ammonia_count,
            r.gas_giant_count, r.landable_count, r.terraformable_count,
            r.bio_signal_total, r.geo_signal_total,
            r.neutron_count, r.black_hole_count, r.white_dwarf_count,
            r.score_breakdown
        FROM systems s
        JOIN ratings r ON r.system_id64 = s.id64
        WHERE {where_clause}
        ORDER BY {order}
        LIMIT ${limit_n} OFFSET ${offset_n}
    """

    count_query = f"""
        SELECT COUNT(*)
        FROM systems s
        JOIN ratings r ON r.system_id64 = s.id64
        WHERE {where_clause}
    """

    async with pool.acquire() as conn:
        rows  = await conn.fetch(query, *params)
        total = await conn.fetchval(count_query, *params[:-2])

    results = []
    for r in rows:
        d = dict(r)
        d['coords'] = {'x': d['x'], 'y': d['y'], 'z': d['z']}
        d['primaryEconomy']   = d.pop('primary_economy', 'Unknown')
        d['secondaryEconomy'] = d.pop('secondary_economy', 'None')
        d['_rating'] = {
            'score':            d.pop('score', None),
            'scoreAgriculture': d.pop('score_agriculture', None),
            'scoreRefinery':    d.pop('score_refinery', None),
            'scoreIndustrial':  d.pop('score_industrial', None),
            'scoreHightech':    d.pop('score_hightech', None),
            'scoreMilitary':    d.pop('score_military', None),
            'scoreTourism':     d.pop('score_tourism', None),
            'economySuggestion': d.pop('economy_suggestion', None),
            'breakdown':        d.pop('score_breakdown', None),
        }
        d['bodies'] = []
        results.append(d)

    response = {'results': results, 'total': total, 'count': len(results)}
    await cache_set(cache_key, response, settings.ttl_search, redis)
    background_tasks.add_task(_log_query, 'local_search_fallback', (time.time() - t0) * 1000)
    return response


# ---------------------------------------------------------------------------
# Galaxy search
# ---------------------------------------------------------------------------
@app.post('/api/search/galaxy')
@limiter.limit(settings.rate_limit_search)
async def galaxy_search(
    request: Request,
    req: GalaxySearchRequest,
    background_tasks: BackgroundTasks,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    background_tasks.add_task(_inc_metric, 'db_queries')

    economy   = req.economy.strip()
    min_score = req.min_score
    limit     = min(req.limit, 500)

    if _LS_AVAILABLE:
        try:
            body_dict = {
                'economy':           economy,
                'min_score':         min_score,
                'limit':             limit,
                'include_colonised': False,
            }
            return await _ls.local_db_galaxy_search(body_dict, pool)
        except Exception as exc:
            log.warning('galaxy_search delegation error: %s — falling back to inline', exc)

    offset    = req.offset
    cache_key = f'galaxy:{economy}:{min_score}:{limit}:{offset}'
    cached = await cache_get(cache_key, redis)
    if cached: return cached

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                id64, name, x, y, z,
                primary_economy, secondary_economy,
                population, score, economy_score,
                elw_count, ammonia_count, gas_giant_count,
                bio_signal_total, score_breakdown
            FROM search_galaxy_economy($1, $2, $3, $4)
        """, economy if economy.lower() != 'any' else 'HighTech',
            min_score, limit, offset)

        _eco_col = {
            'agriculture': 'score_agriculture', 'refinery': 'score_refinery',
            'industrial': 'score_industrial', 'hightech': 'score_hightech',
            'high tech': 'score_hightech', 'military': 'score_military',
            'tourism': 'score_tourism',
        }.get(economy.lower(), 'score')
        total = await conn.fetchval(f"""
            SELECT COUNT(*)
            FROM ratings r
            JOIN systems s ON s.id64 = r.system_id64
            WHERE s.population = 0
              AND r.{_eco_col} IS NOT NULL
              AND r.{_eco_col} >= $1
        """, min_score)

    results = []
    for r in rows:
        d = dict(r)
        d['coords'] = {'x': d['x'], 'y': d['y'], 'z': d['z']}
        d['primaryEconomy'] = d.pop('primary_economy')
        d['_rating'] = {
            'score':         d.pop('score', None),
            'economyScore':  d.pop('economy_score', None),
            'breakdown':     d.pop('score_breakdown', None),
        }
        results.append(d)

    response = {'results': results, 'total': total, 'economy': economy}
    await cache_set(cache_key, response, settings.ttl_search, redis)
    return response


# ---------------------------------------------------------------------------
# Cluster search
# ---------------------------------------------------------------------------
@app.post('/api/search/cluster')
@limiter.limit(settings.rate_limit_search)
async def cluster_search(
    request: Request,
    req: ClusterSearchRequest,
    background_tasks: BackgroundTasks,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    background_tasks.add_task(_inc_metric, 'db_queries')

    if not req.requirements:
        raise HTTPException(400, 'At least one economy requirement must be specified')
    if len(req.requirements) > 6:
        raise HTTPException(400, 'Maximum 6 economy requirements')

    if _LS_AVAILABLE:
        try:
            body_dict = {
                'requirements':    [r.model_dump() for r in req.requirements],
                'limit':           req.limit,
                'reference_coords': req.reference_coords,
            }
            return await _ls.local_db_cluster_search(body_dict, pool)
        except Exception as exc:
            log.warning('cluster_search delegation error: %s — falling back to inline', exc)

    reqs_json = json.dumps([r.model_dump() for r in req.requirements])
    cache_key = f'cluster:{reqs_json}:{req.limit}:{req.offset}'
    cached = await cache_get(cache_key, redis)
    if cached: return cached

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM search_cluster($1::jsonb, $2, $3)
        """, reqs_json, req.limit, req.offset)

        parts = []
        for r in req.requirements:
            col = {
                'agriculture': 'agriculture_count',
                'refinery':    'refinery_count',
                'industrial':  'industrial_count',
                'hightech':    'hightech_count',
                'high tech':   'hightech_count',
                'military':    'military_count',
                'tourism':     'tourism_count',
            }.get(r.economy.lower())
            if col:
                parts.append(f'{col} >= {r.min_count}')
            else:
                log.warning('cluster_search: unknown economy name %r — skipping from total count', r.economy)
        where = ' AND '.join(parts) if parts else 'TRUE'
        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM cluster_summary
            WHERE {where} AND coverage_score IS NOT NULL
        """)

    results = []
    for r in rows:
        d = dict(r)
        d['coords'] = {
            'x': d.pop('anchor_x'),
            'y': d.pop('anchor_y'),
            'z': d.pop('anchor_z'),
        }
        d['id64']       = d.pop('anchor_id64')
        d['name']       = d.pop('anchor_name')
        d['population'] = d.pop('anchor_population')
        results.append(d)

    response = {
        'results':      results,
        'total':        total,
        'requirements': [r.model_dump() for r in req.requirements],
    }
    await cache_set(cache_key, response, settings.ttl_cluster, redis)
    return response


# ---------------------------------------------------------------------------
# System detail
# ---------------------------------------------------------------------------
@app.get('/api/system/{id64}', response_model=SystemDetailResponse)
async def get_system(
    id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    cache_key = f'sys:{id64}'
    cached = await cache_get(cache_key, redis)
    if cached: return cached

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT s.*,
                r.score, r.score_agriculture, r.score_refinery,
                r.score_industrial, r.score_hightech,
                r.score_military, r.score_tourism,
                r.economy_suggestion, r.elw_count, r.ww_count,
                r.ammonia_count, r.gas_giant_count, r.landable_count,
                r.terraformable_count, r.bio_signal_total, r.geo_signal_total,
                r.neutron_count, r.black_hole_count, r.white_dwarf_count,
                r.score_breakdown
            FROM systems s
            LEFT JOIN ratings r ON r.system_id64 = s.id64
            WHERE s.id64 = $1
        """, id64)

        if not row:
            raise HTTPException(404, f'System {id64} not found')

        bodies = await conn.fetch("""
            SELECT id, name, subtype, body_type,
                   distance_from_star, is_landable, is_terraformable,
                   is_earth_like, is_water_world, is_ammonia_world,
                   bio_signal_count, geo_signal_count,
                   surface_temp, radius, mass, gravity,
                   estimated_mapping_value, estimated_scan_value,
                   is_main_star, spectral_class, is_scoopable
            FROM bodies
            WHERE system_id64 = $1
            ORDER BY distance_from_star ASC NULLS LAST
        """, id64)

        stations = await conn.fetch("""
            SELECT id, name, station_type, distance_from_star,
                   landing_pad_size, has_market, has_shipyard, has_outfitting
            FROM stations WHERE system_id64 = $1
        """, id64)

    d = sys_row_to_dict(row)
    d['bodies']   = [dict(b) for b in bodies]
    d['stations'] = [dict(s) for s in stations]

    # Exploration value estimator (Data Enrichment #2)
    total_scan  = sum(b.get('estimated_scan_value',    0) or 0 for b in d['bodies'])
    total_map   = sum(b.get('estimated_mapping_value', 0) or 0 for b in d['bodies'])
    d['exploration_value'] = {
        'total_scan_value':    total_scan,
        'total_mapping_value': total_map,
        'combined_value':      total_scan + total_map,
    }

    result = {'record': d, 'system': d}
    await cache_set(cache_key, result, settings.ttl_system, redis)
    return result


@app.get('/api/local/system/{id64}')
async def local_get_system(
    id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    return await get_system(id64, pool, redis)


# ---------------------------------------------------------------------------
# Body detail
# ---------------------------------------------------------------------------
@app.get('/api/body/{body_id}')
async def get_body(
    body_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    cache_key = f'body:{body_id}'
    cached = await cache_get(cache_key, redis)
    if cached: return cached

    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM bodies WHERE id = $1', body_id)
        if not row:
            raise HTTPException(404, f'Body {body_id} not found')

    result = dict(row)
    await cache_set(cache_key, result, settings.ttl_system, redis)
    return result


# ---------------------------------------------------------------------------
# Batch system lookup
# ---------------------------------------------------------------------------
@app.post('/api/systems/batch')
async def batch_systems(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    body = await request.json()
    id64s = body.get('id64s', [])
    if not id64s or len(id64s) > 500:
        raise HTTPException(400, 'Provide 1-500 id64s')

    result: dict[str, Any] = {}
    missing: list[int] = []
    for id64 in id64s:
        cached = await cache_get(f'sys:{id64}', redis)
        if cached:
            result[str(id64)] = cached.get('record') or cached
        else:
            missing.append(id64)

    if missing:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.*,
                    r.score, r.score_breakdown, r.economy_suggestion,
                    r.elw_count, r.ww_count, r.ammonia_count,
                    r.gas_giant_count, r.landable_count,
                    r.bio_signal_total, r.geo_signal_total,
                    r.neutron_count, r.black_hole_count
                FROM systems s
                LEFT JOIN ratings r ON r.system_id64 = s.id64
                WHERE s.id64 = ANY($1::bigint[])
            """, missing)

            bodies_rows = await conn.fetch("""
                SELECT system_id64, id, name, subtype,
                       distance_from_star, is_landable, is_terraformable,
                       is_earth_like, is_water_world, is_ammonia_world,
                       bio_signal_count, geo_signal_count,
                       estimated_mapping_value, estimated_scan_value
                FROM bodies
                WHERE system_id64 = ANY($1::bigint[])
                ORDER BY system_id64, distance_from_star ASC NULLS LAST
            """, missing)

        bodies_by_system: dict[int, list] = {}
        for b in bodies_rows:
            bid = b['system_id64']
            bodies_by_system.setdefault(bid, []).append(dict(b))

        for row in rows:
            d = sys_row_to_dict(row)
            d['bodies'] = bodies_by_system.get(d['id64'], [])
            result[str(d['id64'])] = d
            await cache_set(f'sys:{d["id64"]}', {'record': d}, settings.ttl_system, redis)

    return {'systems': result}


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------
@app.get('/api/watchlist')
async def get_watchlist(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.*,
                r.score, r.economy_suggestion
            FROM watchlist w
            LEFT JOIN ratings r ON r.system_id64 = w.system_id64
            ORDER BY w.added_at DESC
        """)
    return {'watchlist': [dict(r) for r in rows]}


@app.post('/api/watchlist/{id64}')
async def add_watchlist(
    id64: int,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        sys_row = await conn.fetchrow(
            'SELECT name, x, y, z, population, is_colonised FROM systems WHERE id64 = $1',
            id64
        )
        if not sys_row:
            raise HTTPException(404, f'System {id64} not found')
        await conn.execute("""
            INSERT INTO watchlist (system_id64, name, x, y, z, population, is_colonised)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (system_id64) DO NOTHING
        """, id64, sys_row['name'], sys_row['x'], sys_row['y'], sys_row['z'],
            sys_row['population'], sys_row['is_colonised'])
    return {'ok': True}


@app.delete('/api/watchlist/{id64}')
async def remove_watchlist(id64: int, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM watchlist WHERE system_id64 = $1', id64)
    return {'ok': True}


@app.patch('/api/watchlist/{id64}/alert')
async def update_alert(
    id64: int,
    alert: WatchlistAlert,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE watchlist
            SET alert_min_score = $1, alert_economy = $2
            WHERE system_id64 = $3
        """, alert.min_score, alert.economy, id64)
    return {'ok': True}


@app.get('/api/watchlist/changes')
async def watchlist_changes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM watchlist_changelog
            ORDER BY detected_at DESC LIMIT 100
        """)
    return {'changes': [dict(r) for r in rows]}


@app.get('/api/watchlist/changelog')
async def watchlist_changelog(pool: asyncpg.Pool = Depends(get_pool)):
    return await watchlist_changes(pool)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
@app.get('/api/systems/{id64}/note')
async def get_note(id64: int, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT note, updated_at FROM system_notes WHERE system_id64 = $1', id64
        )
    return {'note': row['note'] if row else '', 'updated_at': str(row['updated_at']) if row else None}


@app.post('/api/systems/{id64}/note')
async def save_note(id64: int, body: NoteBody, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO system_notes (system_id64, note, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (system_id64) DO UPDATE SET note = $2, updated_at = NOW()
        """, id64, body.note)
    return {'ok': True}


@app.delete('/api/systems/{id64}/note')
async def delete_note(id64: int, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM system_notes WHERE system_id64 = $1', id64)
    return {'ok': True}


@app.get('/api/systems/notes')
async def all_notes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT n.system_id64, s.name, n.note, n.updated_at
            FROM system_notes n
            JOIN systems s ON s.id64 = n.system_id64
            ORDER BY n.updated_at DESC
        """)
    return {'notes': [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------
@app.get('/api/cache/stats')
async def cache_stats(
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    stats: dict[str, Any] = {
        'cache_hits':   _metrics['cache_hits'],
        'cache_misses': _metrics['cache_misses'],
    }
    if redis:
        try:
            info = await redis.info('stats')
            stats['redis_hits']      = info.get('keyspace_hits', 0)
            stats['redis_misses']    = info.get('keyspace_misses', 0)
            stats['redis_memory_mb'] = round(int((await redis.info('memory')).get('used_memory', 0)) / 1e6, 1)
        except Exception:
            pass
    async with pool.acquire() as conn:
        stats['db_cache_rows'] = await conn.fetchval(
            "SELECT COUNT(*) FROM api_cache WHERE expires_at > NOW()"
        )
    return stats


@app.post('/api/cache/clear')
async def cache_clear(
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    if redis:
        try: await redis.flushdb()
        except Exception: pass
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM api_cache WHERE expires_at <= NOW()")
    return {'ok': True, 'message': 'Cache cleared'}


# ---------------------------------------------------------------------------
# Live EDDN events SSE endpoint
# ---------------------------------------------------------------------------
_sse_clients: list[asyncio.Queue] = []

@app.get('/api/events/live')
async def live_events(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_clients.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = queue.get_nowait()
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                except asyncio.QueueEmpty:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(25)
        finally:
            try:
                _sse_clients.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


async def _broadcast_eddn_event(event: dict) -> None:
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _sse_clients.remove(q)
        except ValueError:
            pass


@app.get('/api/events/recent')
async def recent_events(
    limit: int = 50,
    pool: asyncpg.Pool = Depends(get_pool),
):
    limit = min(limit, 200)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT system_name, system_id64, event_type, received_at
            FROM eddn_log
            ORDER BY received_at DESC
            LIMIT $1
        """, limit)
    return {
        'events': [
            {
                'system_name': r['system_name'],
                'id64':        r['system_id64'],
                'type':        r['event_type'],
                'timestamp':   r['received_at'].isoformat() if r['received_at'] else None,
            }
            for r in rows
        ],
        'jobs': _active_jobs
    }


@app.post('/api/admin/rebuild-clusters')
@limiter.limit('1/minute')
async def trigger_rebuild_clusters(request: Request, background_tasks: BackgroundTasks):
    """Trigger a background cluster rebuild (dirty anchors only)."""
    job_id = "cluster_rebuild"
    if _active_jobs.get(job_id, {}).get("status") == "running":
        return JSONResponse(
            status_code=409,
            content={"message": "A cluster rebuild is already in progress.", "job": _active_jobs[job_id]}
        )
    
    background_tasks.add_task(run_cluster_rebuild)
    return {"message": "Cluster rebuild triggered in background.", "job_id": job_id}


# ---------------------------------------------------------------------------
# Catch-all: serve index.html for any unmatched path (SPA fallback)
# ---------------------------------------------------------------------------
from fastapi.responses import FileResponse as _FileResponse

@app.get('/{full_path:path}', include_in_schema=False)
async def spa_fallback(full_path: str):
    # Try exact file first
    candidate = _FRONTEND_DIR / full_path
    if candidate.is_file():
        return _FileResponse(str(candidate))
    # Fall back to index.html for SPA routing
    return _FileResponse(str(_FRONTEND_DIR / 'index.html'))


# Mount static assets directory (JS, CSS, images, etc.)
if _FRONTEND_DIR.is_dir():
    app.mount('/static', StaticFiles(directory=str(_FRONTEND_DIR)), name='static')


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run(app, host='0.0.0.0', port=port, log_level=settings.log_level.lower())
