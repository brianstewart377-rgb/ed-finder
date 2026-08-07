from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import routers.archetypes as archetypes  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_throttle():
    """Each test starts with a cold throttle, matching a fresh process."""
    archetypes._last_cache_error_logged_at = 0.0
    yield
    archetypes._last_cache_error_logged_at = 0.0


def _broken_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get.side_effect = ConnectionError('redis unreachable')
    redis.set.side_effect = ConnectionError('redis unreachable')
    return redis


@pytest.mark.asyncio
async def test_cache_get_degrades_and_logs_on_redis_error(caplog):
    """2026-08-07 Codex Review finding: a Redis outage silently bypassed the
    cache with zero log line — correct degrade-to-DB behavior, invisible
    failure. Confirms both halves: still returns None (degrades), and now
    logs a warning (visible)."""
    with caplog.at_level(logging.WARNING, logger='ed_finder'):
        result = await archetypes._cache_get(_broken_redis(), 'arch:v1:sys:1')

    assert result is None
    assert any('cache get failed' in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_cache_set_degrades_and_logs_on_redis_error(caplog):
    with caplog.at_level(logging.WARNING, logger='ed_finder'):
        await archetypes._cache_set(_broken_redis(), 'arch:v1:sys:1', {'x': 1})

    assert any('cache set failed' in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_cache_version_degrades_and_logs_on_redis_error(caplog):
    with caplog.at_level(logging.WARNING, logger='ed_finder'):
        result = await archetypes._cache_version(_broken_redis())

    assert result == 1
    assert any('cache version failed' in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_repeated_failures_within_interval_log_once(caplog):
    """A sustained outage must not log once per request — that's log spam
    under exactly the condition (many requests, all failing) most likely to
    flood the log right when an operator needs a clean signal."""
    redis = _broken_redis()
    with caplog.at_level(logging.WARNING, logger='ed_finder'):
        for _ in range(5):
            await archetypes._cache_get(redis, 'arch:v1:sys:1')

    warnings = [r for r in caplog.records if 'cache get failed' in r.message]
    assert len(warnings) == 1
