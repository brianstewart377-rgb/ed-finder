from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

from routers import admin as admin_router  # noqa: E402


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def transaction(self, readonly: bool = False):
        assert readonly is True
        return _FakeTransaction()

    async def fetchval(self, query: str, *args):
        if "last_nightly_update" in query:
            return '2026-07-11T01:30:00+00:00'
        if 'WITH updated AS (' in query and 'UPDATE admin_job_runs' in query:
            return 0
        raise AssertionError(f'unexpected fetchval query: {query}')

    async def fetchrow(self, query: str, *args):
        if 'FROM source_runs' in query:
            return {
                'runs_last_24h': 4,
                'failed_runs_last_24h': 1,
                'latest_started_at': '2026-07-11T02:00:00+00:00',
                'latest_finished_at': '2026-07-11T02:05:00+00:00',
            }
        if 'FROM systems' in query and 'rating_dirty = true' in query:
            return {
                'dirty_systems': 12,
                'oldest_dirty_updated_at': '2026-07-10T23:30:00+00:00',
                'newest_dirty_updated_at': '2026-07-11T02:15:00+00:00',
            }
        raise AssertionError(f'unexpected fetchrow query: {query}')

    async def fetch(self, query: str, *args):
        if 'FROM source_runs' in query:
            return [
                {
                    'source_name': 'spansh_import',
                    'domain': 'canonical',
                    'trigger_context': 'scheduled_nightly',
                    'status': 'succeeded',
                    'started_at': '2026-07-11T02:00:00+00:00',
                    'finished_at': '2026-07-11T02:05:00+00:00',
                    'rows_read': 900,
                    'rows_staged': 850,
                },
            ]
        if 'FROM admin_job_runs' in query:
            return [
                {
                    'id': 41,
                    'job_key': 'cluster_rebuild',
                    'status': 'completed',
                    'started_at': '2026-07-11T02:10:00+00:00',
                    'finished_at': '2026-07-11T02:12:00+00:00',
                    'exit_code': 0,
                    'error_text': None,
                    'details_json': {},
                },
                {
                    'id': 42,
                    'job_key': 'ratings_rebuild',
                    'status': 'completed',
                    'started_at': '2026-07-11T02:15:00+00:00',
                    'finished_at': '2026-07-11T02:16:00+00:00',
                    'exit_code': 0,
                    'error_text': None,
                    'details_json': {'dirty_before': 12, 'cleared': 12},
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


@pytest.mark.asyncio
async def test_admin_cron_status_prefers_persisted_job_history_over_memory_state():
    pool = _FakePool()
    readonly_pool = _FakePool()
    original_active_jobs = dict(admin_router.active_jobs)
    admin_router.active_jobs.clear()
    admin_router.active_jobs.update({
        'cluster_rebuild': {
            'status': 'running',
            'start_time': '2099-01-01T00:00:00+00:00',
        },
        'ratings_rebuild': {
            'status': 'running',
            'start_time': '2099-01-01T00:00:00+00:00',
        },
    })

    try:
        status = await admin_router.admin_cron_status(pool=pool, readonly_pool=readonly_pool)
    finally:
        admin_router.active_jobs.clear()
        admin_router.active_jobs.update(original_active_jobs)

    assert status['schema_version'] == 'admin_cron_status/v1'
    assert status['scheduled_source_runs']['runs_last_24h'] == 4
    assert status['jobs']['cluster_rebuild']['status'] == 'completed'
    assert status['jobs']['cluster_rebuild']['job_run_id'] == 41
    assert status['jobs']['ratings_rebuild']['dirty_before'] == 12
    assert status['jobs']['ratings_rebuild']['cleared'] == 12
