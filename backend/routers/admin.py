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

from config  import limiter
from deps    import get_pool, get_redis, require_admin
from helpers import run_cluster_rebuild
from state   import active_jobs, active_jobs_lock, metrics

router = APIRouter(tags=['admin'])


@router.get('/api/cache/stats')
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
    """Flush Redis + expired api_cache rows. X-Admin-Token required."""
    if redis:
        try:
            await redis.flushdb()
        except Exception:
            pass
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM api_cache WHERE expires_at <= NOW()')
    return {'ok': True, 'message': 'Cache cleared'}


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
