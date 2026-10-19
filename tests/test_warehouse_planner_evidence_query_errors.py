"""Warehouse planner evidence: query timeouts are errors, not "missing evidence".

`_safe_fetchval` used to swallow every `asyncpg.PostgresError` and return
None, so a `statement_timeout` (QueryCanceledError) on the canonical
timestamp query produced the same "Canonical evidence timestamps are
unavailable" warning as a genuinely absent table. Only undefined-table /
undefined-column errors mean "missing"; everything else must surface, with
a bounded message that never carries the raw database text.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import asyncpg
import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from edfinder_api import warehouse_planner_evidence_provider as provider  # noqa: E402
from edfinder_api.routers import warehouse_planner_evidence as route  # noqa: E402


class _Conn:
    def __init__(self, exc: BaseException):
        self.exc = exc

    async def fetchval(self, query, *args):
        raise self.exc


async def test_undefined_table_is_missing_evidence():
    assert await provider._safe_fetchval(_Conn(asyncpg.UndefinedTableError('relation "x" does not exist')), 'SELECT 1') is None


async def test_undefined_column_is_missing_evidence():
    assert await provider._safe_fetchval(_Conn(asyncpg.UndefinedColumnError('column "y" does not exist')), 'SELECT 1') is None


@pytest.mark.parametrize(
    'exc',
    [
        asyncpg.QueryCanceledError('canceling statement due to statement timeout'),
        asyncpg.InsufficientPrivilegeError('permission denied for table systems'),
        asyncpg.InterfaceError('connection is closed'),
        TimeoutError(),
    ],
)
async def test_other_errors_surface_as_query_errors(exc):
    with pytest.raises(provider.PlannerEvidenceQueryError) as excinfo:
        await provider._safe_fetchval(_Conn(exc), 'SELECT 1', stage='canonical evidence')
    assert excinfo.value.__cause__ is exc
    assert excinfo.value.error_type == type(exc).__name__


def test_query_error_message_is_bounded_and_non_sensitive():
    raw = asyncpg.QueryCanceledError(
        'canceling statement due to statement timeout while running '
        "SELECT * FROM systems -- postgresql://user:secret@db.internal:5432/edfinder"
    )
    err = provider.PlannerEvidenceQueryError('canonical evidence', raw)
    text = str(err)

    assert text == 'canonical evidence query failed: QueryCanceledError sqlstate=57014'
    assert 'secret' not in text
    assert 'SELECT' not in text
    assert 'db.internal' not in text
    assert len(text) < 200


def test_query_error_truncates_stage_and_type_names():
    err = provider.PlannerEvidenceQueryError('s' * 500, RuntimeError('x'))
    assert len(err.stage) == 64
    assert err.error_type == 'RuntimeError'


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TimeoutOnCanonicalConn:
    """Answers the system/count queries, then times out on the MAX(ts) query."""

    async def fetchrow(self, query, *args):
        return {'id64': 1, 'name': 'Sol'}

    async def fetchval(self, query, *args):
        if 'SELECT MAX(ts)::text' in query:
            raise asyncpg.QueryCanceledError('canceling statement due to statement timeout')
        if 'to_regclass' in query:
            return True
        return 0


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


async def test_live_provider_propagates_timeout_instead_of_reporting_missing():
    with pytest.raises(provider.PlannerEvidenceQueryError):
        await provider.load_live_planner_evidence(_Pool(_TimeoutOnCanonicalConn()), 1)


async def test_route_turns_query_error_into_503_with_bounded_detail(monkeypatch, caplog):
    async def fail(pool, id64):
        raise provider.PlannerEvidenceQueryError(
            'canonical evidence',
            asyncpg.QueryCanceledError('canceling statement due to statement timeout'),
        )

    monkeypatch.setattr(route, 'load_live_planner_evidence', fail)

    with pytest.raises(HTTPException) as excinfo:
        await route.warehouse_planner_evidence(1, pool=object())

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == 'canonical evidence query failed: QueryCanceledError sqlstate=57014'
    assert 'warehouse planner evidence query failed for 1' in caplog.text


async def test_observed_summary_timeout_surfaces(monkeypatch):
    class _PresentConn:
        async def fetchval(self, query, *args):
            return True

    async def timeout_summary(pool, id64):
        raise asyncpg.QueryCanceledError('canceling statement due to statement timeout')

    monkeypatch.setattr(provider, 'observed_fact_summary', timeout_summary)

    with pytest.raises(provider.PlannerEvidenceQueryError) as excinfo:
        await provider._safe_observed_summary(_Pool(_PresentConn()), 1)
    assert excinfo.value.stage == 'observed evidence'


async def test_observed_summary_missing_column_stays_a_warning(monkeypatch):
    class _PresentConn:
        async def fetchval(self, query, *args):
            return True

    async def missing_column(pool, id64):
        raise asyncpg.UndefinedColumnError('column "fact_type" does not exist')

    monkeypatch.setattr(provider, 'observed_fact_summary', missing_column)

    result = await provider._safe_observed_summary(_Pool(_PresentConn()), 1)
    assert result['_warning'].startswith('Observed evidence could not be summarized safely')
