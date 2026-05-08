"""Search endpoints — autocomplete + local/galaxy/cluster searches."""
import json
import time
from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from config  import settings, limiter, log
from deps    import get_pool, get_redis, cache_get, cache_set, inc_metric, log_slow
from models  import (
    SearchResponse, SearchFilters, LocalSearchRequest,
    GalaxySearchRequest, ClusterSearchRequest,
)
from helpers import sys_row_to_dict

# Local-search delegate (optional in minimal deployments).
try:
    import local_search as _ls
    _LS_AVAILABLE = True
except ImportError:
    _ls = None  # type: ignore
    _LS_AVAILABLE = False

router = APIRouter(tags=['search'])




@router.get('/api/local/autocomplete')
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
@router.post('/api/local/search', response_model=SearchResponse)
@limiter.limit(settings.rate_limit_search)
async def local_search_endpoint(
    request: Request,
    req: LocalSearchRequest,
    background_tasks: BackgroundTasks,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    # Code #10: increment metric in background — off critical path
    background_tasks.add_task(inc_metric, 'db_queries')
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
            background_tasks.add_task(log_slow, 'local_search', (time.time() - t0) * 1000)
            return result
        except Exception as exc:
            # Include type + repr + asyncpg sqlstate so empty-string asyncpg
            # errors (dropped/cancelled connections) become diagnosable
            # instead of silently falling through.
            log.warning(
                'local_search delegation error: %s repr=%r sqlstate=%s — falling back to inline',
                type(exc).__name__, exc, getattr(exc, 'sqlstate', None),
            )

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

    cache_key = (
        f'search:{ref_x:.1f},{ref_y:.1f},{ref_z:.1f}:{min_dist}-{max_dist}:'
        f'{pop_zero}:{economy}:{sort_by}:{size}:{offset}:{galaxy_wide}:{min_rating}:'
        # Include body filters / requirement booleans / star types so the
        # cache key changes whenever the user adjusts the body sliders or
        # quick-pill filters. Without these, any subsequent request that
        # only differs in body filters silently re-uses the stale (broader)
        # response — making it look like the sliders are doing nothing.
        f'bf={json.dumps(req.body_filters or {}, sort_keys=True)}:'
        f'rb={int(bool(req.require_bio))}:rg={int(bool(req.require_geo))}:'
        f'rt={int(bool(req.require_terra))}:'
        f'st={",".join(sorted(req.star_types or []))}'
    )
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
        # Backwards-compat: accept both snake_case (v2 frontend) and
        # camelCase (legacy callers) for body filter keys.
        _ALIASES = {
            'gasGiant': 'gas_giant', 'blackHole': 'black_hole',
            'whiteDwarf': 'white_dwarf', 'metalRich': 'metal_rich',
            'rockyIce': 'rocky_ice',
        }
        for alias, canonical in _ALIASES.items():
            if alias in bf and canonical not in bf:
                bf[canonical] = bf[alias]
        # All columns that the v2 sliders + presets can hit.
        FILTER_PAIRS = [
            ('r.landable_count',      'landable'),
            ('r.terraformable_count', 'terraformable'),
            ('r.elw_count',           'elw'),
            ('r.ww_count',            'ww'),
            ('r.ammonia_count',       'ammonia'),
            ('r.gas_giant_count',     'gas_giant'),
            ('r.hmc_count',           'hmc'),
            ('r.metal_rich_count',    'metal_rich'),
            ('r.rocky_count',         'rocky'),
            ('r.rocky_ice_count',     'rocky_ice'),
            ('r.icy_count',           'icy'),
            ('r.neutron_count',       'neutron'),
            ('r.black_hole_count',    'black_hole'),
            ('r.white_dwarf_count',   'white_dwarf'),
            ('r.other_star_count',    'other_star'),
            ('r.ring_count',          'rings'),
            ('r.walkable_count',      'walkable'),
            ('r.bio_signal_total',    'bio'),
            ('r.geo_signal_total',    'geo'),
        ]
        for col, key in FILTER_PAIRS:
            rng = bf.get(key) or {}
            if not isinstance(rng, dict):
                continue
            min_val = int(rng.get('min', 0) or 0)
            max_val = rng.get('max')
            if min_val > 0:
                params.append(min_val)
                where.append(f'{col} >= ${param_n}')
                param_n += 1
            if max_val is not None:
                params.append(int(max_val))
                where.append(f'({col} IS NULL OR {col} <= ${param_n})')
                param_n += 1

    if req.require_bio:   where.append('r.bio_signal_total > 0')
    if req.require_geo:   where.append('r.geo_signal_total > 0')
    if req.require_terra: where.append('r.terraformable_count > 0')

    dist_expr = (
        f"SQRT((s.x-{ref_x})*(s.x-{ref_x}) + "
        f"(s.y-{ref_y})*(s.y-{ref_y}) + "
        f"(s.z-{ref_z})*(s.z-{ref_z}))"
    )
    if not galaxy_wide:
        # Bounding-box prune (cheap, uses btree on s.x/y/z) followed by
        # squared-distance BETWEEN — orders of magnitude faster than calling
        # distance_ly() per row, which the planner does not always inline.
        # This is the same pattern local_db_search uses; copying it into
        # the fallback so a fallback never melts the DB the way it did
        # at 50 LY around Sol (10-minute COUNT(*) seen in production logs).
        where.append(f's.x BETWEEN {ref_x - max_dist} AND {ref_x + max_dist}')
        where.append(f's.y BETWEEN {ref_y - max_dist} AND {ref_y + max_dist}')
        where.append(f's.z BETWEEN {ref_z - max_dist} AND {ref_z + max_dist}')
        where.append(
            f'((s.x-{ref_x})*(s.x-{ref_x}) + '
            f'(s.y-{ref_y})*(s.y-{ref_y}) + '
            f'(s.z-{ref_z})*(s.z-{ref_z})) '
            f'BETWEEN {min_dist*min_dist} AND {max_dist*max_dist}'
        )

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
        # Cap the fallback at 15 s of server-side time. Without this, a slow
        # COUNT(*) ran for 9.8 minutes in production while holding a pool
        # slot, starving every subsequent request and snowballing into a
        # cascade of "delegation error → fallback" warnings. SET LOCAL only
        # applies inside a transaction and reverts at COMMIT, which is
        # essential for pgBouncer transaction-pool mode (otherwise a
        # session-level SET would leak to the next client to grab the
        # connection from the pool).
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = '15s'")
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
    background_tasks.add_task(log_slow, 'local_search_fallback', (time.time() - t0) * 1000)
    return response


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
