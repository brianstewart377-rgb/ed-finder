"""
Shared pytest fixtures for ED Finder API integration tests.

Provides:

  * ``app``       — the live FastAPI application (lifespan honoured)
  * ``client``    — async ``httpx.AsyncClient`` against ``app``
  * ``pool``      — the same asyncpg pool the app is using
  * ``redis_client`` — the same redis client the app is using
  * ``clean_db``  — wipes per-test mutable tables before each test

These fixtures expect a running PostgreSQL with the project schema
already loaded, plus a Redis instance, both pointed at by env vars:

    DATABASE_URL  = postgresql://edfinder:edfinder@127.0.0.1:55432/edfinder
    REDIS_URL     = redis://localhost:6379/15        # /15 = test DB
    CORS_ORIGINS  = http://test
    ADMIN_TOKEN   = test-admin-token
"""
from __future__ import annotations

import os
import sys
import importlib
from pathlib import Path
from typing import AsyncGenerator

# --- sys.path: pull in api modules from apps/api/src/ ------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent     # tests/integration/conftest.py → repo root
sys.path.insert(0, str(_ROOT / 'apps' / 'api' / 'src'))
sys.path.insert(0, str(_ROOT / 'apps' / 'importer' / 'src'))

from tests.helpers import db_isolation

# --- env defaults that must be set BEFORE importing the api ----------
if 'DATABASE_URL' in os.environ:
    _db_target = db_isolation.validate_test_db_target(
        os.environ['DATABASE_URL'],
        env=os.environ,
        source='DATABASE_URL',
    )
else:
    _db_target = db_isolation.default_target(os.environ)
    os.environ['DATABASE_URL'] = _db_target.dsn
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/15')
os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('ADMIN_TOKEN', 'test-admin-token')
os.environ.setdefault('LOG_LEVEL', 'WARNING')
os.environ.setdefault('EXPOSE_ERROR_DETAIL', 'true')

import pytest
import pytest_asyncio
import asyncpg
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient


# Function-scoped fixture: each test gets its own pool/redis lifecycle.
# That avoids the "session fixture / per-test event loop" mismatch that
# otherwise hangs on teardown.
@pytest_asyncio.fixture
async def app():
    from main import app as fastapi_app
    async with fastapi_app.router.lifespan_context(fastapi_app):
        yield fastapi_app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    for module_name in ('config', 'edfinder_api.config'):
        try:
            limiter = importlib.import_module(module_name).limiter
            limiter._storage.reset()  # pyright: ignore[reportPrivateUsage]
        except Exception:
            continue
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as c:
        yield c


@pytest_asyncio.fixture
async def pool(app):
    from edfinder_api.state import get_pool_singleton
    return get_pool_singleton()


@pytest_asyncio.fixture
async def redis_client(app):
    from edfinder_api.state import get_redis_singleton
    return get_redis_singleton()


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Wipe per-test mutable rows + Redis cache before every test.

    * PostgreSQL: TRUNCATE the small per-test mutable tables (watchlist,
      system_notes, profile_sync, watchlist_changelog, api_cache).
      Systems / bodies / ratings come from the seed and stay put.
    * Redis (test DB 15): FLUSHDB. Without this, the API's per-endpoint
      caches (map.regions / heatmap / timeline / status / search:v2:…)
      bleed between tests — earlier-run state poisons the next test's
      assertions. This was caught when the Phase-5 map-MV tests
      sporadically failed with body['total']==0 even though the MV
      had 40 rows: the previous test had cached the pre-seed empty
      result.

    Acquires its own short-lived pool because depending on `app` here
    would chain the lifespan into every test that doesn't otherwise need
    it (and slow the suite). Uses a separate connection to keep the
    truncate transaction tiny.
    """
    try:
        db_isolation.require_destructive_reset_opt_in(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(str(exc))
    pool = await asyncpg.create_pool(
        dsn=os.environ['DATABASE_URL'], min_size=1, max_size=2,
        statement_cache_size=0,
    )
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                'TRUNCATE TABLE watchlist, system_notes, profile_sync, '
                'watchlist_changelog, api_cache CASCADE'
            )
    finally:
        await pool.close()

    # Best-effort Redis flush — short timeout so a missing/locked Redis
    # doesn't break tests that don't need it.
    try:
        r = aioredis.from_url(
            os.environ['REDIS_URL'], decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
        )
        await r.flushdb()
        await r.aclose()
    except Exception:
        pass

    # SlowAPI uses in-memory buckets in test/dev config. Reset them between
    # tests so route-limit coverage stays deterministic instead of depending
    # on how many requests earlier tests happened to make.
    for module_name in ('config', 'edfinder_api.config'):
        try:
            limiter = importlib.import_module(module_name).limiter
            limiter._storage.reset()  # pyright: ignore[reportPrivateUsage]
        except Exception:
            continue

    yield
