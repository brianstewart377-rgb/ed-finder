"""Search endpoints — autocomplete + local/galaxy/cluster searches.

Audit fix (2026-05-08, AUDIT_REPORT.md §C5 / Phase 2):
the previous file carried two parallel implementations of every search:
the canonical `local_search.local_db_*` builder, and a 200-line inline
fallback per endpoint that was triggered on any exception. The fallback
had drifted (e.g. it always sorted by `r.score` while the primary path
sorted by the economy-specific `display_score_col`), causing identical
requests to return different orderings depending on which path ran.

This file now has ONE search implementation. If the primary path raises,
we surface RFC 7807 problem-details with HTTP 503 instead of silently
degrading.
"""
import json
import time
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings, limiter, log
from deps   import get_pool, get_redis, cache_get, cache_set, inc_metric, log_slow
from models import (
    SearchResponse, SearchFilters, LocalSearchRequest,
    GalaxySearchRequest, ClusterSearchRequest, AutocompleteResponse,
)

# Single search implementation. If this import fails the app cannot
# serve search at all — fail loud at startup, not at request time.
import local_search as _ls

router = APIRouter(tags=['search'])


# ---------------------------------------------------------------------------
# Internal: RFC 7807 503 response
# ---------------------------------------------------------------------------
def _search_unavailable(detail_msg: str, *, hint: str = '') -> JSONResponse:
    """Surface a search backend failure as RFC 7807 problem-details.

    The audit's Phase 2 contract is "no silent fallback" — when the SQL
    builder raises, callers MUST be able to tell it failed (so they can
    retry, alert, or back off) instead of receiving subtly wrong data
    from a parallel implementation.
    """
    body = {
        'type':    'https://ed-finder.app/problem/search-unavailable',
        'title':   'Search backend temporarily unavailable',
        'status':  503,
        'detail':  detail_msg if settings.expose_error_detail else 'Search service is temporarily unavailable.',
        'hint':    hint or 'Retry in a few seconds; if the problem persists, check /api/health.',
    }
    return JSONResponse(status_code=503, content=body, media_type='application/problem+json')


# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------
@router.get('/api/local/autocomplete', response_model=AutocompleteResponse)
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

    cache_key = f'ac:{q.lower()[:20]}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    try:
        results = await _ls.local_db_autocomplete(q, pool)
    except Exception as exc:
        log.error('local_db_autocomplete failed: %s', exc, exc_info=True)
        return _search_unavailable(f'autocomplete: {exc!r}',
                                    hint='Try again in a few seconds.')

    result = {'results': results, 'source': 'local_db'}
    await cache_set(cache_key, result, settings.ttl_autocomplete, redis)
    return result


# ---------------------------------------------------------------------------
# Local search
# ---------------------------------------------------------------------------
@router.post('/api/local/search', response_model=SearchResponse)
@limiter.limit(settings.rate_limit_search)
async def local_search_endpoint(
    request: Request,
    req: LocalSearchRequest,
    background_tasks: BackgroundTasks,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    background_tasks.add_task(inc_metric, 'db_queries')
    t0 = time.time()

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

    # Cache key includes every dimension that affects the result set,
    # otherwise the cache silently serves stale data when sliders move
    # (this was the original bug behind the inline-fallback's existence).
    cache_key = (
        f"search:v2:{json.dumps(body_dict, sort_keys=True, default=str)}"
    )
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    try:
        result = await _ls.local_db_search(body_dict, pool)
    except Exception as exc:
        # Surface — don't mask. The previous code masked here and silently
        # served different ordering than callers expected (audit §C5).
        log.error(
            'local_db_search failed: type=%s repr=%r sqlstate=%s',
            type(exc).__name__, exc, getattr(exc, 'sqlstate', None),
            exc_info=True,
        )
        return _search_unavailable(
            f'local search: {type(exc).__name__}: {exc}',
            hint='Reduce search radius or filter scope; if persistent, retry shortly.',
        )

    await cache_set(cache_key, result, settings.ttl_search, redis)
    background_tasks.add_task(log_slow, 'local_search', (time.time() - t0) * 1000)
    return result


# ---------------------------------------------------------------------------
# Galaxy search
# ---------------------------------------------------------------------------
@router.post('/api/search/galaxy')
@limiter.limit(settings.rate_limit_search)
async def galaxy_search(
    request: Request,
    req: GalaxySearchRequest,
    background_tasks: BackgroundTasks,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    background_tasks.add_task(inc_metric, 'db_queries')

    economy   = req.economy.strip()
    min_score = req.min_score
    limit     = min(req.limit, 500)

    cache_key = f'galaxy:v2:{economy}:{min_score}:{limit}:{req.offset}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    body_dict = {
        'economy':           economy,
        'min_score':         min_score,
        'limit':             limit,
        'offset':            req.offset,
        'include_colonised': False,
    }
    try:
        result = await _ls.local_db_galaxy_search(body_dict, pool)
    except Exception as exc:
        log.error('local_db_galaxy_search failed: %r', exc, exc_info=True)
        return _search_unavailable(f'galaxy search: {type(exc).__name__}: {exc}')

    await cache_set(cache_key, result, settings.ttl_search, redis)
    return result


# ---------------------------------------------------------------------------
# Cluster search
# ---------------------------------------------------------------------------
@router.post('/api/search/cluster')
@limiter.limit(settings.rate_limit_search)
async def cluster_search(
    request: Request,
    req: ClusterSearchRequest,
    background_tasks: BackgroundTasks,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    background_tasks.add_task(inc_metric, 'db_queries')

    if not req.requirements:
        raise HTTPException(400, 'At least one economy requirement must be specified')
    if len(req.requirements) > 6:
        raise HTTPException(400, 'Maximum 6 economy requirements')

    reqs_json = json.dumps([r.model_dump() for r in req.requirements], sort_keys=True)
    cache_key = f'cluster:v2:{reqs_json}:{req.limit}:{req.offset}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    body_dict = {
        'requirements':     [r.model_dump() for r in req.requirements],
        'limit':            req.limit,
        'reference_coords': req.reference_coords,
    }
    try:
        result = await _ls.local_db_cluster_search(body_dict, pool)
    except Exception as exc:
        log.error('local_db_cluster_search failed: %r', exc, exc_info=True)
        return _search_unavailable(f'cluster search: {type(exc).__name__}: {exc}')

    await cache_set(cache_key, result, settings.ttl_cluster, redis)
    return result
