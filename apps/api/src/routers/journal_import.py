from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from deps import get_pool
from journal_import.api_models import JournalImportReceipt, JournalImportRequest
from journal_import import store

router = APIRouter(tags=['journal-import'])


@router.post('/api/journal/import', response_model=JournalImportReceipt)
async def import_frontier_journal(
    body: JournalImportRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JournalImportReceipt:
    return await store.import_journal_batch(pool, body)


@router.get('/api/journal/imports/{run_key}', response_model=JournalImportReceipt)
async def get_frontier_journal_import(
    run_key: str,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JournalImportReceipt:
    receipt = await store.get_journal_import_receipt(pool, run_key)
    if receipt is None:
        raise HTTPException(404, f'Journal import run {run_key} not found')
    return receipt
