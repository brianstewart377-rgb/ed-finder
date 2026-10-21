"""`local_db_status()` reports a bounded reason code, never raw error text.

Follow-up to PR #864, which fixed the leak at the `/api/local/status`
boundary (`routers/meta.py`) only. The producer in `local_search.py` still
returned ``{"available": False, "reason": str(exc)}``; it now classifies the
exception by type into one of ``helpers.STATUS_REASON_CODES`` and keeps the
raw text in the server log. ``meta.status_failure_reason_code`` passes a
code through unchanged and still text-classifies anything else, so the two
layers agree on one code set.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import asyncpg
import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from edfinder_api import helpers, local_search  # noqa: E402
from edfinder_api.models import StatusResponse  # noqa: E402
from edfinder_api.routers import meta  # noqa: E402


SECRET_TEXT = 'canceling statement due to statement timeout -- postgresql://user:secret@db.internal/edfinder'


class _FailingPool:
    """Pool whose acquire() raises the given exception."""

    def __init__(self, exc: BaseException):
        self._exc = exc

    def acquire(self):
        exc = self._exc

        class _Ctx:
            async def __aenter__(self):
                raise exc

            async def __aexit__(self, *args):
                return False

        return _Ctx()


def _pg(cls, text=SECRET_TEXT):
    """Build an asyncpg server-error instance of ``cls`` carrying ``text``."""
    return cls.new({'M': text, 'C': getattr(cls, 'sqlstate', '00000') or '00000', 'S': 'ERROR'})


@pytest.mark.parametrize(
    ('exc', 'code'),
    [
        (TimeoutError(SECRET_TEXT), helpers.STATUS_REASON_TIMEOUT),
        (_pg(asyncpg.QueryCanceledError), helpers.STATUS_REASON_TIMEOUT),
        (_pg(asyncpg.UndefinedTableError, 'relation "import_meta" does not exist'), helpers.STATUS_REASON_SCHEMA),
        (_pg(asyncpg.UndefinedColumnError), helpers.STATUS_REASON_SCHEMA),
        (_pg(asyncpg.UndefinedFunctionError), helpers.STATUS_REASON_SCHEMA),
        (_pg(asyncpg.InvalidSchemaNameError), helpers.STATUS_REASON_SCHEMA),
        (asyncpg.InterfaceError('pool is closed'), helpers.STATUS_REASON_CONNECTION),
        (_pg(asyncpg.TooManyConnectionsError), helpers.STATUS_REASON_CONNECTION),
        (_pg(asyncpg.CannotConnectNowError), helpers.STATUS_REASON_CONNECTION),
        (_pg(asyncpg.PostgresConnectionError), helpers.STATUS_REASON_CONNECTION),
        (ConnectionRefusedError(111, 'Connection refused'), helpers.STATUS_REASON_CONNECTION),
        (OSError('Network is unreachable'), helpers.STATUS_REASON_CONNECTION),
        (_pg(asyncpg.PostgresSyntaxError), helpers.STATUS_REASON_UNKNOWN),
        (_pg(asyncpg.InsufficientPrivilegeError), helpers.STATUS_REASON_UNKNOWN),
        (RuntimeError(SECRET_TEXT), helpers.STATUS_REASON_UNKNOWN),
        (ValueError('x' * 10_000), helpers.STATUS_REASON_UNKNOWN),
    ],
)
def test_exception_classification_is_by_type_and_bounded(exc, code):
    result = helpers.status_failure_reason_code_for_exception(exc)
    assert result == code
    assert result in helpers.STATUS_REASON_CODES


def test_code_sets_agree_between_helpers_and_meta():
    assert meta.STATUS_REASON_CODES == helpers.STATUS_REASON_CODES
    assert helpers.STATUS_REASON_CODES == frozenset({
        'db_timeout', 'db_schema_missing', 'db_unavailable', 'db_error',
    })


@pytest.mark.parametrize(
    ('exc', 'code'),
    [
        (_pg(asyncpg.QueryCanceledError), 'db_timeout'),
        (_pg(asyncpg.UndefinedTableError, 'relation "galaxy_regions" does not exist'), 'db_schema_missing'),
        (asyncpg.InterfaceError('pool is closed'), 'db_unavailable'),
        (RuntimeError(SECRET_TEXT), 'db_error'),
    ],
)
async def test_local_db_status_returns_only_a_reason_code(exc, code, caplog):
    caplog.set_level('WARNING', logger=local_search.log.name)

    result = await local_search.local_db_status(_FailingPool(exc))

    assert result == {'available': False, 'reason': code}
    assert 'secret' not in str(result)
    # The raw text is still there for the operator, in the log only.
    assert 'local_db_status error' in caplog.text
    assert f'({code})' in caplog.text
    assert type(exc).__name__ in caplog.text
    # The payload stays valid against the strict (extra=forbid) response model.
    StatusResponse.model_validate(result)


def test_meta_passes_a_producer_code_through_unchanged():
    for code in helpers.STATUS_REASON_CODES:
        assert meta.status_failure_reason_code(code) == code


def test_meta_still_classifies_raw_text_as_defence_in_depth():
    # If the producer ever regresses to str(exc), the boundary still bounds it.
    assert meta.status_failure_reason_code(SECRET_TEXT) == 'db_timeout'
    assert meta.status_failure_reason_code('db_timeout_extra') == 'db_timeout'
    assert meta.status_failure_reason_code('DB_TIMEOUT') == 'db_timeout'
    assert meta.status_failure_reason_code('relation does not exist') == 'db_schema_missing'
    assert meta.status_failure_reason_code(42) == 'db_error'


async def test_end_to_end_status_route_never_caches_or_leaks(monkeypatch, caplog):
    """`/api/local/status` → `local_db_status` → failure: no cache write,
    the code is served unchanged and the raw text appears only in the log."""
    sets: list[tuple] = []

    async def fake_get(key, redis=None):
        return None

    async def fake_set(key, value, ttl, redis=None):
        sets.append((key, value, ttl))

    monkeypatch.setattr(meta, 'cache_get', fake_get)
    monkeypatch.setattr(meta, 'cache_set', fake_set)
    monkeypatch.setattr(meta, '_ls', local_search)
    monkeypatch.setattr(meta, '_LS_AVAILABLE', True)

    body = await meta.local_status(pool=_FailingPool(_pg(asyncpg.QueryCanceledError)), redis=None)

    assert body == {'available': False, 'reason': 'db_timeout'}
    assert sets == []
    assert 'secret' not in str(body)
    assert 'secret' in caplog.text


def test_local_search_no_longer_returns_str_exc():
    source = (API_SRC / 'local_search.py').read_text(encoding='utf-8')
    assert '"reason": str(exc)' not in source
    assert 'status_failure_reason_code_for_exception(exc)' in source
