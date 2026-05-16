from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from colony_planner.layout_import_models import LayoutImportResponse, LayoutImportSummary
from colony_planner.layout_import_provider import get_layout_import_provider
from routers.colony_planner import router


class FakeProvider:
    def __init__(self, response: LayoutImportResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[int, str]] = []

    async def import_layout(self, system_id64: int, source: str) -> LayoutImportResponse:
        self.calls.append((system_id64, source))
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def response(status='success', warnings=None, errors=None):
    warnings = warnings or []
    errors = errors or []
    return LayoutImportResponse(
        system_id64=123,
        source='spansh',
        status=status,
        fetched_at=datetime(2026, 5, 16, tzinfo=UTC),
        summary=LayoutImportSummary(
            bodies_found=3,
            stations_found=2,
            bodies_upserted=0,
            stations_upserted=0,
            warnings_count=len(warnings),
        ),
        warnings=warnings,
        errors=errors,
    )


async def post_import(provider: FakeProvider, payload=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_layout_import_provider] = lambda: provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        return await client.post('/api/colony-planner/system/123/import-layout', json=payload or {})


@pytest.mark.asyncio
async def test_layout_import_endpoint_returns_success_payload_shape():
    provider = FakeProvider(response())

    result = await post_import(provider)

    assert result.status_code == 200
    body = result.json()
    assert body == {
        'system_id64': 123,
        'source': 'spansh',
        'status': 'success',
        'fetched_at': '2026-05-16T00:00:00Z',
        'summary': {
            'bodies_found': 3,
            'stations_found': 2,
            'bodies_upserted': 0,
            'stations_upserted': 0,
            'warnings_count': 0,
        },
        'warnings': [],
        'errors': [],
    }
    assert provider.calls == [(123, 'spansh')]


@pytest.mark.asyncio
async def test_layout_import_endpoint_returns_failed_payload_on_provider_error():
    provider = FakeProvider(error=RuntimeError('spansh timeout'))

    result = await post_import(provider, {'source': 'spansh'})

    assert result.status_code == 200
    body = result.json()
    assert body['system_id64'] == 123
    assert body['source'] == 'spansh'
    assert body['status'] == 'failed'
    assert body['summary'] == {
        'bodies_found': 0,
        'stations_found': 0,
        'bodies_upserted': 0,
        'stations_upserted': 0,
        'warnings_count': 0,
    }
    assert body['warnings'] == []
    assert body['errors'] == ['spansh timeout']
    assert provider.calls == [(123, 'spansh')]


@pytest.mark.asyncio
async def test_layout_import_endpoint_returns_partial_payload_when_warnings_exist():
    provider = FakeProvider(response(status='partial', warnings=['Body names need review']))

    result = await post_import(provider)

    assert result.status_code == 200
    body = result.json()
    assert body['status'] == 'partial'
    assert body['summary']['warnings_count'] == 1
    assert body['warnings'] == ['Body names need review']


@pytest.mark.asyncio
async def test_layout_import_endpoint_does_not_call_simulation_or_optimiser(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('simulation or optimiser must not run during layout import')

    monkeypatch.setattr('optimiser.candidate_generator.generate_candidates', forbidden)
    monkeypatch.setattr('simulation.build_preview.simulate_build_preview', forbidden)
    provider = FakeProvider(response())

    result = await post_import(provider)

    assert result.status_code == 200
    assert result.json()['status'] == 'success'
    assert provider.calls == [(123, 'spansh')]
