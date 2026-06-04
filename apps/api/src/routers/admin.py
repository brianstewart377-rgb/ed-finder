"""Admin + cache-management endpoints.

Every write endpoint in this module is guarded by `require_admin`, which
is disabled entirely unless the ADMIN_TOKEN env var is set. Nginx further
restricts /api/admin/* to 127.0.0.1 as defence in depth.
"""
from datetime import datetime, timezone
from typing   import Any, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from config  import limiter, settings
from deps    import get_pool, get_redis, require_admin
from enrichment_operator_status import (
    read_enrichment_status_snapshot,
    read_warehouse_status_snapshot,
)
from helpers import run_cluster_rebuild
from models  import CacheStatsResponse
from state   import active_jobs, active_jobs_lock, metrics

router = APIRouter(tags=['admin'])


@router.get('/api/cache/stats', response_model=CacheStatsResponse)
async def cache_stats(
    pool:  asyncpg.Pool              = Depends(get_pool),
    redis: Optional[aioredis.Redis]  = Depends(get_redis),
):
    stats: dict[str, Any] = {
        'cache_hits':   metrics['cache_hits'],
        'cache_misses': metrics['cache_misses'],
    }
    if redis:
        try:
            info = await redis.info('stats')
            stats['redis_hits']      = info.get('keyspace_hits', 0)
            stats['redis_misses']    = info.get('keyspace_misses', 0)
            stats['redis_memory_mb'] = round(
                int((await redis.info('memory')).get('used_memory', 0)) / 1e6, 1
            )
        except Exception:
            pass
    async with pool.acquire() as conn:
        stats['db_cache_rows'] = await conn.fetchval(
            'SELECT COUNT(*) FROM api_cache WHERE expires_at > NOW()'
        )
    return stats


@router.post('/api/cache/clear', dependencies=[Depends(require_admin)])
async def cache_clear(
    pool:  asyncpg.Pool              = Depends(get_pool),
    redis: Optional[aioredis.Redis]  = Depends(get_redis),
):
    """Flush ED Finder cache keys + expired api_cache rows. X-Admin-Token required.

    Audit fix (2026-05-08, AUDIT_REPORT.md §L9): previously this called
    `redis.flushdb()` which also wiped slowapi rate-limit keys, briefly
    disabling per-IP throttling right after a flush. Now we SCAN+DEL
    only the cache prefixes we own.
    """
    deleted = 0
    if redis:
        try:
            # Cache key prefixes used by ED Finder routers (status, search,
            # autocomplete, system, body, galaxy, cluster, map, og).
            patterns = (
                'status:*', 'search:*', 'ac:*', 'sys:*', 'body:*',
                'galaxy:*', 'cluster:*', 'map:*', 'og:*',
            )
            for pattern in patterns:
                async for key in redis.scan_iter(match=pattern, count=500):
                    await redis.delete(key)
                    deleted += 1
        except Exception:
            pass
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM api_cache WHERE expires_at <= NOW()')
    return {'ok': True, 'message': f'Cache cleared ({deleted} Redis keys removed)'}


