#!/usr/bin/env python3
"""
ED Finder — Hetzner Backend
Version: 3.1 (PostgreSQL 16 / asyncpg)

This file is the **composition root**. It wires config, state, middleware,
lifespan, exception handlers, and router mounts. Business logic lives in
routers/ and helpers/.

Endpoint surface (see individual router docstrings for detail):

  routers/meta.py       health, status, local/status, metrics
  routers/watchlist.py  watchlist CRUD + changelog
  routers/notes.py      per-system user notes
  routers/events.py     EDDN SSE live feed + recent
  routers/admin.py      cache stats/clear + cluster-rebuild trigger
  (remaining in this file) autocomplete, local/search, galaxy, cluster,
                            system/body/batch detail, map/*, ratings/rerank
"""
import os
import sys
import time
import json
import logging
import asyncio
import pathlib as _pl
from datetime import datetime, timezone
from typing import Optional, Any, AsyncGenerator, List
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, Response, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse, FileResponse as _FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Shared config, state, deps, models, helpers
from config   import settings, log, limiter
from state    import (
    set_pool, set_redis, get_pool_singleton, get_redis_singleton,
    metrics as _metrics,
)
from deps     import get_pool, get_redis, require_admin, cache_get, cache_set
# Compatibility aliases — the routes still inlined below (search / systems /
# map / ratings) use the older `_inc_metric` / `_log_query` names.
from deps     import inc_metric as _inc_metric, log_slow as _log_query  # noqa: F401
from models   import (
    CoordsModel, RatingModel, BodyModel, StationModel, SystemModel,
    SearchResponse, SystemDetailResponse, HealthResponse, WatchlistAlert,
    NoteBody, SearchFilters, LocalSearchRequest, GalaxySearchRequest,
    ClusterRequirement, ClusterSearchRequest,
)
from helpers  import sys_row_to_dict

# Routers
from routers.meta      import router as meta_router
from routers.watchlist import router as watchlist_router
from routers.notes     import router as notes_router
from routers.admin     import router as admin_router
from routers.events    import router as events_router, eddn_pubsub_bridge

# Local search module (optional — absent in minimal deployments).
try:
    import local_search as _ls
    _LS_AVAILABLE = True
except ImportError:
    _ls = None  # type: ignore
    _LS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
_sse_pubsub_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sse_pubsub_task
    log.info(f"ED Finder Hetzner backend v{settings.app_version} starting ...")
    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=5, max_size=20,
        command_timeout=300,
        # pgBouncer transaction-pool mode requires prepared-statement cache off.
        statement_cache_size=0,
        server_settings={'application_name': 'ed_finder_api'},
    )
    set_pool(pool)

    redis = None
    try:
        redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        await redis.ping()
        set_redis(redis)
        log.info("Redis connected ✓ (pool max=%d)", settings.redis_max_connections)
    except Exception as e:
        log.warning(f"Redis unavailable ({e}) — running without cache")
        set_redis(None)
        redis = None

    if redis is not None:
        _sse_pubsub_task = asyncio.create_task(eddn_pubsub_bridge())
        log.info("EDDN→SSE pub/sub bridge started ✓")

    log.info("PostgreSQL pool ready ✓")
    app.state.pool  = pool
    app.state.redis = redis
    yield

    if _sse_pubsub_task:
        _sse_pubsub_task.cancel()
        try:
            await _sse_pubsub_task
        except (asyncio.CancelledError, Exception):
            pass
    if pool:   await pool.close()
    if redis:  await redis.aclose()
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

# Rate limiter — attach to app state (slowapi middleware auto-discovers it).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(',') if o.strip()],
    allow_methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'X-Admin-Token', 'Authorization'],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


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
# Exception handlers (RFC 7807 Problem Details)
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
    detail = str(exc) if settings.expose_error_detail else 'Internal server error'
    return JSONResponse(
        status_code=500,
        content={
            'type':   'https://httpstatuses.com/500',
            'title':  'Internal Server Error',
            'status': 500,
            'detail': detail,
        },
    )


# ---------------------------------------------------------------------------
# Router mounts — keep the /s/<id64> share router before static fallback.
# ---------------------------------------------------------------------------
from share_router import router as share_router  # noqa: E402
app.include_router(share_router)
app.include_router(meta_router)
app.include_router(watchlist_router)
app.include_router(notes_router)
app.include_router(admin_router)
app.include_router(events_router)

