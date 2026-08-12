from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from edfinder_api.routes.api_models import (  # noqa: E402
    ExpeditionImport,
    PlannedRouteImport,
    RouteWaypoint,
)
from edfinder_api.routes.store import _detail_from_rows, _journal_waypoints  # noqa: E402
from edfinder_api.routers import routes as routes_router  # noqa: E402


def _route_row(**overrides):
    return {
        'route_id': UUID('12345678-1234-5678-1234-567812345678'),
        'name': 'Test route',
        'source': 'spansh',
        'type': 'spansh',
        'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'updated_at': datetime(2026, 1, 2, tzinfo=timezone.utc),
        'metadata': {'route_mode': 'neutron'},
        **overrides,
    }


def _waypoint(order: int, name: str, x: float, distance: float | None):
    return {
        'order': order,
        'system_id64': order + 1,
        'system_name': name,
        'x': x,
        'y': 0.0,
        'z': 0.0,
        'distance_from_previous': distance,
        'bookmarked': False,
        'notes': None,
    }


def _request(path: str = '/api/routes/list') -> Request:
    return Request({
        'type': 'http', 'method': 'GET', 'path': path, 'headers': [],
        'client': ('127.0.0.1', 12345),
    })


def _detail():
    return _detail_from_rows(
        _route_row(),
        [],
        [_waypoint(0, 'Sol', 0, None)],
    )


def test_spansh_import_accepts_exact_neutron_and_carrier_modes():
    waypoint = RouteWaypoint.model_validate(_waypoint(0, 'Sol', 0, None))
    for mode in ('exact', 'neutron', 'carrier'):
        request = PlannedRouteImport.model_validate({
            'commander_id': 'sync-key-1234567890',
            'name': f'{mode} route',
            'route_mode': mode,
            'waypoints': [waypoint.model_dump()],
        })
        assert request.route_mode == mode


def test_spansh_import_rejects_partial_coordinates():
    with pytest.raises(ValidationError):
        RouteWaypoint.model_validate({
            'order': 0,
            'system_name': 'Broken',
            'x': 1,
            'bookmarked': False,
        })


def test_expedition_bookmarks_are_structured_metadata():
    request = ExpeditionImport.model_validate({
        'commander_id': 'sync-key-1234567890',
        'name': 'Distant Worlds Test',
        'organizer': 'Pilots Federation',
        'description': 'A long expedition.',
        'departure_at': '2026-08-20T18:00:00Z',
        'waypoints': [{
            **_waypoint(0, 'Beagle Point', -1111, None),
            'bookmarked': True,
            'notes': 'Meet at the beacon',
        }],
    })
    assert request.waypoints[0].bookmarked is True
    assert request.waypoints[0].notes == 'Meet at the beacon'
    assert request.departure_at is not None and request.departure_at.tzinfo == timezone.utc


def test_navroute_parser_preserves_route_waypoint_coordinates_and_bookmarks():
    parsed = _journal_waypoints({
        'Route': [
            {'StarSystem': 'Sol', 'SystemAddress': '10477373803', 'StarPos': [0, 0, 0]},
            {'StarSystem': 'Skaudai AM-B d14-138', 'SystemAddress': '999', 'StarPos': [1, 2, 3], 'Bookmarked': True},
        ],
    })
    assert [item['system_name'] for item in parsed] == ['Sol', 'Skaudai AM-B d14-138']
    assert parsed[1]['bookmarked'] is True
    assert parsed[1]['x'] == 1.0


def test_route_comparison_matches_planned_actual_and_computes_remaining_distance():
    waypoints = [
        _waypoint(0, 'Sol', 0, None),
        _waypoint(1, 'Waypoint B', 10, 10),
        _waypoint(2, 'Waypoint C', 30, 20),
    ]
    event_rows = [{
        'system_id64': 1,
        'system_name': 'Sol',
        'x': 0.0,
        'y': 0.0,
        'z': 0.0,
        'visited_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'distance_from_planned': 0.0,
        'event_order': 0,
        'context': {'event_type': 'FSDJump'},
    }]
    detail = _detail_from_rows(_route_row(), event_rows, waypoints)
    assert detail.completion_percent == pytest.approx(33.3)
    assert detail.current_waypoint_index == 1
    assert detail.remaining_distance == 30.0
    assert [item.visited for item in detail.planned_actual_alignment] == [True, False, False]


