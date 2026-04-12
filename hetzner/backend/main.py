#!/usr/bin/env python3
"""
ED Finder — Hetzner Backend
Version: 1.0 (PostgreSQL / asyncpg edition)

All existing Pi endpoints preserved + new endpoints:
  GET  /api/local/search           — standard distance search (Postgres)
  GET  /api/local/status           — DB health + stats
  GET  /api/local/autocomplete     — system name autocomplete
  POST /api/search/galaxy          — galaxy-wide economy search (no distance limit)
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
"""

import os
import sys
import time
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Any
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN      = os.getenv('DATABASE_URL',  'postgresql://edfinder:edfinder@postgres:5432/edfinder')
REDIS_URL   = os.getenv('REDIS_URL',     'redis://redis:6379/0')
LOG_LEVEL   = os.getenv('LOG_LEVEL',     'INFO')
APP_VERSION = '1.0.0-hetzner'

# Cache TTLs (seconds)
TTL_SEARCH      = int(os.getenv('TTL_SEARCH',  '3600'))    # 1 hour
TTL_SYSTEM      = int(os.getenv('TTL_SYSTEM',  '86400'))   # 24 hours
TTL_STATUS      = int(os.getenv('TTL_STATUS',  '60'))      # 1 minute
TTL_AUTOCOMPLETE = int(os.getenv('TTL_AC',     '3600'))    # 1 hour
TTL_CLUSTER     = int(os.getenv('TTL_CLUSTER', '3600'))    # 1 hour

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('ed_finder')

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------
_pool:  Optional[asyncpg.Pool] = None
_redis: Optional[aioredis.Redis] = None
_metrics = {
    'requests_total':  0,
    'cache_hits':      0,
    'cache_misses':    0,
    'db_queries':      0,
    'errors_total':    0,
    'startup_time':    time.time(),
}

# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _redis
    log.info(f"ED Finder Hetzner backend v{APP_VERSION} starting ...")
    _pool = await asyncpg.create_pool(
        dsn=DB_DSN,
        min_size=5,
        max_size=20,
        command_timeout=30,
        server_settings={'application_name': 'ed_finder_api'},
    )
    try:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        await _redis.ping()
        log.info("Redis connected ✓")
    except Exception as e:
        log.warning(f"Redis unavailable ({e}) — running without cache")
        _redis = None

    log.info("PostgreSQL pool ready ✓")
    yield

    if _pool:   await _pool.close()
    if _redis:  await _redis.aclose()
    log.info("Shutdown complete")

