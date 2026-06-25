from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse



router = APIRouter(tags=['review-support'])


async def _review_event_stream():
    # Keep the review-only SSE endpoint alive so the frontend can degrade
    # cleanly to recent-events polling without a 404 transport error.
    while True:
        yield b': review-only keepalive\n\n'
        await asyncio.sleep(15)


@router.get('/api/events/live', include_in_schema=False)
async def review_live_events() -> StreamingResponse:
    return StreamingResponse(_review_event_stream(), media_type='text/event-stream')


@router.get('/api/events/recent', include_in_schema=False)
async def review_recent_events() -> dict[str, object]:
    return {
        'events': [],
        'jobs': {},
    }
