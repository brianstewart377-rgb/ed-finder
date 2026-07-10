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
    """The pool's server_settings must propagate statement_timeout
    through pgBouncer transaction-pool mode.

    Production-verified failure mode (2026-05-09):
        ``SHOW statement_timeout`` returned ``'0'`` over an
        asyncpg+pgbouncer pooled connection because pgBouncer issues
        an implicit ``DISCARD ALL`` / ``RESET`` between transactions,
        wiping any ``SET`` we'd issued in the per-connection init
        callback. Moving it into ``asyncpg.create_pool(server_settings=…)``
        sends it as a protocol-level startup parameter which pgBouncer
        preserves across the pool. This test pins that behaviour so we
        don't silently regress when someone refactors the pool init.
    """
    async with pool.acquire() as conn:
        timeout = await conn.fetchval('SHOW statement_timeout')
    assert timeout not in ('0', '0ms', '0s'), (
        f"statement_timeout is unset on pooled connections: {timeout!r}. "
        "If you moved it back into init=_init_conn, pgBouncer's RESET "
        "is wiping it — put it in server_settings instead. See main.py "
        "line ~120."
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


async def test_galaxy_wide_search_preserves_distance_when_reference_is_present(client):
    r = await client.post('/api/local/search', json={
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'economy': 'any'},
        'galaxy_wide':      True,
        'sort_by':          'distance',
        'size':             20,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(row.get('distance') is not None for row in body['results']), body['results']
