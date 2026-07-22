"""Map data endpoints — galaxy regions, cluster hulls, heatmap, timeline."""
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from edfinder_api.config import settings, limiter, log
from edfinder_api.deps import get_pool, get_redis, cache_get, cache_set
from edfinder_api.search_economies import canonical_economy_key, ratings_score_column

router = APIRouter(tags=['map'])

MAX_MAP_HEATMAP_CELLS = 50_000





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
    cached = await cache_get(cache_key, redis)
    if cached is not None:
        return JSONResponse(content=cached)

    async with pool.acquire() as conn:
        # Materialised view path (audit §C4 / Phase 5):
        # mv_map_regions is refreshed nightly by refresh_map_mviews().
        # Cache miss is now O(42) instead of an AVG() over 186M rows.
        # Falls back to the live query only if the MV doesn't exist yet
        # (e.g. first deploy before the migration runs).
        try:
            rows = await conn.fetch(
                'SELECT id, name, x, y, z, system_count FROM mv_map_regions ORDER BY id'
            )
        except asyncpg.exceptions.UndefinedTableError:
            log.warning('mv_map_regions missing; falling back to live AVG()')
            async with conn.transaction():
                await conn.execute("SET LOCAL statement_timeout = '5s'")
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
                """, timeout=10)

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

    await cache_set(cache_key, result, settings.ttl_cluster, redis)
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
    cached = await cache_get(cache_key, redis)
    if cached is not None:
        return JSONResponse(content=cached)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
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
    await cache_set(cache_key, result, settings.ttl_cluster, redis)
    return result


@router.get('/api/map/heatmap')
@limiter.limit('30/minute')
async def map_heatmap(
    request: Request,
    voxel_size:  int = Query(200,  ge=50,  le=2000, description='Voxel cell size in LY'),
    min_systems: int = Query(5,    ge=1,   le=100,  description='Minimum systems per voxel'),
    max_cells:   int = Query(
        MAX_MAP_HEATMAP_CELLS,
        ge=100,
        le=MAX_MAP_HEATMAP_CELLS,
        description='Maximum heatmap cells returned',
    ),
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
    eco_key = None
    if economy:
        eco_key = canonical_economy_key(economy)
        if eco_key is None:
            raise HTTPException(status_code=422, detail=f'Invalid economy: {economy}')
        eco_col = ratings_score_column(eco_key)

    cache_key = f'map:heatmap:v2:{voxel_size}:{min_systems}:{max_cells}:{eco_col or "overall"}'
    cached = await cache_get(cache_key, redis)
    if cached is not None:
        return JSONResponse(content=cached)

    # Audit §C4 / Phase 5: pick the closest pre-aggregated MV resolution
    # to the request's voxel_size. Cache miss is now an indexed read
    # against ~thousands of rows instead of a 186M-row GROUP BY.
    # Available MVs: 200 / 500 / 1000 LY. Smaller voxels round up.
    if voxel_size <= 300:
        _mv = 'mv_map_heatmap_200ly';  _bucket = 200
    elif voxel_size <= 700:
        _mv = 'mv_map_heatmap_500ly';  _bucket = 500
    else:
        _mv = 'mv_map_heatmap_1000ly'; _bucket = 1000

    # eco_col → which max_<eco> column on the MV. None = max_score.
    _eco_col = (
        f'max_{eco_key}' if eco_key else 'max_score'
    )
    _filter_col = (
        f'max_{eco_key}' if eco_key else 'max_score'
    )

    score_col = eco_col or 'score'
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(f"""
                SELECT cx, cy, cz, n,
                       avg_score AS avg_score,
                       {_eco_col} AS max_score
                FROM   {_mv}
                WHERE  n >= $1 AND {_filter_col} IS NOT NULL
                ORDER BY n DESC, cx, cy, cz
                LIMIT $2
            """, min_systems, max_cells + 1)
        except asyncpg.exceptions.UndefinedTableError:
            log.warning('%s missing; falling back to live GROUP BY', _mv)
            # Defence-in-depth: cap heatmap scan at 8 s.
            async with conn.transaction():
                await conn.execute("SET LOCAL statement_timeout = '8s'")
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
                    ORDER BY n DESC, cx, cy, cz
                    LIMIT $3
                """, voxel_size, min_systems, max_cells + 1, timeout=15)

    truncated = len(rows) > max_cells
    bounded_rows = rows[:max_cells]

    result = {
        'voxel_size': voxel_size,
        'voxel_bucket': _bucket,        # actual MV resolution used
        'economy':    economy,
        'cells':      [dict(r) for r in bounded_rows],
        'count':      len(bounded_rows),
        'max_cells':  max_cells,
        'truncated':  truncated,
    }
    await cache_set(cache_key, result, settings.ttl_cluster, redis)
    return result


@router.get('/api/map/timeline')
@limiter.limit('30/minute')
async def map_timeline(
    request: Request,
    bucket:  str  = Query('month', pattern='^(day|week|month|quarter|year)$'),
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
    cached = await cache_get(cache_key, redis)
    if cached is not None:
        return JSONResponse(content=cached)

    async with pool.acquire() as conn:
        # Audit §C4 / Phase 5: read from mv_map_timeline_month
        # (refreshed nightly). Cache miss is now an indexed read instead
        # of DATE_TRUNC + COUNT(*) over 186M rows.
        # The MV is month-bucketed; for week/day requests we re-aggregate
        # below from a window narrower than the full timeline.
        try:
            if bucket == 'month':
                rows = await conn.fetch("""
                    SELECT bucket, systems_discovered
                    FROM mv_map_timeline_month ORDER BY bucket
                """)
            else:
                # Other bucket sizes are computed live, but only over the
                # narrow date range that's actually used in practice (we
                # cap at 5 years for non-month buckets to keep the live
                # query bounded).
                async with conn.transaction():
                    await conn.execute("SET LOCAL statement_timeout = '5s'")
                    rows = await conn.fetch(f"""
                        SELECT
                            DATE_TRUNC('{trunc}', COALESCE(first_discovered_at, updated_at))::date AS bucket,
                            COUNT(*) AS systems_discovered
                        FROM   systems
                        WHERE  COALESCE(first_discovered_at, updated_at)
                                 >= NOW() - INTERVAL '5 years'
                        GROUP BY bucket
                        ORDER BY bucket
                    """, timeout=10)
        except asyncpg.exceptions.UndefinedTableError:
            log.warning('mv_map_timeline_month missing; falling back to live')
            async with conn.transaction():
                await conn.execute("SET LOCAL statement_timeout = '5s'")
                rows = await conn.fetch(f"""
                    SELECT
                        DATE_TRUNC('{trunc}', COALESCE(first_discovered_at, updated_at))::date AS bucket,
                        COUNT(*) AS systems_discovered
                    FROM   systems
                    WHERE  COALESCE(first_discovered_at, updated_at) IS NOT NULL
                    GROUP BY bucket
                    ORDER BY bucket
                """, timeout=10)

    result = {
        'bucket': bucket,
        'points': [
            {'date': r['bucket'].isoformat() if r['bucket'] else None,
             'count': r['systems_discovered']}
            for r in rows
        ],
        'total': sum(r['systems_discovered'] for r in rows),
    }
    await cache_set(cache_key, result, settings.ttl_cluster, redis)
    return result
