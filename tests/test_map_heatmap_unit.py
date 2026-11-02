"""No-DB heatmap coverage selection, bounds, cache, and legacy SQL contracts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException


os.environ.setdefault('CORS_ORIGINS', 'http://test')

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / 'apps' / 'api' / 'src'))


class _FakeConn:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.queries: list[str] = []
        self.arguments: list[tuple] = []
        self.rows = rows if rows is not None else [
            {'cx': 0, 'cy': 0, 'cz': 0, 'n': 1, 'avg_score': 10, 'max_score': 20}
        ]

    async def fetch(self, query: str, *args, **kwargs) -> list[dict]:
        self.queries.append(query)
        self.arguments.append(args)
        return self.rows

    async def fetchrow(self, query: str, *args, **kwargs):
        # No published spatial pyramid in this no-DB fixture: the new
        # pyramid-resolution check (`_current_spatial_pyramid`) always finds
        # nothing, so these focused economy/legacy-lane tests keep exercising
        # exactly the legacy MV/live-aggregate path they were written for.
        # Deliberately untracked in self.queries/arguments -- those lists are
        # asserted against as "the" aggregate `.fetch()` call by index.
        return None


class _AcquireContext:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self.conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakePool:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.conn = _FakeConn(rows)

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.conn)


def _map_heatmap_handler():
    from routers.map import map_heatmap

    return map_heatmap.__wrapped__


# Calling `.__wrapped__` directly bypasses FastAPI's dependency injection, so
# unset `Query(...)` parameters keep their literal default expression (a
# `Query` sentinel object, not the value it would normally resolve to). Every
# call below must therefore pass every parameter explicitly; these are the
# "no bounds requested" values for the six added viewport-bounds parameters.
NO_BOUNDS = dict(min_x=None, max_x=None, min_y=None, max_y=None, min_z=None, max_z=None)


@pytest.mark.parametrize(
    ('economy', 'expected_column'),
    [
        ('HighTech', 'max_hightech'),
        ('High Tech', 'max_hightech'),
        ('high-tech', 'max_hightech'),
        ('tourism', 'max_tourism'),
    ],
)
async def test_map_heatmap_uses_canonical_economy_mv_column(economy, expected_column):
    pool = _FakePool()
    result = await _map_heatmap_handler()(
        request=None,
        voxel_size=200,
        min_systems=1,
        max_cells=50_000,
        coverage='truncated',
        economy=economy,
        **NO_BOUNDS,
        pool=pool,
        redis=None,
    )

    query = pool.conn.queries[0]
    assert expected_column in query
    assert f'{expected_column} AS max_score' in query
    assert f'AND {expected_column} IS NOT NULL' in query
    assert 'ORDER BY n DESC, cx, cy, cz' in query
    assert 'LIMIT $2' in query
    assert pool.conn.arguments == [(1, 50_001)]
    assert result['economy'] == economy
    assert result['truncated'] is False


async def test_map_heatmap_rejects_invalid_economy():
    pool = _FakePool()
    with pytest.raises(HTTPException) as exc_info:
        await _map_heatmap_handler()(
            request=None,
            voxel_size=200,
            min_systems=1,
            max_cells=50_000,
            coverage='truncated',
            economy='NotAnEconomy',
            **NO_BOUNDS,
            pool=pool,
            redis=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == 'Invalid economy: NotAnEconomy'
    assert pool.conn.queries == []


async def test_map_heatmap_caps_deterministically_and_reports_truncation():
    rows = [
        {'cx': index, 'cy': 0, 'cz': -index, 'n': 200 - index, 'avg_score': 50, 'max_score': 80}
        for index in range(101)
    ]
    pool = _FakePool(rows)
    result = await _map_heatmap_handler()(
        request=None,
        voxel_size=200,
        min_systems=1,
        max_cells=100,
        coverage='truncated',
        economy=None,
        **NO_BOUNDS,
        pool=pool,
        redis=None,
    )

    assert result['count'] == 100
    assert result['max_cells'] == 100
    assert result['truncated'] is True
    assert len(result['cells']) == 100
    assert result['cells'][0]['cx'] == 0
    assert result['cells'][-1]['cx'] == 99
    assert pool.conn.arguments == [(1, 101)]


async def test_map_heatmap_maximum_compact_json_stays_within_raw_response_budget():
    rows = [
        {
            'cx': 99_999_999,
            'cy': -99_999_999,
            'cz': 99_999_999,
            'n': 999_999_999,
            'avg_score': 100,
            'max_score': 100,
        }
        for _ in range(50_001)
    ]
    result = await _map_heatmap_handler()(
        request=None,
        voxel_size=200,
        min_systems=1,
        max_cells=50_000,
        coverage='truncated',
        economy=None,
        **NO_BOUNDS,
        pool=_FakePool(rows),
        redis=None,
    )

    payload_bytes = len(json.dumps(result, separators=(',', ':')).encode('utf-8'))
    assert result['truncated'] is True
    assert result['count'] == 50_000
    assert payload_bytes <= 8 * 1_048_576


LEVELS = [
    {'level': 6, 'cell_size_ly': 40.0},
    {'level': 5, 'cell_size_ly': 80.0},
    {'level': 4, 'cell_size_ly': 160.0},
]
PYRAMID = {
    'spatial_generation_id': 'spatial-test',
    'canonical_generation_id': 'canonical-test',
    'spatial_pyramid_version': 'pyramid_test',
    'source_system_count': 10_000,
    'coverage_at': None,
}


class _PyramidConn(_FakeConn):
    def __init__(self, counts, *, levels=None):
        super().__init__()
        self.counts = counts
        self.levels = LEVELS if levels is None else levels
        self.counted_levels = []
        self.selected_levels = []

    async def fetchrow(self, query, *args, **kwargs):
        self.queries.append(query)
        self.arguments.append(args)
        if 'current_spatial_generation' in query:
            return PYRAMID
        assert 'WHERE spatial_pyramid_version = $1' in query
        assert args == ('pyramid_test', 50.0)
        return self.levels[0] if self.levels else None

    async def fetch(self, query, *args, **kwargs):
        self.queries.append(query)
        self.arguments.append(args)
        if 'FROM v3_spatial.cell_level' in query:
            assert 'spatial_pyramid_version = $1 AND cell_size_ly >= $2' in query
            assert 'ORDER BY cell_size_ly, level' in query
            assert args == ('pyramid_test', 40.0)
            return self.levels
        level = args[2]
        self.selected_levels.append(level)
        return [
            {'origin_x_ly': float(i), 'origin_y_ly': 0.0, 'origin_z_ly': 0.0,
             'centroid_x_ly': float(i), 'centroid_y_ly': 0.0, 'centroid_z_ly': 0.0,
             'system_count': 1, 'representative_system_id64': i + 1}
            for i in range(min(self.counts[level], args[-1]))
        ]

    async def fetchval(self, query, *args, **kwargs):
        self.queries.append(query)
        self.arguments.append(args)
        self.counted_levels.append(args[2])
        assert 'SELECT count(*) FROM (' in query
        assert 'LIMIT $' in query
        assert args[-1] == 101
        return min(self.counts[args[2]], args[-1])


async def _pyramid_request(conn=None, **overrides):
    pool = _FakePool()
    if conn is not None:
        pool.conn = conn
    params = dict(request=None, voxel_size=50, min_systems=1, max_cells=100,
                  coverage='complete', economy=None, **NO_BOUNDS, pool=pool, redis=None)
    params.update(overrides)
    return await _map_heatmap_handler()(**params)


@pytest.mark.parametrize(
    ('counts', 'expected_level', 'visited'),
    [
        ({6: 100, 5: 50, 4: 20}, 6, [6]),
        ({6: 101, 5: 75, 4: 20}, 5, [6, 5]),
        ({6: 5_000_000, 5: 101, 4: 80}, 4, [6, 5, 4]),
        ({6: 0, 5: 0, 4: 0}, 6, [6]),
    ],
)
async def test_complete_density_uses_first_registered_level_that_fits(counts, expected_level, visited):
    conn = _PyramidConn(counts)
    result = await _pyramid_request(conn)
    assert result['requested_level'] == 6
    assert result['served_level'] == result['level'] == expected_level
    assert result['count'] == result['level_cell_count'] == counts[expected_level]
    assert result['coverage'] == 'complete'
    assert result['truncated'] is False
    assert conn.counted_levels == visited
    assert conn.selected_levels == [expected_level]
    assert 'system_count DESC' not in conn.queries[-1]


async def test_complete_density_fails_closed_when_even_coarsest_exceeds_budget():
    conn = _PyramidConn({6: 1000, 5: 500, 4: 101})
    result = await _pyramid_request(conn)
    assert result.status_code == 503
    assert result.media_type == 'application/problem+json'
    assert conn.counted_levels == [6, 5, 4]
    assert conn.selected_levels == []


async def test_complete_density_count_timeout_returns_problem_json(monkeypatch):
    conn = _PyramidConn({6: 1})

    async def timed_out(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(conn, 'fetchval', timed_out)
    result = await _pyramid_request(conn)
    assert result.status_code == 503
    assert result.media_type == 'application/problem+json'
    assert conn.selected_levels == []


@pytest.mark.parametrize('conn', [None, _PyramidConn({}, levels=[])])
async def test_complete_density_requires_published_pyramid_and_registered_level(conn):
    result = await _pyramid_request(conn)
    assert result.status_code == 503
    assert result.media_type == 'application/problem+json'
    assert json.loads(result.body)['status'] == 503


async def test_complete_density_count_and_cells_share_bounds_and_min_systems():
    conn = _PyramidConn({6: 4})
    bounds = dict(min_x=-123.5, max_x=200, min_y=-50, max_y=60, min_z=-70, max_z=80)
    result = await _pyramid_request(conn, min_systems=7, **bounds)
    assert result['bounds'] == bounds
    count_query, cell_query = conn.queries[-2:]
    assert conn.arguments[-2] == conn.arguments[-1] == (
        'spatial-test', 'pyramid_test', 6, 7, -123.5, 200, -50, 60, -70, 80, 101,
    )
    for query in (count_query, cell_query):
        assert 'spatial_generation_id = $1' in query
        assert 'spatial_pyramid_version = $2' in query
        assert 'level = $3' in query
        assert 'system_count >= $4' in query
        for parameter, (axis, comparison) in enumerate(
            [(axis, comparison) for axis in 'xyz' for comparison in ('>=', '<=')], start=5,
        ):
            assert f'centroid_{axis}_ly {comparison} ${parameter}' in query
        assert '-123.5' not in query


async def test_legacy_pyramid_cut_preserves_popularity_and_unknown_total():
    conn = _PyramidConn({6: 120})
    result = await _pyramid_request(conn, coverage='truncated')
    assert result['count'] == 100
    assert result['truncated'] is True
    assert result['coverage'] == 'truncated'
    assert result['level_cell_count'] is None
    assert result['requested_level'] == result['served_level'] == 6
    assert conn.counted_levels == []
    assert 'ORDER BY system_count DESC' in conn.queries[-1]


async def test_complete_density_cache_distinguishes_mode_and_exact_bounds(monkeypatch):
    from routers import map as map_router

    keys = []

    async def read_cache(key, redis):
        keys.append(key)
        return {'cached': True}

    monkeypatch.setattr(map_router, 'cache_get', read_cache)
    await _pyramid_request(coverage='truncated', min_x=0.0001)
    await _pyramid_request(coverage='complete', min_x=0.0001)
    await _pyramid_request(coverage='complete', min_x=0.0002)
    assert len(set(keys)) == 3


@pytest.mark.parametrize('overrides', [
    {'min_x': float('nan')}, {'max_y': float('inf')}, {'min_z': 5, 'max_z': 4},
    {'economy': 'Tourism'},
])
async def test_complete_density_rejects_invalid_bounds_and_economy(overrides):
    with pytest.raises(HTTPException) as exc:
        await _pyramid_request(**overrides)
    assert exc.value.status_code == 422
