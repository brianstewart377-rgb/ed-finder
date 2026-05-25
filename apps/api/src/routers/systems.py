"""System / body / batch detail endpoints."""
from typing import Any, List, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from config  import settings, log
from deps    import get_pool, get_redis, cache_get, cache_set
from models  import SystemDetailResponse
from helpers import sys_row_to_dict

try:
    import local_search as _ls
    _LS_AVAILABLE = True
except ImportError:
    _ls = None  # type: ignore
    _LS_AVAILABLE = False

router = APIRouter(tags=['systems'])

SYSTEM_CACHE_VERSION = 'v3'
BODY_CACHE_VERSION = 'v2'




# ---------------------------------------------------------------------------
# System detail
# ---------------------------------------------------------------------------
@router.get('/api/system/{id64}', response_model=SystemDetailResponse)
async def get_system(
    id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    cache_key = f'sys:{SYSTEM_CACHE_VERSION}:{id64}'
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
                r.confidence, r.rationale, r.rating_version
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
            SELECT id, id AS market_id, name, station_type, distance_from_star, body_name,
                   landing_pad_size, primary_economy, secondary_economy,
                   has_market, has_shipyard, has_outfitting,
                   has_refuel, has_repair, has_rearm
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


@router.get('/api/local/system/{id64}')
async def local_get_system(
    id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    return await get_system(id64, pool, redis)


# ---------------------------------------------------------------------------
# Body detail
# ---------------------------------------------------------------------------
@router.get('/api/body/{body_id}')
async def get_body(
    body_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    cache_key = f'body:{BODY_CACHE_VERSION}:{body_id}'
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
@router.post('/api/systems/batch')
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
        cached = await cache_get(f'sys:{SYSTEM_CACHE_VERSION}:{id64}', redis)
        if cached:
            result[str(id64)] = cached.get('record') or cached
        else:
            missing.append(id64)

    if missing:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.*,
                    r.score, r.score_breakdown, r.economy_suggestion,
                    r.rating_version,
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
            await cache_set(f'sys:{SYSTEM_CACHE_VERSION}:{d["id64"]}', {'record': d}, settings.ttl_system, redis)

    return {'systems': result}
