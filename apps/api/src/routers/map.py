"""Map data endpoints — galaxy regions, cluster hulls, heatmap, timeline."""
import math
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from edfinder_api.config import settings, limiter, log
from edfinder_api.deps import get_pool, get_redis, cache_get, cache_set
from edfinder_api.models import MapViewportResponse, MapViewportSystem
from edfinder_api.search_economies import canonical_economy_key, ratings_score_column
from edfinder_api.v3_schema import current_generation_schema

router = APIRouter(tags=['map'])

MAX_MAP_HEATMAP_CELLS = 50_000

# The reconciled v3 spatial density pyramid's derived-product code
# (scripts/v3_spatial_pyramid.py:PRODUCT_CODE). Kept as a literal here rather
# than imported: apps/api ships independently of the repo-tooling `scripts/`
# package (its own uv env/pyproject), so the two must stay in sync by
# convention, same as other product codes referenced across that boundary.
SPATIAL_PYRAMID_PRODUCT_CODE = 'spatial_pyramid'

# Real-star viewport lane (the zoom-in detail lane; heatmap is the aggregate lane).
MAX_MAP_VIEWPORT_SYSTEMS = 40_000   # hard cap on individual systems per viewport
MAX_MAP_VIEWPORT_LY = 15_000        # per-axis box guard; wider -> stay on the heatmap

# Whole-galaxy starfield lane. The production heatmap MVs are not populated on
# the V3 canonical schema yet, so a wide view falls back to a bounded page
# sample of real canonical systems. Positions are never fabricated; this is a
# viewport sample, not a synthetic density layer.
MAX_GALAXY_SAMPLE_SYSTEMS = 40_000
GALAXY_SAMPLE_PERCENT = 0.05





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


async def _current_spatial_pyramid(conn: asyncpg.Connection) -> Optional[asyncpg.Record]:
    """Resolve the active reconciled spatial density pyramid: the
    `spatial_pyramid` `v3_meta.derived_product` (lifecycle_state='READY')
    belonging to the current *published* `v3_meta.derived_generation`.

    Mirrors `apps/api/src/routers/ratings_v4.py:_current`'s join (current
    pointer + PUBLISHED generation), additionally joined to the pyramid
    product exactly as
    `scripts/v3_spatial_pyramid.py:pyramid_for_current_generation` does.
    Returns `None` -- meaning "serve the legacy fallback" -- both when the
    v3_meta/v3_spatial schema is entirely absent (pre-migration DB) and when
    nothing currently qualifies.
    """
    try:
        return await conn.fetchrow(
            '''SELECT c.derived_generation_id,
                      p.product_version AS spatial_pyramid_version,
                      p.expected_rows AS source_system_count,
                      p.validated_at AS coverage_at
                 FROM v3_meta.current_derived_generation c
                 JOIN v3_meta.derived_generation d USING (derived_generation_id)
                 JOIN v3_meta.derived_product p
                   ON p.derived_generation_id = c.derived_generation_id
                  AND p.product_code = $1
                WHERE d.lifecycle_state = 'PUBLISHED'
                  AND p.lifecycle_state = 'READY' ''',
            SPATIAL_PYRAMID_PRODUCT_CODE,
        )
    except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.InvalidSchemaNameError):
        return None


