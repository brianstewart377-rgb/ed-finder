import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request

from edfinder_api.config import limiter
from edfinder_api.deps import get_pool
from edfinder_api.exploration.api_models import (
    ExplorationFactsResponse,
    ExplorationImportReceipt,
    ExplorationImportRequest,
)
from edfinder_api.exploration import store

router = APIRouter(tags=['exploration'])


@router.post('/api/exploration/import', response_model=ExplorationImportReceipt)
@limiter.limit('10/minute')
async def import_exploration(
    request: Request,
    body: ExplorationImportRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ExplorationImportReceipt:
    try:
        return await store.import_exploration_batch(pool, body)
    except store.ExplorationImportRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get('/api/exploration/facts/{sync_key}', response_model=ExplorationFactsResponse)
@limiter.limit('60/minute')
async def get_exploration_facts_for_sync_key(
    request: Request,
    sync_key: str = Path(..., min_length=16, max_length=128),
    pool: asyncpg.Pool = Depends(get_pool),
) -> ExplorationFactsResponse:
    del request
    return await store.get_exploration_facts(pool, sync_key)
