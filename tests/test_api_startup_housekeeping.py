from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'


@pytest.fixture
def api_main(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(API_SRC))
    monkeypatch.setenv('CORS_ORIGINS', 'http://test')
    sys.modules.pop('main', None)
    module = __import__('main')
    yield module
    sys.modules.pop('main', None)


@pytest.mark.asyncio
async def test_checkpoint_startup_skips_admin_operation_reap(api_main, monkeypatch):
    """The checkpoint's real lifespan must not call the UPDATE-capable reaper."""
    class FakeConnection:
        async def fetch(self, _query):
            return []

    class AcquireContext:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    class FakePool:
        def acquire(self):
            return AcquireContext()

        async def close(self):
            pass

    pool = FakePool()

    async def create_pool(**_kwargs):
        return pool

    def unavailable_redis(*_args, **_kwargs):
        raise ConnectionError('cache unavailable in focused startup test')

    reap = AsyncMock()
    monkeypatch.setattr(api_main.asyncpg, 'create_pool', create_pool)
    monkeypatch.setattr(api_main.aioredis, 'from_url', unavailable_redis)
    monkeypatch.setattr(api_main, 'reap_stale_admin_operation_runs', reap)
    monkeypatch.setattr(
        api_main.settings,
        'admin_operation_startup_reap_enabled',
        False,
    )
    monkeypatch.setattr(api_main.settings, 'database_readonly_url', None)
    monkeypatch.setattr(api_main.settings, 'eddn_simulation_ingest_enabled', False)

    async with api_main.app.router.lifespan_context(api_main.app):
        assert api_main.app.state.pool is pool

    reap.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_startup_still_reaps_stale_admin_operations(api_main, monkeypatch):
    """Default runtime semantics retain interrupted-operation recovery."""
    pool = object()
    reap = AsyncMock(return_value=2)
    monkeypatch.setattr(api_main, 'reap_stale_admin_operation_runs', reap)
    monkeypatch.setattr(
        api_main.settings,
        'admin_operation_startup_reap_enabled',
        True,
    )

    await api_main._reap_stale_admin_runs_on_startup(pool)

    reap.assert_awaited_once_with(pool)


def test_admin_operation_startup_reap_defaults_enabled(monkeypatch):
    monkeypatch.syspath_prepend(str(API_SRC))
    monkeypatch.delenv('ADMIN_OPERATION_STARTUP_REAP_ENABLED', raising=False)
    from edfinder_api.config import Settings

    assert (
        Settings(cors_origins='http://test', _env_file=None)
        .admin_operation_startup_reap_enabled
        is True
    )
