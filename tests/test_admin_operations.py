from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

from routers import admin as admin_router  # noqa: E402


def _fake_request() -> Request:
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': '/api/admin/operations/telemetry_hot_log_snapshot',
        'headers': [],
        'client': ('127.0.0.1', 12345),
    })


class _FakeConn:
    def __init__(self) -> None:
        self.finalize_calls: list[tuple] = []

    async def fetchval(self, query: str, *args):
        if 'INSERT INTO admin_job_runs' in query:
            return 77
        if 'WITH updated AS (' in query and 'UPDATE admin_job_runs' in query:
            return 0
        raise AssertionError(f'unexpected fetchval query: {query}')

    async def execute(self, query: str, *args):
        if 'UPDATE admin_job_runs' in query:
            self.finalize_calls.append(args)
            return 'UPDATE 1'
        if "set_config('statement_timeout'" in query:
            return 'SELECT 1'
        if "set_config('lock_timeout'" in query:
            return 'SELECT 1'
        if "set_config('application_name'" in query:
            return 'SELECT 1'
        if "set_config('max_parallel_workers_per_gather'" in query:
            return 'SELECT 1'
        if "set_config('work_mem'" in query:
            return 'SELECT 1'
        if "set_config('enable_hashjoin'" in query:
            return 'SELECT 1'
        raise AssertionError(f'unexpected execute query: {query}')

    async def fetch(self, query: str, *args):
        if 'FROM admin_job_runs' in query:
            return [
                {
                    'id': 91,
                    'job_key': 'telemetry_hot_log_snapshot',
                    'status': 'completed',
                    'started_at': '2026-07-11T12:30:00+00:00',
                    'finished_at': '2026-07-11T12:30:04+00:00',
                    'exit_code': 0,
                    'error_text': None,
                    'details_json': {
                        'operation_key': 'telemetry_hot_log_snapshot',
                        'script_name': 'telemetry_hot_log_snapshot.py',
                        'output_text': 'ED-Finder telemetry hot-log snapshot\njournal_import_staging:\n  total_rows: 26',
                    },
                },
            ]
        raise AssertionError(f'unexpected fetch query: {query}')


class _FakeAcquire:
    def __init__(self, conn: _FakeConn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _FakeAcquire(self.conn)


class _FakeReadonlyTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeReadonlyConn(_FakeConn):
    def transaction(self, readonly: bool = False):
        assert readonly is True
        return _FakeReadonlyTransaction()


class _FakeReadonlyPool(_FakePool):
    def __init__(self):
        self.conn = _FakeReadonlyConn()


@pytest.mark.asyncio
async def test_run_admin_operation_returns_output_and_persists_job_result(monkeypatch: pytest.MonkeyPatch):
    pool = _FakePool()
    readonly_pool = _FakeReadonlyPool()
    seen: dict[str, object] = {}

    async def fake_operation(_conn):
        seen['conn'] = _conn
        return True, 'ED-Finder telemetry hot-log snapshot\njournal_import_staging:\n  total_rows: 26\n'

    monkeypatch.setattr(admin_router, '_run_telemetry_hot_log_snapshot_operation', fake_operation)

    result = await admin_router.run_admin_operation(
        _fake_request(),
        'telemetry_hot_log_snapshot',
        pool=pool,
        readonly_pool=readonly_pool,
    )

    assert result['ok'] is True
    assert result['operation_key'] == 'telemetry_hot_log_snapshot'
    assert result['job_run_id'] == 77
    assert 'journal_import_staging' in result['output_text']
    assert pool.conn.finalize_calls, 'expected admin_job_runs finalization'
    assert seen['conn'] is readonly_pool.conn


@pytest.mark.asyncio
async def test_admin_operation_history_returns_recent_persisted_runs():
    pool = _FakePool()
    readonly_pool = _FakeReadonlyPool()

    result = await admin_router.admin_operation_history(pool=pool, readonly_pool=readonly_pool, limit=5)

    assert result['schema_version'] == 'admin_operation_history/v1'
    assert result['read_only'] is True
    assert len(result['operations']) == 1
    assert result['operations'][0]['job_run_id'] == 91
    assert result['operations'][0]['operation_key'] == 'telemetry_hot_log_snapshot'
    assert 'journal_import_staging' in str(result['operations'][0]['output_text'])