# ---------------------------------------------------------------------------
# Frontend directory (used by the remaining routes below and SPA fallback).
# ---------------------------------------------------------------------------
_FRONTEND_DIR = _pl.Path(__file__).parent.parent / 'frontend'


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
            r.score_extraction,
            r.economy_suggestion,
            r.elw_count, r.ww_count, r.ammonia_count,
            r.gas_giant_count, r.landable_count, r.terraformable_count,
            r.bio_signal_total, r.geo_signal_total,
            r.neutron_count, r.black_hole_count, r.white_dwarf_count,
            r.score_breakdown,
            r.terraforming_potential, r.body_diversity,
            r.confidence, r.rationale
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
                'offset':            req.offset,
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
                r.score_extraction,
                r.economy_suggestion, r.elw_count, r.ww_count,
                r.ammonia_count, r.gas_giant_count, r.landable_count,
                r.terraformable_count, r.bio_signal_total, r.geo_signal_total,
                r.neutron_count, r.black_hole_count, r.white_dwarf_count,
                r.score_breakdown,
                r.terraforming_potential, r.body_diversity,
                r.confidence, r.rationale
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
    id64s = body.get('ids', body.get('id64s', []))  # frontend sends 'ids'; 'id64s' kept for back-compat
    if not id64s or len(id64s) > 500:
        raise HTTPException(400, 'Provide 1-500 ids')

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
# Map support endpoints (v3.1) — cluster hulls, region labels, heatmap voxels
# ---------------------------------------------------------------------------
# These power the merged unified map tab (see frontend work in next commit):
#   * cluster hulls   → translucent spheres / convex hulls drawn per cluster
#   * region labels   → dim text labels for the 42 canonical ED regions
#   * heatmap voxels  → 200 LY cells carrying mean score, for density mode
# All three are aggregate-only (no per-system PII or auth); cached server-side.
# ---------------------------------------------------------------------------

@app.get('/api/map/regions')
@limiter.limit('60/minute')
async def map_regions(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """Return the 42 canonical ED galaxy regions with centroid coordinates
    (computed from the systems actually imported, so centres sit where the
    data is)."""
    cache_key = 'map:regions:v1'
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                _metrics['cache_hits'] += 1
                return JSONResponse(content=json.loads(cached))
        except Exception:
            pass
    _metrics['cache_misses'] += 1

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT r.id, r.name,
                   AVG(s.x)::real AS x,
                   AVG(s.y)::real AS y,
                   AVG(s.z)::real AS z,
                   COUNT(s.id64)  AS system_count
            FROM   galaxy_regions r
            LEFT JOIN systems s ON s.galaxy_region_id = r.id
            GROUP BY r.id, r.name
            ORDER BY r.id
        """, timeout=180)

    result = {
        'regions': [
            {
                'id':           r['id'],
                'name':         r['name'],
                'x':            r['x'],
                'y':            r['y'],
                'z':            r['z'],
                'system_count': r['system_count'],
            } for r in rows
        ],
        'total_regions': len(rows),
    }

    if redis:
        try:
            await redis.set(cache_key, json.dumps(result, default=str), ex=settings.ttl_cluster)
        except Exception:
            pass
    return result


@app.get('/api/map/clusters/hulls')
@limiter.limit('60/minute')
async def map_cluster_hulls(
    request: Request,
    min_count:  int  = Query(3, ge=1, le=100, description='Minimum systems per cluster'),
    max_hulls:  int  = Query(500, ge=10, le=2000, description='Cap on returned hulls'),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """Return cluster-anchor positions + approximate radius for map overlay.

    Each cluster is summarised as:
      { anchor_id64, anchor_name, x, y, z, radius_ly, system_count,
        top_economy, top_score }

    `radius_ly` is estimated from the best-known cluster's coverage (500 LY
    for standard cluster builder, 2000 LY for macro grid).  Cheap enough to
    compute on the fly and lets the frontend draw a translucent sphere
    without pulling per-member coordinates.
    """
    cache_key = f'map:cluster_hulls:v1:{min_count}:{max_hulls}'
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                _metrics['cache_hits'] += 1
                return JSONResponse(content=json.loads(cached))
        except Exception:
            pass
    _metrics['cache_misses'] += 1

    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT  cs.system_id64 AS anchor_id64,
                    s.name         AS anchor_name,
                    s.x, s.y, s.z,
                    500::real      AS radius_ly,
                    (cs.agriculture_count + cs.refinery_count +
                     cs.industrial_count  + cs.hightech_count  +
                     cs.military_count    + cs.tourism_count)  AS system_count,
                    GREATEST(
                        COALESCE(cs.agriculture_best,0), COALESCE(cs.refinery_best,0),
                        COALESCE(cs.industrial_best,0),  COALESCE(cs.hightech_best,0),
                        COALESCE(cs.military_best,0),    COALESCE(cs.tourism_best,0)
                    ) AS top_score,
                    CASE GREATEST(
                        COALESCE(cs.agriculture_best,0), COALESCE(cs.refinery_best,0),
                        COALESCE(cs.industrial_best,0),  COALESCE(cs.hightech_best,0),
                        COALESCE(cs.military_best,0),    COALESCE(cs.tourism_best,0)
                    )
                        WHEN COALESCE(cs.agriculture_best,0) THEN 'Agriculture'
                        WHEN COALESCE(cs.refinery_best,0)    THEN 'Refinery'
                        WHEN COALESCE(cs.industrial_best,0)  THEN 'Industrial'
                        WHEN COALESCE(cs.hightech_best,0)    THEN 'HighTech'
                        WHEN COALESCE(cs.military_best,0)    THEN 'Military'
                        WHEN COALESCE(cs.tourism_best,0)     THEN 'Tourism'
                    END AS top_economy
            FROM    cluster_summary cs
            JOIN    systems s ON s.id64 = cs.system_id64
            WHERE   (cs.agriculture_count + cs.refinery_count + cs.industrial_count +
                     cs.hightech_count + cs.military_count + cs.tourism_count) >= $1
            ORDER BY top_score DESC NULLS LAST
            LIMIT   $2
        """, min_count, max_hulls)

    result = {
        'clusters': [dict(r) for r in rows],
        'count':    len(rows),
        'cached':   False,
    }
    if redis:
        try:
            await redis.set(cache_key, json.dumps(result, default=str), ex=settings.ttl_cluster)
        except Exception:
            pass
    return result


