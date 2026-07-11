from __future__ import annotations

import os
import sys
from datetime import timezone
from pathlib import Path

import pytest
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
SQL_PATH = ROOT / 'sql' / '032_journal_import_staging.sql'
MANIFEST_PATH = ROOT / 'sql' / 'migration-manifest.txt'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

from journal_import.api_models import (  # noqa: E402
    JournalImportReceipt,
    JournalImportRequest,
    JournalPromotionReceipt,
    JournalTelemetrySummaryResponse,
)
from routers import journal_import as journal_import_router  # noqa: E402


def _fake_request() -> Request:
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': '/api/journal/import',
        'headers': [],
        'client': ('127.0.0.1', 12345),
    })


class _FakeJournalImportStore:
    def __init__(self) -> None:
        self.receipts: dict[str, dict[str, object]] = {}

    async def import_journal_batch(self, _pool: object, request):
        receipt = JournalImportReceipt.model_validate({
            'run_key': 'jrnl-20260708-demo',
            'status': 'succeeded',
            'parser_version': request.client_manifest.parser_version,
            'started_at': '2026-07-08T18:00:00+00:00',
            'finished_at': '2026-07-08T18:00:01+00:00',
            'files': [item.model_dump(mode='json') for item in request.client_manifest.files],
            'summary': {
                'observations_received': len(request.observations),
                'observations_staged': len(request.observations),
                'duplicates_skipped': 0,
                'conflicts_flagged': 0,
                'files_seen': len(request.client_manifest.files),
                'event_counts': {'Scan': len(request.observations)},
            },
        })
        self.receipts[receipt.run_key] = receipt
        return receipt

    async def get_journal_import_receipt(self, _pool: object, run_key: str):
        return self.receipts.get(run_key)

    async def promote_journal_batch(self, _pool: object, run_key: str):
        if run_key not in self.receipts:
            return None
        return JournalPromotionReceipt.model_validate({
            'run_key': run_key,
            'status': 'succeeded',
            'promoted_at': '2026-07-11T09:00:00+00:00',
            'duration_ms': 12,
            'summary': {
                'staged_rows_seen': 1,
                'eligible_rows': 1,
                'skipped_rows': 0,
                'facts_promoted': 1,
                'ring_rows_promoted': 0,
                'ring_rows_unresolved': 0,
                'dirty_systems_marked': 1,
                'event_counts': {'Scan': 1},
            },
        })

    async def get_journal_telemetry_summary(self, _pool: object, sync_key: str):
        return JournalTelemetrySummaryResponse.model_validate({
            'sync_key': sync_key,
            'runs_count': 2,
            'last_imported_at': '2026-07-11T12:00:00+00:00',
            'observations_staged': 5,
            'duplicates_skipped': 1,
            'systems_observed': 2,
            'body_observation_count': 3,
            'docked_observation_count': 1,
            'event_counts': {'Scan': 3, 'Docked': 1, 'Location': 1},
            'recent_runs': [
                {
                    'run_key': 'jrnl-20260711-demo-a',
                    'status': 'succeeded',
                    'started_at': '2026-07-11T11:00:00+00:00',
                    'finished_at': '2026-07-11T11:00:05+00:00',
                    'observations_staged': 3,
                    'duplicates_skipped': 1,
                    'event_counts': {'Scan': 2, 'Docked': 1},
                },
            ],
            'recent_systems': [
                {
                    'system_id64': 123,
                    'system_name': 'Test System',
                    'last_observed_at': '2026-07-11T11:59:00+00:00',
                    'event_count': 3,
                    'event_types': ['Docked', 'Scan'],
                },
            ],
        })


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> _FakeJournalImportStore:
    store = _FakeJournalImportStore()
    monkeypatch.setattr(journal_import_router.store, 'import_journal_batch', store.import_journal_batch)
    monkeypatch.setattr(journal_import_router.store, 'get_journal_import_receipt', store.get_journal_import_receipt)
    monkeypatch.setattr(journal_import_router.store, 'promote_journal_batch', store.promote_journal_batch)
    monkeypatch.setattr(journal_import_router.store, 'get_journal_telemetry_summary', store.get_journal_telemetry_summary)
    return store


@pytest.mark.asyncio
async def test_post_journal_import_returns_staging_receipt(fake_store: _FakeJournalImportStore):
    request = JournalImportRequest.model_validate({
            'sync_key': 'sync-key-1234567890',
            'client_manifest': {
                'parser_version': 'journal-import-worker-v1',
                'files': [{'name': 'Journal.demo.log', 'event_count': 1}],
            },
            'evidence_mode': 'staging_only',
            'observations': [
                {
                    'observation_key': '0123456789abcdef0123456789abcdef',
                    'source_file': 'Journal.demo.log',
                    'event_type': 'Scan',
                    'observed_at': '2026-07-08T18:00:00Z',
                    'system_id64': 123,
                    'system_name': 'Test System',
                    'subject_type': 'body',
                    'subject_id': '7',
                    'summary': 'Body scan observed for Test 7.',
                    'payload': {'BodyName': 'Test 7'},
                    'privacy_boundary': {'strip_before_network': True},
                },
            ],
        })
    receipt = await journal_import_router.import_frontier_journal(_fake_request(), request, pool=object())

    assert receipt.run_key == 'jrnl-20260708-demo'
    assert receipt.parser_version == 'journal-import-worker-v1'
    assert receipt.summary.observations_received == 1
    assert receipt.summary.observations_staged == 1


