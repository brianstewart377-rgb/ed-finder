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
    ):
        self.system = system
        self.body_count = body_count
        self.station_count = station_count
        self.has_station_links = has_station_links
        self.linked_station_count = linked_station_count
        self.latest_canonical_at = latest_canonical_at

    async def fetchrow(self, query: str, *args):
        if 'SELECT id64, name FROM systems' in query:
            return self.system
        raise AssertionError(f'Unexpected fetchrow query: {query}')

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
    assert result.freshness_status == 'not_evaluated'
    assert result.evaluated_at == '2026-06-18T09:30:00Z'
    assert result.manual_review_required is True
    assert any(item.source == 'canonical' for item in result.items)
    assert any(item.source == 'observed' for item in result.items)
    assert any('Lave' in item.summary for item in result.items if item.source == 'canonical')
    assert any('service_presence:2' in item.summary for item in result.items if item.source == 'observed')
    assert any('warehouse join exists' in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
async def test_stage23a_live_provider_keeps_unknown_systems_unavailable(monkeypatch: pytest.MonkeyPatch):
    async def _observed_summary(_pool, _id64: int):
        raise AssertionError('Observed summary should not run for missing systems')

    monkeypatch.setattr(provider, 'observed_fact_summary', _observed_summary)
    pool = _FakePool(_FakeConnection(system=None))

    result = await provider.load_live_planner_evidence(pool, 42)

    assert result.availability == 'unavailable'
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
        warnings=['Per-system warehouse evidence is not included until a safe selected-system warehouse join exists; any source-run metadata remains review context only.'],
    )

    response = backend.build_warehouse_planner_evidence(9466842275401, live_result=live_result)

    assert response.schema_version == 'warehouse_planner_evidence/v1'
    assert response.evidence_summary.availability == 'report_only'
    assert response.evidence_summary.items[0].source == 'canonical'
    assert response.evidence_summary.items[1].source == 'observed'
    assert response.freshness.status == 'not_evaluated'
    assert response.freshness.evaluated_at == '2026-06-18T09:30:00Z'
    assert response.source_run.source_name == 'warehouse_reconciliation'
    assert response.source_run.run_key == 'warehouse/run-20260618.json'

    fixtures = backend.DEVELOPMENT_FIXTURE_SYSTEMS
    monkeypatch.setattr(backend, 'resolve_runtime_warehouse_fixture', lambda id64: fixtures.get(id64))
    fixture_response = backend.build_warehouse_planner_evidence(12866676218109, live_result=live_result)
    assert any(item.source == 'warehouse_report_only' for item in fixture_response.evidence_summary.items)
    assert any('non-live example data' in warning.lower() for warning in fixture_response.warnings)