app = FastAPI(
    title='ED Finder API',
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def cache_get(key: str) -> Optional[Any]:
    if not _redis: return None
    try:
        v = await _redis.get(key)
        if v:
            _metrics['cache_hits'] += 1
            return json.loads(v)
    except Exception: pass
    _metrics['cache_misses'] += 1
    return None

async def cache_set(key: str, value: Any, ttl: int):
    if not _redis: return
    try:
        await _redis.setex(key, ttl, json.dumps(value, default=str))
    except Exception: pass

def sys_row_to_dict(r) -> dict:
    """Convert asyncpg Record to a dict the frontend understands."""
    if r is None: return {}
    d = dict(r)
    # Normalise field names to match existing frontend expectations
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
    # Ratings
    d['_rating']    = {
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
# Pydantic models
# ---------------------------------------------------------------------------
class SearchFilters(BaseModel):
    distance:   Optional[dict] = None   # {min: 0, max: 200}
    population: Optional[dict] = None   # {value: 0, comparison: 'equal'}
    economy:    Optional[str]  = None

class LocalSearchRequest(BaseModel):
    filters:            Optional[SearchFilters] = None
    reference_coords:   Optional[dict]          = None   # {x, y, z}
    sort_by:            Optional[str]            = 'rating'
    size:               int                      = Field(default=50, le=500)
    from_:              int                      = Field(default=0, alias='from')
    body_filters:       Optional[dict]           = None
    require_bio:        Optional[bool]           = None
    require_geo:        Optional[bool]           = None
    require_terra:      Optional[bool]           = None
    min_rating:         Optional[int]            = None
    galaxy_wide:        bool                     = False   # NEW: skip distance filter

    class Config:
        populate_by_name = True

class GalaxySearchRequest(BaseModel):
    economy:    str                = 'any'
    min_score:  int                = Field(default=0, ge=0, le=100)
    limit:      int                = Field(default=100, le=500)
    offset:     int                = 0

class ClusterRequirement(BaseModel):
    economy:    str
    min_count:  int = Field(default=1, ge=1)
    min_score:  int = Field(default=40, ge=0, le=100)

class ClusterSearchRequest(BaseModel):
    requirements:   list[ClusterRequirement]
    limit:          int = Field(default=50, le=200)
    offset:         int = 0

class WatchlistAlert(BaseModel):
    min_score:  Optional[int] = None
    economy:    Optional[str] = None

class NoteBody(BaseModel):
    note: str

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
@app.middleware('http')
async def metrics_middleware(request: Request, call_next):
    _metrics['requests_total'] += 1
    start = time.time()
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        _metrics['errors_total'] += 1
        raise

# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------
@app.get('/api/health')
async def health():
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval('SELECT 1')
        return {'status': 'ok', 'db': 'connected', 'version': APP_VERSION}
    except Exception as e:
        raise HTTPException(503, detail=str(e))


@app.get('/api/status')
async def status():
    cache_key = 'status:main'
    cached = await cache_get(cache_key)
    if cached: return cached

    async with _pool.acquire() as conn:
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
        'version':              APP_VERSION,
    }
    await cache_set(cache_key, result, TTL_STATUS)
    return result


@app.get('/api/local/status')
async def local_status():
    """Alias of /api/status — compatibility with Pi frontend."""
    return await status()


@app.get('/api/metrics', response_class=PlainTextResponse, include_in_schema=False)
async def metrics():
    uptime = time.time() - _metrics['startup_time']
    lines = [
        f'# ED Finder Hetzner Metrics',
        f'ed_finder_requests_total {_metrics["requests_total"]}',
        f'ed_finder_cache_hits_total {_metrics["cache_hits"]}',
        f'ed_finder_cache_misses_total {_metrics["cache_misses"]}',
        f'ed_finder_errors_total {_metrics["errors_total"]}',
        f'ed_finder_uptime_seconds {uptime:.0f}',
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------
@app.get('/api/local/autocomplete')
async def autocomplete(q: str = '', limit: int = 10):
    if len(q) < 2:
        return {'results': []}

    cache_key = f'ac:{q.lower()[:20]}'
    cached = await cache_get(cache_key)
    if cached: return cached

    async with _pool.acquire() as conn:
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
    await cache_set(cache_key, result, TTL_AUTOCOMPLETE)
    return result


# ---------------------------------------------------------------------------
# Standard local search (existing Pi endpoint, rewritten for Postgres)
# ---------------------------------------------------------------------------
@app.post('/api/local/search')
async def local_search(req: LocalSearchRequest):
    _metrics['db_queries'] += 1

    filters     = req.filters or SearchFilters()
    ref         = req.reference_coords or {'x': 0, 'y': 0, 'z': 0}
    ref_x       = float(ref.get('x', 0))
    ref_y       = float(ref.get('y', 0))
    ref_z       = float(ref.get('z', 0))
    sort_by     = req.sort_by or 'rating'
    size        = min(req.size, 500)
    offset      = req.from_
    galaxy_wide = req.galaxy_wide

    # Distance filter
    dist_filter = filters.distance or {}
    min_dist    = float(dist_filter.get('min', 0))
    max_dist    = float(dist_filter.get('max', 500))

    # Population filter
    pop_filter  = filters.population or {}
    pop_zero    = pop_filter.get('comparison') in ('equal', '=') and \
                  int(pop_filter.get('value', -1)) == 0

    # Economy filter
    economy     = (filters.economy or 'any').strip()

    # Rating filter
    min_rating  = req.min_rating or 0

    # Cache key
    cache_key = f'search:{ref_x:.1f},{ref_y:.1f},{ref_z:.1f}:{min_dist}-{max_dist}:{pop_zero}:{economy}:{sort_by}:{size}:{offset}:{galaxy_wide}:{min_rating}'
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Build query
    params = []
    where  = ['r.score IS NOT NULL']
    param_n = 1

    if pop_zero:
        where.append(f's.population = 0')

    if economy and economy.lower() not in ('any', 'none', ''):
        params.append(economy)
        where.append(f's.primary_economy = ${param_n}::economy_type')
        param_n += 1

    if min_rating > 0:
        params.append(min_rating)
        where.append(f'r.score >= ${param_n}')
        param_n += 1

    # Body filters
    if req.body_filters:
        bf = req.body_filters
        if bf.get('elw',     {}).get('min', 0) > 0:
            params.append(bf['elw']['min'])
            where.append(f'r.elw_count >= ${param_n}'); param_n += 1
        if bf.get('ammonia', {}).get('min', 0) > 0:
            params.append(bf['ammonia']['min'])
            where.append(f'r.ammonia_count >= ${param_n}'); param_n += 1
        if bf.get('gasGiant',{}).get('min', 0) > 0:
            params.append(bf['gasGiant']['min'])
            where.append(f'r.gas_giant_count >= ${param_n}'); param_n += 1
        if bf.get('ww',      {}).get('min', 0) > 0:
            params.append(bf['ww']['min'])
            where.append(f'r.ww_count >= ${param_n}'); param_n += 1
        if bf.get('neutron', {}).get('min', 0) > 0:
            params.append(bf['neutron']['min'])
            where.append(f'r.neutron_count >= ${param_n}'); param_n += 1

    if req.require_bio:
        where.append('r.bio_signal_total > 0')
    if req.require_geo:
        where.append('r.geo_signal_total > 0')
    if req.require_terra:
        where.append('r.terraformable_count > 0')

    # Distance constraint (skipped in galaxy-wide mode)
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

    async with _pool.acquire() as conn:
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
        d['bodies'] = []  # Bodies fetched separately if needed
        results.append(d)

    response = {'results': results, 'total': total, 'count': len(results)}
    await cache_set(cache_key, response, TTL_SEARCH)
    return response


# ---------------------------------------------------------------------------
# NEW: Galaxy-wide economy search
# ---------------------------------------------------------------------------
@app.post('/api/search/galaxy')
async def galaxy_search(req: GalaxySearchRequest):
    """
    Find the best uncolonised systems for a given economy type,
    galaxy-wide, sorted by economy-specific score descending.
    No distance limit.
    """
    _metrics['db_queries'] += 1

    economy   = req.economy.strip()
    min_score = req.min_score
    limit     = min(req.limit, 500)
    offset    = req.offset

    cache_key = f'galaxy:{economy}:{min_score}:{limit}:{offset}'
    cached = await cache_get(cache_key)
    if cached: return cached

    async with _pool.acquire() as conn:
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

        total = await conn.fetchval("""
            SELECT COUNT(*)
            FROM ratings r
            JOIN systems s ON s.id64 = r.system_id64
            WHERE s.population = 0
              AND r.score IS NOT NULL
        """)

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
    await cache_set(cache_key, response, TTL_SEARCH)
    return response


# ---------------------------------------------------------------------------
# NEW: Multi-economy cluster search
# ---------------------------------------------------------------------------
@app.post('/api/search/cluster')
async def cluster_search(req: ClusterSearchRequest):
    """
    Find the best anchor points in the galaxy where a 500ly bubble
    covers all requested economy types with sufficient viable systems.

    Example request:
      {
        "requirements": [
          {"economy": "HighTech",    "min_count": 1, "min_score": 40},
          {"economy": "Agriculture", "min_count": 2, "min_score": 30},
          {"economy": "Refinery",    "min_count": 2, "min_score": 30}
        ]
      }
    """
    _metrics['db_queries'] += 1

    if not req.requirements:
        raise HTTPException(400, 'At least one economy requirement must be specified')
    if len(req.requirements) > 6:
        raise HTTPException(400, 'Maximum 6 economy requirements')

    reqs_json = json.dumps([r.model_dump() for r in req.requirements])
    cache_key = f'cluster:{reqs_json}:{req.limit}:{req.offset}'
    cached = await cache_get(cache_key)
    if cached: return cached

    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM search_cluster($1::jsonb, $2, $3)
        """, reqs_json, req.limit, req.offset)

        # Total count for this query
        # Build simple WHERE to count matching anchors
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
    await cache_set(cache_key, response, TTL_CLUSTER)
    return response


# ---------------------------------------------------------------------------
# System detail
# ---------------------------------------------------------------------------
@app.get('/api/system/{id64}')
async def get_system(id64: int):
    cache_key = f'sys:{id64}'
    cached = await cache_get(cache_key)
    if cached: return cached

    async with _pool.acquire() as conn:
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

    result = {'record': d, 'system': d}
    await cache_set(cache_key, result, TTL_SYSTEM)
    return result


@app.get('/api/local/system/{id64}')
async def local_get_system(id64: int):
    """Alias — compatibility with Pi frontend."""
    return await get_system(id64)


# ---------------------------------------------------------------------------
# Body detail
# ---------------------------------------------------------------------------
@app.get('/api/body/{body_id}')
async def get_body(body_id: int):
    cache_key = f'body:{body_id}'
    cached = await cache_get(cache_key)
    if cached: return cached

    async with _pool.acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM bodies WHERE id = $1', body_id)
        if not row:
            raise HTTPException(404, f'Body {body_id} not found')

    result = dict(row)
    await cache_set(cache_key, result, TTL_SYSTEM)
    return result


# ---------------------------------------------------------------------------
# Batch system lookup
# ---------------------------------------------------------------------------
@app.post('/api/systems/batch')
async def batch_systems(request: Request):
    body = await request.json()
    id64s = body.get('id64s', [])
    if not id64s or len(id64s) > 500:
        raise HTTPException(400, 'Provide 1-500 id64s')

    # Check cache for each
    result = {}
    missing = []
    for id64 in id64s:
        cached = await cache_get(f'sys:{id64}')
        if cached:
            result[str(id64)] = cached.get('record') or cached
        else:
            missing.append(id64)

    if missing:
        async with _pool.acquire() as conn:
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

        # Group bodies by system
        bodies_by_system: dict[int, list] = {}
        for b in bodies_rows:
            bid = b['system_id64']
            bodies_by_system.setdefault(bid, []).append(dict(b))

        for row in rows:
            d = sys_row_to_dict(row)
            d['bodies'] = bodies_by_system.get(d['id64'], [])
            result[str(d['id64'])] = d
            await cache_set(f'sys:{d["id64"]}', {'record': d}, TTL_SYSTEM)

    return {'systems': result}


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------
@app.get('/api/watchlist')
async def get_watchlist():
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.*,
                r.score, r.economy_suggestion
            FROM watchlist w
            LEFT JOIN ratings r ON r.system_id64 = w.system_id64
            ORDER BY w.added_at DESC
        """)
    return {'watchlist': [dict(r) for r in rows]}


@app.post('/api/watchlist/{id64}')
async def add_watchlist(id64: int, request: Request):
    body = await request.json()
    async with _pool.acquire() as conn:
        # Get system info
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
async def remove_watchlist(id64: int):
    async with _pool.acquire() as conn:
        await conn.execute('DELETE FROM watchlist WHERE system_id64 = $1', id64)
    return {'ok': True}


@app.patch('/api/watchlist/{id64}/alert')
async def update_alert(id64: int, alert: WatchlistAlert):
    async with _pool.acquire() as conn:
        await conn.execute("""
            UPDATE watchlist
            SET alert_min_score = $1, alert_economy = $2
            WHERE system_id64 = $3
        """, alert.min_score, alert.economy, id64)
    return {'ok': True}


@app.get('/api/watchlist/changes')
async def watchlist_changes():
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM watchlist_changelog
            ORDER BY detected_at DESC LIMIT 100
        """)
    return {'changes': [dict(r) for r in rows]}


@app.get('/api/watchlist/changelog')
async def watchlist_changelog():
    return await watchlist_changes()


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
@app.get('/api/systems/{id64}/note')
async def get_note(id64: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT note, updated_at FROM system_notes WHERE system_id64 = $1', id64
        )
    return {'note': row['note'] if row else '', 'updated_at': str(row['updated_at']) if row else None}


@app.post('/api/systems/{id64}/note')
async def save_note(id64: int, body: NoteBody):
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO system_notes (system_id64, note, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (system_id64) DO UPDATE SET note = $2, updated_at = NOW()
        """, id64, body.note)
    return {'ok': True}


