"""System / body / batch detail endpoints."""
from typing import Any, List, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from config  import settings, log
from deps    import get_pool, get_redis, cache_get, cache_set
from models  import SystemDetailResponse
from helpers import sys_row_to_dict
from station_body_resolver import is_transient_non_slot_station_type, resolve_station_body_association

try:
    import local_search as _ls
    _LS_AVAILABLE = True
except ImportError:
    _ls = None  # type: ignore
    _LS_AVAILABLE = False

router = APIRouter(tags=['systems'])

SYSTEM_CACHE_VERSION = 'v4'
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

        has_station_links = await conn.fetchval("SELECT to_regclass('public.station_body_links') IS NOT NULL")
        if has_station_links:
            stations = await conn.fetch("""
                SELECT s.id, s.id AS market_id, s.system_id64, s.name, s.station_type,
                       s.distance_from_star, s.body_name AS station_body_name,
                       s.distance_source, s.distance_confidence, s.distance_updated_at,
                       s.station_type_source, s.station_type_confidence, s.station_type_updated_at,
                       s.body_name_source, s.body_name_confidence, s.body_name_updated_at,
                       COALESCE(l.body_name, s.body_name) AS body_name,
                       l.body_id, l.lane, l.association_status,
                       l.association_confidence, l.association_source,
                       l.resolver_notes,
                       s.landing_pad_size, s.primary_economy, s.secondary_economy,
                       s.has_market, s.has_shipyard, s.has_outfitting,
                       s.has_refuel, s.has_repair, s.has_rearm
                FROM stations s
                LEFT JOIN station_body_links l ON l.station_id = s.id
                WHERE s.system_id64 = $1
            """, id64)
        else:
            stations = await conn.fetch("""
                SELECT id, id AS market_id, system_id64, name, station_type, distance_from_star,
                       distance_source, distance_confidence, distance_updated_at,
                       station_type_source, station_type_confidence, station_type_updated_at,
                       body_name_source, body_name_confidence, body_name_updated_at,
                       body_name AS station_body_name, body_name,
                       NULL::bigint AS body_id,
                       NULL::text AS lane,
                       NULL::text AS association_status,
                       NULL::text AS association_confidence,
                       NULL::text AS association_source,
                       NULL::text AS resolver_notes,
                       landing_pad_size, primary_economy, secondary_economy,
                       has_market, has_shipyard, has_outfitting,
                       has_refuel, has_repair, has_rearm
                FROM stations WHERE system_id64 = $1
            """, id64)

    d = sys_row_to_dict(row)
    d['bodies']   = [dict(b) for b in bodies]
    d['stations'] = [_station_with_association(dict(s), d['bodies']) for s in stations]

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


def _station_with_association(station: dict, bodies: list[dict]) -> dict:
    if is_transient_non_slot_station_type(station.get('station_type')):
        association = resolve_station_body_association(station, bodies)
        station.update(association.to_api_dict())
        return station
    if station.get('association_status'):
        return station
    association = resolve_station_body_association(station, bodies)
    station.update(association.to_api_dict())
    return station


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
