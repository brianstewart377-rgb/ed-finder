"""Map data endpoints — galaxy regions, cluster hulls, heatmap, timeline."""
import json
from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from config  import settings, limiter, log
from deps    import get_pool, get_redis, cache_get, cache_set
from state   import metrics as _metrics

router = APIRouter(tags=['map'])





# ---------------------------------------------------------------------------
# Map support endpoints (v3.1) — cluster hulls, region labels, heatmap voxels
# ---------------------------------------------------------------------------
# These power the merged unified map tab (see frontend work in next commit):
#   * cluster hulls   → translucent spheres / convex hulls drawn per cluster
#   * region labels   → dim text labels for the 42 canonical ED regions
#   * heatmap voxels  → 200 LY cells carrying mean score, for density mode
# All three are aggregate-only (no per-system PII or auth); cached server-side.
# ---------------------------------------------------------------------------

@router.get('/api/map/regions')
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


@router.get('/api/map/clusters/hulls')
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


@router.get('/api/map/heatmap')
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


@router.get('/api/map/timeline')
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
