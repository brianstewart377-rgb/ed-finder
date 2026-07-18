import pytest

from edfinder_api.routers import admin


class _FakeConnection:
    async def execute(self, query):
        assert query == 'DELETE FROM api_cache'
        return 'DELETE 3'


class _AcquireContext:
    async def __aenter__(self):
        return _FakeConnection()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakePool:
    def acquire(self):
        return _AcquireContext()


class _FailingRedis:
    async def scan_iter(self, *, match, count):
        assert match
        assert count == 500
        raise RuntimeError('redis unavailable')
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_cache_clear_reports_partial_failure_when_redis_fails(caplog):
    result = await admin.cache_clear(pool=_FakePool(), redis=_FailingRedis())

    assert result == {
        'ok': False,
        'partial': True,
        'redis_cleared': False,
        'message': 'Cache clear incomplete: Redis failed after 0 keys; 3 DB rows removed',
    }
    assert 'Redis cache clear failed after deleting 0 keys' in caplog.text


@pytest.mark.asyncio
async def test_cache_clear_reports_success_without_redis():
    result = await admin.cache_clear(pool=_FakePool(), redis=None)

    assert result == {
        'ok': True,
        'partial': False,
        'redis_cleared': True,
        'message': 'Cache cleared (0 Redis keys removed, 3 DB rows removed)',
    }
