"""Focused no-DB coverage for map heatmap economy SQL selection."""
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
        economy=economy,
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
            economy='NotAnEconomy',
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
        economy=None,
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
        economy=None,
        pool=_FakePool(rows),
        redis=None,
    )

    payload_bytes = len(json.dumps(result, separators=(',', ':')).encode('utf-8'))
    assert result['truncated'] is True
    assert result['count'] == 50_000
    assert payload_bytes <= 8 * 1_048_576
