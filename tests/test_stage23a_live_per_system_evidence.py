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

import warehouse_planner_evidence as backend  # noqa: E402
import warehouse_planner_evidence_provider as provider  # noqa: E402
from warehouse_planner_evidence_provider import LivePlannerEvidenceResult  # noqa: E402
from warehouse_planner_evidence_models import WarehousePlannerEvidenceBoundedStaging  # noqa: E402


class _FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _FakeAcquire(self.conn)


class _FakeConnection:
    def __init__(
        self,
        *,
        system: dict[str, object] | None,
        body_count: int = 0,
        station_count: int = 0,
        has_station_links: bool = True,
        linked_station_count: int | None = None,
        latest_canonical_at: str | None = None,
        stage19bb_tables_present: bool = False,
        stage19bb_rows: list[dict[str, object]] | None = None,
    ):
        self.system = system
        self.body_count = body_count
        self.station_count = station_count
        self.has_station_links = has_station_links
        self.linked_station_count = linked_station_count
        self.latest_canonical_at = latest_canonical_at
        self.stage19bb_tables_present = stage19bb_tables_present
        self.stage19bb_rows = stage19bb_rows or []

    async def fetchrow(self, query: str, *args):
        if 'SELECT id64, name FROM systems' in query:
            return self.system
        if "to_regclass('public.enrichment_source_runs')" in query:
            return {
                'has_bridge': self.stage19bb_tables_present,
                'has_staging': self.stage19bb_tables_present,
            }
        raise AssertionError(f'Unexpected fetchrow query: {query}')

    async def fetch(self, query: str, *args):
        if 'FROM enrichment_source_runs esr' in query and 'JOIN staging_edsm_stations ses' in query:
            return self.stage19bb_rows
        raise AssertionError(f'Unexpected fetch query: {query}')

    async def fetchval(self, query: str, *args):
        if "to_regclass('public.station_body_links')" in query:
            return self.has_station_links
        if "to_regclass('public.observed_facts')" in query:
            return True
        if 'COUNT(*)::int FROM bodies' in query:
            return self.body_count
        if 'COUNT(*)::int FROM stations' in query and 'station_body_links' not in query:
            return self.station_count
        if 'FROM station_body_links l' in query:
            return self.linked_station_count
        if 'SELECT MAX(ts)::text' in query:
            return self.latest_canonical_at
        raise AssertionError(f'Unexpected fetchval query: {query}')