@app.delete('/api/systems/{id64}/note')
async def delete_note(id64: int):
    async with _pool.acquire() as conn:
        await conn.execute('DELETE FROM system_notes WHERE system_id64 = $1', id64)
    return {'ok': True}


@app.get('/api/systems/notes')
async def all_notes():
    async with _pool.acquire() as conn:
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
async def cache_stats():
    stats = {'cache_hits': _metrics['cache_hits'], 'cache_misses': _metrics['cache_misses']}
    if _redis:
        try:
            info = await _redis.info('stats')
            stats['redis_hits'] = info.get('keyspace_hits', 0)
            stats['redis_misses'] = info.get('keyspace_misses', 0)
            stats['redis_memory_mb'] = round(int((await _redis.info('memory')).get('used_memory', 0)) / 1e6, 1)
        except Exception: pass
    async with _pool.acquire() as conn:
        stats['db_cache_rows'] = await conn.fetchval(
            "SELECT COUNT(*) FROM api_cache WHERE expires_at > NOW()"
        )
    return stats


@app.post('/api/cache/clear')
async def cache_clear():
    if _redis:
        try: await _redis.flushdb()
        except Exception: pass
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM api_cache WHERE expires_at <= NOW()")
    return {'ok': True, 'message': 'Cache cleared'}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, log_level=LOG_LEVEL.lower())