@app.get('/api/map/heatmap')
@limiter.limit('30/minute')
async def map_heatmap(
    request: Request,
    voxel_size:  int = Query(200,  ge=50,  le=2000, description='Voxel cell size in LY'),
    min_systems: int = Query(5,    ge=1,   le=100,  description='Minimum systems per voxel'),
    economy:     Optional[str] = Query(None, description='Filter to a specific economy score'),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """Voxel-aggregated mean score for heatmap rendering.

    Bins systems into `voxel_size` LY cubes, returns cells containing at
    least `min_systems` rated systems with their (x, y, z) centre and
    mean score. Keeps payload small enough for a full galaxy pull at
    200 LY voxels (≈ a few MB) while giving the frontend a spatial signal
    density map would never provide.
    """
    eco_col = None
    if economy:
        eco_map = {
            'agriculture': 'score_agriculture', 'refinery':   'score_refinery',
            'industrial':  'score_industrial',  'hightech':   'score_hightech',
            'military':    'score_military',    'tourism':    'score_tourism',
            'extraction':  'score_extraction',
        }
        eco_col = eco_map.get(economy.lower())

    cache_key = f'map:heatmap:v1:{voxel_size}:{min_systems}:{eco_col or "overall"}'
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                _metrics['cache_hits'] += 1
                return JSONResponse(content=json.loads(cached))
        except Exception:
            pass
    _metrics['cache_misses'] += 1

    score_col = eco_col or 'score'
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT
                FLOOR(s.x / $1)::int * $1 + $1/2 AS cx,
                FLOOR(s.y / $1)::int * $1 + $1/2 AS cy,
                FLOOR(s.z / $1)::int * $1 + $1/2 AS cz,
                COUNT(*)              AS n,
                AVG(r.{score_col})::int AS avg_score,
                MAX(r.{score_col})    AS max_score
            FROM   systems s
            JOIN   ratings r ON r.system_id64 = s.id64
            WHERE  r.{score_col} IS NOT NULL
            GROUP BY cx, cy, cz
            HAVING COUNT(*) >= $2
        """, voxel_size, min_systems, timeout=300)

    result = {
        'voxel_size': voxel_size,
        'economy':    economy,
        'cells':      [dict(r) for r in rows],
        'count':      len(rows),
    }
    if redis:
        try:
            await redis.set(cache_key, json.dumps(result, default=str), ex=settings.ttl_cluster)
        except Exception:
            pass
    return result


@app.get('/api/map/timeline')
@limiter.limit('30/minute')
async def map_timeline(
    request: Request,
    bucket:  str  = Query('month', regex='^(day|week|month|quarter|year)$'),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """Return discovery-count time buckets for the EDDN time scrubber.

    Powers the bonus "watch colonisation unfold" feature — a slider at the
    bottom of the map that filters to 'systems first scanned before
    <date>'.  Buckets by day/week/month/quarter/year.
    """
    trunc = {
        'day':     'day',
        'week':    'week',
        'month':   'month',
        'quarter': 'quarter',
        'year':    'year',
    }[bucket]

    cache_key = f'map:timeline:v1:{bucket}'
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                _metrics['cache_hits'] += 1
                return JSONResponse(content=json.loads(cached))
        except Exception:
            pass
    _metrics['cache_misses'] += 1

    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT
                DATE_TRUNC('{trunc}', COALESCE(first_discovered_at, updated_at))::date AS bucket,
                COUNT(*) AS systems_discovered
            FROM   systems
            WHERE  COALESCE(first_discovered_at, updated_at) IS NOT NULL
            GROUP BY bucket
            ORDER BY bucket
        """, timeout=180)

    result = {
        'bucket': bucket,
        'points': [
            {'date': r['bucket'].isoformat() if r['bucket'] else None,
             'count': r['systems_discovered']}
            for r in rows
        ],
        'total': sum(r['systems_discovered'] for r in rows),
    }
    if redis:
        try:
            await redis.set(cache_key, json.dumps(result, default=str), ex=settings.ttl_cluster)
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# Ratings rerank — v3.1
# ---------------------------------------------------------------------------
# Applies user-tunable weights to the stored dimensional scores without
# recomputing anything from bodies.  The `score` column in DB is the canonical
# v3.1 score (42/23/18/10/5/2 weights); this endpoint lets a CMDR reweight
# "show me the top 50 but weight Tourism-strategic 40% and slots only 10%"
# and get an instantly reordered list.
#
# Request:
#   POST /api/ratings/rerank
#   {
#     "id64s":  [12345, 67890, ...]   # from a prior search
#     "weights": {                    # any subset; unspecified = defaults
#       "economy":       0.42,
#       "slots":         0.23,
#       "strategic":     0.18,
#       "safety":        0.10,
#       "terraforming":  0.05,
#       "diversity":     0.02
#     },
#     "economy": "Tourism"  # optional — which economy score drives "economy"
#                           # dimension.  Default: the stored economy_suggestion
#   }
#
# Response:
#   [{ "id64": ..., "reranked_score": 87, "original_score": 74,
#      "rationale": "Tourism-leaning via 2 ELW; 3 landable; neutron nearby" }]
# ---------------------------------------------------------------------------

