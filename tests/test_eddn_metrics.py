"""Unit coverage for the EDDN listener's structured logging +
Prometheus metrics endpoint (added 2026-05-09).

Lives outside tests/integration because it doesn't need PG/Redis —
the metrics server is a pure asyncio.start_server over a stub
``_stats`` dict.
"""
import asyncio
import json
import logging
import os
import socket
import sys
from pathlib import Path

import pytest

# Ensure the EDDN listener is importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / 'apps' / 'eddn' / 'src'))


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://stub@localhost/stub')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'eddn.log'))
    monkeypatch.setenv('METRICS_PORT', '0')  # disabled by default
    yield


@pytest.fixture
def listener():
    """Re-import the listener so each test sees a fresh module-level state."""
    if 'eddn_listener' in sys.modules:
        del sys.modules['eddn_listener']
    import eddn_listener  # type: ignore  noqa: F401
    return eddn_listener


def test_prometheus_text_format(listener):
    """The text exposition must be valid Prometheus 0.0.4 format —
    every counter/gauge has '# HELP', '# TYPE', and a sample line."""
    listener._stats['events_received']  = 100
    listener._stats['events_processed'] = 95
    listener._stats['errors']           = 5
    listener._pending_systems[1]        = {'foo': 'bar'}

    text = listener._prometheus_text().decode('utf-8')

    # Required metric names — these are the dashboards' contract.
    for name in (
        'eddn_events_received_total',
        'eddn_events_processed_total',
        'eddn_systems_upserted_total',
        'eddn_bodies_upserted_total',
        'eddn_errors_total',
        'eddn_pending_systems',
        'eddn_pending_bodies',
        'eddn_seconds_since_flush',
        'eddn_uptime_seconds',
        'eddn_events_per_minute',
        'eddn_errors_per_minute',
    ):
        assert f'# HELP {name}' in text, f'missing HELP for {name}'
        assert f'# TYPE {name}' in text, f'missing TYPE for {name}'
        # The sample line must appear with the actual numeric value
        sample_lines = [
            ln for ln in text.splitlines()
            if ln and not ln.startswith('#') and ln.split(' ', 1)[0] == name
        ]
        assert sample_lines, f'no sample line for {name}'

    # Counters reflect the stub state.
    assert 'eddn_events_received_total 100' in text
    assert 'eddn_events_processed_total 95' in text
    assert 'eddn_errors_total 5' in text
    assert 'eddn_pending_systems 1' in text


def test_json_log_formatter_emits_valid_json(listener):
    """JSON formatter must produce a single-line parseable JSON document
    per record, with caller-supplied extras pass-through."""
    fmt = listener._JsonFormatter()
    record = logging.LogRecord(
        name='eddn_listener', level=logging.INFO, pathname=__file__,
        lineno=1, msg='upsert ok', args=None, exc_info=None,
    )
    record.system_id = 12345
    record.population = int(8e9)

    out = fmt.format(record)
    payload = json.loads(out)  # must be a single-line valid JSON
    assert payload['msg']    == 'upsert ok'
    assert payload['level']  == 'INFO'
    assert payload['logger'] == 'eddn_listener'
    assert payload['system_id']  == 12345
    assert payload['population'] == 8_000_000_000
    # `ts` must be ISO-8601 with timezone (no naive datetimes)
    assert 'T' in payload['ts'] and ('+' in payload['ts'] or 'Z' in payload['ts'])


def test_star_pos_requires_complete_numeric_triple(listener):
    assert listener._extract_star_pos(None) == (None, None, None)
    assert listener._extract_star_pos([78.5, None, 16.78125]) == (None, None, None)
    assert listener._extract_star_pos([78.5, '-100.25', 16.78125]) == (
        78.5,
        -100.25,
        16.78125,
    )


def test_location_partial_star_pos_does_not_overwrite_known_coords(listener):
    listener._pending_systems[42] = {
        'id64': 42,
        'x': 1.0,
        'y': 2.0,
        'z': 3.0,
    }

    async def run():
        await listener.handle_location_or_jump(
            None,
            {},
            {'SystemAddress': 42, 'StarSystem': 'Partial', 'StarPos': [9.0, None, 3.0]},
        )

    asyncio.run(run())

    assert listener._pending_systems[42]['x'] == 1.0
    assert listener._pending_systems[42]['y'] == 2.0
    assert listener._pending_systems[42]['z'] == 3.0


def test_location_missing_population_does_not_overwrite_known_population(listener):
    listener._pending_systems[44] = {
        'id64': 44,
        'pop': 123_456,
    }

    async def run():
        await listener.handle_location_or_jump(
            None,
            {},
            {'SystemAddress': 44, 'StarSystem': 'No Population Field'},
        )

    asyncio.run(run())

    assert listener._pending_systems[44]['pop'] == 123_456


def test_fss_partial_star_pos_is_stored_as_unknown_coords(listener):
    async def run():
        await listener.handle_fss_discovery(
            None,
            {},
            {'SystemAddress': 43, 'StarSystem': 'Partial FSS', 'StarPos': [9.0, None, 3.0]},
        )

    asyncio.run(run())

    assert listener._pending_systems[43]['x'] is None
    assert listener._pending_systems[43]['y'] is None
    assert listener._pending_systems[43]['z'] is None


def _unused_tcp_port_or_skip() -> int:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except PermissionError:
        pytest.skip('sandbox does not permit opening sockets')
    with sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_metrics_server_serves_metrics_and_404s_other_paths(listener):
    """End-to-end: bind a listener, hit /metrics, /healthz, /nope, verify
    each returns the right status."""
    unused_tcp_port = _unused_tcp_port_or_skip()

    async def run():
        listener.METRICS_PORT = unused_tcp_port
        server_task = asyncio.create_task(listener.metrics_server())
        await asyncio.sleep(0.1)

        async def get(path: str) -> tuple[str, str]:
            r, w = await asyncio.open_connection('127.0.0.1', unused_tcp_port)
            w.write(f'GET {path} HTTP/1.1\r\nHost: x\r\n\r\n'.encode())
            await w.drain()
            data = await r.read()
            head, _, body = data.decode().partition('\r\n\r\n')
            w.close(); await w.wait_closed()
            return head.split('\r\n', 1)[0], body

        status, body = await get('/metrics')
        assert status.startswith('HTTP/1.1 200'), (status, body)
        assert 'eddn_events_received_total' in body

        status, _ = await get('/healthz')
        assert status.startswith('HTTP/1.1 200'), status

        status, _ = await get('/wat')
        assert status.startswith('HTTP/1.1 404'), status

        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
