"""Watchlist + watchlist-changelog endpoints."""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from deps   import get_pool
from models import WatchlistAlert

router = APIRouter(tags=['watchlist'])


@router.get('/api/watchlist')
async def get_watchlist(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.*,
                   r.score, r.economy_suggestion
              FROM watchlist w
         LEFT JOIN ratings r ON r.system_id64 = w.system_id64
          ORDER BY w.added_at DESC
        """)
    return {'watchlist': [dict(r) for r in rows]}


@router.post('/api/watchlist/{id64}')
async def add_watchlist(
    id64: int,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        sys_row = await conn.fetchrow(
            'SELECT name, x, y, z, population, is_colonised FROM systems WHERE id64 = $1',
            id64,
        )
        if not sys_row:
            raise HTTPException(404, f'System {id64} not found')
        await conn.execute("""
            INSERT INTO watchlist (system_id64, name, x, y, z, population, is_colonised)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (system_id64) DO NOTHING
        """, id64, sys_row['name'], sys_row['x'], sys_row['y'], sys_row['z'],
             sys_row['population'], sys_row['is_colonised'])
    return {'ok': True}


@router.delete('/api/watchlist/{id64}')
async def remove_watchlist(id64: int, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM watchlist WHERE system_id64 = $1', id64)
    return {'ok': True}


@router.patch('/api/watchlist/{id64}/alert')
async def update_alert(
    id64: int,
    alert: WatchlistAlert,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE watchlist
               SET alert_min_score = $1, alert_economy = $2
             WHERE system_id64 = $3
        """, alert.min_score, alert.economy, id64)
    return {'ok': True}


@router.get('/api/watchlist/changes')
async def watchlist_changes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM watchlist_changelog
             ORDER BY detected_at DESC
             LIMIT 100
        """)
    return {'changes': [dict(r) for r in rows]}


@router.get('/api/watchlist/changelog')
async def watchlist_changelog(pool: asyncpg.Pool = Depends(get_pool)):
    # Alias for legacy callers.
    return await watchlist_changes(pool)
