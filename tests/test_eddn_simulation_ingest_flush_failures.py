"""EDDN simulation ingest — flush-failure accounting and liveness.

The July 2026 outage shape: the ingest loop kept cycling, every DB flush
failed and was swallowed by ``_flush_batch``, and the liveness gauge kept
advancing on every received message — so the stall alert never fired for
13 days. These tests pin the repaired contract:

* a failed flush increments the failure counters and does NOT advance the
  liveness timestamp;
* a successful flush resets the consecutive count and records the
  last-successful-flush timestamp;
* message receipt advances liveness only while the write path is healthy;
* after N consecutive failures (bounded env setting) the loop raises
  ``EddnFlushFailureThresholdExceeded`` and the outer loop reconnects;
* /api/metrics exposes the new counter and gauges.

This keeps the EDDN ingest as the named runtime exception in CLAUDE.md; it
adds no journal-import automation.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', os.path.join(os.getcwd(), 'test-local.log'))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api.ingest import eddn_client  # noqa: E402


class _FailingAcquire:
    def __init__(self, exc: Exception):
        self.exc = exc

    async def __aenter__(self):
        raise self.exc

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FailingPool:
    def __init__(self, exc: Exception | None = None):
        self.exc = exc or RuntimeError('connection refused')

    def acquire(self):
        return _FailingAcquire(self.exc)


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _OkConnection:
    def __init__(self):
        self.executemany_calls = 0

    def transaction(self):
        return _Transaction()

    async def executemany(self, query, rows):
        self.executemany_calls += 1


class _OkAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _OkPool:
    def __init__(self):
        self.conn = _OkConnection()

    def acquire(self):
        return _OkAcquire(self.conn)


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    monkeypatch.setattr(eddn_client, '_last_flush_at', time.time() - 1000)
    monkeypatch.setattr(eddn_client, '_last_successful_flush_at', 0.0)
    monkeypatch.setattr(eddn_client, '_flush_failures_total', 0)
    monkeypatch.setattr(eddn_client, '_consecutive_flush_failures', 0)
    yield


def _journal_row() -> dict:
    return {
        'system_address': 1,
        'system_name': 'Test',
        'body_id': None,
        'body_name': None,
        'event_type': 'Scan',
        'event_timestamp': None,
        'source': 'eddn',
        'raw_event': {'event': 'Scan'},
    }


async def test_failed_flush_counts_and_does_not_advance_liveness(caplog):
    before = eddn_client._last_flush_at

    ok = await eddn_client._flush_batch(_FailingPool(), [_journal_row()], [])

    assert ok is False
    assert eddn_client.flush_failures_total() == 1
    assert eddn_client.consecutive_flush_failures() == 1
    assert eddn_client.last_successful_flush_timestamp() == 0.0
    assert eddn_client._last_flush_at == before, 'a failed flush must not look like liveness'
    assert eddn_client.seconds_since_last_flush() >= 999
    assert 'EDDN flush failed (1 consecutive, 1 total this process)' in caplog.text


async def test_successful_flush_resets_consecutive_and_records_timestamp():
    monkey_before = time.time()
    eddn_client._consecutive_flush_failures = 3
    eddn_client._flush_failures_total = 7

    ok = await eddn_client._flush_batch(_OkPool(), [_journal_row()], [])

    assert ok is True
    assert eddn_client.consecutive_flush_failures() == 0
    assert eddn_client.flush_failures_total() == 7, 'the total is monotonic'
    assert eddn_client.last_successful_flush_timestamp() >= monkey_before
    assert eddn_client.seconds_since_last_flush() < 5


async def test_empty_batch_is_a_successful_no_op():
    assert await eddn_client._flush_batch(_FailingPool(), [], []) is True
    assert eddn_client.flush_failures_total() == 0


def test_write_path_health_gates_receive_liveness():
    assert eddn_client._write_path_healthy() is True
    eddn_client._record_flush_failure()
    assert eddn_client._write_path_healthy() is False
    eddn_client._record_flush_success()
    assert eddn_client._write_path_healthy() is True


def test_receive_path_only_advances_liveness_while_healthy():
    """The loop's recv branch is `if _write_path_healthy(): _last_flush_at = now`.
    Pin that gate in source so a refactor cannot quietly restore the
    unconditional advance that hid the July 2026 outage."""
    source = (ROOT / 'apps' / 'api' / 'src' / 'ingest' / 'eddn_client.py').read_text(encoding='utf-8')
    assert 'if _write_path_healthy():\n                _last_flush_at = time.time()' in source
    # No other unconditional assignment of the liveness timestamp in the loop body.
    loop_body = source.split('async def _run_ingest_loop', 1)[1].split('def _raise_if_flush_threshold_exceeded', 1)[0]
    assert loop_body.count('_last_flush_at = time.time()') == 1


def test_threshold_raises_after_n_consecutive_failures(monkeypatch):
    monkeypatch.setattr(eddn_client, 'max_consecutive_flush_failures', lambda: 3)

    eddn_client._record_flush_failure()
    eddn_client._record_flush_failure()
    eddn_client._raise_if_flush_threshold_exceeded(False)  # 2 < 3 — still tolerated

    eddn_client._record_flush_failure()
    with pytest.raises(eddn_client.EddnFlushFailureThresholdExceeded) as excinfo:
        eddn_client._raise_if_flush_threshold_exceeded(False)
    assert '3 consecutive EDDN flush failures (limit 3)' in str(excinfo.value)

    # A success never raises, whatever the count was.
    eddn_client._raise_if_flush_threshold_exceeded(True)


def test_threshold_is_clamped_to_bounds(monkeypatch):
    from edfinder_api.config import settings

    monkeypatch.setattr(settings, 'eddn_simulation_ingest_max_consecutive_flush_failures', 0)
    assert eddn_client.max_consecutive_flush_failures() == eddn_client.MIN_CONSECUTIVE_FLUSH_FAILURES
    monkeypatch.setattr(settings, 'eddn_simulation_ingest_max_consecutive_flush_failures', 10_000)
    assert eddn_client.max_consecutive_flush_failures() == eddn_client.MAX_CONSECUTIVE_FLUSH_FAILURES
    monkeypatch.setattr(settings, 'eddn_simulation_ingest_max_consecutive_flush_failures', 12)
    assert eddn_client.max_consecutive_flush_failures() == 12


def test_threshold_setting_has_a_bounded_default():
    from edfinder_api.config import Settings

    field = Settings.model_fields['eddn_simulation_ingest_max_consecutive_flush_failures']
    assert field.default == eddn_client.DEFAULT_MAX_CONSECUTIVE_FLUSH_FAILURES == 5
    constraints = {type(m).__name__: m for m in field.metadata}
    assert constraints['Ge'].ge == 1
    assert constraints['Le'].le == 1000


async def test_outer_loop_reconnects_after_threshold(monkeypatch, caplog):
    calls = {'runs': 0, 'sleeps': []}

    async def fake_loop(pool):
        calls['runs'] += 1
        if calls['runs'] == 1:
            raise eddn_client.EddnFlushFailureThresholdExceeded('5 consecutive EDDN flush failures (limit 5)')
        raise eddn_client.asyncio.CancelledError()

    async def fake_sleep(seconds):
        calls['sleeps'].append(seconds)

    monkeypatch.setattr(eddn_client, '_run_ingest_loop', fake_loop)
    monkeypatch.setattr(eddn_client.asyncio, 'sleep', fake_sleep)

    with pytest.raises(eddn_client.asyncio.CancelledError):
        await eddn_client.run_eddn_simulation_ingest(pool=None)

    assert calls['runs'] == 2
    assert calls['sleeps'] == [eddn_client.RECONNECT_DELAY]
    assert 'EDDN simulation ingest write path unhealthy' in caplog.text


def test_metrics_endpoint_exposes_flush_failure_metrics():
    meta_source = (ROOT / 'apps' / 'api' / 'src' / 'routers' / 'meta.py').read_text(encoding='utf-8')

    assert '# TYPE ed_finder_eddn_simulation_ingest_flush_failures_total counter' in meta_source
    assert '# TYPE ed_finder_eddn_simulation_ingest_consecutive_flush_failures gauge' in meta_source
    assert '# TYPE ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds gauge' in meta_source


async def test_metrics_endpoint_renders_values():
    from edfinder_api.routers import meta

    eddn_client._record_flush_failure()
    eddn_client._record_flush_failure()
    body = await meta.metrics_endpoint()

    assert 'ed_finder_eddn_simulation_ingest_flush_failures_total 2\n' in body
    assert 'ed_finder_eddn_simulation_ingest_consecutive_flush_failures 2\n' in body
    assert 'ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds 0\n' in body


async def test_final_flush_on_quiet_feed_exit_applies_the_breaker(monkeypatch):
    """One relevant event, then the normal 30 s quiet-feed timeout: the batch
    is flushed only from the exit path. A low-volume outage where every
    batch takes this path must still trip the breaker."""
    monkeypatch.setattr(eddn_client, 'max_consecutive_flush_failures', lambda: 2)

    await eddn_client._flush_pending_on_exit(_FailingPool(), [_journal_row()], [], exception_in_flight=False)
    assert eddn_client.consecutive_flush_failures() == 1

    with pytest.raises(eddn_client.EddnFlushFailureThresholdExceeded):
        await eddn_client._flush_pending_on_exit(_FailingPool(), [_journal_row()], [], exception_in_flight=False)
    assert eddn_client.consecutive_flush_failures() == 2
    assert eddn_client.seconds_since_last_flush() >= 999, 'failed final flushes are not liveness'


async def test_final_flush_never_raises_while_an_exception_is_propagating(monkeypatch):
    """Cancellation (or the in-loop breaker) must keep propagating; raising
    from the exit path would replace it."""
    monkeypatch.setattr(eddn_client, 'max_consecutive_flush_failures', lambda: 1)

    await eddn_client._flush_pending_on_exit(_FailingPool(), [_journal_row()], [], exception_in_flight=True)
    assert eddn_client.consecutive_flush_failures() == 1  # still counted, just not raised


async def test_final_flush_success_refreshes_liveness_and_resets():
    eddn_client._record_flush_failure()
    await eddn_client._flush_pending_on_exit(_OkPool(), [_journal_row()], [], exception_in_flight=False)
    assert eddn_client.consecutive_flush_failures() == 0
    assert eddn_client.seconds_since_last_flush() < 5


async def test_final_flush_with_nothing_pending_is_a_no_op():
    before = eddn_client._last_flush_at
    await eddn_client._flush_pending_on_exit(_FailingPool(), [], [], exception_in_flight=False)
    assert eddn_client._last_flush_at == before
    assert eddn_client.flush_failures_total() == 0


def test_exit_path_passes_cancellation_state_from_sys_exception():
    source = (ROOT / 'apps' / 'api' / 'src' / 'ingest' / 'eddn_client.py').read_text(encoding='utf-8')
    assert 'exception_in_flight=sys.exception() is not None' in source
