"""Meta endpoints — health, status, metrics.

Anything diagnostic / non-business-logic lives here. Every environment
should be able to hit these without auth.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from edfinder_api.config import settings
from edfinder_api.deps import get_pool, get_redis, cache_get, cache_set
from edfinder_api.models import HealthResponse, StatusResponse
from edfinder_api.state import metrics

log = logging.getLogger('ed_finder')

router = APIRouter(tags=['meta'])

# Local_search may be unavailable in minimal deployments (CI, local dev).
try:
    import edfinder_api.local_search as _ls
    _LS_AVAILABLE = True
except ImportError:
    _ls = None  # type: ignore
    _LS_AVAILABLE = False


@router.get('/api/health', response_model=HealthResponse)
async def health(pool: asyncpg.Pool = Depends(get_pool)):
    """Cheap, bounded liveness probe.

    Bounded at 2 s with `asyncio.wait_for` so a wedged pool (every
    connection held by a slow query) cannot hang the healthcheck for
    the asyncpg `command_timeout` of 5 minutes. nginx's
    `proxy_read_timeout` on /api/health is 300s and Cloudflare's edge
    timeout is ~100s, so an unbounded probe means CF returns its own
    524 to the user before nginx ever gives up — and the api container
    keeps showing (healthy) to Docker's own healthcheck because that
    runs from inside the container against localhost without going
    through any of those timeouts.

    Capping the probe at 2 s makes /api/health honest about pool
    exhaustion: if no connection is acquirable inside that window, we
    return 503 with a clear message and Docker can mark the container
    unhealthy and restart it, breaking the wedge.
    """
    async def _probe() -> None:
        async with pool.acquire() as conn:
            await conn.fetchval('SELECT 1')

    try:
        await asyncio.wait_for(_probe(), timeout=2.0)
        return HealthResponse(
            status='ok',
            database='connected',
            version=settings.app_version,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            503,
            detail='database probe timed out after 2s — pool likely exhausted',
        )
    except Exception as e:
        raise HTTPException(503, detail=str(e))


@router.get('/api/status', response_model=StatusResponse)
async def status(
    pool:  asyncpg.Pool              = Depends(get_pool),
    redis: Optional[aioredis.Redis]  = Depends(get_redis),
):
    cache_key = 'status:main'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    async with pool.acquire() as conn:
        # pg_class.reltuples is PG's ANALYZE-derived row estimate (~1ms)
        # vs 30+ seconds for COUNT(*) FROM bodies on a 1B+ row table.
        # Estimates auto-refresh on every autovac/analyze cycle - plenty
        # accurate for a status display. cluster_summary stays as COUNT(*)
        # because the table is small and has a WHERE filter.
        counts = await conn.fetchrow("""
            SELECT
              COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='systems'), 0) AS sys_count,
              COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='bodies'),  0) AS body_count,
              COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='ratings'), 0) AS rated_count
        """)
        sys_count  = int(counts['sys_count'])
        body_count = int(counts['body_count'])
        rated      = int(counts['rated_count'])
        clustered  = await conn.fetchval(
            'SELECT COUNT(*) FROM cluster_summary WHERE coverage_score IS NOT NULL'
        )
        meta_rows  = await conn.fetch('SELECT key, value FROM app_meta')
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


@router.get('/api/local/status', response_model=StatusResponse)
async def local_status(
    pool:  asyncpg.Pool              = Depends(get_pool),
    redis: Optional[aioredis.Redis]  = Depends(get_redis),
):
    # Cache mirrors /api/status — without it, V2 Admin polls this every 30s
    # and triggered 8 sequential COUNT(*) queries (including COUNT(*) FROM
    # bodies on a ~1B row table) on every poll, starving build_grid.py of
    # disk I/O during the grid backfill.
    cache_key = 'status:local'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached
    if _LS_AVAILABLE:
        try:
            result = await _ls.local_db_status(pool)
            await cache_set(cache_key, result, settings.ttl_status, redis)
            return result
        except Exception as exc:
            log.warning('local_db_status error: %s', exc)
    return await status(pool, redis)


@router.get('/api/metrics', response_class=PlainTextResponse, include_in_schema=False)
async def metrics_endpoint():
    uptime = time.time() - metrics['startup_time']
    lines = [
        '# HELP ed_finder_requests_total Total HTTP requests',
        '# TYPE ed_finder_requests_total counter',
        f'ed_finder_requests_total {metrics["requests_total"]}',
        '# HELP ed_finder_cache_hits_total Redis cache hits',
        '# TYPE ed_finder_cache_hits_total counter',
        f'ed_finder_cache_hits_total {metrics["cache_hits"]}',
        '# HELP ed_finder_cache_misses_total Redis cache misses',
        '# TYPE ed_finder_cache_misses_total counter',
        f'ed_finder_cache_misses_total {metrics["cache_misses"]}',
        '# HELP ed_finder_errors_total Total unhandled errors',
        '# TYPE ed_finder_errors_total counter',
        f'ed_finder_errors_total {metrics["errors_total"]}',
        '# HELP ed_finder_db_queries_total Total DB queries dispatched',
        '# TYPE ed_finder_db_queries_total counter',
        f'ed_finder_db_queries_total {metrics["db_queries"]}',
        '# HELP ed_finder_uptime_seconds Seconds since startup',
        '# TYPE ed_finder_uptime_seconds gauge',
        f'ed_finder_uptime_seconds {uptime:.0f}',
    ]
    return '\n'.join(lines)
