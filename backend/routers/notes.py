"""Per-system user notes — tiny CRUD surface backed by `system_notes`."""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from deps   import get_pool
from models import NoteBody

router = APIRouter(tags=['notes'])


@router.get('/api/systems/{id64}/note')
async def get_note(id64: int, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT note, updated_at FROM system_notes WHERE system_id64 = $1',
            id64,
        )
    return {
        'note':       row['note'] if row else '',
        'updated_at': str(row['updated_at']) if row else None,
    }


@router.post('/api/systems/{id64}/note')
async def save_note(id64: int, body: NoteBody, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO system_notes (system_id64, note, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (system_id64) DO UPDATE
               SET note = $2, updated_at = NOW()
        """, id64, body.note)
    return {'ok': True}


@router.delete('/api/systems/{id64}/note')
async def delete_note(id64: int, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM system_notes WHERE system_id64 = $1', id64)
    return {'ok': True}


@router.get('/api/systems/notes')
async def all_notes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT n.system_id64, s.name, n.note, n.updated_at
              FROM system_notes n
              JOIN systems s ON s.id64 = n.system_id64
             ORDER BY n.updated_at DESC
        """)
    return {'notes': [dict(r) for r in rows]}