# Default v3.1 weights — must sum to 1.0 for reranked_score to be in 0-100.
_DEFAULT_WEIGHTS = {
    'economy':      0.42,
    'slots':        0.23,
    'strategic':    0.18,
    'safety':       0.10,
    'terraforming': 0.05,
    'diversity':    0.02,
}

_ECONOMY_COLS = {
    'Agriculture': 'score_agriculture',
    'Refinery':    'score_refinery',
    'Industrial':  'score_industrial',
    'HighTech':    'score_hightech',
    'Military':    'score_military',
    'Tourism':     'score_tourism',
    'Extraction':  'score_extraction',
}


class RerankRequest(BaseModel):
    id64s:   List[int] = Field(..., min_length=1, max_length=500)
    weights: Optional[dict] = None
    economy: Optional[str]  = None      # e.g. 'Tourism'; None = use stored primary


@app.post('/api/ratings/rerank')
@limiter.limit('60/minute')
async def ratings_rerank(
    request: Request,
    body: RerankRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    # ── Normalise weights: accept partial user input, fill gaps from defaults
    w = dict(_DEFAULT_WEIGHTS)
    if body.weights:
        for k, v in body.weights.items():
            if k in w:
                try:
                    w[k] = max(0.0, min(1.0, float(v)))
                except (TypeError, ValueError):
                    pass
    total = sum(w.values()) or 1.0
    w = {k: v / total for k, v in w.items()}   # normalise to sum=1.0

    # ── Resolve which economy drives the "economy" dimension
    eco_col = None
    if body.economy and body.economy in _ECONOMY_COLS:
        eco_col = _ECONOMY_COLS[body.economy]

    # Build the eco-score expression: either the requested column, or the
    # stored `economy_suggestion` column pulled dynamically per row.
    if eco_col:
        eco_expr = f"COALESCE({eco_col}, 0)"
    else:
        # Pick the highest of the seven per-row (handles rows missing
        # economy_suggestion gracefully).
        eco_expr = (
            "GREATEST("
            "COALESCE(score_agriculture,0), COALESCE(score_refinery,0),"
            "COALESCE(score_industrial,0),  COALESCE(score_hightech,0),"
            "COALESCE(score_military,0),    COALESCE(score_tourism,0),"
            "COALESCE(score_extraction,0))"
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                system_id64 AS id64,
                score                             AS original_score,
                {eco_expr}                        AS eco_score,
                COALESCE(slots, 0)                AS slots,
                COALESCE(body_quality, 0)         AS strategic,
                COALESCE(orbital_safety, 0)       AS safety,
                COALESCE(terraforming_potential,0) AS terraforming,
                COALESCE(body_diversity, 0)       AS diversity,
                confidence,
                rationale,
                economy_suggestion
            FROM ratings
            WHERE system_id64 = ANY($1::bigint[])
            """,
            body.id64s,
        )

    # ── Apply weights in Python (trivial math; keeps the SQL readable)
    result = []
    for r in rows:
        reranked = (
            r['eco_score']     * w['economy']      +
            r['slots']         * w['slots']        +
            r['strategic']     * w['strategic']    +
            r['safety']        * w['safety']       +
            r['terraforming']  * w['terraforming'] +
            r['diversity']     * w['diversity'] * (100.0 / 30.0)  # diversity is 0-30
        )
        # Optional confidence multiplier: stale data nudges score down slightly.
        if r['confidence'] is not None:
            reranked *= r['confidence']
        result.append({
            'id64':           r['id64'],
            'reranked_score': int(round(reranked)),
            'original_score': r['original_score'],
            'confidence':     float(r['confidence']) if r['confidence'] is not None else None,
            'rationale':      r['rationale'],
            'economy_used':   body.economy or r['economy_suggestion'],
        })

    # Return sorted descending by reranked_score
    result.sort(key=lambda x: x['reranked_score'], reverse=True)
    return {
        'weights_applied': w,
        'economy_used':    body.economy,
        'results':         result,
    }

# SPA fallback + static files
# ---------------------------------------------------------------------------

# Mount static assets directory before registering the catch-all so that
# /static/<file> is served by StaticFiles (which includes its own safe path
# resolution).
if _FRONTEND_DIR.is_dir():
    app.mount('/static', StaticFiles(directory=str(_FRONTEND_DIR)), name='static')


_FRONTEND_REAL = _FRONTEND_DIR.resolve()


def _safe_frontend_path(raw: str) -> Optional[_pl.Path]:
    """Resolve a user-supplied path relative to the frontend dir, rejecting
    anything that escapes via '..' or symlinks."""
    if not raw:
        return None
    try:
        candidate = (_FRONTEND_DIR / raw).resolve()
    except (OSError, RuntimeError):
        return None
    # Must be inside the frontend directory (or equal to it).
    if candidate != _FRONTEND_REAL and _FRONTEND_REAL not in candidate.parents:
        return None
    return candidate


@app.get('/{full_path:path}', include_in_schema=False)
async def spa_fallback(full_path: str):
    # API paths should have been matched already; if someone requests
    # /api/<unknown> return 404 JSON instead of serving index.html.
    if full_path.startswith('api/'):
        raise HTTPException(404, f'API endpoint {full_path} not found')

    candidate = _safe_frontend_path(full_path)
    if candidate and candidate.is_file():
        return _FileResponse(str(candidate))
    # Fall back to index.html for SPA routing
    return _FileResponse(str(_FRONTEND_DIR / 'index.html'))


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run(app, host='0.0.0.0', port=port, log_level=settings.log_level.lower())