async def _pyramid_level(conn: asyncpg.Connection, version: str, voxel_size: int) -> Optional[asyncpg.Record]:
    """Pick the registered `v3_spatial.cell_level` row whose `cell_size_ly`
    best matches the request's `voxel_size`, for the pyramid's own version --
    the query-time level choice the design doc calls for (semantic scale +
    budget; the level ladder itself is Task 7's benchmarking concern, not
    this read path's).
    """
    return await conn.fetchrow(
        '''SELECT level, cell_size_ly
             FROM v3_spatial.cell_level
            WHERE spatial_pyramid_version = $1
            ORDER BY abs(cell_size_ly - $2)
            LIMIT 1''',
        version, float(voxel_size),
    )


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
    min_x: Optional[float] = Query(None, description='Bounds min X (LY); omitted = whole galaxy'),
    max_x: Optional[float] = Query(None, description='Bounds max X (LY); omitted = whole galaxy'),
    min_y: Optional[float] = Query(None, description='Bounds min Y (LY); omitted = whole galaxy'),
    max_y: Optional[float] = Query(None, description='Bounds max Y (LY); omitted = whole galaxy'),
    min_z: Optional[float] = Query(None, description='Bounds min Z (LY); omitted = whole galaxy'),
    max_z: Optional[float] = Query(None, description='Bounds max Z (LY); omitted = whole galaxy'),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """Density-pyramid-aggregated heatmap for map rendering.

    Reads `v3_spatial.cell_summary` for the reconciled, generation-pinned
    density pyramid of the current *published* derived generation (bounded
    by the optional viewport box, at a level chosen to match `voxel_size`,
    capped at `max_cells` with an honest `truncated` flag) whenever one is
    published and READY, tagged `"source": "pyramid"`.

    Ratings are excluded from that pyramid's truth gate (it is a physical
    density product, not a rated one), so an `economy`-scored request cannot
    be served from it; that request -- and any request made before a pyramid
    has ever been published -- instead uses the legacy rated-MV/live-
    aggregate lane this endpoint has always served, tagged explicitly
    `"source": "legacy-fallback"` so callers can tell them apart.
    """
    eco_col = None
    eco_key = None
    if economy:
        eco_key = canonical_economy_key(economy)
        if eco_key is None:
            raise HTTPException(status_code=422, detail=f'Invalid economy: {economy}')
        eco_col = ratings_score_column(eco_key)

    bounds = {
        'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y,
        'min_z': min_z, 'max_z': max_z,
    }
    bounds_key = ':'.join('x' if v is None else f'{v:.3f}' for v in bounds.values())

    cache_key = (
        f'map:heatmap:v3:{voxel_size}:{min_systems}:{max_cells}:'
        f'{eco_col or "overall"}:{bounds_key}'
    )
    cached = await cache_get(cache_key, redis)
    if cached is not None:
        return JSONResponse(content=cached)

    # Ratings are neither an input nor a filter to the pyramid's base density
    # (design doc "Truth gate"), so an economy-scored request is routed
    # straight to the legacy lane rather than silently ignoring the filter.
    pyramid = None
    level_row = None
    if economy is None:
        async with pool.acquire() as conn:
            pyramid = await _current_spatial_pyramid(conn)
            if pyramid is not None:
                level_row = await _pyramid_level(conn, pyramid['spatial_pyramid_version'], voxel_size)
                if level_row is None:
                    log.warning(
                        'spatial pyramid %s has no registered cell_level; falling back to legacy heatmap',
                        pyramid['spatial_pyramid_version'],
                    )
                    pyramid = None

    if pyramid is not None:
        conditions = [
            'derived_generation_id = $1', 'spatial_pyramid_version = $2',
            'level = $3', 'system_count >= $4',
        ]
        args: list = [
            pyramid['derived_generation_id'], pyramid['spatial_pyramid_version'],
            level_row['level'], min_systems,
        ]

        def _add_bound(column: str, value: Optional[float], op: str) -> None:
            if value is None:
                return
            args.append(value)
            conditions.append(f'{column} {op} ${len(args)}')

        _add_bound('centroid_x_ly', min_x, '>=')
        _add_bound('centroid_x_ly', max_x, '<=')
        _add_bound('centroid_y_ly', min_y, '>=')
        _add_bound('centroid_y_ly', max_y, '<=')
        _add_bound('centroid_z_ly', min_z, '>=')
        _add_bound('centroid_z_ly', max_z, '<=')

        args.append(max_cells + 1)
        where_clause = ' AND '.join(conditions)

        async with pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT origin_x_ly, origin_y_ly, origin_z_ly,
                       centroid_x_ly, centroid_y_ly, centroid_z_ly,
                       system_count, landable_count, station_count,
                       biological_system_count, terraformable_system_count
                  FROM v3_spatial.cell_summary
                 WHERE {where_clause}
                 ORDER BY system_count DESC, origin_x_ly, origin_y_ly, origin_z_ly
                 LIMIT ${len(args)}
            """, *args)

        truncated = len(rows) > max_cells
        bounded_rows = rows[:max_cells]
        coverage_at = pyramid['coverage_at']

        result = {
            'source': 'pyramid',
            'generation_id': str(pyramid['derived_generation_id']),
            'spatial_pyramid_version': pyramid['spatial_pyramid_version'],
            'source_system_count': pyramid['source_system_count'],
            'coverage_at': coverage_at.isoformat() if coverage_at else None,
            'level': level_row['level'],
            'cell_size_ly': level_row['cell_size_ly'],
            'voxel_size': voxel_size,
            'bounds': bounds,
            'cells': [dict(r) for r in bounded_rows],
            'count': len(bounded_rows),
            'max_cells': max_cells,
            'truncated': truncated,
        }
        await cache_set(cache_key, result, settings.ttl_cluster, redis)
        return result

    # --- Legacy fallback: no current published generation has a READY
    # spatial pyramid yet (or an economy filter was requested, which the
    # pyramid's truth gate cannot serve) -- keep the existing rated-MV/
    # live-aggregate lane, tagged explicitly so callers can tell they are
    # not reading the reconciled pyramid.
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
        'source': 'legacy-fallback',
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
        cache_key = (
            f'map:systems:sample:v3:{lo_x:.0f}:{hi_x:.0f}:{lo_y:.0f}:{hi_y:.0f}:'
            f'{lo_z:.0f}:{hi_z:.0f}:{limit}'
        )
        cached = await cache_get(cache_key, redis)
        if cached is not None:
            return JSONResponse(content=cached)

        try:
            schema = await current_generation_schema(pool)
        except asyncpg.exceptions.UndefinedTableError:
            schema = None

        async with pool.acquire() as conn:
            if schema is None:
                rows = await conn.fetch("""
                    SELECT id64, name, x, y, z, main_star_type, galaxy_region_id,
                           (population IS NOT NULL AND population > 0) AS populated
                    FROM   systems TABLESAMPLE SYSTEM ($1::float4)
                    WHERE  x BETWEEN $2 AND $3
                      AND  y BETWEEN $4 AND $5
                      AND  z BETWEEN $6 AND $7
                    ORDER BY md5(id64::text)
                    LIMIT  $8
                """, GALAXY_SAMPLE_PERCENT, lo_x, hi_x, lo_y, hi_y, lo_z, hi_z,
                    min(limit, MAX_GALAXY_SAMPLE_SYSTEMS))
            else:
                rows = await conn.fetch(f"""
                    SELECT s.id64, s.name, s.x_ly AS x, s.y_ly AS y,
                           s.z_ly AS z, s.galaxy_region_id,
                           FALSE AS populated,
                           body.spectral_class AS main_star_type
                      FROM {schema}.systems s TABLESAMPLE SYSTEM ($1::float4)
                      LEFT JOIN LATERAL (
                        SELECT b.spectral_class
                          FROM {schema}.bodies b
                         WHERE b.system_id64 = s.id64
                           AND b.is_main_star
                         ORDER BY b.body_pk
                         LIMIT 1
                      ) body ON TRUE
                     WHERE s.x_ly BETWEEN $2 AND $3
                       AND s.y_ly BETWEEN $4 AND $5
                       AND s.z_ly BETWEEN $6 AND $7
                     ORDER BY md5(s.id64::text)
                     LIMIT  $8
                """, GALAXY_SAMPLE_PERCENT, lo_x, hi_x, lo_y, hi_y, lo_z, hi_z,
                    min(limit, MAX_GALAXY_SAMPLE_SYSTEMS))

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
        result = MapViewportResponse(systems=systems, truncated=True)
        await cache_set(cache_key, result.model_dump(mode='json'), settings.ttl_cluster, redis)
        return result

    cache_key = (
        f'map:systems:v3:{lo_x:.0f}:{hi_x:.0f}:{lo_y:.0f}:{hi_y:.0f}:'
        f'{lo_z:.0f}:{hi_z:.0f}:{limit}'
    )
    cached = await cache_get(cache_key, redis)
    if cached is not None:
        return JSONResponse(content=cached)

    try:
        schema = await current_generation_schema(pool)
    except asyncpg.exceptions.UndefinedTableError:
        # Review and integration databases still use the legacy unqualified
        # catalogue. Production resolves the published V3 generation schema.
        schema = None

    async with pool.acquire() as conn:
        if schema is None:
            rows = await conn.fetch("""
                WITH candidates AS MATERIALIZED (
                    SELECT id64, name, x, y, z, main_star_type, galaxy_region_id,
                           (population IS NOT NULL AND population > 0) AS populated
                    FROM   systems
                    WHERE  x BETWEEN $1 AND $2
                      AND  y BETWEEN $3 AND $4
                      AND  z BETWEEN $5 AND $6
                    ORDER BY x, y, z
                    LIMIT  $7
                )
                SELECT id64, name, x, y, z, main_star_type, galaxy_region_id, populated
                FROM   candidates
                ORDER BY populated DESC,
                         CASE left(main_star_type, 1)
                            WHEN 'O' THEN 0 WHEN 'B' THEN 1 WHEN 'A' THEN 2
                            WHEN 'F' THEN 3 WHEN 'G' THEN 4 WHEN 'K' THEN 5
                            WHEN 'M' THEN 6 ELSE 7 END,
                         id64
            """, lo_x, hi_x, lo_y, hi_y, lo_z, hi_z, limit + 1)
        else:
            rows = await conn.fetch(f"""
                SELECT s.id64, s.name, s.x_ly AS x, s.y_ly AS y, s.z_ly AS z,
                       s.galaxy_region_id,
                       FALSE AS populated,
                       body.spectral_class AS main_star_type
                  FROM {schema}.systems s
                  LEFT JOIN LATERAL (
                    SELECT b.spectral_class
                      FROM {schema}.bodies b
                     WHERE b.system_id64 = s.id64
                       AND b.is_main_star
                     ORDER BY b.body_pk
                     LIMIT 1
                  ) body ON TRUE
                 WHERE s.grid_x BETWEEN $1 AND $2
                   AND s.grid_y BETWEEN $3 AND $4
                   AND s.grid_z BETWEEN $5 AND $6
                   AND s.x_ly BETWEEN $7 AND $8
                   AND s.y_ly BETWEEN $9 AND $10
                   AND s.z_ly BETWEEN $11 AND $12
                 ORDER BY s.id64
                 LIMIT $13
            """,
                math.floor(lo_x / 10), math.floor(hi_x / 10),
                math.floor(lo_y / 10), math.floor(hi_y / 10),
                math.floor(lo_z / 10), math.floor(hi_z / 10),
                lo_x, hi_x, lo_y, hi_y, lo_z, hi_z, limit + 1)

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