@router.post('/api/admin/rebuild-clusters', dependencies=[Depends(require_admin)])
@limiter.limit('1/minute')
async def trigger_rebuild_clusters(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Kick a background cluster rebuild (dirty anchors only).

    Returns 409 if a rebuild is already running. X-Admin-Token required.
    """
    job_id = 'cluster_rebuild'
    async with active_jobs_lock:
        current = active_jobs.get(job_id, {})
        if current.get('status') == 'running':
            return JSONResponse(
                status_code=409,
                content={
                    'message': 'A cluster rebuild is already in progress.',
                    'job': current,
                },
            )
        # Claim the slot before the task runs so concurrent requests 409 cleanly.
        active_jobs[job_id] = {
            'status':     'running',
            'start_time': datetime.now(timezone.utc).isoformat(),
            'end_time':   None,
            'exit_code':  None,
            'error':      None,
        }

    background_tasks.add_task(run_cluster_rebuild, active_jobs)
    return {'message': 'Cluster rebuild triggered in background.', 'job_id': job_id}


@router.post('/api/admin/rebuild-ratings', dependencies=[Depends(require_admin)])
@limiter.limit('1/minute')
async def trigger_rebuild_ratings(request: Request):
    """Recompute ratings for systems flagged as `rating_dirty`.

    For the preview pod this runs synchronously on a tiny dataset
    (~40 systems). Production should swap in the real pipeline that
    walks bodies/stations and recomputes the per-economy scores.
    Rate-limited to 1/min and X-Admin-Token gated.
    """
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        # Pick everything flagged dirty (or, if nothing's dirty, everything —
        # makes the button useful even on a clean DB for forced refresh).
        dirty = await conn.fetchval(
            "SELECT COUNT(*) FROM systems WHERE rating_dirty = true"
        )
        target_clause = (
            'WHERE r.system_id64 IN (SELECT id64 FROM systems WHERE rating_dirty = true)'
            if dirty else ''
        )
        await conn.execute(
            f"""
            UPDATE ratings r SET
              score_agriculture = LEAST(98, GREATEST(20,
                  25 + CASE WHEN s.primary_economy = 'Agriculture' THEN 55 ELSE 0 END
                     + CASE WHEN s.security = 'High' THEN 8 ELSE 0 END
                     + LEAST(15, s.body_count * 2)
                     - CASE WHEN s.primary_economy = 'Industrial' THEN 18 ELSE 0 END))::smallint,
              score_refinery    = LEAST(98, GREATEST(20,
                  30 + CASE WHEN s.primary_economy = 'Refinery' THEN 55 ELSE 0 END
                     + LEAST(20, s.body_count * 2)
                     + CASE WHEN s.allegiance = 'Federation' THEN 6 ELSE 0 END))::smallint,
              score_industrial  = LEAST(98, GREATEST(15,
                  28 + CASE WHEN s.primary_economy = 'Industrial' THEN 60 ELSE 0 END
                     + CASE WHEN s.population > 1000000 THEN 12 ELSE 0 END
                     - CASE WHEN s.primary_economy = 'Tourism' THEN 22 ELSE 0 END))::smallint,
              score_hightech    = LEAST(98, GREATEST(15,
                  22 + CASE WHEN s.primary_economy = 'HighTech' THEN 65 ELSE 0 END
                     + CASE WHEN s.population > 100000000 THEN 14 ELSE 0 END
                     + CASE WHEN s.allegiance = 'Empire' THEN 8 ELSE 0 END))::smallint,
              score_military    = LEAST(95, GREATEST(15,
                  20 + CASE WHEN s.primary_economy = 'Military'   THEN 55 ELSE 0 END
                     + CASE WHEN s.allegiance = 'Empire' THEN 16 ELSE 0 END
                     + CASE WHEN s.allegiance = 'Federation' THEN 12 ELSE 0 END
                     + CASE WHEN s.security = 'High' THEN 8 ELSE 0 END))::smallint,
              score_tourism     = LEAST(98, GREATEST(15,
                  18 + CASE WHEN s.primary_economy = 'Tourism' THEN 60 ELSE 0 END
                     + CASE WHEN s.galaxy_region_id = 1 THEN 22 ELSE 0 END
                     - CASE WHEN s.primary_economy = 'Industrial' THEN 18 ELSE 0 END))::smallint
            FROM systems s
            WHERE r.system_id64 = s.id64
              {('AND r.system_id64 IN (SELECT id64 FROM systems WHERE rating_dirty = true)') if dirty else ''}
            """
        )
        # Recompute composite "score" = max of dimension scores.
        await conn.execute(
            f"""
            UPDATE ratings r SET score = GREATEST(
              COALESCE(r.score_agriculture,0), COALESCE(r.score_refinery,0),
              COALESCE(r.score_industrial,0),  COALESCE(r.score_hightech,0),
              COALESCE(r.score_military,0),    COALESCE(r.score_tourism,0)
            )::smallint
            {target_clause}
            """
        )
        # Clear the dirty flag.
        cleared = await conn.execute(
            "UPDATE systems SET rating_dirty = false WHERE rating_dirty = true"
        )
        n_cleared = int(cleared.split()[-1]) if cleared else 0

    return {
        'ok':           True,
        'message':      f'Rebuilt ratings for {dirty if dirty else "all"} systems'
                        + (f', cleared {n_cleared} dirty flags' if n_cleared else ''),
        'dirty_before': dirty,
        'cleared':      n_cleared,
    }


@router.get(
    '/api/admin/enrichment/station-status',
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def station_enrichment_operator_status():
    """Return a sanitized read-only station enrichment status snapshot.

    This endpoint deliberately reads only a configured JSON artifact produced
    by `station_enrichment_status.py --json`. It never invokes the enrichment
    script, Docker, EDSM, or the database.
    """
    return read_enrichment_status_snapshot(settings.enrichment_status_json_path)


@router.get(
    '/api/admin/enrichment/warehouse-status',
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def warehouse_enrichment_operator_status():
    """Return a sanitized read-only warehouse reconciliation/status snapshot.

    This endpoint reads only a configured JSON artifact. It never runs
    warehouse importer scripts, Docker, live APIs, or database queries.
    """
    return read_warehouse_status_snapshot(settings.enrichment_warehouse_status_json_path)

@router.get(
    '/api/admin/data-status',
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def admin_data_status(pool: asyncpg.Pool = Depends(get_pool)):
    """Return a read-only admin snapshot of core data status.

    This endpoint is intentionally status-only. It runs inside a read-only
    database transaction and does not perform imports, migrations, station-type
    writes, canonical writes, or canonical apply.
    """
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            transaction_read_only = await conn.fetchval('SHOW transaction_read_only')

            station_counts = dict(await conn.fetchrow(
                """
                SELECT
                  COUNT(*)::int AS total_station_rows,
                  COUNT(*) FILTER (WHERE station_type::text = 'Unknown')::int AS unknown_station_rows,
                  COUNT(*) FILTER (WHERE station_type::text = 'Coriolis')::int AS coriolis_station_rows,
                  COUNT(*) FILTER (WHERE station_type::text = 'Dodec')::int AS dodec_station_rows,
                  COUNT(*) FILTER (WHERE station_type_source IS NOT NULL)::int AS rows_with_station_type_source
                FROM stations
                """
            ))

            station_type_counts = [
                dict(row)
                for row in await conn.fetch(
                    """
                    SELECT
                      station_type::text AS station_type,
                      COUNT(*)::int AS rows
                    FROM stations
                    GROUP BY station_type
                    ORDER BY station_type
                    """
                )
            ]

            station_type_source_counts = [
                dict(row)
                for row in await conn.fetch(
                    """
                    SELECT
                      COALESCE(station_type_source, 'NULL') AS station_type_source,
                      station_type::text AS station_type,
                      COUNT(*)::int AS rows
                    FROM stations
                    GROUP BY station_type_source, station_type
                    ORDER BY station_type_source, station_type
                    """
                )
            ]

            identity_counts = dict(await conn.fetchrow(
                """
                SELECT
                  COUNT(*)::int AS total_identity_rows,
                  COUNT(*) FILTER (WHERE identity_status = 'confirmed')::int AS confirmed_identity_rows,
                  COUNT(*) FILTER (WHERE conflict_reason IS NOT NULL)::int AS rows_with_conflict_reason,
                  COUNT(*) FILTER (WHERE edsm_station_id IS NOT NULL)::int AS rows_with_edsm_station_id,
                  COUNT(*) FILTER (WHERE market_id IS NOT NULL)::int AS rows_with_market_id
                FROM station_external_identity
                """
            ))

            identity_source_status_counts = [
                dict(row)
                for row in await conn.fetch(
                    """
                    SELECT
                      source,
                      identity_status,
                      COUNT(*)::int AS rows
                    FROM station_external_identity
                    GROUP BY source, identity_status
                    ORDER BY source, identity_status
                    """
                )
            ]

            unknown_station_source_counts = [
                dict(row)
                for row in await conn.fetch(
                    """
                    SELECT
                      stg.station_type::text AS source_station_type,
                      COUNT(*)::int AS rows
                    FROM station_external_identity sei
                    JOIN stations s
                      ON s.id = sei.canonical_station_id
                    JOIN public.staging_edsm_stations stg
                      ON stg.edsm_station_id = sei.edsm_station_id
                    WHERE sei.identity_status = 'confirmed'
                      AND s.station_type = 'Unknown'
                    GROUP BY stg.station_type
                    ORDER BY rows DESC, source_station_type NULLS FIRST
                    """
                )
            ]

            recent_station_type_updates = [
                dict(row)
                for row in await conn.fetch(
                    """
                    SELECT
                      id AS canonical_station_id,
                      name AS canonical_station_name,
                      system_id64,
                      station_type::text AS station_type,
                      station_type_source,
                      station_type_updated_at
                    FROM stations
                    WHERE station_type_source IS NOT NULL
                    ORDER BY station_type_updated_at DESC NULLS LAST, id
                    LIMIT 20
                    """
                )
            ]

    return {
        'schema_version': 'admin_data_status/v1',
        'read_only': True,
        'transaction_read_only': transaction_read_only,
        'station_counts': station_counts,
        'station_type_counts': station_type_counts,
        'station_type_source_counts': station_type_source_counts,
        'identity_counts': identity_counts,
        'identity_source_status_counts': identity_source_status_counts,
        'unknown_station_source_counts': unknown_station_source_counts,
        'recent_station_type_updates': recent_station_type_updates,
        'policy_summary': {
            'dodec_supported': station_counts.get('dodec_station_rows', 0) > 0,
            'fleet_carriers_remain_unknown': any(
                row.get('source_station_type') == 'Drake-Class Carrier'
                for row in unknown_station_source_counts
            ),
            'construction_depots_remain_unknown': any(
                row.get('source_station_type') == 'Space Construction Depot'
                for row in unknown_station_source_counts
            ),
        },
        'safety_summary': {
            'db_read_only_confirmed': transaction_read_only == 'on',
            'db_writes_performed': False,
            'migrations_performed': False,
            'station_type_writes_performed': False,
            'canonical_apply_performed': False,
        },
    }

