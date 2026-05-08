"""FastAPI dependencies + shared cache helpers.

Routers do:

    from deps import get_pool, get_redis
    @router.get(...)
    async def endpoint(pool = Depends(get_pool), redis = Depends(get_redis)):
        ...

`require_admin` is both a reusable Depends and a sentinel — it raises 403
if no ADMIN_TOKEN env var is set, so admin endpoints are disabled by
default.
"""
from __future__ import annotations

import hmac
import json
import logging
from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import HTTPException, Request

from config   import settings
from state    import (
    get_pool_singleton, get_redis_singleton, metrics,
)

log = logging.getLogger('ed_finder')


# ── DB / cache providers for Depends() ──────────────────────────────────
async def get_pool() -> asyncpg.Pool:
    pool = get_pool_singleton()
    if pool is None:
        raise HTTPException(503, 'Database pool not initialised')
    return pool


async def get_redis() -> Optional[aioredis.Redis]:
    return get_redis_singleton()


# ── Admin bearer-token auth. ────────────────────────────────────────────
async def require_admin(request: Request) -> None:
    token = settings.admin_token
    if not token:
        raise HTTPException(403, 'Admin endpoints disabled (ADMIN_TOKEN not set)')
    supplied = request.headers.get('X-Admin-Token') or ''
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        supplied = supplied or auth[7:].strip()
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(401, 'Invalid admin token')


# ── Redis cache helpers. Tolerant of an absent Redis (returns None). ────
async def cache_get(
    key: str,
    redis: Optional[aioredis.Redis] = None,
) -> Optional[Any]:
    r = redis or get_redis_singleton()
    if not r:
        return None
    try:
        v = await r.get(key)
        if v:
            metrics['cache_hits'] += 1
            return json.loads(v)
    except Exception:
        pass
    metrics['cache_misses'] += 1
    return None


async def cache_set(
    key: str,
    value: Any,
    ttl: int,
    redis: Optional[aioredis.Redis] = None,
) -> None:
    r = redis or get_redis_singleton()
    if not r:
        return
    try:
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


# ── Small metric / slow-query helpers. ──────────────────────────────────
def inc_metric(key: str) -> None:
    metrics[key] = metrics.get(key, 0) + 1


def log_slow(endpoint: str, duration_ms: float) -> None:
    if duration_ms > 2000:
        log.warning('Slow query on %s: %.0fms', endpoint, duration_ms)
