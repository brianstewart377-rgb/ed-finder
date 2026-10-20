"""EDDN→SSE bridge: recovers when Redis was down at API boot.

Previously `eddn_pubsub_bridge()` returned immediately when the Redis
singleton was None, and the lifespan only created the task when Redis had
answered PING at boot — so an API that started while Redis was restarting
never served live events until the API itself was restarted, and nothing
in /api/metrics said so. These tests pin the repaired contract:

* the bridge keeps retrying the connection with capped exponential backoff;
* once connected it installs the client (set_redis) so the cache recovers too;
* the bridge state is exported as a gauge with stable codes;
* the lifespan starts the task unconditionally.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', os.path.join(os.getcwd(), 'test-local.log'))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api import state  # noqa: E402
from edfinder_api.routers import events  # noqa: E402


class _FakePubSub:
    def __init__(self, messages):
        self._messages = list(messages)
        self.subscribed = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def unsubscribe(self, channel):
        pass

    async def aclose(self):
        self.closed = True

    async def listen(self):
        for message in self._messages:
            yield message
        # A real listen() blocks forever; emulate "stream still open" by
        # parking until cancelled.
        await asyncio.Event().wait()


class _FakeRedis:
    def __init__(self, messages=()):
        self.pubsub_obj = _FakePubSub(messages)

    def pubsub(self):
        return self.pubsub_obj

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch):
    monkeypatch.setattr(state, '_redis', None)
    monkeypatch.setattr(events, '_bridge_state', events.BRIDGE_STATE_NOT_STARTED)
    monkeypatch.setattr(events, '_bridge_reconnects_total', 0)
    events.sse_clients.clear()
    yield
    events.sse_clients.clear()
    state._redis = None


async def test_bridge_retries_with_capped_backoff_then_connects_and_installs_client(monkeypatch):
    attempts = {'n': 0}
    sleeps: list[float] = []
    fake = _FakeRedis(messages=[{'type': 'message', 'data': '{"system_name": "Sol"}'}])
    observed_states: list[int] = []

    async def fake_connect():
        attempts['n'] += 1
        observed_states.append(events.bridge_state())
        if attempts['n'] < 4:
            raise ConnectionError('redis down')
        return fake

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(events, 'connect_redis', fake_connect)
    monkeypatch.setattr(events.asyncio, 'sleep', fake_sleep)
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    events.sse_clients.append(queue)

    task = asyncio.create_task(events.eddn_pubsub_bridge())
    # The fake stream delivers one event and then parks; wait for it.
    event = await asyncio.wait_for(queue.get(), timeout=2.0)
    assert event == {'system_name': 'Sol'}

    assert attempts['n'] == 4
    assert sleeps == [1.0, 2.0, 4.0], 'exponential backoff from 1 s, no sleep after success'
    assert all(s == events.BRIDGE_STATE_CONNECTING for s in observed_states)
    assert events.bridge_state() == events.BRIDGE_STATE_SUBSCRIBED
    assert events.bridge_reconnects_total() == 3
    assert state.get_redis_singleton() is fake, 'the bridge installs the client so cache_get/cache_set recover'
    assert fake.pubsub_obj.subscribed == [events.EDDN_PUBSUB_CHANNEL]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events.bridge_state() == events.BRIDGE_STATE_STOPPED


async def test_backoff_is_capped(monkeypatch):
    sleeps: list[float] = []

    async def always_fail():
        raise ConnectionError('redis down')

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 9:
            raise asyncio.CancelledError()

    monkeypatch.setattr(events, 'connect_redis', always_fail)
    monkeypatch.setattr(events.asyncio, 'sleep', fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await events.eddn_pubsub_bridge()

    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert max(sleeps) == events.BRIDGE_BACKOFF_MAX_SECONDS
    assert state.get_redis_singleton() is None


async def test_connect_failure_log_does_not_include_the_url(monkeypatch, caplog):
    async def fail_with_dsn_in_message():
        raise ConnectionError('Error connecting to redis://:secret@redis:6379/0')

    async def stop(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(events, 'connect_redis', fail_with_dsn_in_message)
    monkeypatch.setattr(events.asyncio, 'sleep', stop)

    with pytest.raises(asyncio.CancelledError):
        await events.eddn_pubsub_bridge()

    assert 'Redis still unavailable (ConnectionError)' in caplog.text
    assert 'secret' not in caplog.text
    assert 'redis://' not in caplog.text


async def test_mid_stream_error_moves_to_retrying_and_reconnects(monkeypatch):
    class _BrokenPubSub(_FakePubSub):
        async def listen(self):
            raise ConnectionResetError('lost')
            yield  # pragma: no cover

    class _BrokenRedis(_FakeRedis):
        def __init__(self):
            self.pubsub_obj = _BrokenPubSub([])

    state._redis = _BrokenRedis()
    seen: list[int] = []

    async def fake_sleep(_seconds):
        seen.append(events.bridge_state())
        if len(seen) >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(events.asyncio, 'sleep', fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await events.eddn_pubsub_bridge()

    assert seen == [events.BRIDGE_STATE_RETRYING, events.BRIDGE_STATE_RETRYING]
    assert events.bridge_reconnects_total() == 1


def test_lifespan_starts_the_bridge_unconditionally():
    main_source = (ROOT / 'apps' / 'api' / 'src' / 'main.py').read_text(encoding='utf-8')

    assert '_sse_pubsub_task = asyncio.create_task(eddn_pubsub_bridge())' in main_source
    assert 'if redis is not None:\n        _sse_pubsub_task' not in main_source
    # Boot and bridge share one bounded connect helper (no second from_url).
    assert 'redis = await connect_redis()' in main_source
    assert 'aioredis.from_url(' not in main_source


def test_metrics_endpoint_exposes_bridge_state_gauge():
    meta_source = (ROOT / 'apps' / 'api' / 'src' / 'routers' / 'meta.py').read_text(encoding='utf-8')

    assert '# TYPE ed_finder_sse_bridge_state gauge' in meta_source
    assert '# TYPE ed_finder_sse_bridge_reconnects_total counter' in meta_source
    assert 'ed_finder_sse_bridge_state {sse_bridge_state()}' in meta_source


def test_bridge_state_codes_are_stable():
    assert (
        events.BRIDGE_STATE_NOT_STARTED,
        events.BRIDGE_STATE_CONNECTING,
        events.BRIDGE_STATE_SUBSCRIBED,
        events.BRIDGE_STATE_RETRYING,
        events.BRIDGE_STATE_STOPPED,
    ) == (0, 1, 2, 3, 4)
