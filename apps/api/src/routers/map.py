"""Map data endpoints — galaxy regions, cluster hulls, heatmap, timeline."""
import hashlib
import math
import re
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from edfinder_api.config import settings, limiter, log
from edfinder_api.deps import get_pool, get_redis, cache_get, cache_set
from edfinder_api.models import MapViewportResponse, MapViewportSystem
from edfinder_api.search_economies import canonical_economy_key, ratings_score_column

router = APIRouter(tags=['map'])

MAX_MAP_HEATMAP_CELLS = 50_000

# Real-star viewport lane (the zoom-in detail lane; heatmap is the aggregate lane).
MAX_MAP_VIEWPORT_SYSTEMS = 40_000   # hard cap on individual systems per viewport
MAX_MAP_VIEWPORT_LY = 15_000        # per-axis box guard; wider -> stay on the heatmap
MAX_V3_MAP_GRID_CELLS = 50_000      # bounded 10 LY cells resolved through the serving index
V3_GRID_EDGE_LY = 10.0
_V3_SCHEMA = re.compile(r'^v3_gen_[a-z][a-z0-9_]{0,30}$')


def _macro_grid_key(grid_x: int, grid_y: int, grid_z: int) -> int:
    """Return the canonical importer's stable 10 LY cell identity."""
    raw = '\x1f'.join(
        str(part) for part in ('macro-grid-v1', grid_x, grid_y, grid_z)
    ).encode('utf-8')
    value = int.from_bytes(hashlib.sha256(raw).digest()[:8], 'big') & ((1 << 63) - 1)
    return value or 1


def _v3_grid_keys(
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    lo_z: float,
    hi_z: float,
) -> list[int] | None:
    ranges = [
        range(math.floor(lo_x / V3_GRID_EDGE_LY), math.floor(hi_x / V3_GRID_EDGE_LY) + 1),
        range(math.floor(lo_y / V3_GRID_EDGE_LY), math.floor(hi_y / V3_GRID_EDGE_LY) + 1),
        range(math.floor(lo_z / V3_GRID_EDGE_LY), math.floor(hi_z / V3_GRID_EDGE_LY) + 1),
    ]
    cell_count = len(ranges[0]) * len(ranges[1]) * len(ranges[2])
    if cell_count > MAX_V3_MAP_GRID_CELLS:
        return None
    return [
        _macro_grid_key(grid_x, grid_y, grid_z)
        for grid_x in ranges[0]
        for grid_y in ranges[1]
        for grid_z in ranges[2]
    ]


async def _published_v3_schema(conn: asyncpg.Connection) -> str | None:
    """Resolve the published V3 generation, or ``None`` on a legacy database."""
    has_pointer = await conn.fetchval(
        "SELECT to_regclass('v3_meta.current_canonical_generation') IS NOT NULL"
    )
    if not has_pointer:
        return None
    row = await conn.fetchrow(
        '''
        SELECT generation.relation_schema
          FROM v3_meta.current_canonical_generation current
          JOIN v3_meta.canonical_generation generation USING (generation_id)
         WHERE current.singleton
        '''
    )
    if row is None:
        raise HTTPException(503, 'No published V3 canonical generation')
    schema = str(row['relation_schema'])
    if not _V3_SCHEMA.fullmatch(schema):
        raise HTTPException(500, 'Unsafe canonical generation relation schema')
    return schema





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