@pytest.mark.asyncio
async def test_get_journal_import_receipt_returns_existing_run(fake_store: _FakeJournalImportStore):
    fake_store.receipts['jrnl-20260708-demo'] = JournalImportReceipt.model_validate({
        'run_key': 'jrnl-20260708-demo',
        'status': 'succeeded',
        'parser_version': 'journal-import-worker-v1',
        'started_at': '2026-07-08T18:00:00+00:00',
        'finished_at': '2026-07-08T18:00:01+00:00',
        'files': [{'name': 'Journal.demo.log', 'event_count': 1}],
        'summary': {
            'observations_received': 1,
            'observations_staged': 1,
            'duplicates_skipped': 0,
            'conflicts_flagged': 0,
            'files_seen': 1,
            'event_counts': {'Scan': 1},
        },
    })
    receipt = await journal_import_router.get_frontier_journal_import(_fake_request(), 'jrnl-20260708-demo', pool=object())

    assert receipt.summary.event_counts == {'Scan': 1}


@pytest.mark.asyncio
async def test_post_journal_import_promotion_returns_operator_receipt(fake_store: _FakeJournalImportStore):
    fake_store.receipts['jrnl-20260708-demo'] = JournalImportReceipt.model_validate({
        'run_key': 'jrnl-20260708-demo',
        'status': 'succeeded',
        'parser_version': 'journal-import-worker-v1',
        'started_at': '2026-07-08T18:00:00+00:00',
        'finished_at': '2026-07-08T18:00:01+00:00',
        'files': [{'name': 'Journal.demo.log', 'event_count': 1}],
        'summary': {
            'observations_received': 1,
            'observations_staged': 1,
            'duplicates_skipped': 0,
            'conflicts_flagged': 0,
            'files_seen': 1,
            'event_counts': {'Scan': 1},
        },
    })

    receipt = await journal_import_router.promote_frontier_journal_import(
        _fake_request(),
        'jrnl-20260708-demo',
        pool=object(),
    )

    assert receipt.run_key == 'jrnl-20260708-demo'
    assert receipt.summary.facts_promoted == 1
    assert receipt.summary.dirty_systems_marked == 1


@pytest.mark.asyncio
async def test_get_journal_telemetry_summary_returns_sync_key_scoped_snapshot(fake_store: _FakeJournalImportStore):
    telemetry = await journal_import_router.get_frontier_journal_telemetry(
        _fake_request(),
        'sync-key-1234567890',
        pool=object(),
    )

    assert telemetry.sync_key == 'sync-key-1234567890'
    assert telemetry.runs_count == 2
    assert telemetry.event_counts['Scan'] == 3
    assert telemetry.recent_systems[0].system_name == 'Test System'


@pytest.mark.unit
def test_journal_import_request_requires_sync_key():
    with pytest.raises(Exception):
        JournalImportRequest.model_validate({
            'sync_key': 'short',
            'client_manifest': {
                'parser_version': 'journal-import-worker-v1',
                'files': [],
            },
            'observations': [],
        })


@pytest.mark.unit
def test_journal_import_request_rejects_non_staging_evidence_modes():
    with pytest.raises(Exception):
        JournalImportRequest.model_validate({
            'sync_key': 'sync-key-1234567890',
            'client_manifest': {
                'parser_version': 'journal-import-worker-v1',
                'files': [],
            },
            'evidence_mode': 'quarantined',
            'observations': [],
        })


@pytest.mark.unit
def test_journal_import_request_normalizes_observed_at_to_utc_datetime():
    request = JournalImportRequest.model_validate({
        'sync_key': 'sync-key-1234567890',
        'client_manifest': {
            'parser_version': 'journal-import-worker-v1',
            'files': [],
        },
        'observations': [
            {
                'observation_key': '0123456789abcdef0123456789abcdef',
                'source_file': 'Journal.demo.log',
                'event_type': 'Scan',
                'observed_at': '2026-07-08T18:00:00Z',
                'system_id64': 123,
                'subject_type': 'body',
                'subject_id': '7',
                'payload': {},
                'privacy_boundary': {},
            },
        ],
    })

    observed_at = request.observations[0].observed_at
    assert observed_at is not None
    assert observed_at.tzinfo == timezone.utc
    assert observed_at.isoformat() == '2026-07-08T18:00:00+00:00'


@pytest.mark.unit
def test_journal_import_migration_is_manifested_and_bounded():
    sql = SQL_PATH.read_text(encoding='utf-8')
    manifest = MANIFEST_PATH.read_text(encoding='utf-8')

    assert 'CREATE TABLE IF NOT EXISTS journal_import_staging' in sql
    assert 'source_record_hash  TEXT            NOT NULL UNIQUE' in sql
    assert '032_journal_import_staging.sql' in manifest
