import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from edfinder_api.config import limiter
from edfinder_api.deps import get_pool
from edfinder_api.journal_import.api_models import JournalImportReceipt, JournalImportRequest
from edfinder_api.journal_import import store

router = APIRouter(tags=['journal-import'])


@router.post('/api/journal/import', response_model=JournalImportReceipt)
@limiter.limit('5/minute')
async def import_frontier_journal(
    request: Request,
    body: JournalImportRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JournalImportReceipt:
    try:
        return await store.import_journal_batch(pool, body)
    except store.JournalImportRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get('/api/journal/imports/{run_key}', response_model=JournalImportReceipt)
@limiter.limit('30/minute')
async def get_frontier_journal_import(
    request: Request,
    run_key: str,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JournalImportReceipt:
    receipt = await store.get_journal_import_receipt(pool, run_key)
    if receipt is None:
        raise HTTPException(404, f'Journal import run {run_key} not found')
    return receipt
