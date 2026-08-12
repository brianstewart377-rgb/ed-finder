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

os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')

from powerplay.api_models import (  # noqa: E402
    CommanderPowerplayResponse,
    PowerplayHistoryResponse,
    PowerplayImportReceipt,
    PowerplayImportRequest,
    PowerplaySystemsResponse,
)
from routers import powerplay as router_module  # noqa: E402


def request() -> Request:
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})


class FakeStore:
    keys: list[str] = []

    @classmethod
    async def import_powerplay_events(cls, pool, body):
        cls.keys.append(body.commander_key)
        return PowerplayImportReceipt(
            commander_key=body.commander_key,
            events_received=len(body.events),
            system_observations_staged=1,
            commander_events_staged=0,
            duplicates_skipped=0,
            cycles_versioned=1,
        )

    @classmethod
    async def get_current_systems(cls, pool, commander_key, *, limit):
        cls.keys.append(commander_key)
        return PowerplaySystemsResponse(
            commander_key=commander_key, systems=[], count=0, truncated=False,
        )

    @classmethod
    async def get_commander_state(cls, pool, commander_key):
        cls.keys.append(commander_key)
        return CommanderPowerplayResponse(
            commander_key=commander_key,
            cycle_start='2025-03-20T07:00:00+00:00',
        )

    @classmethod
    async def get_history(cls, pool, commander_key, *, cycle_limit, change_limit):
        cls.keys.append(commander_key)
        return PowerplayHistoryResponse(commander_key=commander_key, cycles=[], change_events=[])


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    FakeStore.keys = []
    monkeypatch.setattr(router_module.store, 'import_powerplay_events', FakeStore.import_powerplay_events)
    monkeypatch.setattr(router_module.store, 'get_current_systems', FakeStore.get_current_systems)
    monkeypatch.setattr(router_module.store, 'get_commander_state', FakeStore.get_commander_state)
    monkeypatch.setattr(router_module.store, 'get_history', FakeStore.get_history)


@pytest.mark.asyncio
async def test_powerplay_endpoints_are_commander_scoped():
    alice = 'alice-powerplay-1234567890'
    bob = 'bob-powerplay-123456789012'
    systems = await router_module.powerplay_systems(request(), alice, 100, object())
    commander = await router_module.powerplay_commander(request(), bob, object())
    history = await router_module.powerplay_history(request(), alice, 52, 2_000, object())
    assert systems.commander_key == alice
    assert commander.commander_key == bob
    assert history.commander_key == alice
    assert FakeStore.keys == [alice, bob, alice]


@pytest.mark.asyncio
async def test_import_endpoint_accepts_raw_anomalous_values():
    body = PowerplayImportRequest.model_validate({
        'commander_key': 'alice-powerplay-1234567890',
        'source': 'journal',
        'source_version': 'parser-v1',
        'events': [{
            'observation_key': 'system-observation-key-v1',
            'event_type': 'Location',
            'observed_at': '2025-03-20T07:00:00Z',
            'source_payload': {
                'event': 'Location',
                'SystemAddress': '10477373803',
                'PowerplayStateControlProgress': 5000,
                'PowerplayStateReinforcement': -1,
            },
        }],
    })
    receipt = await router_module.import_powerplay_journal(request(), body, object())
    assert receipt.events_received == 1
    assert receipt.system_observations_staged == 1
