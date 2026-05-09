"""EDDN live feed: Server-Sent Events endpoint + Redis pub/sub bridge.

The EDDN listener container publishes events on the Redis `eddn_events`
channel. Each API worker process runs one instance of
`eddn_pubsub_bridge()` (started by the lifespan) which subscribes once
and broadcasts every event to all locally-connected SSE clients.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from deps  import get_pool, get_redis
from state import active_jobs, sse_clients, get_redis_singleton

log = logging.getLogger('ed_finder')

router = APIRouter(tags=['events'])

EDDN_PUBSUB_CHANNEL = 'eddn_events'


# ---------------------------------------------------------------------------
# Background worker — subscribes to Redis pub/sub and fans out to queues.
# Started by the lifespan in main.py at app start-up.
# ---------------------------------------------------------------------------
async def eddn_pubsub_bridge() -> None:
    """Subscribe to Redis EDDN channel and fan out to local SSE queues.

    Audit fix (2026-05-08, AUDIT_REPORT.md §H2): wrap the inner
    `pubsub.listen()` loop in a backoff-reconnect outer loop. Previously
    a single Redis blip (restart, network partition, OOM-kill) would kill
    the bridge for the lifetime of the API container — front-ends
    silently stopped receiving live events with no recovery.
    """
    backoff = 1.0
    while True:
        r = get_redis_singleton()
        if r is None:
            return
        pubsub = None
        try:
            pubsub = r.pubsub()
            await pubsub.subscribe(EDDN_PUBSUB_CHANNEL)
            backoff = 1.0  # reset on successful subscribe
            async for message in pubsub.listen():
                if message.get('type') != 'message':
                    continue
                data = message.get('data')
                if not data:
                    continue
                try:
                    event = json.loads(data) if isinstance(data, str) else data
                except (ValueError, TypeError):
                    continue
                _broadcast(event)
        except asyncio.CancelledError:
            try:
                if pubsub is not None:
                    await pubsub.unsubscribe(EDDN_PUBSUB_CHANNEL)
                    await pubsub.aclose()
            except Exception:
                pass
            raise
        except Exception as e:
            log.error('EDDN pub/sub bridge error (will reconnect in %.1fs): %s', backoff, e)
            try:
                if pubsub is not None:
                    await pubsub.aclose()
            except Exception:
                pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 60.0)
            continue


def _broadcast(event: dict) -> None:
    """Fan event out to every connected SSE client on this worker.

    On QueueFull (slow consumer) we drop the *oldest* event and put the
    new one — the connection stays subscribed. Previous behaviour was to
    detach the whole queue from `sse_clients`, which combined with the
    25 s heartbeat sleep below caused permanent silence after the first
    burst at high event rates (>10/s). See git blame for the audit-era
    incident write-up.
    """
    for q in list(sse_clients):  # snapshot — list can mutate under us
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest event, keep the queue subscribed.
            try:
                q.get_nowait()
                q.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------
@router.get('/api/events/live')
async def live_events(request: Request):
    # 200-event buffer (was 50). At ~19 events/sec a 50-deep buffer
    # filled in <3s during a busy spell, which combined with the old
    # 25 s heartbeat sleep stalled clients for 25-second stretches.
    # 200 gives ~10s of headroom and is still tiny in memory terms.
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    sse_clients.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Block until an event arrives OR the heartbeat
                    # timeout fires. Crucially, this does NOT busy-poll
                    # and does NOT sleep through bursts — events are
                    # delivered the moment they're broadcast.
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # No events for 15 s → send a heartbeat to keep
                    # nginx / Cloudflare / browser-side EventSource
                    # connections alive. Loops back immediately to
                    # wait for the next event.
                    yield ": heartbeat\n\n"
        finally:
            try:
                sse_clients.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control':      'no-cache',
            'X-Accel-Buffering':  'no',
        },
    )


@router.get('/api/events/recent')
async def recent_events(
    limit: int = 50,
    pool:  asyncpg.Pool = Depends(get_pool),
):
    limit = min(limit, 200)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT system_name, system_id64, event_type, received_at
              FROM eddn_log
             ORDER BY received_at DESC
             LIMIT $1
        """, limit)
    return {
        'events': [
            {
                'system_name': r['system_name'],
                'id64':        r['system_id64'],
                'type':        r['event_type'],
                'timestamp':   r['received_at'].isoformat() if r['received_at'] else None,
            }
            for r in rows
        ],
        'jobs': active_jobs,
    }
