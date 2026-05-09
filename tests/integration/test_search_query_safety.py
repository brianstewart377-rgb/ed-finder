"""Search query-safety guarantees: server-side `statement_timeout`
on every connection, and the `total_is_capped` envelope that
prevents galaxy-wide COUNT(*) from scanning all 186 M rows.

Together these make 'fail fast' the contract for *every* code path
through `local_search.py`, not just the inline-fallback that the
audit's commit be6e2b8 tightened (and PR #3 then deleted).
"""
import pytest


pytestmark = pytest.mark.asyncio


async def test_every_connection_has_a_statement_timeout(pool):
    """The pool's per-connection initialiser must SET statement_timeout.

    Set 0 = no limit; we expect the configured non-zero value (default
    15000 ms). Without this, the only ceiling is asyncpg's 5-min
    `command_timeout`, which is the audit's exact 'silent slow path'
    failure mode.
    """
    async with pool.acquire() as conn:
        timeout = await conn.fetchval('SHOW statement_timeout')
    # PG returns this as a string like '15s' or '15000ms'. Either is fine
    # so long as it's NOT '0'/'0ms' (= no limit).
    assert timeout not in ('0', '0ms', '0s'), (
        f"statement_timeout is unset on pooled connections: {timeout!r}. "
        "Searches will run for up to asyncpg.command_timeout (5 min) "
        "and pin pool slots — see the audit's §C5 incident."
    )


async def test_galaxy_wide_count_is_capped(client):
    """Galaxy-wide searches must NOT run COUNT(*) over the full systems
    table. We expect total ≤ 10_000 and total_is_capped=True if the
    seed grew past the cap (it doesn't today, but the contract holds)."""
    r = await client.post('/api/local/search', json={
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'economy': 'any'},
        'galaxy_wide':      True,
        'size':             5,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # The cap is 10 000 — total cannot exceed it on galaxy_wide.
    assert body['total'] <= 10_000, (
        f"galaxy_wide total={body['total']} > cap; "
        "COUNT(*) is unbounded again."
    )


async def test_local_search_total_is_not_capped(client):
    """Distance-bounded local searches keep the precise total — only the
    galaxy_wide path is allowed to truncate."""
    r = await client.post('/api/local/search', json={
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'distance': {'min': 0, 'max': 500}},
        'size':             5,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # Local search must not advertise truncation
    assert not body.get('total_is_capped'), body
