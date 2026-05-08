"""Sanity test — verifies the test infra (conftest fixtures) actually
boots the API + Postgres + Redis."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_health(client):
    r = await client.get('/api/health')
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'ok'


async def test_db_reachable(pool):
    async with pool.acquire() as conn:
        n = await conn.fetchval('SELECT count(*) FROM systems')
        assert n >= 40, f"expected seed systems, got {n}"


async def test_redis_reachable(redis_client):
    pong = await redis_client.ping()
    assert pong is True
