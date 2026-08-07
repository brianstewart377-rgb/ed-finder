from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import routers.archetypes as archetypes  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_throttle():
    """Each test starts with a cold throttle, matching a fresh process."""
    archetypes._last_cache_error_logged_at = None
    yield
    archetypes._last_cache_error_logged_at = None


def _broken_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get.side_effect = ConnectionError('redis unreachable')
    redis.set.side_effect = ConnectionError('redis unreachable')
    return redis


# Mocking archetypes.log directly, rather than using pytest's caplog fixture,
# so this test's outcome depends only on this module's own code — not on
# root-logger handler/propagation state, which (unlike a fresh process) can
# be left in an unknown configuration by whichever of the other ~1600 tests
# in the full suite happened to run first in the same pytest session.


@pytest.mark.asyncio
async def test_cache_get_degrades_and_logs_on_redis_error():
    """2026-08-07 Codex Review finding: a Redis outage silently bypassed the
    cache with zero log line — correct degrade-to-DB behavior, invisible
    failure. Confirms both halves: still returns None (degrades), and now
    logs a warning (visible)."""
    with patch.object(archetypes, 'log') as mock_log:
        result = await archetypes._cache_get(_broken_redis(), 'arch:v1:sys:1')

    assert result is None
    mock_log.warning.assert_called_once()
    assert 'get' in mock_log.warning.call_args.args[1]


@pytest.mark.asyncio
async def test_cache_set_degrades_and_logs_on_redis_error():
    with patch.object(archetypes, 'log') as mock_log:
        await archetypes._cache_set(_broken_redis(), 'arch:v1:sys:1', {'x': 1})

    mock_log.warning.assert_called_once()
    assert 'set' in mock_log.warning.call_args.args[1]


@pytest.mark.asyncio
async def test_cache_version_degrades_and_logs_on_redis_error():
    with patch.object(archetypes, 'log') as mock_log:
        result = await archetypes._cache_version(_broken_redis())

    assert result == 1
    mock_log.warning.assert_called_once()
    assert 'version' in mock_log.warning.call_args.args[1]


@pytest.mark.asyncio
async def test_repeated_failures_within_interval_log_once():
    """A sustained outage must not log once per request — that's log spam
    under exactly the condition (many requests, all failing) most likely to
    flood the log right when an operator needs a clean signal."""
    redis = _broken_redis()
    with patch.object(archetypes, 'log') as mock_log:
        for _ in range(5):
            await archetypes._cache_get(redis, 'arch:v1:sys:1')

    mock_log.warning.assert_called_once()


@pytest.mark.asyncio
async def test_first_failure_logs_even_when_monotonic_clock_is_young():
    """Codex Review finding: time.monotonic()'s reference point is
    platform-defined and commonly host-boot-relative, not guaranteed far
    from zero. A 0.0 sentinel would make `now - 0.0 >= 60` false whenever
    `now` itself is under 60 (e.g. shortly after a host reboot), silently
    swallowing the first failure — and everything else for up to a minute
    — instead of logging it. Simulates that by patching time.monotonic()
    to return a small value, proving the None sentinel doesn't have the
    same blind spot."""
    with patch.object(archetypes.time, 'monotonic', return_value=5.0):
        with patch.object(archetypes, 'log') as mock_log:
            await archetypes._cache_get(_broken_redis(), 'arch:v1:sys:1')

    mock_log.warning.assert_called_once()
