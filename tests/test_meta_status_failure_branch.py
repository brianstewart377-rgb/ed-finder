"""/api/local/status: a failure payload is never cached and never leaks raw text.

`local_db_status()` swallows database errors and returns
``{"available": False, "reason": str(exc)}``. The router used to cache that
payload for ``ttl_status`` (60 s) and return it verbatim — so a one-off
blip became a minute of "unavailable", and the raw exception text (which can
carry SQL, host names or DSN fragments) went to the caller. The router now
skips the cache on the failure branch and maps the reason to a fixed code.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from edfinder_api.models import StatusResponse  # noqa: E402
from edfinder_api.routers import meta  # noqa: E402


RAW_REASON = 'canceling statement due to statement timeout -- postgresql://user:secret@db.internal/edfinder'


class _FakeLocalSearch:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def local_db_status(self, pool):
        self.calls += 1
        return self.result


@pytest.fixture
def cache_spy(monkeypatch):
    store: dict[str, object] = {}
    sets: list[tuple] = []

    async def fake_get(key, redis=None):
        return store.get(key)

    async def fake_set(key, value, ttl, redis=None):
        sets.append((key, value, ttl))
        store[key] = value

    monkeypatch.setattr(meta, 'cache_get', fake_get)
    monkeypatch.setattr(meta, 'cache_set', fake_set)
    return sets


async def test_failure_payload_is_not_cached_and_reason_is_a_code(monkeypatch, cache_spy, caplog):
    fake_ls = _FakeLocalSearch({'available': False, 'reason': RAW_REASON})
    monkeypatch.setattr(meta, '_ls', fake_ls)
    monkeypatch.setattr(meta, '_LS_AVAILABLE', True)

    first = await meta.local_status(pool=object(), redis=None)
    second = await meta.local_status(pool=object(), redis=None)

    assert first == {'available': False, 'reason': 'db_timeout'}
    assert second == first
    assert fake_ls.calls == 2, 'the failure branch must be re-evaluated on every request'
    assert cache_spy == [], 'a failure payload must never be written to the cache'
    assert 'secret' not in str(first)
    # The raw reason still goes to the server log for the operator.
    assert 'local_db_status unavailable' in caplog.text
    # The payload stays valid against the strict (extra=forbid) response model.
    StatusResponse.model_validate(first)


async def test_success_payload_is_still_cached(monkeypatch, cache_spy):
    ok = {'available': True, 'backend': 'postgresql', 'systems_count': 5, 'version': 'x'}
    fake_ls = _FakeLocalSearch(ok)
    monkeypatch.setattr(meta, '_ls', fake_ls)
    monkeypatch.setattr(meta, '_LS_AVAILABLE', True)

    first = await meta.local_status(pool=object(), redis=None)
    second = await meta.local_status(pool=object(), redis=None)

    assert first == ok
    assert second == ok
    assert fake_ls.calls == 1, 'the success payload is served from cache'
    assert cache_spy == [('status:local', ok, meta.settings.ttl_status)]


@pytest.mark.parametrize(
    ('raw', 'code'),
    [
        ('canceling statement due to statement timeout', 'db_timeout'),
        ('TimeoutError', 'db_timeout'),
        ('relation "import_meta" does not exist', 'db_schema_missing'),
        ('UndefinedTableError: ...', 'db_schema_missing'),
        ('connection refused', 'db_unavailable'),
        ('pool is closed', 'db_unavailable'),
        ('too many connections for role', 'db_unavailable'),
        ('something else entirely', 'db_error'),
        (None, 'db_error'),
        ('', 'db_error'),
    ],
)
def test_reason_codes_are_bounded(raw, code):
    result = meta.status_failure_reason_code(raw)
    assert result == code
    assert result in meta.STATUS_REASON_CODES


def test_reason_code_never_echoes_input():
    assert meta.status_failure_reason_code(RAW_REASON) == 'db_timeout'
    for raw in ('x' * 10_000, 'postgresql://a:b@c/d', '<script>'):
        assert meta.status_failure_reason_code(raw) in meta.STATUS_REASON_CODES