@pytest.mark.asyncio
async def test_stage23a_live_provider_returns_real_source_labelled_system_evidence(monkeypatch: pytest.MonkeyPatch):
    async def _observed_summary(_pool, _id64: int):
        return {
            'total_count': 3,
            'by_fact_type': {'service_presence': 2, 'economy': 1},
            'latest_observed_at': '2026-06-18T09:30:00Z',
        }

    monkeypatch.setattr(provider, 'observed_fact_summary', _observed_summary)
    pool = _FakePool(
        _FakeConnection(
            system={'id64': 9466842275401, 'name': 'Lave'},
            body_count=4,
            station_count=2,
            has_station_links=True,
            linked_station_count=1,
            latest_canonical_at='2026-06-18T08:00:00Z',
        )
    )

    result = await provider.load_live_planner_evidence(pool, 9466842275401)

    assert result.availability == 'report_only'
    assert result.envelope_status == 'available'
    assert result.freshness_status == 'not_evaluated'
    assert result.evaluated_at == '2026-06-18T09:30:00Z'
    assert result.manual_review_required is True
    assert any(item.source == 'canonical' for item in result.items)
    assert any(item.source == 'observed' for item in result.items)
    assert any('Lave' in item.summary for item in result.items if item.source == 'canonical')
    assert any('service_presence:2' in item.summary for item in result.items if item.source == 'observed')
    assert result.bounded_staging.status == 'not_evaluated'
    assert any('not evaluated' in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
async def test_stage23b_live_provider_exposes_bounded_staging_provenance_when_safe_rows_exist(monkeypatch: pytest.MonkeyPatch):
    async def _observed_summary(_pool, _id64: int):
        return {'total_count': 0, 'by_fact_type': {}, 'latest_observed_at': None}

    monkeypatch.setattr(provider, 'observed_fact_summary', _observed_summary)
    pool = _FakePool(
        _FakeConnection(
            system={'id64': 9466842275401, 'name': 'Lave'},
            body_count=4,
            station_count=2,
            has_station_links=True,
            linked_station_count=1,
            latest_canonical_at='2026-06-18T08:00:00Z',
            stage19bb_tables_present=True,
            stage19bb_rows=[
                {
                    'bridge_key': 'source_runs:stage19bb-edsm-1000-row-bounded-staging-20260619T195942Z',
                    'matched_row_count': 1,
                    'latest_source_updated_at': '2026-06-19T19:59:42Z',
                },
                {
                    'bridge_key': 'source_runs:stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z',
                    'matched_row_count': 2,
                    'latest_source_updated_at': '2026-06-19T20:00:18Z',
                },
            ],
        )
    )

    result = await provider.load_live_planner_evidence(pool, 9466842275401)

    assert result.availability == 'report_only'
    assert result.envelope_status == 'available'
    assert result.bounded_staging.status == 'available'
    assert result.bounded_staging.source_name == 'edsm'
    assert result.bounded_staging.source_sha256 == 'b256017814a1015fb24748c8027f1a00cba2f187a257ef3e0f9e3a6ba6e45984'
    assert result.bounded_staging.source_run_key == 'stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z'
    assert result.bounded_staging.bridge_key == 'source_runs:stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z'
    assert result.bounded_staging.row_limit == 10000
    assert result.bounded_staging.available_row_limits == [1000, 10000]
    assert result.bounded_staging.matched_row_count == 2
    assert any(item.source == 'warehouse_report_only' for item in result.items)
    assert any('not canonical truth' in warning.lower() for warning in result.warnings)
    assert any('full edsm coverage' in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
async def test_stage23b_live_provider_returns_unavailable_when_system_has_no_bounded_rows(monkeypatch: pytest.MonkeyPatch):
    async def _observed_summary(_pool, _id64: int):
        return {'total_count': 0, 'by_fact_type': {}, 'latest_observed_at': None}

    monkeypatch.setattr(provider, 'observed_fact_summary', _observed_summary)
    pool = _FakePool(
        _FakeConnection(
            system={'id64': 9466842275401, 'name': 'Lave'},
            body_count=4,
            station_count=2,
            has_station_links=True,
            linked_station_count=1,
            latest_canonical_at='2026-06-18T08:00:00Z',
            stage19bb_tables_present=True,
            stage19bb_rows=[],
        )
    )

    result = await provider.load_live_planner_evidence(pool, 9466842275401)

    assert result.availability == 'report_only'
    assert result.envelope_status == 'available'
    assert result.bounded_staging.status == 'unavailable'
    assert result.bounded_staging.source_run_key is None
    assert result.bounded_staging.row_limit is None
    assert any('bounded staging remains unavailable' in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
async def test_stage23a_live_provider_keeps_unknown_systems_unavailable(monkeypatch: pytest.MonkeyPatch):
    async def _observed_summary(_pool, _id64: int):
        raise AssertionError('Observed summary should not run for missing systems')

    monkeypatch.setattr(provider, 'observed_fact_summary', _observed_summary)
    pool = _FakePool(_FakeConnection(system=None))

    result = await provider.load_live_planner_evidence(pool, 42)

    assert result.availability == 'unavailable'
    assert result.envelope_status == 'unknown'
    assert result.freshness_status == 'unknown'
    assert result.evaluated_at is None
    assert result.manual_review_required is True
    assert result.items == []
    assert any('unavailable' in warning.lower() for warning in result.warnings)


@pytest.mark.unit
def test_stage23a_builder_uses_live_provider_results_and_fixture_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        backend,
        'read_warehouse_status_snapshot',
        lambda _path: {
            'available': True,
            'message': 'Warehouse status artifact loaded.',
            'artifact': {'file_name': 'warehouse-status.json', 'updated_at': '2026-06-18T14:00:00+00:00'},
            'latest_reconciliation_run': {'report_file_name': 'run-20260618.json'},
            'warnings': [],
        },
    )
    monkeypatch.setattr(backend, 'resolve_runtime_warehouse_fixture', lambda _id64: None)

    live_result = LivePlannerEvidenceResult(
        availability='report_only',
        envelope_status='available',
        items=[
            backend.WarehousePlannerEvidenceItem(
                label='report_only',
                source='canonical',
                summary='Canonical app data includes 2 stations and 4 bodies.',
            ),
            backend.WarehousePlannerEvidenceItem(
                label='needs_review',
                source='observed',
                summary='Observed evidence includes 3 persisted facts; latest observed at 2026-06-18T09:30:00Z.',
            ),
        ],
        freshness_status='not_evaluated',
        evaluated_at='2026-06-18T09:30:00Z',
        manual_review_required=True,
        bounded_staging=WarehousePlannerEvidenceBoundedStaging(
            status='available',
            report_only=True,
            bounded_staging_only=True,
            source_name='edsm',
            source_batch_label='edsm-stations-20260619T190906Z',
            source_sha256='b256017814a1015fb24748c8027f1a00cba2f187a257ef3e0f9e3a6ba6e45984',
            source_run_key='stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z',
            bridge_key='source_runs:stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z',
            row_limit=10000,
            available_row_limits=[1000, 10000],
            matched_row_count=2,
            latest_source_updated_at='2026-06-19T20:00:18Z',
            summary='Stage 19BB bounded staging evidence includes 2 staging rows for this system in the approved 10000-row context; it remains bounded staging-only review context, not canonical truth and not full EDSM coverage.',
        ),
        warnings=['Stage 19BB bounded staging evidence is available for this system as report-only context only; it is not canonical truth and does not imply full EDSM coverage.'],
    )

    response = backend.build_warehouse_planner_evidence(9466842275401, live_result=live_result)

    assert response.schema_version == 'warehouse_planner_evidence/v1'
    assert response.evidence_envelope.status == 'available'
    assert response.evidence_envelope.source_classes == ['canonical', 'observed_facts', 'bounded_staging']
    assert response.evidence_envelope.semantics == [
        'canonical_truth',
        'report_only_review_context',
        'not_full_coverage',
        'observed_report',
        'bounded_staging_evidence',
    ]
    assert response.evidence_envelope.report_only is True
    assert response.evidence_envelope.selected_system_only is True
    assert response.evidence_envelope.planner_truth_source_class == 'canonical'
    assert response.evidence_envelope.claims_canonical_truth is False
    assert response.evidence_envelope.claims_full_coverage is False
    assert response.evidence_summary.availability == 'report_only'
    assert response.evidence_summary.items[0].source == 'canonical'
    assert response.evidence_summary.items[1].source == 'observed'
    assert response.freshness.status == 'not_evaluated'
    assert response.freshness.evaluated_at == '2026-06-18T09:30:00Z'
    assert response.source_run.source_name == 'warehouse_reconciliation'
    assert response.source_run.run_key == 'warehouse/run-20260618.json'
    assert response.bounded_staging.status == 'available'
    assert response.bounded_staging.source_run_key == 'stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z'
    assert response.bounded_staging.source_sha256 == 'b256017814a1015fb24748c8027f1a00cba2f187a257ef3e0f9e3a6ba6e45984'
    assert response.bounded_staging.row_limit == 10000
    assert response.bounded_staging.bounded_staging_only is True
    assert response.bounded_staging.report_only is True

    fixtures = backend.DEVELOPMENT_FIXTURE_SYSTEMS
    monkeypatch.setattr(backend, 'resolve_runtime_warehouse_fixture', lambda id64: fixtures.get(id64))
    fixture_response = backend.build_warehouse_planner_evidence(12866676218109, live_result=live_result)
    assert any(item.source == 'warehouse_report_only' for item in fixture_response.evidence_summary.items)
    assert any('non-live example data' in warning.lower() for warning in fixture_response.warnings)
    assert fixture_response.evidence_envelope.status == 'available'
    assert fixture_response.evidence_envelope.source_classes == ['derived_report']
    assert fixture_response.evidence_envelope.semantics == ['report_only_review_context', 'not_full_coverage']
    assert fixture_response.bounded_staging.status == 'not_evaluated'