def test_personal_history_supports_chronological_events_across_months():
    waypoints = [_waypoint(0, 'January', 0, None), _waypoint(1, 'August', 100, 100)]
    events = [
        {
            'system_id64': 1,
            'system_name': 'January',
            'x': 0.0, 'y': 0.0, 'z': 0.0,
            'visited_at': datetime(2026, 1, 4, tzinfo=timezone.utc),
            'distance_from_planned': None, 'event_order': 0, 'context': {},
        },
        {
            'system_id64': 2,
            'system_name': 'August',
            'x': 100.0, 'y': 0.0, 'z': 0.0,
            'visited_at': datetime(2026, 8, 12, tzinfo=timezone.utc),
            'distance_from_planned': None, 'event_order': 1, 'context': {},
        },
    ]
    detail = _detail_from_rows(_route_row(type='personal', source='journal'), events, waypoints)
    assert [event.order for event in detail.events] == [0, 1]
    assert detail.events[0].visited_at.startswith('2026-01')
    assert detail.events[1].visited_at.startswith('2026-08')


def test_route_migration_is_manifested_and_normalized():
    sql = (ROOT / 'sql' / '047_routes.sql').read_text(encoding='utf-8')
    manifest = (ROOT / 'sql' / 'migration-manifest.txt').read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS routes' in sql
    assert 'CREATE TABLE IF NOT EXISTS route_events' in sql
    assert "CHECK (type IN ('personal', 'journal', 'spansh', 'expedition'))" in sql
    assert 'event_order' in sql and 'distance_from_planned' in sql
    assert '047_routes.sql' in manifest


@pytest.mark.asyncio
async def test_route_endpoints_preserve_commander_scope_and_filters(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    async def list_routes(_pool, commander_id, route_type=None):
        calls.append((commander_id, route_type))
        detail = _detail()
        return {'routes': [detail.model_dump(exclude={'waypoints', 'events', 'planned_actual_alignment'})], 'count': 1}

    monkeypatch.setattr(routes_router.store, 'list_routes', list_routes)
    result = await routes_router.list_commander_routes(
        _request(), 'sync-key-1234567890', 'spansh', pool=object(),
    )
    expeditions = await routes_router.list_expeditions(
        _request('/api/routes/expeditions'), 'sync-key-1234567890', pool=object(),
    )
    assert result['count'] == 1
    assert expeditions['count'] == 1
    assert calls == [
        ('sync-key-1234567890', 'spansh'),
        ('sync-key-1234567890', 'expedition'),
    ]


@pytest.mark.asyncio
async def test_route_detail_and_personal_trail_endpoints(monkeypatch):
    detail = _detail()

    async def get_route(_pool, route_id, commander_id):
        assert route_id == detail.route_id
        assert commander_id == 'sync-key-1234567890'
        return detail

    async def get_trail(_pool, commander_id, from_date, to_date):
        assert commander_id == 'sync-key-1234567890'
        assert from_date is not None and to_date is not None
        return detail

    monkeypatch.setattr(routes_router.store, 'get_route', get_route)
    monkeypatch.setattr(routes_router.store, 'get_personal_trail', get_trail)
    returned_detail = await routes_router.get_route_detail(
        _request(f'/api/routes/{detail.route_id}'), detail.route_id,
        'sync-key-1234567890', pool=object(),
    )
    trail = await routes_router.get_personal_jump_trail(
        _request('/api/routes/trail'), 'sync-key-1234567890',
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 8, 31, tzinfo=timezone.utc), pool=object(),
    )
    assert returned_detail.route_id == detail.route_id
    assert trail.route_id == detail.route_id