@router.get('/api/map/systems', response_model=MapViewportResponse)
@limiter.limit('60/minute')
async def map_systems(
    request: Request,
    min_x: float = Query(..., description='Viewport bounding-box min X (LY)'),
    max_x: float = Query(..., description='Viewport bounding-box max X (LY)'),
    min_y: float = Query(..., description='Viewport bounding-box min Y (LY)'),
    max_y: float = Query(..., description='Viewport bounding-box max Y (LY)'),
    min_z: float = Query(..., description='Viewport bounding-box min Z (LY)'),
    max_z: float = Query(..., description='Viewport bounding-box max Z (LY)'),
    limit: int = Query(
        10_000, ge=1, le=MAX_MAP_VIEWPORT_SYSTEMS,
        description='Maximum individual systems returned',
    ),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
) -> MapViewportResponse:
    """Individual star systems within a viewport bounding box — the zoom-in
    real-star detail lane (the heatmap is the zoomed-out aggregate lane).

    Read-only. Returns up to `limit` systems ordered notable-first (populated,
    then by star-brightness proxy from spectral class), so the important stars
    appear first at partial zoom and fill in as you zoom deeper. An over-wide
    box is rejected with `too_wide=True` (the client should stay on the heatmap)
    rather than forcing a whole-galaxy scan.
    """
    # Tolerate min/max sent in either order.
    lo_x, hi_x = sorted((min_x, max_x))
    lo_y, hi_y = sorted((min_y, max_y))
    lo_z, hi_z = sorted((min_z, max_z))

    if ((hi_x - lo_x) > MAX_MAP_VIEWPORT_LY
            or (hi_y - lo_y) > MAX_MAP_VIEWPORT_LY
            or (hi_z - lo_z) > MAX_MAP_VIEWPORT_LY):
        return MapViewportResponse(systems=[], truncated=False)

    async with pool.acquire() as conn:
        v3_schema = await _published_v3_schema(conn)

    grid_keys = (
        _v3_grid_keys(lo_x, hi_x, lo_y, hi_y, lo_z, hi_z)
        if v3_schema is not None else None
    )
    # The V3 canonical catalogue deliberately exposes only its bounded 10 LY
    # serving index. Wide views stay on the aggregate density lane instead of
    # degrading into a scan of the 198M-row generation.
    if v3_schema is not None and grid_keys is None:
        return MapViewportResponse(systems=[], truncated=False)

    cache_key = (
        f'map:systems:v4:{v3_schema or "legacy"}:{lo_x:.0f}:{hi_x:.0f}:'
        f'{lo_y:.0f}:{hi_y:.0f}:'
        f'{lo_z:.0f}:{hi_z:.0f}:{limit}'
    )
    cached = await cache_get(cache_key, redis)
    if cached is not None:
        return JSONResponse(content=cached)

    async with pool.acquire() as conn:
        if v3_schema is not None:
            rows = await conn.fetch(f"""
                WITH candidates AS MATERIALIZED (
                    SELECT system.id64, system.name,
                           system.x_ly AS x, system.y_ly AS y, system.z_ly AS z,
                           star.spectral_class AS main_star_type,
                           system.galaxy_region_id,
                           EXISTS (
                               SELECT 1 FROM {v3_schema}.stations station
                                WHERE station.system_id64 = system.id64
                                  AND station.lifecycle_state = 'ACTIVE'
                           ) AS populated
                      FROM {v3_schema}.systems system
                      LEFT JOIN LATERAL (
                          SELECT body.spectral_class
                            FROM {v3_schema}.bodies body
                           WHERE body.system_id64 = system.id64
                             AND body.is_main_star IS TRUE
                             AND body.lifecycle_state = 'ACTIVE'
                           ORDER BY body.body_pk
                           LIMIT 1
                      ) star ON TRUE
                     WHERE system.macro_grid_key = ANY($7::bigint[])
                       AND system.lifecycle_state = 'ACTIVE'
                       AND system.x_ly BETWEEN $1 AND $2
                       AND system.y_ly BETWEEN $3 AND $4
                       AND system.z_ly BETWEEN $5 AND $6
                     ORDER BY system.x_ly, system.y_ly, system.z_ly
                     LIMIT $8
                )
                SELECT id64, name, x, y, z, main_star_type, galaxy_region_id, populated
                  FROM candidates
                 ORDER BY populated DESC,
                          CASE left(main_star_type, 1)
                             WHEN 'O' THEN 0 WHEN 'B' THEN 1 WHEN 'A' THEN 2
                             WHEN 'F' THEN 3 WHEN 'G' THEN 4 WHEN 'K' THEN 5
                             WHEN 'M' THEN 6 ELSE 7 END,
                          id64
            """, lo_x, hi_x, lo_y, hi_y, lo_z, hi_z, grid_keys, limit + 1)
        else:
            rows = await conn.fetch("""
                WITH candidates AS MATERIALIZED (
                    SELECT id64, name, x, y, z, main_star_type, galaxy_region_id,
                           (population IS NOT NULL AND population > 0) AS populated
                    FROM systems
                    WHERE x BETWEEN $1 AND $2
                      AND y BETWEEN $3 AND $4
                      AND z BETWEEN $5 AND $6
                    ORDER BY x, y, z
                    LIMIT $7
                )
                SELECT id64, name, x, y, z, main_star_type, galaxy_region_id, populated
                FROM candidates
                ORDER BY populated DESC,
                         CASE left(main_star_type, 1)
                            WHEN 'O' THEN 0 WHEN 'B' THEN 1 WHEN 'A' THEN 2
                            WHEN 'F' THEN 3 WHEN 'G' THEN 4 WHEN 'K' THEN 5
                            WHEN 'M' THEN 6 ELSE 7 END,
                         id64
            """, lo_x, hi_x, lo_y, hi_y, lo_z, hi_z, limit + 1)

    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]

    systems = [
        MapViewportSystem(
            id64=r['id64'],
            name=r['name'],
            x=r['x'],
            y=r['y'],
            z=r['z'],
            main_star_class=r['main_star_type'],
            populated=r['populated'],
        )
        for r in rows
    ]
    result = MapViewportResponse(systems=systems, truncated=truncated)
    await cache_set(cache_key, result.model_dump(), settings.ttl_search, redis)
    return result
